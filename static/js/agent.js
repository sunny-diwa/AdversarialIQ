/**
 * Bloomberg Terminal V3.0 - AI Trader Agent Chatbot Engine
 * Supports Groq API, Local Ollama, and Institutional Quant Execution
 */

class SP500TraderAgent {
  constructor() {
    this.messagesContainer = document.getElementById("chat-messages-container");
    this.input = document.getElementById("chat-user-input");
    this.sendBtn = document.getElementById("chat-send-btn");
    this.currentSymbol = "NVDA";

    this.provider = localStorage.getItem("trader_provider") || "groq";
    this.model = localStorage.getItem("trader_model") || "llama-3.3-70b-versatile";
    this.groqApiKey = localStorage.getItem("trader_groq_key") || "";
    this.ollamaUrl = localStorage.getItem("trader_ollama_url") || "http://localhost:11434";
  }

  init(symbol = "NVDA") {
    this.currentSymbol = symbol;
    this.setupListeners();
    this.updateProviderBadge();
  }

  setupListeners() {
    if (this.sendBtn) {
      this.sendBtn.addEventListener("click", () => this.handleSend());
    }

    if (this.input) {
      this.input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          this.handleSend();
        }
      });
    }

    const clearBtn = document.getElementById("btn-clear-chat");
    if (clearBtn) {
      clearBtn.addEventListener("click", () => {
        if (this.messagesContainer) {
          this.messagesContainer.innerHTML = `
            <div class="chat-msg agent">
              <div class="meta">TRADER AGENT • DESK ONLINE</div>
              <div class="msg-bubble">
                Chat cleared. S&amp;P 500 Quantitative Desk ready. Ask me any question about equities, technicals, or paper trades!
              </div>
            </div>
          `;
        }
      });
    }
    document.querySelectorAll(".quick-pill").forEach(pill => {
      pill.addEventListener("click", () => {
        const text = pill.dataset.prompt;
        if (text && this.input) {
          this.input.value = text.replace("{symbol}", this.currentSymbol);
          this.handleSend();
        }
      });
    });
  }

  setSymbol(sym) {
    this.currentSymbol = sym;
  }

  updateProviderBadge() {
    const badge = document.getElementById("agent-provider-tag");
    if (badge) {
      if (this.provider === "groq") {
        badge.innerText = `GROQ [${this.model.split('-')[0] || 'Llama'}]`;
        badge.style.color = "var(--amber-primary)";
      } else if (this.provider === "ollama") {
        badge.innerText = `OLLAMA LOCAL [${this.model}]`;
        badge.style.color = "var(--cyan-primary)";
      } else {
        badge.innerText = "QUANT RULE ENGINE";
        badge.style.color = "var(--green-up)";
      }
    }
  }

  async handleSend() {
    const text = this.input ? this.input.value.trim() : "";
    if (!text) return;

    this.input.value = "";
    this.appendMessage("user", text);

    const typingId = this.appendTyping();

    try {
      const res = await fetch("/api/agent/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          provider: this.provider,
          model: this.model,
          groq_api_key: this.groqApiKey,
          ollama_base_url: this.ollamaUrl,
          current_symbol: this.currentSymbol
        })
      });

      this.removeTyping(typingId);

      if (res.status === 200) {
        const data = await res.json();
        this.appendMessage("agent", data.response, data.provider);

        // If trade was executed, trigger portfolio refresh
        if (data.trade && window.terminalPortfolio) {
          window.terminalPortfolio.loadPortfolio();
        }
      } else {
        this.appendMessage("agent", `⚠️ Agent Error: ${res.statusText}`);
      }
    } catch (e) {
      this.removeTyping(typingId);
      this.appendMessage("agent", `⚠️ Failed to reach Trader Agent: ${e.message}`);
    }
  }

  appendMessage(sender, content, provider = null) {
    if (!this.messagesContainer) return;

    const msgEl = document.createElement("div");
    msgEl.className = `chat-msg ${sender}`;

    const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    const metaTag = sender === "user" ? `YOU • ${timeStr}` : `${provider || 'TRADER AGENT'} • ${timeStr}`;

    const formattedContent = this.formatMarkdown(content);

    msgEl.innerHTML = `
      <div class="meta">${metaTag}</div>
      <div class="msg-bubble">${formattedContent}</div>
    `;

    this.messagesContainer.appendChild(msgEl);
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
  }

  appendTyping() {
    if (!this.messagesContainer) return null;
    const id = `typing-${Date.now()}`;
    const el = document.createElement("div");
    el.id = id;
    el.className = "chat-msg agent";
    el.innerHTML = `
      <div class="meta">QUANT AGENT • ANALYZING</div>
      <div class="msg-bubble" style="color:var(--amber-primary);">
        <span class="pulse-dot" style="display:inline-block; margin-right:6px;"></span> Processing market data &amp; technical indicators...
      </div>
    `;
    this.messagesContainer.appendChild(el);
    this.messagesContainer.scrollTop = this.messagesContainer.scrollHeight;
    return id;
  }

  removeTyping(id) {
    if (!id) return;
    const el = document.getElementById(id);
    if (el) el.remove();
  }

  formatMarkdown(text) {
    if (!text) return "";
    let html = text
      .replace(/^### (.*$)/gim, '<div style="color:var(--amber-primary); font-weight:800; font-size:13px; margin:4px 0;">$1</div>')
      .replace(/^#### (.*$)/gim, '<div style="color:var(--cyan-primary); font-weight:700; font-size:11px; margin:4px 0;">$1</div>')
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/`(.*?)`/g, '<code style="background:#020509; border:1px solid #233048; padding:1px 4px; color:#00ff66; border-radius:2px;">$1</code>')
      .replace(/\n\n/g, '<div style="height:6px;"></div>')
      .replace(/\n- /g, '<br>• ')
      .replace(/\n/g, '<br>');
    return html;
  }
}

function json_payload(obj) {
  return JSON.stringify(obj);
}

window.SP500TraderAgent = SP500TraderAgent;
