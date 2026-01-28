from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.data_fetch import latest_quote
from src.pipeline import run_pipeline

from .schemas import Config, ConfigUpdate, TradeRequest
from .state import (
    apply_auto_trade,
    build_state,
    buy,
    compute_signals,
    default_state,
    ensure_portfolio,
    now_iso,
    sell,
    update_portfolio,
)
from .store import Store

BASE_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = BASE_DIR / "static"

CONFIG_KEY = "config"
STATE_KEY = "state"

app = FastAPI(title="Market Pulse API")
cors_raw = os.getenv("CORS_ORIGINS", "").strip()
if cors_raw:
    cors_origins = [origin.strip() for origin in cors_raw.split(",") if origin.strip()]
else:
    cors_origins = ["*"]
allow_credentials = False if cors_origins == ["*"] else True
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

store = Store(os.getenv("REDIS_URL"))
update_lock = asyncio.Lock()
shutdown_event = asyncio.Event()

DEFAULT_CONFIG = Config().dict()


class ConnectionManager:
    def __init__(self) -> None:
        self.active = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active:
            self.active.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]) -> None:
        for socket in list(self.active):
            try:
                await socket.send_json(message)
            except Exception:
                self.disconnect(socket)


manager = ConnectionManager()


def merge_config(data: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = DEFAULT_CONFIG.copy()
    if isinstance(data, dict):
        for key, value in data.items():
            if key in merged and value is not None:
                merged[key] = value
    return merged


async def get_config() -> Dict[str, Any]:
    data = await store.get_json(CONFIG_KEY)
    merged = merge_config(data)
    if data != merged:
        await store.set_json(CONFIG_KEY, merged)
    return merged


async def get_state() -> Dict[str, Any]:
    state = await store.get_json(STATE_KEY)
    if not state:
        state = default_state()
        await store.set_json(STATE_KEY, state)
    return state


async def fetch_live_price(ticker: str) -> Optional[float]:
    try:
        quote = await asyncio.to_thread(latest_quote, ticker)
    except Exception:
        return None
    if quote is None or "close" not in quote:
        return None
    try:
        return float(quote["close"])
    except Exception:
        return None


async def refresh_pipeline(config: Dict[str, Any], force_retrain: bool = False) -> Dict[str, Any]:
    async with update_lock:
        state = await get_state()
        portfolio = ensure_portfolio(state.get("portfolio"))
        try:
            result = await asyncio.to_thread(
                run_pipeline,
                ticker=config["ticker"],
                intraday_days=config["intraday_days"],
                invest_amount=config["invest_amount"],
                force_retrain=force_retrain,
                max_points=config["max_points"],
                train_window=config["train_window"] or None,
                minute_horizon=config["minute_horizon"],
                long_horizon_steps=config["long_horizon_steps"],
                execute_trades=False,
            )
        except Exception as exc:
            state["status"] = "error"
            state["error"] = str(exc)
            state["updated_at"] = now_iso()
            await store.set_json(STATE_KEY, state)
            return state

        live_price = await fetch_live_price(config["ticker"])
        current_price = live_price if live_price is not None else result.get("latest_price")
        state = build_state(result, current_price, portfolio, config)
        state = apply_auto_trade(state, config)
        await store.set_json(STATE_KEY, state)
        return state


async def refresh_price_only(config: Dict[str, Any]) -> Dict[str, Any]:
    async with update_lock:
        state = await get_state()
        if state.get("status") == "initializing":
            return state
        live_price = await fetch_live_price(config["ticker"])
        if live_price is None:
            return state
        state["latest_price"] = live_price
        portfolio = ensure_portfolio(state.get("portfolio"))
        portfolio = update_portfolio(portfolio, live_price, max_points=config["chart_points"])
        state["portfolio"] = portfolio
        state["signals"] = compute_signals(state, config, portfolio, live_price)
        state["updated_at"] = now_iso()
        state = apply_auto_trade(state, config)
        await store.set_json(STATE_KEY, state)
        return state


async def update_loop() -> None:
    last_model = 0.0
    last_price = 0.0
    while not shutdown_event.is_set():
        config = await get_config()
        now = time.monotonic()
        if now - last_model >= config["model_refresh_seconds"]:
            state = await refresh_pipeline(config)
            await manager.broadcast(state)
            last_model = now
        if now - last_price >= config["price_refresh_seconds"]:
            state = await refresh_price_only(config)
            await manager.broadcast(state)
            last_price = now
        await asyncio.sleep(1)


@app.on_event("startup")
async def startup() -> None:
    await store.connect()
    existing_config = await store.get_json(CONFIG_KEY)
    if not existing_config:
        await store.set_json(CONFIG_KEY, DEFAULT_CONFIG)
    existing_state = await store.get_json(STATE_KEY)
    if not existing_state:
        await store.set_json(STATE_KEY, default_state())
    asyncio.create_task(update_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    shutdown_event.set()
    await store.close()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.get("/api/config")
async def api_get_config() -> Dict[str, Any]:
    return await get_config()


@app.post("/api/config")
async def api_update_config(update: ConfigUpdate) -> Dict[str, Any]:
    config = await get_config()
    payload = update.dict(exclude_none=True)
    config.update(payload)
    await store.set_json(CONFIG_KEY, config)
    state = await refresh_pipeline(config)
    await manager.broadcast(state)
    return config


@app.post("/api/retrain")
async def api_retrain() -> Dict[str, Any]:
    config = await get_config()
    state = await refresh_pipeline(config, force_retrain=True)
    await manager.broadcast(state)
    return {"status": state.get("status"), "updated_at": state.get("updated_at")}


@app.get("/api/state")
async def api_get_state() -> Dict[str, Any]:
    return await get_state()


@app.post("/api/trade/buy")
async def api_trade_buy(request: TradeRequest) -> Dict[str, Any]:
    async with update_lock:
        config = await get_config()
        state = await get_state()
        price = state.get("latest_price") or await fetch_live_price(config["ticker"])
        amount = request.amount if request.amount is not None else config["invest_amount"]
        if not price or amount <= 0:
            raise HTTPException(status_code=400, detail="Invalid price or amount")
        portfolio = ensure_portfolio(state.get("portfolio"))
        portfolio = buy(portfolio, float(price), float(amount))
        state["portfolio"] = portfolio
        state["signals"] = compute_signals(state, config, portfolio, price)
        state["updated_at"] = now_iso()
        await store.set_json(STATE_KEY, state)
    await manager.broadcast(state)
    return state


@app.post("/api/trade/sell")
async def api_trade_sell() -> Dict[str, Any]:
    async with update_lock:
        config = await get_config()
        state = await get_state()
        price = state.get("latest_price") or await fetch_live_price(config["ticker"])
        if not price:
            raise HTTPException(status_code=400, detail="No price available")
        portfolio = ensure_portfolio(state.get("portfolio"))
        portfolio = sell(portfolio, float(price))
        state["portfolio"] = portfolio
        state["signals"] = compute_signals(state, config, portfolio, price)
        state["updated_at"] = now_iso()
        await store.set_json(STATE_KEY, state)
    await manager.broadcast(state)
    return state


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await manager.connect(websocket)
    try:
        state = await get_state()
        await websocket.send_json(state)
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)
