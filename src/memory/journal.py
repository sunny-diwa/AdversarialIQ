"""
Trade & Thesis Journal (SQLite Storage)
Persistently logs every adversarial debate, Bull/Bear arguments, conviction score,
entry/exit execution prices, bracket orders, and realized P&L.
Database location: data/adversarial_memory.db
"""

import json
import logging
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.config import DB_FILE, SP500_MAP

logger = logging.getLogger("ThesisJournal")


def get_connection() -> sqlite3.Connection:
    """Returns a connection to the SQLite memory database with row factory."""
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def init_journal_db():
    """Initializes tables for Trade & Thesis Journal and Agent Reflections."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS theses_journal (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT UNIQUE,
                symbol TEXT NOT NULL,
                sector TEXT,
                action TEXT NOT NULL,
                entry_price REAL NOT NULL,
                exit_price REAL,
                shares INTEGER NOT NULL,
                stop_loss REAL,
                take_profit REAL,
                conviction_score INTEGER,
                bull_thesis TEXT,
                bear_counter TEXT,
                judge_ruling TEXT,
                risk_gate_decision TEXT,
                realized_pnl REAL DEFAULT 0.0,
                pnl_pct REAL DEFAULT 0.0,
                status TEXT NOT NULL, -- OPEN, CLOSED, VETOED
                opened_at TEXT NOT NULL,
                closed_at TEXT
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_reflections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trade_id TEXT,
                symbol TEXT NOT NULL,
                sector TEXT,
                outcome TEXT NOT NULL, -- LOSS, WIN, SCRATCH
                lesson TEXT NOT NULL,
                key_factors TEXT,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_journal_symbol ON theses_journal(symbol);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_journal_status ON theses_journal(status);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reflections_symbol ON agent_reflections(symbol);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_reflections_sector ON agent_reflections(sector);
        """)
        conn.commit()


# Initialize tables on import
try:
    init_journal_db()
except Exception as e:
    logger.error(f"Error initializing journal database: {e}")


def log_trade_thesis(
    trade_id: str,
    symbol: str,
    action: str,
    entry_price: float,
    shares: int,
    bull_arguments: List[str],
    bear_arguments: List[str],
    conviction_score: int,
    judge_ruling: str,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    risk_gate_decision: Optional[Dict[str, Any]] = None,
    status: str = "OPEN"
) -> bool:
    """Logs an adversarial tribunal debate thesis to SQLite."""
    sym = symbol.strip().upper()
    sector = SP500_MAP.get(sym, {}).get("sector", "Other")
    opened_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO theses_journal (
                    trade_id, symbol, sector, action, entry_price, shares,
                    stop_loss, take_profit, conviction_score,
                    bull_thesis, bear_counter, judge_ruling,
                    risk_gate_decision, status, opened_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_id,
                sym,
                sector,
                action.upper(),
                float(entry_price),
                int(shares),
                float(stop_loss) if stop_loss else None,
                float(take_profit) if take_profit else None,
                int(conviction_score),
                json.dumps(bull_arguments),
                json.dumps(bear_arguments),
                judge_ruling,
                json.dumps(risk_gate_decision or {}),
                status.upper(),
                opened_at
            ))
            conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to log trade thesis for {sym}: {e}")
            return False


def record_trade_close(
    symbol: str,
    exit_price: float,
    realized_pnl: float,
    trade_id: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Updates the most recent OPEN thesis for this symbol (or specific trade_id) as CLOSED with realized P&L.
    Returns the closed record dictionary for post-mortem reflection.
    """
    sym = symbol.strip().upper()
    closed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with get_connection() as conn:
        cursor = conn.cursor()
        try:
            if trade_id:
                cursor.execute("SELECT * FROM theses_journal WHERE trade_id = ?", (trade_id,))
            else:
                cursor.execute(
                    "SELECT * FROM theses_journal WHERE symbol = ? AND status = 'OPEN' ORDER BY id DESC LIMIT 1",
                    (sym,)
                )
            row = cursor.fetchone()
            if not row:
                return None

            record = dict(row)
            entry_price = float(record["entry_price"])
            pnl_pct = ((float(exit_price) - entry_price) / entry_price * 100) if entry_price > 0 else 0.0

            cursor.execute("""
                UPDATE theses_journal
                SET exit_price = ?, realized_pnl = ?, pnl_pct = ?, status = 'CLOSED', closed_at = ?
                WHERE id = ?
            """, (float(exit_price), float(realized_pnl), round(pnl_pct, 2), closed_at, record["id"]))
            conn.commit()

            record["exit_price"] = float(exit_price)
            record["realized_pnl"] = float(realized_pnl)
            record["pnl_pct"] = round(pnl_pct, 2)
            record["closed_at"] = closed_at
            record["status"] = "CLOSED"
            return record
        except Exception as e:
            logger.error(f"Failed to record trade close for {sym}: {e}")
            return None


def get_recent_theses(limit: int = 25, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
    """Returns recent recorded trade theses with parsed arguments and P&L."""
    with get_connection() as conn:
        cursor = conn.cursor()
        if symbol:
            cursor.execute(
                "SELECT * FROM theses_journal WHERE symbol = ? ORDER BY id DESC LIMIT ?",
                (symbol.strip().upper(), limit)
            )
        else:
            cursor.execute("SELECT * FROM theses_journal ORDER BY id DESC LIMIT ?", (limit,))
        
        rows = cursor.fetchall()
        results = []
        for r in rows:
            d = dict(r)
            try:
                d["bull_thesis"] = json.loads(d.get("bull_thesis") or "[]")
            except Exception:
                pass
            try:
                d["bear_counter"] = json.loads(d.get("bear_counter") or "[]")
            except Exception:
                pass
            try:
                d["risk_gate_decision"] = json.loads(d.get("risk_gate_decision") or "{}")
            except Exception:
                pass
            results.append(d)
        return results


def get_journal_stats() -> Dict[str, Any]:
    """Computes summary statistics across all journaled trades."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM theses_journal")
        total_theses = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM theses_journal WHERE status = 'OPEN'")
        open_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*), SUM(realized_pnl) FROM theses_journal WHERE status = 'CLOSED'")
        row = cursor.fetchone()
        closed_count = row[0] or 0
        total_pnl = row[1] or 0.0

        cursor.execute("SELECT COUNT(*) FROM theses_journal WHERE status = 'CLOSED' AND realized_pnl > 0")
        wins = cursor.fetchone()[0] or 0
        losses = closed_count - wins
        win_rate = (wins / closed_count * 100) if closed_count > 0 else 0.0

        return {
            "total_theses": total_theses,
            "open_theses": open_count,
            "closed_theses": closed_count,
            "total_realized_pnl": round(total_pnl, 2),
            "wins": wins,
            "losses": losses,
            "win_rate_pct": round(win_rate, 1)
        }
