"""Data acquisition utilities for live and historical prices (Binance REST)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests


def _normalize(df: pd.DataFrame) -> pd.DataFrame:
    """Lower-case columns, drop empty closes, and strip timezone."""
    if df is None:
        return pd.DataFrame()
    if hasattr(df, "empty") and df.empty:
        return pd.DataFrame()
    if not hasattr(df, "copy"):
        return pd.DataFrame()
    result = df.copy()
    result.index = pd.to_datetime(result.index).tz_localize(None)
    result.columns = [str(c).lower() for c in result.columns]
    if "close" not in result.columns:
        return pd.DataFrame()
    result = result.dropna(subset=["close"])
    result = result.sort_index()
    return result


def _binance_symbol(ticker: str) -> str:
    """Map a generic ticker like BTC-USD to Binance spot symbol (BTCUSDT)."""
    symbol = ticker.replace("-", "")
    if symbol.endswith("USD") and not symbol.endswith("USDT"):
        symbol = symbol[:-3] + "USDT"
    return symbol.upper()


def _coinbase_product(ticker: str) -> str:
    """Map a generic ticker like BTC-USD to Coinbase product (BTC-USD)."""
    parts = ticker.replace("_", "-").upper().split("-")
    if len(parts) >= 2:
        base = parts[0]
        quote = parts[1]
    else:
        base = ticker.replace("-", "").upper()
        quote = "USD"
    if quote == "USDT":
        quote = "USD"
    return f"{base}-{quote}"


def _fetch_binance_klines(symbol: str, interval: str, start_ms: int, end_ms: int):
    """Fetch klines chunk from Binance."""
    url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ms,
        "endTime": end_ms,
        "limit": 1000,
    }
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return []


def _klines_to_df(klines) -> pd.DataFrame:
    """Convert Binance kline payload to DataFrame."""
    if not klines:
        return pd.DataFrame()
    cols = [
        "open_time",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "close_time",
        "quote_asset_volume",
        "number_of_trades",
        "taker_buy_base",
        "taker_buy_quote",
        "ignore",
    ]
    df = pd.DataFrame(klines, columns=cols)
    numeric_cols = ["open", "high", "low", "close", "volume"]
    df[numeric_cols] = df[numeric_cols].astype(float)
    df["open_time"] = pd.to_datetime(df["open_time"], unit="ms", utc=True)
    df = df.set_index("open_time")
    return df[["open", "high", "low", "close", "volume"]]


def _fetch_coinbase_candles(
    product_id: str, granularity: int, start_iso: str, end_iso: str
):
    """Fetch candles chunk from Coinbase Exchange."""
    url = f"https://api.exchange.coinbase.com/products/{product_id}/candles"
    params = {"granularity": granularity, "start": start_iso, "end": end_iso}
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        return []


def _coinbase_candles_to_df(candles) -> pd.DataFrame:
    """Convert Coinbase candle payload to DataFrame."""
    if not candles:
        return pd.DataFrame()
    # Coinbase format: [time, low, high, open, close, volume]
    df = pd.DataFrame(candles, columns=["time", "low", "high", "open", "close", "volume"])
    df[["open", "high", "low", "close", "volume"]] = df[
        ["open", "high", "low", "close", "volume"]
    ].astype(float)
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time").sort_index()
    return df[["open", "high", "low", "close", "volume"]]


def _coinbase_granularity(interval: str) -> int:
    """Map interval string to Coinbase granularity seconds."""
    mapping = {"1m": 60, "5m": 300, "1h": 3600}
    return mapping.get(interval, 60)


def fetch_intraday_history(
    ticker: str = "BTC-USD",
    lookback_days: int = 2,
    interval: str = "1m",
    max_points: Optional[int] = None,
) -> pd.DataFrame:
    """Fetch intraday bars from Binance, optionally capped by max_points."""
    symbol = _binance_symbol(ticker)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = int(
        (datetime.now(timezone.utc) - timedelta(days=lookback_days)).timestamp() * 1000
    )

    frames = []
    cursor = start_ms
    total_rows = 0
    while cursor < now_ms:
        batch = _fetch_binance_klines(symbol, interval, cursor, now_ms)
        if not batch:
            break
        df_batch = _klines_to_df(batch)
        frames.append(df_batch)
        total_rows += len(df_batch)
        last_close = batch[-1][6]
        cursor = last_close + 1
        if len(batch) < 1000:
            break
        if max_points and total_rows >= max_points:
            break

    if not frames:
        # Fallback to Coinbase if Binance is unavailable.
        product_id = _coinbase_product(ticker)
        granularity = _coinbase_granularity(interval)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=lookback_days)
        frames = []
        cursor = start_time
        # Coinbase limit ~300 candles per request
        step = timedelta(seconds=granularity * 300)
        while cursor < end_time:
            chunk_end = min(cursor + step, end_time)
            candles = _fetch_coinbase_candles(
                product_id,
                granularity,
                cursor.isoformat(),
                chunk_end.isoformat(),
            )
            df_chunk = _coinbase_candles_to_df(candles)
            if not df_chunk.empty:
                frames.append(df_chunk)
            cursor = chunk_end
        if not frames:
            return pd.DataFrame()
    df = pd.concat(frames)
    if max_points:
        df = df.tail(max_points)
    return _normalize(df)


def fetch_daily_history(ticker: str = "BTC-USD", days: int = 365) -> pd.DataFrame:
    """Fetch higher-interval bars (1h) to approximate daily context."""
    symbol = _binance_symbol(ticker)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_ms = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)

    frames = []
    cursor = start_ms
    while cursor < now_ms:
        batch = _fetch_binance_klines(symbol, "1h", cursor, now_ms)
        if not batch:
            break
        frames.append(_klines_to_df(batch))
        last_close = batch[-1][6]
        cursor = last_close + 1
        if len(batch) < 1000:
            break

    if not frames:
        # Fallback to Coinbase 1h candles.
        product_id = _coinbase_product(ticker)
        granularity = _coinbase_granularity("1h")
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(days=days)
        frames = []
        cursor = start_time
        step = timedelta(seconds=granularity * 300)
        while cursor < end_time:
            chunk_end = min(cursor + step, end_time)
            candles = _fetch_coinbase_candles(
                product_id,
                granularity,
                cursor.isoformat(),
                chunk_end.isoformat(),
            )
            df_chunk = _coinbase_candles_to_df(candles)
            if not df_chunk.empty:
                frames.append(df_chunk)
            cursor = chunk_end
        if not frames:
            return pd.DataFrame()
    df = pd.concat(frames)
    return _normalize(df)


def latest_quote(ticker: str = "BTC-USD") -> Optional[pd.Series]:
    """Return the most recent 1m quote from Binance."""
    df = fetch_intraday_history(ticker=ticker, lookback_days=1, interval="1m")
    if df.empty:
        return None
    return df.iloc[-1]


def combined_price_history(
    ticker: str = "BTC-USD", intraday_days: int = 2, max_points: Optional[int] = None
) -> pd.DataFrame:
    """Concatenate recent intraday bars with higher-interval context."""
    intraday = fetch_intraday_history(
        ticker=ticker, lookback_days=intraday_days, max_points=max_points
    )
    daily = fetch_daily_history(ticker=ticker, days=365)
    frames = [frame for frame in [daily, intraday] if not frame.empty]
    if not frames:
        return pd.DataFrame()
    merged = pd.concat(frames)
    merged = merged[~merged.index.duplicated(keep="last")]
    return _normalize(merged)


def load_cached_history(path: Path) -> pd.DataFrame:
    """Load cached CSV if present."""
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, parse_dates=[0], index_col=0)
    return _normalize(df)


def save_history(df: pd.DataFrame, path: Path) -> None:
    """Persist history for offline reuse."""
    if df is None or df.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)
