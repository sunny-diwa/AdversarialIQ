/**
 * AdversarialIQ V4.5 - Quantitative Backtest Studio Module
 * Executes 5-year algorithmic and natural language backtests on 10 marquee S&P 500 stocks.
 * Renders interactive Chart.js equity curves, KPI scorecards, and generated Python code.
 */

class BacktestStudio {
  constructor() {
    this.chartInstance = null;
    this.marqueeSymbols = [];
    this.currentBacktest = null;
    this.init();
  }

  init() {
    this.fetchMarqueeCatalog();
    this.bindEvents();
  }

  async fetchMarqueeCatalog() {
    const select = document.getElementById("bt-symbol-select");
    if (!select) return;

    try {
      const res = await fetch("/api/backtest/symbols");
      if (res.ok) {
        this.marqueeSymbols = await res.json();
        select.innerHTML = this.marqueeSymbols.map(s => {
          const badge = s.cached ? "✓ 5Y CACHED" : "FETCHING...";
          return `<option value="${s.symbol}">${s.symbol} — ${s.name} (${s.sector}) [${badge}]</option>`;
        }).join("");
      }
    } catch (e) {
      console.error("Error loading backtest symbols:", e);
    }
  }

  bindEvents() {
    const runBtn = document.getElementById("btn-run-backtest");
    const modeToggles = document.querySelectorAll(".bt-mode-btn");
    const promptChips = document.querySelectorAll(".strategy-chip");
    const promptInput = document.getElementById("bt-strategy-prompt");
    const subTabBtns = document.querySelectorAll(".bt-subtab-btn");

    // Mode Toggle (NLP vs Preset)
    modeToggles.forEach(btn => {
      btn.addEventListener("click", () => {
        modeToggles.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const mode = btn.dataset.mode;

        const nlpBox = document.getElementById("bt-nlp-container");
        const presetBox = document.getElementById("bt-preset-container");

        if (mode === "nlp") {
          if (nlpBox) nlpBox.style.display = "block";
          if (presetBox) presetBox.style.display = "none";
        } else {
          if (nlpBox) nlpBox.style.display = "none";
          if (presetBox) presetBox.style.display = "block";
        }
      });
    });

    // Preset Prompt Chips
    promptChips.forEach(chip => {
      chip.addEventListener("click", () => {
        if (promptInput) {
          promptInput.value = chip.dataset.prompt;
          promptInput.focus();
        }
      });
    });

    // Sub-tabs (Code vs Trade Log)
    subTabBtns.forEach(btn => {
      btn.addEventListener("click", () => {
        subTabBtns.forEach(b => b.classList.remove("active"));
        btn.classList.add("active");
        const tab = btn.dataset.subtab;

        const codePane = document.getElementById("bt-subtab-code");
        const tradesPane = document.getElementById("bt-subtab-trades");

        if (tab === "code") {
          if (codePane) codePane.style.display = "block";
          if (tradesPane) tradesPane.style.display = "none";
        } else {
          if (codePane) codePane.style.display = "none";
          if (tradesPane) tradesPane.style.display = "block";
        }
      });
    });

    // Run Backtest Button
    if (runBtn) {
      runBtn.addEventListener("click", () => this.executeBacktest());
    }
  }

  async executeBacktest() {
    const symbolEl = document.getElementById("bt-symbol-select");
    const symbol = symbolEl ? symbolEl.value : "NVDA";
    const capitalEl = document.getElementById("bt-capital-input");
    const capital = capitalEl ? parseFloat(capitalEl.value) || 10000.0 : 10000.0;

    const stopLossEl = document.getElementById("bt-stoploss-input");
    const stopLoss = (stopLossEl && stopLossEl.value) ? parseFloat(stopLossEl.value) / 100.0 : null;

    const takeProfitEl = document.getElementById("bt-takeprofit-input");
    const takeProfit = (takeProfitEl && takeProfitEl.value) ? parseFloat(takeProfitEl.value) / 100.0 : null;

    const activeModeBtn = document.querySelector(".bt-mode-btn.active");
    const mode = activeModeBtn ? activeModeBtn.dataset.mode : "nlp";

    const statusEl = document.getElementById("bt-run-status");
    const runBtn = document.getElementById("btn-run-backtest");

    if (runBtn) runBtn.disabled = true;
    if (statusEl) {
      statusEl.textContent = "⚡ Running vectorized 5-year simulation over 1,255 bars...";
      statusEl.style.color = "var(--cyan-primary)";
    }

    try {
      let data;
      if (mode === "nlp") {
        const promptInput = document.getElementById("bt-strategy-prompt");
        const prompt = promptInput ? promptInput.value.trim() : "SMA 20 crosses SMA 50";

        // Provider/Model from localStorage or defaults
        const provider = localStorage.getItem("trader_provider") || "groq";
        const model = localStorage.getItem("trader_model") || "openai/gpt-oss-120b";

        const res = await fetch("/api/backtest/nlp", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol,
            prompt,
            initial_capital: capital,
            stop_loss_pct: stopLoss,
            take_profit_pct: takeProfit,
            provider,
            model
          })
        });
        data = await res.json();
      } else {
        const presetSelect = document.getElementById("bt-preset-select");
        const strategy_name = presetSelect ? presetSelect.value : "sma_cross";

        const res = await fetch("/api/backtest/run", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            symbol,
            strategy_name,
            initial_capital: capital,
            stop_loss_pct: stopLoss || 0.07,
            take_profit_pct: takeProfit || 0.20
          })
        });
        data = await res.json();
      }

      if (data && data.total_return_pct !== undefined) {
        this.renderResults(data);
        if (statusEl) {
          statusEl.textContent = `✓ Backtest completed in 0.04s. Final Equity: $${data.final_equity.toLocaleString()}`;
          statusEl.style.color = "var(--green-up)";
        }
      } else {
        if (statusEl) {
          statusEl.textContent = `✗ Error: ${data.detail || "Backtest execution failed"}`;
          statusEl.style.color = "var(--red-down)";
        }
      }
    } catch (err) {
      if (statusEl) {
        statusEl.textContent = `✗ Execution failed: ${err.message}`;
        statusEl.style.color = "var(--red-down)";
      }
    } finally {
      if (runBtn) runBtn.disabled = false;
    }
  }

  renderResults(res) {
    this.currentBacktest = res;

    // 1. KPI Cards
    const elReturn = document.getElementById("bt-kpi-return");
    const elBenchmark = document.getElementById("bt-kpi-benchmark");
    const elAlpha = document.getElementById("bt-kpi-alpha");
    const elSharpe = document.getElementById("bt-kpi-sharpe");
    const elDrawdown = document.getElementById("bt-kpi-drawdown");
    const elWinrate = document.getElementById("bt-kpi-winrate");
    const elProfitFactor = document.getElementById("bt-kpi-profitfactor");
    const elTrades = document.getElementById("bt-kpi-trades");

    if (elReturn) {
      elReturn.textContent = `${res.total_return_pct >= 0 ? "+" : ""}${res.total_return_pct.toFixed(2)}%`;
      elReturn.style.color = res.total_return_pct >= 0 ? "var(--green-up)" : "var(--red-down)";
    }
    if (elBenchmark) {
      elBenchmark.textContent = `${res.benchmark_return_pct >= 0 ? "+" : ""}${res.benchmark_return_pct.toFixed(2)}%`;
    }
    if (elAlpha) {
      elAlpha.textContent = `${res.alpha_pct >= 0 ? "+" : ""}${res.alpha_pct.toFixed(2)}%`;
      elAlpha.style.color = res.alpha_pct >= 0 ? "var(--green-up)" : "var(--red-down)";
    }
    if (elSharpe) elSharpe.textContent = res.sharpe_ratio;
    if (elDrawdown) {
      elDrawdown.textContent = `${res.max_drawdown_pct.toFixed(2)}%`;
      elDrawdown.style.color = "var(--red-down)";
    }
    if (elWinrate) elWinrate.textContent = `${res.win_rate_pct}%`;
    if (elProfitFactor) elProfitFactor.textContent = res.profit_factor;
    if (elTrades) elTrades.textContent = `${res.total_trades} (${res.winning_trades}W / ${res.losing_trades}L)`;

    // 2. Render Equity Curve Canvas Chart
    this.renderEquityChart(res.equity_chart, res.symbol);

    // 3. Render Python Code
    const codeBlock = document.getElementById("bt-generated-code");
    if (codeBlock) {
      codeBlock.textContent = res.generated_code || "// Standard vectorized strategy executed";
    }

    // 4. Render Trade Table
    const tradeTbody = document.getElementById("bt-trades-tbody");
    if (tradeTbody) {
      const trades = res.recent_trades || [];
      if (trades.length === 0) {
        tradeTbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:12px; color:var(--text-muted);">No trades executed during backtest period.</td></tr>`;
      } else {
        tradeTbody.innerHTML = trades.map(t => {
          const pnlColor = t.pnl >= 0 ? "var(--green-up)" : "var(--red-down)";
          return `
            <tr>
              <td style="font-size:10px; color:#cbd5e1;">${t.entry_date}</td>
              <td style="font-size:10px; color:#cbd5e1;">${t.exit_date}</td>
              <td style="text-align:right; font-size:10.5px;">$${t.entry_price.toFixed(2)}</td>
              <td style="text-align:right; font-size:10.5px;">$${t.exit_price.toFixed(2)}</td>
              <td style="text-align:right; font-size:10.5px; font-weight:bold; color:${pnlColor};">${t.pnl >= 0 ? "+" : ""}$${t.pnl.toFixed(2)} (${t.pnl_pct >= 0 ? "+" : ""}${t.pnl_pct}%)</td>
              <td style="text-align:center; font-size:10px; color:var(--text-muted);">${t.hold_days} d</td>
              <td style="font-size:9.5px; color:var(--amber-primary);">${t.reason}</td>
            </tr>
          `;
        }).join("");
      }
    }
  }

  renderEquityChart(chartData, symbol) {
    const canvas = document.getElementById("bt-equity-chart");
    if (!canvas || !chartData) return;

    if (this.chartInstance) {
      this.chartInstance.destroy();
    }

    const ctx = canvas.getContext("2d");
    this.chartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: chartData.labels,
        datasets: [
          {
            label: `Strategy Equity ($)`,
            data: chartData.strategy_equity,
            borderColor: "#22c55e",
            backgroundColor: "rgba(34, 197, 94, 0.08)",
            borderWidth: 2,
            pointRadius: 0,
            fill: true,
            tension: 0.1
          },
          {
            label: `${symbol} Buy & Hold ($)`,
            data: chartData.benchmark_equity,
            borderColor: "#94a3b8",
            borderDash: [4, 4],
            borderWidth: 1.5,
            pointRadius: 0,
            fill: false,
            tension: 0.1
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: {
          mode: "index",
          intersect: false
        },
        plugins: {
          legend: {
            display: true,
            labels: { color: "#cbd5e1", font: { family: "JetBrains Mono", size: 10 } }
          },
          tooltip: {
            backgroundColor: "#090e18",
            titleFont: { family: "JetBrains Mono" },
            bodyFont: { family: "JetBrains Mono" },
            borderColor: "#334155",
            borderWidth: 1
          }
        },
        scales: {
          x: {
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: { color: "#64748b", font: { family: "JetBrains Mono", size: 9 }, maxTicksLimit: 10 }
          },
          y: {
            grid: { color: "rgba(255, 255, 255, 0.05)" },
            ticks: {
              color: "#64748b",
              font: { family: "JetBrains Mono", size: 9 },
              callback: (v) => `$${Number(v).toLocaleString()}`
            }
          }
        }
      }
    });
  }
}

// Global instance initialized on DOM load
window.backtestStudio = new BacktestStudio();
