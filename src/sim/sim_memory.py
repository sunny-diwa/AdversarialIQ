"""
Layered Stateful Memory Engine for Adversarial Simulation:
1. Bull Personal Memory (wins, bull-trap blunders, symbol notes)
2. Bear Personal Memory (risk saves, squeeze blunders, symbol notes)
3. Execution Agent 3 Personal Memory (sizing, bracket, chop lessons)
4. Intra-Day Session Memory (08:30 pre-market brief -> hourly scans -> today's debates & trades)
5. Cross-Day Memory (day-by-day EOD ledger, lessons & carryover watchlist across the month)
"""

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("SimMemory")


class SimulationMemory:
    """Manages persistent agent, session, and cross-day memory partitions on disk."""

    def __init__(self, run_dir: Path):
        self.mem_dir = run_dir / "memory"
        self.mem_dir.mkdir(parents=True, exist_ok=True)
        self.sessions_archive_dir = self.mem_dir / "sessions"
        self.sessions_archive_dir.mkdir(parents=True, exist_ok=True)

        self.bull_path = self.mem_dir / "bull_memory.json"
        self.bear_path = self.mem_dir / "bear_memory.json"
        self.executor_path = self.mem_dir / "executor_memory.json"
        self.day_path = self.mem_dir / "day_memory.json"
        self.current_session_path = self.mem_dir / "current_session.json"

        self.bull: Dict[str, Any] = self._load_json(self.bull_path, {
            "role": "AGENT_BULL",
            "stats": {"debates_won": 0, "debates_conceded": 0, "correct_calls": 0, "blunder_calls": 0},
            "lessons": [
                "Respect 48h earnings blackouts and extreme RSI > 78 euphoria without volume expansion.",
                "Prioritize breakouts backed by VWAP hold + positive A-CIS net directional spread + downstream demand."
            ],
            "symbol_notes": {},
            "recent_events": []
        })

        self.bear: Dict[str, Any] = self._load_json(self.bear_path, {
            "role": "AGENT_BEAR",
            "stats": {"debates_won": 0, "debates_conceded": 0, "correct_calls": 0, "squeeze_blunders": 0},
            "lessons": [
                "Do not short strong fundamental catalyst momentum when VIX < 15 and stock reclaims VWAP + SMA20.",
                "Highest conviction bearish setups combine below-VWAP rejection, negative MACD cross, and negative A-CIS spread."
            ],
            "symbol_notes": {},
            "recent_events": []
        })

        self.executor: Dict[str, Any] = self._load_json(self.executor_path, {
            "role": "AGENT_EXECUTOR",
            "stats": {"total_orders": 0, "longs": 0, "shorts": 0, "holds": 0},
            "lessons": [
                "If debate ends in an unconvincing stalemate near flat levels, prefer HOLD rather than churning capital.",
                "Always ensure stops sit beyond 1.2x hourly noise (ATR/2% minimum buffer) so normal wicks do not shake out positions."
            ],
            "recent_decisions": []
        })

        self.days: List[Dict[str, Any]] = self._load_json(self.day_path, [])
        self.session: Dict[str, Any] = self._load_json(self.current_session_path, {})

    @property
    def day_memory(self) -> List[Dict[str, Any]]:
        return self.days

    def _load_json(self, path: Path, default: Any) -> Any:
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed loading memory {path}: {e}")
        return json.loads(json.dumps(default))

    def save_all(self):
        for path, obj in [
            (self.bull_path, self.bull),
            (self.bear_path, self.bear),
            (self.executor_path, self.executor),
            (self.day_path, self.days),
            (self.current_session_path, self.session),
        ]:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=2)

    # -------------------------------------------------------------------------
    # Session Lifecycle (Intra-Day Memory)
    # -------------------------------------------------------------------------

    def start_new_session(self, trade_date_str: str, macro_summary: str):
        """Initializes fresh intra-day session memory at 08:30 EST."""
        self.session = {
            "date": trade_date_str,
            "macro_open": macro_summary,
            "premarket_brief": "",
            "premarket_watchlist": [],
            "hourly_notes": [],
            "debates_today": [],
            "trades_today": [],
            "last_actions_by_symbol": {}
        }
        self.save_all()

    def record_premarket_analysis(self, brief_md: str, watchlist: List[Dict[str, Any]]):
        self.session["premarket_brief"] = brief_md[:1800]
        self.session["premarket_watchlist"] = watchlist[:12]
        self.save_all()

    def record_hourly_snapshot(self, time_label: str, triage_summary: str, symbol_states: Dict[str, Any]):
        self.session.setdefault("hourly_notes", []).append({
            "time": time_label,
            "triage_summary": triage_summary[:700],
            "prices": {k: v.get("price") for k, v in symbol_states.items()}
        })
        self.session["hourly_notes"] = self.session["hourly_notes"][-10:]
        self.save_all()

    def record_debate_outcome(
        self,
        timestamp: str,
        symbol: str,
        winner: str,
        conceded_by: Optional[str],
        rounds: int,
        action_taken: str,
        confidence: int,
        key_reason: str
    ):
        if winner == "BULL":
            self.bull["stats"]["debates_won"] += 1
            if conceded_by == "BEAR":
                self.bear["stats"]["debates_conceded"] += 1
        elif winner == "BEAR":
            self.bear["stats"]["debates_won"] += 1
            if conceded_by == "BULL":
                self.bull["stats"]["debates_conceded"] += 1

        self.executor["stats"]["total_orders"] += (1 if action_taken != "HOLD" else 0)
        if action_taken in ("BUY",):
            self.executor["stats"]["longs"] += 1
        elif action_taken in ("SHORT",):
            self.executor["stats"]["shorts"] += 1
        elif action_taken == "HOLD":
            self.executor["stats"]["holds"] += 1

        entry = {
            "time": timestamp,
            "symbol": symbol,
            "winner": winner,
            "conceded_by": conceded_by or "NONE",
            "rounds": rounds,
            "action": action_taken,
            "confidence": confidence,
            "reason": key_reason[:220]
        }
        self.session.setdefault("debates_today", []).append(entry)
        self.session.setdefault("last_actions_by_symbol", {})[symbol] = entry
        self.executor.setdefault("recent_decisions", []).append(entry)
        self.executor["recent_decisions"] = self.executor["recent_decisions"][-25:]
        self.save_all()

    def record_trade_event_today(self, trade_event: Dict[str, Any]):
        self.session.setdefault("trades_today", []).append(trade_event)
        self.save_all()

    # -------------------------------------------------------------------------
    # Cross-Day Memory & Agent Learning Updates (End of Day)
    # -------------------------------------------------------------------------

    def record_eod_day_summary(
        self,
        day_record: Dict[str, Any],
        bull_lessons_new: Optional[List[str]] = None,
        bear_lessons_new: Optional[List[str]] = None,
        executor_lessons_new: Optional[List[str]] = None,
        symbol_notes_bull: Optional[Dict[str, str]] = None,
        symbol_notes_bear: Optional[Dict[str, str]] = None
    ):
        """Archives today's session and injects EOD lessons into personal + cross-day memories."""
        # Archive full session JSON
        d_str = day_record.get("date", self.session.get("date", "unknown"))
        archive_path = self.sessions_archive_dir / f"{d_str}.json"
        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(self.session, f, indent=2)

        self.days.append(day_record)
        self.days = self.days[-35:]

        for l in (bull_lessons_new or []):
            clean = l.strip() if isinstance(l, str) else (str(l) if not isinstance(l, dict) else l.get("lesson", json.dumps(l)))
            clean = clean.strip()
            if clean and clean not in self.bull["lessons"]:
                self.bull["lessons"].append(clean)
        self.bull["lessons"] = self.bull["lessons"][-12:]

        for l in (bear_lessons_new or []):
            clean = l.strip() if isinstance(l, str) else (str(l) if not isinstance(l, dict) else l.get("lesson", json.dumps(l)))
            clean = clean.strip()
            if clean and clean not in self.bear["lessons"]:
                self.bear["lessons"].append(clean)
        self.bear["lessons"] = self.bear["lessons"][-12:]

        for l in (executor_lessons_new or []):
            clean = l.strip() if isinstance(l, str) else (str(l) if not isinstance(l, dict) else l.get("lesson", json.dumps(l)))
            clean = clean.strip()
            if clean and clean not in self.executor["lessons"]:
                self.executor["lessons"].append(clean)
        self.executor["lessons"] = self.executor["lessons"][-12:]

        for sym, note in (symbol_notes_bull or {}).items():
            if note:
                n_str = note.strip() if isinstance(note, str) else (note.get("note", json.dumps(note)) if isinstance(note, dict) else str(note))
                if n_str.strip():
                    self.bull["symbol_notes"][sym.upper()] = n_str.strip()[:260]

        for sym, note in (symbol_notes_bear or {}).items():
            if note:
                n_str = note.strip() if isinstance(note, str) else (note.get("note", json.dumps(note)) if isinstance(note, dict) else str(note))
                if n_str.strip():
                    self.bear["symbol_notes"][sym.upper()] = n_str.strip()[:260]

        # Record wins/losses attribution
        for tr in self.session.get("trades_today", []):
            pnl = tr.get("realized_pnl")
            if pnl is not None:
                side = tr.get("side", "LONG")
                sym = tr.get("symbol", "")
                if (side == "LONG" and pnl > 0) or (side == "SHORT" and pnl < 0):
                    if side == "LONG":
                        self.bull["stats"]["correct_calls"] += 1
                    else:
                        self.bear["stats"]["squeeze_blunders"] += 1
                elif (side == "SHORT" and pnl > 0) or (side == "LONG" and pnl < 0):
                    if side == "SHORT":
                        self.bear["stats"]["correct_calls"] += 1
                    else:
                        self.bull["stats"]["blunder_calls"] += 1

                self.bull.setdefault("recent_events", []).append({
                    "date": d_str, "symbol": sym, "side": side, "pnl": round(pnl, 2)
                })
                self.bear.setdefault("recent_events", []).append({
                    "date": d_str, "symbol": sym, "side": side, "pnl": round(pnl, 2)
                })
        self.bull["recent_events"] = self.bull.get("recent_events", [])[-15:]
        self.bear["recent_events"] = self.bear.get("recent_events", [])[-15:]

        self.save_all()

    # -------------------------------------------------------------------------
    # Compact Prompt Context Formatters (Token-Budget Safe)
    # -------------------------------------------------------------------------

    def format_day_memory_for_prompt(self, max_days: int = 4) -> str:
        if not self.days:
            return "Day 1 of simulation (no prior trading days on record yet)."
        lines = []
        for d in self.days[-max_days:]:
            lines.append(
                f"- {d['date']}: Equity=${d['ending_equity']:,.2f} ({d['daily_pnl_pct']:+.2f}% vs SPY {d.get('spy_pct', 0):+.2f}%) | "
                f"Macro={d.get('macro_regime', 'NEUTRAL')} | Takeaways: {d.get('key_lesson', 'N/A')}"
            )
        return "\n".join(lines)

    def format_session_memory_for_prompt(self, symbol: Optional[str] = None) -> str:
        if not self.session:
            return "Session starting fresh."
        parts = [f"Date: {self.session.get('date')} | Macro Open: {self.session.get('macro_open', 'N/A')}"]
        if symbol and symbol.upper() in self.session.get("last_actions_by_symbol", {}):
            la = self.session["last_actions_by_symbol"][symbol.upper()]
            parts.append(
                f"Earlier Today ({la['time']}) on {symbol}: Winner={la['winner']} (Conceded={la['conceded_by']}) -> "
                f"Action={la['action']} ({la['confidence']}%) | Note: {la['reason']}"
            )
        watch = self.session.get("premarket_watchlist", [])
        if symbol:
            w_match = [w for w in watch if w.get("symbol") == symbol.upper()]
            if w_match:
                parts.append(f"08:30 Pre-Market Plan for {symbol}: {w_match[0].get('plan', w_match[0].get('bias', ''))}")
        trades_today = self.session.get("trades_today", [])
        if trades_today:
            t_str = "; ".join([f"{t.get('time','')} {t.get('action','')} {t.get('symbol','')} @${t.get('price',0):.2f}" for t in trades_today[-4:]])
            parts.append(f"Trades Today: {t_str}")
        return "\n".join(parts)

    def format_bull_memory(self, symbol: str) -> str:
        sym = symbol.upper()
        lessons = "\n".join([f"- {l}" for l in self.bull.get("lessons", [])[-5:]])
        sym_note = self.bull.get("symbol_notes", {}).get(sym, "No specific prior Bull notes on this ticker.")
        st = self.bull.get("stats", {})
        return (
            f"[Bull Track Record: Won {st.get('debates_won',0)} / Conceded {st.get('debates_conceded',0)} | "
            f"Trade Wins {st.get('correct_calls',0)} / Bull Traps {st.get('blunder_calls',0)}]\n"
            f"Ticker Note ({sym}): {sym_note}\nActive Bull Lessons:\n{lessons}"
        )

    def format_bear_memory(self, symbol: str) -> str:
        sym = symbol.upper()
        lessons = "\n".join([f"- {l}" for l in self.bear.get("lessons", [])[-5:]])
        sym_note = self.bear.get("symbol_notes", {}).get(sym, "No specific prior Bear notes on this ticker.")
        st = self.bear.get("stats", {})
        return (
            f"[Bear Track Record: Won {st.get('debates_won',0)} / Conceded {st.get('debates_conceded',0)} | "
            f"Bear Calls Right {st.get('correct_calls',0)} / Squeezes {st.get('squeeze_blunders',0)}]\n"
            f"Ticker Note ({sym}): {sym_note}\nActive Bear Lessons:\n{lessons}"
        )

    def format_executor_memory(self, symbol: str) -> str:
        lessons = "\n".join([f"- {l}" for l in self.executor.get("lessons", [])[-5:]])
        st = self.executor.get("stats", {})
        return (
            f"[Execution Desk Stats: Orders={st.get('total_orders',0)} (Longs={st.get('longs',0)}, Shorts={st.get('shorts',0)}, Holds={st.get('holds',0)})]\n"
            f"Execution Discipline Rules:\n{lessons}"
        )
