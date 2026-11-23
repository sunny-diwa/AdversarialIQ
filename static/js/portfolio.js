/**
 * Bloomberg Terminal V3.0 - S&P 500 Paper Trading Portfolio Engine
 * Mark-to-Market Valuation, Position Blotter & Order Pad Execution
 */

class SP500PaperPortfolio {
  constructor() {
    this.currentData = null;
  }

  async init() {
    this.setupListeners();
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

  async loadPortfolio() {
    try {
      const res = await fetch("/api/portfolio/get");
      const data = await res.json();
      this.currentData = data;
      this.renderOverview(data);
      this.renderPositions(data.positions || []);
      this.renderTradeBlotter(data.recent_trades || []);
    } catch (e) {
      console.error("Failed to load portfolio:", e);
    }
  }

  renderOverview(p) {
    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.innerText = val !== undefined ? val : "--";
    };

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
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:15px; color:var(--text-muted);">No open positions. Use the order pad or Trader Agent to execute paper trades.</td></tr>`;
      return;
    }

    tbody.innerHTML = positions.map(pos => {
      const isUp = pos.unrealized_pnl >= 0;
      const sign = isUp ? "+" : "";
      const col = isUp ? "color:var(--green-up);" : "color:var(--red-down);";

      return `
        <tr class="clickable-row" data-sym="${pos.symbol}" title="Click to view ${pos.symbol}">
          <td><strong style="color:var(--cyan-primary);">${pos.symbol}</strong></td>
          <td style="text-align:right; font-weight:700;">${pos.quantity}</td>
          <td style="text-align:right;">$${pos.avg_price.toFixed(2)}</td>
          <td style="text-align:right; font-weight:700;">$${pos.current_price.toFixed(2)}</td>
          <td style="text-align:right;">$${pos.cost_basis.toLocaleString()}</td>
          <td style="text-align:right; font-weight:700;">$${pos.current_value.toLocaleString()}</td>
          <td style="text-align:right; ${col} font-weight:800;">${sign}$${pos.unrealized_pnl.toFixed(2)} (${sign}${pos.unrealized_pct.toFixed(2)}%)</td>
          <td style="text-align:center;">
            <button class="f-key btn-port-term" data-sym="${pos.symbol}" style="font-size:9.5px; padding:1px 5px;">📈 TERMINAL</button>
          </td>
        </tr>
      `;
    }).join("");

    tbody.querySelectorAll("tr.clickable-row").forEach(r => {
      r.addEventListener("click", (e) => {
        if (e.target.closest(".btn-port-term")) return;
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
  }

  renderTradeBlotter(trades) {
    const tbody = document.getElementById("portfolio-blotter-tbody");
    if (!tbody) return;

    if (!trades || trades.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:10px; color:var(--text-muted);">No trades executed yet.</td></tr>`;
      return;
    }

    tbody.innerHTML = trades.slice().reverse().map(t => {
      const isBuy = t.type === "BUY";
      const col = isBuy ? "color:var(--green-up);" : "color:var(--amber-primary);";

      return `
        <tr>
          <td style="color:var(--text-muted); font-size:10px;">${t.timestamp}</td>
          <td><strong style="${col}">${t.type}</strong></td>
          <td><strong style="color:var(--cyan-primary);">${t.symbol}</strong></td>
          <td>${t.quantity}</td>
          <td>$${t.price.toFixed(2)}</td>
          <td style="font-weight:700;">$${t.total.toLocaleString()}</td>
        </tr>
      `;
    }).join("");
  }

  async handleQuickOrder(action) {
    const symInput = document.getElementById("order-symbol-input");
    const qtyInput = document.getElementById("order-qty-input");
    const symbol = (symInput ? symInput.value : window.terminalApp.activeSymbol || "NVDA").toUpperCase().trim();
    const quantity = parseInt(qtyInput ? qtyInput.value : "10");

    if (!symbol || quantity <= 0) {
      alert("Please specify a valid symbol and quantity > 0");
      return;
    }

    try {
      const res = await fetch("/api/portfolio/trade", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, symbol, quantity })
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
    if (confirm("Reset paper trading portfolio back to $100,000 cash?")) {
      try {
        await fetch("/api/portfolio/reset", { method: "POST" });
        await this.loadPortfolio();
        alert("Portfolio reset to $100,000 cash.");
      } catch (e) {
        alert(`Reset error: ${e.message}`);
      }
    }
  }
}

window.SP500PaperPortfolio = SP500PaperPortfolio;
