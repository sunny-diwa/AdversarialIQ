"""
AdversarialIQ Conversational Router & Trader Agent
Parses natural language execution commands, triggers adversarial tribunal debates,
enforces non-LLM risk guardrail on user orders, and orchestrates multi-provider LLMs.
"""

import logging
import re
from typing import Any, Dict, Optional

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
                "trade": trade
            }
        except Exception as e:
            return {"response": f"⚠️ **Trade Rejected by Risk Guardrail:** {str(e)}"}

    # 2. Extract mentioned ticker
    words = re.findall(r"\b[A-Z]{1,5}\b", prompt.upper())
    for w in words:
        if w in SP500_MAP:
            target_sym = w
            break

    # 3. Detect Backtest / Strategy Simulation intent
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
                "backtest": bt
            }
        except Exception as e:
            logger.error(f"Backtest generation error: {e}")
            return {"response": f"⚠️ **Backtest Execution Notice:** {str(e)}"}

    # 4. Detect AdversarialIQ Debate / Tribunal intent
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
        return {"response": court_md, "provider": "AdversarialIQ Court", "symbol": target_sym}

    # 4. Detect Non-LLM Risk Gate & Sizing intent
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
| **Volatilty (14-Day ATR)** | `${gate['atr_14']:.2f}` (Stop Distance: `${gate['stop_distance']:.2f}`) |
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
        return {"response": risk_md, "provider": "Non-LLM Risk Gate", "symbol": target_sym}

    # 5. Detect 48-Hour Earnings Blackout Window intent
    if any(k in prompt.lower() for k in ["earnings blackout", "blackout window", "earnings date", "calendar"]):
        from src.data.calendar import fetch_earnings_calendar
        cal = fetch_earnings_calendar(target_sym)
        date_display = cal.get("earnings_date") or "No immediate announcement detected"
        hours_display = f"{cal['hours_to_earnings']} hours" if cal.get("hours_to_earnings") is not None else "N/A"

        badge = "🟢 CLEAR" if cal["action"] == "CLEAR" else ("🟡 WARNING (50% SIZING)" if cal["action"] == "HALVE" else "🔴 VETO BLACKOUT")

        cal_md = f"""### 📅 48-Hour Earnings Blackout Window: **{target_sym}**
*Binary Event Filter preventing pre-earnings algorithmic drawdown*

---

- **Blackout Status:** **`{cal['blackout_status']}`** ({badge})
- **Scheduled Earnings Date:** **`{date_display}`**
- **Countdown to Earnings:** **`{hours_display}`**
- **Sizing Action:** **`{cal['action']}`** (Multiplier: `{cal['size_multiplier']}x`)
- **Intelligence Source:** `{cal.get('source', 'yfinance').upper()}`

#### 📌 Risk Manager Audit:
> *{cal['reason']}*

---
*Rule: Orders within 24h of earnings are strictly VETOED. Orders within 24-48h are automatically halved.*
"""
        return {"response": cal_md, "provider": "Earnings Calendar Filter", "symbol": target_sym}

    # 6. Detect Daily Desk Briefing intent
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
    bull_args_str = '; '.join(tribunal['prosecution_bull'].get('arguments', []))
    bear_args_str = '; '.join(tribunal['prosecution_bear'].get('arguments', []))

    system_prompt = f"""You are AdversarialIQ, an institutional quantitative hedge fund trader and adversarial intelligence syndicate.
You evaluate every stock using an adversarial debate approach:
- Agent Bull proves the case for Long.
- Agent Bear proves the case for Short / Risk.
- Agent Judge delivers the final conviction score (0-100), ruling, and disciplined ATR-based risk position sizing.

LIVE DOSSIER FOR {target_sym}:
- Price: ${tribunal['price']:.2f}
- Bull Prosecution Arguments: {bull_args_str}
- Bear Defense Arguments: {bear_args_str}
- AdversarialIQ Conviction Score: {tribunal['conviction_score']}/100
- Adjudicated Ruling: {tribunal['verdict']}
- Position Size: {tribunal['judicial_risk_parameters']['recommended_shares']} shares | Stop Loss: {tribunal['judicial_risk_parameters']['stop_loss']} | Target: {tribunal['judicial_risk_parameters']['take_profit']}
- Past Post-Mortem Lessons: {tribunal.get('past_lessons_summary', 'None')}

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
