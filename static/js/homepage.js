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
      const price = typeof item.price === 'number' ? item.price : 100.0;
      const pct = typeof item.pct_change === 'number' ? item.pct_change : 0.0;
      const isUp = pct >= 0;
      const sign = isUp ? "+" : "";
      const colorCls = isUp ? "color:var(--green-up);" : "color:var(--red-down);";

      return `
        <tr class="clickable-row" data-sym="${item.symbol}">
          <td style="color:var(--text-muted); font-size:10px;">${idx + 1}</td>
          <td style="font-weight:800; color:var(--cyan-primary);">${item.symbol}</td>
          <td style="color:#cbd5e1; max-width:110px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${item.name || item.sector || ''}</td>
          <td style="text-align:right; font-weight:700;">$${price.toFixed(2)}</td>
          <td style="text-align:right; font-weight:800; ${colorCls}">${sign}${pct.toFixed(2)}%</td>
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
        if (sym && window.terminalApp) {
          window.terminalApp.selectStock(sym, "dashboard");
        }
      });
    });

    // Bind specific Terminal button
    tbody.querySelectorAll(".btn-action-term").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const sym = btn.dataset.sym;
        if (sym && window.terminalApp) {
          window.terminalApp.selectStock(sym, "terminal");
        }
      });
    });

    // Bind specific Stock button
    tbody.querySelectorAll(".btn-action-stock").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const sym = btn.dataset.sym;
        if (sym && window.terminalApp) {
          window.terminalApp.selectStock(sym, "dashboard");
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
        const secName = s.name || s.sector || "Sector";
        const count = s.count || 0;
        const weight = typeof s.weight_pct === 'number' ? s.weight_pct.toFixed(1) : (s.weight || '0.0');
        const perf = typeof s.day_change === 'number' ? s.day_change : (typeof s.perf_pct === 'number' ? s.perf_pct : 0.0);
        const isUp = perf >= 0;
        const sign = isUp ? "+" : "";
        const col = isUp ? "var(--green-up)" : "var(--red-down)";
        const sampleChips = (s.sample_stocks || []).slice(0, 4).map(sym => `
          <button class="f-key sec-sym-pill" data-sym="${sym}" title="Inspect ${sym}" style="font-size:8.5px; padding:1px 5px; border:1px solid #1a2538; background:#0d1522; color:var(--cyan-primary); border-radius:2px;">${sym}</button>
        `).join("");

        return `
          <div class="sector-tile" data-sector="${secName}" style="padding:7px; border:1px solid #1c283f; background:#090e18; border-radius:3px;">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
              <div class="sec-title" title="${secName}" style="font-size:10.5px; font-weight:bold; color:#f1f5f9; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; max-width:140px;">${secName}</div>
              <span style="font-size:9.5px; font-weight:800; color:${col}; background:rgba(0,0,0,0.5); padding:1px 5px; border-radius:2px; white-space:nowrap;">
                ${sign}${perf.toFixed(2)}%
              </span>
            </div>
            <div class="sec-meta" style="font-size:9px; color:var(--text-muted); display:flex; justify-content:space-between; margin-bottom:6px;">
              <span>${count} Equities</span>
              <span style="color:var(--cyan-primary); font-weight:600;">${weight}% Weight</span>
            </div>
            <div style="display:flex; gap:3px; align-items:center; flex-wrap:wrap;">
              ${sampleChips}
            </div>
          </div>
        `;
      }).join("");

      // Bind stock pills inside sector tiles
      grid.querySelectorAll(".sec-sym-pill").forEach(btn => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          const sym = btn.dataset.sym;
          if (sym && window.terminalApp) {
            window.terminalApp.selectStock(sym, "dashboard");
          }
        });
      });

      // Bind sector tile click to scanner filter
      grid.querySelectorAll(".sector-tile").forEach(tile => {
        tile.addEventListener("click", () => {
          const sec = tile.dataset.sector;
          if (window.terminalScanner) {
            const secSelect = document.getElementById("scanner-sector");
            if (secSelect) {
              secSelect.value = sec;
              window.terminalScanner.runScan();
            }
          }
          if (window.terminalApp) {
            window.terminalApp.switchView("scanner");
          }
        });
      });
    } catch (e) {
      console.warn("Failed to load sectors on homepage:", e);
    }
  }
}
