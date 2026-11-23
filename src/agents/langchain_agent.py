"""
AdversarialIQ LangChain Agent Syndicate & Pipeline
Builds composable LangChain runnables, prompt templates, and execution chains for:
1. Agent Bull (Advocate / Prosecutor)
2. Agent Bear (Adversary / Risk Auditor)
3. Agent Judge (Chief Magistrate & Synthesizer)
4. Conversational Financial Assistant
With automatic Langfuse Cloud tracing callbacks.
"""

import json
import logging
import uuid
from typing import Any, Dict, List, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
from langchain_core.prompts import (
    ChatPromptTemplate,
    HumanMessagePromptTemplate,
    PromptTemplate,
    SystemMessagePromptTemplate,
)
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnableSequence

from src.agents.schemas import (
    BearDefenseCase,
    BullProsecutionCase,
    ChiefJudgeRuling,
    RiskGateVerdict,
)
from src.core.config import SP500_MAP
from src.data.calendar import fetch_earnings_calendar
from src.data.macro import fetch_macro_regime
from src.data.market import fetch_stock_technicals
from src.data.news import fetch_breaking_news
from src.data.sec_edgar import fetch_insider_and_13f_activity, fetch_sec_filings
from src.execution.alpaca import AlpacaPaperClient
from src.execution.portfolio import get_portfolio_state
from src.llm.manager import LLMManager
from src.memory.journal import log_trade_thesis
from src.memory.reflection_store import format_lessons_for_prompt
from src.observability.langfuse_client import (
    LangfuseTracker,
    get_langfuse_callback,
    is_langfuse_configured,
)
from src.risk.guardrail import RiskGuardrail

logger = logging.getLogger("LangChainAgent")


# -----------------------------------------------------------------------------
# LangChain Prompt Templates
# -----------------------------------------------------------------------------

BULL_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "You are AGENT BULL, Senior Long Equity Prosecutor of the AdversarialIQ Syndicate. "
        "Your duty is to build an aggressive, rigorously evidenced prosecution case for initiating "
        "a LONG position on {symbol} ({company_name}).\n"
        "Ground your case on: technical breakout indicators (RSI, MACD, moving averages), "
        "SEC EDGAR 10-K/10-Q growth metrics, Form 4 insider buying clusters, and positive catalyst news sentiment."
    )),
    ("human", (
        "Market Dossier for {symbol}:\n"
        "- Current Price: ${price:.2f}\n"
        "- Technicals: RSI={rsi:.1f}, MACD={macd:.2f}, Signal={macd_signal:.2f}, SMA50=${sma50:.2f}\n"
        "- Form 4 Insider Sentiment: {insider_summary}\n"
        "- News Catalysts: {news_summary}\n"
        "- SEC EDGAR MD&A Status: {sec_summary}\n"
        "- Historical Reflexivity Lessons: {past_lessons}\n\n"
        "Present your prosecutorial case. Highlight key catalysts and argue why upside outweighs market beta."
    ))
])

BEAR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "You are AGENT BEAR, Senior Downside Adversary and Risk Auditor of the AdversarialIQ Syndicate. "
        "Your sworn mandate is to dismantle the Bull thesis, identify tail-risk vulnerabilities, and protect "
        "institutional capital from drawdown.\n"
        "Audit: technical overextension/resistance, yield curve inversion (FRED DGS10/2Y), CBOE VIX volatility, "
        "insider selling clusters, and imminent earnings announcement blackout windows (48 hours)."
    )),
    ("human", (
        "Review {symbol} Dossier & Bull Prosecution:\n"
        "- Bull Thesis: {bull_thesis}\n"
        "- Technical Indicators: RSI={rsi:.1f}, MACD={macd:.2f}, SMA50=${sma50:.2f}\n"
        "- Macro Regime: {macro_regime} (VIX: {vix:.2f}, 10Y-2Y Spread: {yield_spread_bps:.1f} bps)\n"
        "- Earnings Blackout: {earnings_status}\n"
        "- Form 4 Insider Activity: {insider_summary}\n\n"
        "Cross-examine the setup. Expose downside hazards and state why long exposure carries excessive risk."
    ))
])

JUDGE_PROMPT = ChatPromptTemplate.from_messages([
    ("system", (
        "You are THE CHIEF JUDGE of the AdversarialIQ Tribunal, an impartial quantitative magistrate. "
        "You adjudicate debates between Agent Bull and Agent Bear under institutional risk standards.\n"
        "Assign a definitive Conviction Score (0 to 100):\n"
        "- >= 65: APPROVED (EXECUTE LONG / BUY)\n"
        "- <= 38: PROHIBITED (BEARISH / VETO)\n"
        "- 39 to 64: REJECTED (STAND DOWN / HOLD)\n"
        "Synthesize both arguments, weigh the macro regime, and issue a binding judicial ruling."
    )),
    ("human", (
        "Adversarial Debate Transcript for {symbol}:\n\n"
        "[AGENT BULL PROSECUTION]:\n{bull_arguments}\n\n"
        "[AGENT BEAR DEFENSE]:\n{bear_arguments}\n\n"
        "[MACRO REGIME]: {macro_regime} (VIX={vix:.2f}, Spread={yield_spread_bps:.1f} bps)\n"
        "[EARNINGS RISK]: {earnings_status}\n\n"
        "Render your judicial decision, conviction score, and actionable synthesis."
    ))
])


# -----------------------------------------------------------------------------
# LangChain Model Dispatcher with Langfuse Callbacks
# -----------------------------------------------------------------------------

def invoke_langchain_model(
    prompt_text: str,
    system_prompt: str = "You are an institutional trading syndicate agent.",
    provider: str = "groq",
    model: str = "openai/gpt-oss-120b",
    symbol: str = "MARKET"
) -> str:
    """Dispatches prompt through LLMManager with automatic Langfuse Cloud tracing and failover."""
    res = LLMManager.generate(
        prompt=prompt_text,
        system_prompt=system_prompt,
        preferred_provider=provider,
        model=model,
        symbol=symbol
    )
    return res.get("response", "")


class LangChainTribunal:
    """
    LangChain-driven AdversarialIQ Tribunal pipeline.
    Orchestrates Bull Advocate -> Bear Adversary -> Chief Judge -> Non-LLM Risk Guardrail -> Persistence.
    """

    def __init__(
        self,
        symbol: str,
        account_capital: Optional[float] = None,
        provider: str = "groq",
        model: Optional[str] = None
    ):
        self.symbol = symbol.strip().upper()
        meta = SP500_MAP.get(self.symbol, {"name": self.symbol, "sector": "Other"})
        self.company_name = meta.get("name", self.symbol)
        self.account_capital = account_capital
        self.provider = provider
        self.model = model or ("openai/gpt-oss-120b" if provider == "groq" else ("gemini-4-hydrogen" if provider in ("gemini", "google") else "codestral-latest"))

    def run(self, auto_execute: bool = False, alpaca_key: Optional[str] = None, alpaca_secret: Optional[str] = None) -> Dict[str, Any]:
        """Executes the full LangChain multi-agent tribunal."""
        logger.info(f"Executing LangChain Adversarial Tribunal for {self.symbol} ({self.provider}/{self.model})")

        # 1. Fetch Multi-layer Data Dossier
        technicals = fetch_stock_technicals(self.symbol)
        sec_data = fetch_sec_filings(self.symbol)
        insider_data = fetch_insider_and_13f_activity(self.symbol)
        news_data = fetch_breaking_news(self.symbol)
        macro_data = fetch_macro_regime()
        calendar_data = fetch_earnings_calendar(self.symbol)
        past_lessons = format_lessons_for_prompt(self.symbol)

        price = technicals.get("price", 100.0)
        rsi = technicals.get("rsi", 50.0)
        macd = technicals.get("macd", 0.0)
        macd_signal = technicals.get("macd_signal", 0.0)
        sma50 = technicals.get("sma50", price)

        macro_regime = macro_data.get("regime", "NEUTRAL")
        macro_ind = macro_data.get("indicators", {})
        vix = macro_ind.get("vix", 16.0)
        yield_spread = macro_ind.get("yield_spread_bps", 12.0)

        insider_summary = f"{insider_data.get('cluster_verdict', 'NEUTRAL')} ({insider_data.get('recent_buys_count', 0)} buys, {insider_data.get('recent_sells_count', 0)} sells)"
        news_summary = f"{news_data.get('overall_sentiment', {}).get('label', 'NEUTRAL')} sentiment, Catalysts: {', '.join(news_data.get('top_catalysts', ['MOMENTUM'])[:3])}"
        sec_summary = "10-K/10-Q filed with SEC EDGAR; active liquidity." if sec_data.get("has_filings") else "Standard reports."
        earnings_status = calendar_data.get("reason", "No immediate earnings within 48h") if calendar_data.get("has_earnings_soon") else "Clear of 48-hour earnings blackout window."

        # 2. Stage Bull (LangChain runnable invocation)
        bull_input = {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "price": price,
            "rsi": rsi,
            "macd": macd,
            "macd_signal": macd_signal,
            "sma50": sma50,
            "insider_summary": insider_summary,
            "news_summary": news_summary,
            "sec_summary": sec_summary,
            "past_lessons": past_lessons
        }
        bull_formatted = BULL_PROMPT.format_messages(**bull_input)
        bull_response = invoke_langchain_model(
            prompt_text=bull_formatted[1].content,
            system_prompt=bull_formatted[0].content,
            provider=self.provider,
            model=self.model,
            symbol=self.symbol
        )

        bull_score = 55
        if rsi < 45:
            bull_score += 15
        if macd > macd_signal:
            bull_score += 10
        if price >= sma50:
            bull_score += 10
        if "BUYING" in insider_summary:
            bull_score += 10
        bull_score = min(95, bull_score)

        bull_case = BullProsecutionCase(
            title="🐂 AGENT BULL (MOMENTUM & CATALYST PROSECUTOR)",
            thesis=bull_response[:300].strip(),
            arguments=[line.strip() for line in bull_response.split("\n") if line.strip() and len(line) > 15][:4] or [bull_response[:200]],
            key_catalysts=news_data.get("top_catalysts", ["MOMENTUM"])[:3],
            case_score=bull_score,
            proposed_action="BUY"
        )

        # 3. Stage Bear (LangChain runnable invocation)
        bear_input = {
            "symbol": self.symbol,
            "bull_thesis": bull_case.thesis,
            "rsi": rsi,
            "macd": macd,
            "sma50": sma50,
            "macro_regime": macro_regime,
            "vix": vix,
            "yield_spread_bps": yield_spread,
            "earnings_status": earnings_status,
            "insider_summary": insider_summary
        }
        bear_formatted = BEAR_PROMPT.format_messages(**bear_input)
        bear_response = invoke_langchain_model(
            prompt_text=bear_formatted[1].content,
            system_prompt=bear_formatted[0].content,
            provider=self.provider,
            model=self.model,
            symbol=self.symbol
        )

        bear_score = 50
        if rsi > 65:
            bear_score += 18
        if macd < macd_signal:
            bear_score += 12
        if price < sma50:
            bear_score += 14
        if yield_spread < 0:
            bear_score += 12
        if calendar_data.get("has_earnings_soon"):
            bear_score += 15
        bear_score = min(95, bear_score)

        bear_case = BearDefenseCase(
            title="🐻 AGENT BEAR (RISK & MACRO ADVERSARY)",
            thesis=bear_response[:300].strip(),
            arguments=[line.strip() for line in bear_response.split("\n") if line.strip() and len(line) > 15][:4] or [bear_response[:200]],
            downside_risks=[line.strip() for line in bear_response.split("\n") if line.strip()][:3],
            case_score=bear_score,
            proposed_action="AVOID"
        )

        # 4. Stage Chief Judge (LangChain arbitration)
        judge_input = {
            "symbol": self.symbol,
            "bull_arguments": "\n".join(bull_case.arguments),
            "bear_arguments": "\n".join(bear_case.arguments),
            "macro_regime": macro_regime,
            "vix": vix,
            "yield_spread_bps": yield_spread,
            "earnings_status": earnings_status
        }
        judge_formatted = JUDGE_PROMPT.format_messages(**judge_input)
        judge_response = invoke_langchain_model(
            prompt_text=judge_formatted[1].content,
            system_prompt=judge_formatted[0].content,
            provider=self.provider,
            model=self.model,
            symbol=self.symbol
        )

        net = bull_score - bear_score
        conviction_index = max(10, min(95, int(50 + (net * 0.75))))

        if conviction_index >= 65:
            ruling = "APPROVED (EXECUTE BUY / LONG)"
            badge = "bullish"
            action = "BUY"
        elif conviction_index <= 38:
            ruling = "PROHIBITED (BEARISH BIAS / SHORT OR HEDGE)"
            badge = "bearish"
            action = "VETO"
        else:
            ruling = "REJECTED (STAND DOWN / NEUTRAL ARBITRAGE)"
            badge = "neutral"
            action = "HOLD"

        judge_ruling = ChiefJudgeRuling(
            arbiter="⚖️ AGENT JUDGE (CHIEF RISK MAGISTRATE)",
            ruling=ruling,
            conviction_score=conviction_index,
            verdict_badge=badge,
            ruling_summary=judge_response[:260].strip(),
            synthesis_rationale=f"LangChain Synthesis: Bull Score {bull_score}/100 vs. Bear Score {bear_score}/100. Net conviction: {conviction_index}/100.",
            recommended_action=action
        )

        # 5. Non-LLM Risk Guardrail
        alpaca = AlpacaPaperClient()
        equity = self.account_capital or 10000.0
        positions = {}
        if alpaca.is_configured():
            acct = alpaca.get_account()
            if acct:
                equity = float(acct.get("portfolio_value", equity) or equity)
                for p in alpaca.get_positions():
                    positions[p["symbol"]] = p
        else:
            port = get_portfolio_state()
            equity = float(port.get("total_equity", equity) or equity)
            positions = port.get("positions", {})

        risk_verdict = RiskGuardrail.evaluate_order(
            symbol=self.symbol,
            action=action,
            equity=equity,
            current_positions=positions,
            conviction_score=conviction_index
        )
        risk_gate = RiskGateVerdict(**risk_verdict)

        trade_id = str(uuid.uuid4())[:8]
        bracket_legs = {
            "stop_loss": risk_gate.stop_loss,
            "take_profit": risk_gate.take_profit,
            "risk_reward_ratio": risk_gate.risk_reward_ratio
        }

        # 6. Persistence to SQLite Thesis Journal
        log_trade_thesis(
            trade_id=trade_id,
            symbol=self.symbol,
            action=action,
            entry_price=price,
            shares=risk_gate.adjusted_shares,
            bull_arguments=bull_case.arguments,
            bear_arguments=bear_case.arguments,
            conviction_score=conviction_index,
            judge_ruling=judge_ruling.ruling_summary,
            stop_loss=risk_gate.stop_loss,
            take_profit=risk_gate.take_profit,
            risk_gate_decision=risk_gate.model_dump(),
            status="OPEN" if risk_gate.approved else "VETOED"
        )

        # 7. Langfuse Cloud Trace Mirroring
        try:
            LangfuseTracker.trace_tribunal(
                symbol=self.symbol,
                bull_thesis=bull_case.thesis,
                bear_thesis=bear_case.thesis,
                judge_ruling=judge_ruling.ruling_summary,
                conviction_score=conviction_index,
                action=action,
                risk_approved=risk_gate.approved,
                bracket=bracket_legs
            )
        except Exception:
            pass

        return {
            "symbol": self.symbol,
            "company_name": self.company_name,
            "price": price,
            "engine": "LangChain Composable Runnable",
            "provider": self.provider,
            "model": self.model,
            "dossier": {
                "technicals": technicals,
                "macro": macro_data,
                "calendar": calendar_data,
                "news": news_data,
                "insider": insider_data
            },
            "past_lessons": past_lessons,
            "bull_case": bull_case.model_dump(),
            "bear_case": bear_case.model_dump(),
            "judge_ruling": judge_ruling.model_dump(),
            "risk_gate": risk_gate.model_dump(),
            "completed": True
        }
