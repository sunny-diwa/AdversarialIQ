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

    // Dock Tabs Switcher (Ecosystem, Peers, SEC, Insider, News, Macro)
    document.querySelectorAll(".stock-dock-tab").forEach(tab => {
      tab.addEventListener("click", () => {
        const target = tab.dataset.tab;
        document.querySelectorAll(".stock-dock-tab").forEach(t => t.classList.toggle("active", t === tab));
        const panes = ["ecosystem", "peers", "sec", "insider", "news", "macro"];
        panes.forEach(p => {
          const el = document.getElementById(`pane-dock-${p}`);
          if (el) el.style.display = (p === target) ? "block" : "none";
        });
      });
    });
  }

  async loadCompany(symbol = "NVDA") {
    const sym = (symbol || "NVDA").toUpperCase().trim();
    this.currentSymbol = sym;

    // Immediately update hero labels
    const symEl = document.getElementById("stockpage-symbol");
    if (symEl) symEl.innerText = sym;

    try {
      // 1. Fetch Live Quote with error safety
      try {
        const qRes = await fetch(`/api/stock/${encodeURIComponent(sym)}/quote`);
        if (qRes.ok) {
          const quote = await qRes.json();
          this.cachedQuote = quote;
          this.renderQuoteHighlight(quote);
          this.renderQuantPlan(quote);
        }
      } catch (err) {
        console.warn("Quote fetch error:", err);
      }

      // 2. Fetch Company Deep-Dive Data
      try {
        const res = await fetch(`/api/stock/${encodeURIComponent(sym)}/company`);
        if (res.ok) {
          const comp = await res.json();
          this.renderProfile(comp);
          this.renderFinancials(comp);
          this.renderPeers(comp.peers || []);
        }
      } catch (err) {
        console.warn("Company details error:", err);
      }

      // 3. Fetch Supply Chain & Ecosystem Intelligence
      this.loadEcosystem(sym);

      // 4. Fetch Multi-Layer Data in Parallel (SEC, Insider 13F, News, Macro)
      this.loadSecFilings(sym);
      this.loadInsiderActivity(sym);
      this.loadNews(sym);
      this.loadMacroRegime();

      // 5. Fetch market movers for side-by-side display
      try {
        const mRes = await fetch("/api/market/movers");
        if (mRes.ok) {
          const movers = await mRes.json();
          this.syncMovers(movers);
        }
      } catch (err) {
        console.warn("Market movers error:", err);
      }

    } catch (e) {
      console.error("Failed to load company dashboard:", e);
    }
  }

  async loadEcosystem(symbol) {
    try {
      const res = await fetch(`/api/stock/${encodeURIComponent(symbol)}/ecosystem`);
      if (!res.ok) return;
      const data = await res.json();

      // 1. Summary & Grounding Badge
      const descEl = document.getElementById("eco-summary-desc");
      if (descEl) descEl.innerText = data.ecosystem_summary || "Ecosystem structure and supply chain relationships.";

      const badgeEl = document.getElementById("eco-grounding-badge");
      if (badgeEl) badgeEl.innerText = data.grounding_source || "Google Grounded + SEC 10-K";

      // 2. Upstream Suppliers
      const suppEl = document.getElementById("eco-suppliers-list");
      if (suppEl && Array.isArray(data.upstream_suppliers)) {
        if (data.upstream_suppliers.length === 0) {
          suppEl.innerHTML = `<div style="font-size:9.5px; color:var(--text-muted); text-align:center; padding:10px;">No primary upstream bottlenecks identified.</div>`;
        } else {
          suppEl.innerHTML = data.upstream_suppliers.map(s => `
            <div style="background:#090e18; border:1px solid #1a2538; padding:5px 7px; border-radius:2px; display:flex; justify-content:space-between; align-items:flex-start; gap:6px;">
              <div style="flex:1;">
                <div style="display:flex; align-items:center; gap:6px;">
                  <button class="f-key btn-eco-ticker" data-sym="${s.symbol}" style="font-size:9.5px; font-weight:800; padding:1px 5px; color:var(--cyan-primary);">${s.symbol}</button>
                  <strong style="color:#f1f5f9; font-size:10px;">${s.name}</strong>
                </div>
                <div style="color:var(--text-muted); font-size:9px; margin-top:2px;">${s.role}</div>
                <div style="color:#94a3b8; font-size:8.5px; margin-top:2px; line-height:1.2;">${s.description || ''}</div>
              </div>
              <div style="text-align:right; font-size:8.5px; white-space:nowrap;">
                <span class="quote-change-badge ${s.criticality === 'EXTREME' || s.criticality === 'CRITICAL' ? 'down' : 'up'}" style="font-size:8px; padding:1px 4px;">${s.criticality}</span>
                <div style="color:var(--text-muted); font-size:8px; margin-top:2px;">${s.tier}</div>
              </div>
            </div>
          `).join("");
        }
      }

      // 3. Downstream Customers
      const custEl = document.getElementById("eco-customers-list");
      if (custEl && Array.isArray(data.downstream_customers)) {
        if (data.downstream_customers.length === 0) {
          custEl.innerHTML = `<div style="font-size:9.5px; color:var(--text-muted); text-align:center; padding:10px;">Diversified commercial end customers.</div>`;
        } else {
          custEl.innerHTML = data.downstream_customers.map(c => `
            <div style="background:#090e18; border:1px solid #1a2538; padding:5px 7px; border-radius:2px; display:flex; justify-content:space-between; align-items:flex-start; gap:6px;">
              <div style="flex:1;">
                <div style="display:flex; align-items:center; gap:6px;">
                  <button class="f-key btn-eco-ticker" data-sym="${c.symbol}" style="font-size:9.5px; font-weight:800; padding:1px 5px; color:var(--green-up);">${c.symbol}</button>
                  <strong style="color:#f1f5f9; font-size:10px;">${c.name}</strong>
                </div>
                <div style="color:var(--text-muted); font-size:9px; margin-top:2px;">${c.role}</div>
                <div style="color:#94a3b8; font-size:8.5px; margin-top:2px; line-height:1.2;">${c.use_case || ''}</div>
              </div>
              <div style="text-align:right; font-size:8.5px; white-space:nowrap;">
                ${c.revenue_share_pct ? `<span style="color:var(--cyan-primary); font-weight:bold;">~${c.revenue_share_pct}% Rev</span>` : ''}
                <div style="color:var(--text-muted); font-size:8px; margin-top:2px;">${c.tier}</div>
              </div>
            </div>
          `).join("");
        }
      }

      // 4. Competitors
      const compEl = document.getElementById("eco-competitors-list");
      if (compEl && Array.isArray(data.competitors)) {
        if (data.competitors.length === 0) {
          compEl.innerHTML = `<div style="font-size:9.5px; color:var(--text-muted); text-align:center; padding:10px;">No direct peer competitors identified.</div>`;
        } else {
          compEl.innerHTML = data.competitors.map(cp => `
            <div style="background:#090e18; border:1px solid #1a2538; padding:5px 7px; border-radius:2px; display:flex; justify-content:space-between; align-items:flex-start; gap:6px;">
              <div style="flex:1;">
                <div style="display:flex; align-items:center; gap:6px;">
                  <button class="f-key btn-eco-ticker" data-sym="${cp.symbol}" style="font-size:9.5px; font-weight:800; padding:1px 5px; color:var(--amber-primary);">${cp.symbol}</button>
                  <strong style="color:#f1f5f9; font-size:10px;">${cp.name}</strong>
                </div>
                <div style="color:#94a3b8; font-size:8.5px; margin-top:2px; line-height:1.2;">${cp.competitive_advantage || cp.key_products || ''}</div>
              </div>
              <div style="text-align:right; font-size:8.5px; white-space:nowrap;">
                <span class="quote-change-badge ${cp.moat_rating === 'WIDE' ? 'up' : 'flat'}" style="font-size:8px; padding:1px 4px;">Moat: ${cp.moat_rating}</span>
                <div style="color:var(--text-muted); font-size:8px; margin-top:2px;">Threat: ${cp.threat_level}</div>
              </div>
            </div>
          `).join("");
        }
      }

      // Bind all dynamic ticker buttons in ecosystem cards
      document.querySelectorAll(".btn-eco-ticker").forEach(btn => {
        btn.addEventListener("click", (e) => {
          e.stopPropagation();
          const targetSym = btn.dataset.sym;
          if (targetSym && window.terminalApp) {
            window.terminalApp.selectStock(targetSym, "dashboard");
          }
        });
      });

      // 5. Consumer Breakdown Panel
      const cb = data.consumer_breakdown || {};
      const b2b = cb.b2b_vs_b2c || {};
      const conc = cb.customer_concentration || {};
      const price = cb.pricing_power || {};
      const sw = cb.switching_costs || {};

      const b2bPct = typeof b2b.b2b_pct === 'number' ? b2b.b2b_pct : 50;
      const b2cPct = typeof b2b.b2c_pct === 'number' ? b2b.b2c_pct : 50;

      const b2bTxt = document.getElementById("eco-b2b-pct-txt");
      if (b2bTxt) b2bTxt.innerText = `B2B Enterprise: ${b2bPct}%`;
      const b2cTxt = document.getElementById("eco-b2c-pct-txt");
      if (b2cTxt) b2cTxt.innerText = `B2C Consumer: ${b2cPct}%`;

      const b2bBar = document.getElementById("eco-b2b-bar");
      if (b2bBar) b2bBar.style.width = `${b2bPct}%`;
      const b2cBar = document.getElementById("eco-b2c-bar");
      if (b2cBar) b2cBar.style.width = `${b2cPct}%`;

      const concEl = document.getElementById("eco-concentration-val");
      if (concEl) concEl.innerText = `${conc.top_5_customers_pct || '--'}% (Risk: ${conc.risk_level || 'BALANCED'})`;

      const priceEl = document.getElementById("eco-pricing-val");
      if (priceEl) priceEl.innerText = `${price.score_out_of_10 || 8.0}/10 (${price.level || 'HIGH'})`;

      const swEl = document.getElementById("eco-switching-val");
      if (swEl) swEl.innerText = `${sw.moat_driver || 'Product Integration'} — ${sw.notes || 'High customer retention'}`;

      const chipsEl = document.getElementById("eco-endmarkets-chips");
      if (chipsEl && Array.isArray(cb.end_markets)) {
        chipsEl.innerHTML = cb.end_markets.map(m => `
          <span style="font-size:8.5px; padding:2px 5px; background:#111927; border:1px solid #1f2b3e; border-radius:2px; color:var(--cyan-primary);">
            ${m.segment}: <strong>${m.share_pct}%</strong>
          </span>
        `).join("");
      }

    } catch (err) {
      console.warn("Failed to load company ecosystem:", err);
    }
  }

  async loadSecFilings(symbol) {
    try {
      const res = await fetch(`/api/stock/${encodeURIComponent(symbol)}/sec`);
      const data = await res.json();

      const titleEl = document.getElementById("sec-company-title");
      if (titleEl) titleEl.innerText = `${data.company_name || symbol} (CIK: ${data.cik || 'Indexed'})`;

      const cikBadge = document.getElementById("sec-cik-badge");
      if (cikBadge) cikBadge.innerText = `Total Indexed Submissions: ${data.total_filings_indexed || '--'}`;

      const mdaEl = document.getElementById("sec-mda-content");
      if (mdaEl) mdaEl.innerText = data.mda_summary || "Standard Item 7 operational and strategic performance disclosures.";

      const riskEl = document.getElementById("sec-risk-content");
      if (riskEl) riskEl.innerText = data.risk_factors_summary || "Market risk, competition, operational, and macroeconomic risk factors.";

      const listEl = document.getElementById("sec-filings-list");
      if (listEl && Array.isArray(data.filings)) {
        listEl.innerHTML = data.filings.slice(0, 8).map(f => `
          <div style="background:#111927; border:1px solid #1f2b3e; padding:3px 6px; border-radius:2px; font-size:9.5px;">
            <strong style="color:var(--amber-primary);">${f.form}</strong>
            <span style="color:var(--text-muted); margin-left:4px;">${f.filing_date}</span>
            <span style="color:#94a3b8; margin-left:4px;">${(f.description || '').slice(0, 25)}</span>
          </div>
        `).join("");
      }
    } catch (err) {
      console.warn("Failed to load SEC filings:", err);
    }
  }

  async loadInsiderActivity(symbol) {
    try {
      const res = await fetch(`/api/stock/${encodeURIComponent(symbol)}/insider`);
      const data = await res.json();

      const verdEl = document.getElementById("insider-verdict-badge");
      if (verdEl) {
        verdEl.innerText = data.cluster_verdict || "BALANCED / INACTIVE";
        if (data.cluster_verdict && data.cluster_verdict.includes("BUYING")) {
          verdEl.style.color = "var(--green-up)";
        } else if (data.cluster_verdict && data.cluster_verdict.includes("SELLING")) {
          verdEl.style.color = "var(--red-down)";
        } else {
          verdEl.style.color = "var(--text-muted)";
        }
      }

      const countsEl = document.getElementById("insider-counts-badge");
      if (countsEl) {
        countsEl.innerText = `${data.recent_buys_count || 0} Buys vs ${data.recent_sells_count || 0} Sells (90-Day Executive Cluster)`;
      }

      // Form 4 Table
      const tradesTbody = document.getElementById("insider-trades-tbody");
      if (tradesTbody && Array.isArray(data.form4_transactions)) {
        if (data.form4_transactions.length === 0) {
          tradesTbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:8px; color:var(--text-muted);">No Form 4 filings recorded in period.</td></tr>`;
        } else {
          tradesTbody.innerHTML = data.form4_transactions.slice(0, 6).map(t => {
            const isBuy = t.transaction_type === "BUY";
            const col = isBuy ? "color:var(--green-up);" : "color:var(--red-down);";
            return `
              <tr>
                <td style="color:#cbd5e1; font-weight:bold;">${t.insider_name}</td>
                <td style="color:var(--text-muted);">${t.officer_title || 'Officer'}</td>
                <td style="${col} font-weight:bold;">${t.transaction_type}</td>
                <td style="text-align:right;">${(t.shares || 0).toLocaleString()}</td>
                <td style="text-align:right;">$${((t.value || 0) / 1000).toFixed(1)}K</td>
              </tr>
            `;
          }).join("");
        }
      }

      // 13F Table
      const f13Tbody = document.getElementById("insider-13f-tbody");
      if (f13Tbody && Array.isArray(data.institutional_holders)) {
        if (data.institutional_holders.length === 0) {
          f13Tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; padding:8px; color:var(--text-muted);">No 13F holdings indexed.</td></tr>`;
        } else {
          f13Tbody.innerHTML = data.institutional_holders.slice(0, 5).map(h => `
            <tr>
              <td style="color:#cbd5e1;">${h.holder}</td>
              <td style="text-align:right; color:var(--cyan-primary); font-weight:bold;">${h.shares_pct}%</td>
              <td style="text-align:right; color:var(--amber-primary);">$${h.value_billions}B</td>
            </tr>
          `).join("");
        }
      }
    } catch (err) {
      console.warn("Failed to load insider activity:", err);
    }
  }

  async loadNews(symbol) {
    try {
      const res = await fetch(`/api/stock/${encodeURIComponent(symbol)}/news`);
      const data = await res.json();

      const badge = document.getElementById("news-sentiment-badge");
      if (badge && data.overall_sentiment) {
        const s = data.overall_sentiment;
        badge.innerText = `${s.label} (${s.score > 0 ? '+' : ''}${s.score.toFixed(2)})`;
        badge.className = `quote-change-badge ${s.label === 'BULLISH' ? 'up' : (s.label === 'BEARISH' ? 'down' : 'flat')}`;
      }

      const countsEl = document.getElementById("news-counts-breakdown");
      if (countsEl && data.overall_sentiment) {
        const s = data.overall_sentiment;
        countsEl.innerText = `(${s.bullish_count} Bullish, ${s.bearish_count} Bearish, ${s.neutral_count} Neutral)`;
      }

      // Catalyst tags
      const catContainer = document.getElementById("news-catalysts-container");
      if (catContainer && Array.isArray(data.top_catalysts)) {
        catContainer.innerHTML = data.top_catalysts.map(c => `
          <span style="font-size:9px; padding:1px 5px; background:#1e293b; color:var(--cyan-primary); border:1px solid #334155; border-radius:2px;">
            ${c}
          </span>
        `).join("");
      }

      // Articles
      const feed = document.getElementById("news-articles-feed");
      if (feed && Array.isArray(data.articles)) {
        if (data.articles.length === 0) {
          feed.innerHTML = `<div style="text-align:center; padding:10px; color:var(--text-muted);">No breaking news headlines.</div>`;
        } else {
          feed.innerHTML = data.articles.slice(0, 8).map(a => {
            const sentCol = a.sentiment === 'BULLISH' ? 'var(--green-up)' : (a.sentiment === 'BEARISH' ? 'var(--red-down)' : 'var(--text-muted)');
            return `
              <div style="background:#090e18; border:1px solid #1a2538; padding:6px 8px; border-radius:2px; display:flex; justify-content:space-between; align-items:center; gap:8px;">
                <div style="flex:1;">
                  <a href="${a.url}" target="_blank" style="color:#f1f5f9; text-decoration:none; font-size:10.5px; font-weight:bold; line-height:1.3; display:block;">
                    ${a.headline} ↗
                  </a>
                  <div style="font-size:9.5px; color:var(--text-muted); margin-top:2px;">
                    <span>${a.source}</span>
                    <span style="margin:0 4px;">•</span>
                    <span style="color:var(--cyan-primary);">${a.catalyst || 'GENERAL'}</span>
                  </div>
                </div>
                <div style="font-size:10px; font-weight:bold; color:${sentCol}; padding:2px 6px; background:#111927; border-radius:2px; white-space:nowrap;">
                  ${a.sentiment}
                </div>
              </div>
            `;
          }).join("");
        }
      }
    } catch (err) {
      console.warn("Failed to load news:", err);
    }
  }

  async loadMacroRegime() {
    try {
      const res = await fetch("/api/macro/regime");
      const data = await res.json();

      const regEl = document.getElementById("macro-regime-title");
      if (regEl) regEl.innerText = `${data.regime || 'NEUTRAL'} (${data.bias || 'BALANCED'})`;

      const ind = data.indicators || {};
      const setT = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.innerText = val;
      };

      setT("macro-dock-10y", `${(ind.ten_year_yield || 4.4).toFixed(2)}%`);
      setT("macro-dock-2y", `${(ind.two_year_or_short_rate || 4.2).toFixed(2)}%`);
      setT("macro-dock-spread", `${(ind.yield_spread_bps || 0) > 0 ? '+' : ''}${(ind.yield_spread_bps || 0).toFixed(1)} bps`);
      setT("macro-dock-vix", `${(ind.vix || 16.5).toFixed(2)}`);

      const synEl = document.getElementById("macro-dock-synopsis");
      if (synEl) synEl.innerText = data.summary || "Treasury yield curve and economic indicators operating in standard regime.";
    } catch (err) {
      console.warn("Failed to load macro regime:", err);
    }
  }

  renderQuoteHighlight(q) {
    if (!q) return;
    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.innerText = val !== undefined && val !== null ? val : "--";
    };

    const sym = q.symbol || this.currentSymbol || "EQUITY";
    setT("stockpage-symbol", sym);
    setT("stockpage-name", q.name || sym);
    setT("stockpage-sector", q.sector || "Information Technology");
    setT("stockpage-industry", q.sub_industry || "S&P 500");

    const price = (typeof q.price === "number") ? q.price : 100.0;
    const change = (typeof q.change === "number") ? q.change : 0.0;
    const pct = (typeof q.pct_change === "number") ? q.pct_change : 0.0;

    setT("stockpage-price", `$${price.toFixed(2)}`);

    const isUp = change >= 0;
    const sign = isUp ? "+" : "";
    const chgStr = `${sign}${change.toFixed(2)} (${sign}${pct.toFixed(2)}%)`;
    const cls = isUp ? "up" : "down";

    const heroChg = document.getElementById("stockpage-chg");
    if (heroChg) {
      heroChg.innerText = chgStr;
      heroChg.className = `quote-change-badge ${cls}`;
    }

    // Sidebar Quote Card Elements (Chatbot view)
    setT("dash-quote-sym", `${sym} // ${q.name || sym}`);
    setT("dash-quote-price", `$${price.toFixed(2)}`);
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
    setT("dash-val-range", `$${q.day_low ?? (price * 0.98).toFixed(2)} - $${q.day_high ?? (price * 1.02).toFixed(2)}`);
    setT("dash-val-52w", `$${q.year_low ?? (price * 0.8).toFixed(2)} - $${q.year_high ?? (price * 1.25).toFixed(2)}`);
  }

  renderProfile(comp) {
    if (!comp) return;
    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.innerText = val !== undefined ? val : "--";
    };

    setT("dash-profile-name", `${comp.name || this.currentSymbol} (${comp.symbol || this.currentSymbol})`);
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
    if (!comp) return;
    const val = comp.valuation || {};
    const prof = comp.profitability || comp.financials || {};
    const bal = comp.financial_health || comp.financials || {};

    const setT = (id, val) => {
      const el = document.getElementById(id);
      if (el) el.innerText = val !== undefined && val !== null ? val : "--";
    };

    // Valuation Multiples
    const evVal = val.enterprise_value_b ?? (val.enterprise_value ? (val.enterprise_value / 1e9).toFixed(1) : undefined);
    setT("val-ev", evVal !== undefined ? `$${evVal}B` : "--");
    setT("val-fpe", val.forward_pe ? `${val.forward_pe}x` : "--");
    setT("val-peg", val.peg_ratio ? `${val.peg_ratio}` : "--");
    setT("val-pb", val.price_to_book ? `${val.price_to_book}x` : "--");
    setT("val-ps", val.price_to_sales ? `${val.price_to_sales}x` : "--");
    setT("val-evebitda", val.ev_to_ebitda ? `${val.ev_to_ebitda}x` : "--");

    // Margins & Profitability
    const gm = prof.gross_margin ?? prof.gross_margins;
    const om = prof.operating_margin ?? prof.operating_margins;
    const pm = prof.profit_margin ?? prof.profit_margins;
    setT("prof-gross", gm !== undefined ? `${gm}%` : "--");
    setT("prof-oper", om !== undefined ? `${om}%` : "--");
    setT("prof-net", pm !== undefined ? `${pm}%` : "--");
    setT("prof-roe", prof.roe !== undefined ? `${prof.roe}%` : "--");

    // Balance Sheet & Liquidity
    const cashVal = bal.total_cash_b ?? (bal.total_cash ? (bal.total_cash / 1e9).toFixed(1) : undefined);
    const debtVal = bal.total_debt_b ?? (bal.total_debt ? (bal.total_debt / 1e9).toFixed(1) : undefined);
    const fcfVal = bal.free_cash_flow_b ?? (bal.free_cashflow ? (bal.free_cashflow / 1e9).toFixed(1) : undefined);

    setT("bal-cash", cashVal !== undefined ? `$${cashVal}B` : "--");
    setT("bal-debt", debtVal !== undefined ? `$${debtVal}B` : "--");
    setT("bal-de", bal.debt_to_equity !== undefined ? `${bal.debt_to_equity}` : "--");
    setT("bal-fcf", fcfVal !== undefined ? `$${fcfVal}B` : "--");
  }

  renderPeers(peers) {
    const container = document.getElementById("dash-peers-table-body");
    if (!container) return;

    if (!peers || peers.length === 0) {
      container.innerHTML = `<tr><td colspan="6" style="text-align:center; color:var(--text-muted); padding:10px;">No sector peers indexed.</td></tr>`;
      return;
    }

    container.innerHTML = peers.map(p => {
      const pObj = (typeof p === "string") ? { symbol: p, name: p, price: 100.0, pct_change: 0.0, market_cap: 50.0 } : p;
      const sym = pObj.symbol || "EQUITY";
      const name = pObj.name || sym;
      const isUp = (pObj.pct_change || pObj.change || 0) >= 0;
      const sign = isUp ? "+" : "";
      const col = isUp ? "color:var(--green-up);" : "color:var(--red-down);";
      const price = typeof pObj.price === 'number' ? pObj.price : 100.0;
      const pct = typeof pObj.pct_change === 'number' ? pObj.pct_change : 0.0;
      const mcap = pObj.market_cap ? (typeof pObj.market_cap === 'number' && pObj.market_cap > 1e6 ? (pObj.market_cap / 1e9).toFixed(1) : pObj.market_cap) : '--';

      return `
        <tr class="clickable-row" data-sym="${sym}" title="Select ${sym}">
          <td><strong style="color:var(--cyan-primary);">${sym}</strong></td>
          <td style="color:#cbd5e1;">${name}</td>
          <td style="text-align:right; font-weight:700;">$${price.toFixed(2)}</td>
          <td style="text-align:right; ${col}">${sign}${pct.toFixed(2)}%</td>
          <td style="text-align:right; color:var(--amber-primary);">$${mcap}B</td>
          <td style="text-align:center;">
            <button class="f-key peer-select-btn" data-sym="${sym}" style="font-size:9.5px; padding:1px 6px;">SELECT</button>
          </td>
        </tr>
      `;
    }).join("");

    container.querySelectorAll(".clickable-row, .peer-select-btn").forEach(el => {
      el.addEventListener("click", () => {
        const sym = el.dataset.sym;
        if (sym && window.terminalApp) window.terminalApp.selectStock(sym, "dashboard");
      });
    });
  }

  renderQuantPlan(q) {
    const price = (typeof q?.price === 'number') ? q.price : 100.0;
    const low = (typeof q?.day_low === 'number') ? q.day_low : price * 0.98;
    const high = (typeof q?.day_high === 'number') ? q.day_high : price * 1.02;

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
      gainersTbody.innerHTML = data.gainers.slice(0, 7).map(g => {
        const price = typeof g.price === 'number' ? g.price : 100.0;
        const pct = typeof g.pct_change === 'number' ? g.pct_change : 0.0;
        return `
          <tr class="clickable-row" data-sym="${g.symbol}" title="Switch to ${g.symbol}" style="cursor:pointer;">
            <td style="color:var(--cyan-primary); font-weight:800;">${g.symbol}</td>
            <td style="text-align:right;">$${price.toFixed(2)}</td>
            <td style="text-align:right; color:var(--green-up); font-weight:bold;">+${pct.toFixed(2)}%</td>
          </tr>
        `;
      }).join("");

      gainersTbody.querySelectorAll("tr").forEach(r => {
        r.addEventListener("click", () => {
          if (r.dataset.sym && window.terminalApp) window.terminalApp.selectStock(r.dataset.sym, "dashboard");
        });
      });
    }

    // 2. Stock Page Losers mini-table
    const losersTbody = document.getElementById("stockpage-losers-tbody");
    if (losersTbody && data.losers) {
      losersTbody.innerHTML = data.losers.slice(0, 7).map(l => {
        const price = typeof l.price === 'number' ? l.price : 100.0;
        const pct = typeof l.pct_change === 'number' ? l.pct_change : 0.0;
        return `
          <tr class="clickable-row" data-sym="${l.symbol}" title="Switch to ${l.symbol}" style="cursor:pointer;">
            <td style="color:var(--cyan-primary); font-weight:800;">${l.symbol}</td>
            <td style="text-align:right;">$${price.toFixed(2)}</td>
            <td style="text-align:right; color:var(--red-down); font-weight:bold;">${pct.toFixed(2)}%</td>
          </tr>
        `;
      }).join("");

      losersTbody.querySelectorAll("tr").forEach(r => {
        r.addEventListener("click", () => {
          if (r.dataset.sym && window.terminalApp) window.terminalApp.selectStock(r.dataset.sym, "dashboard");
        });
      });
    }
  }
}

window.SP500CompanyDashboard = SP500CompanyDashboard;
