"""
Persistent Agent Reflection Store
Stores and retrieves post-mortem lessons extracted from closed trades.
Enables self-improving agents by injecting past lessons into future adversarial debates.
"""

import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.config import DB_FILE, SP500_MAP

logger = logging.getLogger("ReflectionStore")


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def save_reflection(
    trade_id: str,
    symbol: str,
    sector: str,
    outcome: str,  # LOSS, WIN, SCRATCH
    lesson: str,
    key_factors: Optional[str] = None
) -> bool:
    """Stores a structured post-mortem reflection lesson in SQLite."""
    sym = symbol.strip().upper()
    sec = sector or SP500_MAP.get(sym, {}).get("sector", "Other")
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO agent_reflections (
                    trade_id, symbol, sector, outcome, lesson, key_factors, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_id,
                sym,
                sec,
                outcome.upper(),
                lesson.strip(),
                (key_factors or "").strip(),
                created_at
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save reflection for {sym}: {e}")
            return False


def retrieve_reflections(
    symbol: Optional[str] = None,
    sector: Optional[str] = None,
    limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Retrieves the most relevant past lessons for a given ticker or its GICS sector.
    Prioritizes ticker-specific lessons, followed by sector-level lessons.
    """
    sym = (symbol or "").strip().upper()
    sec = sector or (SP500_MAP.get(sym, {}).get("sector", "Other") if sym else None)

    results = []
    with get_connection() as conn:
        cursor = conn.cursor()

        # 1. Fetch exact ticker matches
        if sym:
            cursor.execute("""
                SELECT * FROM agent_reflections
                WHERE symbol = ?
                ORDER BY id DESC LIMIT ?
            """, (sym, limit))
            for r in cursor.fetchall():
                results.append(dict(r))

        # 2. Fetch sector-level matches if space remains
        remaining = limit - len(results)
        if remaining > 0 and sec:
            cursor.execute("""
                SELECT * FROM agent_reflections
                WHERE sector = ? AND symbol != ?
                ORDER BY id DESC LIMIT ?
            """, (sec, sym, remaining))
            for r in cursor.fetchall():
                results.append(dict(r))

        # 3. Fetch general lessons if still empty
        if not results:
            cursor.execute("""
                SELECT * FROM agent_reflections
                ORDER BY id DESC LIMIT ?
            """, (limit,))
            for r in cursor.fetchall():
                results.append(dict(r))

    return results


def format_lessons_for_prompt(symbol: str) -> str:
    """Formats past post-mortem lessons into a clean Markdown block for LLM prompts."""
    lessons = retrieve_reflections(symbol=symbol, limit=3)
    if not lessons:
        return "No historical post-mortem penalties recorded on this ticker or sector."

    lines = []
    for l in lessons:
        lines.append(
            f"• [{l['outcome']} on {l['symbol']}] {l['lesson']} (Key Factors: {l.get('key_factors', 'Technical/Fundamental')})"
        )
    return "\n".join(lines)
