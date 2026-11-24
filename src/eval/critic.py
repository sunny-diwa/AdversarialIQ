"""
AdversarialIQ Agentic Architecture - Critic & Autonomous Self-Correction Refiner
Evaluates agent turns across grounding, risk compliance, adversarial rigor, and tool accuracy.
If the draft fails institutional standards, triggers a targeted self-correction refinement loop.
"""

from datetime import datetime
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from src.core.config import SP500_MAP
from src.eval.grounding import FactualityGroundingEvaluator
from src.eval.guardrail import RiskGuardrailComplianceEvaluator
from src.eval.models import EvaluationResult
from src.eval.store import EvalStore
from src.eval.tool_eval import ToolCallEvaluator
from src.eval.tribunal_eval import AdversarialDebateEvaluator

logger = logging.getLogger("AgentCritic")


class AgentCriticRefiner:
    """Orchestrates comprehensive multi-agent evaluation and automated self-correction."""

    @classmethod
    def evaluate_turn(
        cls,
        response_text: str,
        symbol: str,
        agent_name: str = "TradingDeskAgent",
        provider: str = "Groq",
        model: str = "openai/gpt-oss-120b",
        grounded_data: Optional[Dict[str, Any]] = None,
        trade_context: Optional[Dict[str, Any]] = None,
        tribunal_data: Optional[Dict[str, Any]] = None,
        tool_call: Optional[Dict[str, Any]] = None,
        call_history: Optional[List[str]] = None,
        trace_id: Optional[str] = None
    ) -> EvaluationResult:
        """
        Executes a holistic multi-dimensional evaluation of an agent turn.
        Returns: EvaluationResult
        """
        sym = symbol.strip().upper()
        all_issues: List[str] = []
        metrics: Dict[str, Any] = {}

        # 1. Factuality & Grounding Evaluation (Weight: 30%)
        g_score, g_issues, g_details = FactualityGroundingEvaluator.evaluate(
            response_text=response_text,
            symbol=sym,
            grounded_data=grounded_data
        )
        all_issues.extend(g_issues)
        metrics["grounding"] = g_details

        # 2. Risk Guardrail Compliance Evaluation (Weight: 35%)
        r_score, r_issues, r_details = RiskGuardrailComplianceEvaluator.evaluate(
            response_text=response_text,
            symbol=sym,
            trade_context=trade_context
        )
        all_issues.extend(r_issues)
        metrics["guardrail"] = r_details

        # 3. Adversarial Rigor & Debate Evaluation (Weight: 20%)
        if tribunal_data:
            adv_score, adv_issues, adv_details = AdversarialDebateEvaluator.evaluate(
                tribunal_data=tribunal_data,
                symbol=sym
            )
            all_issues.extend(adv_issues)
            metrics["adversarial"] = adv_details
        else:
            adv_score = 90.0  # Baseline neutral for standard conversational turns

        # 4. Tool Selection & Execution Evaluation (Weight: 10%)
        if tool_call:
            t_name = tool_call.get("tool", "")
            t_args = tool_call.get("arguments", {})
            t_score, t_issues, t_details = ToolCallEvaluator.evaluate(
                tool_name=t_name,
                arguments=t_args,
                call_history=call_history
            )
            all_issues.extend(t_issues)
            metrics["tool"] = t_details
        else:
            t_score = 100.0

        # 5. Institutional Tone & Clarity Evaluation (Weight: 5%)
        tone_score = 100.0
        # Penalize excessive exclamation marks or informal slang
        if len(re.findall(r"!{2,}", response_text)) > 0:
            tone_score -= 15.0
            all_issues.append("INFORMAL_PUNCTUATION: Excessive exclamation marks degrade institutional tone")
        if any(w in response_text.lower() for w in ["to the moon", "diamond hands", "yolo", "stonks"]):
            tone_score -= 30.0
            all_issues.append("UNPROFESSIONAL_SLANG: Inappropriate retail slang detected in quantitative note")
        tone_score = max(0.0, tone_score)

        # Weighted Composite Score Calculation
        composite = (
            (g_score * 0.30) +
            (r_score * 0.35) +
            (adv_score * 0.20) +
            (t_score * 0.10) +
            (tone_score * 0.05)
        )
        composite = round(max(0.0, min(100.0, composite)), 1)

        # Verdict Classification
        has_critical_failure = any(
            i.startswith("CAP_BREACH") or
            i.startswith("INVALID_STOP_PLACEMENT") or
            i.startswith("EARNINGS_BLACKOUT_VIOLATION") or
            i.startswith("ENTITY_CONFUSION")
            for i in all_issues
        )

        if has_critical_failure or composite < 60.0:
            verdict = "FAIL"
            passed = False
        elif composite < 80.0 or len(all_issues) > 1:
            verdict = "NEEDS_REVISION"
            passed = False
        else:
            verdict = "PASS"
            passed = True

        # Synthesis Critique
        if passed:
            critique = f"Output meets institutional quality benchmarks ({composite}/100). Factual grounding and risk parameters verified."
        else:
            critique = f"Audit flagged {len(all_issues)} issue(s): " + "; ".join(all_issues[:3])

        eval_result = EvaluationResult(
            symbol=sym,
            agent_name=agent_name,
            provider=provider,
            model=model,
            composite_score=composite,
            grounding_score=round(g_score, 1),
            guardrail_score=round(r_score, 1),
            adversarial_score=round(adv_score, 1),
            tool_accuracy_score=round(t_score, 1),
            tone_score=round(tone_score, 1),
            verdict=verdict,
            passed=passed,
            issues=all_issues,
            critique=critique,
            metrics_breakdown=metrics,
            trace_id=trace_id
        )

        # Persist to SQLite store
        EvalStore.save_evaluation(eval_result)
        return eval_result

    @classmethod
    def refine_if_needed(
        cls,
        draft_text: str,
        prompt: str,
        symbol: str,
        provider: str = "groq",
        model: str = "openai/gpt-oss-120b",
        grounded_data: Optional[Dict[str, Any]] = None,
        trade_context: Optional[Dict[str, Any]] = None,
        max_retries: int = 1
    ) -> Tuple[str, EvaluationResult]:
        """
        Runs the Critic Self-Correction Refinement Loop:
        1. Evaluates draft.
        2. If 'NEEDS_REVISION' or 'FAIL', prompts LLM with targeted feedback.
        3. Re-evaluates and returns vetted response.
        """
        eval_res = cls.evaluate_turn(
            response_text=draft_text,
            symbol=symbol,
            agent_name="SelfCorrectionLoop",
            provider=provider,
            model=model,
            grounded_data=grounded_data,
            trade_context=trade_context
        )

        if eval_res.passed or max_retries <= 0:
            return draft_text, eval_res

        # Attempt automated self-correction
        try:
            from src.llm.manager import LLMManager

            critic_prompt = f"""### 🛡️ CRITIC AUDIT FEEDBACK & SELF-CORRECTION DIRECTIVE
Your initial draft output contained institutional audit failures:
{chr(10).join([f'- {iss}' for iss in eval_res.issues])}

USER PROMPT: {prompt}
ORIGINAL DRAFT:
{draft_text}

MANDATORY CORRECTIONS:
1. Ensure all prices and metrics match grounded data for {symbol}.
2. If proposing a trade, include mandatory stop-loss (strictly below entry for longs) and target (strictly above entry).
3. Ensure position sizing does not exceed 5% portfolio risk.
4. Deliver structured, direct institutional analysis.

Please output the revised, corrected final response now."""

            correction = LLMManager.generate(
                prompt=critic_prompt,
                system_prompt="You are AdversarialIQ Senior Compliance Officer and Quality Auditor. Output the corrected response.",
                preferred_provider=provider,
                model=model,
                symbol=symbol
            )
            revised_text = correction.get("response", draft_text)

            # Re-evaluate revised output
            re_eval = cls.evaluate_turn(
                response_text=revised_text,
                symbol=symbol,
                agent_name="SelfCorrectedOutput",
                provider=provider,
                model=model,
                grounded_data=grounded_data,
                trade_context=trade_context
            )
            return revised_text, re_eval
        except Exception as e:
            logger.warning(f"Self-correction loop error: {e}")
            return draft_text, eval_res
