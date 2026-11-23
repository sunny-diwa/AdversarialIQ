"""
Structured Output Schemas for AdversarialIQ Multi-Agent Syndicate
Enforces strict Pydantic validation across Bull, Bear, Judge, Risk Gate, and Execution states.
Guarantees clean, typed JSON contracts across all LLM providers and routers.
"""

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class BullProsecutionCase(BaseModel):
    """Pydantic model representing Agent Bull's prosecution case for LONG/BUY."""
    title: str = Field(default="🐂 AGENT BULL (MOMENTUM & CATALYST PROSECUTOR)")
    thesis: str = Field(description="Core investment thesis summarizing why this asset will appreciate.")
    arguments: List[str] = Field(description="Evidence points from technicals, SEC MD&A, and news catalysts.")
    key_catalysts: List[str] = Field(default_factory=list, description="Immediate catalysts supporting the move.")
    case_score: int = Field(ge=0, le=100, description="Conviction score (0-100) on the bullish thesis.")
    proposed_action: Literal["BUY", "HOLD"] = Field(default="BUY")


class BearDefenseCase(BaseModel):
    """Pydantic model representing Agent Bear's risk and defense case for SHORT/AVOID."""
    title: str = Field(default="🐻 AGENT BEAR (RISK & MACRO ADVERSARY)")
    thesis: str = Field(description="Adversarial critique highlighting key risks, downside traps, and multiple compression.")
    arguments: List[str] = Field(description="Risk points from SEC Risk Factors, insider divestment, and macro inversion.")
    downside_risks: List[str] = Field(default_factory=list, description="Top tail risks and catalysts for downside.")
    case_score: int = Field(ge=0, le=100, description="Conviction score (0-100) on the bearish risk case.")
    proposed_action: Literal["AVOID", "HEDGE", "SHORT"] = Field(default="AVOID")


class ChiefJudgeRuling(BaseModel):
    """Pydantic model representing Agent Judge's definitive verdict and risk adjudication."""
    arbiter: str = Field(default="⚖️ AGENT JUDGE (CHIEF RISK MAGISTRATE)")
    ruling: Literal[
        "APPROVED (EXECUTE BUY / LONG)",
        "REJECTED (STAND DOWN / NEUTRAL ARBITRAGE)",
        "PROHIBITED (BEARISH BIAS / SHORT OR HEDGE)"
    ]
    conviction_score: int = Field(ge=0, le=100, description="AdversarialIQ Conviction Score (0-100).")
    verdict_badge: Literal["bullish", "neutral", "bearish"]
    ruling_summary: str = Field(description="Concise rationale balancing Bull vs. Bear evidence.")
    recommended_action: Literal["BUY", "SELL", "HOLD", "VETO"]


class RiskGateVerdict(BaseModel):
    """Pydantic model for Non-LLM Risk Guardrail decision."""
    approved: bool
    symbol: str
    action: str
    sector: str
    price: float
    equity: float
    raw_shares: int
    adjusted_shares: int
    total_consideration: float
    portfolio_allocation_pct: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    risk_reward_ratio: str = "1 : 2.0"
    atr_14: float = 0.0
    stop_distance: float = 0.0
    veto_reasons: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    risk_checks: Dict[str, Any] = Field(default_factory=dict)


class TribunalState(BaseModel):
    """Tracks full cyclic workflow state across the AdversarialIQ pipeline."""
    symbol: str
    company_name: str
    price: float
    stage: str = "INTAKE"  # INTAKE, DOSSIER, BULL, BEAR, JUDGE, RISK_GATE, EXECUTION, COMPLETE
    dossier: Dict[str, Any] = Field(default_factory=dict)
    past_lessons: str = ""
    bull_case: Optional[BullProsecutionCase] = None
    bear_case: Optional[BearDefenseCase] = None
    judge_ruling: Optional[ChiefJudgeRuling] = None
    risk_gate: Optional[RiskGateVerdict] = None
    execution_result: Optional[Dict[str, Any]] = None
    completed: bool = False
