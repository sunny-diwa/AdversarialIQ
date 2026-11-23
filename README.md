# AdversarialIQ - S&P 500 AI Trading Terminal & Multi-Agent Syndicate

An institutional-grade trading terminal, live technical scanner, and adversarial multi-agent trading court built specifically for S&P 500 equities.

---

## ⚖️ The AdversarialIQ Core Thesis

At its core, **AdversarialIQ** operates on an adversarial prosecution framework for every trade and equity evaluation:

```
                          ┌───────────────────────────┐
                          │   5-LAYER DATA DOSSIER    │
                          │ Technicals • SEC EDGAR    │
                          │ Insider 13F • News • FRED │
                          └─────────────┬─────────────┘
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 │                                             │
                 ▼                                             ▼
  🐂 AGENT BULL (ADVOCATE)                      🐻 AGENT BEAR (ADVERSARY)
  Prosecutes the maximum upside case            Aggressively stress-tests downside
  • Technical momentum & breakouts              • Multiples compression & debt
  • Item 7 MD&A revenue growth                  • SEC Item 1A Risk Factors
  • Executive insider buying clusters           • Executive insider divestments
  • Real-time catalyst headlines                • 10Y-2Y yield curve inversion
                 │                                             │
                 └──────────────────────┬──────────────────────┘
                                        │
                                        ▼
                         ⚖️ AGENT JUDGE (CHIEF ARBITER)
                         Cross-examines both cases impartially
                         • AdversarialIQ Conviction Score (0-100)
                         • Definitive Ruling: APPROVED / PROHIBITED / REJECTED
                         • Kelly & 2% Account Risk Position Sizing
                         • Stop-Loss & Target Breakout Orders
                                        │
                                        ▼
                         ⚡ ALPACA PAPER TRADING API
                         Direct execution routing via https://paper-api.alpaca.markets
                         (With automatic local simulated desk fallback)
```

---

## 🏛️ Production Architecture (`src/`)

```
terminal/
├── src/
│   ├── __init__.py
│   ├── config.py           # Master config, SEC identity, cache TTLs, S&P 500 catalog (.env loader)
│   ├── alpaca_client.py    # Alpaca US Paper Trading API client (Account, Positions, Orders, Ping)
│   ├── llm.py              # Multi-provider LLM manager (Groq, Gemini, Mistral, NVIDIA NIM, Ollama, Quant)
│   ├── market_data.py      # yfinance real-time quotes, multi-timeframe candles, SMA/EMA/BB/RSI/MACD/ATR
│   ├── sec_edgar.py        # SEC EDGAR 10-K/10-Q/8-K MD&A disclosures, Form 4 insider clusters & 13F ownership
│   ├── news.py             # Breaking news aggregator, catalyst classifier (Earnings, M&A, AI), sentiment polarity
│   ├── macro.py            # FRED API & CBOE Treasury yield curve (10Y-2Y spread, inversion warning, VIX)
│   ├── portfolio.py        # Institutional paper trading ($10,000 base, Alpaca Paper routing, Kelly analytics)
│   ├── scanner.py          # Multi-indicator technical screener & S&P 500 market movers
│   └── agent_syndicate.py  # AdversarialIQ Bull-Bear-Judge tribunal & FinGPT briefing note
├── server.py               # Production FastAPI server & REST API endpoints
├── terminal_trader.py      # Standalone Bloomberg-style ASCII CLI Terminal
├── .env.example            # Master environment configuration template
├── data/sp500.json         # S&P 500 constituent catalog (503 equities)
├── data/portfolio.json     # Clean $10,000 paper trading ledger
└── static/                 # Bloomberg Terminal UI (Canvas Candlesticks, Multi-layer Docks, Order Pad)
```

---

## 🤖 Multi-Provider LLM Engine with On-Demand Health Ping

| Provider | Supported Models | Key Source & URL |
|---|---|---|
| **Groq Cloud** | `llama-3.3-70b-versatile`, `llama-3.1-8b-instant`, `mixtral-8x7b-32768` | Free API key at https://console.groq.com |
| **Google AI Studio** | `gemini-2.0-flash`, `gemini-1.5-pro`, `gemini-1.5-flash` | Free API key at https://aistudio.google.com |
| **Mistral AI** | `mistral-small-latest`, `mistral-large-latest`, `codestral-latest` | Free API key at https://console.mistral.ai |
| **NVIDIA NIM** | `z-ai/glm-5.3-flash`, `meta/llama-3.3-70b-instruct`, `mistralai/mistral-large-2-instruct` | Free API key at https://build.nvidia.com |
| **Ollama Local** | Dynamic local models (e.g., `llama3`, `mistral`) | Local daemon at http://localhost:11434 |
| **Autonomous Quant Engine** | `rule-based-v3` | Zero external API keys required |

- **On-Demand Health Testing (`POST /api/agent/provider/ping`):**
  - Sends a lightweight 1-token probe **strictly when you switch or test a provider** in the Settings Modal.
  - Measures roundtrip latency in milliseconds (`🟢 LIVE (42ms)` or `🔴 DOWN`).
  - **Zero continuous background polling**, strictly preserving your provider rate limits.
- **Automatic Failover:**
  - If a primary cloud provider encounters rate limiting (HTTP 429) or network interruption, the engine automatically fails over through the chain and finally to the autonomous quantitative engine.

---

## 📈 Alpaca US Paper Trading Integration

- **Base Endpoint:** `https://paper-api.alpaca.markets/v2`
- **Features:**
  - Real-time buying power, portfolio cash, and marked-to-market equity.
  - Live position tracking with unrealized profit & loss.
  - Market orders, limit orders, and bracket stop-loss / take-profit order routing.
  - 1-click test button in Settings Modal verifying API connectivity.
  - **Zero-Key Fallback:** If Alpaca keys are not provided, the terminal automatically runs in **Local Simulated Desk** mode ($10,000 clean baseline, 0 positions), so it functions immediately out of the box!

---

## 🌟 Institutional Multi-Layer Data Infrastructure

1. **Price & Technicals (`yfinance`):** Real-time candles, SMA 20/50/200, Bollinger Bands, RSI (14), MACD (12,26,9), and Volume.
2. **10-K / 10-Q / 8-K Reports (SEC EDGAR via `edgartools`):** Full corporate filings index, Item 7 MD&A disclosures, Item 1A Risk Factors.
3. **Insider & 13F Activity (SEC Form 4 & 13F):** Executive cluster detection (`🟢 ACCUMULATION` / `🔴 DISTRIBUTION`), 90-day Form 4 trades table, top institutional ownership.
4. **Breaking News (Finnhub & RSS Fallback):** Headline sentiment scoring (`BULLISH`, `BEARISH`, `NEUTRAL`), catalyst tagging (`EARNINGS`, `M&A`, `PRODUCT/AI`, `REGULATORY`).
5. **Macro Indicators (FRED API & CBOE Treasury Fallback):** 10-Year Treasury Yield (`^TNX`), Short-Rate (`^IRX`), 10Y-2Y Yield Curve Spread (bps), Inversion Warning signal, CBOE VIX Volatility regime.

---

## 🚀 Quick Start & Environment Setup

```bash
# 1. Clone repository
git clone https://github.com/sunny-diwa/AdversarialIQ.git
cd AdversarialIQ

# 2. Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure your API keys in .env
cp .env.example .env
# Edit .env with your Alpaca, Groq, Gemini, Mistral, or NVIDIA keys

# 5. Launch the terminal server
python server.py
```

Open **`http://localhost:8080`** in your browser.

### Keyboard Shortcuts
- `<F1>`: Market Pulse Homepage & S&P 500 Movers
- `<F2>`: AdversarialIQ Multi-Agent Tribunal Desk
- `<F3>`: Company Dashboard & Multi-Layer Institutional Dock
- `<F4>`: Candlestick Terminal & Indicator Suite
- `<F5>`: Paper Trading Portfolio Ledger (Alpaca / Local Desk)
- `<F6>`: S&P 500 Multi-Indicator Scanner
