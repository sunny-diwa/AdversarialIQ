/**
 * Bloomberg Terminal V3.0 - S&P 500 Paper Trading Portfolio & Risk Desk
 * Institutional Risk Analytics: Win Rate, Profit Factor, Concentration Cap,
 * Equity Trajectory Curve & Risk-Based Position Sizing (FinRobot/TradingAgents Model)
 */

class SP500PaperPortfolio {
  constructor() {
    this.currentData = null;
    this.equityChart = null;
  }

  async init() {
    this.setupListeners();
    this.setupRiskSizing();
    await this.loadPortfolio();
  }

  setupListeners() {
    const buyBtn = document.getElementById("btn-quick-buy");
    const sellBtn = document.getElementById("btn-quick-sell");
    const resetBtn = document.getElementById("btn-reset-portfolio");

    if (buyBtn) buyBtn.addEventListener("click", () => this.handleQuickOrder("BUY"));
    if (sellBtn) sellBtn.addEventListener("click", () => this.handleQuickOrder("SELL"));
    if (resetBtn) resetBtn.addEventListener("click", () => this.handleReset());
  }

  setupRiskSizing() {
    // Risk-based and Allocation-based sizing chips
    const bindSizingChips = (selector, isRisk) => {
      document.querySelectorAll(selector).forEach(chip => {
        chip.addEventListener("click", () => {
          const sym = window.terminalApp ? window.terminalApp.activeSymbol : "NVDA";
          const price = window.terminalChart ? window.terminalChart.currentPrice || 100.0 : 100.0;
          let qty = 1;

          if (isRisk) {
            // Risk amount ($100 or $200) / estimated 4% stop-loss distance
            const riskDollars = parseFloat(chip.dataset.risk) || 200.0;
            const stopDist = Math.max(price * 0.04, 1.0);
            qty = Math.max(1, Math.floor(riskDollars / stopDist));
          } else {
            // Direct dollar allocation ($1,000 or $2,500)
            const allocDollars = parseFloat(chip.dataset.alloc) || 1000.0;
            qty = Math.max(1, Math.floor(allocDollars / price));
          }

          // Update qty inputs across both order pads
          const qtyInput1 = document.getElementById("order-qty-input");
          const qtyInput2 = document.getElementById("term-order-qty");
          if (qtyInput1) qtyInput1.value = qty;
          if (qtyInput2) qtyInput2.value = qty;

          // Trigger est cost update
          const estEl = document.getElementById("term-order-est");
          if (estEl && price) {
            estEl.innerText = `$${(price * qty).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
          }
        });
      });
    };

    bindSizingChips(".order-risk-chip, .term-risk-chip", true);
    bindSizingChips(".order-alloc-chip, .term-alloc-chip", false);
  }

  async loadPortfolio() {
    try {
      const aKey = localStorage.getItem("alpaca_api_key") || "";
      const aSec = localStorage.getItem("alpaca_secret_key") || "";
      let url = "/api/portfolio/get";
      if (aKey && aSec) {
        url += `?alpaca_key=${encodeURIComponent(aKey)}&alpaca_secret=${encodeURIComponent(aSec)}`;
      }

      const res = await fetch(url);
      const data = await res.json();
      this.currentData = data;
      this.renderOverview(data);
      this.renderPositions(data.positions || []);
      this.renderTradeBlotter(data.trades || data.recent_trades || []);
      this.renderEquityChart(data.equity_history || []);
      await this.loadThesesJournal();
      await this.loadReflections();
    } catch (e) {
      console.error("Failed to load portfolio:", e);
    }
  }

  renderOverview(p) {
    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.innerText = val !== undefined ? val : "--";
    };

    // Broker mode badge
    const brokerEl = document.getElementById("port-broker-mode");
    const indicatorEl = document.getElementById("port-alpaca-indicator");
    if (brokerEl) {
      if (p.mode === "ALPACA_PAPER") {
        brokerEl.innerText = `🟢 ALPACA US PAPER TRADING (Account: ${p.account_number || 'ACTIVE'})`;
        brokerEl.style.background = "#14532d";
        brokerEl.style.color = "#86efac";
        if (indicatorEl) indicatorEl.innerText = "Connected to Alpaca Paper Desk";
      } else {
        brokerEl.innerText = "SIMULATED LOCAL DESK ($10,000 BASE)";
        brokerEl.style.background = "#1e293b";
        brokerEl.style.color = "var(--cyan-primary)";
        if (indicatorEl) indicatorEl.innerText = "Local Simulated Desk (Alpaca Key in Settings)";
      }
    }

    // Primary Ledger Overview ($10K base or Alpaca Live)
    setT("port-total-equity", `$${p.total_equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
    setT("port-cash", `$${p.cash.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
    setT("port-holdings", `$${p.holdings_value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);

    const pnlEl = document.getElementById("port-total-pnl");
    if (pnlEl) {
      const isUp = p.total_pnl >= 0;
      const sign = isUp ? "+" : "";
      pnlEl.innerText = `${sign}$${p.total_pnl.toFixed(2)} (${sign}${p.total_pnl_pct.toFixed(2)}%)`;
      pnlEl.style.color = isUp ? "var(--green-up)" : "var(--red-down)";
    }

    setT("port-realized-pnl", `$${p.realized_pnl.toFixed(2)}`);

    // Advanced Risk Desk Analytics (TradingAgents Model)
    setT("port-win-rate", `${p.win_rate !== undefined ? p.win_rate : 0.0}%`);
    setT("port-profit-factor", `${p.profit_factor !== undefined ? p.profit_factor : 1.00}x`);

    const concEl = document.getElementById("port-concentration");
    if (concEl) {
      const conc = p.concentration_risk || 0.0;
      concEl.innerText = `${conc}% (${conc > 25 ? '⚠️ HIGH' : 'SAFE'})`;
      concEl.style.color = conc > 25 ? "var(--red-down)" : "var(--green-up)";
    }

    setT("port-cash-ratio", `${p.cash_ratio || 100}% Cash / ${p.invested_ratio || 0}% Stocks`);
    setT("port-total-trades", p.total_trades !== undefined ? p.total_trades : 0);

    // Sync Mini-Portfolio box on Chatbot page
    setT("agent-mini-equity", `$${p.total_equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
    setT("agent-mini-cash", `$${p.cash.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`);
    const miniPnl = document.getElementById("agent-mini-pnl");
    if (miniPnl) {
      const isUp = p.total_pnl >= 0;
      const sign = isUp ? "+" : "";
      miniPnl.innerText = `${sign}$${p.total_pnl.toFixed(2)} (${sign}${p.total_pnl_pct.toFixed(2)}%)`;
      miniPnl.style.color = isUp ? "var(--green-up)" : "var(--red-down)";
    }
  }

  renderPositions(positions) {
    const tbody = document.getElementById("portfolio-positions-tbody");
    if (!tbody) return;

    if (!positions || positions.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:18px; color:var(--text-muted);">No open positions. Account initialized with $10,000 cash (0 positions). Execute paper trades via Order Pad or Chatbot.</td></tr>`;
      return;
    }

    tbody.innerHTML = positions.map(pos => {
      const isUp = pos.unrealized_pnl >= 0;
      const sign = isUp ? "+" : "";
      const col = isUp ? "color:var(--green-up);" : "color:var(--red-down);";

      return `
        <tr class="clickable-row" data-sym="${pos.symbol}" title="Inspect ${pos.symbol}">
          <td><strong style="color:var(--cyan-primary);">${pos.symbol}</strong></td>
          <td style="text-align:right; font-weight:700;">${pos.quantity}</td>
          <td style="text-align:right;">$${pos.avg_price.toFixed(2)}</td>
          <td style="text-align:right; font-weight:700;">$${pos.current_price.toFixed(2)}</td>
          <td style="text-align:right;">$${pos.cost_basis.toLocaleString()}</td>
          <td style="text-align:right; font-weight:700;">$${pos.current_value.toLocaleString()}</td>
          <td style="text-align:right; ${col} font-weight:800;">${sign}$${pos.unrealized_pnl.toFixed(2)} (${sign}${pos.unrealized_pct.toFixed(2)}%)</td>
          <td style="text-align:center;">
            <button class="f-key btn-port-term" data-sym="${pos.symbol}" style="font-size:9.5px; padding:1px 5px;">📈 TERM</button>
            <button class="f-key btn-port-close" data-sym="${pos.symbol}" data-qty="${pos.quantity}" style="font-size:9.5px; padding:1px 5px; color:var(--red-down); border-color:var(--red-down);">CLOSE</button>
          </td>
        </tr>
      `;
    }).join("");

    tbody.querySelectorAll("tr.clickable-row").forEach(r => {
      r.addEventListener("click", (e) => {
        if (e.target.closest(".btn-port-term") || e.target.closest(".btn-port-close")) return;
        if (window.terminalApp) window.terminalApp.selectStock(r.dataset.sym);
      });
    });

    tbody.querySelectorAll(".btn-port-term").forEach(b => {
      b.addEventListener("click", (e) => {
        e.stopPropagation();
        if (window.terminalApp) {
          window.terminalApp.selectStock(b.dataset.sym);
          window.terminalApp.switchView("terminal");
        }
      });
    });

    tbody.querySelectorAll(".btn-port-close").forEach(b => {
      b.addEventListener("click", async (e) => {
        e.stopPropagation();
        const sym = b.dataset.sym;
        const qty = parseInt(b.dataset.qty) || 1;
        if (confirm(`Close entire position of ${qty} shares in ${sym} at market?`)) {
          try {
            const res = await fetch("/api/portfolio/trade", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ action: "SELL", symbol: sym, quantity: qty, rationale: "Manual Position Close" })
            });
            const data = await res.json();
            if (res.status === 200) {
              alert(`Position closed: ${data.message}`);
              await this.loadPortfolio();
            } else {
              alert(`Close failed: ${data.detail || data.message}`);
            }
          } catch (err) {
            alert(`Error closing position: ${err}`);
          }
        }
      });
    });
  }

  renderTradeBlotter(trades) {
    const tbody = document.getElementById("portfolio-blotter-tbody");
    if (!tbody) return;

    if (!trades || trades.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:12px; color:var(--text-muted);">No trades executed yet. Account initialized with $10,000 cash.</td></tr>`;
      return;
    }

    tbody.innerHTML = trades.slice().reverse().map(t => {
      const isBuy = t.type === "BUY";
      const col = isBuy ? "color:var(--green-up);" : "color:var(--amber-primary);";
      const pnlStr = t.pnl !== undefined ? (t.pnl >= 0 ? `+${t.pnl.toFixed(2)}` : `${t.pnl.toFixed(2)}`) : "--";
      const pnlCol = t.pnl !== undefined ? (t.pnl >= 0 ? "color:var(--green-up);" : "color:var(--red-down);") : "color:var(--text-muted);";

      return `
        <tr>
          <td style="color:var(--text-muted); font-size:10px;">${t.timestamp}</td>
          <td><strong style="${col}">${t.type}</strong></td>
          <td style="font-size:10px; color:#94a3b8;">${t.order_type || 'MARKET'}</td>
          <td><strong style="color:var(--cyan-primary);">${t.symbol}</strong></td>
          <td style="text-align:right;">${t.quantity}</td>
          <td style="text-align:right;">$${t.price.toFixed(2)}</td>
          <td style="text-align:right; font-weight:700;">$${t.total.toLocaleString()}</td>
          <td style="text-align:right; font-weight:bold; ${pnlCol}">${pnlStr}</td>
          <td style="font-size:10px; color:#cbd5e1; max-width:180px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${t.rationale || 'Manual Desk Execution'}</td>
        </tr>
      `;
    }).join("");
  }

  async loadThesesJournal() {
    const tbody = document.getElementById("portfolio-theses-tbody");
    if (!tbody) return;

    try {
      const res = await fetch("/api/memory/journal?limit=20");
      const theses = await res.json();
      if (!theses || theses.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:12px; color:var(--text-muted);">No recorded theses in SQLite database. Run Adversarial Tribunal on any stock to log a thesis.</td></tr>`;
        return;
      }

      tbody.innerHTML = theses.map(t => {
        const isBuy = t.action === "BUY";
        const actCol = isBuy ? "color:var(--green-up);" : "color:var(--amber-primary);";
        const pnl = t.realized_pnl;
        const pnlStr = pnl !== null && pnl !== undefined ? (pnl >= 0 ? `+$${pnl.toFixed(2)}` : `-$${Math.abs(pnl).toFixed(2)}`) : "--";
        const pnlCol = pnl !== null && pnl !== undefined ? (pnl >= 0 ? "color:var(--green-up);" : "color:var(--red-down);") : "color:var(--text-muted);";
        const convBadge = t.conviction_score >= 65 ? "background:#14532d; color:#86efac;" : (t.conviction_score <= 40 ? "background:#7f1d1d; color:#fca5a5;" : "background:#1e293b; color:#cbd5e1;");
        const statusCol = t.status === "OPEN" ? "color:var(--green-up);" : (t.status === "CLOSED" ? "color:#94a3b8;" : "color:var(--red-down);");

        return `
          <tr>
            <td style="color:var(--text-muted); font-size:10px;">${t.opened_at || '--'}</td>
            <td><strong style="color:var(--cyan-primary);">${t.symbol}</strong></td>
            <td><strong style="${actCol}">${t.action}</strong></td>
            <td style="text-align:right;">$${(t.entry_price || 0).toFixed(2)}</td>
            <td style="text-align:right;">${t.exit_price ? '$' + t.exit_price.toFixed(2) : '--'}</td>
            <td style="text-align:right; font-weight:bold; ${pnlCol}">${pnlStr}</td>
            <td style="text-align:center;"><span style="font-size:9.5px; padding:1px 6px; border-radius:3px; font-weight:bold; ${convBadge}">${t.conviction_score}/100</span></td>
            <td><strong style="${statusCol}">${t.status}</strong></td>
            <td style="font-size:10px; color:#cbd5e1; max-width:240px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${t.judge_ruling || '--'}</td>
          </tr>
        `;
      }).join("");
    } catch (e) {
      console.error("Error loading theses journal:", e);
    }
  }

  async loadReflections() {
    const tbody = document.getElementById("portfolio-reflections-tbody");
    if (!tbody) return;

    try {
      const res = await fetch("/api/memory/reflections?limit=10");
      const reflections = await res.json();
      if (!reflections || reflections.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:12px; color:var(--text-muted);">No post-mortem reflections recorded yet. Reflections are generated when paper trades are closed.</td></tr>`;
        return;
      }

      tbody.innerHTML = reflections.map(r => {
        const outCol = r.outcome === "WIN" ? "color:var(--green-up);" : (r.outcome === "LOSS" ? "color:var(--red-down);" : "color:var(--amber-primary);");
        return `
          <tr>
            <td style="color:var(--text-muted); font-size:10px;">${r.created_at || '--'}</td>
            <td><strong style="color:var(--cyan-primary);">${r.symbol}</strong></td>
            <td style="color:#94a3b8; font-size:10.5px;">${r.sector || 'Other'}</td>
            <td><strong style="${outCol}">${r.outcome}</strong></td>
            <td style="color:#f1f5f9; font-size:10.5px;">${r.lesson}</td>
            <td style="font-size:9.5px; color:var(--text-muted);">${r.key_factors || '--'}</td>
          </tr>
        `;
      }).join("");
    } catch (e) {
      console.error("Error loading agent reflections:", e);
    }
  }

  renderEquityChart(history) {
    const canvas = document.getElementById("portfolio-equity-canvas");
    if (!canvas) return;

    const ctx = canvas.getContext("2d");
    if (this.equityChart) this.equityChart.destroy();

    const labels = history.map(h => h.timestamp.split(" ")[1] || h.timestamp);
    const equityVals = history.map(h => h.equity);

    const isProfit = (equityVals[equityVals.length - 1] || 10000.0) >= 10000.0;
    const strokeCol = isProfit ? "#00ff66" : "#ff3344";

    this.equityChart = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: "Portfolio Equity ($)",
          data: equityVals,
          borderColor: strokeCol,
          backgroundColor: isProfit ? "rgba(0, 255, 102, 0.08)" : "rgba(255, 51, 68, 0.08)",
          borderWidth: 2,
          pointRadius: equityVals.length <= 1 ? 4 : 2,
          pointBackgroundColor: strokeCol,
          fill: true,
          tension: 0.2
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: "rgba(10, 14, 23, 0.95)",
            borderColor: strokeCol,
            borderWidth: 1,
            callbacks: {
              label: (ctx) => `Equity: $${Number(ctx.raw || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}`
            }
          }
        },
        scales: {
          x: {
            grid: { color: "#161f30" },
            ticks: { color: "#94a3b8", font: { family: "JetBrains Mono", size: 8 } }
          },
          y: {
            position: "right",
            grid: { color: "#161f30" },
            ticks: {
              color: "#94a3b8",
              font: { family: "JetBrains Mono", size: 9 },
              callback: (v) => `$${Number(v).toLocaleString()}`
            }
          }
        }
      }
    });
  }

  async handleQuickOrder(action) {
    const symInput = document.getElementById("order-symbol-input");
    const qtyInput = document.getElementById("order-qty-input");
    const typeSelect = document.getElementById("order-type-select");

    const symbol = (symInput ? symInput.value : window.terminalApp.activeSymbol || "NVDA").toUpperCase().trim();
    const quantity = parseInt(qtyInput ? qtyInput.value : "10");
    const order_type = typeSelect ? typeSelect.value : "MARKET";

    if (!symbol || quantity <= 0) {
      alert("Please specify a valid symbol and quantity > 0");
      return;
    }

    try {
      const aKey = localStorage.getItem("alpaca_api_key") || "";
      const aSec = localStorage.getItem("alpaca_secret_key") || "";

      const res = await fetch("/api/portfolio/trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          action,
          symbol,
          quantity,
          order_type,
          rationale: `Manual Order Pad (${order_type})`,
          alpaca_key: aKey,
          alpaca_secret: aSec
        })
      });

      const data = await res.json();
      if (res.status === 200) {
        alert(`Order Executed: ${data.message}`);
        await this.loadPortfolio();
      } else {
        alert(`Order Failed: ${data.detail || data.message}`);
      }
    } catch (e) {
      alert(`Trade error: ${e.message}`);
    }
  }

  async handleReset() {
    if (confirm("Reset paper trading account back to clean $10,000 cash balance and 0 positions?")) {
      try {
        await fetch("/api/portfolio/reset", { method: "POST" });
        await this.loadPortfolio();
        alert("Portfolio reset to initial $10,000 cash balance with 0 positions.");
      } catch (e) {
        alert(`Reset error: ${e.message}`);
      }
    }
  }
}

window.SP500PaperPortfolio = SP500PaperPortfolio;
