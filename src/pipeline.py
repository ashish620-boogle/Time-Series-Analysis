"""End-to-end pipeline wiring fetch, preprocessing, modeling, and trading."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from .data_fetch import (
    combined_price_history,
    fetch_intraday_history,
    load_cached_history,
    save_history,
)
from .models import load_model, predict, save_model, train_and_evaluate
from .preprocess import build_supervised, temporal_train_val_split
from .trading import simulate_trades
from sklearn.metrics import r2_score, mean_squared_error


def _train_or_load(
    features: pd.DataFrame,
    target: pd.Series,
    model_path: Path,
    random_state: int = 42,
    force_retrain: bool = False,
):
    """Load a model if present; otherwise train and persist it."""
    if model_path.exists() and not force_retrain:
        model = load_model(model_path)
        if model is not None:
            return model, float("nan"), False

    X_train, X_val, y_train, y_val = temporal_train_val_split(features, target)
    model, mae = train_and_evaluate(
        X_train, y_train, X_val, y_val, random_state=random_state
    )
    save_model(model, model_path)
    return model, mae, True


def run_pipeline(
    ticker: str = "BTC-USD",
    intraday_days: int = 7,
    minute_horizon: int = 1,
    long_horizon_steps: int = 9,  # defaults to ~45 minutes on 5m bars
    artifact_dir: str = "artifacts",
    invest_amount: Optional[float] = None,
    force_retrain: bool = False,
    max_points: Optional[int] = 50000,
    train_window: Optional[int] = None,
    execute_trades: bool = False,
):
    """
    Train (or load) models and produce forecasts + trading simulation.

    Returns a dictionary with predictions, metrics, and portfolio state.
    """
    artifact_root = Path(artifact_dir)
    cache_path = artifact_root / f"{ticker}_history.csv"

    intraday_data = fetch_intraday_history(
        ticker=ticker, lookback_days=intraday_days, interval="1m", max_points=max_points
    )
    data = (
        intraday_data
        if not intraday_data.empty
        else combined_price_history(ticker=ticker, intraday_days=intraday_days, max_points=max_points)
    )
    if data.empty:
        # Try cached history if network is unavailable.
        data = load_cached_history(cache_path)
    if data.empty:
        raise ValueError(
            "No price data available. Check internet connectivity, reduce intraday_days, "
            "or try a different ticker."
        )

    historical_prices = data["close"].copy()

    # Persist latest pull for offline reuse.
    save_history(data, cache_path)

    minute_model_path = artifact_root / f"{ticker}_minute.joblib"
    hour_model_path = artifact_root / f"{ticker}_hour.joblib"

    # Optionally limit training window to most recent N rows
    recent_data = data
    if train_window:
        recent_data = recent_data.tail(train_window)

    # Minute-ahead model
    minute_features, minute_target, minute_latest = build_supervised(
        recent_data, horizon_steps=minute_horizon, freq="1min"
    )
    if minute_features.empty or minute_target.empty:
        raise ValueError("Insufficient minute-level data to train.")

    minute_model, minute_mae, minute_trained = _train_or_load(
        minute_features, minute_target, minute_model_path, force_retrain=force_retrain
    )
    minute_predictions_array = predict(minute_model, minute_features)
    minute_predictions = pd.Series(
        minute_predictions_array, index=minute_features.index
    )
    # Compute MAE on last 100 predictions if available
    if len(minute_predictions) >= 1:
        tail_n = min(100, len(minute_predictions))
        minute_mae = float(
            (minute_predictions.tail(tail_n) - minute_target.tail(tail_n)).abs().mean()
        )
        minute_mse_val = float(
            mean_squared_error(minute_target.tail(tail_n), minute_predictions.tail(tail_n))
        )
        minute_rmse_val = float(minute_mse_val**0.5)
        minute_r2_val = float(
            r2_score(minute_target.tail(tail_n), minute_predictions.tail(tail_n))
        )
    else:
        minute_mse_val = float("nan")
        minute_rmse_val = float("nan")
        minute_r2_val = float("nan")
    minute_next_array = predict(minute_model, minute_latest)
    next_minute_price = (
        float(minute_next_array[0]) if minute_next_array.size else float("nan")
    )

    # Longer horizon model (default 45-minute horizon using 5m bars)
    hour_features, hour_target, hour_latest = build_supervised(
        recent_data, horizon_steps=long_horizon_steps, freq="5min"
    )
    if hour_features.empty or hour_target.empty:
        raise ValueError("Insufficient hourly-level data to train.")

    hour_model, hour_mae, hour_trained = _train_or_load(
        hour_features, hour_target, hour_model_path, force_retrain=force_retrain
    )
    hour_predictions_array = predict(hour_model, hour_features)
    hour_predictions = pd.Series(hour_predictions_array, index=hour_features.index)
    # Compute MAE on last 100 predictions if available
    if len(hour_predictions) >= 1:
        tail_n = min(100, len(hour_predictions))
        hour_mae = float(
            (hour_predictions.tail(tail_n) - hour_target.tail(tail_n)).abs().mean()
        )
        hour_mse_val = float(
            mean_squared_error(hour_target.tail(tail_n), hour_predictions.tail(tail_n))
        )
        hour_rmse_val = float(hour_mse_val**0.5)
        hour_r2_val = float(
            r2_score(hour_target.tail(tail_n), hour_predictions.tail(tail_n))
        )
    else:
        hour_mse_val = float("nan")
        hour_rmse_val = float("nan")
        hour_r2_val = float("nan")
    hour_next_array = predict(hour_model, hour_latest)
    next_hour_price = float(hour_next_array[0]) if hour_next_array.size else float("nan")

    # Trading simulation on minute bars
    sim_result = {
        "cash": 0.0,
        "shares": 0,
        "latest_price": float(minute_features["close"].iloc[-1]),
        "portfolio_value": 0.0,
        "profit": 0.0,
        "equivalent_units_for_invest": 0.0,
        "invest_cap": invest_amount or 0.0,
        "events": [],
        "profit_history": [],
        "withdraw_value": 0.0,
        "withdraw_profit": 0.0,
    }

    # Series for visualization (use full training window)
    price_series = minute_features["close"]
    pred_series = minute_predictions

    # Forecast points beyond the last timestamp (for display only)
    last_ts = price_series.index[-1]
    forecast_points = [
        {
            "timestamp": last_ts + pd.Timedelta(minutes=minute_horizon),
            "label": "Next minute",
            "price": next_minute_price,
        },
        {
            "timestamp": last_ts + pd.Timedelta(minutes=long_horizon_steps * 5),
            "label": "Long horizon",
            "price": next_hour_price,
        },
    ]

    return {
        "ticker": ticker,
        "latest_price": float(minute_features["close"].iloc[-1]),
        "next_minute_price": next_minute_price,
        "next_hour_price": next_hour_price,
        "minute_mae": minute_mae,
        "minute_mse": minute_mse_val,
        "minute_rmse": minute_rmse_val,
        "minute_r2": minute_r2_val,
        "hour_mae": hour_mae,
        "hour_mse": hour_mse_val,
        "hour_rmse": hour_rmse_val,
        "hour_r2": hour_r2_val,
        "minute_model_path": str(minute_model_path),
        "hour_model_path": str(hour_model_path),
        "minute_trained": minute_trained,
        "hour_trained": hour_trained,
        "portfolio": sim_result,
        "minute_prices": price_series,
        "minute_predictions": pred_series,
        "forecast_points": forecast_points,
        "historical_prices": historical_prices,
    }
