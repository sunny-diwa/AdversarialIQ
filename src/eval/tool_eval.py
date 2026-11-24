"""
AdversarialIQ Agentic Architecture - Financial Tool Selection & Execution Evaluator
Validates tool dispatching, schema adherence, argument formatting, and loop protection.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

from src.core.config import SP500_MAP

logger = logging.getLogger("ToolEvaluator")


class ToolCallEvaluator:
    """Evaluates whether agent tool invocations are accurate, loop-free, and correctly parameterized."""

    VALID_TOOLS = {
        "get_company_news", "get_stock_technicals", "get_sec_filings", "get_insider_activity",
        "get_macro_regime", "get_earnings_calendar", "get_market_movers", "scan_sp500_stocks",
        "get_sp500_sectors", "get_market_benchmarks", "get_company_profile", "get_company_ecosystem",
        "run_backtest", "run_adversarial_tribunal", "evaluate_risk_guardrail", "execute_paper_trade",
        "get_portfolio_status", "get_desk_briefing", "get_post_mortem_lessons",
        "query_agent_memory", "rewrite_agent_memory"
    }

    @classmethod
    def evaluate(
        cls,
        tool_name: str,
        arguments: Dict[str, Any],
        call_history: Optional[List[str]] = None
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        Evaluates a tool call specification.
        Returns: (score [0-100], issues_list, audit_details)
        """
        score = 100.0
        issues = []
        details = {
            "tool_name": tool_name,
            "arguments": arguments
        }

        # 1. Tool Name Validity
        if tool_name not in cls.VALID_TOOLS:
            score -= 50.0
            issues.append(f"UNKNOWN_TOOL: Tool '{tool_name}' is not registered in the institutional catalog")

        # 2. Argument Validation (Symbol check)
        sym = arguments.get("symbol")
        if sym is not None:
            clean_sym = str(sym).strip().upper()
            details["clean_symbol"] = clean_sym
            if not clean_sym:
                score -= 30.0
                issues.append("EMPTY_SYMBOL: Tool requires a valid stock symbol argument")
            elif clean_sym not in SP500_MAP and not clean_sym.startswith("^"):
                score -= 15.0
                issues.append(f"UNRECOGNIZED_TICKER: Symbol '{clean_sym}' not found in S&P 500 catalog")

        # 3. Numeric bounds validation (e.g. limit or quantity)
        if "limit" in arguments:
            try:
                lim = int(arguments["limit"])
                if lim <= 0 or lim > 100:
                    score -= 15.0
                    issues.append(f"INVALID_LIMIT_RANGE: Limit {lim} must be between 1 and 100")
            except (ValueError, TypeError):
                score -= 20.0
                issues.append("NON_NUMERIC_LIMIT: 'limit' argument must be an integer")

        if "quantity" in arguments:
            try:
                qty = int(arguments["quantity"])
                if qty <= 0:
                    score -= 30.0
                    issues.append(f"NON_POSITIVE_QUANTITY: Order quantity {qty} must be > 0")
            except (ValueError, TypeError):
                score -= 30.0
                issues.append("NON_NUMERIC_QUANTITY: 'quantity' argument must be an integer")

        # 4. Recursive Loop Detection
        if call_history:
            details["call_history_len"] = len(call_history)
            sig = f"{tool_name}:{str(sorted(arguments.items()))}"
            identical_calls = sum(1 for c in call_history if c == sig)
            if identical_calls >= 2:
                score -= 40.0
                issues.append(f"RECURSIVE_LOOP_DETECTED: Tool '{tool_name}' invoked {identical_calls + 1} times with identical parameters")

        final_score = max(0.0, min(100.0, score))
        details["tool_accuracy_score"] = final_score
        return final_score, issues, details
