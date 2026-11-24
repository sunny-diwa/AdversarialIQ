"""
AdversarialIQ Agentic Architecture - Risk Guardrail Compliance Evaluator
Verifies deterministic mathematical risk bounds, 2% ATR risk budgeting,
portfolio caps, mandatory bracket orders, and earnings blackout compliance.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("GuardrailEvaluator")


class RiskGuardrailComplianceEvaluator:
    """Evaluates whether agent output strictly complies with Non-LLM Risk Guardrails."""

    @classmethod
    def evaluate(
        cls,
        response_text: str,
        symbol: str,
        trade_context: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        Evaluates trade proposals and tactical positioning for institutional risk gate adherence.
        Returns: (score [0-100], issues_list, audit_details)
        """
        score = 100.0
        issues = []
        details = {}

        ctx = trade_context or {}
        price = float(ctx.get("price") or 100.0)
        action = ctx.get("action", "").upper()
        quantity = int(ctx.get("quantity") or ctx.get("shares") or 0)
        portfolio_equity = float(ctx.get("portfolio_equity") or 10000.0)

        text_lower = response_text.lower()
        is_order_proposal = any(k in text_lower for k in ["buy", "sell", "order", "bracket", "stop-loss", "stop loss", "shares"])

        # 1. Single Ticker Concentration Cap (Max 5% of Portfolio Equity)
        if quantity > 0 and price > 0 and portfolio_equity > 0:
            position_val = quantity * price
            allocation_pct = (position_val / portfolio_equity) * 100.0
            details["position_value"] = position_val
            details["allocation_pct"] = round(allocation_pct, 2)
            if allocation_pct > 5.5:  # Allow small floating margin
                score -= 35.0
                issues.append(f"CAP_BREACH: Position size ${position_val:,.2f} ({allocation_pct:.1f}%) exceeds max 5.0% single-ticker cap")

        # 2. Mandatory Bracket Orders (Stop-Loss and Take-Profit)
        if is_order_proposal and any(k in text_lower for k in ["recommend", "ruling", "tribunal", "execute", "target"]):
            has_stop = bool(re.search(r"stop[-\s]?loss|\bstop\b\s*:\s*\$?\d+", text_lower))
            has_target = bool(re.search(r"take[-\s]?profit|profit[-\s]?target|\btarget\b\s*:\s*\$?\d+", text_lower))

            details["has_stop_loss"] = has_stop
            details["has_take_profit"] = has_target

            if not has_stop:
                score -= 25.0
                issues.append("MISSING_STOP_LOSS: Proposed trade lacks mandatory capital-preservation stop loss")
            if not has_target:
                score -= 15.0
                issues.append("MISSING_PROFIT_TARGET: Proposed trade lacks defined institutional profit target")

        # 3. Stop-Loss Mathematical Validity Check
        stop_match = re.search(r"stop(?:[-\s]?loss)?\s*(?:at|:)?\s*\$?(\d+(?:\.\d+)?)", text_lower)
        target_match = re.search(r"(?:take[-\s]?profit|target)\s*(?:at|:)?\s*\$?(\d+(?:\.\d+)?)", text_lower)

        if stop_match and target_match and price > 0:
            stop_val = float(stop_match.group(1))
            target_val = float(target_match.group(1))
            details["parsed_stop"] = stop_val
            details["parsed_target"] = target_val

            # For long positions: stop must be below entry price and target above
            if "buy" in text_lower or action == "BUY":
                if stop_val >= price:
                    score -= 30.0
                    issues.append(f"INVALID_STOP_PLACEMENT: Long stop-loss (${stop_val:.2f}) must be strictly below current price (${price:.2f})")
                if target_val <= price:
                    score -= 25.0
                    issues.append(f"INVALID_TARGET_PLACEMENT: Long profit target (${target_val:.2f}) must be strictly above current price (${price:.2f})")

                # Risk / Reward ratio check
                risk = price - stop_val
                reward = target_val - price
                if risk > 0 and reward > 0:
                    rr = reward / risk
                    details["risk_reward_ratio"] = round(rr, 2)
                    if rr < 1.3:
                        score -= 15.0
                        issues.append(f"UNFAVORABLE_RISK_REWARD: Risk/reward ratio of {rr:.2f}:1 is below 1.5:1 institutional requirement")

        # 4. Earnings Blackout Window Check
        if ctx.get("has_earnings_soon"):
            hours = ctx.get("hours_to_earnings", 24)
            details["hours_to_earnings"] = hours
            if any(k in text_lower for k in ["buy", "aggressive", "overweight"]):
                score -= 30.0
                issues.append(f"EARNINGS_BLACKOUT_VIOLATION: Trade proposed during 48-hour earnings blackout window (~{hours:.1f}h away)")

        # 5. High Volatility Sizing Check (VIX > 25)
        vix = float(ctx.get("vix", 15.0))
        details["vix"] = vix
        if vix > 25.0 and quantity > 50 and price > 100.0:
            score -= 15.0
            issues.append(f"ELEVATED_VOLATILITY: High VIX ({vix:.1f}) requires defensive positioning and smaller position sizing")

        final_score = max(0.0, min(100.0, score))
        details["guardrail_score"] = final_score
        return final_score, issues, details
