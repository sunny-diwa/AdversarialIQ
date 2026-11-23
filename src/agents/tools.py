"""
AdversarialIQ Institutional Tool Registry & Execution Engine
Provides callable financial tools with standardized schemas and execution dispatchers:
1. get_company_news: Real-time Finnhub/RSS news, catalyst classification, and sentiment scores.
2. get_stock_technicals: RSI(14), MACD, ATR(14), SMA(20/50/200), Bollinger Bands, and volatility.
3. get_sec_filings: SEC EDGAR 10-K, 10-Q, 8-K filings, MD&A analysis, and Item 1A risk factors.
4. get_insider_activity: Form 4 executive buy/sell clusters and 13F institutional ownership.
5. get_macro_regime: FRED interest rates, 10Y-2Y yield curve spread, CPI inflation, and VIX.
6. get_earnings_calendar: 48-hour earnings blackout window and announcement countdown.
7. run_backtest: 5-year quantitative strategy backtest with Sharpe, Sortino, Alpha, and Max Drawdown.
8. run_adversarial_tribunal: Cross-examination between Agent Bull, Agent Bear, and Chief Judge.
9. execute_paper_trade: Deterministic Non-LLM Risk Guardrail execution with mandatory bracket orders.
10. get_portfolio_status: Live equity, cash balance, active positions, and win rate.
"""

import json
import logging
from typing import Any, Callable, Dict, List, Optional

from src.core.config import SP500_MAP
from src.data.calendar import fetch_earnings_calendar
from src.data.macro import fetch_macro_regime
from src.data.market import fetch_stock_quote, fetch_stock_technicals
from src.data.news import fetch_breaking_news
from src.data.sec_edgar import fetch_insider_and_13f_activity, fetch_sec_filings
from src.execution.portfolio import execute_order, get_portfolio_state

logger = logging.getLogger("ToolRegistry")


# -----------------------------------------------------------------------------
# Tool Implementations
# -----------------------------------------------------------------------------

def tool_get_company_news(symbol: str, limit: int = 5) -> Dict[str, Any]:
    """Fetches real-time company news, headlines, sentiment analysis, and catalyst tags."""
    sym = symbol.strip().upper()
    data = fetch_breaking_news(sym)
    articles = data.get("articles", [])[:limit]
    sentiment = data.get("overall_sentiment", {})
    score = sentiment.get("score", 0.0)
    label = sentiment.get("label", "NEUTRAL")
    catalysts = data.get("top_catalysts", ["GENERAL_NEWS"])

    icon = "🟢" if label == "BULLISH" else ("🔴" if label == "BEARISH" else "⚪")

    lines = [
        f"### 📰 Breaking News & Catalyst Intelligence: **{sym}**",
        f"**Aggregate Sentiment:** {icon} **`{label}`** (`{score:+.2f}`) | **Top Catalysts:** {', '.join([f'`{c}`' for c in catalysts])} | **Articles Analyzed:** `{data.get('article_count', len(articles))}`",
        "",
        "---",
        ""
    ]

    if articles:
        for i, a in enumerate(articles, 1):
            sent_icon = "🟢" if a.get("sentiment") == "BULLISH" else ("🔴" if a.get("sentiment") == "BEARISH" else "⚪")
            cat_str = " ".join([f"`{c}`" for c in a.get("catalysts", [])[:2]])
            lines.append(f"#### {i}. {a.get('title')}")
            lines.append(f"- **Source:** `{a.get('source', 'News Wire')}` | **Published:** `{a.get('timestamp')}` | **Sentiment:** {sent_icon} `{a.get('sentiment')}` ({a.get('sentiment_score', 0):+.2f})")
            if cat_str:
                lines.append(f"- **Tagged Catalysts:** {cat_str}")
            if a.get("summary"):
                lines.append(f"> *{a.get('summary')}*")
            lines.append("")
    else:
        lines.append(f"*No breaking headlines detected for {sym} within the past 7 days. Market is operating on technical consensus.*")

    return {
        "tool": "get_company_news",
        "symbol": sym,
        "overall_sentiment": sentiment,
        "top_catalysts": catalysts,
        "article_count": len(articles),
        "articles": articles,
        "formatted_markdown": "\n".join(lines)
    }


def tool_get_stock_technicals(symbol: str) -> Dict[str, Any]:
    """Fetches calculated technicals: RSI, MACD, 14-day ATR, moving averages, and Bollinger Bands."""
    sym = symbol.strip().upper()
    tech = fetch_stock_technicals(sym)

    price = tech.get("price", 0.0)
    rsi = tech.get("rsi", 50.0)
    macd = tech.get("macd", 0.0)
    signal = tech.get("macd_signal", 0.0)
    hist = tech.get("macd_hist", 0.0)
    atr = tech.get("atr_14", 0.0)
    sma20 = tech.get("sma20", 0.0)
    sma50 = tech.get("sma50", 0.0)
    sma200 = tech.get("sma200", 0.0)
    vol = tech.get("volatility_20d_pct", 0.0)
    bb_u = tech.get("bb_upper", 0.0)
    bb_l = tech.get("bb_lower", 0.0)

    # Momentum signals
    rsi_sig = "🔴 OVERBOUGHT" if rsi > 70 else ("🟢 OVERSOLD" if rsi < 30 else "⚪ NEUTRAL")
    macd_sig = "🟢 BULLISH CROSSOVER" if macd > signal else "🔴 BEARISH CROSSOVER"
    trend_sig = "🟢 BULLISH TREND (Above SMA50)" if price >= sma50 else "🔴 BEARISH TREND (Below SMA50)"

    md = f"""### 📊 Technical Indicators & Quantitative Setup: **{sym}** (${price:.2f})
*Institutional Momentum, Trend, and Volatility Metrics*

---

| Metric / Indicator | Value | Signal / Assessment |
|:---|:---|:---|
| **Current Price** | **${price:.2f}** | {trend_sig} |
| **RSI (14-Day)** | **`{rsi:.1f}`** | {rsi_sig} |
| **MACD (12, 26, 9)** | **`{macd:.2f}`** (Signal: `{signal:.2f}`) | {macd_sig} (Hist: `{hist:+.2f}`) |
| **14-Day ATR (Volatility)** | **`${atr:.2f}`** | Stop Distance: `${atr * 1.5:.2f}` (1.5x ATR) |
| **20-Day Annualized Vol** | **`{vol:.1f}%`** | Volatility Bracket |
| **SMA 20 / 50 / 200** | `${sma20:.2f}` / `${sma50:.2f}` / `${sma200:.2f}` | Trend Structure |
| **Bollinger Bands** | Upper: `${bb_u:.2f}` / Lower: `${bb_l:.2f}` | Volatility Envelope |

---
*Tip: Say `Debate {sym}` to pit Agent Bull against Agent Bear with these metrics.*"""

    return {
        "tool": "get_stock_technicals",
        "symbol": sym,
        "price": price,
        "rsi": rsi,
        "macd": macd,
        "macd_signal": signal,
        "atr_14": atr,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "volatility_20d_pct": vol,
        "formatted_markdown": md
    }


def tool_get_sec_filings(symbol: str) -> Dict[str, Any]:
    """Fetches real SEC EDGAR 10-K, 10-Q, 8-K filings with MD&A summary and risk factors."""
    sym = symbol.strip().upper()
    data = fetch_sec_filings(sym)

    filings = data.get("filings", [])
    mda = data.get("mda_summary", "Standard financial disclosure on SEC EDGAR.")
    risks = data.get("risk_factors", [])

    filings_table = "\n".join([
        f"| `{f.get('form')}` | `{f.get('filing_date')}` | [{f.get('description', 'Filing Report')}]({f.get('url', '#')}) |"
        for f in filings[:5]
    ]) or "| — | No recent filings | — |"

    risks_list = "\n".join([f"- ⚠️ {r}" for r in risks[:4]]) if risks else "- Standard competitive and regulatory risk profile."

    md = f"""### 🏛️ SEC EDGAR Regulatory Filings & 10-K Audit: **{sym}**
*Direct access to official Securities and Exchange Commission records*

---

#### 📋 Recent SEC Filings:
| Form | Filing Date | Document Access |
|:---|:---|:---|
{filings_table}

#### 🔍 Item 7: Management's Discussion & Analysis (MD&A):
> {mda}

#### ⚠️ Item 1A: Disclosed Principal Risk Factors:
{risks_list}

---
*SEC EDGAR Fair Access User-Agent compliant.*"""

    return {
        "tool": "get_sec_filings",
        "symbol": sym,
        "filings": filings,
        "mda_summary": mda,
        "risk_factors": risks,
        "formatted_markdown": md
    }


def tool_get_insider_activity(symbol: str) -> Dict[str, Any]:
    """Fetches Form 4 insider transactions, cluster verdicts, and 13F institutional ownership."""
    sym = symbol.strip().upper()
    data = fetch_insider_and_13f_activity(sym)

    verdict = data.get("cluster_verdict", "NEUTRAL")
    buys = data.get("recent_buys_count", 0)
    sells = data.get("recent_sells_count", 0)
    recent = data.get("recent_transactions", [])
    inst = data.get("institutional_holders", [])

    tx_table = "\n".join([
        f"| {t.get('insider_name', 'Insider')} | `{t.get('transaction_type')}` | `{t.get('shares', 0):,}` shares | `${t.get('value', 0):,.2f}` | `{t.get('date')}` |"
        for t in recent[:5]
    ]) or "| — | No recent Form 4 clusters | — | — | — |"

    inst_table = "\n".join([
        f"| {h.get('holder')} | `{h.get('shares', 0):,}` shares | `{h.get('pct_out', 0):.2f}%` |"
        for h in inst[:4]
    ]) or "| — | Institutional data unavailable | — |"

    v_icon = "🟢" if "BUYING" in verdict else ("🔴" if "SELLING" in verdict else "⚪")

    md = f"""### 🐋 Form 4 Insider Clusters & 13F Ownership: **{sym}**
*C-Suite Purchases, Executive Dispositions, and Institutional Whale Holdings*

---

- **Cluster Signal Verdict:** {v_icon} **`{verdict}`**
- **Recent Executive Buying:** **`{buys}` filings**
- **Recent Executive Selling:** **`{sells}` filings**

#### 💼 Notable Form 4 Insider Transactions:
| Executive / Officer | Action | Shares | Value | Date |
|:---|:---|:---|:---|:---|
{tx_table}

#### 🏦 Top 13F Institutional Holders:
| Institutional Fund | Shares Held | Portfolio Stake |
|:---|:---|:---|
{inst_table}

---
*Form 4 and 13F filings are sourced from SEC EDGAR.*"""

    return {
        "tool": "get_insider_activity",
        "symbol": sym,
        "verdict": verdict,
        "buys_count": buys,
        "sells_count": sells,
        "recent_transactions": recent,
        "institutional_holders": inst,
        "formatted_markdown": md
    }


def tool_get_macro_regime() -> Dict[str, Any]:
    """Fetches macroeconomic indicators from Federal Reserve (FRED) and computes market regime."""
    data = fetch_macro_regime()
    regime = data.get("regime", "NEUTRAL")
    ind = data.get("indicators", {})

    dgs10 = ind.get("dgs10", 4.35)
    dgs2 = ind.get("dgs2", 4.20)
    spread = ind.get("yield_spread_bps", 15.0)
    vix = ind.get("vix", 16.5)
    cpi = ind.get("cpi_yoy_pct", 2.6)
    ff = ind.get("fed_funds_rate", 4.88)
    inverted = ind.get("yield_curve_inverted", False)

    curve_badge = "🔴 INVERTED (Recession Warning)" if inverted else "🟢 NORMAL SLOPING"
    r_icon = "🟢" if regime == "RISK_ON" else ("🔴" if regime == "RISK_OFF" else "🟡")

    md = f"""### 🌍 Federal Reserve (FRED) Macro Regime Context
*Systemic Macro Factors & Multi-Asset Volatility Environment*

---

- **Current Market Regime:** {r_icon} **`{regime}`**
- **Yield Curve Health:** **{curve_badge}**

| Macro Factor | Current Level | Regime Assessment |
|:---|:---|:---|
| **10-Year Treasury Yield (DGS10)** | **`{dgs10:.2f}%`** | Long-term discount benchmark |
| **2-Year Treasury Yield (DGS2)** | **`{dgs2:.2f}%`** | Fed policy expectations |
| **10Y - 2Y Yield Spread** | **`{spread:+.1f} bps`** | {'Inverted' if inverted else 'Positive slope'} |
| **CBOE Volatility Index (VIX)** | **`{vix:.2f}`** | {'Elevated market fear' if vix > 20 else 'Complacent / Bullish regime'} |
| **CPI Inflation (YoY)** | **`{cpi:.1f}%`** | Consumer price pressure |
| **Effective Fed Funds Rate** | **`{ff:.2f}%`** | Federal Reserve policy target |

---
*Data refreshed from Federal Reserve Economic Data (FRED) API.*"""

    return {
        "tool": "get_macro_regime",
        "regime": regime,
        "indicators": ind,
        "formatted_markdown": md
    }


def tool_get_earnings_calendar(symbol: str) -> Dict[str, Any]:
    """Fetches 48-hour earnings blackout window and announcement calendar."""
    sym = symbol.strip().upper()
    cal = fetch_earnings_calendar(sym)

    status = cal.get("blackout_status", "CLEAR")
    date_display = cal.get("earnings_date") or "No immediate announcement detected"
    hours_display = f"{cal.get('hours_to_earnings')} hours" if cal.get("hours_to_earnings") is not None else "N/A"
    badge = "🟢 CLEAR" if cal.get("action") == "CLEAR" else ("🟡 WARNING (50% SIZING)" if cal.get("action") == "HALVE" else "🔴 VETO BLACKOUT")

    md = f"""### 📅 48-Hour Earnings Blackout Window: **{sym}**
*Binary Event Protection Gate*

---

- **Status:** **`{status}`** ({badge})
- **Scheduled Earnings Date:** **`{date_display}`**
- **Countdown to Announcement:** **`{hours_display}`**
- **Risk Gate Action:** **`{cal.get('action', 'CLEAR')}`** (Size Multiplier: `{cal.get('size_multiplier', 1.0)}x`)

#### 📌 Risk Manager Guidance:
> *{cal.get('reason', 'Normal trading permitted.')}*"""

    return {
        "tool": "get_earnings_calendar",
        "symbol": sym,
        "blackout_status": status,
        "action": cal.get("action", "CLEAR"),
        "hours_to_earnings": cal.get("hours_to_earnings"),
        "formatted_markdown": md
    }


def tool_run_backtest(symbol: str, strategy: str) -> Dict[str, Any]:
    """Synthesizes and runs a 5-year quantitative strategy backtest on historical daily bars."""
    from src.backtest import StrategyGenerator
    sym = symbol.strip().upper()
    bt = StrategyGenerator.synthesize_and_run(strategy_prompt=strategy, symbol=sym)

    ret_col = "🟢" if bt["total_return_pct"] >= 0 else "🔴"
    bench_col = "🟢" if bt["benchmark_return_pct"] >= 0 else "🔴"
    alpha_col = "🟢" if bt["alpha_pct"] >= 0 else "🔴"

    md = f"""### ⚡ 5-Year Quantitative Backtest Engine: **{bt['symbol']}**
**Horizon:** `{bt['period']}` | **Starting Capital:** `${bt['initial_capital']:,.2f}` | **Model:** `{bt.get('model_used', 'LLM')}`

---

#### 📊 Performance vs. Benchmark:
| Metric | Strategy | Benchmark | Alpha / Edge |
|:---|:---|:---|:---|
| **Total Return** | **{ret_col} {bt['total_return_pct']:+.2f}%** | {bench_col} {bt['benchmark_return_pct']:+.2f}% | {alpha_col} **{bt['alpha_pct']:+.2f}%** |
| **Final Equity** | **${bt['final_equity']:,.2f}** | — | — |
| **Sharpe Ratio** | **`{bt['sharpe_ratio']}`** | — | *(Assumes 4.0% RFR)* |
| **Sortino Ratio** | **`{bt['sortino_ratio']}`** | — | *(Downside Risk Adjusted)* |
| **Max Drawdown** | **`{bt['max_drawdown_pct']:.2f}%`** | — | Peak-to-Trough |

#### 🎯 Trade Statistics:
- **Total Trades:** `{bt['total_trades']}` (Wins: **`{bt['winning_trades']}`** | Losses: **`{bt['losing_trades']}`**)
- **Win Rate:** **`{bt['win_rate_pct']}%`** | **Profit Factor:** **`{bt['profit_factor']}`**"""

    return {
        "tool": "run_backtest",
        "symbol": sym,
        "backtest": bt,
        "formatted_markdown": md
    }


def tool_run_adversarial_tribunal(symbol: str) -> Dict[str, Any]:
    """Runs the full Bull vs Bear adversarial debate and judicial ruling."""
    from src.agents.tribunal import run_adversarial_trade_tribunal
    sym = symbol.strip().upper()
    tribunal = run_adversarial_trade_tribunal(sym)
    bull = tribunal["prosecution_bull"]
    bear = tribunal["prosecution_bear"]
    judge_risk = tribunal["judicial_risk_parameters"]

    bull_bullets = "\n".join([f"  • {a}" for a in bull.get("arguments", [])])
    bear_bullets = "\n".join([f"  • {a}" for a in bear.get("arguments", [])])

    md = f"""### ⚖️ AdversarialIQ Trade Tribunal: **{sym}** (${tribunal['price']:.2f})
*Cross-Examination: Bull Advocate vs. Bear Adversary vs. Chief Judge*

---

#### {bull.get('title', '🐂 AGENT BULL')} (Score: {bull.get('case_score', 50)}/100)
{bull_bullets}

#### {bear.get('title', '🐻 AGENT BEAR')} (Score: {bear.get('case_score', 50)}/100)
{bear_bullets}

---

#### {judge_risk['arbiter']} — ADJUDICATED RISK MANDATE
- **Conviction Score:** **`{tribunal['conviction_score']}/100`**
- **Judicial Ruling:** **`{tribunal['verdict']}`**
- *{tribunal['verdict_summary']}*

| Parameter | Mandate |
|:---|:---|
| **Recommended Size** | **`{judge_risk['recommended_shares']} shares`** ({judge_risk['total_capital_required']}) |
| **Stop-Loss** | `{judge_risk['stop_loss']}` |
| **Take-Profit** | `{judge_risk['take_profit']}` |
| **Risk / Reward** | `{judge_risk['risk_reward_ratio']}` |"""

    return {
        "tool": "run_adversarial_tribunal",
        "symbol": sym,
        "tribunal": tribunal,
        "formatted_markdown": md
    }


def tool_execute_paper_trade(symbol: str, action: str, quantity: int) -> Dict[str, Any]:
    """Executes paper trade on Alpaca or local desk with strict Non-LLM Risk Gate validation."""
    sym = symbol.strip().upper()
    act = action.strip().upper()
    res = execute_order(action=act, symbol=sym, quantity=int(quantity))
    trade = res.get("trade", {})
    bracket = trade.get("bracket", {})

    broker = "Alpaca US Paper Trading" if "alpaca_order_id" in trade else "Local Simulated Desk"

    md = f"""✅ **Paper Trade Executed!**
- **Broker:** `{broker}`
- **Action:** `{act}` {trade.get('quantity', quantity)} shares of **{sym}**
- **Fill Price:** `${trade.get('price', 0.0):.2f}` (Total: `${trade.get('total', 0.0):,.2f}`)
- **Mandatory Bracket Legs:** Stop-Loss `${bracket.get('stop_loss', 0.0):.2f}` | Take-Profit `${bracket.get('take_profit', 0.0):.2f}`"""

    return {
        "tool": "execute_paper_trade",
        "symbol": sym,
        "action": act,
        "trade": trade,
        "formatted_markdown": md
    }


def tool_get_portfolio_status() -> Dict[str, Any]:
    """Returns live paper portfolio equity, cash, positions, and win rate."""
    port = get_portfolio_state()
    equity = port.get("total_equity", 10000.0)
    cash = port.get("cash_balance", 10000.0)
    positions = port.get("positions", [])
    win_rate = port.get("win_rate_pct", 0.0)

    pos_rows = "\n".join([
        f"| **{p.get('symbol')}** | `{p.get('quantity')}` | `${p.get('avg_entry_price', 0.0):.2f}` | `${p.get('current_price', 0.0):.2f}` | `{p.get('unrealized_pnl_pct', 0.0):+.2f}%` |"
        for p in positions
    ]) or "| — | No open positions | — | — | — |"

    md = f"""### 💼 Paper Portfolio State
- **Total Portfolio Equity:** **`${equity:,.2f}`**
- **Cash Reserves:** **`${cash:,.2f}`**
- **Active Open Positions:** **`{len(positions)} / 5 max`**
- **Historical Win Rate:** **`{win_rate:.1f}%`**

| Symbol | Shares | Entry Price | Current Price | Unrealized P&L |
|:---|:---|:---|:---|:---|
{pos_rows}"""

    return {
        "tool": "get_portfolio_status",
        "portfolio": port,
        "formatted_markdown": md
    }


# -----------------------------------------------------------------------------
# Tool Registry Map & Dispatcher
# -----------------------------------------------------------------------------

AVAILABLE_TOOLS: Dict[str, Callable[..., Dict[str, Any]]] = {
    "get_company_news": tool_get_company_news,
    "get_stock_technicals": tool_get_stock_technicals,
    "get_sec_filings": tool_get_sec_filings,
    "get_insider_activity": tool_get_insider_activity,
    "get_macro_regime": tool_get_macro_regime,
    "get_earnings_calendar": tool_get_earnings_calendar,
    "run_backtest": tool_run_backtest,
    "run_adversarial_tribunal": tool_run_adversarial_tribunal,
    "execute_paper_trade": tool_execute_paper_trade,
    "get_portfolio_status": tool_get_portfolio_status,
}


TOOL_SCHEMAS: List[Dict[str, Any]] = [
    {
        "name": "get_company_news",
        "description": "Fetches real-time company news articles, headlines, sentiment analysis, and catalyst classification for an S&P 500 company.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The stock ticker symbol, e.g. AAPL, NVDA, TSLA"},
                "limit": {"type": "integer", "description": "Number of news articles to return (default 5)"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_stock_technicals",
        "description": "Calculates real-time technical indicators including RSI, MACD, 14-day ATR, moving averages (SMA 20, 50, 200), and Bollinger Bands.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The stock ticker symbol, e.g. AAPL, NVDA, MSFT"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_sec_filings",
        "description": "Fetches official SEC EDGAR 10-K, 10-Q, and 8-K filings with Item 7 MD&A analysis and Item 1A principal risk factors.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The stock ticker symbol, e.g. AAPL, NVDA, AMZN"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_insider_activity",
        "description": "Fetches Form 4 executive insider buying/selling clusters and 13F institutional whale ownership holdings from SEC EDGAR.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The stock ticker symbol, e.g. AAPL, NVDA, GOOGL"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "get_macro_regime",
        "description": "Fetches Federal Reserve (FRED) macroeconomic indicators including 10-Year and 2-Year Treasury yields, yield spread, CPI, VIX, and regime classification.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_earnings_calendar",
        "description": "Checks the 48-hour earnings blackout window, scheduled earnings announcement date, countdown, and sizing action.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The stock ticker symbol, e.g. AAPL, NVDA, TSLA"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "run_backtest",
        "description": "Synthesizes and runs a 5-year quantitative strategy backtest on historical daily bars with Sharpe, Sortino, Win Rate, and Alpha.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The stock ticker symbol, e.g. AAPL, NVDA, MSFT"},
                "strategy": {"type": "string", "description": "Natural language description of trading rules, e.g. 'Buy when RSI < 35, exit when RSI > 65'"}
            },
            "required": ["symbol", "strategy"]
        }
    },
    {
        "name": "run_adversarial_tribunal",
        "description": "Runs the full AdversarialIQ Tribunal: Bull Prosecution vs. Bear Defense vs. Chief Judge with ATR position sizing.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The stock ticker symbol, e.g. AAPL, NVDA, META"}
            },
            "required": ["symbol"]
        }
    },
    {
        "name": "execute_paper_trade",
        "description": "Executes a paper trade with deterministic Non-LLM Risk Guardrail sizing and mandatory bracket orders.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "The stock ticker symbol, e.g. AAPL, NVDA"},
                "action": {"type": "string", "enum": ["BUY", "SELL"], "description": "BUY or SELL"},
                "quantity": {"type": "integer", "description": "Number of shares"}
            },
            "required": ["symbol", "action", "quantity"]
        }
    },
    {
        "name": "get_portfolio_status",
        "description": "Fetches paper trading portfolio balance, cash reserves, open positions, and win rate.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
]


def execute_tool(name: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Safely dispatches and executes a tool from the registry with arguments.
    Returns standard structured payload with 'status', 'result', and 'formatted_markdown'.
    """
    func = AVAILABLE_TOOLS.get(name)
    if not func:
        return {
            "status": "ERROR",
            "error": f"Tool '{name}' not found in registry.",
            "available_tools": list(AVAILABLE_TOOLS.keys())
        }

    args = arguments or {}
    try:
        res = func(**args)
        return {
            "status": "SUCCESS",
            "tool": name,
            "arguments": args,
            "result": res,
            "formatted_markdown": res.get("formatted_markdown", "")
        }
    except Exception as e:
        logger.error(f"Error executing tool {name} with args {args}: {e}")
        return {
            "status": "ERROR",
            "tool": name,
            "arguments": args,
            "error": str(e)
        }
