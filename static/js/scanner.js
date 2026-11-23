/**
 * Bloomberg Terminal V3.0 - S&P 500 Live Multi-Indicator Scanner
 * Real-Time Scanning across 500 Equities for RSI, MACD, Moving Averages & Breakouts
 */

class SP500LiveScanner {
  constructor() {
    this.currentStrategy = "all";
    this.tableBody = document.getElementById("scanner-table-body");
    this.sectorsContainer = document.getElementById("scanner-sectors-list");
  }

  async init() {
    this.setupFilters();
    await this.loadSectors();
    await this.runScan(this.currentStrategy);
  }

  setupFilters() {
    document.querySelectorAll(".scanner-strat-btn").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        document.querySelectorAll(".scanner-strat-btn").forEach(b => b.classList.remove("active"));
        e.target.classList.add("active");
        this.currentStrategy = e.target.dataset.strategy;
        await this.runScan(this.currentStrategy);
      });
    });

    const refreshBtn = document.getElementById("btn-refresh-scanner");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => this.runScan(this.currentStrategy));
    }
  }

  async loadSectors() {
    if (!this.sectorsContainer) return;
    try {
      const res = await fetch("/api/sp500/sectors");
      const sectors = await res.json();

      this.sectorsContainer.innerHTML = sectors.map(sec => `
        <div style="background:#0f1626; border:1px solid #1a2538; padding:6px 10px; border-radius:2px; display:flex; justify-content:space-between; align-items:center; font-size:11px;">
          <div>
            <div style="font-weight:700; color:#fff;">${sec.sector}</div>
            <div style="font-size:9px; color:var(--text-muted);">${sec.sample_stocks.join(", ")}</div>
          </div>
          <div style="color:var(--cyan-primary); font-weight:800; font-size:12px;">${sec.count}</div>
        </div>
      `).join("");
    } catch (e) {
      console.warn("Failed to load sectors:", e);
    }
  }

  async runScan(strategy = "all") {
    if (!this.tableBody) return;
    this.tableBody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:20px; color:var(--amber-primary);"><span class="pulse-dot" style="display:inline-block; margin-right:6px;"></span> SCANNING S&amp;P 500 CONSTITUENTS...</td></tr>`;

    try {
      const res = await fetch(`/api/scanner/run?strategy=${strategy}`);
      const data = await res.json();
      const results = data.results || [];

      const timeEl = document.getElementById("scanner-timestamp");
      if (timeEl && data.timestamp) timeEl.innerText = `LAST SCAN: ${data.timestamp}`;

      if (results.length === 0) {
        this.tableBody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:20px; color:var(--text-muted);">No stocks currently meeting threshold for ${strategy}.</td></tr>`;
        return;
      }

      this.tableBody.innerHTML = results.map(s => {
        const isUp = s.pct_change >= 0;
        const sign = isUp ? "+" : "";
        const col = isUp ? "color:var(--green-up);" : "color:var(--red-down);";
        const rsiColor = s.rsi <= 35 ? "color:var(--green-up); font-weight:bold;" : (s.rsi >= 65 ? "color:var(--red-down); font-weight:bold;" : "color:#94a3b8;");
        const macdColor = s.macd > s.macd_signal ? "color:var(--green-up);" : "color:var(--red-down);";

        const signalBadges = s.signals.map(sig => {
          let badgeStyle = "background:#1e293b; color:#cbd5e1;";
          if (sig.includes("OVERSOLD") || sig.includes("BULL")) badgeStyle = "background:rgba(0,255,102,0.15); color:var(--green-up);";
          if (sig.includes("OVERBOUGHT") || sig.includes("DOWN")) badgeStyle = "background:rgba(255,51,68,0.15); color:var(--red-down);";
          return `<span style="font-size:9px; padding:1px 4px; border-radius:2px; font-weight:700; ${badgeStyle}">${sig.replace(/_/g, " ")}</span>`;
        }).join(" ");

        return `
          <tr class="clickable-row" data-sym="${s.symbol}" title="Inspect ${s.symbol}">
            <td><strong style="color:var(--cyan-primary);">${s.symbol}</strong></td>
            <td style="color:#f8fafc;">${s.name}</td>
            <td style="color:var(--text-muted); font-size:10px;">${s.sector}</td>
            <td style="text-align:right; font-weight:700;">$${s.price.toFixed(2)}</td>
            <td style="text-align:right; ${col}">${sign}${s.pct_change.toFixed(2)}%</td>
            <td style="text-align:right; ${rsiColor}">${s.rsi}</td>
            <td style="text-align:right; ${macdColor}">${s.macd.toFixed(2)}</td>
            <td>${signalBadges}</td>
            <td style="text-align:center; white-space:nowrap;">
              <button class="f-key btn-scan-term" data-sym="${s.symbol}" style="font-size:9.5px; padding:1px 5px;">📈 TERM</button>
              <button class="f-key btn-scan-stock" data-sym="${s.symbol}" style="font-size:9.5px; padding:1px 5px;">🏢 INFO</button>
            </td>
          </tr>
        `;
      }).join("");

      this.tableBody.querySelectorAll("tr.clickable-row").forEach(r => {
        r.addEventListener("click", (e) => {
          if (e.target.closest(".btn-scan-term") || e.target.closest(".btn-scan-stock")) return;
          if (window.terminalApp) {
            window.terminalApp.selectStock(r.dataset.sym);
            window.terminalApp.switchView("dashboard");
          }
        });
      });

      this.tableBody.querySelectorAll(".btn-scan-term").forEach(b => {
        b.addEventListener("click", (e) => {
          e.stopPropagation();
          if (window.terminalApp) {
            window.terminalApp.selectStock(b.dataset.sym);
            window.terminalApp.switchView("terminal");
          }
        });
      });

      this.tableBody.querySelectorAll(".btn-scan-stock").forEach(b => {
        b.addEventListener("click", (e) => {
          e.stopPropagation();
          if (window.terminalApp) {
            window.terminalApp.selectStock(b.dataset.sym);
            window.terminalApp.switchView("dashboard");
          }
        });
      });

    } catch (e) {
      this.tableBody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:20px; color:var(--red-down);">Scan failed: ${e.message}</td></tr>`;
    }
  }
}

window.SP500LiveScanner = SP500LiveScanner;
