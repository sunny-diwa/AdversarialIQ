# S&P 500 AI Quantitative Trader & Bloomberg Terminal (AdversarialIQ)

An institutional-grade trading terminal, live technical scanner, and conversational multi-agent trader desk built specifically for S&P 500 equities.

---

## 🏛️ Architecture & Core Data Layers (`src/`)

```
terminal/
├── src/
│   ├── config.py           # Paths, SEC identity, cache TTLs, S&P 500 universe
│   ├── llm.py              # Multi-provider LLM manager (Groq, Ollama, Quant) with on-demand ping & failover
│   ├── market_data.py      # yfinance real-time quotes, multi-timeframe candles, SMA/EMA/BB/RSI/MACD
│   ├── sec_edgar.py        # SEC EDGAR 10-K/10-Q/8-K MD&A disclosures, Form 4 insider clusters & 13F ownership
│   ├── news.py             # Breaking news aggregator, catalyst classifier (Earnings, M&A, AI), and sentiment polarity
│   ├── macro.py            # FRED API & CBOE Treasury yield curve (10Y-2Y spread, inversion warning, VIX)
│   ├── portfolio.py        # Institutional paper trading ($10,000 base, 0 positions, Kelly risk analytics)
│   ├── scanner.py          # Multi-indicator technical scanner (RSI, MACD cross, trend, momentum)
│   └── agent_syndicate.py  # TradingAgents adversarial debate, FinGPT briefing & prompt synthesizer
├── server.py               # Production FastAPI server & REST API endpoints
├── terminal_trader.py      # Standalone Bloomberg-style ASCII CLI Terminal
├── data/                   # S&P 500 catalog & persistent paper portfolio ledger
└── static/                 # Bloomberg Terminal UI (Candlestick Canvas, Multi-layer Docks, Order Pad)
```

---

## 🌟 Institutional Multi-Layer Data Integrations

| Layer | Tool / API | Cost & Requirement | Terminal Integration |
|---|---|---|---|
| **Price & Technicals** | `yfinance` | Free (No key) | Real-time quotes, candlestick history, SMA 20/50/200, Bollinger Bands, RSI 14, MACD (12,26,9), and Volume. |
| **10-K / 10-Q / 8-K Reports** | SEC EDGAR (`edgartools`) | Free (User-Agent header only) | Full corporate filings index, Item 7 MD&A disclosure summaries, Item 1A Risk Factors, and earnings releases. |
| **Insider & 13F Activity** | SEC EDGAR (Form 4 & 13F) | Free (No key) | Executive cluster detection (`🟢 ACCUMULATION` / `🔴 DISTRIBUTION`), 90-day Form 4 trades table, and top 13F institutional fund ownership. |
| **Breaking News** | Finnhub / Google RSS | Free API key / Zero-key fallback | Real-time headline sentiment scoring (`BULLISH`, `BEARISH`, `NEUTRAL`), catalyst classification (`EARNINGS`, `M&A`, `PRODUCT/AI`, `REGULATORY`), and publisher wire. |
| **Macro Indicators** | FRED API (`fredapi`) / CBOE | Free API key / Zero-key fallback | 10-Year Treasury Yield, Short-Rate, 10Y-2Y Yield Curve Spread (bps), Inversion Warning signal, CBOE VIX Volatility regime, and CPI inflation proxy. |

---

## 🤖 Multi-Provider LLM Engine & On-Demand Health Ping

- **Supported Providers:**
  - **Groq Cloud API:** High-speed inference using Llama 3.3 70B, Llama 3.1 8B, and Mixtral 8x7B.
  - **Ollama Local:** Private offline on-device inference (`http://localhost:11434`).
  - **Autonomous Quantitative Rule Engine:** Built-in quantitative analyzer requiring zero external API keys.
- **On-Demand Health Testing (`/api/agent/provider/ping`):**
  - Sends a lightweight 1-token probe **only when the user selects or tests a provider** in the Settings Modal.
  - Measures roundtrip latency in milliseconds (`🟢 LIVE (42ms)` or `🔴 DOWN`).
  - **Strictly avoids background polling loops** to preserve user rate limits and token quotas.
- **Automatic Failover:**
  - If a primary cloud provider encounters a rate limit (HTTP 429) or connection error, the syndicate automatically fails over to the local Ollama instance or autonomous quantitative rule engine.

---

## 💼 Institutional Paper Trading Environment

- **Clean Baseline:** Initialized with **$10,000.00 USD cash** and **0 initial positions**.
- **TradingAgents Risk Desk Analytics:**
  - **Win Rate %** (Closed trades)
  - **Profit Factor** (Gross profit / Gross loss)
  - **Max Concentration Cap** (Strict 25% single-stock capital ceiling)
  - **Cash Allocation %** & **Invested Ratio %**
  - **Equity Trajectory Curve:** Real-time canvas tracking marked-to-market portfolio value.
- **Order Pad:** Market and Limit orders with Stop-Loss & Take-Profit brackets, plus 1% ($100), 2% ($200), 10% ($1K), and 25% ($2.5K) position-sizing chips.
- **Chat-Based Trade Execution:** Natural language trade commands (e.g., `Buy 10 shares of NVDA`, `Sell 5 AAPL`) update the ledger immediately.

---

## 🥊 TradingAgents Syndicate & FinGPT Intelligence

- **Adversarial Syndicate Debate:**
  - 🐂 **Bullish Researcher:** Momentum catalysts, technical breakouts, and volume structure.
  - 🐻 **Bearish Risk Analyst:** Multiples compression, resistance hurdles, and macro risks.
  - 🛡️ **Chief Risk Officer (CRO):** Kelly Criterion & 2% account risk sizing ($200 max risk) on the $10,000 account.
  - ⚖️ **Synthesized Trader Verdict:** Conviction score and recommended execution.
- **FinGPT Morning Desk Intelligence Brief:**
  - Macroeconomic regime classification (`RISK-ON GROWTH EXPANSION`, `DEFENSIVE / INVERTED YIELD CURVE`).
  - High-conviction S&P 500 setups and sector risk alerts.

---

## 🖥️ Standalone Terminal CLI (`terminal_trader.py`)

Run the full CLI terminal client in your shell:

```bash
# View candlestick chart & indicators for any S&P 500 ticker
python terminal_trader.py NVDA

# Run interactive trading agent chat REPL
python terminal_trader.py --chat

# View paper trading portfolio status
python terminal_trader.py --portfolio
```

---

## 🚀 Installation & Quick Start

```bash
# 1. Clone repository
git clone https://github.com/sunny-diwa/AdversarialIQ.git
cd AdversarialIQ

# 2. Setup virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run the web server
python server.py
```

Open **`http://localhost:8080`** in your browser.

### Keyboard Shortcuts
- `<F1>`: Market Pulse Homepage & S&P 500 Movers
- `<F2>`: Multi-Agent Quantitative Trader Desk
- `<F3>`: Company Dashboard & Multi-Layer Institutional Dock
- `<F4>`: Candlestick Terminal & Indicator Suite
- `<F5>`: Paper Trading Portfolio Ledger ($10K Base)
- `<F6>`: S&P 500 Multi-Indicator Scanner
