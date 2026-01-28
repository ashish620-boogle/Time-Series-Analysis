# Bitcoin Price Forecasting & Live Mark-to-Market Demo

01) What this project is
- A complete, runnable system that fetches live BTC-USD data, engineers features, trains short- and medium-horizon forecasters, and serves an interactive Streamlit UI with live mark-to-market profit tracking and simple buy/sell cues.
- A reference for turning exploratory time-series notebooks into a production-style pipeline: ingestion → preprocessing → modeling → evaluation → persistence → UI/interaction.
- Built to be configurable (data depth, training window, horizons, ticker) while staying lightweight and fast to refresh.

02) Why it exists
- Demonstrate live time-series ML with clear separation of concerns and reproducibility.
- Show how forecasts can inform user-facing cues without opaque trading logic.
- Provide a sandbox for extending to richer models, assets, and risk-aware strategies.

03) High-level architecture
- Data layer: Binance REST klines (1m intraday + 1h context), normalized, optional cache for offline use.
- Preprocessing: even resampling, engineered statistical/volatility/momentum features, supervised framing for multiple horizons.
- Models: two scikit-learn pipelines using HistGradientBoostingRegressor (minute-ahead and ~45-minute-ahead).
- Pipeline: orchestrates fetch → feature build → train/load → predict → metrics/series for visualization.
- UI: Streamlit app that displays prices, forecasts, cues, and mark-to-market P&L; live price fetched directly for actions.
- State: user investment and profit tracking held in session; model artifacts/history cached on disk.

04) Data sources and rationale
- Source: Binance `/api/v3/klines` for BTC-USD (mapped to BTCUSDT) at 1m resolution (intraday) and 1h (context).
- Why Binance: deeper intraday history and reliable 1m bars compared to Yahoo 1m limits.
- Normalization: lower-case columns, tz-naive datetime index, drop rows without closes, sorted chronologically.
- Caching: history can be saved to `artifacts/<ticker>_history.csv` and reused when network is unavailable.

05) Preprocessing pipeline (src/preprocess.py)
- Resampling: enforce even grid (1m or 5m) and forward-fill to stabilize rolling features.
- Features:
  - Simple returns (`pct_change`) and log returns (scale-stabilized).
  - Rolling means: 5, 15, 60 to capture short/medium trend.
  - Rolling std: 15, 60 to capture local volatility regimes.
  - Momentum: 10-step price diffs.
  - Range fraction: (high - low) / close for intrabar volatility.
  - Volume stats: mean/std/EMA over 20 for liquidity/pressure cues.
- Targets: shift close by `horizon_steps` to create supervised labels; keep latest row for inference; drop inf/NaN.
- Rationale: blend very short-term microstructure cues with slightly longer context; avoid heavy differencing to keep interpretability.

06) Modeling choices (src/models.py)
- Pipeline: median imputer → standard scaler → HistGradientBoostingRegressor.
- Why HistGradientBoosting:
  - Handles nonlinearities and interactions with minimal tuning.
  - Fast to train/predict; good for frequent refresh and limited latency.
  - Robust to moderate outliers once scaled.
- Horizons:
  - Minute model: `minute_horizon` steps on 1m bars (default 1 → next minute).
  - Long model: `long_horizon_steps` on 5m bars (default 9 → ~45 minutes).
- Evaluation: MAE recomputed on the last 100 predictions to reflect current regime performance.
- Persistence: models saved to `artifacts/<ticker>_minute.joblib` and `_hour.joblib` to avoid retraining on every refresh when not needed.
- Alternatives considered:
  - ARIMA/SARIMA: better for linear/stationary signals; less flexible with rich features/regime shifts.
  - LSTM/Seq2Seq: more expressive but heavier, higher latency, and needs more data/ops overhead for this use case.
  - XGBoost/LightGBM: similar tree class; HistGB from sklearn keeps dependencies small and training fast.

07) Pipeline orchestration (src/pipeline.py)
- Inputs: ticker, intraday_days, `max_points` (cap rows), `train_window` (tail length), `minute_horizon`, `long_horizon_steps`, artifact_dir.
- Steps:
  1) Fetch 1m intraday (capped by `max_points`); if empty, load cache or combine with 1h context.
  2) Optionally tail-trim to `train_window` rows.
  3) Build supervised sets for 1m and 5m frequencies.
  4) Train or load models; compute predictions; recompute tail MAE.
  5) Return forecasts, price series, prediction series, and forecast markers for UI.
- Design rationale:
  - Tail trimming lets you focus on recent regimes without discarding full fetch.
  - Separate frequencies avoid leaking between grids and preserve horizon intent.
  - Returning time series (not just scalars) powers richer charting.

08) Trading / profit logic (app.py)
- Simple, user-driven mark-to-market:
  - User enters amount, clicks “Set investment”; units = amount / live price (fetched directly).
  - Profit = units * live_price – invested_amount.
  - Profit curve updates every refresh; “Sell now” realizes revenue/profit and clears holdings.
- Signals with animations:
  - Buy cue: `(next_hour_price - hour_mae) > 1.5 * live_price` → balloons.
  - Sell cue: `(next_minute_price - minute_mae) > 1.2 * last_bought_price` → snow.
- Rationale:
  - Keep execution explicit and transparent; no hidden fills or slippage simulation.
  - Show how forecasts map to user-facing cues without overpromising a strategy.

09) UI/UX (Streamlit, app.py)
- Live price: fetched each refresh via `latest_quote`; overrides pipeline price for actions/P&L.
- Charts:
  - Live vs Predicted: full history truncated to a fixed session cutoff window (default 8 hours), actual line + recent predicted tail + forecast markers; y-axis auto-scales with a small margin.
  - Profit over time: mark-to-market profit points (every refresh) from the time you set the investment; line + markers for visibility.
- Controls: ticker, data caps, horizons, training window, investment amount, set/sell buttons.
- Auto-refresh: 3-second loop to keep prices, forecasts, and profit synchronized.
- State: session stores units, invested amount, profit points, last bought price, chart cutoff, and withdraw state.

10) Configuration knobs
- `max_points`: cap intraday rows fetched (e.g., 50k–100k) to balance depth vs latency.
- `train_window`: tail length for training (0 = all fetched).
- `minute_horizon`, `long_horizon_steps`: forecast steps (1m grid and 5m grid).
- Ticker: default BTC-USD; mapping to Binance symbol handled in data fetch.
- Refresh cadence: 3s in `app.py` (adjust if needed).

11) Why these pipelines and not others
- Data: Binance chosen for depth and reliability of high-frequency bars; yfinance 1m is often constrained.
- Features: rolling stats and momentum are lightweight and effective for short-horizon regressors; avoid overfitting with too many exotic signals.
- Models: gradient boosting strikes a balance between speed, nonlinearity, and ease of tuning; heavy deep models are unnecessary for this demo.
- Tail MAE: focuses on current performance, not historical average that may hide regime drift.
- User-driven P&L: keeps the demo honest—no latent strategy assumptions, just the value of held units.

12) Future improvements
- Backtesting and execution modeling: add slippage, fees, and realistic fills.
- Regime detection: switch feature sets/models based on volatility/liquidity regimes.
- Portfolio view: multiple assets, risk budgeting, and correlation-aware sizing.
- Persistence: DB-backed positions/P&L for multi-user or durable state.
- Alerts: notifications when signals fire or thresholds cross.
- Explainability: SHAP or permutation importance to highlight drivers of forecasts.
- Monitoring: data quality checks, feature drift alerts, and model health dashboards.
- CI/CD: linting, tests, and deployment checks for the pipeline and app.

13) File-by-file
- `app.py`: Streamlit UI; live quote fetch; charts; buy/sell cues; investment and profit tracking; auto-refresh loop.
- `main.py`: CLI entry to run the pipeline once and print metrics/forecasts.
- `src/data_fetch.py`: Binance fetchers, normalization, optional cache load/save.
- `src/preprocess.py`: resampling, feature engineering, supervised framing, time-based split utilities.
- `src/models.py`: model pipeline definition, train/eval/predict/save/load.
- `src/pipeline.py`: orchestration of fetch → preprocess → train/load → predict → package results for UI.
- `requirements.txt`: Python deps (Streamlit, pandas, numpy, scikit-learn, altair, requests, joblib).
- `artifacts/`: cached history CSVs and saved models.

14) Conceptual deep dive: feature rationale
- Returns/log returns: capture short-term drift; log returns stabilize multiplicative changes.
- Rolling means: trend context; multiple windows prevent overreliance on a single scale.
- Rolling std: volatility regimes; informs risk-aware decisions and model context.
- Momentum: simple differencing to catch quick moves without heavy lookback.
- Range fraction: intrabar volatility proxy; can correlate with breakouts/mean reversion.
- Volume EMAs/stats: liquidity and pressure hints; short-term order flow proxy.

15) Conceptual deep dive: model rationale
- Tree boosting advantages:
  - Nonlinear and interaction-friendly without feature crosses.
  - Handles heteroscedasticity better than plain linear models.
  - Fast inference suitable for frequent refresh.
- Why not deep nets here:
  - Heavier ops and more tuning; less explainable out of the box.
  - For short horizons with tabular features, boosted trees are often competitive.
- Why not classical ARIMA-only:
  - Less flexible with exogenous features and nonstationary, regime-shifting crypto data.

16) Evaluation philosophy
- Use tail MAE (last 100 predictions) to track live-regime fitness.
- Separate horizons to keep expectations clear (1m vs ~45m).
- Prefer simplicity and transparency over complex metrics in the UI.

17) UI cues and logic
- Buy cue = `(next_hour_price - hour_mae) > 1.5 * live_price` → balloons.
- Sell cue = `(next_minute_price - minute_mae) > 1.2 * last_bought_price` → snow.
- These are illustrative thresholds; adjust as needed. They show how forecasts can map to action hints without executing trades.

18) Profit/P&L logic
- On “Set investment”: record units = amount / live price, start time, and reset profit history.
- Profit at any moment: units * live price – invested amount.
- Profit chart: records a point each refresh (3s) and renders line + markers; resets on sell or new investment.
- “Sell now”: realizes revenue at current live price, stores P&L, and clears holdings.

19) Fixed chart window and scaling
- Chart cutoff stored once per session (default last 8 hours from initial max timestamp) to avoid shifting windows.
- Y-axis uses tight margin (±2%) around observed values for clarity; fallback to auto-scale if no values.

20) Live deployment
- Streamlit Cloud: https://time-series-analysis-btc-forecasting.streamlit.app/
- Uses the same codebase; ensure network access for live Binance data.

21) How to run (app)
1) Install deps:
   ```bash
   pip install -r requirements.txt
   ```
2) Start Streamlit:
   ```bash
   streamlit run app.py
   ```
3) In the UI:
   - Set ticker, horizons, `max_points`, `train_window`.
   - Enter an amount and click “Set investment” to start live P&L.
   - Watch signals; click “Sell now” to realize revenue/P&L and reset.
   - Charts auto-refresh every ~3s.

22) How to run (CLI)
```bash
python main.py \
  --ticker BTC-USD \
  --max-points 50000 \
  --train-window 0 \
  --minute-horizon 1 \
  --long-horizon-steps 9
```

23) Operational notes
- Network required for live fetch; cached CSV in `artifacts/` can be used offline.
- Auto-refresh reruns the app; stop the process to halt.
- Signals are demo cues; no actual trading/execution is performed.

24) Extending this project
- Swap models: plug LightGBM/XGBoost or small neural nets into `src/models.py`.
- Add features: realized vol, order-book depth (if available), imbalance metrics.
- Add backtesting: simulate fills, slippage, fees, and risk constraints.
- Persist state: database for multi-user P&L and positions.
- Add alerts: email/push when cues trigger.
- Observability: logs/metrics for fetch latency, model drift, and UI health.

25) Risks and caveats
- Crypto is volatile; forecasts are not guarantees.
- Data quality issues (API hiccups) can affect training/prediction; cache mitigates but does not eliminate risk.
- No risk management or position sizing is enforced; user discretion required.

26) Summary
- This repository provides a practical blueprint for live BTC time-series forecasting with transparent features, lightweight models, and an interactive UI that ties forecasts to simple cues and live P&L.
- The architecture is modular: swap data sources, features, or models with minimal coupling.
- The live app link offers a ready-to-use deployment for quick exploration.

27) Detailed data flow
- Step A: `data_fetch` pulls 1m klines (and 1h context) from Binance, normalizes, and optionally caches.
- Step B: `preprocess` resamples, engineers features, and frames supervised datasets for both horizons.
- Step C: `models` builds pipelines; `pipeline` trains or loads and computes forecasts + tail MAE.
- Step D: `pipeline` returns price series, predictions, and forecast markers to `app.py`/CLI.
- Step E: `app.py` fetches a fresh live quote, overrides display price, renders charts, cues, and P&L.

28) Data schema (expected columns)
- open, high, low, close, volume (floats)
- datetime index (tz-naive after normalization)
- Derived features are internal and not persisted separately.

29) Configuration defaults
- Ticker: BTC-USD
- max_points: 50000
- train_window: 0 (use all fetched)
- minute_horizon: 1
- long_horizon_steps: 9 (≈45 minutes on 5m bars)
- Chart cutoff: last 8 hours from initial load, fixed per session
- Refresh cadence: 3 seconds

30) Performance considerations
- HistGradientBoosting is fast for the feature set size; suitable for frequent retrains on tens of thousands of rows.
- Resampling and feature calc are vectorized in pandas; keep `max_points` reasonable for low latency.
- Auto-refresh at 3s triggers repeated fetches; adjust if hitting rate limits.

31) Rate limits and networking
- Binance REST has per-minute limits; avoid unnecessary rapid fetches (reuse cached history where possible).
- Latest quote fetch occurs each refresh; consider slowing the refresh cadence if rate-limited.
- Offline mode: load cached CSV in `artifacts/` to allow UI exploration without network.

32) Testing and validation ideas
- Unit tests for feature shapes, NaN handling, and target alignment.
- Smoke tests for data fetch (mock API), model train/predict on small fixtures.
- Chart/UX smoke tests via Streamlit’s testing utilities (future work).

33) Deployment notes
- Local: `streamlit run app.py`.
- Cloud: Streamlit Cloud (as in the live deployment link); ensure environment vars and network egress are allowed.
- Artifacts: models and history cached in `artifacts/`; consider persistent storage if redeploying frequently.

34) Security considerations
- No secrets are required for public Binance endpoints; if adding authenticated endpoints, store keys securely.
- Sanitize user inputs if extending to broader tickers or parameters.
- Monitor dependency updates (requests, pandas, Streamlit) for security patches.

35) Extending to multiple assets
- Add a mapping layer for symbols (e.g., ETH-USD → ETHUSDT).
- Adjust horizons/feature windows per asset volatility profile.
- Consider per-asset `max_points`/`train_window` for memory and latency control.

36) Enhancing modeling
- Try LightGBM/XGBoost for potential gains; compare tail MAE and latency.
- Experiment with probabilistic forecasts (quantile regression, NGBoost) to add uncertainty estimates.
- Add regime-switching: choose model/feature sets based on recent vol or volume conditions.

37) Enhancing features
- Realized volatility over shorter windows; intraday seasonalities.
- Order book depth/imbalance (if available) for microstructure-aware features.
- Calendar features (hour-of-day/day-of-week) to capture intraday patterns.

38) Monitoring and observability
- Log fetch latency, model latency, and refresh cycle time.
- Track tail MAE over time to detect drift.
- Alert on fetch failures or excessive cache usage.

39) Known limitations
- No transaction cost or slippage modeling.
- Signals are heuristic thresholds, not optimized strategies.
- Session-based state; no persistent user portfolio across sessions.
- Auto-refresh reruns frequently; adjust cadence to avoid rate limits.

40) How to contribute or extend
- Fork and add tests around data fetch and feature engineering.
- Propose new feature sets or model variants in `src/models.py`.
- Add backtesting and execution simulators for more realistic strategy evaluation.
- Improve UI/UX with richer visual cues or multi-asset dashboards.

41) Quick FAQ
- Q: Can I use another asset?  
  A: Yes; change the ticker and ensure Binance symbol mapping is valid (e.g., ETH-USD → ETHUSDT).
- Q: How do I reduce latency?  
  A: Lower `max_points`, use a smaller `train_window`, and adjust refresh cadence.
- Q: Why is the line flat?  
  A: Check y-axis scaling and chart cutoff; tight scaling with 2% margin is applied, but extreme values can compress the view.
- Q: Can I disable auto-refresh?  
  A: Remove or change the sleep/rerun loop at the end of `app.py`.

42) Environmental assumptions
- Python 3.8+.
- Network egress allowed for Binance REST if live data is needed.
- Local filesystem write access for `artifacts/`.

43) License and usage
- This repo is for educational/demonstration purposes; no warranties.
- Adapt and extend at your own risk; crypto markets are volatile.

44) Live app recap
- URL: https://time-series-analysis-btc-forecasting.streamlit.app/
- Same codebase; refresh interval and signals as documented above.
45) FastAPI Dashboard (new architecture)
- FastAPI backend manages market updates, predictions, trade simulation, and WebSocket streaming.
- Frontend dashboard (Plotly) is served from `/static` and updates in real time.
- Redis is optional; if `REDIS_URL` is unset, the app falls back to in-memory cache.

How to run (FastAPI + dashboard)
1) Install deps:
   ```bash
   pip install -r requirements.txt
   ```
2) Optional: start Redis locally and set `REDIS_URL`, e.g. `redis://localhost:6379/0`.
3) Run the backend:
   ```bash
   uvicorn backend.main:app --reload
   ```
4) Open `http://localhost:8000` in a browser.

46) Fly.io deployment (FastAPI dashboard)
1) Install the Fly CLI: https://fly.io/docs/flyctl/install/
2) Login:
   ```bash
   fly auth login
   ```
3) Edit `fly.toml` and set `app` to a unique name (or run `fly launch --no-deploy` to generate it).
4) Deploy:
   ```bash
   fly deploy
   ```
5) Open `https://<your-app>.fly.dev`.

Optional Redis:
- Set a Redis URL via `fly secrets set REDIS_URL=redis://...` and redeploy.
47) Netlify frontend + Railway backend
- Deploy the FastAPI app to Railway (backend). Note the public URL (e.g. https://your-app.railway.app).
- Set allowed CORS origins on the backend (optional): set `CORS_ORIGINS` to your Netlify site URL.

Netlify steps (frontend only)
1) Set the backend URL in `static/config.js` before deploying:
   ```js
   window.BACKEND_URL = "https://your-app.railway.app";
   ```
2) Deploy to Netlify using the `static` folder as the publish directory.
3) Open the Netlify URL; the dashboard will connect to Railway for `/api` and `/ws`.
