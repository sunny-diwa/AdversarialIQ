# S&P 500 AI Quantitative Trader & Bloomberg Terminal

An institutional-grade trading terminal, live technical scanner, and conversational AI trader desk built specifically for S&P 500 equities.

---

## Architecture & Features

### 1. Market Homepage
- **Macro Market Benchmarks:** Streaming real-time quotes for S&P 500 (`^GSPC`), Nasdaq 100 (`^IXIC`), Dow Jones (`^DJI`), and the VIX Volatility Index (`^VIX`).
- **Real-Time S&P 500 Movers:**
  - **Highest Gainers:** Top percentage gainers with real-time quotes and quick action links.
  - **Highest Losers:** Top percentage losers with instant access to technicals.
  - **Most Active / Momentum:** High-volatility equities with active technical setups.
- **11 GICS Sector Heatmap:** Constituent counts, sector weights, and industry breakdown.

### 2. Conversational Trader Agent & Multi-Agent Syndicate (TradingAgents & FinRobot Model)
- **Model Providers:**
  - **Groq Cloud API:** High-speed inference using Llama 3.3 70B, Llama 3.1 8B, and Mixtral 8x7B.
  - **Ollama Local:** Offline on-device inference via local models.
  - **Autonomous Quantitative Rule Engine:** Algorithmic rule-based analyzer that functions with zero external API keys.
- **Multi-Persona Syndicate Debate:**
  - 🐂 **Bullish Researcher:** Momentum catalysts, technical breakouts, and volume structure.
  - 🐻 **Bearish Risk Analyst:** Multiples compression, resistance hurdles, and macro risks.
  - 🛡️ **Chief Risk Officer (CRO):** Kelly Criterion & 2% account sizing on the $10,000 capital baseline.
  - ⚖️ **Synthesized Trader Verdict:** Conviction score and execution recommendations.
- **FinGPT Morning Desk Intelligence Brief:** Daily regime analysis, high-conviction S&P 500 setups, and risk guardrails.
- **Disciplined Paper Trading Engine:**
  - **Starting Capital:** **$10,000.00 USD** with **0 initial positions**.
  - **Order Types:** Market and Limit orders with attached Stop-Loss & Take-Profit brackets.
  - **Risk Metrics Desk:** Live Win Rate %, Profit Factor, Max Concentration % (25% cap), Cash Allocation ratio, and Equity Trajectory curve.
  - **Execution Logging:** Intent parser capable of executing virtual trades (e.g. `Buy 10 shares of NVDA`) directly into the ledger with agent rationale.

### 3. Comprehensive Company Overview (Stock Page)
- **Complete Fundamentals on One Screen:**
  - Business profile, leadership, headquarters, and web domain.
  - Valuation multiples: Enterprise Value, Trailing P/E, Forward P/E, PEG, Price/Book, Price/Sales, EV/EBITDA.
  - Profitability and margins: Gross, Operating, and Net Profit margins, plus Return on Equity (ROE).
  - Balance sheet liquidity: Total Cash, Total Debt, Debt/Equity, and Free Cash Flow.
  - S&P 500 Same-Sector Peer Matrix with live comparison.
- **Integrated Side-by-Side Movers:** Real-time top gainers and losers accessible directly on the stock page for instant cross-ticker switching.

### 4. Interactive Stock Trading Terminal
- **Multi-Timeframe Candlestick Engine:** `1D`, `5D`, `1M`, `6M`, `1Y`, and `5Y`.
- **Technical Indicator Suite:**
  - Moving Averages: SMA 20, SMA 50, SMA 200.
  - Volatility Bands: Bollinger Bands (20, 2).
  - Oscillators: RSI (14) with overbought/oversold thresholds, MACD (12, 26, 9) histogram & signal line.
- **Trading Floor Desk:**
  - Actionable quant trade setups with recommended entry, 20-day support/stop-loss, and breakout target.
  - Interactive Paper Order Pad with immediate cost calculation and execution.
  - Embedded Terminal CLI console stream.

### 5. Standalone Terminal CLI (`terminal_trader.py`)
- Full CLI terminal client featuring ASCII candlesticks, technical indicator tables, live S&P 500 scanner, paper portfolio ledger, and interactive chat REPL.

---

## Installation & Setup

### Prerequisites
- Python 3.10+
- (Optional) Groq API Key or local Ollama instance

### Local Setup
```bash
# 1. Clone the repository
git clone <repository_url>
cd terminal

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. (Optional) Configure environment variables
cp .env.example .env

# 5. Start the web terminal server
python server.py
```
Open **`http://localhost:8080`** in any web browser.

### Docker Deployment
```bash
docker compose up -d
```

---

## CLI Terminal Usage

Run the standalone terminal interface directly from your command line:

```bash
# View candlestick chart & technicals for a ticker
python terminal_trader.py NVDA

# Run the live S&P 500 technical scanner
python terminal_trader.py --scan

# Check paper trading portfolio ledger
python terminal_trader.py --portfolio

# Launch the interactive AI Trader Agent REPL
python terminal_trader.py --chat
```

---

## API Endpoints Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/sp500/list` | Master list of all 503 S&P 500 constituents |
| `GET` | `/api/market/movers` | Cached top gainers, losers, and most active stocks |
| `GET` | `/api/benchmarks` | Real-time quotes for SPX, Dow, Nasdaq, VIX, Crude |
| `GET` | `/api/stock/{symbol}/quote` | Fast live quote and daily metrics |
| `GET` | `/api/stock/{symbol}/history` | Candlesticks with SMA, BB, RSI, and MACD |
| `GET` | `/api/stock/{symbol}/company` | Financial valuation, margins, balance sheet & peers |
| `GET` | `/api/scanner/run` | Multi-factor S&P 500 technical screener |
| `GET` | `/api/portfolio/get` | Paper trading portfolio and marked-to-market PnL |
| `POST` | `/api/portfolio/trade` | Route virtual BUY/SELL order |
| `POST` | `/api/portfolio/reset` | Reset paper trading account to $10,000 cash balance |
| `GET` | `/api/agent/debater` | TradingAgents syndicate debate (Bull vs Bear vs CRO) |
| `GET` | `/api/agent/briefing` | FinGPT daily desk intelligence note |
| `POST` | `/api/agent/chat` | AI Trader Agent conversational inference |
