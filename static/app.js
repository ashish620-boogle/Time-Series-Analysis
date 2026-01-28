const BASE_URL = (window.BACKEND_URL || "").replace(/\/$/, "");

function apiUrl(path) {
  if (!BASE_URL) {
    return path;
  }
  return `${BASE_URL}${path}`;
}

function wsUrl() {
  if (!BASE_URL) {
    const protocol = window.location.protocol === "https:" ? "wss" : "ws";
    return `${protocol}://${window.location.host}/ws`;
  }
  const url = new URL(BASE_URL);
  const protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${url.host}/ws`;
}

const elements = {
  connectionPill: document.getElementById("connection-pill"),
  updatedAt: document.getElementById("updated-at"),
  metricLatest: document.getElementById("metric-latest"),
  metricTicker: document.getElementById("metric-ticker"),
  metricMinute: document.getElementById("metric-minute"),
  metricHour: document.getElementById("metric-hour"),
  metricMinuteMae: document.getElementById("metric-minute-mae"),
  metricHourMae: document.getElementById("metric-hour-mae"),
  signalBuy: document.getElementById("signal-buy"),
  signalSell: document.getElementById("signal-sell"),
  portfolioUnits: document.getElementById("portfolio-units"),
  portfolioInvested: document.getElementById("portfolio-invested"),
  portfolioValue: document.getElementById("portfolio-value"),
  portfolioProfit: document.getElementById("portfolio-profit"),
  tradeEvents: document.getElementById("trade-events"),
  inputTicker: document.getElementById("input-ticker"),
  inputIntraday: document.getElementById("input-intraday"),
  inputMaxPoints: document.getElementById("input-max-points"),
  inputTrainWindow: document.getElementById("input-train-window"),
  inputMinuteHorizon: document.getElementById("input-minute-horizon"),
  inputLongHorizon: document.getElementById("input-long-horizon"),
  inputInvestAmount: document.getElementById("input-invest-amount"),
  inputAutoTrade: document.getElementById("input-auto-trade"),
  actionStatus: document.getElementById("action-status"),
  btnApply: document.getElementById("btn-apply"),
  btnRetrain: document.getElementById("btn-retrain"),
  btnBuy: document.getElementById("btn-buy"),
  btnSell: document.getElementById("btn-sell"),
};

let priceLayout = null;
let profitLayout = null;

function formatUSD(value) {
  if (!Number.isFinite(value)) {
    return "$--";
  }
  return `$${value.toFixed(2)}`;
}

function formatNumber(value, digits = 4) {
  if (!Number.isFinite(value)) {
    return "--";
  }
  return value.toFixed(digits);
}

function setText(el, value) {
  if (el) {
    el.textContent = value;
  }
}

function setConnection(isOnline) {
  if (!elements.connectionPill) {
    return;
  }
  elements.connectionPill.textContent = isOnline ? "Live" : "Offline";
  elements.connectionPill.classList.toggle("offline", !isOnline);
}

function setActionStatus(message, isError = false) {
  if (!elements.actionStatus) {
    return;
  }
  elements.actionStatus.textContent = message;
  elements.actionStatus.classList.toggle("error", isError);
}

function toggleSignal(element, isActive) {
  if (!element) {
    return;
  }
  element.classList.toggle("active", Boolean(isActive));
}

function updateEvents(events) {
  if (!elements.tradeEvents) {
    return;
  }
  if (!events || events.length === 0) {
    elements.tradeEvents.innerHTML = "<li>Waiting for trades...</li>";
    return;
  }
  const recent = events.slice(-6).reverse();
  elements.tradeEvents.innerHTML = recent
    .map(
      (event) => {
        const profit =
          event.kind === "sell" && Number.isFinite(Number(event.profit))
            ? ` | P/L ${formatUSD(Number(event.profit))}`
            : "";
        return `<li>${event.kind.toUpperCase()} - ${event.units} units @ $${event.price}${profit} <br><small>${event.timestamp}</small></li>`;
      }
    )
    .join("");
}

function initCharts() {
  priceLayout = {
    margin: { t: 10, r: 10, b: 40, l: 50 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    xaxis: { color: "#6b6258", showgrid: false },
    yaxis: { color: "#6b6258", gridcolor: "rgba(31,27,22,0.08)" },
    legend: { orientation: "h", y: 1.1 },
  };

  profitLayout = {
    margin: { t: 10, r: 10, b: 40, l: 50 },
    paper_bgcolor: "rgba(0,0,0,0)",
    plot_bgcolor: "rgba(0,0,0,0)",
    xaxis: { color: "#6b6258", showgrid: false },
    yaxis: { color: "#6b6258", gridcolor: "rgba(31,27,22,0.08)" },
  };

  Plotly.newPlot("price-chart", [], priceLayout, { responsive: true });
  Plotly.newPlot("profit-chart", [], profitLayout, { responsive: true });
}

function updateCharts(payload) {
  const actual = (payload.series && payload.series.actual) || [];
  const predictedValidation =
    (payload.series && payload.series.predicted_validation) || [];
  const predictedTest =
    (payload.series && payload.series.predicted_test) || [];
  const forecast = (payload.series && payload.series.forecast) || [];

  const actualTrace = {
    x: actual.map((p) => p.timestamp),
    y: actual.map((p) => p.value),
    type: "scatter",
    mode: "lines",
    line: { color: "#0d7b70", width: 2 },
    name: "Actual",
  };

  const validationTrace = {
    x: predictedValidation.map((p) => p.timestamp),
    y: predictedValidation.map((p) => p.value),
    type: "scatter",
    mode: "lines",
    line: { color: "#e76f51", width: 2, dash: "dot" },
    name: "Validation",
  };

  const testTrace = {
    x: predictedTest.map((p) => p.timestamp),
    y: predictedTest.map((p) => p.value),
    type: "scatter",
    mode: "lines",
    line: { color: "#f1c40f", width: 2, dash: "dash" },
    name: "Test",
  };

  const forecastTrace = {
    x: forecast.map((p) => p.timestamp),
    y: forecast.map((p) => p.value),
    type: "scatter",
    mode: "markers+text",
    text: forecast.map((p) => p.label || ""),
    textposition: "top center",
    marker: { color: "#264653", size: 10 },
    name: "Forecast",
  };

  Plotly.react(
    "price-chart",
    [actualTrace, validationTrace, testTrace, forecastTrace],
    priceLayout,
    { responsive: true }
  );

  const profitPoints = (payload.portfolio && payload.portfolio.profit_points) || [];
  const profitTrace = {
    x: profitPoints.map((p) => p.timestamp),
    y: profitPoints.map((p) => p.profit),
    type: "scatter",
    mode: "lines+markers",
    line: { color: "#2a9d8f", width: 2 },
    marker: { size: 6, color: "#2a9d8f" },
    name: "Profit",
  };

  Plotly.react("profit-chart", [profitTrace], profitLayout, { responsive: true });
}

function applyState(payload) {
  if (!payload) {
    return;
  }
  const latestPrice = Number(payload.latest_price);
  const minuteForecast = Number(payload.next_minute_price);
  const hourForecast = Number(payload.next_hour_price);
  const minuteMae = Number(payload.minute_mae);
  const hourMae = Number(payload.hour_mae);

  setText(elements.metricLatest, formatUSD(latestPrice));
  setText(elements.metricMinute, formatUSD(minuteForecast));
  setText(elements.metricHour, formatUSD(hourForecast));
  setText(elements.metricMinuteMae, formatNumber(minuteMae));
  setText(elements.metricHourMae, formatNumber(hourMae));
  setText(elements.metricTicker, payload.ticker || "--");
  setText(elements.updatedAt, payload.updated_at || "--");

  const portfolio = payload.portfolio || {};
  setText(elements.portfolioUnits, portfolio.units || 0);
  setText(elements.portfolioInvested, formatUSD(Number(portfolio.invested_amount)));
  setText(elements.portfolioValue, formatUSD(Number(portfolio.portfolio_value)));
  setText(elements.portfolioProfit, formatUSD(Number(portfolio.profit)));

  const signals = payload.signals || {};
  toggleSignal(elements.signalBuy, signals.buy);
  toggleSignal(elements.signalSell, signals.sell);

  updateEvents(portfolio.events || []);
  updateCharts(payload);
}

async function postJSON(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : null,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || "Request failed");
  }
  return response.json();
}

function numberOrNull(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

async function loadConfig() {
  try {
    const response = await fetch(apiUrl("/api/config"));
    const config = await response.json();
    if (!config) {
      return;
    }
    if (elements.inputTicker) elements.inputTicker.value = config.ticker || "";
    if (elements.inputIntraday) elements.inputIntraday.value = config.intraday_days || "";
    if (elements.inputMaxPoints) elements.inputMaxPoints.value = config.max_points || "";
    if (elements.inputTrainWindow) elements.inputTrainWindow.value = config.train_window || "";
    if (elements.inputMinuteHorizon) elements.inputMinuteHorizon.value = config.minute_horizon || "";
    if (elements.inputLongHorizon) elements.inputLongHorizon.value = config.long_horizon_steps || "";
    if (elements.inputInvestAmount) elements.inputInvestAmount.value = config.invest_amount || "";
    if (elements.inputAutoTrade) elements.inputAutoTrade.checked = Boolean(config.auto_trade);
  } catch (error) {
    setActionStatus("Config load failed.", true);
  }
}

function bindActions() {
  if (elements.btnApply) {
    elements.btnApply.addEventListener("click", async () => {
      const payload = {
        ticker: elements.inputTicker.value.trim() || undefined,
        intraday_days: numberOrNull(elements.inputIntraday.value),
        max_points: numberOrNull(elements.inputMaxPoints.value),
        train_window: numberOrNull(elements.inputTrainWindow.value),
        minute_horizon: numberOrNull(elements.inputMinuteHorizon.value),
        long_horizon_steps: numberOrNull(elements.inputLongHorizon.value),
        invest_amount: numberOrNull(elements.inputInvestAmount.value),
        auto_trade: elements.inputAutoTrade.checked,
      };

      Object.keys(payload).forEach((key) => {
        if (payload[key] === null || payload[key] === undefined || payload[key] === "") {
          delete payload[key];
        }
      });

      try {
        setActionStatus("Updating settings...");
        await postJSON(apiUrl("/api/config"), payload);
        setActionStatus("Settings updated.");
      } catch (error) {
        setActionStatus(error.message || "Update failed.", true);
      }
    });
  }

  if (elements.btnRetrain) {
    elements.btnRetrain.addEventListener("click", async () => {
      try {
        setActionStatus("Retraining models...");
        await postJSON(apiUrl("/api/retrain"));
        setActionStatus("Retrain triggered.");
      } catch (error) {
        setActionStatus(error.message || "Retrain failed.", true);
      }
    });
  }

  if (elements.btnBuy) {
    elements.btnBuy.addEventListener("click", async () => {
      try {
        setActionStatus("Submitting buy...");
        const amount = numberOrNull(elements.inputInvestAmount.value);
        await postJSON(apiUrl("/api/trade/buy"), amount ? { amount } : {});
        setActionStatus("Buy executed.");
      } catch (error) {
        setActionStatus(error.message || "Buy failed.", true);
      }
    });
  }

  if (elements.btnSell) {
    elements.btnSell.addEventListener("click", async () => {
      try {
        setActionStatus("Submitting sell...");
        await postJSON(apiUrl("/api/trade/sell"));
        setActionStatus("Sell executed.");
      } catch (error) {
        setActionStatus(error.message || "Sell failed.", true);
      }
    });
  }
}

function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const socket = new WebSocket(wsUrl());

  socket.addEventListener("open", () => {
    setConnection(true);
  });

  socket.addEventListener("message", (event) => {
    try {
      const payload = JSON.parse(event.data);
      applyState(payload);
    } catch (error) {
      setActionStatus("Bad data from server.", true);
    }
  });

  socket.addEventListener("close", () => {
    setConnection(false);
    setTimeout(connectWebSocket, 2000);
  });

  socket.addEventListener("error", () => {
    socket.close();
  });
}

async function loadState() {
  try {
    const response = await fetch(apiUrl("/api/state"));
    const payload = await response.json();
    applyState(payload);
  } catch (error) {
    setActionStatus("State load failed.", true);
  }
}

initCharts();
bindActions();
loadConfig();
loadState();
connectWebSocket();
