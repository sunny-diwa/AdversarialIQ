"""
AdversarialIQ Agentic Architecture - Adversarial Debate & Tribunal Evaluator
Audits the rigor, dialectical balance, and anti-confirmation bias of the 3-agent tribunal
(Agent Bull Advocate vs. Agent Bear Adversary vs. Chief Judge Magistrate).
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("TribunalEvaluator")


class AdversarialDebateEvaluator:
    """Evaluates multi-agent debate rigor, dialectical tension, and judicial synthesis."""

    @classmethod
    def evaluate(
        cls,
        tribunal_data: Dict[str, Any],
        symbol: str
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        Evaluates an Adversarial Tribunal debate packet.
        Returns: (score [0-100], issues_list, audit_details)
        """
        score = 100.0
        issues = []
        details = {}

        bull = tribunal_data.get("prosecution_bull") or tribunal_data.get("bull_case") or {}
        bear = tribunal_data.get("prosecution_bear") or tribunal_data.get("bear_case") or {}
        judge = tribunal_data.get("judge_ruling") or tribunal_data.get("judicial_risk_parameters") or {}

        # 1. Bull Argument Extraction & Depth
        bull_args = bull.get("arguments", [])
        if isinstance(bull_args, str):
            bull_args = [bull_args]
        details["bull_arguments_count"] = len(bull_args)

        if len(bull_args) == 0:
            score -= 30.0
            issues.append("MISSING_BULL_CASE: Agent Bull failed to present substantive upside arguments")
        elif len(bull_args) == 1:
            score -= 10.0
            issues.append("THIN_BULL_CASE: Agent Bull presented only a single isolated argument")

        # 2. Bear Argument Extraction & Depth (Critical for Risk Mitigation)
        bear_args = bear.get("arguments", [])
        if isinstance(bear_args, str):
            bear_args = [bear_args]
        details["bear_arguments_count"] = len(bear_args)

        if len(bear_args) == 0:
            score -= 35.0
            issues.append("MISSING_BEAR_CASE: Agent Bear failed to present downside risk counter-arguments")
        elif len(bear_args) == 1:
            score -= 10.0
            issues.append("THIN_BEAR_CASE: Agent Bear presented only anemic risk factors")

        # 3. Dialectical Balance & Confirmation Bias Check
        # If Bull has many points and Bear has virtually none (or vice versa), penalize confirmation bias
        diff = abs(len(bull_args) - len(bear_args))
        if diff >= 3 and min(len(bull_args), len(bear_args)) <= 1:
            score -= 20.0
            issues.append(f"ONE_SIDED_BIAS: Unbalanced prosecution ({len(bull_args)} Bull vs. {len(bear_args)} Bear arguments)")

        # 4. Chief Judge Adjudication & Conviction
        conviction = tribunal_data.get("conviction_score")
        if conviction is None:
            conviction = judge.get("conviction_score")

        details["conviction_score"] = conviction
        if conviction is None:
            score -= 20.0
            issues.append("UNSCORED_RULING: Chief Judge failed to assign quantitative conviction score [0-100]")
        elif not (0 <= float(conviction) <= 100):
            score -= 25.0
            issues.append(f"OUT_OF_BOUNDS_CONVICTION: Conviction score {conviction} must be between 0 and 100")

        verdict = tribunal_data.get("verdict") or judge.get("verdict")
        details["verdict"] = verdict
        if not verdict or verdict not in ["BUY", "SELL", "HOLD", "VETO", "VETOED"]:
            score -= 15.0
            issues.append(f"AMBIGUOUS_VERDICT: Adjudicated ruling '{verdict}' is not an institutional actionable verdict")

        final_score = max(0.0, min(100.0, score))
        details["adversarial_score"] = final_score
        return final_score, issues, details
