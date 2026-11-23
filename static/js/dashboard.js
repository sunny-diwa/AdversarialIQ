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

      // 1. AdversarialIQ Catalyst Impact & Volatility Predictor (A-CIS)
      const scores = data.catalyst_scores || {};
      const movScore = Math.round(scores.movement_probability_score || 0);
      const movBadge = document.getElementById("eco-movement-badge");
      if (movBadge) {
        movBadge.innerText = scores.movement_label || "CALCULATED";
        movBadge.className = `quote-change-badge ${movScore >= 60 ? 'down' : (movScore >= 40 ? 'flat' : 'up')}`;
      }

      const movScoreEl = document.getElementById("eco-movement-score");
      if (movScoreEl) movScoreEl.innerText = `${movScore} / 100`;

      const movBar = document.getElementById("eco-movement-bar");
      if (movBar) {
        movBar.style.width = `${movScore}%`;
        movBar.style.background = movScore >= 70 ? 'var(--red-down)' : (movScore >= 45 ? 'var(--amber-primary)' : 'var(--cyan-primary)');
      }

      const movDesc = document.getElementById("eco-movement-desc");
      if (movDesc) movDesc.innerText = scores.movement_rationale || "Impulse potential across direct sentiment and cross-entity dependencies.";

      // Directional Up vs Down Prediction Scores
      const upScore = Math.round(scores.up_score || 0);
      const downScore = Math.round(scores.down_score || 0);
      const totalScore = Math.max(upScore + downScore, 1);
      const upPct = Math.round((upScore / totalScore) * 100);
      const downPct = 100 - upPct;

      const upEl = document.getElementById("eco-up-score");
      if (upEl) upEl.innerText = `${upScore}`;
      const downEl = document.getElementById("eco-down-score");
      if (downEl) downEl.innerText = `${downScore}`;

      const bullBar = document.getElementById("eco-bull-bar");
      if (bullBar) bullBar.style.width = `${upPct}%`;
      const bearBar = document.getElementById("eco-bear-bar");
      if (bearBar) bearBar.style.width = `${downPct}%`;

      const biasBadge = document.getElementById("eco-bias-badge");
      if (biasBadge) {
        biasBadge.innerText = scores.dominant_bias || "-- BIAS";
        if ((scores.dominant_bias || "").includes("BULLISH")) {
          biasBadge.style.color = "var(--green-up)";
          biasBadge.style.borderColor = "rgba(0, 255, 102, 0.3)";
          biasBadge.style.background = "rgba(0, 255, 102, 0.08)";
        } else if ((scores.dominant_bias || "").includes("BEARISH")) {
          biasBadge.style.color = "var(--red-down)";
          biasBadge.style.borderColor = "rgba(255, 51, 68, 0.3)";
          biasBadge.style.background = "rgba(255, 51, 68, 0.08)";
        } else {
          biasBadge.style.color = "var(--cyan-primary)";
          biasBadge.style.borderColor = "rgba(0, 229, 255, 0.3)";
          biasBadge.style.background = "rgba(0, 229, 255, 0.08)";
        }
      }

      // Technical Touch Scorecard
      const tech = scores.technical_scorecard || {};
      const techBias = document.getElementById("eco-tech-bias");
      if (techBias) {
        techBias.innerText = tech.composite_bias || "--";
        techBias.style.color = tech.composite_bias === "BULLISH" ? "var(--green-up)" : (tech.composite_bias === "BEARISH" ? "var(--red-down)" : "var(--cyan-primary)");
      }
      const setMetric = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.innerText = val !== undefined && val !== null ? val : "--";
      };
      setMetric("eco-tech-trend", `${tech.trend_score || '--'}/100`);
      setMetric("eco-tech-mom", `${tech.momentum_score || '--'}/100`);
      setMetric("eco-tech-vol", `${tech.volatility_score || '--'}/100`);
      setMetric("eco-tech-flow", `${tech.volume_pressure_score || '--'}/100`);

      // Active Catalysts Tags
      const catTags = document.getElementById("eco-catalysts-tags");
      if (catTags && Array.isArray(scores.key_catalysts)) {
        catTags.innerHTML = scores.key_catalysts.map(c => `
          <span style="font-size:7.5px; color:#cbd5e1; background:#111927; padding:1.5px 6px; border-radius:2px; border:1px solid #1f2b3e;">${c}</span>
        `).join("");
      }

      // Start-of-Day Pre-Market Projection Banner
      const sod = scores.start_of_day || {};
      setMetric("eco-sod-prob", `${Math.round(sod.movement_probability_score || movScore)}%`);
      setMetric("eco-sod-up", `${Math.round(sod.up_score || upScore)}`);
      setMetric("eco-sod-down", `${Math.round(sod.down_score || downScore)}`);
      setMetric("eco-sod-gap", `${(sod.open_gap_pct || 0) >= 0 ? '+' : ''}${Number(sod.open_gap_pct || 0).toFixed(2)}%`);
      const sodVerdict = document.getElementById("eco-sod-verdict");
      if (sodVerdict) {
        sodVerdict.innerText = sod.dominant_bias || "BALANCED";
        if ((sod.dominant_bias || "").includes("BULLISH")) {
          sodVerdict.style.color = "var(--green-up)";
          sodVerdict.style.borderColor = "rgba(0,255,102,0.25)";
          sodVerdict.style.background = "rgba(0,255,102,0.1)";
        } else if ((sod.dominant_bias || "").includes("BEARISH")) {
          sodVerdict.style.color = "var(--red-down)";
          sodVerdict.style.borderColor = "rgba(255,51,68,0.25)";
          sodVerdict.style.background = "rgba(255,51,68,0.1)";
        } else {
          sodVerdict.style.color = "var(--cyan-primary)";
          sodVerdict.style.borderColor = "rgba(0,229,255,0.25)";
          sodVerdict.style.background = "rgba(0,229,255,0.1)";
        }
      }

      // 2. Summary & Grounding Badge
      const descEl = document.getElementById("eco-summary-desc");
      if (descEl) descEl.innerText = data.ecosystem_summary || "Ecosystem structure and supply chain relationships.";

      const badgeEl = document.getElementById("eco-grounding-badge");
      if (badgeEl) badgeEl.innerText = data.grounding_source || "Google Grounded + SEC 10-K";

      // 3. Upstream Suppliers
      const suppEl = document.getElementById("eco-suppliers-list");
      if (suppEl && Array.isArray(data.upstream_suppliers)) {
        if (data.upstream_suppliers.length === 0) {
          suppEl.innerHTML = `<div style="font-size:9.5px; color:var(--text-muted); text-align:center; padding:10px;">No primary upstream bottlenecks identified.</div>`;
        } else {
          suppEl.innerHTML = data.upstream_suppliers.map(s => `
            <div style="background:#090e18; border:1px solid #1a2538; padding:6px 8px; border-radius:2px; display:flex; flex-direction:column; gap:4px;">
              <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:6px;">
                <div style="flex:1;">
                  <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                    <button class="f-key btn-eco-ticker" data-sym="${s.symbol}" style="font-size:9.5px; font-weight:800; padding:1px 5px; color:var(--cyan-primary);">${s.symbol}</button>
                    <strong style="color:#f1f5f9; font-size:10px;">${s.name}</strong>
                    <span class="quote-change-badge ${s.status === 'UP' ? 'up' : (s.status === 'DOWN' ? 'down' : 'flat')}" style="font-size:8px; padding:1px 5px; font-weight:800;">
                      $${Number(s.price || 100).toFixed(2)} (${s.pct_change >= 0 ? '+' : ''}${Number(s.pct_change || 0).toFixed(2)}%)
                    </span>
                  </div>
                  <div style="color:var(--text-muted); font-size:9px; margin-top:2px;">${s.role}</div>
                  <div style="color:#94a3b8; font-size:8.5px; margin-top:2px; line-height:1.2;">${s.description || ''}</div>
                </div>
                <div style="text-align:right; font-size:8.5px; white-space:nowrap;">
                  <span class="quote-change-badge ${s.criticality === 'EXTREME' || s.criticality === 'CRITICAL' ? 'down' : 'up'}" style="font-size:8px; padding:1px 4px;">${s.criticality}</span>
                  <div style="color:var(--text-muted); font-size:8px; margin-top:2px;">${s.tier}</div>
                </div>
              </div>
              <div style="font-size:8px; color:#cbd5e1; display:flex; gap:4px; align-items:center; background:#0c121d; padding:2px 5px; border-radius:2px; border:1px solid #1a2538;">
                <span style="font-size:7.5px; font-weight:bold; color:${s.news_sentiment === 'POSITIVE' ? 'var(--green-up)' : (s.news_sentiment === 'NEGATIVE' ? 'var(--red-down)' : 'var(--cyan-primary)')};">[${s.news_sentiment || 'NEWS'}]</span>
                <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1;" title="${s.latest_news || ''}">${s.latest_news || 'Operational telemetry baseline.'}</span>
              </div>
            </div>
          `).join("");
        }
      }

      // 4. Downstream Customers
      const custEl = document.getElementById("eco-customers-list");
      if (custEl && Array.isArray(data.downstream_customers)) {
        if (data.downstream_customers.length === 0) {
          custEl.innerHTML = `<div style="font-size:9.5px; color:var(--text-muted); text-align:center; padding:10px;">Diversified commercial end customers.</div>`;
        } else {
          custEl.innerHTML = data.downstream_customers.map(c => `
            <div style="background:#090e18; border:1px solid #1a2538; padding:6px 8px; border-radius:2px; display:flex; flex-direction:column; gap:4px;">
              <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:6px;">
                <div style="flex:1;">
                  <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                    <button class="f-key btn-eco-ticker" data-sym="${c.symbol}" style="font-size:9.5px; font-weight:800; padding:1px 5px; color:var(--green-up);">${c.symbol}</button>
                    <strong style="color:#f1f5f9; font-size:10px;">${c.name}</strong>
                    <span class="quote-change-badge ${c.status === 'UP' ? 'up' : (c.status === 'DOWN' ? 'down' : 'flat')}" style="font-size:8px; padding:1px 5px; font-weight:800;">
                      $${Number(c.price || 100).toFixed(2)} (${c.pct_change >= 0 ? '+' : ''}${Number(c.pct_change || 0).toFixed(2)}%)
                    </span>
                  </div>
                  <div style="color:var(--text-muted); font-size:9px; margin-top:2px;">${c.role}</div>
                  <div style="color:#94a3b8; font-size:8.5px; margin-top:2px; line-height:1.2;">${c.use_case || ''}</div>
                </div>
                <div style="text-align:right; font-size:8.5px; white-space:nowrap;">
                  ${c.revenue_share_pct ? `<span style="color:var(--cyan-primary); font-weight:bold;">~${c.revenue_share_pct}% Rev</span>` : ''}
                  <div style="color:var(--text-muted); font-size:8px; margin-top:2px;">${c.tier}</div>
                </div>
              </div>
              <div style="font-size:8px; color:#cbd5e1; display:flex; gap:4px; align-items:center; background:#0c121d; padding:2px 5px; border-radius:2px; border:1px solid #1a2538;">
                <span style="font-size:7.5px; font-weight:bold; color:${c.news_sentiment === 'POSITIVE' ? 'var(--green-up)' : (c.news_sentiment === 'NEGATIVE' ? 'var(--red-down)' : 'var(--cyan-primary)')};">[${c.news_sentiment || 'NEWS'}]</span>
                <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1;" title="${c.latest_news || ''}">${c.latest_news || 'Demand pipeline tracking.'}</span>
              </div>
            </div>
          `).join("");
        }
      }

      // 5. Competitors
      const compEl = document.getElementById("eco-competitors-list");
      if (compEl && Array.isArray(data.competitors)) {
        if (data.competitors.length === 0) {
          compEl.innerHTML = `<div style="font-size:9.5px; color:var(--text-muted); text-align:center; padding:10px;">No direct peer competitors identified.</div>`;
        } else {
          compEl.innerHTML = data.competitors.map(cp => `
            <div style="background:#090e18; border:1px solid #1a2538; padding:6px 8px; border-radius:2px; display:flex; flex-direction:column; gap:4px;">
              <div style="display:flex; justify-content:space-between; align-items:flex-start; gap:6px;">
                <div style="flex:1;">
                  <div style="display:flex; align-items:center; gap:6px; flex-wrap:wrap;">
                    <button class="f-key btn-eco-ticker" data-sym="${cp.symbol}" style="font-size:9.5px; font-weight:800; padding:1px 5px; color:var(--amber-primary);">${cp.symbol}</button>
                    <strong style="color:#f1f5f9; font-size:10px;">${cp.name}</strong>
                    <span class="quote-change-badge ${cp.status === 'UP' ? 'up' : (cp.status === 'DOWN' ? 'down' : 'flat')}" style="font-size:8px; padding:1px 5px; font-weight:800;">
                      $${Number(cp.price || 100).toFixed(2)} (${cp.pct_change >= 0 ? '+' : ''}${Number(cp.pct_change || 0).toFixed(2)}%)
                    </span>
                  </div>
                  <div style="color:#94a3b8; font-size:8.5px; margin-top:2px; line-height:1.2;">${cp.competitive_advantage || cp.key_products || ''}</div>
                </div>
                <div style="text-align:right; font-size:8.5px; white-space:nowrap;">
                  <span class="quote-change-badge ${cp.moat_rating === 'WIDE' ? 'up' : 'flat'}" style="font-size:8px; padding:1px 4px;">Moat: ${cp.moat_rating}</span>
                  <div style="color:var(--text-muted); font-size:8px; margin-top:2px;">Threat: ${cp.threat_level}</div>
                </div>
              </div>
              <div style="font-size:8px; color:#cbd5e1; display:flex; gap:4px; align-items:center; background:#0c121d; padding:2px 5px; border-radius:2px; border:1px solid #1a2538;">
                <span style="font-size:7.5px; font-weight:bold; color:${cp.news_sentiment === 'POSITIVE' ? 'var(--green-up)' : (cp.news_sentiment === 'NEGATIVE' ? 'var(--red-down)' : 'var(--cyan-primary)')};">[${cp.news_sentiment || 'NEWS'}]</span>
                <span style="white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:1;" title="${cp.latest_news || ''}">${cp.latest_news || 'Competitive positioning monitoring.'}</span>
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
      if (riskEl) {
        riskEl.innerText = data.risk_factors_summary || (Array.isArray(data.risk_factors) ? data.risk_factors.join(" • ") : "Market risk, competition, operational, and macroeconomic risk factors.");
      }

      const listEl = document.getElementById("sec-filings-list");
      if (listEl && Array.isArray(data.filings)) {
        listEl.innerHTML = data.filings.slice(0, 8).map(f => `
          <div style="background:#111927; border:1px solid #1f2b3e; padding:3px 6px; border-radius:2px; font-size:9.5px;">
            <strong style="color:var(--amber-primary);">${f.form}</strong>
            <span style="color:var(--text-muted); margin-left:4px;">${f.filing_date}</span>
            <span style="color:#94a3b8; margin-left:4px;">${(f.description || '').slice(0, 35)}</span>
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
        } else if (data.cluster_verdict && (data.cluster_verdict.includes("SELLING") || data.cluster_verdict.includes("BEARISH"))) {
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
      const transactions = data.form4_transactions || data.transactions || [];
      if (tradesTbody && Array.isArray(transactions)) {
        if (transactions.length === 0) {
          tradesTbody.innerHTML = `<tr><td colspan="5" style="text-align:center; padding:8px; color:var(--text-muted);">No Form 4 filings recorded in period.</td></tr>`;
        } else {
          tradesTbody.innerHTML = transactions.slice(0, 6).map(t => {
            const txType = t.transaction_type || (t.type && t.type.includes("BUY") ? "BUY" : "SELL");
            const isBuy = txType === "BUY";
            const col = isBuy ? "color:var(--green-up);" : "color:var(--red-down);";
            const name = t.insider_name || t.insider || "Officer";
            const title = t.officer_title || t.position || "Executive";
            const shs = t.shares || 0;
            const valK = t.value ? (t.value / 1000).toFixed(1) : ((shs * 150) / 1000).toFixed(1);
            return `
              <tr>
                <td style="color:#cbd5e1; font-weight:bold;">${name}</td>
                <td style="color:var(--text-muted);">${title}</td>
                <td style="${col} font-weight:bold;">${txType}</td>
                <td style="text-align:right;">${shs.toLocaleString()}</td>
                <td style="text-align:right;">$${valK}K</td>
              </tr>
            `;
          }).join("");
        }
      }

      // 13F Table
      const f13Tbody = document.getElementById("insider-13f-tbody");
      const holders = data.institutional_holders || [];
      if (f13Tbody && Array.isArray(holders)) {
        if (holders.length === 0) {
          f13Tbody.innerHTML = `<tr><td colspan="3" style="text-align:center; padding:8px; color:var(--text-muted);">No 13F holdings indexed.</td></tr>`;
        } else {
          f13Tbody.innerHTML = holders.slice(0, 6).map(h => {
            const pct = h.shares_pct ?? h.pct_out ?? 0;
            const valB = h.value_billions ?? (h.value ? (h.value / 1e9).toFixed(1) : '--');
            return `
              <tr>
                <td style="color:#cbd5e1;">${h.holder}</td>
                <td style="text-align:right; color:var(--cyan-primary); font-weight:bold;">${typeof pct === 'number' ? pct.toFixed(2) : pct}%</td>
                <td style="text-align:right; color:var(--amber-primary);">$${valB}B</td>
              </tr>
            `;
          }).join("");
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
        const bCount = s.bullish_count ?? 0;
        const brCount = s.bearish_count ?? 0;
        const nCount = s.neutral_count ?? 0;
        countsEl.innerText = `(${bCount} Bullish, ${brCount} Bearish, ${nCount} Neutral)`;
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
            const headline = a.headline || a.title || "Market Catalyst Update";
            const catalyst = a.catalyst || (a.catalysts && a.catalysts[0]) || "GENERAL";
            const sentCol = a.sentiment === 'BULLISH' ? 'var(--green-up)' : (a.sentiment === 'BEARISH' ? 'var(--red-down)' : 'var(--text-muted)');
            return `
              <div style="background:#090e18; border:1px solid #1a2538; padding:6px 8px; border-radius:2px; display:flex; justify-content:space-between; align-items:center; gap:8px;">
                <div style="flex:1;">
                  <a href="${a.url || '#'}" target="_blank" style="color:#f1f5f9; text-decoration:none; font-size:10.5px; font-weight:bold; line-height:1.3; display:block;">
                    ${headline} ↗
                  </a>
                  <div style="font-size:9.5px; color:var(--text-muted); margin-top:2px;">
                    <span>${a.source || 'Financial Wire'}</span>
                    <span style="margin:0 4px;">•</span>
                    <span style="color:var(--cyan-primary);">${catalyst}</span>
                  </div>
                </div>
                <div style="font-size:10px; font-weight:bold; color:${sentCol}; padding:2px 6px; background:#111927; border-radius:2px; white-space:nowrap;">
                  ${a.sentiment || 'NEUTRAL'}
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
    const isUp = change >= 0;

    const priceEl = document.getElementById("stockpage-price");
    if (priceEl) {
      priceEl.innerText = `$${price.toFixed(2)}`;
      priceEl.classList.remove("flash-up", "flash-down");
      void priceEl.offsetWidth; // trigger reflow
      priceEl.classList.add(isUp ? "flash-up" : "flash-down");
    }

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

    let mcapStr = "--";
    if (q.market_cap) {
      if (q.market_cap >= 1e12) {
        mcapStr = `$${(q.market_cap / 1e12).toFixed(2)}T ($${(q.market_cap / 1e9).toFixed(0)}B)`;
      } else {
        mcapStr = `$${(q.market_cap / 1e9).toFixed(1)}B`;
      }
    }
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
