"""Preprocessing helpers: resampling, feature engineering, and temporal splits."""

from __future__ import annotations

from typing import Tuple

import numpy as np
import pandas as pd


def resample_prices(prices: pd.DataFrame, freq: str = "1min") -> pd.DataFrame:
    """Resample to an even timeline and forward-fill gaps."""
    if prices is None or prices.empty:
        return pd.DataFrame()
    resampled = (
        prices.resample(freq)
        .last()
        .ffill()
    )
    resampled = resampled.dropna(subset=["close"])
    return resampled


def _feature_block(prices: pd.DataFrame) -> pd.DataFrame:
    """Create rolling/momentum/volatility features."""
    df = prices.copy()
    if "volume" not in df.columns:
        df["volume"] = 0.0
    df["return_1"] = df["close"].pct_change()
    df["return_5"] = df["close"].pct_change(periods=5)
    df["log_return"] = np.log(df["close"]).diff()
    df["range_frac"] = (df["high"] - df["low"]) / df["close"]
    df["rolling_mean_5"] = df["close"].rolling(5).mean()
    df["rolling_mean_15"] = df["close"].rolling(15).mean()
    df["rolling_mean_60"] = df["close"].rolling(60).mean()
    df["rolling_std_15"] = df["close"].rolling(15).std()
    df["rolling_std_60"] = df["close"].rolling(60).std()
    df["momentum_10"] = df["close"].diff(10)
    df["volume_mean_20"] = df["volume"].rolling(20).mean()
    df["volume_std_20"] = df["volume"].rolling(20).std()
    df["volume_ema_20"] = df["volume"].ewm(span=20, adjust=False).mean()
    return df


def build_supervised(
    prices: pd.DataFrame, horizon_steps: int, freq: str = "1min"
) -> Tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """
    Turn a price series into features/targets for a given forecast horizon.

    Returns (X, y, latest_row_for_inference).
    """
    if prices is None or prices.empty:
        return pd.DataFrame(), pd.Series(dtype=float), pd.DataFrame()

    resampled = resample_prices(prices, freq=freq)
    engineered = _feature_block(resampled)
    engineered = engineered.replace([np.inf, -np.inf], np.nan).dropna()

    target = engineered["close"].shift(-horizon_steps)
    engineered["target"] = target

    latest_features = engineered.drop(columns=["target"]).tail(1)

    supervised = engineered.dropna(subset=["target"])
    features = supervised.drop(columns=["target"])
    labels = supervised["target"]
    return features, labels, latest_features


def temporal_train_val_split(
    X: pd.DataFrame, y: pd.Series, train_frac: float = 0.8
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    """Time-ordered split for validation."""
    if X.empty or y.empty:
        return (
            pd.DataFrame(),
            pd.DataFrame(),
            pd.Series(dtype=float),
            pd.Series(dtype=float),
        )
    cutoff = max(1, int(len(X) * train_frac))
    X_train, X_val = X.iloc[:cutoff], X.iloc[cutoff:]
    y_train, y_val = y.iloc[:cutoff], y.iloc[cutoff:]
    return X_train, X_val, y_train, y_val
