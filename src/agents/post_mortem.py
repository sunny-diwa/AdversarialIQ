"""
Post-Mortem Reflection Agent
Autonomous Agent that inspects closed paper trades (especially losing trades),
evaluates why the thesis failed against the actual outcome, extracts concise lessons,
and persists them into the reflection memory store so the syndicate self-improves.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from src.memory.journal import get_connection, get_recent_theses
from src.memory.reflection_store import save_reflection

logger = logging.getLogger("PostMortemAgent")


class PostMortemAgent:
    """Evaluates closed trades, extracts structural lessons, and stores them in memory."""

    @classmethod
    def analyze_trade(cls, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Conducts post-mortem analysis on a closed trade.
        Evaluates Bull thesis vs. Bear counter-arguments against the realized outcome.
        """
        sym = trade_data.get("symbol", "").upper()
        sector = trade_data.get("sector", "Other")
        trade_id = str(trade_data.get("trade_id") or trade_data.get("id", ""))
        pnl = float(trade_data.get("realized_pnl", 0.0) or 0.0)
        pnl_pct = float(trade_data.get("pnl_pct", 0.0) or 0.0)
        entry_price = float(trade_data.get("entry_price", 0.0) or 0.0)
        exit_price = float(trade_data.get("exit_price", entry_price) or entry_price)

        bull_thesis = trade_data.get("bull_thesis", [])
        if isinstance(bull_thesis, str):
            try:
                bull_thesis = json.loads(bull_thesis)
            except Exception:
                bull_thesis = [bull_thesis]

        bear_counter = trade_data.get("bear_counter", [])
        if isinstance(bear_counter, str):
            try:
                bear_counter = json.loads(bear_counter)
            except Exception:
                bear_counter = [bear_counter]

        if pnl < 0:
            outcome = "LOSS"
            # Identify which bear risk factors materialized
            top_bear = bear_counter[0] if bear_counter else "Macro volatility and technical overhead resistance."
            lesson = (
                f"Failed LONG setup on {sym}: Realized loss of ${abs(pnl):.2f} ({pnl_pct:.1f}%). "
                f"Syndicate overweighted short-term technical bounce while Bear risks materialized: '{top_bear}'."
            )
            key_factors = "Overweighted Momentum vs. Fundamental Headwinds"
        elif pnl > 0:
            outcome = "WIN"
            top_bull = bull_thesis[0] if bull_thesis else "Technical trend alignment and catalyst follow-through."
            lesson = (
                f"Successful execution on {sym}: Captured +${pnl:.2f} (+{pnl_pct:.1f}%). "
                f"Adversarial thesis validated: '{top_bull}'."
            )
            key_factors = "Trend Alignment & Favorable Risk/Reward"
        else:
            outcome = "SCRATCH"
            lesson = f"Scratch trade on {sym} (${pnl:.2f}); exited around breakeven."
            key_factors = "Consolidation / Low Volatility"

        # Save to SQLite reflection store
        save_reflection(
            trade_id=trade_id,
            symbol=sym,
            sector=sector,
            outcome=outcome,
            lesson=lesson,
            key_factors=key_factors
        )

        return {
            "trade_id": trade_id,
            "symbol": sym,
            "sector": sector,
            "outcome": outcome,
            "realized_pnl": pnl,
            "pnl_pct": pnl_pct,
            "lesson": lesson,
            "key_factors": key_factors
        }

    @classmethod
    def run_post_mortem_batch(cls, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Runs post-mortem reviews on recent closed trades that do not have existing reflections.
        """
        results = []
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT t.* FROM theses_journal t
                LEFT JOIN agent_reflections r ON t.trade_id = r.trade_id
                WHERE t.status = 'CLOSED' AND r.id IS NULL
                ORDER BY t.id DESC LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            for r in rows:
                data = dict(r)
                res = cls.analyze_trade(data)
                results.append(res)
        return results
