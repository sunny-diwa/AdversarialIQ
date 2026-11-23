/**
 * Bloomberg Terminal V3.0 - Candlestick Price Chart & Indicator Suite
 * Multi-Indicator Rendering: Candlesticks, SMA, BB, RSI, MACD, Volume
 * Integrated Terminal Lower Deck: Quant Setup, Live Order Pad & Terminal CLI Simulator
 */

class SP500PriceChart {
  constructor(mainCanvasId, rsiCanvasId, macdCanvasId) {
    this.mainCanvas = document.getElementById(mainCanvasId);
    this.rsiCanvas = document.getElementById(rsiCanvasId);
    this.macdCanvas = document.getElementById(macdCanvasId);

    this.mainChart = null;
    this.rsiChart = null;
    this.macdChart = null;

    this.currentSymbol = "NVDA";
    this.currentPeriod = "1mo";

    this.showSma20 = true;
    this.showSma50 = true;
    this.showBb = true;
    this.showRsi = true;
    this.showMacd = true;

    this.cachedData = null;
    this.currentPrice = 0;
  }

  async init(symbol = "NVDA") {
    this.currentSymbol = symbol;
    this.setupListeners();
    this.setupTerminalOrderPad();
    await this.loadChartData(this.currentSymbol, this.currentPeriod);
  }

  setupListeners() {
    // Timeframe selector buttons
    document.querySelectorAll(".chart-tf-btn").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        document.querySelectorAll(".chart-tf-btn").forEach(b => b.classList.remove("active"));
        e.target.classList.add("active");
        this.currentPeriod = e.target.dataset.period;
        await this.loadChartData(this.currentSymbol, this.currentPeriod);
      });
    });

    // Indicator toggles
    const bindToggle = (id, prop) => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("change", (e) => {
          this[prop] = e.target.checked;
          if (this.cachedData) this.render(this.cachedData);
        });
      }
    };

    bindToggle("toggle-sma20", "showSma20");
    bindToggle("toggle-sma50", "showSma50");
    bindToggle("toggle-bb", "showBb");
    bindToggle("toggle-rsi", "showRsi");
    bindToggle("toggle-macd", "showMacd");
  }

  setupTerminalOrderPad() {
    const qtyInput = document.getElementById("term-order-qty");
    const updateEst = () => {
      const qty = parseInt(qtyInput ? qtyInput.value : 10) || 10;
      const estEl = document.getElementById("term-order-est");
      if (estEl && this.currentPrice) {
        estEl.innerText = `$${(this.currentPrice * qty).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
      }
    };

    if (qtyInput) {
      qtyInput.addEventListener("input", updateEst);
    }

    const buyBtn = document.getElementById("btn-term-buy");
    const sellBtn = document.getElementById("btn-term-sell");

    const execTrade = async (action) => {
      const qty = parseInt(qtyInput ? qtyInput.value : 10) || 10;
      try {
        const res = await fetch("/api/portfolio/trade", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            action: action,
            symbol: this.currentSymbol,
            quantity: qty
          })
        });
        const data = await res.json();
        if (res.status === 200) {
          alert(`ORDER FILLED: ${data.action} ${data.quantity} shares of ${data.symbol} @ $${data.execution_price.toFixed(2)}`);
          if (window.terminalPortfolio) window.terminalPortfolio.loadPortfolio();
        } else {
          alert(`Order rejected: ${data.detail || 'Insufficient cash or holdings'}`);
        }
      } catch (e) {
        alert(`Trade execution failed: ${e}`);
      }
    };

    if (buyBtn) buyBtn.addEventListener("click", () => execTrade("BUY"));
    if (sellBtn) sellBtn.addEventListener("click", () => execTrade("SELL"));
  }

  async loadChartData(symbol, period) {
    this.currentSymbol = symbol;
    this.currentPeriod = period;

    const symHeader = document.getElementById("chart-active-symbol");
    if (symHeader) symHeader.innerText = `${symbol} // TRADING TERMINAL`;

    const termSym = document.getElementById("term-order-sym");
    if (termSym) termSym.innerText = symbol;

    try {
      const res = await fetch(`/api/stock/${encodeURIComponent(symbol)}/history?period=${period}`);
      const json = await res.json();
      this.cachedData = json;
      this.render(json);
      this.updateIndicatorsPanel(json.summary || {}, json.candles || []);
      this.updateTerminalDesk(json);
    } catch (e) {
      console.error("Failed to load chart data:", e);
    }
  }

  render(json) {
    const candles = json.candles || [];
    if (!candles || candles.length === 0) return;

    const labels = candles.map(c => c.time);
    const closePrices = candles.map(c => c.close);
    const openPrices = candles.map(c => c.open);
    const volumes = candles.map(c => c.volume);

    this.currentPrice = closePrices[closePrices.length - 1];

    // 1. Render Main Price & Overlay Chart
    this.renderMainChart(labels, candles, closePrices, openPrices, volumes);

    // 2. Render RSI Sub-chart
    const rsiWrapper = document.getElementById("rsi-sub-container");
    if (this.showRsi) {
      if (rsiWrapper) rsiWrapper.style.display = "block";
      this.renderRsiChart(labels, candles);
    } else {
      if (rsiWrapper) rsiWrapper.style.display = "none";
    }

    // 3. Render MACD Sub-chart
    const macdWrapper = document.getElementById("macd-sub-container");
    if (this.showMacd) {
      if (macdWrapper) macdWrapper.style.display = "block";
      this.renderMacdChart(labels, candles);
    } else {
      if (macdWrapper) macdWrapper.style.display = "none";
    }
  }

  renderMainChart(labels, candles, closePrices, openPrices, volumes) {
    if (!this.mainCanvas) return;
    const ctx = this.mainCanvas.getContext("2d");

    if (this.mainChart) this.mainChart.destroy();

    const isUp = closePrices[closePrices.length - 1] >= closePrices[0];
    const baseColor = isUp ? "#00ff66" : "#ff3344";

    const datasets = [
      {
        type: "line",
        label: "Price Close",
        data: closePrices,
        borderColor: baseColor,
        borderWidth: 2,
        pointRadius: 0,
        fill: true,
        backgroundColor: isUp ? "rgba(0, 255, 102, 0.08)" : "rgba(255, 51, 68, 0.08)",
        tension: 0.1,
        yAxisID: "y"
      }
    ];

    // Overlays
    if (this.showSma20) {
      datasets.push({
        type: "line",
        label: "SMA 20",
        data: candles.map(c => c.sma20),
        borderColor: "#ffcc00",
        borderWidth: 1.5,
        pointRadius: 0,
        fill: false,
        borderDash: [4, 4],
        yAxisID: "y"
      });
    }

    if (this.showSma50) {
      datasets.push({
        type: "line",
        label: "SMA 50",
        data: candles.map(c => c.sma50),
        borderColor: "#3b82f6",
        borderWidth: 1.5,
        pointRadius: 0,
        fill: false,
        yAxisID: "y"
      });
    }

    if (this.showBb) {
      datasets.push({
        type: "line",
        label: "BB Upper",
        data: candles.map(c => c.bb_upper),
        borderColor: "#00e5ff",
        borderWidth: 1,
        pointRadius: 0,
        fill: false,
        borderDash: [2, 2],
        yAxisID: "y"
      });
      datasets.push({
        type: "line",
        label: "BB Lower",
        data: candles.map(c => c.bb_lower),
        borderColor: "#00e5ff",
        borderWidth: 1,
        pointRadius: 0,
        fill: false,
        borderDash: [2, 2],
        yAxisID: "y"
      });
    }

    this.mainChart = new Chart(ctx, {
      data: {
        labels: labels,
        datasets: datasets
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: {
            display: true,
            labels: { color: "#94a3b8", font: { family: "JetBrains Mono", size: 10 }, boxWidth: 12 }
          },
          tooltip: {
            backgroundColor: "rgba(10, 14, 23, 0.95)",
            borderColor: "#ff9900",
            borderWidth: 1,
            titleFont: { family: "JetBrains Mono", size: 11, weight: "bold" },
            bodyFont: { family: "JetBrains Mono", size: 10 },
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: $${Number(ctx.raw || 0).toFixed(2)}`
            }
          }
        },
        scales: {
          x: {
            grid: { color: "#161f30" },
            ticks: { color: "#94a3b8", font: { family: "JetBrains Mono", size: 9 }, maxTicksLimit: 10 }
          },
          y: {
            position: "right",
            grid: { color: "#161f30" },
            ticks: {
              color: "#94a3b8",
              font: { family: "JetBrains Mono", size: 10 },
              callback: (val) => `$${Number(val || 0).toFixed(2)}`
            }
          }
        }
      }
    });
  }

  renderRsiChart(labels, candles) {
    if (!this.rsiCanvas) return;
    const ctx = this.rsiCanvas.getContext("2d");

    if (this.rsiChart) this.rsiChart.destroy();

    const rsiValues = candles.map(c => c.rsi);

    this.rsiChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: "RSI (14)",
          data: rsiValues,
          borderColor: "#ff9900",
          borderWidth: 1.5,
          pointRadius: 0,
          fill: false,
          tension: 0.1
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(10, 14, 23, 0.95)",
            borderColor: "#ff9900",
            borderWidth: 1,
            titleFont: { family: "JetBrains Mono", size: 10 },
            bodyFont: { family: "JetBrains Mono", size: 10 }
          }
        },
        scales: {
          x: { display: false },
          y: {
            position: "right",
            min: 10,
            max: 90,
            grid: { color: "#161f30" },
            ticks: {
              color: "#94a3b8",
              font: { family: "JetBrains Mono", size: 9 },
              stepSize: 20
            }
          }
        }
      }
    });
  }

  renderMacdChart(labels, candles) {
    if (!this.macdCanvas) return;
    const ctx = this.macdCanvas.getContext("2d");

    if (this.macdChart) this.macdChart.destroy();

    const macdValues = candles.map(c => c.macd);
    const signalValues = candles.map(c => c.macd_signal);
    const histValues = candles.map(c => c.macd_hist);

    this.macdChart = new Chart(ctx, {
      data: {
        labels: labels,
        datasets: [
          {
            type: "bar",
            label: "Histogram",
            data: histValues,
            backgroundColor: histValues.map(v => (v || 0) >= 0 ? "rgba(0, 255, 102, 0.6)" : "rgba(255, 51, 68, 0.6)")
          },
          {
            type: "line",
            label: "MACD",
            data: macdValues,
            borderColor: "#00e5ff",
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false
          },
          {
            type: "line",
            label: "Signal",
            data: signalValues,
            borderColor: "#ff3344",
            borderWidth: 1.2,
            pointRadius: 0,
            fill: false
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: {
            display: true,
            labels: { color: "#94a3b8", font: { family: "JetBrains Mono", size: 9 }, boxWidth: 10 }
          }
        },
        scales: {
          x: { display: false },
          y: {
            position: "right",
            grid: { color: "#161f30" },
            ticks: { color: "#94a3b8", font: { family: "JetBrains Mono", size: 9 } }
          }
        }
      }
    });
  }

  updateIndicatorsPanel(summary, candles) {
    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.innerText = val !== undefined && val !== null ? val : "--";
    };

    const latest = candles.length > 0 ? candles[candles.length - 1] : {};

    setT("val-price", latest.close ? `$${latest.close.toFixed(2)}` : "--");
    setT("val-rsi", summary.rsi !== undefined ? `${summary.rsi} (${summary.rsi_state || 'NEUTRAL'})` : "--");
    setT("val-macd", summary.macd !== undefined ? `${summary.macd} (${summary.macd_trend || 'NEUTRAL'})` : "--");
    setT("val-sma20", summary.sma20 ? `$${summary.sma20}` : "--");
    setT("val-sma50", summary.sma50 ? `$${summary.sma50}` : "--");
    setT("val-bb-up", latest.bb_upper ? `$${latest.bb_upper.toFixed(2)}` : "--");
    setT("val-bb-low", latest.bb_lower ? `$${latest.bb_lower.toFixed(2)}` : "--");
  }

  updateTerminalDesk(json) {
    const candles = json.candles || [];
    if (candles.length === 0) return;

    const latest = candles[candles.length - 1];
    const price = latest.close || 100.0;

    // Calculate 20-day high and low
    const slice20 = candles.slice(-20);
    const high20 = Math.max(...slice20.map(c => c.high || price));
    const low20 = Math.min(...slice20.map(c => c.low || price));

    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.innerText = val;
    };

    setT("term-20d-range", `$${low20.toFixed(2)} - $${high20.toFixed(2)}`);
    setT("term-target-price", `$${(high20 * 1.025).toFixed(2)}`);
    setT("term-stop-price", `$${(low20 * 0.985).toFixed(2)}`);

    // Signal verdict
    const summary = json.summary || {};
    const rsi = summary.rsi || 50;
    const isBull = (summary.macd || 0) > (summary.macd_signal || 0) && price >= (summary.sma50 || 0);

    const verdictEl = document.getElementById("term-signal-verdict");
    if (verdictEl) {
      if (rsi <= 35) {
        verdictEl.innerText = "RSI OVERSOLD (DIP BUY)";
        verdictEl.style.color = "var(--green-up)";
      } else if (rsi >= 65) {
        verdictEl.innerText = "RSI OVERBOUGHT (TAKE PROFIT)";
        verdictEl.style.color = "var(--red-down)";
      } else if (isBull) {
        verdictEl.innerText = "BULLISH MOMENTUM";
        verdictEl.style.color = "var(--green-up)";
      } else {
        verdictEl.innerText = "BEARISH TREND";
        verdictEl.style.color = "var(--red-down)";
      }
    }

    // Update order est
    const qtyInput = document.getElementById("term-order-qty");
    const qty = parseInt(qtyInput ? qtyInput.value : 10) || 10;
    setT("term-order-est", `$${(price * qty).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

    // Update CLI simulator feed
    const cliFeed = document.getElementById("term-cli-feed");
    if (cliFeed) {
      cliFeed.innerHTML = `
[SHELL COMMAND] > python terminal_trader.py ${this.currentSymbol}
------------------------------------------------------------
TICKER: ${this.currentSymbol} | LAST: $${price.toFixed(2)} | RSI(14): ${rsi}
20-DAY HIGH: $${high20.toFixed(2)} | 20-DAY LOW: $${low20.toFixed(2)}
MACD: ${summary.macd || 0} (Signal: ${summary.macd_signal || 0})
Trade Target: $${(high20 * 1.025).toFixed(2)} | Stop-Loss: $${(low20 * 0.985).toFixed(2)}
Virtual Ledger: Ready to route BUY/SELL ${this.currentSymbol} to $10,000 paper account.
`;
    }
  }
}

window.SP500PriceChart = SP500PriceChart;
