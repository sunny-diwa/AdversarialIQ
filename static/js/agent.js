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
    this.model = localStorage.getItem("trader_model") || "openai/gpt-oss-120b";
    this.groqApiKey = localStorage.getItem("trader_groq_key") || "";
    this.geminiApiKey = localStorage.getItem("trader_gemini_key") || "";
    this.mistralApiKey = localStorage.getItem("trader_mistral_key") || "";
    this.nvidiaApiKey = localStorage.getItem("trader_nvidia_key") || "";
    this.ollamaUrl = localStorage.getItem("trader_ollama_url") || "http://localhost:11434";
    this.alpacaKey = localStorage.getItem("alpaca_api_key") || "";
    this.alpacaSecret = localStorage.getItem("alpaca_secret_key") || "";
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
              <div class="meta">ADVERSARIALIQ COURT • DESK ONLINE</div>
              <div class="msg-bubble">
                Court cleared. AdversarialIQ Trade Tribunal ready. Ask any ticker cross-examination, technical setup, or route paper trades!
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
      const p = this.provider;
      if (p === "groq") {
        badge.innerText = `GROQ [${(this.model || 'Llama').split('-')[0]}]`;
        badge.style.color = "var(--amber-primary)";
      } else if (p === "gemini") {
        badge.innerText = `GEMINI [${this.model || '2.0-flash'}]`;
        badge.style.color = "#60a5fa";
      } else if (p === "mistral") {
        badge.innerText = `MISTRAL [${(this.model || 'small').split('-')[1] || 'AI'}]`;
        badge.style.color = "#f97316";
      } else if (p === "nvidia") {
        badge.innerText = `NVIDIA NIM [${(this.model || 'glm').split('/')[1] || 'NIM'}]`;
        badge.style.color = "#76b900";
      } else if (p === "ollama") {
        badge.innerText = `OLLAMA [${this.model || 'llama3'}]`;
        badge.style.color = "var(--cyan-primary)";
      } else {
        badge.innerText = "QUANT ENGINE (AUTONOMOUS)";
        badge.style.color = "var(--green-up)";
      }
    }

    const brokerBadge = document.getElementById("agent-broker-badge");
    if (brokerBadge) {
      const aKey = this.alpacaKey || localStorage.getItem("alpaca_api_key");
      if (aKey) {
        brokerBadge.innerText = "BROKER: ALPACA US PAPER READY";
        brokerBadge.style.color = "var(--green-up)";
      } else {
        brokerBadge.innerText = "BROKER: LOCAL SIMULATED DESK ($10K)";
        brokerBadge.style.color = "var(--cyan-primary)";
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
          gemini_api_key: this.geminiApiKey,
          mistral_api_key: this.mistralApiKey,
          nvidia_api_key: this.nvidiaApiKey,
          ollama_base_url: this.ollamaUrl,
          current_symbol: this.currentSymbol,
          alpaca_key: this.alpacaKey,
          alpaca_secret: this.alpacaSecret
        })
      });

      this.removeTyping(typingId);

      if (res.status === 200) {
        const data = await res.json();
        const metaTag = data.tool_called 
          ? `${data.provider || 'TRADER AGENT'} • TOOL: ${data.tool_called.toUpperCase()}`
          : data.provider;
        this.appendMessage("agent", data.response, metaTag, data.evaluation);

        // If backtest was executed, feed to Backtest Studio
        if (data.backtest && window.backtestStudio) {
          window.backtestStudio.renderResults(data.backtest);
        }

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

  appendMessage(sender, content, provider = null, evaluation = null) {
    if (!this.messagesContainer) return;

    const msgEl = document.createElement("div");
    msgEl.className = `chat-msg ${sender}`;

    const timeStr = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    let metaTag = sender === "user" ? `YOU • ${timeStr}` : `${provider || 'TRADER AGENT'} • ${timeStr}`;

    if (evaluation && sender === "agent") {
      const passColor = evaluation.verdict === 'PASS' ? '#22c55e' : (evaluation.verdict === 'NEEDS_REVISION' ? '#f59e0b' : '#ef4444');
      const score = Math.round(evaluation.composite_score || 0);
      metaTag += ` • <span class="eval-pill-clickable" style="cursor:pointer; color:${passColor}; font-weight:bold; border:1px solid ${passColor}; padding:1px 6px; border-radius:3px; font-size:9.5px; background:rgba(0,0,0,0.4);" title="Click to inspect Agent Evaluation & Benchmark Audit">🛡️ EVAL: ${score}/100 ${evaluation.verdict}</span>`;
    }

    const formattedContent = this.formatMarkdown(content);

    let evalDrawerHtml = "";
    if (evaluation && sender === "agent") {
      const gScore = evaluation.grounding_score != null ? Math.round(evaluation.grounding_score) : '--';
      const rScore = evaluation.guardrail_score != null ? Math.round(evaluation.guardrail_score) : '--';
      const advScore = evaluation.adversarial_score != null ? Math.round(evaluation.adversarial_score) : '--';
      const tScore = evaluation.tool_score != null ? Math.round(evaluation.tool_score) : '--';
      const selfCorr = evaluation.needs_revision ? 'Self-Corrected' : 'Deterministic Direct';

      evalDrawerHtml = `
        <div class="eval-detail-drawer" style="margin-top:8px; padding:6px 10px; background:rgba(15,23,42,0.7); border:1px solid rgba(56,189,248,0.25); border-radius:4px; font-size:10px; color:#94a3b8; display:flex; flex-wrap:wrap; gap:12px; align-items:center;">
          <div><span style="color:#64748b;">Grounding:</span> <strong style="color:#38bdf8;">${gScore}/100</strong></div>
          <div><span style="color:#64748b;">Risk Guardrails:</span> <strong style="color:#22c55e;">${rScore}/100</strong></div>
          <div><span style="color:#64748b;">Adversarial Balance:</span> <strong style="color:#f59e0b;">${advScore}/100</strong></div>
          <div><span style="color:#64748b;">Tool Integrity:</span> <strong style="color:#a855f7;">${tScore}/100</strong></div>
          <div><span style="color:#64748b;">Reflection:</span> <strong style="color:#fff;">${selfCorr}</strong></div>
        </div>
      `;
    }

    msgEl.innerHTML = `
      <div class="meta">${metaTag}</div>
      <div class="msg-bubble">${formattedContent}${evalDrawerHtml}</div>
    `;

    // Hook click on eval pill to open traces modal directly to eval tab
    const pill = msgEl.querySelector(".eval-pill-clickable");
    if (pill) {
      pill.addEventListener("click", () => {
        const modal = document.getElementById("traces-modal");
        const evalTabBtn = document.getElementById("tab-btn-eval-audit");
        if (modal) {
          modal.classList.add("open");
          if (evalTabBtn) evalTabBtn.click();
        }
      });
    }

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
    let html = text;

    // Code blocks ```python ... ```
    html = html.replace(/```(?:python)?\s*([\s\S]*?)```/g, (match, code) => {
      return `<pre style="background:#020509; border:1px solid #1e293b; border-radius:4px; padding:10px; color:#38bdf8; font-family:'JetBrains Mono', monospace; font-size:10.5px; line-height:1.4; overflow-x:auto; margin:8px 0;"><code>${code.trim()}</code></pre>`;
    });

    // Markdown tables
    html = html.replace(/(\|.+?\|\n\|[-:| ]+\|\n(?:\|.+?\|\n?)+)/g, (match) => {
      const rows = match.trim().split("\n");
      const headers = rows[0].split("|").slice(1, -1).map(h => h.trim());
      const bodyRows = rows.slice(2);

      let tHtml = '<table class="bloomberg-table" style="margin:8px 0; width:100%;"><thead><tr>';
      headers.forEach(h => {
        tHtml += `<th style="padding:4px 8px; font-size:10px;">${h}</th>`;
      });
      tHtml += '</tr></thead><tbody>';
      bodyRows.forEach(r => {
        const cells = r.split("|").slice(1, -1).map(c => c.trim());
        tHtml += '<tr>';
        cells.forEach(c => {
          tHtml += `<td style="padding:4px 8px; font-size:10px;">${c}</td>`;
        });
        tHtml += '</tr>';
      });
      tHtml += '</tbody></table>';
      return tHtml;
    });

    html = html
      .replace(/^### (.*$)/gim, '<div style="color:var(--amber-primary); font-weight:800; font-size:13px; margin:6px 0;">$1</div>')
      .replace(/^#### (.*$)/gim, '<div style="color:var(--cyan-primary); font-weight:700; font-size:11px; margin:6px 0 2px 0;">$1</div>')
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
