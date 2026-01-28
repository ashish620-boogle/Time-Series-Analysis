from pydantic import BaseModel, Field
from typing import Optional


class Config(BaseModel):
    ticker: str = "BTC-USD"
    intraday_days: int = Field(7, ge=1)
    max_points: int = Field(50000, ge=1000)
    train_window: int = Field(0, ge=0)
    minute_horizon: int = Field(1, ge=1)
    long_horizon_steps: int = Field(9, ge=1)
    invest_amount: float = Field(1000.0, ge=0)
    auto_trade: bool = False
    buy_multiplier: float = Field(1.5, ge=0)
    sell_multiplier: float = Field(1.2, ge=0)
    chart_points: int = Field(500, ge=50, le=5000)
    price_refresh_seconds: int = Field(15, ge=1)
    model_refresh_seconds: int = Field(60, ge=5)


class ConfigUpdate(BaseModel):
    ticker: Optional[str] = None
    intraday_days: Optional[int] = Field(None, ge=1)
    max_points: Optional[int] = Field(None, ge=1000)
    train_window: Optional[int] = Field(None, ge=0)
    minute_horizon: Optional[int] = Field(None, ge=1)
    long_horizon_steps: Optional[int] = Field(None, ge=1)
    invest_amount: Optional[float] = Field(None, ge=0)
    auto_trade: Optional[bool] = None
    buy_multiplier: Optional[float] = Field(None, ge=0)
    sell_multiplier: Optional[float] = Field(None, ge=0)
    chart_points: Optional[int] = Field(None, ge=50, le=5000)
    price_refresh_seconds: Optional[int] = Field(None, ge=1)
    model_refresh_seconds: Optional[int] = Field(None, ge=5)


class TradeRequest(BaseModel):
    amount: Optional[float] = Field(None, ge=0)
