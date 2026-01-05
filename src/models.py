"""Model training, evaluation, and persistence utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.metrics import mean_absolute_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def build_regressor(random_state: int = 42) -> Pipeline:
    """Return a tree-based regressor wrapped with imputation and scaling."""
    return Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
            (
                "model",
                HistGradientBoostingRegressor(
                    max_depth=6,
                    learning_rate=0.05,
                    max_iter=400,
                    min_samples_leaf=20,
                    random_state=random_state,
                ),
            ),
        ]
    )


def train_model(
    X_train: pd.DataFrame, y_train: pd.Series, random_state: int = 42
) -> Pipeline:
    """Fit a regression model."""
    model = build_regressor(random_state=random_state)
    model.fit(X_train, y_train)
    return model


def evaluate_model(model: Pipeline, X_val: pd.DataFrame, y_val: pd.Series) -> float:
    """Compute MAE on validation set."""
    if X_val.empty or y_val.empty:
        return float("nan")
    preds = model.predict(X_val)
    return float(mean_absolute_error(y_val, preds))


def predict(model: Pipeline, X: pd.DataFrame) -> np.ndarray:
    """Predict helper."""
    if X is None or X.empty:
        return np.array([])
    return model.predict(X)


def save_model(model: Pipeline, path: Path) -> Path:
    """Persist a trained model to disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, path)
    return path


def load_model(path: Path) -> Optional[Pipeline]:
    """Load a model if it exists."""
    if not path.exists():
        return None
    return joblib.load(path)


def train_and_evaluate(
    X_train: pd.DataFrame,
    y_train: pd.Series,
    X_val: pd.DataFrame,
    y_val: pd.Series,
    random_state: int = 42,
) -> Tuple[Pipeline, float]:
    """Fit and evaluate, returning the model and validation MAE."""
    model = train_model(X_train, y_train, random_state=random_state)
    mae = evaluate_model(model, X_val, y_val)
    return model, mae
