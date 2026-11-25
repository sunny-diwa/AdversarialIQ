/**
 * Bloomberg Terminal V3.0 - Main Desktop Orchestrator
 * Central State, Global Search, Hot Tickers, Benchmark Ticker Engine & Multi-View Router
 */

class BloombergApp {
  constructor() {
    this.activeSymbol = "NVDA";
    this.currentView = "homepage";
    this.sp500List = [];
    this.previousBenchmarkPrices = new Map();

    // Module instances
    this.homepage = null;
    this.agent = null;
    this.dashboard = null;
    this.chart = null;
    this.scanner = null;
    this.portfolio = null;
  }

  async init() {
    this.initClocks();
    this.initNavigation();
    this.initSettingsModal();
    this.initObservabilityModal();
    this.initHotTickers();
    this.initHeaderQuickButtons();

    // 1. Load S&P 500 Master List
    await this.loadSP500List();

    // 2. Instantiate Sub-modules
    this.homepage = new SP500Homepage();
    await this.homepage.init();
    window.terminalHomepage = this.homepage;

    this.agent = new SP500TraderAgent();
    this.agent.init(this.activeSymbol);
    window.terminalAgent = this.agent;

    this.dashboard = new SP500CompanyDashboard();
    window.terminalDashboard = this.dashboard;

    this.chart = new SP500PriceChart("main-candlestick-canvas", "rsi-canvas", "macd-canvas");
    await this.chart.init(this.activeSymbol);
    window.terminalChart = this.chart;

    this.scanner = new SP500LiveScanner();
    await this.scanner.init();
    window.terminalScanner = this.scanner;

    this.portfolio = new SP500PaperPortfolio();
    await this.portfolio.init();
    window.terminalPortfolio = this.portfolio;

    // 3. Load initial active stock data
    await this.selectStock(this.activeSymbol);

    // 4. Start 1-second benchmark tick stream
    this.startTickEngine();
  }

  async loadSP500List() {
    try {
      const res = await fetch("/api/sp500/list");
      this.sp500List = await res.json();
      this.setupGlobalSearch();
    } catch (e) {
      console.warn("Failed to load S&P 500 catalog:", e);
    }
  }

  setupGlobalSearch() {
    const input = document.getElementById("header-stock-search");
    const dropdown = document.getElementById("header-stock-dropdown");
    if (!input || !dropdown) return;

    input.value = "";

    const renderDropdown = (query) => {
      const q = query.trim().toUpperCase();
      let matches = this.sp500List;
      if (q) {
        matches = this.sp500List.filter(s =>
          s.symbol.toUpperCase().includes(q) ||
          s.name.toUpperCase().includes(q) ||
          (s.sector && s.sector.toUpperCase().includes(q))
        );
      }
      matches = matches.slice(0, 16);

      if (matches.length === 0) {
        dropdown.innerHTML = `<div style="padding:10px; color:var(--text-muted); font-size:10px;">No matching S&P 500 equities</div>`;
      } else {
        dropdown.innerHTML = matches.map(m => `
          <div class="dropdown-item" data-sym="${m.symbol}">
            <span class="sym">${m.symbol}</span>
            <span class="name">${m.name}</span>
            <span style="font-size:9.5px; color:var(--text-muted);">${m.sector || ''}</span>
          </div>
        `).join("");

        dropdown.querySelectorAll(".dropdown-item").forEach(item => {
          item.addEventListener("click", () => {
            const sym = item.dataset.sym;
            this.selectStock(sym, "dashboard");
            dropdown.style.display = "none";
            input.value = "";
          });
        });
      }
      dropdown.style.display = "block";
    };

    input.addEventListener("focus", () => renderDropdown(input.value));
    input.addEventListener("input", (e) => renderDropdown(e.target.value));

    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        const val = input.value.trim().toUpperCase();
        if (val) {
          this.selectStock(val, "dashboard");
          dropdown.style.display = "none";
          input.value = "";
        }
      }
    });

    document.addEventListener("click", (e) => {
      if (!input.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.style.display = "none";
      }
    });
  }

  initHotTickers() {
    document.querySelectorAll(".ticker-chip").forEach(chip => {
      chip.addEventListener("click", () => {
        const sym = chip.dataset.sym;
        if (sym) this.selectStock(sym, "dashboard");
      });
    });
  }

  initHeaderQuickButtons() {
    const btnTerm = document.getElementById("btn-quick-terminal");
    if (btnTerm) {
      btnTerm.addEventListener("click", () => {
        this.switchView("terminal");
      });
    }

    const btnChat = document.getElementById("btn-quick-chat");
    if (btnChat) {
      btnChat.addEventListener("click", () => {
        this.switchView("agent");
        const input = document.getElementById("chat-user-input");
        if (input) {
          input.value = `Analyze technical setup and valuation for ${this.activeSymbol}`;
          input.focus();
        }
      });
    }
  }

  async selectStock(symbol, switchViewName = null) {
    if (!symbol) return;
    const sym = symbol.toUpperCase().trim();
    this.activeSymbol = sym;

    // 1. Immediately update all DOM elements showing the active stock across all views synchronously
    const setElemText = (id, text) => {
      const el = document.getElementById(id);
      if (el) el.innerText = text;
    };

    setElemText("global-active-ticker", sym);
    setElemText("stockpage-symbol", sym);
    setElemText("chart-active-symbol", `${sym} // TRADING TERMINAL`);
    setElemText("term-order-sym", sym);
    setElemText("nav-btn-sym", sym);
    setElemText("nav-chat-sym", sym);
    setElemText("dash-quote-sym", `${sym} // LOADING QUOTE...`);

    const orderInput = document.getElementById("order-symbol-input");
    if (orderInput) orderInput.value = sym;

    // Optional immediate view switch
    if (switchViewName) {
      this.switchView(switchViewName);
    }

    // 2. Fetch quick quote to update top active bar safely
    try {
      const qRes = await fetch(`/api/stock/${encodeURIComponent(sym)}/quote`);
      if (qRes.ok) {
        const q = await qRes.json();
        const price = (typeof q?.price === "number") ? q.price : 100.0;
        const change = (typeof q?.change === "number") ? q.change : 0.0;
        const pct = (typeof q?.pct_change === "number") ? q.pct_change : 0.0;

        const pEl = document.getElementById("global-active-price");
        const cEl = document.getElementById("global-active-chg");
        if (pEl) pEl.innerText = `$${price.toFixed(2)}`;
        if (cEl) {
          const isUp = change >= 0;
          const sign = isUp ? "+" : "";
          cEl.innerText = `${sign}${change.toFixed(2)} (${sign}${pct.toFixed(2)}%)`;
          cEl.className = `quote-change-badge ${isUp ? 'up' : 'down'}`;
        }
      }
    } catch (e) {
      console.warn("Failed to fetch quote for header active badge:", e);
    }

    // 3. Refresh sub-views with try/catch isolation so failure in one never blocks others
    if (this.agent && typeof this.agent.setSymbol === "function") {
      try {
        this.agent.setSymbol(sym);
      } catch (err) {
        console.warn("Agent setSymbol error:", err);
      }
    }

    if (this.dashboard && typeof this.dashboard.loadCompany === "function") {
      try {
        await this.dashboard.loadCompany(sym);
      } catch (err) {
        console.warn("Dashboard loadCompany error:", err);
      }
    }

    if (this.chart && typeof this.chart.loadChartData === "function") {
      try {
        await this.chart.loadChartData(sym, this.chart.currentPeriod);
      } catch (err) {
        console.warn("Chart loadChartData error:", err);
      }
    }
  }

  initClocks() {
    const updateTime = () => {
      const now = new Date();
      const formatTime = (timeZone) => {
        return new Intl.DateTimeFormat("en-GB", {
          timeZone,
          hour: "2-digit",
          minute: "2-digit",
          second: "2-digit",
          hour12: false
        }).format(now);
      };

      const nyc = document.getElementById("clock-newyork");
      const ldn = document.getElementById("clock-london");
      const tyo = document.getElementById("clock-tokyo");

      if (nyc) nyc.innerText = formatTime("America/New_York");
      if (ldn) ldn.innerText = formatTime("Europe/London");
      if (tyo) tyo.innerText = formatTime("Asia/Tokyo");
    };

    updateTime();
    setInterval(updateTime, 1000);
  }

  initNavigation() {
    // Mode Switcher Tabs
    document.querySelectorAll(".nav-tab[data-view]").forEach(btn => {
      btn.addEventListener("click", () => {
        const view = btn.dataset.view;
        this.switchView(view);
      });
    });

    // Global Keyboard Shortcuts (F1-F6)
    window.addEventListener("keydown", (e) => {
      if (e.key === "F1") { e.preventDefault(); this.switchView("homepage"); }
      if (e.key === "F2") { e.preventDefault(); this.switchView("agent"); }
      if (e.key === "F3") { e.preventDefault(); this.switchView("dashboard"); }
      if (e.key === "F4") { e.preventDefault(); this.switchView("terminal"); }
      if (e.key === "F5") { e.preventDefault(); this.switchView("portfolio"); }
      if (e.key === "F6") { e.preventDefault(); this.switchView("scanner"); }
      if (e.key === "F7") { e.preventDefault(); this.switchView("backtest"); }
    });
  }

  switchView(viewName) {
    this.currentView = viewName;

    document.querySelectorAll(".nav-tab[data-view]").forEach(b => {
      b.classList.toggle("active", b.dataset.view === viewName);
    });

    const panes = ["homepage", "agent", "dashboard", "terminal", "portfolio", "scanner", "backtest"];
    panes.forEach(pId => {
      const el = document.getElementById(`view-${pId}`);
      if (el) {
        el.style.display = (pId === viewName) ? "flex" : "none";
      }
    });

    // Resize chart if switching to terminal view
    if (viewName === "terminal" && this.chart && this.chart.cachedData) {
      setTimeout(() => this.chart.render(this.chart.cachedData), 50);
    }
  }

  startTickEngine() {
    const poll = async () => {
      try {
        const res = await fetch("/api/benchmarks");
        const list = await res.json();
        const strip = document.getElementById("ticker-strip");
        if (!strip || !Array.isArray(list)) return;

        strip.innerHTML = list.map(b => {
          const isUp = b.change >= 0;
          const sign = isUp ? "+" : "";
          const cls = isUp ? "up" : "down";

          const prev = this.previousBenchmarkPrices.get(b.symbol);
          let flashClass = "";
          if (prev !== undefined && prev !== b.price) {
            flashClass = b.price > prev ? "tick-flash-green" : "tick-flash-red";
          }
          this.previousBenchmarkPrices.set(b.symbol, b.price);

          return `
            <div class="ticker-item">
              <span class="ticker-name">${b.name}</span>
              <span class="ticker-price ${flashClass}">$${b.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
              <span class="ticker-change ${cls}">${sign}${b.change.toFixed(2)} (${sign}${b.pct_change.toFixed(2)}%)</span>
            </div>
          `;
        }).join('<span style="color:#2a374f;">|</span>');

      } catch (e) {
        console.warn("Benchmark poll error:", e);
      }
    };

    poll();
    setInterval(poll, 1500); // 1.5-second interval
  }

  initSettingsModal() {
    const modal = document.getElementById("settings-modal");
    const openBtn = document.getElementById("btn-open-settings");
    const closeBtn = document.getElementById("btn-close-settings");
    const saveBtn = document.getElementById("btn-save-settings");
    const testBtn = document.getElementById("btn-test-provider");
    const testAlpacaBtn = document.getElementById("btn-test-alpaca");

    const providerSelect = document.getElementById("settings-provider-select");
    const modelSelect = document.getElementById("settings-model-select");
    const groqKeyInput = document.getElementById("settings-groq-key");
    const geminiKeyInput = document.getElementById("settings-gemini-key");
    const mistralKeyInput = document.getElementById("settings-mistral-key");
    const nvidiaKeyInput = document.getElementById("settings-nvidia-key");
    const ollamaUrlInput = document.getElementById("settings-ollama-url");

    const alpacaKeyInput = document.getElementById("settings-alpaca-key");
    const alpacaSecretInput = document.getElementById("settings-alpaca-secret");
    const alpacaUrlInput = document.getElementById("settings-alpaca-url");
    const alpacaStatus = document.getElementById("alpaca-ping-status");
    const alpacaMsg = document.getElementById("alpaca-ping-msg");

    const finnhubKeyInput = document.getElementById("settings-finnhub-key");
    const fredKeyInput = document.getElementById("settings-fred-key");
    const pingStatus = document.getElementById("provider-ping-status");
    const pingMsg = document.getElementById("provider-ping-msg");

    let cachedModels = null;

    const updateModelOptions = () => {
      if (!modelSelect || !cachedModels) return;
      const prov = providerSelect.value;
      const currentMod = localStorage.getItem("trader_model") || "";
      let list = [];

      if (prov === "groq") list = cachedModels.groq || [];
      else if (prov === "gemini") list = cachedModels.gemini || [];
      else if (prov === "mistral") list = cachedModels.mistral || [];
      else if (prov === "nvidia") list = cachedModels.nvidia || [];
      else if (prov === "ollama") list = cachedModels.ollama || [{ id: "llama3", name: "Ollama: llama3 (Default)" }];
      else list = [{ id: "rule-based-v3", name: "Autonomous Rule Engine" }];

      modelSelect.innerHTML = list.map(m => `
        <option value="${m.id}" ${m.id === currentMod ? 'selected' : ''}>${m.name}</option>
      `).join("");
    };

    const testProviderPing = async () => {
      if (!providerSelect || !pingStatus) return;
      const prov = providerSelect.value;
      let key = "";
      if (prov === "groq" && groqKeyInput) key = groqKeyInput.value.trim();
      else if (prov === "gemini" && geminiKeyInput) key = geminiKeyInput.value.trim();
      else if (prov === "mistral" && mistralKeyInput) key = mistralKeyInput.value.trim();
      else if (prov === "nvidia" && nvidiaKeyInput) key = nvidiaKeyInput.value.trim();

      const mod = modelSelect ? modelSelect.value : "";
      const url = ollamaUrlInput ? ollamaUrlInput.value.trim() : "";

      pingStatus.innerText = "⏳ TESTING...";
      pingStatus.style.background = "#854d0e";
      pingStatus.style.color = "#fef08a";
      if (pingMsg) {
        pingMsg.style.display = "block";
        pingMsg.innerText = `Connecting to ${prov.toUpperCase()}...`;
      }

      try {
        const res = await fetch("/api/agent/provider/ping", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            provider: prov,
            model: mod,
            api_key: key,
            base_url: url
          })
        });

        const data = await res.json();
        if (data.status === "LIVE") {
          pingStatus.innerText = `🟢 LIVE (${data.latency_ms}ms)`;
          pingStatus.style.background = "#14532d";
          pingStatus.style.color = "#86efac";
          if (pingMsg) pingMsg.innerText = `✅ ${data.message || 'Connected successfully'}`;
        } else {
          pingStatus.innerText = `🔴 DOWN`;
          pingStatus.style.background = "#7f1d1d";
          pingStatus.style.color = "#fca5a5";
          if (pingMsg) pingMsg.innerText = `⚠️ ${data.error || 'Connection failed'}`;
        }
      } catch (err) {
        pingStatus.innerText = "🔴 ERROR";
        pingStatus.style.background = "#7f1d1d";
        pingStatus.style.color = "#fca5a5";
        if (pingMsg) pingMsg.innerText = `Network error: ${err.message}`;
      }
    };

    const testAlpacaPing = async () => {
      if (!alpacaStatus) return;
      const aKey = alpacaKeyInput ? alpacaKeyInput.value.trim() : "";
      const aSec = alpacaSecretInput ? alpacaSecretInput.value.trim() : "";
      const aUrl = alpacaUrlInput ? alpacaUrlInput.value.trim() : "https://paper-api.alpaca.markets";

      alpacaStatus.innerText = "⏳ TESTING...";
      alpacaStatus.style.background = "#854d0e";
      alpacaStatus.style.color = "#fef08a";
      if (alpacaMsg) {
        alpacaMsg.style.display = "block";
        alpacaMsg.innerText = "Connecting to Alpaca US Paper Trading API...";
      }

      try {
        const res = await fetch("/api/alpaca/ping", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ api_key: aKey, secret_key: aSec, base_url: aUrl })
        });
        const data = await res.json();
        if (data.status === "LIVE") {
          alpacaStatus.innerText = `🟢 LIVE (${data.latency_ms}ms)`;
          alpacaStatus.style.background = "#14532d";
          alpacaStatus.style.color = "#86efac";
          if (alpacaMsg) {
            alpacaMsg.innerText = `✅ Connected to Alpaca (${data.account_number}). Buying Power: $${data.buying_power.toLocaleString()}`;
          }
        } else {
          alpacaStatus.innerText = data.status === "UNCONFIGURED" ? "⚫ UNCONFIGURED" : "🔴 DOWN";
          alpacaStatus.style.background = data.status === "UNCONFIGURED" ? "#1e293b" : "#7f1d1d";
          alpacaStatus.style.color = data.status === "UNCONFIGURED" ? "#94a3b8" : "#fca5a5";
          if (alpacaMsg) alpacaMsg.innerText = data.error || data.message || "Connection failed";
        }
      } catch (e) {
        alpacaStatus.innerText = "🔴 ERROR";
        alpacaStatus.style.background = "#7f1d1d";
        alpacaStatus.style.color = "#fca5a5";
        if (alpacaMsg) alpacaMsg.innerText = `Error: ${e.message}`;
      }
    };

    if (testBtn) testBtn.addEventListener("click", testProviderPing);
    if (testAlpacaBtn) testAlpacaBtn.addEventListener("click", testAlpacaPing);

    if (providerSelect) {
      providerSelect.addEventListener("change", () => {
        updateModelOptions();
        testProviderPing();
      });
    }

    if (openBtn) {
      openBtn.addEventListener("click", async () => {
        // Load stored settings
        if (providerSelect) providerSelect.value = localStorage.getItem("trader_provider") || "groq";
        if (groqKeyInput) groqKeyInput.value = localStorage.getItem("trader_groq_key") || "";
        if (geminiKeyInput) geminiKeyInput.value = localStorage.getItem("trader_gemini_key") || "";
        if (mistralKeyInput) mistralKeyInput.value = localStorage.getItem("trader_mistral_key") || "";
        if (nvidiaKeyInput) nvidiaKeyInput.value = localStorage.getItem("trader_nvidia_key") || "";
        if (ollamaUrlInput) ollamaUrlInput.value = localStorage.getItem("trader_ollama_url") || "http://localhost:11434";

        if (alpacaKeyInput) alpacaKeyInput.value = localStorage.getItem("alpaca_api_key") || "";
        if (alpacaSecretInput) alpacaSecretInput.value = localStorage.getItem("alpaca_secret_key") || "";
        if (alpacaUrlInput) alpacaUrlInput.value = localStorage.getItem("alpaca_base_url") || "https://paper-api.alpaca.markets";

        if (finnhubKeyInput) finnhubKeyInput.value = localStorage.getItem("finnhub_api_key") || "";
        if (fredKeyInput) fredKeyInput.value = localStorage.getItem("fred_api_key") || "";

        // Query available models from server
        try {
          const res = await fetch("/api/agent/models");
          cachedModels = await res.json();
          updateModelOptions();
        } catch (e) {
          console.warn("Failed to load models:", e);
        }

        modal.classList.add("open");
        testProviderPing();
        testAlpacaPing();
      });
    }

    if (closeBtn) closeBtn.addEventListener("click", () => modal.classList.remove("open"));

    if (saveBtn) {
      saveBtn.addEventListener("click", () => {
        if (providerSelect) localStorage.setItem("trader_provider", providerSelect.value);
        if (modelSelect) localStorage.setItem("trader_model", modelSelect.value);
        if (groqKeyInput) localStorage.setItem("trader_groq_key", groqKeyInput.value.trim());
        if (geminiKeyInput) localStorage.setItem("trader_gemini_key", geminiKeyInput.value.trim());
        if (mistralKeyInput) localStorage.setItem("trader_mistral_key", mistralKeyInput.value.trim());
        if (nvidiaKeyInput) localStorage.setItem("trader_nvidia_key", nvidiaKeyInput.value.trim());
        if (ollamaUrlInput) localStorage.setItem("trader_ollama_url", ollamaUrlInput.value.trim());

        if (alpacaKeyInput) localStorage.setItem("alpaca_api_key", alpacaKeyInput.value.trim());
        if (alpacaSecretInput) localStorage.setItem("alpaca_secret_key", alpacaSecretInput.value.trim());
        if (alpacaUrlInput) localStorage.setItem("alpaca_base_url", alpacaUrlInput.value.trim());

        if (finnhubKeyInput) localStorage.setItem("finnhub_api_key", finnhubKeyInput.value.trim());
        if (fredKeyInput) localStorage.setItem("fred_api_key", fredKeyInput.value.trim());

        if (this.agent) {
          this.agent.provider = providerSelect.value;
          this.agent.model = modelSelect.value;
          this.agent.groqApiKey = groqKeyInput ? groqKeyInput.value.trim() : "";
          this.agent.geminiApiKey = geminiKeyInput ? geminiKeyInput.value.trim() : "";
          this.agent.mistralApiKey = mistralKeyInput ? mistralKeyInput.value.trim() : "";
          this.agent.nvidiaApiKey = nvidiaKeyInput ? nvidiaKeyInput.value.trim() : "";
          this.agent.ollamaUrl = ollamaUrlInput ? ollamaUrlInput.value.trim() : "";
          this.agent.alpacaKey = alpacaKeyInput ? alpacaKeyInput.value.trim() : "";
          this.agent.alpacaSecret = alpacaSecretInput ? alpacaSecretInput.value.trim() : "";
          this.agent.updateProviderBadge();
        }

        if (this.portfolio) {
          this.portfolio.loadPortfolio();
        }

        modal.classList.remove("open");
      });
    }
  }

  initObservabilityModal() {
    const btnOpen = document.getElementById("btn-open-traces");
    const btnOpenEvals = document.getElementById("btn-open-evals");
    const btnOpenMemory = document.getElementById("btn-open-memory");
    const btnOpenPrompts = document.getElementById("btn-open-prompts");
    const btnClose = document.getElementById("btn-close-traces");
    const btnRefresh = document.getElementById("btn-refresh-traces");
    const btnRefreshEvals = document.getElementById("btn-refresh-evals");
    const btnRunBenchmark = document.getElementById("btn-run-benchmark");
    const modal = document.getElementById("traces-modal");

    const switchModalTab = (tabId) => {
      if (!modal) return;
      const tabBtns = modal.querySelectorAll(".setting-tabs .settings-tab-btn");
      tabBtns.forEach(btn => {
        if (btn.dataset.tab === tabId) {
          btn.classList.add("active");
        } else {
          btn.classList.remove("active");
        }
      });
      modal.querySelectorAll(".tab-pane").forEach(pane => {
        pane.style.display = pane.id === tabId ? "block" : "none";
      });

      if (tabId === "tab-eval-audit") {
        loadEvaluatorData();
      } else if (tabId === "tab-agent-memory") {
        loadAgentMemoryData();
      } else if (tabId === "tab-prompts-studio") {
        loadPromptsStudio();
      } else {
        loadObservabilityData();
      }
    };

    // Modal Tab click listeners
    if (modal) {
      modal.querySelectorAll(".setting-tabs .settings-tab-btn").forEach(btn => {
        btn.addEventListener("click", () => {
          switchModalTab(btn.dataset.tab);
        });
      });
    }

    const loadObservabilityData = async () => {
      try {
        const [tracesRes, metricsRes] = await Promise.all([
          fetch("/api/observability/traces?limit=30"),
          fetch("/api/observability/metrics")
        ]);

        const traces = await tracesRes.json();
        const metrics = await metricsRes.json();

        // Update metrics
        const totalEl = document.getElementById("trace-metric-total");
        const latEl = document.getElementById("trace-metric-latency");
        const tokEl = document.getElementById("trace-metric-tokens");
        const succEl = document.getElementById("trace-metric-success");

        if (totalEl) totalEl.innerText = metrics.total_calls || 0;
        if (latEl) latEl.innerText = `${metrics.avg_latency_ms || 0} ms`;
        if (tokEl) tokEl.innerText = Number(metrics.total_tokens_est || 0).toLocaleString();
        if (succEl) succEl.innerText = `${metrics.success_rate_pct || 100}%`;

        // Render table
        const tbody = document.getElementById("traces-table-tbody");
        if (!tbody) return;

        if (!traces || traces.length === 0) {
          tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:15px; color:var(--text-muted);">No LLM trace records yet. Ask questions in the Agent tab to generate traces.</td></tr>`;
          return;
        }

        tbody.innerHTML = traces.map(t => {
          const statusCol = t.status === "SUCCESS" ? "color:var(--green-up);" : (t.status === "FAILOVER" ? "color:var(--amber-primary);" : "color:var(--red-down);");
          return `
            <tr>
              <td style="color:var(--text-muted); font-size:10px;">${t.timestamp.split(" ")[1] || t.timestamp}</td>
              <td><strong style="color:var(--cyan-primary); font-size:10.5px;">${t.provider}</strong></td>
              <td style="color:#94a3b8; font-size:10px;">${t.model}</td>
              <td><strong style="color:#fff;">${t.symbol || 'MARKET'}</strong></td>
              <td style="text-align:right; font-size:10.5px; font-weight:bold; color:var(--cyan-primary);">${t.latency_ms} ms</td>
              <td style="text-align:right; font-size:10.5px; color:var(--amber-primary);">${t.total_tokens_est}</td>
              <td style="text-align:center;"><strong style="${statusCol} font-size:10px;">${t.status}</strong></td>
              <td style="font-size:10px; color:#cbd5e1; max-width:260px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${t.prompt_preview}</td>
            </tr>
          `;
        }).join("");
      } catch (e) {
        console.error("Error loading traces:", e);
      }
    };

    const loadEvaluatorData = async () => {
      try {
        const [metricsRes, benchRes, recentRes] = await Promise.all([
          fetch("/api/eval/metrics"),
          fetch("/api/eval/benchmark/latest"),
          fetch("/api/eval/recent?limit=25")
        ]);

        const metrics = await metricsRes.json();
        const bench = await benchRes.json();
        const recent = await recentRes.json();

        // Update KPI Metrics Cards
        const totalEl = document.getElementById("eval-metric-total");
        const passRateEl = document.getElementById("eval-metric-passrate");
        const compEl = document.getElementById("eval-metric-composite");
        const groundEl = document.getElementById("eval-metric-grounding");
        const guardEl = document.getElementById("eval-metric-guardrail");
        const advEl = document.getElementById("eval-metric-adversarial");

        if (totalEl) totalEl.innerText = metrics.total_evaluations || 0;
        if (passRateEl) passRateEl.innerText = `${metrics.pass_rate_pct != null ? metrics.pass_rate_pct.toFixed(1) : 100}%`;
        if (compEl) compEl.innerText = `${metrics.avg_composite_score != null ? metrics.avg_composite_score.toFixed(1) : '--'} / 100`;
        if (groundEl) groundEl.innerText = `${metrics.avg_grounding_score != null ? metrics.avg_grounding_score.toFixed(1) : '--'}%`;
        if (guardEl) guardEl.innerText = `${metrics.avg_guardrail_score != null ? metrics.avg_guardrail_score.toFixed(1) : '--'}%`;
        if (advEl) advEl.innerText = `${metrics.avg_adversarial_score != null ? metrics.avg_adversarial_score.toFixed(1) : '--'}%`;

        // Update Benchmark Suite Card
        const benchBadge = document.getElementById("benchmark-status-badge");
        const benchTime = document.getElementById("benchmark-timestamp-label");
        const benchTbody = document.getElementById("benchmark-table-tbody");

        if (benchBadge && bench.total_cases) {
          const passPct = bench.pass_rate_pct != null ? bench.pass_rate_pct.toFixed(1) : 100;
          benchBadge.innerText = `${bench.passed_cases}/${bench.total_cases} PASSED (${passPct}%)`;
          benchBadge.style.background = bench.failed_cases === 0 ? "#22c55e" : "#ef4444";
          benchBadge.style.color = bench.failed_cases === 0 ? "#000" : "#fff";
        }

        if (benchTime && bench.timestamp) {
          const durSec = bench.total_duration_ms ? (bench.total_duration_ms / 1000).toFixed(1) : "--";
          benchTime.innerText = `Last Run: ${bench.timestamp} (${durSec}s)`;
        }

        if (benchTbody && bench.results && bench.results.length > 0) {
          benchTbody.innerHTML = bench.results.map(r => {
            const statusBadge = r.passed
              ? `<span class="pill-badge" style="background:#22c55e; color:#000; font-size:9px; font-weight:bold; padding:2px 6px;">PASS</span>`
              : `<span class="pill-badge" style="background:#ef4444; color:#fff; font-size:9px; font-weight:bold; padding:2px 6px;">FAIL</span>`;
            
            const catColors = {
              "Grounding": "#38bdf8",
              "Guardrail": "#22c55e",
              "Tribunal": "#f59e0b",
              "SEC EDGAR": "#a855f7",
              "Macro": "#06b6d4",
              "Ecosystem": "#ec4899",
              "Order Integrity": "#10b981",
              "Latency": "#eab308"
            };
            const catColor = catColors[r.category] || "#94a3b8";

            return `
              <tr>
                <td><strong style="color:#fff; font-family:'JetBrains Mono',monospace;">${r.case_id}</strong></td>
                <td><strong style="color:#e2e8f0;">${r.name}</strong></td>
                <td><span class="pill-badge" style="border:1px solid ${catColor}; color:${catColor}; font-size:8.5px; padding:1px 5px; background:rgba(0,0,0,0.3);">${r.category}</span></td>
                <td style="text-align:right; font-family:'JetBrains Mono',monospace; color:var(--cyan-primary);">${r.latency_ms ? r.latency_ms.toFixed(0) : '--'} ms</td>
                <td style="text-align:center;">${statusBadge}</td>
                <td style="color:#cbd5e1; font-size:10px;">${r.details || (r.error ? `<span style="color:#ef4444;">${r.error}</span>` : '--')}</td>
              </tr>
            `;
          }).join("");
        }

        // Update Recent Turn Evaluations Table
        const evalTbody = document.getElementById("eval-audit-tbody");
        if (evalTbody) {
          if (!recent || recent.length === 0) {
            evalTbody.innerHTML = `<tr><td colspan="9" style="text-align:center; padding:12px; color:var(--text-muted);">No evaluation records in SQLite memory yet. Interact with the Trader Agent to audit turns.</td></tr>`;
          } else {
            evalTbody.innerHTML = recent.map(ev => {
              const verdictCol = ev.verdict === "PASS" ? "color:var(--green-up);" : (ev.verdict === "NEEDS_REVISION" ? "color:var(--amber-primary);" : "color:var(--red-down);");
              const verdictBadge = `<strong style="${verdictCol} font-size:9.5px; border:1px solid currentColor; padding:1px 5px; border-radius:2px;">${ev.verdict}</strong>`;
              const issuesStr = ev.issues && ev.issues.length > 0 
                ? `<span style="color:#f59e0b;">${ev.issues.join("; ")}</span>` 
                : `<span style="color:#64748b;">None (All strict gates satisfied)</span>`;

              return `
                <tr>
                  <td style="color:var(--text-muted); font-size:9.5px;">${ev.timestamp ? (ev.timestamp.split(" ")[1] || ev.timestamp) : '--'}</td>
                  <td><strong style="color:var(--cyan-primary); font-size:10px;">${ev.agent_name || 'Agent'}</strong></td>
                  <td><strong style="color:#fff;">${ev.symbol || '--'}</strong></td>
                  <td style="text-align:right; font-weight:bold; color:var(--cyan-primary);">${ev.composite_score != null ? Math.round(ev.composite_score) : '--'}/100</td>
                  <td style="text-align:right; color:#38bdf8;">${ev.grounding_score != null ? Math.round(ev.grounding_score) : '--'}</td>
                  <td style="text-align:right; color:var(--green-up);">${ev.guardrail_score != null ? Math.round(ev.guardrail_score) : '--'}</td>
                  <td style="text-align:right; color:var(--amber-primary);">${ev.adversarial_score != null ? Math.round(ev.adversarial_score) : '--'}</td>
                  <td style="text-align:center;">${verdictBadge}</td>
                  <td style="font-size:9.5px;">${issuesStr}</td>
                </tr>
              `;
            }).join("");
          }
        }

      } catch (e) {
        console.error("Error loading evaluator data:", e);
      }
    };

    const loadAgentMemoryData = async () => {
      try {
        const res = await fetch("/api/agent/memory/report");
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        const data = await res.json();

        // 1. Update KPI Summary Cards
        const kpis = data.kpis || {};
        const pnlEl = document.getElementById("mem-metric-pnl");
        const winrateEl = document.getElementById("mem-metric-winrate");
        const tradesEl = document.getElementById("mem-metric-trades");
        const blunderEl = document.getElementById("mem-metric-blunder");
        const winnerEl = document.getElementById("mem-metric-winner");
        const stratCountEl = document.getElementById("mem-metric-strategies");

        if (pnlEl) {
          const pnlVal = Number(kpis.all_time_net_pnl || 0);
          pnlEl.innerText = `${pnlVal >= 0 ? '+' : ''}$${pnlVal.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
          pnlEl.style.color = pnlVal >= 0 ? "var(--green-up)" : "var(--red-down)";
        }
        if (winrateEl) winrateEl.innerText = `${kpis.overall_win_rate_pct != null ? kpis.overall_win_rate_pct : '--'}%`;
        if (tradesEl) tradesEl.innerText = kpis.total_historical_trades || 0;
        if (blunderEl) blunderEl.innerText = `${kpis.worst_blunder_symbol || '--'} (-$${Math.abs(kpis.worst_blunder_loss || 0).toLocaleString()})`;
        if (winnerEl) winnerEl.innerText = `${kpis.biggest_gain_symbol || '--'} (+$${Number(kpis.biggest_gain_amount || 0).toLocaleString()})`;
        if (stratCountEl) stratCountEl.innerText = `${kpis.active_strategies_count || 5} Strategies`;

        // 2. Render Top 5 Blunders Table
        const blundersTbody = document.getElementById("mem-blunders-tbody");
        if (blundersTbody) {
          const blunders = data.top_blunders || [];
          if (blunders.length === 0) {
            blundersTbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:12px; color:var(--text-muted);">No recorded blunders in memory partition yet.</td></tr>`;
          } else {
            blundersTbody.innerHTML = blunders.map((b, idx) => `
              <tr>
                <td style="font-weight:bold; color:var(--text-muted); font-family:'JetBrains Mono',monospace;">#${idx + 1}</td>
                <td><strong style="color:#ef4444; font-size:11px;">${b.symbol}</strong></td>
                <td style="text-align:right; font-family:'JetBrains Mono',monospace; color:#ef4444; font-weight:bold;">-$${Math.abs(b.loss_amount || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                <td style="text-align:right; font-family:'JetBrains Mono',monospace; color:#ef4444;">${b.loss_pct}%</td>
                <td><span style="color:var(--amber-primary); font-size:10px; font-weight:bold;">${b.strategy || '--'}</span></td>
                <td style="font-size:10px; color:#cbd5e1; max-width:320px; line-height:1.35;">${b.the_blunder || '--'}</td>
                <td style="font-size:10px; color:#fca5a5; max-width:320px; line-height:1.35;"><strong style="color:#ef4444;">RULE:</strong> ${b.lesson_learned || '--'}</td>
              </tr>
            `).join("");
          }
        }

        // 3. Render Top 5 Biggest Gains Table
        const gainsTbody = document.getElementById("mem-gains-tbody");
        if (gainsTbody) {
          const gains = data.biggest_gains || [];
          if (gains.length === 0) {
            gainsTbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:12px; color:var(--text-muted);">No recorded gains in memory partition yet.</td></tr>`;
          } else {
            gainsTbody.innerHTML = gains.map((g, idx) => `
              <tr>
                <td style="font-weight:bold; color:var(--text-muted); font-family:'JetBrains Mono',monospace;">#${idx + 1}</td>
                <td><strong style="color:var(--green-up); font-size:11px;">${g.symbol}</strong></td>
                <td style="text-align:right; font-family:'JetBrains Mono',monospace; color:var(--green-up); font-weight:bold;">+$${Number(g.gain_amount || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                <td style="text-align:right; font-family:'JetBrains Mono',monospace; color:var(--green-up);">+${g.gain_pct}%</td>
                <td><span style="color:var(--cyan-primary); font-size:10px; font-weight:bold;">${g.strategy || '--'}</span></td>
                <td style="font-size:10px; color:#cbd5e1; max-width:360px; line-height:1.35;">${g.winning_thesis || '--'}</td>
                <td style="text-align:center; font-family:'JetBrains Mono',monospace; color:var(--green-up); font-weight:bold;">${g.conviction_score || '--'}/100</td>
                <td style="font-size:10px; color:var(--text-muted);">${g.holding_period || '--'}</td>
              </tr>
            `).join("");
          }
        }

        // 4. Render Active Strategies Table
        const stratsTbody = document.getElementById("mem-strategies-tbody");
        if (stratsTbody) {
          const strats = data.strategies_driven || [];
          if (strats.length === 0) {
            stratsTbody.innerHTML = `<tr><td colspan="8" style="text-align:center; padding:12px; color:var(--text-muted);">No active strategies registered in partition.</td></tr>`;
          } else {
            stratsTbody.innerHTML = strats.map(s => {
              const riskStr = Array.isArray(s.risk_rules) ? s.risk_rules.join(" • ") : (s.risk_rules || '--');
              return `
                <tr>
                  <td><strong style="color:#fff; font-size:11px;">${s.strategy_name}</strong></td>
                  <td><span class="pill-badge" style="border:1px solid var(--cyan-primary); color:var(--cyan-primary); font-size:9px; padding:1px 5px; background:rgba(0,0,0,0.3);">${s.category}</span></td>
                  <td style="text-align:right; font-family:'JetBrains Mono',monospace; font-weight:bold; color:var(--green-up);">${s.win_rate_pct}%</td>
                  <td style="text-align:right; font-family:'JetBrains Mono',monospace; color:#e2e8f0;">${s.trades_count}</td>
                  <td style="text-align:right; font-family:'JetBrains Mono',monospace; font-weight:bold; color:var(--green-up);">+$${Number(s.cumulative_pnl_usd || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</td>
                  <td style="text-align:right; font-family:'JetBrains Mono',monospace; color:var(--amber-primary);">${s.profit_factor}</td>
                  <td style="text-align:center;"><span class="pill-badge" style="background:#22c55e; color:#000; font-size:9px; font-weight:bold; padding:2px 6px;">${s.status}</span></td>
                  <td style="font-size:9.5px; color:#94a3b8; max-width:280px; line-height:1.35;">${riskStr}</td>
                </tr>
              `;
            }).join("");
          }
        }

      } catch (err) {
        console.error("Error loading agent memory data:", err);
      }
    };

    // Live JSON Partition Inspector & Rewrite Handler
    const partSelector = document.getElementById("memory-part-selector");
    const jsonEditor = document.getElementById("memory-json-editor");
    const btnReloadPart = document.getElementById("btn-reload-memory-part");
    const btnSavePart = document.getElementById("btn-save-memory-part");
    const saveStatus = document.getElementById("memory-save-status");

    const loadSelectedMemoryPartition = async (partName) => {
      if (!jsonEditor || !partName) return;
      if (saveStatus) {
        saveStatus.innerText = `⏳ Loading data/memory/${partName}.json from disk...`;
        saveStatus.style.color = "var(--text-muted)";
      }
      try {
        const res = await fetch(`/api/agent/memory/part/${partName}`);
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        const data = await res.json();
        jsonEditor.value = JSON.stringify(data, null, 2);
        if (saveStatus) {
          saveStatus.innerText = `🟢 Loaded data/memory/${partName}.json at ${(new Date()).toLocaleTimeString()}`;
          saveStatus.style.color = "var(--cyan-primary)";
        }
      } catch (e) {
        if (saveStatus) {
          saveStatus.innerText = `🔴 Failed to load partition: ${e.message}`;
          saveStatus.style.color = "var(--red-down)";
        }
      }
    };

    if (partSelector) {
      partSelector.addEventListener("change", (e) => {
        loadSelectedMemoryPartition(e.target.value);
      });
      // Initial load for default selection
      loadSelectedMemoryPartition(partSelector.value || "strategies");
    }

    if (btnReloadPart && partSelector) {
      btnReloadPart.addEventListener("click", () => {
        loadSelectedMemoryPartition(partSelector.value);
      });
    }

    if (btnSavePart && partSelector && jsonEditor) {
      btnSavePart.addEventListener("click", async () => {
        const partName = partSelector.value;
        let parsedData;
        try {
          parsedData = JSON.parse(jsonEditor.value);
        } catch (jsonErr) {
          if (saveStatus) {
            saveStatus.innerText = `🔴 JSON Syntax Error: ${jsonErr.message}`;
            saveStatus.style.color = "var(--red-down)";
          }
          return;
        }

        btnSavePart.disabled = true;
        btnSavePart.innerHTML = `⏳ SAVING TO DISK...`;
        if (saveStatus) {
          saveStatus.innerText = `Persisting to data/memory/${partName}.json...`;
          saveStatus.style.color = "var(--amber-primary)";
        }

        try {
          const res = await fetch(`/api/agent/memory/part/${partName}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              part: partName,
              data: parsedData,
              operation: "rewrite"
            })
          });
          const result = await res.json();
          if (res.ok && result.success) {
            if (saveStatus) {
              saveStatus.innerText = `✅ SUCCESS: Successfully rewrote data/memory/${partName}.json at ${(new Date()).toLocaleTimeString()}`;
              saveStatus.style.color = "var(--green-up)";
            }
            // Refresh table views and metrics
            await loadAgentMemoryData();
          } else {
            if (saveStatus) {
              saveStatus.innerText = `🔴 Save Error: ${result.error || 'Failed to rewrite partition'}`;
              saveStatus.style.color = "var(--red-down)";
            }
          }
        } catch (err) {
          if (saveStatus) {
            saveStatus.innerText = `🔴 Network Error: ${err.message}`;
            saveStatus.style.color = "var(--red-down)";
          }
        } finally {
          btnSavePart.disabled = false;
          btnSavePart.innerHTML = `SAVE & REWRITE PARTITION`;
        }
      });
    }

    // -------------------------------------------------------------------------
    // Prompts Studio - Centralized prompts/ Registry View & Edit
    // -------------------------------------------------------------------------
    const loadPromptsStudio = async () => {
      try {
        const res = await fetch("/api/prompts/list");
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        const data = await res.json();
        const prompts = data.prompts || [];

        const tbody = document.getElementById("prompts-catalog-tbody");
        if (tbody) {
          if (prompts.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding:12px; color:var(--text-muted);">No prompt files found in prompts/ folder.</td></tr>`;
          } else {
            const catColors = {
              "tribunal": "#f59e0b",
              "chat": "#38bdf8",
              "backtest": "#10b981",
              "critic": "#ef4444",
              "ecosystem": "#ec4899",
              "memory": "#a855f7",
              "simulation": "#fb923c"
            };

            tbody.innerHTML = prompts.map(p => {
              const col = catColors[p.category] || "#94a3b8";
              const varsBadges = p.variables && p.variables.length > 0 
                ? p.variables.map(v => `<span class="pill-badge" style="border:1px solid #475569; color:#94a3b8; font-size:8.5px; padding:1px 4px;">{${v}}</span>`).join(" ")
                : `<span style="color:#64748b; font-size:9px;">None</span>`;

              return `
                <tr>
                  <td><strong style="color:#fff; font-family:'JetBrains Mono',monospace;">${p.name}</strong></td>
                  <td><span class="pill-badge" style="border:1px solid ${col}; color:${col}; font-size:8.5px; padding:1px 6px; background:rgba(0,0,0,0.3); text-transform:uppercase;">${p.category}</span></td>
                  <td style="text-align:right; font-family:'JetBrains Mono',monospace; color:#cbd5e1;">${(p.size_bytes / 1024).toFixed(1)} KB</td>
                  <td style="text-align:right; font-family:'JetBrains Mono',monospace; color:var(--cyan-primary);">${p.char_count}</td>
                  <td>${varsBadges}</td>
                  <td style="font-size:9.5px; color:#cbd5e1; max-width:280px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;">${p.preview}</td>
                  <td style="text-align:center;">
                    <button class="f-key btn-edit-prompt-row" data-name="${p.name}" style="font-size:9px; padding:2px 8px;">EDIT</button>
                  </td>
                </tr>
              `;
            }).join("");

            tbody.querySelectorAll(".btn-edit-prompt-row").forEach(btn => {
              btn.addEventListener("click", () => {
                const name = btn.dataset.name;
                const selector = document.getElementById("prompt-file-selector");
                if (selector) selector.value = name;
                loadSelectedPromptFile(name);
              });
            });
          }
        }
      } catch (err) {
        console.error("Error loading prompts catalog:", err);
      }
    };

    const loadSelectedPromptFile = async (promptName) => {
      const editor = document.getElementById("prompt-file-editor");
      const badge = document.getElementById("prompt-file-badge");
      const varsContainer = document.getElementById("prompt-variables-container");
      const statusEl = document.getElementById("prompt-save-status");

      if (!editor || !promptName) return;
      if (statusEl) {
        statusEl.innerText = `⏳ Loading prompts/${promptName} from disk...`;
        statusEl.style.color = "var(--text-muted)";
      }

      try {
        const res = await fetch(`/api/prompts/get?name=${encodeURIComponent(promptName)}`);
        if (!res.ok) throw new Error(`HTTP error ${res.status}`);
        const data = await res.json();
        editor.value = data.content;
        if (badge) badge.innerText = `prompts/${promptName}`;

        // Detect variables
        const matches = Array.from(new Set(data.content.match(/\{([a-zA-Z0-9_]+)\}/g) || []));
        if (varsContainer) {
          if (matches.length > 0) {
            varsContainer.innerHTML = matches.map(m => `<span class="pill-badge" style="background:#0369a1; color:#fff; font-size:9px; padding:1px 5px; font-family:'JetBrains Mono',monospace;">${m}</span>`).join(" ");
          } else {
            varsContainer.innerHTML = `<span style="color:#64748b; font-size:9.5px;">Static prompt (no template variables)</span>`;
          }
        }

        if (statusEl) {
          statusEl.innerText = `🟢 Loaded prompts/${promptName} (${data.content.length} chars) at ${(new Date()).toLocaleTimeString()}`;
          statusEl.style.color = "var(--cyan-primary)";
        }
      } catch (e) {
        if (statusEl) {
          statusEl.innerText = `🔴 Failed to load prompt file: ${e.message}`;
          statusEl.style.color = "var(--red-down)";
        }
      }
    };

    const promptSelector = document.getElementById("prompt-file-selector");
    const btnReloadPrompt = document.getElementById("btn-reload-prompt-file");
    const btnSavePrompt = document.getElementById("btn-save-prompt-file");

    if (promptSelector) {
      promptSelector.addEventListener("change", (e) => {
        loadSelectedPromptFile(e.target.value);
      });
      // Initial load default
      loadSelectedPromptFile(promptSelector.value || "tribunal/bull_system.txt");
    }

    if (btnReloadPrompt && promptSelector) {
      btnReloadPrompt.addEventListener("click", () => {
        loadSelectedPromptFile(promptSelector.value);
      });
    }

    if (btnSavePrompt && promptSelector) {
      btnSavePrompt.addEventListener("click", async () => {
        const promptName = promptSelector.value;
        const editor = document.getElementById("prompt-file-editor");
        const statusEl = document.getElementById("prompt-save-status");
        if (!editor) return;

        btnSavePrompt.disabled = true;
        btnSavePrompt.innerHTML = `⏳ SAVING...`;
        if (statusEl) {
          statusEl.innerText = `Saving to prompts/${promptName}...`;
          statusEl.style.color = "var(--amber-primary)";
        }

        try {
          const res = await fetch("/api/prompts/save", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              name: promptName,
              content: editor.value
            })
          });
          const result = await res.json();
          if (res.ok && result.success) {
            if (statusEl) {
              statusEl.innerText = `✅ SUCCESS: Saved prompts/${promptName} at ${(new Date()).toLocaleTimeString()} (Active immediately on next model turn)`;
              statusEl.style.color = "var(--green-up)";
            }
            await loadPromptsStudio();
          } else {
            if (statusEl) {
              statusEl.innerText = `🔴 Save Error: ${result.detail || result.error || 'Failed to save prompt'}`;
              statusEl.style.color = "var(--red-down)";
            }
          }
        } catch (err) {
          if (statusEl) {
            statusEl.innerText = `🔴 Network Error: ${err.message}`;
            statusEl.style.color = "var(--red-down)";
          }
        } finally {
          btnSavePrompt.disabled = false;
          btnSavePrompt.innerHTML = `SAVE & APPLY PROMPT`;
        }
      });
    }

    if (btnOpen && modal) {
      btnOpen.addEventListener("click", () => {
        modal.classList.add("open");
        switchModalTab("tab-traces-wire");
      });
    }

    if (btnOpenEvals && modal) {
      btnOpenEvals.addEventListener("click", () => {
        modal.classList.add("open");
        switchModalTab("tab-eval-audit");
      });
    }

    if (btnOpenMemory && modal) {
      btnOpenMemory.addEventListener("click", () => {
        modal.classList.add("open");
        switchModalTab("tab-agent-memory");
      });
    }

    if (btnOpenPrompts && modal) {
      btnOpenPrompts.addEventListener("click", () => {
        modal.classList.add("open");
        switchModalTab("tab-prompts-studio");
      });
    }

    if (btnClose && modal) {
      btnClose.addEventListener("click", () => modal.classList.remove("open"));
    }

    if (btnRefresh) {
      btnRefresh.addEventListener("click", () => loadObservabilityData());
    }

    if (btnRefreshEvals) {
      btnRefreshEvals.addEventListener("click", () => loadEvaluatorData());
    }

    if (btnRunBenchmark) {
      btnRunBenchmark.addEventListener("click", async () => {
        btnRunBenchmark.disabled = true;
        const originalText = btnRunBenchmark.innerHTML;
        btnRunBenchmark.innerHTML = `⏳ RUNNING 10-POINT BENCHMARK SUITE... (~30s)`;
        btnRunBenchmark.style.opacity = "0.75";
        try {
          const res = await fetch("/api/eval/benchmark/run", { method: "POST" });
          if (res.ok) {
            await loadEvaluatorData();
          }
        } catch (err) {
          console.error("Failed to run benchmark suite:", err);
        } finally {
          btnRunBenchmark.disabled = false;
          btnRunBenchmark.innerHTML = originalText;
          btnRunBenchmark.style.opacity = "1";
        }
      });
    }

    if (modal) {
      modal.addEventListener("click", (e) => {
        if (e.target === modal) modal.classList.remove("open");
      });
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window.terminalApp = new BloombergApp();
  window.terminalApp.init();
});
