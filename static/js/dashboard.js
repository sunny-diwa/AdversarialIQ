/**
 * Bloomberg Terminal V3.0 - S&P 500 Company-Wise Dashboard
 * Deep-dive Company Profile, Valuation Multiples, Margins & Sector Peer Matrix
 * Plus Side-by-Side Highest Gainers & Losers on the SAME Page!
 */

class SP500CompanyDashboard {
  constructor() {
    this.currentSymbol = "NVDA";
    this.cachedQuote = null;
    this.setupListeners();
  }

  setupListeners() {
    const btnTerm = document.getElementById("btn-hero-open-terminal");
    if (btnTerm) {
      btnTerm.addEventListener("click", () => {
        if (window.terminalApp) {
          window.terminalApp.selectStock(this.currentSymbol);
          window.terminalApp.switchView("terminal");
        }
      });
    }

    const btnAi = document.getElementById("btn-hero-ask-ai");
    if (btnAi) {
      btnAi.addEventListener("click", () => {
        if (window.terminalApp) {
          window.terminalApp.selectStock(this.currentSymbol);
          window.terminalApp.switchView("agent");
          const input = document.getElementById("chat-user-input");
          if (input) {
            input.value = `Analyze technical setup and valuation for ${this.currentSymbol}`;
            input.focus();
          }
        }
      });
    }

    const btnTrade = document.getElementById("btn-stockpage-trade");
    if (btnTrade) {
      btnTrade.addEventListener("click", () => {
        if (window.terminalApp) {
          window.terminalApp.selectStock(this.currentSymbol);
          window.terminalApp.switchView("terminal");
        }
      });
    }
  }

  async loadCompany(symbol = "NVDA") {
    this.currentSymbol = symbol;

    try {
      // 1. Fetch Live Quote
      const qRes = await fetch(`/api/stock/${encodeURIComponent(symbol)}/quote`);
      const quote = await qRes.json();
      this.cachedQuote = quote;
      this.renderQuoteHighlight(quote);

      // 2. Fetch Company Deep-Dive Data
      const res = await fetch(`/api/stock/${encodeURIComponent(symbol)}/company`);
      const comp = await res.json();
      this.renderProfile(comp);
      this.renderFinancials(comp);
      this.renderPeers(comp.peers || []);

      // 3. Render Quant Action Plan
      this.renderQuantPlan(quote);

      // 4. Fetch market movers for side-by-side display
      const mRes = await fetch("/api/market/movers");
      const movers = await mRes.json();
      this.syncMovers(movers);

    } catch (e) {
      console.error("Failed to load company dashboard:", e);
    }
  }

  renderQuoteHighlight(q) {
    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.innerText = val !== undefined ? val : "--";
    };

    // Hero Banner Elements
    setT("stockpage-symbol", q.symbol);
    setT("stockpage-name", q.name);
    setT("stockpage-sector", q.sector);
    setT("stockpage-industry", q.sub_industry || "S&P 500");
    setT("stockpage-price", `$${q.price.toFixed(2)}`);

    const isUp = q.change >= 0;
    const sign = isUp ? "+" : "";
    const chgStr = `${sign}${q.change.toFixed(2)} (${sign}${q.pct_change.toFixed(2)}%)`;
    const cls = isUp ? "up" : "down";

    const heroChg = document.getElementById("stockpage-chg");
    if (heroChg) {
      heroChg.innerText = chgStr;
      heroChg.className = `quote-change-badge ${cls}`;
    }

    // Sidebar Quote Card Elements (Chatbot view)
    setT("dash-quote-sym", `${q.symbol} // ${q.name}`);
    setT("dash-quote-price", `$${q.price.toFixed(2)}`);
    const chgEl = document.getElementById("dash-quote-change");
    if (chgEl) {
      chgEl.className = `quote-change-badge ${cls}`;
      chgEl.innerText = chgStr;
    }

    const mcapStr = q.market_cap ? `$${(q.market_cap / 1e9).toFixed(1)}B` : "--";
    const peStr = q.pe_ratio ? `${q.pe_ratio}x` : "--";

    setT("dash-val-mcap", mcapStr);
    setT("val-mcap-stock", mcapStr);
    setT("dash-val-pe", peStr);
    setT("val-pe-stock", peStr);
    setT("dash-val-range", `$${q.day_low} - $${q.day_high}`);
    setT("dash-val-52w", `$${q.year_low} - $${q.year_high}`);
  }

  renderProfile(comp) {
    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.innerText = val !== undefined ? val : "--";
    };

    setT("dash-profile-name", `${comp.name} (${comp.symbol})`);
    setT("dash-profile-ceo", comp.ceo || "Leadership");
    setT("dash-profile-city", comp.city || "United States");

    const descEl = document.getElementById("dash-profile-desc");
    if (descEl) {
      descEl.innerText = comp.summary || "S&P 500 Constituent company.";
    }

    const webEl = document.getElementById("dash-profile-web");
    if (webEl && comp.website) {
      webEl.href = comp.website;
      webEl.innerText = comp.website.replace("https://", "").replace("http://", "").replace(/\/$/, "");
    }
  }

  renderFinancials(comp) {
    const val = comp.valuation || {};
    const prof = comp.profitability || {};
    const bal = comp.financial_health || {};

    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.innerText = val !== undefined ? val : "--";
    };

    // Valuation Multiples
    setT("val-ev", val.enterprise_value_b ? `$${val.enterprise_value_b}B` : "--");
    setT("val-fpe", val.forward_pe ? `${val.forward_pe}x` : "--");
    setT("val-peg", val.peg_ratio ? `${val.peg_ratio}` : "--");
    setT("val-pb", val.price_to_book ? `${val.price_to_book}x` : "--");
    setT("val-ps", val.price_to_sales ? `${val.price_to_sales}x` : "--");
    setT("val-evebitda", val.ev_to_ebitda ? `${val.ev_to_ebitda}x` : "--");

    // Margins & Profitability
    setT("prof-gross", prof.gross_margin ? `${prof.gross_margin}%` : "--");
    setT("prof-oper", prof.operating_margin ? `${prof.operating_margin}%` : "--");
    setT("prof-net", prof.profit_margin ? `${prof.profit_margin}%` : "--");
    setT("prof-roe", prof.roe ? `${prof.roe}%` : "--");

    // Balance Sheet & Liquidity
    setT("bal-cash", bal.total_cash_b ? `$${bal.total_cash_b}B` : "--");
    setT("bal-debt", bal.total_debt_b ? `$${bal.total_debt_b}B` : "--");
    setT("bal-de", bal.debt_to_equity ? `${bal.debt_to_equity}` : "--");
    setT("bal-fcf", bal.free_cash_flow_b ? `$${bal.free_cash_flow_b}B` : "--");
  }

  renderPeers(peers) {
    const container = document.getElementById("dash-peers-table-body");
    if (!container) return;

    if (!peers || peers.length === 0) {
      container.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:10px;">No sector peers indexed.</td></tr>`;
      return;
    }

    container.innerHTML = peers.map(p => {
      const isUp = p.change >= 0;
      const sign = isUp ? "+" : "";
      const col = isUp ? "color:var(--green-up);" : "color:var(--red-down);";

      return `
        <tr class="clickable-row" data-sym="${p.symbol}" title="Select ${p.symbol}">
          <td><strong style="color:var(--cyan-primary);">${p.symbol}</strong></td>
          <td style="color:#cbd5e1;">${p.name}</td>
          <td style="text-align:right; font-weight:700;">$${p.price.toFixed(2)}</td>
          <td style="text-align:right; ${col}">${sign}${p.pct_change.toFixed(2)}%</td>
          <td style="text-align:right; color:var(--amber-primary);">$${p.market_cap}B</td>
          <td style="text-align:center;">
            <button class="f-key peer-select-btn" data-sym="${p.symbol}" style="font-size:9.5px; padding:1px 6px;">SELECT</button>
          </td>
        </tr>
      `;
    }).join("");

    container.querySelectorAll(".clickable-row, .peer-select-btn").forEach(el => {
      el.addEventListener("click", () => {
        const sym = el.dataset.sym;
        if (window.terminalApp) window.terminalApp.selectStock(sym);
      });
    });
  }

  renderQuantPlan(q) {
    const price = q.price || 100.0;
    const low = q.day_low || price * 0.98;
    const high = q.day_high || price * 1.02;

    const entry = price;
    const stop = Math.max(low * 0.985, price * 0.95);
    const target = Math.min(high * 1.035, price * 1.08);

    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.innerText = val;
    };

    setT("plan-entry", `$${entry.toFixed(2)}`);
    setT("plan-stop", `$${stop.toFixed(2)}`);
    setT("plan-target", `$${target.toFixed(2)}`);
  }

  syncMovers(data) {
    if (!data) return;

    // 1. Stock Page Gainers mini-table
    const gainersTbody = document.getElementById("stockpage-gainers-tbody");
    if (gainersTbody && data.gainers) {
      gainersTbody.innerHTML = data.gainers.slice(0, 7).map(g => `
        <tr class="clickable-row" data-sym="${g.symbol}" title="Switch to ${g.symbol}" style="cursor:pointer;">
          <td style="color:var(--cyan-primary); font-weight:800;">${g.symbol}</td>
          <td style="text-align:right;">$${g.price.toFixed(2)}</td>
          <td style="text-align:right; color:var(--green-up); font-weight:bold;">+${g.pct_change.toFixed(2)}%</td>
        </tr>
      `).join("");

      gainersTbody.querySelectorAll("tr").forEach(r => {
        r.addEventListener("click", () => {
          if (window.terminalApp) window.terminalApp.selectStock(r.dataset.sym);
        });
      });
    }

    // 2. Stock Page Losers mini-table
    const losersTbody = document.getElementById("stockpage-losers-tbody");
    if (losersTbody && data.losers) {
      losersTbody.innerHTML = data.losers.slice(0, 7).map(l => `
        <tr class="clickable-row" data-sym="${l.symbol}" title="Switch to ${l.symbol}" style="cursor:pointer;">
          <td style="color:var(--cyan-primary); font-weight:800;">${l.symbol}</td>
          <td style="text-align:right;">$${l.price.toFixed(2)}</td>
          <td style="text-align:right; color:var(--red-down); font-weight:bold;">${l.pct_change.toFixed(2)}%</td>
        </tr>
      `).join("");

      losersTbody.querySelectorAll("tr").forEach(r => {
        r.addEventListener("click", () => {
          if (window.terminalApp) window.terminalApp.selectStock(r.dataset.sym);
        });
      });
    }
  }
}

window.SP500CompanyDashboard = SP500CompanyDashboard;
