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
            this.selectStock(sym);
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
          this.selectStock(val);
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
        if (sym) this.selectStock(sym);
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
          input.value = `Analyze technical setup for ${this.activeSymbol}`;
          input.focus();
        }
      });
    }
  }

  async selectStock(symbol) {
    const sym = symbol.toUpperCase().trim();
    this.activeSymbol = sym;

    // Update active badge display in header
    const activeTickerEl = document.getElementById("global-active-ticker");
    if (activeTickerEl) activeTickerEl.innerText = sym;

    const navSym = document.getElementById("nav-btn-sym");
    if (navSym) navSym.innerText = sym;

    const navChatSym = document.getElementById("nav-chat-sym");
    if (navChatSym) navChatSym.innerText = sym;

    const orderInput = document.getElementById("order-symbol-input");
    if (orderInput) orderInput.value = sym;

    // Fetch quick quote to update top active bar
    try {
      const qRes = await fetch(`/api/stock/${encodeURIComponent(sym)}/quote`);
      const q = await qRes.json();
      const pEl = document.getElementById("global-active-price");
      const cEl = document.getElementById("global-active-chg");
      if (pEl) pEl.innerText = `$${q.price.toFixed(2)}`;
      if (cEl) {
        const isUp = q.change >= 0;
        const sign = isUp ? "+" : "";
        cEl.innerText = `${sign}${q.change.toFixed(2)} (${sign}${q.pct_change.toFixed(2)}%)`;
        cEl.className = `quote-change-badge ${isUp ? 'up' : 'down'}`;
      }
    } catch (e) {
      console.warn("Failed to fetch quote for header active badge:", e);
    }

    // Refresh sub-views
    if (this.agent) this.agent.setSymbol(sym);
    if (this.dashboard) await this.dashboard.loadCompany(sym);
    if (this.chart) await this.chart.loadChartData(sym, this.chart.currentPeriod);
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
    });
  }

  switchView(viewName) {
    this.currentView = viewName;

    document.querySelectorAll(".nav-tab[data-view]").forEach(b => {
      b.classList.toggle("active", b.dataset.view === viewName);
    });

    const panes = ["homepage", "agent", "dashboard", "terminal", "portfolio", "scanner"];
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
}

document.addEventListener("DOMContentLoaded", () => {
  window.terminalApp = new BloombergApp();
  window.terminalApp.init();
});
