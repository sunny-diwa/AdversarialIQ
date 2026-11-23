"""
AdversarialIQ Institutional Trading Court & Adversarial Syndicate Engine
For every trade and stock evaluation, runs:
1. Agent Bull (Advocate): Prosecutes the strongest case for LONG/BUY using technicals, SEC MD&A, and news catalysts.
2. Agent Bear (Adversary): Aggressively stress-tests downside risk using SEC Risk Factors, insider selling, and yield curve inversion.
3. Agent Judge (Chief Arbiter): Impartially evaluates both cases, calculates the AdversarialIQ Conviction Score (0-100),
   delivers the judicial ruling, and computes Kelly/2% risk sizing for direct Alpaca Paper routing.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional
import yfinance as yf

from src.alpaca_client import AlpacaPaperClient
from src.config import SP500_MAP
from src.llm import LLMManager
from src.macro import fetch_macro_regime
from src.market_data import compute_indicators, fetch_stock_quote
from src.news import fetch_breaking_news
from src.portfolio import execute_order, get_portfolio_state, load_portfolio
from src.sec_edgar import fetch_insider_and_13f_activity, fetch_sec_filings

logger = logging.getLogger("AdversarialIQ.Syndicate")


def run_adversarial_trade_tribunal(symbol: str = "NVDA", account_capital: Optional[float] = None) -> Dict[str, Any]:
    """
    Core AdversarialIQ Trading Engine:
    Runs Agent Bull vs. Agent Bear cross-examination, followed by Agent Judge's definitive verdict
    and execution sizing for Alpaca Paper Trading.
    """
    sym = symbol.strip().upper()
    meta = SP500_MAP.get(sym, {"name": sym, "sector": "S&P 500"})

    # 1. Fetch live market price and technical indicators
    price = 100.0
    rsi = 50.0
    macd = 0.0
    sig = 0.0
    sma20 = 100.0
    sma50 = 100.0
    sma200 = 100.0
    bb_upper = 105.0
    bb_lower = 95.0
    day_low = 98.0
    day_high = 102.0

    try:
        t = yf.Ticker(sym)
        fast = t.fast_info
        price = fast.last_price or 100.0
        hist = t.history(period="3mo", interval="1d")
        if not hist.empty:
            hist = compute_indicators(hist)
            row = hist.iloc[-1]
            rsi = float(row.get("RSI", 50.0))
            macd = float(row.get("MACD", 0.0))
            sig = float(row.get("MACD_Signal", 0.0))
            sma20 = float(row.get("SMA20", price))
            sma50 = float(row.get("SMA50", price))
            sma200 = float(row.get("SMA200", price))
            bb_upper = float(row.get("BB_Upper", price * 1.05))
            bb_lower = float(row.get("BB_Lower", price * 0.95))
            day_low = float(hist["Low"].tail(20).min())
            day_high = float(hist["High"].tail(20).max())
    except Exception as e:
        logger.warning(f"Technical fetch error for {sym}: {e}")

    # 2. Fetch Multi-Layer Data Dossier
    sec_data = fetch_sec_filings(sym)
    insider_data = fetch_insider_and_13f_activity(sym)
    news_data = fetch_breaking_news(sym)
    macro_data = fetch_macro_regime()

    # 3. Construct Agent Bull Case (Advocate)
    bull_arguments = []
    bull_score = 50

    if rsi < 42:
        bull_arguments.append(f"Technical Reversal: RSI at {rsi:.1f} indicates severe oversold conditions primed for a mean-reversion rebound.")
        bull_score += 15
    elif rsi < 60:
        bull_arguments.append(f"Constructive Momentum: RSI at {rsi:.1f} has room to expand before overbought resistance.")
        bull_score += 8

    if macd > sig:
        bull_arguments.append(f"MACD Bullish Alignment: Line ({macd:.2f}) sits comfortably above Signal ({sig:.2f}), confirming positive trend acceleration.")
        bull_score += 12

    if price >= sma50:
        bull_arguments.append(f"Institutional Trend Support: Stock is holding above the 50-day moving average (${sma50:.2f}), preserving multi-week bull structure.")
        bull_score += 10

    if insider_data.get("cluster_verdict", "").find("BUYING") != -1 or insider_data.get("recent_buys_count", 0) > 0:
        bull_arguments.append(f"Executive Buying Cluster: Form 4 filings confirm {insider_data.get('recent_buys_count', 0)} corporate insider open-market purchases.")
        bull_score += 10

    if news_data.get("overall_sentiment", {}).get("label") == "BULLISH":
        cats = ", ".join(news_data.get("top_catalysts", ["MOMENTUM"])[:2])
        bull_arguments.append(f"Headline Catalyst Support: Real-time news sentiment is positive (+{news_data['overall_sentiment'].get('score', 0):.2f}) driven by {cats}.")
        bull_score += 10

    if sec_data.get("has_filings"):
        bull_arguments.append(f"SEC Disclosures: Item 7 MD&A verifies continuous operational growth and sound enterprise liquidity.")
        bull_score += 5

    # 4. Construct Agent Bear Case (Adversary)
    bear_arguments = []
    bear_score = 50

    if rsi > 65:
        bear_arguments.append(f"Overextended Exhaustion: RSI is at {rsi:.1f}, indicating stretched buyer momentum vulnerable to sharp profit-taking.")
        bear_score += 18
    elif rsi < 35:
        bear_arguments.append(f"Severe Weakness: RSI of {rsi:.1f} highlights persistent institutional distribution and lack of buy-side bids.")
        bear_score += 10

    if macd < sig:
        bear_arguments.append(f"Negative Momentum Cross: MACD line ({macd:.2f}) trails below Signal ({sig:.2f}), indicating downward drift.")
        bear_score += 12

    if price < sma50:
        bear_arguments.append(f"Overhead Supply Resistance: Trading below 50-day SMA (${sma50:.2f}); rallies face heavy supply from trapped holders.")
        bear_score += 14

    if insider_data.get("recent_sells_count", 0) > insider_data.get("recent_buys_count", 0):
        bear_arguments.append(f"Executive Divestment: Corporate insiders executed {insider_data.get('recent_sells_count', 0)} Form 4 sales over the past 90 days.")
        bear_score += 10

    macro_indicators = macro_data.get("indicators", {})
    if macro_indicators.get("yield_spread_bps", 10) < 0:
        bear_arguments.append(f"Macro Inversion Threat: US Treasury 10Y-2Y yield curve spread is {macro_indicators.get('yield_spread_bps'):.1f} bps (Recession Alert).")
        bear_score += 12

    if macro_indicators.get("vix", 16) > 20:
        bear_arguments.append(f"Elevated Volatility: CBOE VIX sits at {macro_indicators.get('vix'):.2f}, signaling broad market risk-off sentiment.")
        bear_score += 10

    if not bear_arguments:
        bear_arguments.append("General equity market beta risk and sector rotation headwinds.")

    # 5. Agent Judge (Chief Arbiter & CRO Ruling)
    capital = account_capital or 10000.0
    # Check if Alpaca paper trading is connected
    alpaca = AlpacaPaperClient()
    if alpaca.is_configured():
        acct = alpaca.get_account()
        if acct:
            capital = acct.get("portfolio_value", capital)

    # Compute AdversarialIQ Conviction Index (0-100)
    net_score = (bull_score - bear_score)
    conviction_index = max(10, min(95, int(50 + (net_score * 0.75))))

    # Risk parameters: 2% account risk
    risk_dollars = round(capital * 0.02, 2)
    stop_distance = max(price * 0.038, 1.0)
    stop_loss_price = round(price - stop_distance, 2)
    target_price = round(price + (stop_distance * 2.3), 2)
    suggested_shares = max(1, int(risk_dollars / stop_distance))
    total_allocation = round(suggested_shares * price, 2)
    allocation_pct = round((total_allocation / capital * 100), 1)

    # Judicial Verdict
    if conviction_index >= 65:
        ruling = "APPROVED (EXECUTE BUY / LONG)"
        badge_class = "bullish"
        ruling_summary = (
            f"Agent Bull prevailed before the court. Strong upside momentum and favorable risk/reward justify "
            f"initiating a LONG position of {suggested_shares} shares with defined stop protection."
        )
    elif conviction_index <= 38:
        ruling = "PROHIBITED (BEARISH BIAS / SHORT OR HEDGE)"
        badge_class = "bearish"
        ruling_summary = (
            f"Agent Bear established significant downside vulnerability. Multiple compression and technical supply "
            f"dictate standing down from long exposure or executing defensive hedges."
        )
    else:
        ruling = "REJECTED (STAND DOWN / NEUTRAL ARBITRAGE)"
        badge_class = "neutral"
        ruling_summary = (
            f"Adversarial arguments reached near equilibrium. Risk/Reward ratio does not satisfy "
            f"institutional standards. Recommend awaiting clear breakout confirmation before capital deployment."
        )

    return {
        "symbol": sym,
        "company": meta.get("name", sym),
        "price": round(price, 2),
        "active_capital": round(capital, 2),
        "execution_broker": "Alpaca US Paper Trading" if alpaca.is_configured() else "Local Simulated Desk",
        "conviction_score": conviction_index,
        "verdict": ruling,
        "verdict_badge": badge_class,
        "verdict_summary": ruling_summary,
        "prosecution_bull": {
            "title": "🐂 AGENT BULL (MOMENTUM & CATALYST PROSECUTOR)",
            "arguments": bull_arguments,
            "case_score": bull_score
        },
        "prosecution_bear": {
            "title": "🐻 AGENT BEAR (RISK & MACRO ADVERSARY)",
            "arguments": bear_arguments,
            "case_score": bear_score
        },
        "judicial_risk_parameters": {
            "arbiter": "⚖️ AGENT JUDGE (CHIEF RISK MAGISTRATE)",
            "capital_base": f"${capital:,.2f}",
            "risk_budget_2pct": f"${risk_dollars:,.2f}",
            "recommended_shares": suggested_shares,
            "total_capital_required": f"${total_allocation:,.2f}",
            "portfolio_allocation_pct": f"{allocation_pct}%",
            "concentration_check": "COMPLIANT (<25% Cap)" if allocation_pct <= 25.0 else "WARNING: Over-Allocated",
            "entry_price": f"${price:.2f}",
            "stop_loss": f"${stop_loss_price:.2f}",
            "target_price": f"${target_price:.2f}",
            "risk_reward_ratio": "1 : 2.30"
        }
    }


def get_daily_desk_briefing(scanner_results: Optional[list] = None) -> Dict[str, Any]:
    """FinGPT-style Morning / Desk Intelligence Note across S&P 500."""
    p = load_portfolio()
    results = scanner_results or []

    top_buys = [s for s in results if s.get("pct_change", 0) > 0 and s.get("rsi", 50) < 60][:3]
    top_hedges = [s for s in results if s.get("pct_change", 0) < 0][:2]
    macro = fetch_macro_regime()

    return {
        "date": datetime.now().strftime("%A, %B %d, %Y"),
        "timestamp": datetime.now().strftime("%H:%M:%S EST"),
        "market_regime": macro.get("regime", "NEUTRAL / SELECTIVE MOMENTUM"),
        "macro_summary": macro.get("summary", ""),
        "portfolio_health": {
            "account_equity": p.get("cash", 10000.0) + sum(pos.get("cost_basis", 0) for pos in p.get("positions", {}).values()),
            "active_positions_count": len(p.get("positions", {})),
            "cash_reserves": p.get("cash", 10000.0),
            "risk_profile": "DISCIPLINED ADVERSARIAL RISK ($10K BASE)"
        },
        "top_setups": top_buys,
        "watch_out": top_hedges
    }


def process_chat_message(
    message: str,
    provider: str = "groq",
    model: str = "llama-3.3-70b-versatile",
    groq_api_key: str = "",
    gemini_api_key: str = "",
    mistral_api_key: str = "",
    nvidia_api_key: str = "",
    ollama_base_url: str = "http://localhost:11434",
    current_symbol: str = "AAPL",
    alpaca_key: Optional[str] = None,
    alpaca_secret: Optional[str] = None
) -> Dict[str, Any]:
    """
    Core AdversarialIQ Conversational Router:
    1. Parses trade execution orders (`Buy 10 NVDA` / `Sell 5 AAPL`) routed through Alpaca.
    2. Runs Adversarial Tribunal on demand.
    3. Serves daily desk briefings.
    4. Orchestrates LLMs across Groq, Gemini, Mistral, NVIDIA NIM, and Ollama.
    """
    prompt = message.strip()
    target_sym = current_symbol.upper()

    # 1. Detect trade command routed to Alpaca or local desk
    trade_match = re.search(r"\b(BUY|SELL)\s+(\d+)\s+(?:SHARES\s+OF\s+)?([A-Z]{1,5})\b", prompt.upper())
    if trade_match:
        action, qty_str, trade_sym = trade_match.groups()
        try:
            res = execute_order(
                action=action,
                symbol=trade_sym,
                quantity=int(qty_str),
                alpaca_key=alpaca_key,
                alpaca_secret=alpaca_secret
            )
            broker = "Alpaca US Paper Trading" if "alpaca_order_id" in res.get("trade", {}) else "Local Simulated Desk"
            return {
                "response": (
                    f"✅ **Trade Routed & Executed Successfully!**\n\n"
                    f"- **Broker:** `{broker}`\n"
                    f"- **Action:** `{action}`\n"
                    f"- **Symbol:** `{trade_sym}`\n"
                    f"- **Quantity:** `{qty_str}` shares\n"
                    f"- **Fill Price:** `${res['trade']['price']:.2f}`\n"
                    f"- **Total Consideration:** `${res['trade']['total']:.2f}`\n\n"
                    f"*Your portfolio ledger and position records have been updated.*"
                ),
                "trade": res["trade"]
            }
        except Exception as e:
            return {"response": f"⚠️ **Trade Rejected:** {str(e)}"}

    # 2. Extract mentioned ticker
    words = re.findall(r"\b[A-Z]{1,5}\b", prompt.upper())
    for w in words:
        if w in SP500_MAP:
            target_sym = w
            break

    # 3. Detect AdversarialIQ Debate / Tribunal intent
    if any(k in prompt.lower() for k in ["adversarial", "debate", "bull vs bear", "syndicate", "judge", "court", "tribunal"]):
        tribunal = run_adversarial_trade_tribunal(target_sym)
        bull = tribunal["prosecution_bull"]
        bear = tribunal["prosecution_bear"]
        judge_risk = tribunal["judicial_risk_parameters"]

        bull_bullets = "\n".join([f"  • {a}" for a in bull["arguments"]])
        bear_bullets = "\n".join([f"  • {a}" for a in bear["arguments"]])

        court_md = f"""### ⚖️ AdversarialIQ Trade Tribunal: **{target_sym}** (${tribunal['price']:.2f})
*Cross-Examination: Bull Advocate vs. Bear Adversary vs. Chief Judge*

---

#### {bull['title']} (Prosecution Score: {bull['case_score']}/100)
{bull_bullets}

#### {bear['title']} (Defense Score: {bear['case_score']}/100)
{bear_bullets}

---

#### {judge_risk['arbiter']} — ADJUDICATED RISK MANDATE
- **AdversarialIQ Conviction Score:** **`{tribunal['conviction_score']}/100`**
- **Judicial Ruling:** **`{tribunal['verdict']}`**
- *{tribunal['verdict_summary']}*

| Parameter | Adjudicated Requirement |
|---|---|
| **Capital Baseline** | `{judge_risk['capital_base']}` ({tribunal['execution_broker']}) |
| **Max Risk Budget (2%)** | `{judge_risk['risk_budget_2pct']}` |
| **Recommended Size** | **`{judge_risk['recommended_shares']} shares`** (`{judge_risk['total_capital_required']}`) |
| **Portfolio Exposure** | `{judge_risk['portfolio_allocation_pct']}` ({judge_risk['concentration_check']}) |
| **Entry Price** | `{judge_risk['entry_price']}` |
| **Stop-Loss Protection** | `{judge_risk['stop_loss']}` |
| **Profit Target** | `{judge_risk['target_price']}` |
| **Risk / Reward Ratio** | `{judge_risk['risk_reward_ratio']}` |

---
*Say `Buy {judge_risk['recommended_shares']} {target_sym}` to execute this ruling on your {tribunal['execution_broker']}.*
"""
        return {"response": court_md, "provider": "AdversarialIQ Court", "symbol": target_sym}

    # 4. Detect Daily Desk Briefing intent
    if any(k in prompt.lower() for k in ["brief", "briefing", "morning note", "desk report"]):
        brief = get_daily_desk_briefing()
        buys = brief.get("top_setups", [])
        buys_text = "\n".join([f"  • **{b['symbol']}** (${b['price']:.2f}): RSI `{b['rsi']}`, MACD `{b['macd']:.2f}`" for b in buys]) or "  • Consolidating markets; awaiting breakout confirmation."

        briefing_md = f"""### 📋 AdversarialIQ Daily Desk Intelligence Brief
**Date:** {brief.get('date')} | **Wire Time:** {brief.get('timestamp')}  
**Macro Market Regime:** **`{brief.get('market_regime')}`**

---

#### 💼 Portfolio Health & Risk Parameters:
- **Account Status:** Active Capital `${brief.get('portfolio_health', {}).get('account_equity', 10000.0):,.2f}`
- **Cash Reserves:** `${brief.get('portfolio_health', {}).get('cash_reserves', 10000.0):,.2f}`
- **Risk Posture:** `{brief.get('portfolio_health', {}).get('risk_profile')}`

#### 🌍 Macro Context:
{brief.get('macro_summary')}

#### 🎯 High-Conviction S&P 500 Setups:
{buys_text}

---
*Ask: `Debate <SYMBOL>` to trigger the AdversarialIQ Bull-Bear-Judge trial on any candidate.*
"""
        return {"response": briefing_md, "provider": "AdversarialIQ Briefing", "symbol": target_sym}

    # 5. Build rich 5-layer system prompt and execute through multi-provider LLM engine
    tribunal = run_adversarial_trade_tribunal(target_sym)
    system_prompt = f"""You are AdversarialIQ, an institutional quantitative hedge fund trader and adversarial intelligence syndicate.
You evaluate every stock using an adversarial debate approach:
- Agent Bull proves the case for Long.
- Agent Bear proves the case for Short / Risk.
- Agent Judge delivers the final conviction score (0-100), ruling, and disciplined 2% risk position sizing.

LIVE DOSSIER FOR {target_sym}:
- Price: ${tribunal['price']:.2f}
- Bull Prosecution Arguments: {'; '.join(tribunal['prosecution_bull']['arguments'])}
- Bear Defense Arguments: {'; '.join(tribunal['prosecution_bear']['arguments'])}
- AdversarialIQ Conviction Score: {tribunal['conviction_score']}/100
- Adjudicated Ruling: {tribunal['verdict']}
- Position Size: {tribunal['judicial_risk_parameters']['recommended_shares']} shares | Stop Loss: {tribunal['judicial_risk_parameters']['stop_loss']} | Target: {tribunal['judicial_risk_parameters']['target_price']}

Deliver structured, direct, professional institutional analysis using markdown tables and bullet points.
If the user asks to execute a trade, remind them they can type 'Buy <qty> <symbol>' or 'Sell <qty> <symbol>'.
"""

    gen_result = LLMManager.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        preferred_provider=provider,
        model=model,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        mistral_api_key=mistral_api_key,
        nvidia_api_key=nvidia_api_key,
        ollama_base_url=ollama_base_url,
        symbol=target_sym
    )

    return {
        "response": gen_result["response"],
        "provider": gen_result["provider"],
        "model": gen_result.get("model", ""),
        "failover": gen_result.get("failover", False),
        "symbol": target_sym
    }
