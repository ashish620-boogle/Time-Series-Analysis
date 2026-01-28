# Market Pulse: Live Crypto Forecasting Dashboard

Market Pulse is a full-stack time-series forecasting and trading-simulation project focused on short-horizon crypto price prediction. It combines real-time market data ingestion, feature engineering, supervised ML models, and a live dashboard that streams updates over WebSockets.

Live deployment (frontend): https://hftsystem.netlify.app/

---

## What this project is about
This project demonstrates how to turn time-series modeling theory into a live system:
- **Forecasting** short-horizon prices (1-minute and ~45-minute horizons).
- **Feature engineering** tailored to intraday market microstructure.
- **Model evaluation** that reflects current regime performance rather than historical averages.
- **Action signals and trading simulation** to link predictions to practical decision cues.
- **Real-time dashboards** driven by a backend that pushes updates over WebSockets.

---

## Core theoretical concepts

### 1) Supervised framing of time series
Instead of modeling a series directly, we convert the time series into supervised learning:
- Build features from rolling returns, volatility, and momentum.
- Shift the target forward by a chosen horizon.
- Train a regression model to predict the future price.

This approach is efficient for short horizons where recent dynamics dominate.

### 2) Feature engineering rationale
Features are lightweight but predictive for short-term dynamics:
- **Returns (pct/log)**: capture immediate drift and relative changes.
- **Rolling means**: short and medium trend context (5/15/60 windows).
- **Rolling std**: volatility regime awareness.
- **Momentum**: directional pressure via short-term differences.
- **Range fraction**: intrabar volatility proxy.
- **Volume stats**: liquidity/pressure hints (mean/std/EMA).

The goal is interpretability and speed — not deep sequence modeling.

### 3) Model choice: tree boosting
We use `HistGradientBoostingRegressor` (scikit-learn) because:
- It captures nonlinear interactions without heavy tuning.
- It trains quickly, allowing frequent refresh cycles.
- It performs well on tabular features without large datasets.

### 4) Multiple horizons
Two models are trained on separate grids:
- **Minute-ahead model**: 1-minute bars.
- **Longer-horizon model**: 5-minute bars with ~45-minute target.

This avoids mixing time granularities and keeps horizon intent clear.

### 5) Evaluation philosophy
Metrics are computed on the most recent predictions (tail MAE/MSE/RMSE/R2), emphasizing current regime performance rather than long-term averages that can mask drift.

---

## Trading logic (simulation)
This is not an execution engine, but a simple simulation framework:
- **Buy signal**: based on long-horizon forecast vs current price (adjusted by MAE).
- **Sell signal**: based on minute forecast vs last buy (adjusted by MAE).
- **Manual actions**: buy/sell buttons to simulate position changes.
- **P&L tracking**: mark-to-market profit over time.

The algorithm is intentionally transparent: it shows how forecasts can translate into signals without claiming a production-grade strategy.

---

## Deployment strategy
The system is split into:
- **Backend** (FastAPI):
  - Fetches live data, runs models, simulates trades.
  - Pushes state updates over WebSockets (`/ws`).
- **Frontend** (static dashboard):
  - Netlify-hosted UI built with HTML/CSS/JS and Plotly.
  - Reads backend URL from `static/config.js`.

This decoupling lets you scale and redeploy frontend and backend independently.

---

## How to run locally

### 1) Install dependencies
```bash
pip install -r requirements.txt
```

### 2) Run the backend
```bash
uvicorn backend.main:app --reload
```

### 3) Open the dashboard
- Local: open `http://localhost:8000`
- (Optional) edit `static/config.js` if serving frontend separately.

---

## Project structure (high-level)
- `src/` — data ingestion, preprocessing, modeling, trading logic.
- `backend/` — FastAPI API + WebSocket server.
- `static/` — dashboard UI (Plotly + WebSocket client).
- `artifacts/` — cached models/data (ignored in git).

---

## Notes and limitations
- This is a **demonstration system**, not a live trading bot.
- Real execution would require slippage modeling, fees, and broker integration.
- Crypto data sources can be rate-limited; fallback providers are supported.

---

## Roadmap ideas
- Add proper train/validation/test splits in training (not just charting).
- Add probabilistic forecasting (quantiles).
- Add multi-asset support and portfolio risk controls.
- Add drift monitoring and alerting.

---

If you want a more advanced backtesting engine or live execution integration, tell me which broker or data provider you want and I can extend the system.
