"""
Institutional Multi-Agent Syndicate & Adversarial Trader Intelligence
Implements TradingAgents multi-persona adversarial debate (Bull Analyst vs Bear Risk Officer vs CRO),
FinGPT daily intelligence briefing, and synthesizes all 5 data layers:
Technicals + SEC EDGAR Filings + Insider/13F Activity + Breaking News Sentiment + Macro Regime.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, Optional
import yfinance as yf

from src.config import SP500_MAP
from src.llm import LLMManager
from src.macro import fetch_macro_regime
from src.market_data import compute_indicators, fetch_stock_quote
from src.news import fetch_breaking_news
from src.portfolio import execute_order, load_portfolio
from src.sec_edgar import fetch_insider_and_13f_activity, fetch_sec_filings

logger = logging.getLogger("AgentSyndicate")


def get_multi_agent_debate(symbol: str = "AAPL") -> Dict[str, Any]:
    """
    Simulates TradingAgents Multi-Persona Syndicate Debate:
    1. Bullish Momentum Analyst
    2. Bearish Macro & Risk Officer
    3. Chief Risk Officer (CRO) position sizing on $10,000 baseline
    4. Synthesized Trader Verdict
    """
    sym = symbol.strip().upper()
    try:
        t = yf.Ticker(sym)
        fast = t.fast_info
        price = fast.last_price or 100.0
        hist = t.history(period="3mo", interval="1d")
        hist = compute_indicators(hist)
        latest = hist.iloc[-1] if not hist.empty else {}

        rsi = float(latest.get("RSI", 50))
        macd = float(latest.get("MACD", 0))
        sig = float(latest.get("MACD_Signal", 0))
        sma50 = float(latest.get("SMA50", price))

        # Position sizing calculations for $10,000 account:
        # 2% risk limit = $200 max risk per trade
        stop_dist = max(price * 0.04, 1.0)
        risk_2pct = 200.0
        suggested_qty = max(1, int(risk_2pct / stop_dist))
        alloc_val = suggested_qty * price

        bull_points = []
        bear_points = []

        if rsi < 40:
            bull_points.append(f"RSI reading of {rsi:.1f} indicates oversold conditions and potential mean reversion.")
        else:
            bear_points.append(f"RSI at {rsi:.1f} indicates momentum is elevated or consolidating.")

        if macd > sig:
            bull_points.append(f"MACD line ({macd:.2f}) is above signal line ({sig:.2f}), confirming positive short-term momentum.")
        else:
            bear_points.append(f"MACD line ({macd:.2f}) is trailing below signal line ({sig:.2f}), signaling downward pressure.")

        if price >= sma50:
            bull_points.append(f"Trading above 50-day SMA (${sma50:.2f}), maintaining intermediate bull trend structure.")
        else:
            bear_points.append(f"Trading below 50-day SMA (${sma50:.2f}), facing institutional overhead supply.")

        meta = SP500_MAP.get(sym, {})
        conviction = 7 if (price >= sma50 and macd > sig) else (4 if rsi <= 35 else 5)

        return {
            "symbol": sym,
            "company": meta.get("name", sym),
            "price": round(price, 2),
            "bull_case": {
                "persona": "🐂 Bullish Momentum Analyst",
                "thesis": f"Favorable risk/reward setup in {sym} supported by market liquidity.",
                "points": bull_points or ["Constructive consolidation near key support levels."]
            },
            "bear_case": {
                "persona": "🐻 Bearish Macro & Risk Analyst",
                "thesis": f"Downside vulnerability in {sym} due to multiple compression or resistance.",
                "points": bear_points or ["Broader macro volatility and sector rotation risks."]
            },
            "risk_assessment": {
                "persona": "🛡️ Chief Risk Officer (CRO)",
                "account_equity": 10000.0,
                "risk_tolerance_pct": "2.0% ($200.00)",
                "recommended_stop_loss": round(price - stop_dist, 2),
                "recommended_target": round(price + (stop_dist * 2.2), 2),
                "recommended_shares": suggested_qty,
                "capital_required": round(alloc_val, 2),
                "portfolio_exposure_pct": round((alloc_val / 10000.0 * 100), 1),
                "concentration_verdict": "SAFE (<25% Cap)" if alloc_val <= 2500.0 else "WARNING: High Allocation"
            },
            "verdict": {
                "action": "BUY" if conviction >= 6 else ("SELL / HEDGE" if conviction <= 4 else "HOLD / NEUTRAL"),
                "conviction_score": f"{conviction}/10"
            }
        }
    except Exception as e:
        logger.error(f"Error in multi-agent debater for {sym}: {e}")
        return {"error": str(e), "symbol": sym}


def get_daily_desk_briefing(scanner_results: Optional[list] = None) -> Dict[str, Any]:
    """FinGPT-style Morning / Desk Intelligence Note across S&P 500."""
    p = load_portfolio()
    results = scanner_results or []

    top_buys = [s for s in results if s.get("pct_change", 0) > 0 and s.get("rsi", 50) < 60][:3]
    top_hedges = [s for s in results if s.get("pct_change", 0) < 0][:2]

    # Fetch macro context
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
            "risk_profile": "CONSERVATIVE / DISCIPLINED ($10K BASE)"
        },
        "top_setups": top_buys,
        "watch_out": top_hedges
    }


def build_deep_agent_context(symbol: str) -> str:
    """
    Synthesizes all 5 data layers into a rich, structured quantitative briefing
    for LLM prompt context injection.
    """
    sym = symbol.upper()
    lines = [f"=== DEEP INSTITUTIONAL INTELLIGENCE CONTEXT FOR {sym} ==="]

    # Layer 1: Price & Technicals
    try:
        quote = fetch_stock_quote(sym)
        lines.append(
            f"1. PRICE & TECHNICALS: Price: ${quote['price']:.2f} ({quote['pct_change']:+.2f}%), "
            f"52W Range: ${quote['year_low']:.2f} - ${quote['year_high']:.2f}, "
            f"P/E: {quote.get('pe_ratio', 'N/A')}, Beta: {quote.get('beta', '1.0')}"
        )
    except Exception:
        pass

    # Layer 2: SEC EDGAR Filings
    try:
        sec = fetch_sec_filings(sym)
        if sec.get("has_filings"):
            latest_10k = sec.get("latest_10k", {})
            lines.append(
                f"2. SEC EDGAR FILINGS: Latest 10-K filed {latest_10k.get('filing_date', 'N/A')}. "
                f"MD&A Summary: {sec.get('mda_summary', 'Standard operational disclosures.')[:250]}..."
            )
    except Exception:
        pass

    # Layer 3: Insider & 13F Activity
    try:
        insider = fetch_insider_and_13f_activity(sym)
        cluster = insider.get("cluster_verdict", "BALANCED / INACTIVE")
        lines.append(
            f"3. INSIDER & 13F OWNERSHIP: Executive Sentiment: {cluster} "
            f"({insider.get('recent_buys_count', 0)} Form 4 Buys vs {insider.get('recent_sells_count', 0)} Sells). "
            f"Top Institutional Holders: {', '.join([h['holder'] for h in insider.get('institutional_holders', [])[:3]])}"
        )
    except Exception:
        pass

    # Layer 4: Breaking News & Catalysts
    try:
        news = fetch_breaking_news(sym)
        sent = news.get("overall_sentiment", {})
        top_cats = news.get("top_catalysts", [])
        lines.append(
            f"4. BREAKING NEWS & CATALYSTS: Sentiment: {sent.get('label', 'NEUTRAL')} (Polarity: {sent.get('score', 0):+.2f}), "
            f"Key Catalysts: {', '.join(top_cats) if top_cats else 'GENERAL'}. "
            f"Total Articles Tracked: {news.get('total_articles', 0)}"
        )
    except Exception:
        pass

    # Layer 5: Macro Regime & Yield Curve
    try:
        macro = fetch_macro_regime()
        ind = macro.get("indicators", {})
        lines.append(
            f"5. MACRO REGIME: {macro.get('regime')} ({macro.get('bias')}). "
            f"10Y Yield: {ind.get('ten_year_yield', 4.4):.2f}%, 10Y-2Y Spread: {ind.get('yield_spread_bps', 15):+.1f} bps "
            f"({macro.get('curve_status')}), VIX: {ind.get('vix', 16.5):.2f}"
        )
    except Exception:
        pass

    lines.append("=====================================================")
    return "\n".join(lines)


def process_chat_message(
    message: str,
    provider: str = "groq",
    model: str = "llama-3.3-70b-versatile",
    groq_api_key: str = "",
    ollama_base_url: str = "http://localhost:11434",
    current_symbol: str = "AAPL"
) -> Dict[str, Any]:
    """
    Processes chat requests with multi-agent syndicate coordination,
    trade command parsing, and resilient LLM invocation.
    """
    prompt = message.strip()
    target_sym = current_symbol.upper()

    # 1. Detect direct paper trading execution command
    trade_match = re.search(r"\b(BUY|SELL)\s+(\d+)\s+(?:SHARES\s+OF\s+)?([A-Z]{1,5})\b", prompt.upper())
    if trade_match:
        action, qty_str, trade_sym = trade_match.groups()
        try:
            res = execute_order(action=action, symbol=trade_sym, quantity=int(qty_str))
            return {
                "response": (
                    f"✅ **Paper Trade Executed Successfully!**\n\n"
                    f"- **Action:** `{action}`\n"
                    f"- **Symbol:** `{trade_sym}`\n"
                    f"- **Quantity:** `{qty_str}` shares\n"
                    f"- **Fill Price:** `${res['trade']['price']:.2f}`\n"
                    f"- **Total Consideration:** `${res['trade']['total']:.2f}`\n\n"
                    f"*Your portfolio ledger has been updated.*"
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

    # 3. Detect Syndicate Multi-Agent Debate intent
    if any(k in prompt.lower() for k in ["debate", "bull vs bear", "syndicate", "cro", "adversarial"]):
        deb = get_multi_agent_debate(target_sym)
        bull = deb.get("bull_case", {})
        bear = deb.get("bear_case", {})
        cro = deb.get("risk_assessment", {})
        verdict = deb.get("verdict", {})

        bull_text = "\n".join([f"  • {p}" for p in bull.get("points", [])])
        bear_text = "\n".join([f"  • {p}" for p in bear.get("points", [])])

        debate_md = f"""### 🥊 Multi-Agent Syndicate Debate: **{target_sym}** (${deb.get('price', 0):.2f})
*TradingAgents Adversarial Institutional Framework*

---

#### {bull.get('persona', '🐂 Bull Analyst')}
> *"{bull.get('thesis', '')}"*
{bull_text}

#### {bear.get('persona', '🐻 Bear Analyst')}
> *"{bear.get('thesis', '')}"*
{bear_text}

---

#### {cro.get('persona', '🛡️ Chief Risk Officer (CRO)')}
- **Account Capital Baseline:** `${cro.get('account_equity', 10000.0):,.2f}` (Disciplined Paper Account)
- **Max Account Risk Per Trade:** `{cro.get('risk_tolerance_pct', '2% ($200)')}`
- **Recommended Position Sizing:** **`{cro.get('recommended_shares', 10)} shares`** (`${cro.get('capital_required', 0):,.2f}` exposure)
- **Stop-Loss Protection:** `${cro.get('recommended_stop_loss', 0):.2f}`
- **Profit Target:** `${cro.get('recommended_target', 0):.2f}`
- **Concentration Risk Check:** **`{cro.get('concentration_verdict', 'SAFE')}`** ({cro.get('portfolio_exposure_pct', 0)}% of account)

---

### ⚖️ Final Synthesized Verdict: **`{verdict.get('action', 'HOLD')}`**
**Conviction Score:** `{verdict.get('conviction_score', '5/10')}`  
*Say `Buy {cro.get('recommended_shares', 10)} {target_sym}` to execute this trade on your paper desk.*
"""
        return {"response": debate_md, "provider": "TradingAgents Syndicate"}

    # 4. Detect Daily Desk Briefing intent
    if any(k in prompt.lower() for k in ["brief", "briefing", "morning note", "desk report"]):
        brief = get_daily_desk_briefing()
        buys = brief.get("top_setups", [])
        buys_text = "\n".join([f"  • **{b['symbol']}** (${b['price']:.2f}): RSI `{b['rsi']}`, MACD `{b['macd']:.2f}`" for b in buys]) or "  • Consolidating markets; awaiting breakout confirmation."

        briefing_md = f"""### 📋 S&P 500 Daily Desk Intelligence Brief
**Date:** {brief.get('date')} | **Wire Time:** {brief.get('timestamp')}  
**Macro Market Regime:** **`{brief.get('market_regime')}`**

---

#### 💼 Portfolio Health & Risk Parameters ($10K Base):
- **Account Status:** Active Capital `${brief.get('portfolio_health', {}).get('account_equity', 10000.0):,.2f}`
- **Cash Reserves:** `${brief.get('portfolio_health', {}).get('cash_reserves', 10000.0):,.2f}`
- **Risk Posture:** `{brief.get('portfolio_health', {}).get('risk_profile')}`

#### 🌍 Macro Context:
{brief.get('macro_summary')}

#### 🎯 High-Conviction S&P 500 Opportunities:
{buys_text}

---
*Ask: `Debate <SYMBOL>` to trigger multi-agent cross-examination on any candidate.*
"""
        return {"response": briefing_md, "provider": "FinGPT Desk Intelligence"}

    # 5. Build rich multi-layer prompt and execute via LLMManager
    deep_context = build_deep_agent_context(target_sym)
    system_prompt = f"""You are the Antigravity S&P 500 AI Trader Agent, an institutional quantitative hedge fund trader and technical analyst.
You specialize strictly in S&P 500 equities.
You synthesize technical indicators, SEC EDGAR 10-K/10-Q disclosures, executive insider Form 4 trades, breaking news catalysts, and macro yield curve regimes to provide actionable, disciplined trading setups (Entry, Target, Stop Loss).
Keep responses structured, concise, and professional using markdown headers, bullet points, and exact numbers.

{deep_context}
"""

    gen_result = LLMManager.generate(
        prompt=prompt,
        system_prompt=system_prompt,
        preferred_provider=provider,
        model=model,
        groq_api_key=groq_api_key,
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
