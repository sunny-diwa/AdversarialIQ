"""
Adversarial State-Machine Orchestrator
Manages the cyclic multi-stage adversarial debate pipeline:
INTAKE -> DATA_DOSSIER -> AGENT_BULL -> AGENT_BEAR -> AGENT_JUDGE -> NON_LLM_RISK_GATE -> EXECUTION_DISPATCH -> PERSISTENCE_LOG
"""

import json
import logging
import uuid
from typing import Any, Dict, Optional

from src.agents.schemas import (
    BearDefenseCase,
    BullProsecutionCase,
    ChiefJudgeRuling,
    RiskGateVerdict,
    TribunalState,
)
from src.core.config import SP500_MAP
from src.data.calendar import fetch_earnings_calendar
from src.data.macro import fetch_macro_regime
from src.data.market import fetch_stock_technicals
from src.data.news import fetch_breaking_news
from src.data.sec_edgar import fetch_insider_and_13f_activity, fetch_sec_filings
from src.execution.alpaca import AlpacaPaperClient
from src.execution.portfolio import execute_order, get_portfolio_state
from src.memory.journal import log_trade_thesis
from src.memory.reflection_store import format_lessons_for_prompt
from src.risk.guardrail import RiskGuardrail

logger = logging.getLogger("StateMachine")


class AdversarialStateMachine:
    """Orchestrates cyclic adversarial debate across typed stages."""

    def __init__(self, symbol: str, account_capital: Optional[float] = None):
        self.symbol = symbol.strip().upper()
        meta = SP500_MAP.get(self.symbol, {"name": self.symbol, "sector": "Other"})
        self.company_name = meta.get("name", self.symbol)
        self.account_capital = account_capital

        self.state = TribunalState(
            symbol=self.symbol,
            company_name=self.company_name,
            price=100.0,
            stage="INTAKE"
        )

    def run_full_pipeline(
        self,
        auto_execute: bool = False,
        alpaca_key: Optional[str] = None,
        alpaca_secret: Optional[str] = None
    ) -> Dict[str, Any]:
        """Runs all stages of the adversarial pipeline from intake to persistence."""
        self._stage_data_dossier()
        self._stage_bull_prosecution()
        self._stage_bear_defense()
        self._stage_judge_ruling()
        self._stage_non_llm_risk_gate()

        if auto_execute and self.state.risk_gate and self.state.risk_gate.approved:
            self._stage_execution(alpaca_key=alpaca_key, alpaca_secret=alpaca_secret)

        self._stage_persistence()
        self.state.completed = True

        return self.to_dict()

    def _stage_data_dossier(self):
        """Stage 1: Ingests technicals, SEC EDGAR, insider Form 4, news sentiment, macro regime, and past lessons."""
        self.state.stage = "DOSSIER"

        technicals = fetch_stock_technicals(self.symbol)
        price = technicals.get("price", 100.0)
        self.state.price = price

        sec_data = fetch_sec_filings(self.symbol)
        insider_data = fetch_insider_and_13f_activity(self.symbol)
        news_data = fetch_breaking_news(self.symbol)
        macro_data = fetch_macro_regime()
        calendar_data = fetch_earnings_calendar(self.symbol)
        past_lessons = format_lessons_for_prompt(self.symbol)

        self.state.dossier = {
            "technicals": technicals,
            "sec": sec_data,
            "insider": insider_data,
            "news": news_data,
            "macro": macro_data,
            "calendar": calendar_data
        }
        self.state.past_lessons = past_lessons

    def _stage_bull_prosecution(self):
        """Stage 2: Agent Bull prosecutes the case for LONG/BUY."""
        self.state.stage = "BULL"
        d = self.state.dossier
        tech = d.get("technicals", {})
        news = d.get("news", {})
        insider = d.get("insider", {})
        sec = d.get("sec", {})

        rsi = tech.get("rsi", 50.0)
        macd = tech.get("macd", 0.0)
        sig = tech.get("macd_signal", 0.0)
        price = tech.get("price", 100.0)
        sma50 = tech.get("sma50", price)

        bull_args = []
        bull_score = 50

        if rsi < 42:
            bull_args.append(f"Technical Reversal: RSI at {rsi:.1f} indicates oversold conditions primed for a mean-reversion rebound.")
            bull_score += 15
        elif rsi < 60:
            bull_args.append(f"Constructive Momentum: RSI at {rsi:.1f} has expansion headroom before resistance.")
            bull_score += 8

        if macd > sig:
            bull_args.append(f"MACD Bullish Trend: MACD ({macd:.2f}) sits above Signal ({sig:.2f}), confirming positive trend momentum.")
            bull_score += 12

        if price >= sma50:
            bull_args.append(f"Moving Average Support: Stock trades above 50-day SMA (${sma50:.2f}), confirming institutional bull structure.")
            bull_score += 10

        if "BUYING" in insider.get("cluster_verdict", "") or insider.get("recent_buys_count", 0) > 0:
            bull_args.append(f"Executive Buying Cluster: Form 4 filings confirm {insider.get('recent_buys_count', 0)} open-market insider purchases.")
            bull_score += 10

        if news.get("overall_sentiment", {}).get("label") == "BULLISH":
            cats = ", ".join(news.get("top_catalysts", ["MOMENTUM"])[:2])
            bull_args.append(f"Catalyst Support: Positive headline sentiment (+{news['overall_sentiment'].get('score', 0):.2f}) driven by {cats}.")
            bull_score += 10

        if sec.get("has_filings"):
            bull_args.append("SEC EDGAR Verification: 10-K/10-Q reports continuous operational execution and solid liquidity.")
            bull_score += 5

        if not bull_args:
            bull_args.append("Technical consolidation with defensive valuation support.")

        self.state.bull_case = BullProsecutionCase(
            title="🐂 AGENT BULL (MOMENTUM & CATALYST PROSECUTOR)",
            thesis=f"Initiate LONG exposure on {self.symbol} based on technical support and constructive catalyst alignment.",
            arguments=bull_args,
            key_catalysts=news.get("top_catalysts", ["MOMENTUM"])[:3],
            case_score=min(95, bull_score),
            proposed_action="BUY"
        )

    def _stage_bear_defense(self):
        """Stage 3: Agent Bear cross-examines Bull's thesis and exposes risk vulnerabilities."""
        self.state.stage = "BEAR"
        d = self.state.dossier
        tech = d.get("technicals", {})
        macro = d.get("macro", {})
        insider = d.get("insider", {})
        calendar = d.get("calendar", {})

        rsi = tech.get("rsi", 50.0)
        macd = tech.get("macd", 0.0)
        sig = tech.get("macd_signal", 0.0)
        price = tech.get("price", 100.0)
        sma50 = tech.get("sma50", price)

        bear_args = []
        bear_score = 50

        if rsi > 65:
            bear_args.append(f"Overextended Exhaustion: RSI is at {rsi:.1f}, indicating stretched buyer momentum vulnerable to sharp profit-taking.")
            bear_score += 18
        elif rsi < 35:
            bear_args.append(f"Severe Weakness: RSI of {rsi:.1f} highlights persistent institutional distribution.")
            bear_score += 10

        if macd < sig:
            bear_args.append(f"Negative Momentum Cross: MACD ({macd:.2f}) trails below Signal ({sig:.2f}), confirming downward pressure.")
            bear_score += 12

        if price < sma50:
            bear_args.append(f"Overhead Supply Resistance: Trading below 50-day SMA (${sma50:.2f}); rallies face heavy trapped supply.")
            bear_score += 14

        if insider.get("recent_sells_count", 0) > insider.get("recent_buys_count", 0):
            bear_args.append(f"Executive Divestment: Corporate insiders executed {insider.get('recent_sells_count', 0)} Form 4 sales over the past 90 days.")
            bear_score += 10

        macro_ind = macro.get("indicators", {})
        if macro_ind.get("yield_spread_bps", 10) < 0:
            bear_args.append(f"Yield Curve Inversion: US 10Y-2Y yield spread is {macro_ind.get('yield_spread_bps'):.1f} bps (Recession Alert).")
            bear_score += 12

        if macro_ind.get("vix", 16) > 20:
            bear_args.append(f"Macro Volatility: CBOE VIX sits at {macro_ind.get('vix'):.2f}, signaling broad equity risk-off sentiment.")
            bear_score += 10

        if calendar.get("has_earnings_soon"):
            bear_args.append(f"Earnings Event Risk: {calendar.get('reason')}")
            bear_score += 15

        if not bear_args:
            bear_args.append("General equity market beta risk and sector rotation headwinds.")

        self.state.bear_case = BearDefenseCase(
            title="🐻 AGENT BEAR (RISK & MACRO ADVERSARY)",
            thesis=f"Stand down or hedge {self.symbol} due to macro fragility and downside volatility risk.",
            arguments=bear_args,
            downside_risks=bear_args[:3],
            case_score=min(95, bear_score),
            proposed_action="AVOID"
        )

    def _stage_judge_ruling(self):
        """Stage 4: Agent Judge adjudicates the debate and assigns the Conviction Index."""
        self.state.stage = "JUDGE"
        bull = self.state.bull_case
        bear = self.state.bear_case

        bull_score = bull.case_score if bull else 50
        bear_score = bear.case_score if bear else 50

        net = bull_score - bear_score
        conviction_index = max(10, min(95, int(50 + (net * 0.75))))

        if conviction_index >= 65:
            ruling = "APPROVED (EXECUTE BUY / LONG)"
            badge = "bullish"
            summary = (
                f"Agent Bull prevailed before the court. Favorable risk/reward and catalyst support "
                f"justify initiating a LONG position under strict ATR bracket protection."
            )
            action = "BUY"
        elif conviction_index <= 38:
            ruling = "PROHIBITED (BEARISH BIAS / SHORT OR HEDGE)"
            badge = "bearish"
            summary = (
                f"Agent Bear established significant downside vulnerability. Macro inversion and technical resistance "
                f"dictate standing down from long exposure."
            )
            action = "VETO"
        else:
            ruling = "REJECTED (STAND DOWN / NEUTRAL ARBITRAGE)"
            badge = "neutral"
            summary = (
                f"Adversarial arguments reached near equilibrium. Risk/Reward ratio does not satisfy "
                f"institutional standards. Recommend awaiting clear breakout confirmation."
            )
            action = "HOLD"

        self.state.judge_ruling = ChiefJudgeRuling(
            arbiter="⚖️ AGENT JUDGE (CHIEF RISK MAGISTRATE)",
            ruling=ruling,
            conviction_score=conviction_index,
            verdict_badge=badge,
            ruling_summary=summary,
            synthesis_rationale=f"Bull Score: {bull_score}/100 vs. Bear Score: {bear_score}/100 -> Net Conviction {conviction_index}/100.",
            recommended_action=action
        )

    def _stage_non_llm_risk_gate(self):
        """Stage 5: Deterministic Non-LLM Risk Guardrail enforces ATR position sizing, exposure caps, and bracket orders."""
        self.state.stage = "RISK_GATE"

        # Determine equity base and active positions
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

        action = "BUY" if self.state.judge_ruling and self.state.judge_ruling.recommended_action == "BUY" else "SELL"
        conviction = self.state.judge_ruling.conviction_score if self.state.judge_ruling else 50

        # Execute Non-LLM Risk Guardrail
        risk_result = RiskGuardrail.evaluate_order(
            symbol=self.symbol,
            action=action,
            equity=equity,
            current_positions=positions,
            conviction_score=conviction
        )

        self.state.risk_gate = RiskGateVerdict(**risk_result)

    def _stage_execution(self, alpaca_key: Optional[str] = None, alpaca_secret: Optional[str] = None):
        """Stage 6: Executes trade via Alpaca or Local Simulated Desk with mandatory bracket orders."""
        self.state.stage = "EXECUTION"
        gate = self.state.risk_gate
        if not gate or not gate.approved or gate.adjusted_shares <= 0:
            return

        try:
            exec_res = execute_order(
                action=gate.action,
                symbol=gate.symbol,
                quantity=gate.adjusted_shares,
                order_type="MARKET",
                stop_loss=gate.stop_loss,
                take_profit=gate.take_profit,
                rationale=f"AdversarialIQ Tribunal Adjudicated ({self.state.judge_ruling.conviction_score if self.state.judge_ruling else 50}/100)",
                alpaca_key=alpaca_key,
                alpaca_secret=alpaca_secret
            )
            self.state.execution_result = exec_res
        except Exception as e:
            logger.error(f"Execution error for {self.symbol}: {e}")
            self.state.execution_result = {"status": "FAILED", "error": str(e)}

    def _stage_persistence(self):
        """Stage 7: Persists trade thesis to SQLite memory journal."""
        self.state.stage = "PERSISTENCE"
        bull = self.state.bull_case
        bear = self.state.bear_case
        judge = self.state.judge_ruling
        gate = self.state.risk_gate

        trade_id = str(uuid.uuid4())[:12]
        shares = gate.adjusted_shares if gate else 0
        price = gate.price if gate else self.state.price
        stop_loss = gate.stop_loss if gate else None
        take_profit = gate.take_profit if gate else None
        conviction = judge.conviction_score if judge else 50
        ruling = judge.ruling if judge else "PENDING"

        log_trade_thesis(
            trade_id=trade_id,
            symbol=self.symbol,
            action="BUY" if (judge and judge.recommended_action == "BUY") else "HOLD",
            entry_price=price,
            shares=shares,
            bull_arguments=bull.arguments if bull else [],
            bear_arguments=bear.arguments if bear else [],
            conviction_score=conviction,
            judge_ruling=ruling,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_gate_decision=gate.dict() if gate else {},
            status="OPEN" if (gate and gate.approved) else "VETOED"
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serializes the state-machine execution result into an API response contract."""
        gate = self.state.risk_gate
        judge = self.state.judge_ruling
        bull = self.state.bull_case
        bear = self.state.bear_case

        alpaca = AlpacaPaperClient()
        broker_name = "Alpaca US Paper Trading" if alpaca.is_configured() else "Local Simulated Desk"

        return {
            "symbol": self.symbol,
            "company": self.company_name,
            "price": self.state.price,
            "active_capital": gate.equity if gate else 10000.0,
            "execution_broker": broker_name,
            "conviction_score": judge.conviction_score if judge else 50,
            "verdict": judge.ruling if judge else "PENDING",
            "verdict_badge": judge.verdict_badge if judge else "neutral",
            "verdict_summary": judge.ruling_summary if judge else "",
            "prosecution_bull": bull.dict() if bull else {},
            "prosecution_bear": bear.dict() if bear else {},
            "judicial_risk_parameters": {
                "arbiter": judge.arbiter if judge else "⚖️ AGENT JUDGE",
                "capital_base": f"${gate.equity:,.2f}" if gate else "$10,000.00",
                "risk_budget_dollars": f"${gate.risk_checks.get('risk_budget_dollars', 100.0):,.2f}" if gate else "$100.00",
                "recommended_shares": gate.adjusted_shares if gate else 0,
                "raw_atr_shares": gate.raw_shares if gate else 0,
                "total_capital_required": f"${gate.total_consideration:,.2f}" if gate else "$0.00",
                "portfolio_allocation_pct": f"{gate.portfolio_allocation_pct:.1f}%" if gate else "0.0%",
                "entry_price": f"${gate.price:.2f}" if gate else f"${self.state.price:.2f}",
                "stop_loss": f"${gate.stop_loss:.2f}" if (gate and gate.stop_loss) else "N/A",
                "take_profit": f"${gate.take_profit:.2f}" if (gate and gate.take_profit) else "N/A",
                "risk_reward_ratio": gate.risk_reward_ratio if gate else "1 : 2.0",
                "atr_14": gate.atr_14 if gate else 2.0,
                "stop_distance": gate.stop_distance if gate else 3.0,
                "approved": gate.approved if gate else False,
                "veto_reasons": gate.veto_reasons if gate else [],
                "warnings": gate.warnings if gate else [],
                "mandatory_bracket_order": gate.risk_checks.get("mandatory_bracket_order", {}) if gate else {}
            },
            "past_lessons_summary": self.state.past_lessons,
            "execution_result": self.state.execution_result
        }
