import altair as alt
import pandas as pd
import streamlit as st
import time

from src.pipeline import run_pipeline
from src.data_fetch import latest_quote
from src.data_fetch import latest_quote




st.set_page_config(page_title="Live Bitcoin Forecaster", layout="wide")
st.title("Live Bitcoin Forecasting & Trading")
st.caption(
    "Default ticker BTC-USD (Binance spot). Models forecast 1 minute ahead and ~45 minutes ahead (3/4 of an hour)."
)


def fetch_pipeline(
    ticker: str,
    invest_amount: float,
    max_points: int,
    train_window: int,
    minute_horizon: int,
    long_horizon_steps: int,
):
    """Cached run to avoid retraining on every rerun."""
    return run_pipeline(
        ticker=ticker,
        invest_amount=invest_amount,
        max_points=max_points,
        train_window=train_window or None,
        minute_horizon=minute_horizon,
        long_horizon_steps=long_horizon_steps,
        execute_trades=False,
    )


def render_metrics(result: dict):
    col1, col2, col3 = st.columns(3)
    col1.metric("Latest price", f"${result['latest_price']:.2f}")
    col2.metric("Next minute forecast", f"${result['next_minute_price']:.2f}")
    col3.metric("~45m forecast", f"${result['next_hour_price']:.2f}")

    col4, col5, col6 = st.columns(3)
    col4.metric("Minute MAE (tail)", f"{result['minute_mae']:.4f}")
    col5.metric("Minute RMSE (tail)", f"{result['minute_rmse']:.4f}")
    col6.metric("Minute R² (tail)", f"{result['minute_r2']:.4f}")

    col7, col8, col9 = st.columns(3)
    col7.metric("Hour MAE (tail)", f"{result['hour_mae']:.4f}")
    col8.metric("Hour RMSE (tail)", f"{result['hour_rmse']:.4f}")
    col9.metric("Hour R² (tail)", f"{result['hour_r2']:.4f}")


def render_portfolio(portfolio: dict, invest_amount: float, latest_price: float):
    st.subheader("Holdings")
    withdrawn = st.session_state.get("withdrawn", False)
    current_units = st.session_state.get("units", 0.0)
    invested_amount = st.session_state.get("invested_amount", invest_amount)
    current_value = latest_price * current_units
    profit_now = current_value - invested_amount if current_units > 0 else 0.0

    if withdrawn:
        cash_display = 0.0
        shares_display = 0
        portfolio_value_display = 0.0
        profit_display = st.session_state.get("withdraw_profit", 0.0)
        display_units = 0
    else:
        cash_display = 0.0
        shares_display = current_units
        portfolio_value_display = current_value
        profit_display = profit_now
        display_units = current_units
    col1, col2, col3 = st.columns(3)
    col1.metric("Cash", f"${cash_display:.2f}")
    col2.metric("Units held", str(display_units))
    col3.metric("Portfolio value", f"${portfolio_value_display:.2f}")
    st.metric("Profit/Loss", f"${profit_display:.2f}")



def main():
    st.session_state.setdefault("withdrawn", False)
    st.session_state.setdefault("withdraw_value", 0.0)
    st.session_state.setdefault("withdraw_profit", 0.0)
    st.session_state.setdefault("units", 0.0)
    st.session_state.setdefault("invested_amount", 0.0)
    st.session_state.setdefault("invest_time", None)
    st.session_state.setdefault("last_autorefresh", time.time())
    st.session_state.setdefault("live_price", None)
    st.session_state.setdefault("profit_points", [])

    with st.sidebar:
        ticker = st.text_input("Ticker / Pair", value="BTC-USD").upper()
        invest_amount = st.number_input(
            "Amount to invest per buy ($)",
            value=1000.0,
            min_value=0.0,
            step=100.0,
        )
        max_points = st.number_input(
            "Max data points to fetch", min_value=1000, max_value=100000, value=50000, step=1000
        )
        train_window = st.number_input(
            "Training window (rows, optional)", min_value=0, max_value=100000, value=0, step=1000
        )
        minute_horizon = st.number_input(
            "Minute horizon (steps)", min_value=1, max_value=60, value=1, step=1
        )
        long_horizon_steps = st.number_input(
            "Long horizon steps (5m bars)", min_value=1, max_value=100, value=9, step=1
        )
        retrain = st.button("Retrain on latest data")
        refresh = st.button("Refresh prices (no retrain)")
        set_investment = st.button("Set investment")
        sell_now = st.button("Sell now")
        st.info("Set invest amount to 0 to allow full deployment of available cash.")

    try:
        if retrain:
            result = run_pipeline(
                ticker=ticker,
                invest_amount=invest_amount,
                force_retrain=True,
                max_points=max_points,
                train_window=train_window or None,
                minute_horizon=minute_horizon,
                long_horizon_steps=long_horizon_steps,
            )
        elif refresh:
            result = fetch_pipeline(
                ticker,
                invest_amount,
                max_points,
                train_window or None,
                minute_horizon,
                long_horizon_steps,
            )
        else:
            result = fetch_pipeline(
                ticker,
                invest_amount,
                max_points,
                train_window or None,
                minute_horizon,
                long_horizon_steps,
            )
        if retrain or refresh:
            st.session_state["withdrawn"] = False
            st.session_state["withdraw_value"] = 0.0
            st.session_state["withdraw_profit"] = 0.0
            st.session_state["units"] = 0.0
            st.session_state["invested_amount"] = 0.0
    except Exception as exc:  # noqa: BLE001
        st.error(f"Pipeline failed: {exc}")
        st.stop()

    # Investment handling
    # Fetch latest live price directly for display/sell actions; fall back to pipeline price.
    live_quote = latest_quote(ticker)
    current_price = (
        float(live_quote["close"])
        if live_quote is not None and "close" in live_quote
        else result["latest_price"]
    )
    st.session_state["live_price"] = current_price
    result["latest_price"] = current_price

    if set_investment and invest_amount > 0:
        units = invest_amount / current_price
        st.session_state["units"] = units
        st.session_state["invested_amount"] = invest_amount
        st.session_state["withdrawn"] = False
        st.session_state["withdraw_value"] = 0.0
        st.session_state["withdraw_profit"] = 0.0
        st.session_state["last_bought_price"] = current_price
        price_series = result.get("minute_prices")
        st.session_state["invest_time"] = price_series.index[-1] if price_series is not None else None
        st.session_state["profit_points"] = []

    if sell_now and st.session_state.get("units", 0) > 0:
        revenue = current_price * st.session_state["units"]
        profit = revenue - st.session_state["invested_amount"]
        st.session_state["withdrawn"] = True
        st.session_state["withdraw_value"] = revenue
        st.session_state["withdraw_profit"] = profit
        st.session_state["units"] = 0.0
        st.session_state["invest_time"] = None
        st.session_state["profit_points"] = []

    st.subheader("Charts")
    col_chart1, col_chart2 = st.columns(2)

    with col_chart1:
        st.markdown("**Live vs Predicted (full history with recent predictions)**")
        price_series = result.get("minute_prices")
        historical_prices = result.get("historical_prices")
        pred_series = result.get("minute_predictions")
        forecast_points = result.get("forecast_points", [])
        if historical_prices is None:
            historical_prices = price_series
        if historical_prices is not None:
            # Truncate to a fixed window once per session (default 8 hours)
            if isinstance(historical_prices.index, pd.DatetimeIndex):
                if "chart_cutoff" not in st.session_state:
                    st.session_state["chart_cutoff"] = historical_prices.index.max() - pd.Timedelta(hours=3)
                cutoff = st.session_state["chart_cutoff"]
                historical_prices = historical_prices[historical_prices.index >= cutoff]
            actual_df = pd.DataFrame(
                {"timestamp": historical_prices.index, "series": "Actual", "price": historical_prices.values}
            )
            overlays = alt.Chart(actual_df).mark_line(color="#1f77b4").encode(
                x="timestamp:T", y="price:Q", tooltip=["timestamp:T", "price:Q"]
            )

            y_values = list(historical_prices.values)

            if pred_series is not None and len(pred_series) > 0:
                tail_len = min(60, len(pred_series))
                pred_tail = pred_series.tail(tail_len)
                pred_df = pd.DataFrame(
                    {"timestamp": pred_tail.index, "series": "Predicted", "price": pred_tail.values}
                )
                pred_chart = (
                    alt.Chart(pred_df)
                    .mark_line(color="#d62728")
                    .encode(x="timestamp:T", y="price:Q", tooltip=["timestamp:T", "price:Q"])
                )
                overlays = overlays + pred_chart
                y_values.extend(pred_tail.values)

            if forecast_points:
                forecast_df = pd.DataFrame(forecast_points)
                forecast_chart = (
                    alt.Chart(forecast_df)
                    .mark_point(color="#9467bd", size=80)
                    .encode(
                        x="timestamp:T",
                        y="price:Q",
                        tooltip=["label:N", "timestamp:T", "price:Q"],
                    )
                )
                overlays = overlays + forecast_chart
                y_values.extend(forecast_df["price"].tolist())

            if y_values:
                y_min = min(y_values) * 0.98
                y_max = max(y_values) * 1.02
                overlays = overlays.encode(y=alt.Y("price:Q", scale=alt.Scale(domain=[y_min, y_max])))
            else:
                overlays = overlays.encode(y=alt.Y("price:Q"))

            st.altair_chart(overlays.interactive(), use_container_width=True)
        else:
            st.info("Price series unavailable for chart.")

    with col_chart2:
        st.markdown("**Profit over time (mark-to-market holdings)**")
        invest_time = st.session_state.get("invest_time")
        units_held = st.session_state.get("units", 0)
        if units_held > 0:
            profit_now = current_price * units_held - st.session_state["invested_amount"]
            st.session_state["profit_points"].append({"timestamp": pd.Timestamp.utcnow(), "profit": profit_now})
            profit_df = pd.DataFrame(st.session_state["profit_points"])
            chart = (
                alt.Chart(profit_df)
                .mark_line(color="#2ca02c")
                .encode(
                    x="timestamp:T",
                    y="profit:Q",
                    tooltip=["timestamp:T", "profit:Q"],
                )
                .interactive()
            )
            points = (
                alt.Chart(profit_df)
                .mark_circle(color="#2ca02c", size=30)
                .encode(x="timestamp:T", y="profit:Q", tooltip=["timestamp:T", "profit:Q"])
            )
            st.altair_chart(chart + points, use_container_width=True)
        else:
            st.info("Set an investment to see live profit.")

    render_metrics(result)

    st.subheader("Predictions")
    st.write(
        f"Next minute price forecast for {ticker}: "
        f"${result['next_minute_price']:.4f}"
    )
    st.write(
        f"Next hour (45 minutes ahead) forecast for {ticker}: "
        f"${result['next_hour_price']:.4f}"
    )

    # Action cues based on forecasts vs live price
    buy_signal = (result["next_hour_price"] - result["hour_mae"]) > 1.5 * current_price
    last_bought_price = st.session_state.get("last_bought_price", current_price)
    sell_signal = (result["next_minute_price"] - result["minute_mae"]) > 1.2 * last_bought_price
    if buy_signal:
        st.success("Buy signal: 45-minute forecast is well above current price.")
        st.balloons()
    if sell_signal:
        st.warning("Sell signal: 1-minute forecast is high relative to current price.")
        st.snow()

    st.divider()
    render_portfolio(result["portfolio"], invest_amount, current_price)

    st.caption(
        "Auto-refresh by rerunning the app or pressing 'R' in Streamlit; "
        "models use cached artifacts unless retrain is clicked."
    )
    # Auto-refresh every 3 seconds
    time.sleep(3)
    if hasattr(st, "rerun"):
        st.rerun()
    else:  # backward compatibility
        st.experimental_rerun()


if __name__ == "__main__":
    main()
