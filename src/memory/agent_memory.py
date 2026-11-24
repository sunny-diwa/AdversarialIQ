"""
AdversarialIQ Agentic Architecture - Agent Memory & Track Record Engine
Persistently records, indexes, queries, and rewrites modular JSON memory parts:
- data/memory/strategies.json   (Active quantitative strategies driven, win rates, rules)
- data/memory/blunders.json     (Top all-time blunders, worst losses, root-cause post-mortems)
- data/memory/gains.json        (Hall of fame biggest wins, winning catalysts, conviction scores)
- data/memory/reflections.json  (Episodic lessons extracted from trades)
- data/memory/theses.json       (Historical trade court debate trials & judicial rulings)
- data/memory/kpis.json         (All-time performance telemetry and win rates)

All parts can be dynamically queried or rewritten by the autonomous agent via tools.
Also synchronized with SQLite (data/adversarial_memory.db).
"""

import json
import logging
from pathlib import Path
import sqlite3
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from src.core.config import DB_FILE, SP500_MAP

logger = logging.getLogger("AgentMemory")

MEMORY_DIR = Path("data/memory")
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

PART_FILES = {
    "strategies": MEMORY_DIR / "strategies.json",
    "blunders": MEMORY_DIR / "blunders.json",
    "gains": MEMORY_DIR / "gains.json",
    "triumphs": MEMORY_DIR / "gains.json",
    "reflections": MEMORY_DIR / "reflections.json",
    "lessons": MEMORY_DIR / "reflections.json",
    "theses": MEMORY_DIR / "theses.json",
    "journal": MEMORY_DIR / "theses.json",
    "kpis": MEMORY_DIR / "kpis.json",
    "stats": MEMORY_DIR / "kpis.json"
}


def get_connection() -> sqlite3.Connection:
    """Returns a connection to the SQLite memory database with row factory."""
    conn = sqlite3.connect(str(DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn


def _read_json(file_path: Path, default_val: Any) -> Any:
    """Safely reads a JSON file from disk."""
    if not file_path.exists():
        return default_val
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error reading JSON from {file_path}: {e}")
        return default_val


def _write_json(file_path: Path, data: Any) -> bool:
    """Safely writes formatted JSON to disk."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error writing JSON to {file_path}: {e}")
        return False


def init_agent_memory_db():
    """Initializes tables for Agent Blunders, Triumphs (Biggest Gains), and Strategies Driven in SQLite."""
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_blunders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                blunder_id TEXT UNIQUE NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                loss_amount REAL NOT NULL,
                loss_pct REAL NOT NULL,
                strategy TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                initial_thesis TEXT NOT NULL,
                the_blunder TEXT NOT NULL,
                lesson_learned TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_triumphs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                triumph_id TEXT UNIQUE NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                gain_amount REAL NOT NULL,
                gain_pct REAL NOT NULL,
                strategy TEXT NOT NULL,
                entry_price REAL,
                exit_price REAL,
                winning_thesis TEXT NOT NULL,
                conviction_score INTEGER NOT NULL,
                holding_period TEXT,
                created_at TEXT NOT NULL
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS agent_strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL,
                win_rate_pct REAL NOT NULL,
                total_trades INTEGER NOT NULL,
                winning_trades INTEGER NOT NULL,
                losing_trades INTEGER NOT NULL,
                total_pnl REAL NOT NULL,
                profit_factor REAL NOT NULL,
                max_drawdown_pct REAL NOT NULL,
                active_status TEXT NOT NULL,
                risk_rules TEXT NOT NULL,
                last_run TEXT NOT NULL
            )
        """)

        cursor.execute("CREATE INDEX IF NOT EXISTS idx_blunders_symbol ON agent_blunders(symbol);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_triumphs_symbol ON agent_triumphs(symbol);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_strategies_name ON agent_strategies(name);")
        conn.commit()


# Initialize SQLite tables
try:
    init_agent_memory_db()
except Exception as e:
    logger.error(f"Error initializing agent memory tables: {e}")


class AgentMemory:
    """
    Modular Institutional Agent Memory Interface.
    Reads and rewrites JSON files in data/memory/ with dual SQLite persistence.
    """

    @classmethod
    def list_parts(cls) -> List[str]:
        """Returns the list of accessible memory partitions."""
        return ["strategies", "blunders", "gains", "reflections", "theses", "kpis"]

    @classmethod
    def get_part_data(cls, part: str) -> Any:
        """Reads the exact JSON content for any memory partition."""
        p = part.lower().strip()
        fpath = PART_FILES.get(p)
        if not fpath:
            raise ValueError(f"Unknown memory partition '{part}'. Valid parts: {cls.list_parts()}")
        default_val = {} if p in ["kpis", "stats"] else []
        return _read_json(fpath, default_val)

    @classmethod
    def rewrite_part(
        cls,
        part: str,
        data: Any,
        operation: str = "rewrite"
    ) -> Dict[str, Any]:
        """
        Allows the autonomous agent to update, append to, or rewrite any part of memory.
        - operation='rewrite': Replaces the entire JSON file with new data.
        - operation='append': Appends a single record (or list of records) to a collection partition.
        - operation='update_item': Finds an item by its ID key and updates its fields.
        """
        p = part.lower().strip()
        fpath = PART_FILES.get(p)
        if not fpath:
            return {
                "success": False,
                "error": f"Unknown memory partition '{part}'. Valid partitions: {cls.list_parts()}"
            }

        existing = cls.get_part_data(p)

        if operation == "rewrite":
            success = _write_json(fpath, data)
            if success:
                cls._sync_json_to_sqlite(p, data)
            return {
                "success": success,
                "part": p,
                "operation": "rewrite",
                "message": f"Successfully rewritten {fpath.name}",
                "item_count": len(data) if isinstance(data, list) else len(data.keys())
            }

        elif operation == "append":
            if not isinstance(existing, list):
                return {"success": False, "error": f"Partition '{p}' is not a list; cannot append."}

            if isinstance(data, list):
                existing.extend(data)
            else:
                existing.append(data)

            success = _write_json(fpath, existing)
            if success:
                cls._sync_json_to_sqlite(p, existing)
            return {
                "success": success,
                "part": p,
                "operation": "append",
                "message": f"Successfully appended new entry to {fpath.name}",
                "total_items": len(existing)
            }

        elif operation == "update_item":
            if not isinstance(existing, list):
                return {"success": False, "error": f"Partition '{p}' is not a list; cannot update_item."}

            if not isinstance(data, dict):
                return {"success": False, "error": "Item data must be a dictionary with an identifying key."}

            # Find matching ID key: strategy_id, blunder_id, triumph_id, trade_id, id
            id_val = (
                data.get("strategy_id") or data.get("blunder_id") or
                data.get("triumph_id") or data.get("trade_id") or data.get("id")
            )
            if not id_val:
                return {"success": False, "error": "Data must provide an identifying ID key to update."}

            updated = False
            for i, item in enumerate(existing):
                curr_id = (
                    item.get("strategy_id") or item.get("blunder_id") or
                    item.get("triumph_id") or item.get("trade_id") or item.get("id")
                )
                if curr_id == id_val:
                    existing[i].update(data)
                    updated = True
                    break

            if not updated:
                existing.append(data)

            success = _write_json(fpath, existing)
            if success:
                cls._sync_json_to_sqlite(p, existing)
            return {
                "success": success,
                "part": p,
                "operation": "update_item",
                "updated_id": id_val,
                "message": f"Successfully updated item {id_val} in {fpath.name}"
            }

        else:
            return {"success": False, "error": f"Unsupported operation '{operation}'. Use 'rewrite', 'append', or 'update_item'."}

    @classmethod
    def _sync_json_to_sqlite(cls, part: str, data: Any):
        """Synchronizes rewritten JSON records back into SQLite tables."""
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                if part in ["blunders"] and isinstance(data, list):
                    for b in data:
                        cursor.execute("""
                            INSERT OR REPLACE INTO agent_blunders (
                                blunder_id, symbol, action, loss_amount, loss_pct, strategy,
                                entry_price, exit_price, initial_thesis, the_blunder, lesson_learned, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            b.get("blunder_id"), b.get("symbol"), b.get("action", "BUY"),
                            float(b.get("loss_amount", 0.0)), float(b.get("loss_pct", 0.0)),
                            b.get("strategy", ""), b.get("entry_price"), b.get("exit_price"),
                            b.get("initial_thesis", ""), b.get("the_blunder", ""),
                            b.get("lesson_learned", ""), b.get("created_at", "")
                        ))
                    conn.commit()

                elif part in ["gains", "triumphs"] and isinstance(data, list):
                    for g in data:
                        cursor.execute("""
                            INSERT OR REPLACE INTO agent_triumphs (
                                triumph_id, symbol, action, gain_amount, gain_pct, strategy,
                                entry_price, exit_price, winning_thesis, conviction_score, holding_period, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            g.get("triumph_id"), g.get("symbol"), g.get("action", "BUY"),
                            float(g.get("gain_amount", 0.0)), float(g.get("gain_pct", 0.0)),
                            g.get("strategy", ""), g.get("entry_price"), g.get("exit_price"),
                            g.get("winning_thesis", ""), int(g.get("conviction_score", 90)),
                            g.get("holding_period", ""), g.get("created_at", "")
                        ))
                    conn.commit()

                elif part in ["strategies"] and isinstance(data, list):
                    for s in data:
                        cursor.execute("""
                            INSERT OR REPLACE INTO agent_strategies (
                                strategy_id, name, category, description, win_rate_pct, total_trades,
                                winning_trades, losing_trades, total_pnl, profit_factor, max_drawdown_pct,
                                active_status, risk_rules, last_run
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            s.get("strategy_id"), s.get("name"), s.get("category", ""),
                            s.get("description", ""), float(s.get("win_rate_pct", 0.0)),
                            int(s.get("total_trades", 0)), int(s.get("winning_trades", 0)),
                            int(s.get("losing_trades", 0)), float(s.get("total_pnl", 0.0)),
                            float(s.get("profit_factor", 1.0)), float(s.get("max_drawdown_pct", 0.0)),
                            s.get("active_status", "ACTIVE"), s.get("risk_rules", ""), s.get("last_run", "")
                        ))
                    conn.commit()
        except Exception as e:
            logger.debug(f"SQLite sync notice for {part}: {e}")

    @classmethod
    def get_top_blunders(cls, limit: int = 5, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves top blunders from blunders.json."""
        all_blunders = cls.get_part_data("blunders")
        if symbol:
            sym = symbol.strip().upper()
            filtered = [b for b in all_blunders if b.get("symbol") == sym]
            return filtered[:limit] if filtered else all_blunders[:limit]
        return all_blunders[:limit]

    @classmethod
    def get_biggest_gains(cls, limit: int = 5, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieves all-time biggest gains from gains.json."""
        all_gains = cls.get_part_data("gains")
        if symbol:
            sym = symbol.strip().upper()
            filtered = [g for g in all_gains if g.get("symbol") == sym]
            return filtered[:limit] if filtered else all_gains[:limit]
        return all_gains[:limit]

    @classmethod
    def get_strategies_driven(cls) -> List[Dict[str, Any]]:
        """Retrieves active strategies from strategies.json."""
        return cls.get_part_data("strategies")

    @classmethod
    def get_memory_summary_kpis(cls) -> Dict[str, Any]:
        """Calculates or retrieves aggregate historical KPIs."""
        kpis_file = cls.get_part_data("kpis")
        if kpis_file and isinstance(kpis_file, dict) and kpis_file.get("total_historical_trades"):
            return kpis_file

        strats = cls.get_strategies_driven()
        blunders = cls.get_top_blunders(10)
        gains = cls.get_biggest_gains(10)

        total_trades = sum(s.get("total_trades", 0) for s in strats)
        total_wins = sum(s.get("winning_trades", 0) for s in strats)
        net_pnl = sum(s.get("total_pnl", 0.0) for s in strats)
        avg_win_rate = (total_wins / total_trades * 100) if total_trades > 0 else 0.0

        worst_blunder = blunders[0] if blunders else {}
        biggest_gain = gains[0] if gains else {}

        kpis = {
            "total_historical_trades": total_trades,
            "overall_win_rate_pct": round(avg_win_rate, 1),
            "all_time_net_pnl": round(net_pnl, 2),
            "worst_blunder_loss": worst_blunder.get("loss_amount", 0.0),
            "worst_blunder_symbol": worst_blunder.get("symbol", "--"),
            "biggest_gain_amount": biggest_gain.get("gain_amount", 0.0),
            "biggest_gain_symbol": biggest_gain.get("symbol", "--"),
            "active_strategies_count": len(strats),
            "structural_lessons_count": len(blunders),
            "last_updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        _write_json(PART_FILES["kpis"], kpis)
        return kpis

    @classmethod
    def query(
        cls,
        part: str = "all",
        symbol: Optional[str] = None,
        limit: int = 5
    ) -> Dict[str, Any]:
        """
        Main query entry point for the agent and tools.
        Returns partition data alongside formatted institutional markdown.
        """
        p = part.lower().strip()

        if p in ["blunders", "blunder", "losses", "mistakes"]:
            data = cls.get_top_blunders(limit=limit, symbol=symbol)
            rows = []
            for i, b in enumerate(data, 1):
                rows.append(
                    f"| `#{i}` | **{b['symbol']}** | `<span style=\"color:#ef4444;\">-${abs(b['loss_amount']):,.2f}</span>` | "
                    f"`<span style=\"color:#ef4444;\">{b['loss_pct']:.1f}%</span>` | `{b['strategy']}` | "
                    f"{b['the_blunder']} | **Rule Enforced:** *{b['lesson_learned']}* |"
                )
            md = f"""### 🚨 Top All-Time Agent Blunders & Structural Post-Mortems
*Self-Critical History from `data/memory/blunders.json`*

| Rank | Ticker | Realized Loss | Loss (%) | Strategy Driven | Critical Error & Root Cause | Permanent Rule Enforced |
|:---:|:---:|:---:|:---:|:---|:---|:---|
""" + "\n".join(rows)
            return {"part": "blunders", "data": data, "formatted_markdown": md}

        elif p in ["gains", "triumphs", "winners", "wins"]:
            data = cls.get_biggest_gains(limit=limit, symbol=symbol)
            rows = []
            for i, g in enumerate(data, 1):
                rows.append(
                    f"| `#{i}` | **{g['symbol']}** | `<span style=\"color:#22c55e;\">+${g['gain_amount']:,.2f}</span>` | "
                    f"`<span style=\"color:#22c55e;\">+{g['gain_pct']:.1f}%</span>` | `{g['strategy']}` | "
                    f"{g['winning_thesis']} | `{g['conviction_score']}/100` | `{g.get('holding_period', '--')}` |"
                )
            md = f"""### 🏆 Top All-Time Biggest Gains (Hall of Fame)
*Alpha Captures from `data/memory/gains.json`*

| Rank | Ticker | Realized Gain | Return (%) | Strategy Driven | Winning Catalyst & Thesis | Conviction | Horizon |
|:---:|:---:|:---:|:---:|:---|:---|:---:|:---:|
""" + "\n".join(rows)
            return {"part": "gains", "data": data, "formatted_markdown": md}

        elif p in ["strategies", "strat", "strategy"]:
            data = cls.get_strategies_driven()
            rows = []
            for s in data:
                rows.append(
                    f"| **{s['name']}** | `{s['category']}` | `<span style=\"color:#22c55e;\">{s['win_rate_pct']:.1f}%</span>` | "
                    f"`{s['total_trades']}` | `<span style=\"color:#38bdf8;\">+${s['total_pnl']:,.2f}</span>` | "
                    f"`{s['profit_factor']:.2f}` | `🟢 {s['active_status']}` |"
                )
            md = f"""### ⚙️ Active Quantitative Strategies Driven by Agent Desk
*Live Strategy Registry from `data/memory/strategies.json`*

| Strategy Name | Category | Win Rate | Trades | Cumulative P&L | Profit Factor | Status |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
""" + "\n".join(rows)
            return {"part": "strategies", "data": data, "formatted_markdown": md}

        elif p in ["reflections", "lessons"]:
            data = cls.get_part_data("reflections")[:limit]
            rows = [
                f"- **{r.get('symbol')}** ({r.get('outcome')}): {r.get('lesson')} *[{r.get('key_factors')}]*"
                for r in data
            ]
            md = f"### 🧠 Episodic Lessons & Post-Mortem Reflections\n*Source: `data/memory/reflections.json`*\n\n" + "\n".join(rows)
            return {"part": "reflections", "data": data, "formatted_markdown": md}

        elif p in ["theses", "journal"]:
            data = cls.get_part_data("theses")[:limit]
            rows = [
                f"- **{t.get('symbol')}** [{t.get('status')}]: {t.get('action')} @ ${t.get('entry_price', 0):.2f} $\\to$ PnL: ${t.get('realized_pnl', 0):,.2f} ({t.get('pnl_pct', 0):.1f}%) | Ruling: *{t.get('judge_ruling', '')}*"
                for t in data
            ]
            md = f"### 📜 Court Debate & Trade Theses Journal\n*Source: `data/memory/theses.json`*\n\n" + "\n".join(rows)
            return {"part": "theses", "data": data, "formatted_markdown": md}

        elif p in ["kpis", "stats"]:
            kpis = cls.get_memory_summary_kpis()
            md = f"""### 📊 Agent Telemetry & Win-Rate Statistics
*Source: `data/memory/kpis.json`*

- **Total Historical Trades:** `{kpis['total_historical_trades']}`
- **Overall Historical Win Rate:** **`{kpis['overall_win_rate_pct']}%`**
- **All-Time Net Realized P&L:** **`+${kpis['all_time_net_pnl']:,.2f}`**
- **Worst Drawdown Blunder:** **`{kpis['worst_blunder_symbol']}`** (`-${abs(kpis['worst_blunder_loss']):,.2f}`)
- **Hall of Fame Winner:** **`{kpis['biggest_gain_symbol']}`** (`+${kpis['biggest_gain_amount']:,.2f}`)
- **Active Strategies Count:** `{kpis['active_strategies_count']}`"""
            return {"part": "kpis", "data": kpis, "formatted_markdown": md}

        else:
            # Default: comprehensive full overview
            md = cls.generate_memory_report_markdown()
            return {
                "part": "all",
                "kpis": cls.get_memory_summary_kpis(),
                "top_blunders": cls.get_top_blunders(5),
                "biggest_gains": cls.get_biggest_gains(5),
                "strategies_driven": cls.get_strategies_driven(),
                "formatted_markdown": md
            }

    @classmethod
    def generate_memory_report_markdown(cls) -> str:
        """Generates full Bloomberg-style audit report combining all JSON memory partitions."""
        kpis = cls.get_memory_summary_kpis()
        blunders = cls.get_top_blunders(5)
        gains = cls.get_biggest_gains(5)
        strategies = cls.get_strategies_driven()

        blunder_rows = []
        for i, b in enumerate(blunders, 1):
            blunder_rows.append(
                f"| `#{i}` | **{b['symbol']}** | `<span style=\"color:#ef4444;\">-${abs(b['loss_amount']):,.2f}</span>` | "
                f"`<span style=\"color:#ef4444;\">{b['loss_pct']:.1f}%</span>` | `{b['strategy']}` | "
                f"{b['the_blunder']} | **Rule Enforced:** *{b['lesson_learned']}* |"
            )
        blunders_table = "\n".join(blunder_rows)

        gain_rows = []
        for i, g in enumerate(gains, 1):
            gain_rows.append(
                f"| `#{i}` | **{g['symbol']}** | `<span style=\"color:#22c55e;\">+${g['gain_amount']:,.2f}</span>` | "
                f"`<span style=\"color:#22c55e;\">+{g['gain_pct']:.1f}%</span>` | `{g['strategy']}` | "
                f"{g['winning_thesis']} | `{g['conviction_score']}/100` | `{g.get('holding_period', '--')}` |"
            )
        gains_table = "\n".join(gain_rows)

        strat_rows = []
        for s in strategies:
            strat_rows.append(
                f"| **{s['name']}** | `{s['category']}` | `<span style=\"color:#22c55e;\">{s['win_rate_pct']:.1f}%</span>` | "
                f"`{s['total_trades']}` | `<span style=\"color:#38bdf8;\">+${s['total_pnl']:,.2f}</span>` | "
                f"`{s['profit_factor']:.2f}` | `🟢 {s['active_status']}` |"
            )
        strat_table = "\n".join(strat_rows)

        md = f"""### 🧠 AdversarialIQ Agent Memory & Track Record Audit
*Autonomous Trading History, Post-Mortem Blunder Registry, and Active Quantitative Strategies*
*Memory Partitions: `data/memory/{{strategies, blunders, gains, reflections, theses, kpis}}.json`*

---

#### 📊 ALL-TIME AGENT PERFORMANCE TELEMETRY:
- **Total Historical Trades:** `{kpis['total_historical_trades']}` trades executed across S&P 500
- **Overall Historical Win Rate:** **`{kpis['overall_win_rate_pct']}%`**
- **All-Time Net Realized P&L:** **`+${kpis['all_time_net_pnl']:,.2f}`**
- **Worst Drawdown Blunder:** **`{kpis['worst_blunder_symbol']}`** (`-${abs(kpis['worst_blunder_loss']):,.2f}`)
- **Hall of Fame Winner:** **`{kpis['biggest_gain_symbol']}`** (`+${kpis['biggest_gain_amount']:,.2f}`)
- **Active Strategies Driven:** `{kpis['active_strategies_count']}` quantitative desks active

---

#### 🚨 TOP 5 ALL-TIME AGENT BLUNDERS & STRUCTURAL POST-MORTEMS
*(Every catastrophic loss is recorded in `data/memory/blunders.json` and transformed into a permanent non-LLM safety rule)*

| Rank | Ticker | Loss ($) | Loss (%) | Strategy Driven | Critical Error & Root Cause | Permanent Rule Enforced |
|:---:|:---:|:---:|:---:|:---|:---|:---|
{blunders_table}

---

#### 🏆 TOP 5 ALL-TIME BIGGEST GAINS (HALL OF FAME)
*(Peak alpha captures recorded in `data/memory/gains.json` driven by 4D supply chain mapping & SEC disclosures)*

| Rank | Ticker | Realized Gain | Return (%) | Strategy Driven | Winning Catalyst & Thesis | Conviction | Horizon |
|:---:|:---:|:---:|:---:|:---|:---|:---:|:---:|
{gains_table}

---

#### ⚙️ ACTIVE QUANTITATIVE STRATEGIES DRIVEN
*(Stored in `data/memory/strategies.json` — continuous execution with automated bracket risk parameters)*

| Strategy Name | Category | Win Rate | Trades | Cumulative P&L | Profit Factor | Status |
|:---|:---|:---:|:---:|:---:|:---:|:---:|
{strat_table}

---
*Memory Protocol: All partitions are stored as human-readable JSON files and can be queried or rewritten by the agent.*"""

        return md

    @classmethod
    def get_full_memory_payload(cls) -> Dict[str, Any]:
        """Returns complete dictionary payload for REST API and UI rendering."""
        return {
            "kpis": cls.get_memory_summary_kpis(),
            "top_blunders": cls.get_top_blunders(10),
            "biggest_gains": cls.get_biggest_gains(10),
            "strategies_driven": cls.get_strategies_driven(),
            "reflections": cls.get_part_data("reflections"),
            "theses": cls.get_part_data("theses"),
            "formatted_markdown": cls.generate_memory_report_markdown()
        }


def get_agent_memory() -> AgentMemory:
    """Convenience getter for AgentMemory instance."""
    return AgentMemory()

