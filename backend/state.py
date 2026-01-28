from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_iso(value: Any) -> str:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass
    return str(value)


def _is_finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except Exception:
        return False


def _split_holdout_predictions(
    predicted: Any, train_frac: float = 0.8, val_frac: float = 0.1
) -> tuple[Any, Any]:
    if predicted is None:
        return None, None
    if hasattr(predicted, "empty") and predicted.empty:
        return predicted, predicted
    if not 0 < train_frac < 1:
        return predicted, predicted
    if not 0 <= val_frac < 1:
        return predicted, predicted
    try:
        total = len(predicted)
    except Exception:
        return predicted, predicted
    if total == 0:
        return predicted, predicted
    train_end = int(total * train_frac)
    val_end = int(total * (train_frac + val_frac))
    if val_end < train_end:
        val_end = train_end
    if val_end > total:
        val_end = total
    try:
        validation = predicted.iloc[train_end:val_end]
        testing = predicted.iloc[val_end:]
    except Exception:
        return predicted, predicted
    return validation, testing


def _is_empty_series(series: Any) -> bool:
    if series is None:
        return True
    if hasattr(series, "empty"):
        try:
            return bool(series.empty)
        except Exception:
            return False
    return False


def default_portfolio() -> Dict[str, Any]:
    return {
        "cash": 0.0,
        "units": 0.0,
        "invested_amount": 0.0,
        "last_bought_price": None,
        "profit": 0.0,
        "portfolio_value": 0.0,
        "withdrawn": False,
        "withdraw_value": 0.0,
        "withdraw_profit": 0.0,
        "profit_points": [],
        "events": [],
    }


def default_state() -> Dict[str, Any]:
    return {
        "status": "initializing",
        "error": None,
        "ticker": None,
        "latest_price": None,
        "next_minute_price": None,
        "next_hour_price": None,
        "minute_mae": None,
        "minute_mse": None,
        "minute_rmse": None,
        "minute_r2": None,
        "hour_mae": None,
        "hour_mse": None,
        "hour_rmse": None,
        "hour_r2": None,
        "series": {"actual": [], "predicted": [], "forecast": []},
        "portfolio": default_portfolio(),
        "signals": {"buy": False, "sell": False},
        "updated_at": now_iso(),
    }


def ensure_portfolio(portfolio: Any) -> Dict[str, Any]:
    base = default_portfolio()
    if isinstance(portfolio, dict):
        base.update(portfolio)
    if base.get("profit_points") is None:
        base["profit_points"] = []
    if base.get("events") is None:
        base["events"] = []
    return base


def _trim_list(items: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    if limit <= 0:
        return items
    if len(items) <= limit:
        return items
    return items[-limit:]


def record_event(
    portfolio: Dict[str, Any],
    kind: str,
    price: float,
    units: float,
    amount: float,
    profit: Optional[float] = None,
) -> None:
    events = list(portfolio.get("events", []))
    event = {
        "timestamp": now_iso(),
        "kind": kind,
        "price": round(price, 4),
        "units": round(units, 6),
        "amount": round(amount, 2),
    }
    if profit is not None:
        event["profit"] = round(profit, 2)
    events.append(event)
    portfolio["events"] = _trim_list(events, 200)


def buy(portfolio: Dict[str, Any], price: float, amount: float) -> Dict[str, Any]:
    portfolio = ensure_portfolio(portfolio)
    if not _is_finite(price) or price <= 0:
        return portfolio
    if not _is_finite(amount) or amount <= 0:
        return portfolio
    units = amount / price
    portfolio["units"] = round(units, 6)
    portfolio["invested_amount"] = round(amount, 2)
    portfolio["last_bought_price"] = round(price, 4)
    portfolio["withdrawn"] = False
    portfolio["withdraw_value"] = 0.0
    portfolio["withdraw_profit"] = 0.0
    portfolio["profit"] = 0.0
    portfolio["portfolio_value"] = round(amount, 2)
    portfolio["profit_points"] = []
    record_event(portfolio, "buy", price, units, amount)
    return portfolio


def sell(portfolio: Dict[str, Any], price: float) -> Dict[str, Any]:
    portfolio = ensure_portfolio(portfolio)
    units = float(portfolio.get("units") or 0.0)
    if units <= 0:
        return portfolio
    if not _is_finite(price) or price <= 0:
        return portfolio
    revenue = units * price
    profit = revenue - float(portfolio.get("invested_amount") or 0.0)
    portfolio["units"] = 0.0
    portfolio["withdrawn"] = True
    portfolio["withdraw_value"] = round(revenue, 2)
    portfolio["withdraw_profit"] = round(profit, 2)
    portfolio["profit"] = round(profit, 2)
    portfolio["portfolio_value"] = 0.0
    record_event(portfolio, "sell", price, units, revenue, profit)
    return portfolio


def update_portfolio(
    portfolio: Dict[str, Any], current_price: float, max_points: int = 500
) -> Dict[str, Any]:
    portfolio = ensure_portfolio(portfolio)
    units = float(portfolio.get("units") or 0.0)
    if units <= 0 or not _is_finite(current_price):
        return portfolio
    value = units * float(current_price)
    profit = value - float(portfolio.get("invested_amount") or 0.0)
    portfolio["profit"] = round(profit, 2)
    portfolio["portfolio_value"] = round(value, 2)
    history = list(portfolio.get("profit_points", []))
    history.append(
        {
            "timestamp": now_iso(),
            "profit": round(profit, 2),
            "portfolio_value": round(value, 2),
        }
    )
    portfolio["profit_points"] = _trim_list(history, max_points)
    return portfolio


def series_to_points(series: Any, limit: Optional[int]) -> List[Dict[str, Any]]:
    if series is None:
        return []
    try:
        if limit is None or limit <= 0:
            items = series.items()
        else:
            items = series.tail(limit).items()
    except Exception:
        return []
    points = []
    for ts, val in items:
        if not _is_finite(val):
            continue
        points.append({"timestamp": _to_iso(ts), "value": float(val)})
    return points


def forecast_to_points(points: Any) -> List[Dict[str, Any]]:
    if not points:
        return []
    result = []
    for point in points:
        if not isinstance(point, dict):
            continue
        price = point.get("price")
        if not _is_finite(price):
            continue
        result.append(
            {
                "timestamp": _to_iso(point.get("timestamp")),
                "value": float(price),
                "label": str(point.get("label", "")),
            }
        )
    return result


def compute_signals(
    state: Dict[str, Any],
    config: Dict[str, Any],
    portfolio: Dict[str, Any],
    current_price: Any = None,
) -> Dict[str, bool]:
    price = current_price if _is_finite(current_price) else state.get("latest_price")
    if not _is_finite(price):
        return {"buy": False, "sell": False}
    price = float(price)
    next_hour = state.get("next_hour_price")
    hour_mae = state.get("hour_mae")
    next_minute = state.get("next_minute_price")
    minute_mae = state.get("minute_mae")
    buy_mult = float(config.get("buy_multiplier", 1.5))
    sell_mult = float(config.get("sell_multiplier", 1.2))
    buy_signal = False
    sell_signal = False
    if _is_finite(next_hour) and _is_finite(hour_mae):
        buy_signal = (float(next_hour) - float(hour_mae)) > buy_mult * price
    last_bought = portfolio.get("last_bought_price") or price
    if _is_finite(next_minute) and _is_finite(minute_mae) and _is_finite(last_bought):
        sell_signal = (float(next_minute) - float(minute_mae)) > sell_mult * float(last_bought)
    return {"buy": bool(buy_signal), "sell": bool(sell_signal)}


def build_state(
    result: Dict[str, Any],
    current_price: float,
    portfolio: Dict[str, Any],
    config: Dict[str, Any],
) -> Dict[str, Any]:
    chart_points = int(config.get("chart_points", 500))
    actual_series = result.get("historical_prices")
    if _is_empty_series(actual_series):
        actual_series = result.get("minute_prices")
    predicted_series = result.get("minute_predictions")
    train_frac = float(config.get("train_frac", 0.8))
    val_frac = float(config.get("val_frac", 0.1))
    validation_series, test_series = _split_holdout_predictions(
        predicted_series, train_frac=train_frac, val_frac=val_frac
    )
    state = {
        "status": "ok",
        "error": None,
        "ticker": result.get("ticker", config.get("ticker")),
        "latest_price": float(current_price)
        if _is_finite(current_price)
        else result.get("latest_price"),
        "next_minute_price": result.get("next_minute_price"),
        "next_hour_price": result.get("next_hour_price"),
        "minute_mae": result.get("minute_mae"),
        "minute_mse": result.get("minute_mse"),
        "minute_rmse": result.get("minute_rmse"),
        "minute_r2": result.get("minute_r2"),
        "hour_mae": result.get("hour_mae"),
        "hour_mse": result.get("hour_mse"),
        "hour_rmse": result.get("hour_rmse"),
        "hour_r2": result.get("hour_r2"),
        "series": {
            "actual": series_to_points(actual_series, None),
            "predicted_validation": series_to_points(validation_series, None),
            "predicted_test": series_to_points(test_series, None),
            "forecast": forecast_to_points(result.get("forecast_points", [])),
        },
        "updated_at": now_iso(),
    }
    portfolio = update_portfolio(portfolio, state.get("latest_price"), max_points=chart_points)
    state["portfolio"] = portfolio
    state["signals"] = compute_signals(state, config, portfolio, state.get("latest_price"))
    return state


def apply_auto_trade(state: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    if not config.get("auto_trade"):
        return state
    portfolio = ensure_portfolio(state.get("portfolio"))
    signals = state.get("signals") or compute_signals(
        state, config, portfolio, state.get("latest_price")
    )
    action = None
    units = float(portfolio.get("units") or 0.0)
    if signals.get("buy") and units <= 0:
        amount = float(config.get("invest_amount") or 0.0)
        portfolio = buy(portfolio, state.get("latest_price"), amount)
        action = "buy"
    elif signals.get("sell") and units > 0:
        portfolio = sell(portfolio, state.get("latest_price"))
        action = "sell"
    if action:
        state["portfolio"] = portfolio
        state["last_action"] = {"kind": action, "timestamp": now_iso()}
    return state
