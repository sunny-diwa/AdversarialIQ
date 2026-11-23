"""
Adversarial Tribunal & Daily Briefing Syndicate Interface
Exposes run_adversarial_trade_tribunal using the typed AdversarialStateMachine.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.agents.state_machine import AdversarialStateMachine
from src.core.config import SP500_MAP
from src.data.macro import fetch_macro_regime
from src.execution.portfolio import load_portfolio

logger = logging.getLogger("Tribunal")


def run_adversarial_trade_tribunal(symbol: str = "NVDA", account_capital: Optional[float] = None) -> Dict[str, Any]:
    """
    Executes the full AdversarialIQ Tribunal pipeline:
    1. Agent Bull (Advocate)
    2. Agent Bear (Adversary)
    3. Agent Judge (Chief Arbiter)
    4. Deterministic Non-LLM Risk Guardrail
    5. Persistence to SQLite Thesis Journal
    """
    fsm = AdversarialStateMachine(symbol=symbol, account_capital=account_capital)
    return fsm.run_full_pipeline(auto_execute=False)


def get_daily_desk_briefing(scanner_results: Optional[list] = None) -> Dict[str, Any]:
    """FinGPT-style Morning / Desk Intelligence Note across S&P 500."""
    p = load_portfolio()
    results = scanner_results or []

    top_buys = [s for s in results if s.get("pct_change", 0) > 0 and s.get("rsi", 50) < 60][:3]
    top_hedges = [s for s in results if s.get("pct_change", 0) < 0][:2]
    macro = fetch_macro_regime()

    return {
        "date": datetime.now().strftime("%A, %B %d, %Y"),
        "timestamp": datetime.now().strftime("%H:%M:%S EST"),
        "market_regime": macro.get("regime", "NEUTRAL / SELECTIVE MOMENTUM"),
        "macro_summary": macro.get("summary", ""),
        "portfolio_health": {
            "account_equity": p.get("cash", 10000.0) + sum(pos.get("cost_basis", 0) for pos in p.get("positions", {}).values()),
            "active_positions_count": len(p.get("positions", {})),
            "cash_reserves": p.get("cash", 10000.0),
            "risk_profile": "DISCIPLINED ADVERSARIAL RISK ($10K BASE)"
        },
        "top_setups": top_buys,
        "watch_out": top_hedges
    }
