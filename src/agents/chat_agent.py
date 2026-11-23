"""
AdversarialIQ Conversational Router & Trader Agent
Parses natural language execution commands, triggers adversarial tribunal debates,
enforces non-LLM risk guardrail on user orders, calls financial tools dynamically
(news, technicals, SEC EDGAR, insider Form 4, macro FRED, earnings calendar),
and orchestrates multi-provider LLMs.
"""

import json
import logging
import re
from typing import Any, Dict, Optional

from src.agents.tools import (
    AVAILABLE_TOOLS,
    TOOL_SCHEMAS,
    execute_tool,
    tool_get_company_news,
    tool_get_earnings_calendar,
    tool_get_insider_activity,
    tool_get_macro_regime,
    tool_get_portfolio_status,
    tool_get_sec_filings,
    tool_get_stock_technicals,
)
from src.agents.tribunal import get_daily_desk_briefing, run_adversarial_trade_tribunal
from src.backtest import StrategyGenerator
from src.core.config import SP500_MAP
from src.execution.portfolio import execute_order
from src.llm.manager import LLMManager
from src.risk.guardrail import RiskGuardrail

logger = logging.getLogger("ChatAgent")


def process_chat_message(
    message: str,
    provider: str = "groq",
    model: str = "openai/gpt-oss-120b",
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
    1. Parses trade execution orders with Non-LLM Risk Guardrail safety check.
    2. Runs Backtest Strategy Simulations on demand.
    3. Triggers Adversarial Tribunal Debates (Bull vs Bear vs Chief Judge).
    4. Dynamically calls tools (Company News, Technicals, SEC Filings, Insider Activity, Macro Regime).
    5. Serves daily desk briefings.
    6. Injects live news & market data directly into LLM input context with tool-calling capabilities.
    """
    prompt = message.strip()
    target_sym = current_symbol.upper()

    # 1. Detect trade command routed to Alpaca or local desk
    trade_match = re.search(r"\b(BUY|SELL)\s+(\d+)\s+(?:SHARES\s+OF\s+)?([A-Z]{1,5})\b", prompt.upper())
    if trade_match:
        action, qty_str, trade_sym = trade_match.groups()
        requested_qty = int(qty_str)

        try:
            res = execute_order(
                action=action,
                symbol=trade_sym,
                quantity=requested_qty,
                alpaca_key=alpaca_key,
                alpaca_secret=alpaca_secret
            )
            broker = "Alpaca US Paper Trading" if "alpaca_order_id" in res.get("trade", {}) else "Local Simulated Desk"
            trade = res.get("trade", {})
            bracket = trade.get("bracket", {})

            bracket_text = ""
            if bracket and bracket.get("stop_loss"):
                bracket_text = f"\n- **Mandatory Bracket Legs:** Stop-Loss `${bracket['stop_loss']:.2f}` | Take-Profit `${bracket['take_profit']:.2f}`"

            return {
                "response": (
                    f"✅ **Trade Routed & Executed Successfully!**\n\n"
                    f"- **Broker:** `{broker}`\n"
                    f"- **Action:** `{action}`\n"
                    f"- **Symbol:** `{trade_sym}`\n"
                    f"- **Quantity:** `{trade.get('quantity', requested_qty)}` shares\n"
                    f"- **Fill Price:** `${trade.get('price', 0.0):.2f}`\n"
                    f"- **Total Consideration:** `${trade.get('total', 0.0):.2f}`"
                    f"{bracket_text}\n\n"
                    f"*Your portfolio ledger and position records have been updated.*"
                ),
                "trade": trade,
                "tool_called": "execute_paper_trade"
            }
        except Exception as e:
            return {"response": f"⚠️ **Trade Rejected by Risk Guardrail:** {str(e)}"}

    # 2. Extract mentioned ticker (prioritize explicit ticker in user message)
    words = re.findall(r"\b[A-Z]{1,5}\b", prompt.upper())
    for w in words:
        if w in SP500_MAP:
            target_sym = w
            break

    # 3. Detect tool catalog / discovery query
    if any(k in prompt.lower() for k in ["what tools", "list tools", "available tools", "show tools", "help tools"]):
        tools_list = "\n".join([
            f"- **`{t['name']}`**: {t['description']}"
            for t in TOOL_SCHEMAS
        ])
        return {
            "response": f"""### 🛠️ AdversarialIQ Live Institutional Tool Suite
The bot is equipped with autonomous real-time quantitative and data tools:

{tools_list}

---
*You can invoke any tool directly by asking (e.g. `What is the latest news on NVDA?`, `Show technicals for AAPL`, `Check SEC filings for MSFT`, `What is the macro regime?`, or `Backtest RSI strategy on TSLA`).*""",
            "tools": TOOL_SCHEMAS
        }

    # 4. Detect Backtest / Strategy Simulation intent
    if any(k in prompt.lower() for k in ["backtest", "back test", "test my strategy", "test strategy", "simulate strategy", "run backtest"]):
        try:
            bt = StrategyGenerator.synthesize_and_run(
                strategy_prompt=prompt,
                symbol=target_sym,
                provider=provider,
                model=model
            )
            ret_col = "🟢" if bt["total_return_pct"] >= 0 else "🔴"
            bench_col = "🟢" if bt["benchmark_return_pct"] >= 0 else "🔴"
            alpha_col = "🟢" if bt["alpha_pct"] >= 0 else "🔴"
            bench_final = bt["initial_capital"] * (1 + bt["benchmark_return_pct"] / 100)

            response_md = f"""### ⚡ AdversarialIQ 5-Year Backtest Engine: **{bt['symbol']}**
**Horizon:** `{bt['period']}` | **Starting Capital:** `${bt['initial_capital']:,.2f}` | **Model:** `{bt.get('model_used', 'LLM')}`

---

#### 📊 Performance Analytics vs. Buy & Hold Benchmark:
| Metric | Strategy | Benchmark | Alpha / Edge |
|:---|:---|:---|:---|
| **Total Return** | **{ret_col} {bt['total_return_pct']:+.2f}%** | {bench_col} {bt['benchmark_return_pct']:+.2f}% | {alpha_col} **{bt['alpha_pct']:+.2f}%** |
| **Final Equity** | **${bt['final_equity']:,.2f}** | ${bench_final:,.2f} | — |
| **Sharpe Ratio** | **{bt['sharpe_ratio']}** | — | *(Assumes 4.0% Risk-Free Rate)* |
| **Sortino Ratio** | **{bt['sortino_ratio']}** | — | *(Downside Risk Adjusted)* |
| **Max Drawdown** | **{bt['max_drawdown_pct']:.2f}%** | — | *(Peak-to-Trough Drawdown)* |
| **Annualized Vol** | **{bt['annualized_volatility_pct']:.2f}%** | — | — |

---

#### 🎯 Trade Execution Statistics:
- **Total Trades:** `{bt['total_trades']}` (Wins: **`{bt['winning_trades']}`** | Losses: **`{bt['losing_trades']}`**)
- **Win Rate:** **`{bt['win_rate_pct']}%`**
- **Profit Factor:** **`{bt['profit_factor']}`**
- **Avg Trade Return:** **`{bt['avg_trade_pnl_pct']:+.2f}%`** | **Avg Hold Duration:** **`{bt['avg_hold_days']} days`**

---

#### 💻 Generated Vectorized Python Logic:
```python
{bt['generated_code']}
```

*Interactive equity curve data points have been generated.*"""

            return {
                "response": response_md,
                "backtest": bt,
                "tool_called": "run_backtest"
            }
        except Exception as e:
            logger.error(f"Backtest generation error: {e}")
            return {"response": f"⚠️ **Backtest Execution Notice:** {str(e)}"}

    # 5. Detect AdversarialIQ Debate / Tribunal intent
    if any(k in prompt.lower() for k in ["adversarial", "debate", "bull vs bear", "syndicate", "judge", "court", "tribunal"]):
        tribunal = run_adversarial_trade_tribunal(target_sym)
        bull = tribunal["prosecution_bull"]
        bear = tribunal["prosecution_bear"]
        judge_risk = tribunal["judicial_risk_parameters"]

        bull_bullets = "\n".join([f"  • {a}" for a in bull.get("arguments", [])])
        bear_bullets = "\n".join([f"  • {a}" for a in bear.get("arguments", [])])

        reasons = ""
        if judge_risk.get("veto_reasons"):
            reasons = "\n- **Risk Gate Veto Reasons:** " + "; ".join(judge_risk["veto_reasons"])
        if judge_risk.get("warnings"):
            reasons += "\n- **Risk Gate Warnings:** " + "; ".join(judge_risk["warnings"])

        court_md = f"""### ⚖️ AdversarialIQ Trade Tribunal: **{target_sym}** (${tribunal['price']:.2f})
*Cross-Examination: Bull Advocate vs. Bear Adversary vs. Chief Judge*

---

#### {bull.get('title', '🐂 AGENT BULL')} (Score: {bull.get('case_score', 50)}/100)
{bull_bullets}

#### {bear.get('title', '🐻 AGENT BEAR')} (Score: {bear.get('case_score', 50)}/100)
{bear_bullets}

---

#### {judge_risk['arbiter']} — ADJUDICATED RISK MANDATE
- **AdversarialIQ Conviction Score:** **`{tribunal['conviction_score']}/100`**
- **Judicial Ruling:** **`{tribunal['verdict']}`**
- *{tribunal['verdict_summary']}*{reasons}

| Parameter | Adjudicated Requirement |
|---|---|
| **Capital Baseline** | `{judge_risk['capital_base']}` ({tribunal['execution_broker']}) |
| **Max Risk Budget** | `{judge_risk.get('risk_budget_dollars', '$100.00')}` |
| **Recommended Size** | **`{judge_risk['recommended_shares']} shares`** (`{judge_risk['total_capital_required']}`) |
| **Portfolio Exposure** | `{judge_risk['portfolio_allocation_pct']}` (Max 5% Ticker / 20% Sector Cap) |
| **14-Day ATR Volatility** | `${judge_risk.get('atr_14', 2.0):.2f}` (Stop Distance: `${judge_risk.get('stop_distance', 3.0):.2f}`) |
| **Entry Price** | `{judge_risk['entry_price']}` |
| **Stop-Loss Protection** | `{judge_risk['stop_loss']}` |
| **Profit Target** | `{judge_risk['take_profit']}` |
| **Risk / Reward Ratio** | `{judge_risk['risk_reward_ratio']}` |

---
*Say `Buy {judge_risk['recommended_shares']} {target_sym}` to execute this ruling on your {tribunal['execution_broker']}.*
"""
        return {"response": court_md, "provider": "AdversarialIQ Court", "symbol": target_sym, "tool_called": "run_adversarial_tribunal"}

    # 6. Detect Non-LLM Risk Gate & Sizing intent
    if any(k in prompt.lower() for k in ["risk gate", "risk sizing", "bracket order", "position size", "position-sizing", "2% risk"]):
        from src.execution.portfolio import get_portfolio_state
        port = get_portfolio_state()
        equity = port.get("total_equity", 10000.0)
        positions = port.get("positions", [])
        gate = RiskGuardrail.evaluate_order(
            symbol=target_sym,
            action="BUY",
            equity=equity,
            current_positions=positions,
            manual_override=True
        )

        checks = gate.get("risk_checks", {})
        bracket = checks.get("mandatory_bracket_order", {})
        reasons = "\n- **Veto Reasons:** " + "; ".join(gate["veto_reasons"]) if gate["veto_reasons"] else ""
        warnings = "\n- **Active Warnings:** " + "; ".join(gate["warnings"]) if gate["warnings"] else ""

        risk_md = f"""### 🛡️ Non-LLM Risk Guardrail: **{target_sym}** (${gate['price']:.2f})
*Deterministic Mathematical Position Sizing & Downside Protection Gate*

---

#### ⚖️ Judicial Status: **`{'APPROVED FOR EXECUTION' if gate['approved'] else 'VETOED BY RISK GATE'}`**{reasons}{warnings}

| Risk Guardrail Parameter | Institutional Value |
|---|---|
| **Capital Baseline** | `${gate['equity']:,.2f}` |
| **Volatility (14-Day ATR)** | `${gate['atr_14']:.2f}` (Stop Distance: `${gate['stop_distance']:.2f}`) |
| **Max Trade Risk Budget** | `${gate['risk_budget_dollars']:,.2f}` ({gate['macro_regime']} Regime) |
| **Raw ATR Position Size** | `{gate['raw_shares']} shares` |
| **Adjusted Safe Size** | **`{gate['adjusted_shares']} shares`** (${gate['total_consideration']:,.2f}) |
| **Portfolio Allocation** | `{gate['portfolio_allocation_pct']:.2f}%` (Max 5% Single-Ticker Cap) |
| **Sector Allocation Cap** | Max 20% in `{gate['sector']}` (Current: `${checks.get('current_sector_exposure', 0):,.2f}`) |
| **Concurrent Positions** | `{checks.get('current_open_positions', 0)} / {checks.get('max_open_positions_cap', 5)} max allowed` |
| **Earnings Blackout Status** | **`{checks.get('earnings_blackout_status', 'CLEAR')}`** |
| **Automated Stop-Loss** | **`${gate['stop_loss']:.2f}`** |
| **Automated Take-Profit** | **`${gate['take_profit']:.2f}`** (R/R {gate['risk_reward_ratio']}) |

---
*Mandatory Bracket Order Class: `{bracket.get('order_class', 'bracket').upper()}` attached to submission.*
"""
        return {"response": risk_md, "provider": "Non-LLM Risk Gate", "symbol": target_sym, "tool_called": "risk_guardrail"}

    # 7. Detect 48-Hour Earnings Blackout Window intent
    if any(k in prompt.lower() for k in ["earnings blackout", "blackout window", "earnings date", "calendar"]):
        res = execute_tool("get_earnings_calendar", {"symbol": target_sym})
        return {
            "response": res.get("formatted_markdown", ""),
            "earnings": res.get("result", {}),
            "tool_called": "get_earnings_calendar",
            "symbol": target_sym
        }

    # 8. Detect Daily Desk Briefing intent
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

    # 9. Detect Company News & Catalyst Query (Tool Calling)
    is_news_query = any(k in prompt.lower() for k in [
        "news", "headline", "headlines", "catalyst", "catalysts",
        "what happened", "what is happening", "press release", "breaking news", "article"
    ])
    if is_news_query:
        logger.info(f"Invoking tool 'get_company_news' for {target_sym}")
        news_tool_res = execute_tool("get_company_news", {"symbol": target_sym, "limit": 5})
        raw_news = news_tool_res.get("result", {})

        is_direct_news_lookup = any(p in prompt.lower() for p in [
            "what is the latest news", "what's the latest news", "what is the news", "what's the news",
            "get news", "show news", "latest news", "breaking news", "tell me news", "catalysts for",
            "what happened with", "any news", "is there any news", "headlines for", "news for", "news on"
        ]) and not any(k in prompt.lower() for k in ["should i buy", "should i sell", "how does", "what does this mean for", "price target impact"])

        if is_direct_news_lookup:
            return {
                "response": news_tool_res.get("formatted_markdown", ""),
                "news": raw_news,
                "tool_called": "get_company_news",
                "symbol": target_sym,
                "provider": "AdversarialIQ News Wire"
            }

        # Otherwise, feed the live news into LLM for an evidence-backed institutional synthesis
        articles = raw_news.get("articles", [])
        headlines_summary = "\n".join([f"- {a.get('title')} ({a.get('sentiment')}): {a.get('summary')[:140]}" for a in articles[:4]])
        sentiment = raw_news.get("overall_sentiment", {})

        system_prompt = f"""You are AdversarialIQ, a quantitative trader and financial analyst.
The user is asking an analytical question regarding {target_sym}.
You have just retrieved the latest real-time news articles and catalyst tags for {target_sym} using the `get_company_news` tool:
- Aggregate Sentiment: {sentiment.get('label')} ({sentiment.get('score', 0):+.2f})
- Top Catalysts: {', '.join(raw_news.get('top_catalysts', []))}
- Live Breaking Headlines:
{headlines_summary}

Synthesize these live news articles directly to answer the user's inquiry with professional rigor.
Highlight how the reported catalysts impact valuation, revenue visibility, and trade positioning."""

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
            "news": raw_news,
            "tool_called": "get_company_news",
            "provider": gen_result["provider"],
            "model": gen_result.get("model", ""),
            "symbol": target_sym
        }

    # 10. Detect Technicals Query (Tool Calling)
    if any(k in prompt.lower() for k in ["technical", "technicals", "rsi", "macd", "moving average", "sma", "ema", "bollinger", "indicators", "chart"]):
        logger.info(f"Invoking tool 'get_stock_technicals' for {target_sym}")
        tech_res = execute_tool("get_stock_technicals", {"symbol": target_sym})
        return {
            "response": tech_res.get("formatted_markdown", ""),
            "technicals": tech_res.get("result", {}),
            "tool_called": "get_stock_technicals",
            "symbol": target_sym,
            "provider": "Market Data Engine"
        }

    # 11. Detect SEC Filings & EDGAR Query (Tool Calling)
    if any(k in prompt.lower() for k in ["sec filing", "sec edgar", "10-k", "10-q", "8-k", "mda", "risk factors", "edgar report", "filings"]):
        logger.info(f"Invoking tool 'get_sec_filings' for {target_sym}")
        sec_res = execute_tool("get_sec_filings", {"symbol": target_sym})
        return {
            "response": sec_res.get("formatted_markdown", ""),
            "filings": sec_res.get("result", {}),
            "tool_called": "get_sec_filings",
            "symbol": target_sym,
            "provider": "SEC EDGAR"
        }

    # 12. Detect Insider Form 4 & 13F Activity Query (Tool Calling)
    if any(k in prompt.lower() for k in ["insider", "form 4", "13f", "insider buying", "insider selling", "whale", "executive transaction"]):
        logger.info(f"Invoking tool 'get_insider_activity' for {target_sym}")
        insider_res = execute_tool("get_insider_activity", {"symbol": target_sym})
        return {
            "response": insider_res.get("formatted_markdown", ""),
            "insider": insider_res.get("result", {}),
            "tool_called": "get_insider_activity",
            "symbol": target_sym,
            "provider": "SEC Form 4 Engine"
        }

    # 13. Detect Macro Regime Query (Tool Calling)
    if any(k in prompt.lower() for k in ["macro regime", "fred", "yield curve", "interest rate", "inflation rate", "treasury yield", "cpi", "vix"]):
        logger.info("Invoking tool 'get_macro_regime'")
        macro_res = execute_tool("get_macro_regime", {})
        return {
            "response": macro_res.get("formatted_markdown", ""),
            "macro": macro_res.get("result", {}),
            "tool_called": "get_macro_regime",
            "symbol": target_sym,
            "provider": "FRED Macro Engine"
        }

    # 14. Detect Portfolio Query (Tool Calling)
    if any(k in prompt.lower() for k in ["portfolio status", "my positions", "account balance", "portfolio equity", "cash balance", "my trades"]):
        logger.info("Invoking tool 'get_portfolio_status'")
        port_res = execute_tool("get_portfolio_status", {})
        return {
            "response": port_res.get("formatted_markdown", ""),
            "portfolio": port_res.get("result", {}),
            "tool_called": "get_portfolio_status",
            "provider": "Portfolio Ledger"
        }

    # 15. Real-Time Multi-Layer Context Injection for General / Conversational Queries
    # Pre-fetch live news, technicals, and tribunal dossier so the LLM gets everything in input
    news_dossier = tool_get_company_news(target_sym, limit=3)
    news_sentiment = news_dossier.get("overall_sentiment", {})
    news_headlines = "; ".join([a.get("title", "") for a in news_dossier.get("articles", [])[:3]])

    tech_dossier = tool_get_stock_technicals(target_sym)
    tribunal = run_adversarial_trade_tribunal(target_sym)
    bull_args_str = '; '.join(tribunal['prosecution_bull'].get('arguments', []))
    bear_args_str = '; '.join(tribunal['prosecution_bear'].get('arguments', []))

    system_prompt = f"""You are AdversarialIQ, an institutional quantitative hedge fund trader and adversarial intelligence syndicate.
You evaluate every stock using an adversarial debate approach with non-LLM risk guardrails and live real-time tools.

LIVE DOSSIER IN INPUT FOR {target_sym}:
- Current Price: ${tribunal['price']:.2f}
- Breaking News Sentiment: {news_sentiment.get('label', 'NEUTRAL')} ({news_sentiment.get('score', 0):+.2f})
- Top Catalysts: {', '.join(news_dossier.get('top_catalysts', []))}
- Recent Headlines: {news_headlines or 'None'}
- Key Technicals: RSI={tech_dossier.get('rsi', 50):.1f}, MACD={tech_dossier.get('macd', 0):.2f}, ATR14=${tech_dossier.get('atr_14', 2.0):.2f}, SMA50=${tech_dossier.get('sma50', 0):.2f}
- Bull Prosecution Case: {bull_args_str}
- Bear Defense Case: {bear_args_str}
- AdversarialIQ Conviction Score: {tribunal['conviction_score']}/100
- Adjudicated Ruling: {tribunal['verdict']}
- Suggested Position Size: {tribunal['judicial_risk_parameters']['recommended_shares']} shares | Stop Loss: {tribunal['judicial_risk_parameters']['stop_loss']} | Target: {tribunal['judicial_risk_parameters']['take_profit']}

AVAILABLE TOOLS YOU CAN CALL:
You can invoke any of the following tools by responding with `TOOL_CALL: {{"tool": "<name>", "arguments": {{...}}}}`:
- `get_company_news(symbol, limit)`: Breaking news, sentiment score, catalyst tags
- `get_stock_technicals(symbol)`: RSI, MACD, ATR, moving averages, Bollinger Bands
- `get_sec_filings(symbol)`: SEC EDGAR 10-K, 10-Q, 8-K filings and risk factors
- `get_insider_activity(symbol)`: Form 4 executive buy/sell clusters, 13F holdings
- `get_macro_regime()`: FRED interest rates, yield curve spread, CPI, VIX
- `get_earnings_calendar(symbol)`: 48-hour earnings blackout window
- `run_backtest(symbol, strategy)`: 5-year quantitative strategy backtest
- `run_adversarial_tribunal(symbol)`: Bull vs Bear debate and judicial ruling
- `execute_paper_trade(symbol, action, quantity)`: Order routing with bracket orders
- `get_portfolio_status()`: Portfolio balance, positions, win rate

Deliver structured, direct, professional institutional analysis using markdown tables and bullet points.
If the user asks to execute a trade, remind them they can type 'Buy <qty> <symbol>' or 'Sell <qty> <symbol>'."""

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

    resp_text = gen_result.get("response", "")

    # Check if the LLM emitted an explicit TOOL_CALL instruction
    tool_call_match = re.search(r"TOOL_CALL:\s*(\{.*?\})", resp_text, re.DOTALL)
    if tool_call_match:
        try:
            tool_payload = json.loads(tool_call_match.group(1))
            t_name = tool_payload.get("tool")
            t_args = tool_payload.get("arguments", {})
            logger.info(f"LLM triggered dynamic tool call: {t_name} with {t_args}")
            executed = execute_tool(t_name, t_args)
            return {
                "response": f"🛠️ **Tool Executed by Agent:** `{t_name}`\n\n" + executed.get("formatted_markdown", str(executed.get("result", ""))),
                "tool_called": t_name,
                "tool_result": executed,
                "provider": gen_result["provider"],
                "model": gen_result.get("model", ""),
                "symbol": target_sym
            }
        except Exception as te:
            logger.warning(f"Failed to execute LLM tool call: {te}")

    return {
        "response": resp_text,
        "provider": gen_result["provider"],
        "model": gen_result.get("model", ""),
        "failover": gen_result.get("failover", False),
        "symbol": target_sym
    }
