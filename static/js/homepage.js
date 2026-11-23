/**
 * Bloomberg Terminal V3.0 - S&P 500 Market Homepage Module
 * Controls Macro Benchmarks, Highest Gainers, Highest Losers, Active Movers & GICS Sectors
 */

class SP500Homepage {
  constructor() {
    this.benchmarks = [];
    this.movers = null;
    this.sectors = [];
  }

  async init() {
    await Promise.all([
      this.loadMacroBenchmarks(),
      this.loadMarketMovers(),
      this.loadSectors()
    ]);

    // Poll movers & benchmarks every 10 seconds
    setInterval(() => this.loadMarketMovers(), 10000);
    setInterval(() => this.loadMacroBenchmarks(), 3000);
  }

  async loadMacroBenchmarks() {
    try {
      const res = await fetch("/api/benchmarks");
      const list = await res.json();
      if (!Array.isArray(list)) return;

      list.forEach(b => {
        const sym = b.symbol;
        const priceStr = b.price.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        const sign = b.change >= 0 ? "+" : "";
        const chgStr = `${sign}${b.change.toFixed(2)} (${sign}${b.pct_change.toFixed(2)}%)`;
        const cls = b.change >= 0 ? "up" : "down";

        if (sym === "^GSPC") {
          const elP = document.getElementById("macro-sp500-price");
          const elC = document.getElementById("macro-sp500-chg");
          if (elP) elP.innerText = priceStr;
          if (elC) {
            elC.innerText = chgStr;
            elC.className = `quote-change-badge ${cls}`;
          }
        } else if (sym === "^IXIC") {
          const elP = document.getElementById("macro-nasdaq-price");
          const elC = document.getElementById("macro-nasdaq-chg");
          if (elP) elP.innerText = priceStr;
          if (elC) {
            elC.innerText = chgStr;
            elC.className = `quote-change-badge ${cls}`;
          }
        } else if (sym === "^DJI") {
          const elP = document.getElementById("macro-dow-price");
          const elC = document.getElementById("macro-dow-chg");
          if (elP) elP.innerText = priceStr;
          if (elC) {
            elC.innerText = chgStr;
            elC.className = `quote-change-badge ${cls}`;
          }
        } else if (sym === "^VIX") {
          const elP = document.getElementById("macro-vix-price");
          const elC = document.getElementById("macro-vix-chg");
          if (elP) elP.innerText = priceStr;
          if (elC) {
            elC.innerText = chgStr;
            elC.className = `quote-change-badge ${cls}`;
          }
        }
      });
    } catch (e) {
      console.warn("Failed to load homepage macro benchmarks:", e);
    }
  }

  async loadMarketMovers() {
    try {
      const res = await fetch("/api/market/movers");
      const data = await res.json();
      this.movers = data;

      this.renderMoversTable("home-gainers-tbody", data.gainers || [], "gain");
      this.renderMoversTable("home-losers-tbody", data.losers || [], "loss");
      this.renderMoversTable("home-actives-tbody", data.actives || [], "active");

      // Also sync to Stock Page mini-tables if open
      if (window.terminalDashboard && typeof window.terminalDashboard.syncMovers === "function") {
        window.terminalDashboard.syncMovers(data);
      }
    } catch (e) {
      console.warn("Failed to load market movers:", e);
    }
  }

  renderMoversTable(tbodyId, list, type) {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;

    if (!list || list.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:12px; color:var(--text-muted);">No records found</td></tr>`;
      return;
    }

    tbody.innerHTML = list.map((item, idx) => {
      const isUp = item.pct_change >= 0;
      const sign = isUp ? "+" : "";
      const colorCls = isUp ? "color:var(--green-up);" : "color:var(--red-down);";

      return `
        <tr class="clickable-row" data-sym="${item.symbol}">
          <td style="color:var(--text-muted); font-size:10px;">${idx + 1}</td>
          <td style="font-weight:800; color:var(--cyan-primary);">${item.symbol}</td>
          <td style="color:#cbd5e1; max-width:110px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${item.name || item.sector || ''}</td>
          <td style="text-align:right; font-weight:700;">$${item.price.toFixed(2)}</td>
          <td style="text-align:right; font-weight:800; ${colorCls}">${sign}${item.pct_change.toFixed(2)}%</td>
          <td style="text-align:center; white-space:nowrap;">
            <button class="f-key btn-action-term" data-sym="${item.symbol}" style="font-size:9.5px; padding:1px 5px;" title="Open Terminal">📈 TERM</button>
            <button class="f-key btn-action-stock" data-sym="${item.symbol}" style="font-size:9.5px; padding:1px 5px;" title="View Fundamentals">🏢 INFO</button>
          </td>
        </tr>
      `;
    }).join("");

    // Bind row clicks
    tbody.querySelectorAll("tr.clickable-row").forEach(row => {
      row.addEventListener("click", (e) => {
        // If an explicit action button was clicked, don't trigger general row click
        if (e.target.closest(".btn-action-term") || e.target.closest(".btn-action-stock")) return;
        const sym = row.dataset.sym;
        if (window.terminalApp) {
          window.terminalApp.selectStock(sym);
          window.terminalApp.switchView("dashboard");
        }
      });
    });

    // Bind specific Terminal button
    tbody.querySelectorAll(".btn-action-term").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const sym = btn.dataset.sym;
        if (window.terminalApp) {
          window.terminalApp.selectStock(sym);
          window.terminalApp.switchView("terminal");
        }
      });
    });

    // Bind specific Stock button
    tbody.querySelectorAll(".btn-action-stock").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const sym = btn.dataset.sym;
        if (window.terminalApp) {
          window.terminalApp.selectStock(sym);
          window.terminalApp.switchView("dashboard");
        }
      });
    });
  }

  async loadSectors() {
    const grid = document.getElementById("home-sectors-grid");
    if (!grid) return;

    try {
      const res = await fetch("/api/sp500/sectors");
      const sectors = await res.json();
      this.sectors = sectors;

      grid.innerHTML = sectors.map(s => {
        return `
          <div class="sector-tile" data-sector="${s.name}">
            <div class="sec-title">${s.name}</div>
            <div class="sec-meta">
              <span>${s.count} Equities</span>
              <span style="color:var(--cyan-primary);">${(s.weight_pct || 0).toFixed(1)}% Weight</span>
            </div>
          </div>
        `;
      }).join("");

      grid.querySelectorAll(".sector-tile").forEach(tile => {
        tile.addEventListener("click", () => {
          const sec = tile.dataset.sector;
          if (window.terminalScanner) {
            window.terminalApp.switchView("scanner");
          }
        });
      });
    } catch (e) {
      console.warn("Failed to load sectors on homepage:", e);
    }
  }
}
