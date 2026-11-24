"""
AdversarialIQ Agentic Architecture - Evaluator & Benchmarking Data Models
Defines structured schemas for real-time evaluations, guardrail verification,
hallucination audits, and benchmarking suites.
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid


@dataclass
class EvaluationResult:
    """Represents the multi-dimensional evaluation of an agent output or trade decision."""
    symbol: str
    agent_name: str
    provider: str
    model: str
    composite_score: float
    grounding_score: float
    guardrail_score: float
    adversarial_score: float
    tool_accuracy_score: float
    tone_score: float
    verdict: str  # "PASS", "NEEDS_REVISION", "FAIL"
    passed: bool
    issues: List[str] = field(default_factory=list)
    critique: str = ""
    metrics_breakdown: Dict[str, Any] = field(default_factory=dict)
    trace_id: Optional[str] = None
    eval_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S EST"))

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkResult:
    """Result of a single test case in the golden agent evaluation suite."""
    case_id: str
    name: str
    category: str
    passed: bool
    score: float
    latency_ms: int
    details: str
    output_summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class BenchmarkReport:
    """Comprehensive regression and capability report across the agent benchmark suite."""
    benchmark_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    timestamp: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S EST"))
    total_cases: int = 0
    passed_cases: int = 0
    failed_cases: int = 0
    pass_rate_pct: float = 0.0
    avg_latency_ms: float = 0.0
    results: List[BenchmarkResult] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["results"] = [r.to_dict() if hasattr(r, "to_dict") else r for r in self.results]
        return d
