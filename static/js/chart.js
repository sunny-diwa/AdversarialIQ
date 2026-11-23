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
    this.tvChart = null;
    this.candleSeries = null;
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

  updateHud(c) {
    if (!c) return;
    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.innerText = val;
    };
    setT("hud-ticker", this.currentSymbol);
    setT("hud-date", c.time || "--");
    setT("hud-open", `$${(typeof c.open === 'number' ? c.open : 0).toFixed(2)}`);
    setT("hud-high", `$${(typeof c.high === 'number' ? c.high : 0).toFixed(2)}`);
    setT("hud-low", `$${(typeof c.low === 'number' ? c.low : 0).toFixed(2)}`);
    setT("hud-close", `$${(typeof c.close === 'number' ? c.close : 0).toFixed(2)}`);

    const chg = (typeof c.close === 'number' && typeof c.open === 'number') ? (c.close - c.open) : 0;
    const pct = (typeof c.open === 'number' && c.open > 0) ? (chg / c.open * 100) : 0;
    const sign = chg >= 0 ? "+" : "";
    const chgEl = document.getElementById("hud-chg");
    if (chgEl) {
      chgEl.innerText = `${sign}${chg.toFixed(2)} (${sign}${pct.toFixed(2)}%)`;
      chgEl.style.color = chg >= 0 ? "var(--green-up)" : "var(--red-down)";
    }

    const vol = typeof c.volume === 'number' ? c.volume : 0;
    const volStr = vol > 1e6 ? `${(vol / 1e6).toFixed(1)}M` : `${(vol / 1e3).toFixed(0)}K`;
    setT("hud-vol", volStr);
  }

  renderMainChart(labels, candles, closePrices, openPrices, volumes) {
    if (!this.mainCanvas) return;
    const wrapper = document.getElementById("main-candlestick-wrapper") || this.mainCanvas.parentElement;

    // Default HUD to latest candle
    if (candles.length > 0) {
      this.updateHud(candles[candles.length - 1]);
    }

    // 1. If TradingView Lightweight Charts is loaded and available
    if (window.LightweightCharts && wrapper) {
      if (this.mainChart && typeof this.mainChart.destroy === "function") {
        this.mainChart.destroy();
        this.mainChart = null;
      }
      if (this.tvChart) {
        this.tvChart.remove();
        this.tvChart = null;
      }

      this.mainCanvas.style.display = "none";
      let tvContainer = document.getElementById("tv-chart-container");
      if (!tvContainer) {
        tvContainer = document.createElement("div");
        tvContainer.id = "tv-chart-container";
        tvContainer.style.width = "100%";
        tvContainer.style.height = "100%";
        tvContainer.style.position = "absolute";
        tvContainer.style.top = "0";
        tvContainer.style.left = "0";
        wrapper.appendChild(tvContainer);
      }
      tvContainer.style.display = "block";
      tvContainer.innerHTML = "";

      const w = wrapper.clientWidth || 800;
      const h = wrapper.clientHeight || 340;

      const tvChart = window.LightweightCharts.createChart(tvContainer, {
        width: w,
        height: h,
        layout: {
          background: { type: 'solid', color: '#090e18' },
          textColor: '#94a3b8',
          fontSize: 10,
          fontFamily: '"JetBrains Mono", monospace'
        },
        grid: {
          vertLines: { color: '#162035' },
          horzLines: { color: '#162035' }
        },
        crosshair: {
          mode: window.LightweightCharts.CrosshairMode ? window.LightweightCharts.CrosshairMode.Normal : 0,
        },
        rightPriceScale: {
          borderColor: '#1f2b3e',
        },
        timeScale: {
          borderColor: '#1f2b3e',
          timeVisible: true,
          secondsVisible: false
        }
      });
      this.tvChart = tvChart;

      // Real Japanese Candlestick Series
      const candleSeries = tvChart.addCandlestickSeries({
        upColor: '#00ff66',
        downColor: '#ff3344',
        borderVisible: false,
        wickUpColor: '#00ff66',
        wickDownColor: '#ff3344',
      });

      const tvCandleData = [];
      const seenDates = new Set();
      candles.forEach((c, idx) => {
        let dStr = (c.time || "").split(" ")[0];
        if (!dStr) {
          const d = new Date();
          d.setDate(d.getDate() - (candles.length - idx));
          dStr = d.toISOString().split("T")[0];
        }
        if (!seenDates.has(dStr)) {
          seenDates.add(dStr);
          tvCandleData.push({
            time: dStr,
            open: parseFloat(c.open || c.close),
            high: parseFloat(c.high || c.close),
            low: parseFloat(c.low || c.close),
            close: parseFloat(c.close)
          });
        }
      });
      tvCandleData.sort((a, b) => (a.time > b.time ? 1 : -1));
      candleSeries.setData(tvCandleData);

      // Volume histogram overlay
      const volSeries = tvChart.addHistogramSeries({
        color: '#00e5ff',
        priceFormat: { type: 'volume' },
        priceScaleId: '',
        scaleMargins: { top: 0.8, bottom: 0 },
      });
      const volData = tvCandleData.map((d, i) => {
        const c = candles[i] || {};
        return {
          time: d.time,
          value: c.volume || 10000000,
          color: d.close >= d.open ? 'rgba(0, 255, 102, 0.28)' : 'rgba(255, 51, 68, 0.28)'
        };
      });
      volSeries.setData(volData);

      // SMA 20 Overlay
      if (this.showSma20) {
        const sma20 = tvChart.addLineSeries({ color: '#ffcc00', lineWidth: 1.5, title: 'SMA 20' });
        sma20.setData(tvCandleData.map((d, i) => ({ time: d.time, value: candles[i]?.sma20 })).filter(d => typeof d.value === 'number'));
      }
      // SMA 50 Overlay
      if (this.showSma50) {
        const sma50 = tvChart.addLineSeries({ color: '#3b82f6', lineWidth: 1.5, title: 'SMA 50' });
        sma50.setData(tvCandleData.map((d, i) => ({ time: d.time, value: candles[i]?.sma50 })).filter(d => typeof d.value === 'number'));
      }
      // Bollinger Bands Overlay
      if (this.showBb) {
        const bbUp = tvChart.addLineSeries({ color: '#00e5ff', lineWidth: 1, lineStyle: 2, title: 'BB Up' });
        const bbLow = tvChart.addLineSeries({ color: '#00e5ff', lineWidth: 1, lineStyle: 2, title: 'BB Low' });
        bbUp.setData(tvCandleData.map((d, i) => ({ time: d.time, value: candles[i]?.bb_upper })).filter(d => typeof d.value === 'number'));
        bbLow.setData(tvCandleData.map((d, i) => ({ time: d.time, value: candles[i]?.bb_lower })).filter(d => typeof d.value === 'number'));
      }

      tvChart.subscribeCrosshairMove(param => {
        if (!param.time || !param.seriesData) return;
        const cData = param.seriesData.get(candleSeries);
        if (cData) {
          const matchingCandle = candles.find(c => (c.time || "").startsWith(param.time)) || cData;
          this.updateHud({
            time: param.time,
            open: cData.open,
            high: cData.high,
            low: cData.low,
            close: cData.close,
            volume: matchingCandle?.volume
          });
        }
      });

      return;
    }

    // 2. High-DPI HTML5 Canvas Japanese Candlestick Engine Fallback (Zero-Dependency)
    this.mainCanvas.style.display = "block";
    const tvContainer = document.getElementById("tv-chart-container");
    if (tvContainer) tvContainer.style.display = "none";

    this.renderCanvasCandlesticks(candles);
  }

  renderCanvasCandlesticks(candles) {
    if (!this.mainCanvas || !candles || candles.length === 0) return;
    const canvas = this.mainCanvas;
    const ctx = canvas.getContext("2d");
    const parent = canvas.parentElement;

    const dpr = window.devicePixelRatio || 1;
    const w = parent.clientWidth || 800;
    const h = parent.clientHeight || 340;

    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = `${w}px`;
    canvas.style.height = `${h}px`;
    ctx.scale(dpr, dpr);

    const padLeft = 10;
    const padRight = 65;
    const padTop = 15;
    const padBottom = 25;
    const plotW = w - padLeft - padRight;
    const plotH = h - padTop - padBottom;

    ctx.fillStyle = "#090e18";
    ctx.fillRect(0, 0, w, h);

    const lows = candles.map(c => typeof c.low === 'number' ? c.low : c.close);
    const highs = candles.map(c => typeof c.high === 'number' ? c.high : c.close);
    const minP = Math.min(...lows) * 0.995;
    const maxP = Math.max(...highs) * 1.005;
    const rangeP = Math.max(maxP - minP, 1.0);

    const yForP = (p) => padTop + (1 - (p - minP) / rangeP) * plotH;

    const maxVol = Math.max(...candles.map(c => c.volume || 1));
    const volH = (v) => ((v || 0) / maxVol) * (plotH * 0.22);

    // Grid lines & Right Price Axis
    ctx.strokeStyle = "#162035";
    ctx.lineWidth = 1;
    ctx.font = '10px "JetBrains Mono", monospace';
    ctx.fillStyle = "#94a3b8";
    ctx.textAlign = "left";

    const steps = 5;
    for (let i = 0; i <= steps; i++) {
      const pVal = minP + (rangeP * (i / steps));
      const y = yForP(pVal);
      ctx.beginPath();
      ctx.moveTo(padLeft, y);
      ctx.lineTo(w - padRight, y);
      ctx.stroke();
      ctx.fillText(`$${pVal.toFixed(2)}`, w - padRight + 6, y + 3);
    }

    const n = candles.length;
    const stepX = plotW / n;
    const candleW = Math.max(3, Math.min(18, stepX * 0.72));

    // Render Candles and Volumes
    candles.forEach((c, i) => {
      const x = padLeft + (i + 0.5) * stepX;
      const isUp = (c.close >= c.open);
      const col = isUp ? "#00ff66" : "#ff3344";

      // Volume Bar
      ctx.fillStyle = isUp ? "rgba(0, 255, 102, 0.22)" : "rgba(255, 51, 68, 0.22)";
      const vH = volH(c.volume);
      ctx.fillRect(x - candleW / 2, padTop + plotH - vH, candleW, vH);

      // Wick
      ctx.strokeStyle = col;
      ctx.lineWidth = 1.3;
      ctx.beginPath();
      ctx.moveTo(x, yForP(c.high));
      ctx.lineTo(x, yForP(c.low));
      ctx.stroke();

      // Body
      ctx.fillStyle = col;
      const openY = yForP(c.open);
      const closeY = yForP(c.close);
      const bodyTop = Math.min(openY, closeY);
      const bodyH = Math.max(1.5, Math.abs(openY - closeY));
      ctx.fillRect(x - candleW / 2, bodyTop, candleW, bodyH);
    });

    // Helper for overlay line
    const drawLine = (prop, color, dash = []) => {
      ctx.strokeStyle = color;
      ctx.lineWidth = 1.5;
      ctx.setLineDash(dash);
      ctx.beginPath();
      let started = false;
      candles.forEach((c, i) => {
        const val = c[prop];
        if (typeof val === 'number') {
          const x = padLeft + (i + 0.5) * stepX;
          const y = yForP(val);
          if (!started) {
            ctx.moveTo(x, y);
            started = true;
          } else {
            ctx.lineTo(x, y);
          }
        }
      });
      ctx.stroke();
      ctx.setLineDash([]);
    };

    if (this.showSma20) drawLine("sma20", "#ffcc00");
    if (this.showSma50) drawLine("sma50", "#3b82f6");
    if (this.showBb) {
      drawLine("bb_upper", "#00e5ff", [3, 3]);
      drawLine("bb_lower", "#00e5ff", [3, 3]);
    }
    drawLine("vwap", "#b388ff");

    // X-Axis Date Labels
    ctx.fillStyle = "#64748b";
    ctx.textAlign = "center";
    const labelStep = Math.max(1, Math.floor(n / 6));
    for (let i = 0; i < n; i += labelStep) {
      const x = padLeft + (i + 0.5) * stepX;
      const dStr = (candles[i].time || "").split(" ")[0];
      ctx.fillText(dStr.slice(5), x, h - 8);
    }

    // Attach interactive hover crosshair & HUD tracker
    canvas.onmousemove = (e) => {
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const idx = Math.floor((mouseX - padLeft) / stepX);
      if (idx >= 0 && idx < candles.length) {
        this.updateHud(candles[idx]);
      }
    };
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
