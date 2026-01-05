"""Trading logic and portfolio simulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pandas as pd


@dataclass
class TradeEvent:
    kind: str  # "buy" or "sell"
    timestamp: pd.Timestamp
    price: float
    shares: int


def simulate_trades(
    prices: pd.Series,
    predicted_prices: pd.Series,
    starting_cash: Optional[float] = None,
    invest_amount: Optional[float] = None,
    buy_threshold: float = 0.002,
    sell_threshold: float = -0.001,
    execute_trades: bool = True,
) -> dict:
    """
    Simulate a simple single-position strategy using predicted returns:
    - If execute_trades is True: buy if predicted return exceeds buy_threshold (allocating up to invest_amount or remaining cash); sell if predicted return is below sell_threshold.
    - If execute_trades is False: no trades executed; only mark-to-market.
    Tracks running profit for charting and withdraw value.
    """
    if prices is None or predicted_prices is None:
        return {}

    df = pd.DataFrame({"price": prices, "pred_price": predicted_prices}).dropna()
    if df.empty:
        return {}

    base_cash = invest_amount if invest_amount and invest_amount > 0 else (starting_cash or 10_000.0)
    cash = float(base_cash)
    shares = 0
    events: List[TradeEvent] = []
    profit_history = []
    invest_cap = invest_amount if invest_amount and invest_amount > 0 else base_cash

    for ts, row in df.iterrows():
        pred_return = (row.pred_price - row.price) / row.price

        if execute_trades:
            # Buy logic
            if shares == 0 and pred_return > buy_threshold and cash > 0:
                budget = min(cash, invest_cap)
                units = int(budget // row.price)
                if units > 0:
                    shares += units
                    cash -= units * row.price
                    events.append(TradeEvent("buy", ts, float(row.price), units))

            # Sell logic
            elif shares > 0 and pred_return < sell_threshold:
                cash += shares * row.price
                events.append(TradeEvent("sell", ts, float(row.price), shares))
                shares = 0

        portfolio_value = cash + shares * row.price
        profit = portfolio_value - base_cash
        profit_history.append(
            {"timestamp": ts, "profit": profit, "portfolio_value": portfolio_value}
        )

    # Final mark-to-market and withdraw calculation
    latest_price = df["price"].iloc[-1]
    portfolio_value = cash + shares * latest_price
    profit = portfolio_value - base_cash
    withdraw_value = portfolio_value  # selling remaining shares at latest price

    # How many units could be purchased with the configured invest amount (or starting cash if not set)
    equivalent_units = round(invest_cap / latest_price, 6) if latest_price > 0 else 0

    return {
        "cash": round(cash, 2),
        "shares": shares,
        "latest_price": float(latest_price),
        "portfolio_value": round(portfolio_value, 2),
        "profit": round(profit, 2),
        "equivalent_units_for_invest": equivalent_units,
        "invest_cap": invest_cap,
        "events": events,
        "profit_history": profit_history,
        "withdraw_value": round(withdraw_value, 2),
        "withdraw_profit": round(profit, 2),
    }
