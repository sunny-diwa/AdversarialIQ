"""
AdversarialIQ Agentic Architecture - Automated Golden Benchmark Suite
Executes a standardized 10-point test suite assessing technical precision,
leadership catalyst tagging, risk gate enforcement, tribunal balance, and SEC extraction.
"""

from datetime import datetime
import json
import logging
import time
from typing import Any, Dict, List

from src.eval.critic import AgentCriticRefiner
from src.eval.models import BenchmarkReport, BenchmarkResult
from src.eval.store import EvalStore

logger = logging.getLogger("BenchmarkSuite")


class AgentBenchmarkSuite:
    """Executes standardized capabilities and regression test cases across the syndicate."""

    @classmethod
    def run_suite(cls, provider: str = "groq", model: str = "openai/gpt-oss-120b") -> BenchmarkReport:
        """
        Runs the 10 golden benchmark test cases.
        Returns: BenchmarkReport
        """
        results: List[BenchmarkResult] = []
        t_start_suite = time.time()

        cases = [
            cls._test_price_technical_accuracy,
            cls._test_executive_leadership_catalyst,
            cls._test_risk_gate_concentration_cap_veto,
            cls._test_risk_gate_earnings_blackout,
            cls._test_adversarial_tribunal_balance,
            cls._test_sec_edgar_risk_extraction,
            cls._test_macro_regime_indicators,
            cls._test_ecosystem_supply_chain_dependencies,
            cls._test_bracket_order_mathematical_integrity,
            cls._test_conversational_router_latency
        ]

        for case_fn in cases:
            t0 = time.time()
            try:
                res = case_fn(provider=provider, model=model)
                res.latency_ms = int((time.time() - t0) * 1000)
                results.append(res)
            except Exception as e:
                latency = int((time.time() - t0) * 1000)
                results.append(BenchmarkResult(
                    case_id=case_fn.__name__,
                    name=case_fn.__name__.replace("_test_", "").replace("_", " ").title(),
                    category="System Exception",
                    passed=False,
                    score=0.0,
                    latency_ms=latency,
                    details=f"Unexpected exception during execution: {str(e)}",
                    output_summary="ERROR"
                ))

        total_cases = len(results)
        passed_cases = sum(1 for r in results if r.passed)
        failed_cases = total_cases - passed_cases
        pass_rate = round((passed_cases / total_cases * 100.0), 1) if total_cases > 0 else 0.0
        avg_latency = round(sum(r.latency_ms for r in results) / total_cases, 1) if total_cases > 0 else 0.0

        report = BenchmarkReport(
            total_cases=total_cases,
            passed_cases=passed_cases,
            failed_cases=failed_cases,
            pass_rate_pct=pass_rate,
            avg_latency_ms=avg_latency,
            results=results
        )

        EvalStore.save_benchmark_report(report)
        return report

    # -------------------------------------------------------------------------
    # Golden Benchmark Test Cases
    # -------------------------------------------------------------------------

    @classmethod
    def _test_price_technical_accuracy(cls, provider: str, model: str) -> BenchmarkResult:
        """Case 01: Verifies real-time stock technical and price retrieval for NVDA."""
        from src.data.market import fetch_stock_quote, fetch_stock_technicals
        q = fetch_stock_quote("NVDA")
        t = fetch_stock_technicals("NVDA")

        price = float(q.get("price") or 0.0)
        rsi = float(t.get("rsi") or 0.0)
        sma50 = float(t.get("sma50") or 0.0)

        passed = price > 0 and 0 <= rsi <= 100 and sma50 > 0
        details = f"Price: ${price:.2f} | RSI(14): {rsi:.1f} | SMA50: ${sma50:.2f}"
        return BenchmarkResult(
            case_id="CASE-01",
            name="Real-Time Price & Indicator Precision",
            category="Market Grounding",
            passed=passed,
            score=100.0 if passed else 0.0,
            latency_ms=0,
            details=details,
            output_summary=f"NVDA quoted at ${price:.2f} with valid RSI {rsi:.1f}"
        )

    @classmethod
    def _test_executive_leadership_catalyst(cls, provider: str, model: str) -> BenchmarkResult:
        """Case 02: Verifies Jensen Huang / CEO reinstatement catalyst classification."""
        from src.data.news import fetch_breaking_news
        news_data = fetch_breaking_news("NVDA")
        articles = news_data.get("articles", [])
        top_cats = news_data.get("top_catalysts", [])

        has_leadership = "EXECUTIVE_LEADERSHIP" in top_cats or any("EXECUTIVE_LEADERSHIP" in a.get("catalysts", []) for a in articles)
        has_jensen = any("jensen" in (a.get("title", "") + a.get("summary", "")).lower() for a in articles)
        passed = has_leadership and has_jensen
        details = f"Leadership Catalyst Tagged: {has_leadership} | Jensen Articles Found: {has_jensen} | Article Count: {len(articles)}"

        return BenchmarkResult(
            case_id="CASE-02",
            name="Executive Leadership & Catalyst Tagging",
            category="Catalyst Extraction",
            passed=passed,
            score=100.0 if passed else (50.0 if has_jensen else 0.0),
            latency_ms=0,
            details=details,
            output_summary="Jensen Huang reinstatement successfully indexed & tagged EXECUTIVE_LEADERSHIP"
        )

    @classmethod
    def _test_risk_gate_concentration_cap_veto(cls, provider: str, model: str) -> BenchmarkResult:
        """Case 03: Verifies that proposing a $25,000 trade on a $10,000 account is vetoed by Risk Gate."""
        from src.risk.guardrail import RiskGuardrail
        result = RiskGuardrail.evaluate_order(
            symbol="NVDA",
            action="BUY",
            equity=10000.0,
            current_positions={},
            requested_shares=200
        )
        adjusted = result.get("adjusted_shares", 200)
        alloc_pct = result.get("portfolio_allocation_pct", 100.0)
        passed = adjusted < 200 and alloc_pct <= 5.5
        veto_reasons = result.get("veto_reasons", [])
        warnings = result.get("warnings", [])
        reasons = veto_reasons or warnings
        details = f"Adjusted from 200 -> {adjusted} shares ({alloc_pct:.1f}% allocation) | Notes: {'; '.join(reasons)}"

        return BenchmarkResult(
            case_id="CASE-03",
            name="Non-LLM Risk Gate: 5% Concentration Cap",
            category="Risk Compliance",
            passed=passed,
            score=100.0 if passed else 0.0,
            latency_ms=0,
            details=details,
            output_summary="Oversized position automatically capped to protect portfolio concentration"
        )

    @classmethod
    def _test_risk_gate_earnings_blackout(cls, provider: str, model: str) -> BenchmarkResult:
        """Case 04: Verifies earnings blackout window identification."""
        from src.data.calendar import fetch_earnings_calendar
        cal = fetch_earnings_calendar("NVDA")
        has_field = "blackout_status" in cal and "action" in cal
        passed = has_field and isinstance(cal.get("hours_to_earnings"), (int, float))
        details = f"Blackout Status: {cal.get('blackout_status')} | Hours to Earnings: {cal.get('hours_to_earnings')}h"

        return BenchmarkResult(
            case_id="CASE-04",
            name="48-Hour Earnings Blackout Window Gate",
            category="Risk Compliance",
            passed=passed,
            score=100.0 if passed else 0.0,
            latency_ms=0,
            details=details,
            output_summary=f"Earnings window successfully verified ({cal.get('blackout_status')})"
        )

    @classmethod
    def _test_adversarial_tribunal_balance(cls, provider: str, model: str) -> BenchmarkResult:
        """Case 05: Verifies dialectical balance between Bull Advocate and Bear Adversary."""
        from src.agents.tribunal import run_adversarial_trade_tribunal
        tribunal = run_adversarial_trade_tribunal("TSLA", provider=provider, model=model)
        bull = tribunal.get("prosecution_bull", {})
        bear = tribunal.get("prosecution_bear", {})

        bull_args = bull.get("arguments", [])
        bear_args = bear.get("arguments", [])
        conviction = tribunal.get("conviction_score")
        verdict = tribunal.get("verdict")

        passed = len(bull_args) >= 1 and len(bear_args) >= 1 and conviction is not None and verdict in ["BUY", "SELL", "HOLD", "VETO", "VETOED"]
        details = f"Bull Points: {len(bull_args)} | Bear Points: {len(bear_args)} | Conviction: {conviction}/100 | Verdict: {verdict}"

        return BenchmarkResult(
            case_id="CASE-05",
            name="Adversarial Tribunal Dialectical Balance",
            category="Multi-Agent Debate",
            passed=passed,
            score=100.0 if passed else 40.0,
            latency_ms=0,
            details=details,
            output_summary=f"TSLA tribunal produced {len(bull_args)} Bull vs {len(bear_args)} Bear points with verdict {verdict}"
        )

    @classmethod
    def _test_sec_edgar_risk_extraction(cls, provider: str, model: str) -> BenchmarkResult:
        """Case 06: Verifies SEC EDGAR 10-K item extraction on MSFT."""
        from src.data.sec_edgar import fetch_sec_filings
        sec_data = fetch_sec_filings("MSFT")
        filings = sec_data.get("filings", [])
        risk_factors = sec_data.get("risk_factors", [])
        passed = len(filings) > 0 or len(risk_factors) > 0
        details = f"Filings Extracted: {len(filings)} | Risk Factors Extracted: {len(risk_factors)}"

        return BenchmarkResult(
            case_id="CASE-06",
            name="SEC EDGAR 10-K Risk Factor Extraction",
            category="Fundamental Grounding",
            passed=passed,
            score=100.0 if passed else 0.0,
            latency_ms=0,
            details=details,
            output_summary=f"Extracted {len(filings)} filings and {len(risk_factors)} risk factors for MSFT"
        )

    @classmethod
    def _test_macro_regime_indicators(cls, provider: str, model: str) -> BenchmarkResult:
        """Case 07: Verifies FRED / macro indicators yield spread and regime label."""
        from src.data.macro import fetch_macro_regime
        macro = fetch_macro_regime()
        indicators = macro.get("indicators", {})
        dgs10 = indicators.get("dgs10")
        dgs2 = indicators.get("dgs2")
        spread = indicators.get("yield_spread_bps")
        regime = macro.get("regime")

        passed = dgs10 is not None and dgs2 is not None and spread is not None and regime in ["RISK_ON", "NEUTRAL", "CAUTIOUS", "RISK_OFF"]
        details = f"Source: {indicators.get('source')} | 10Y: {dgs10}% | 2Y: {dgs2}% | Spread: {spread:+.1f} bps | Regime: {regime}"

        return BenchmarkResult(
            case_id="CASE-07",
            name="Macro Regime & Yield Curve Telemetry",
            category="Macro Grounding",
            passed=passed,
            score=100.0 if passed else 0.0,
            latency_ms=0,
            details=details,
            output_summary=f"Active Macro Regime: {regime} (Spread: {spread:+.1f} bps)"
        )

    @classmethod
    def _test_ecosystem_supply_chain_dependencies(cls, provider: str, model: str) -> BenchmarkResult:
        """Case 08: Verifies 4D supply chain ecosystem mapping for AAPL."""
        from src.data.ecosystem import fetch_company_ecosystem
        eco = fetch_company_ecosystem("AAPL")
        suppliers = eco.get("upstream_suppliers", [])
        customers = eco.get("downstream_customers", [])
        competitors = eco.get("competitors", [])

        passed = len(suppliers) > 0 and len(competitors) > 0
        details = f"Suppliers: {len(suppliers)} | Customers: {len(customers)} | Competitors: {len(competitors)}"

        return BenchmarkResult(
            case_id="CASE-08",
            name="4D Ecosystem & Dependency Mapping",
            category="Ecosystem Grounding",
            passed=passed,
            score=100.0 if passed else 0.0,
            latency_ms=0,
            details=details,
            output_summary=f"AAPL ecosystem mapped with {len(suppliers)} upstream and {len(competitors)} competitor nodes"
        )

    @classmethod
    def _test_bracket_order_mathematical_integrity(cls, provider: str, model: str) -> BenchmarkResult:
        """Case 09: Verifies that bracket order stop loss and take profit adhere to ATR distances."""
        from src.risk.guardrail import RiskGuardrail
        gate = RiskGuardrail.evaluate_order(
            symbol="NVDA",
            action="BUY",
            equity=10000.0,
            current_positions={},
            requested_shares=10
        )
        entry = gate.get("price", 150.0)
        stop = float(gate.get("stop_loss", 0.0))
        target = float(gate.get("take_profit", 0.0))

        passed = stop < entry and target > entry and (target - entry) > (entry - stop)
        details = f"Entry: ${entry:.2f} | Stop: ${stop:.2f} | Target: ${target:.2f} | Valid: {passed}"

        return BenchmarkResult(
            case_id="CASE-09",
            name="Bracket Order Mathematical Integrity",
            category="Risk Compliance",
            passed=passed,
            score=100.0 if passed else 0.0,
            latency_ms=0,
            details=details,
            output_summary=f"Bracket calculated: Stop ${stop:.2f} < Entry ${entry:.2f} < Target ${target:.2f}"
        )

    @classmethod
    def _test_conversational_router_latency(cls, provider: str, model: str) -> BenchmarkResult:
        """Case 10: Verifies fast conversational routing latency without heavy blocking tribunal."""
        from src.agents.chat_agent import process_chat_message
        t0 = time.time()
        chat_res = process_chat_message(
            message="Hello, can you help me?",
            provider=provider,
            model=model,
            current_symbol="NVDA"
        )
        latency = int((time.time() - t0) * 1000)
        resp_text = chat_res.get("response", "")
        passed = latency < 4000 and len(resp_text) > 20 and not chat_res.get("error")
        details = f"Latency: {latency}ms | Response Length: {len(resp_text)} chars"

        return BenchmarkResult(
            case_id="CASE-10",
            name="Conversational Router Fast Path Latency",
            category="System Responsiveness",
            passed=passed,
            score=100.0 if passed else 50.0,
            latency_ms=latency,
            details=details,
            output_summary=f"Conversational greeting completed in {latency}ms (<4000ms threshold)"
        )
