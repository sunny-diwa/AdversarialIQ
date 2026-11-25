"""
1-Month Agentic Fast-Forward Simulator Orchestrator.
Replays exact historical timeline with zero lookahead:
- 08:30 EST (1h before market open): Comprehensive Pre-Market Fundamental, News & A-CIS Score scan across ALL stocks.
- 09:30, 10:30, 11:30, 12:30, 13:30, 14:30, 15:30 EST: Hourly technical triage across ALL stocks, intrabar bracket checks,
  multi-turn Bull vs Bear debates until defeat acceptance -> 3rd Agent execution decision via local SimBroker (Alpaca disabled).
- 16:05 EST: EOD Mark-to-Market & Reflection updating Day Memory, Bull Memory, Bear Memory & Executor Memory.
- Full Markdown + JSON conversation logs emitted for manual inspection!
"""

from datetime import datetime, time as dt_time, timedelta
import json
import logging
import os
from pathlib import Path
import time
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from src.core.config import DATA_DIR
from src.sim.adversarial_debate import AdversarialDebateEngine
from src.sim.historical_store import HistoricalMarketStore, NY_TZ
from src.sim.sim_broker import SimulationBroker
from src.sim.sim_memory import SimulationMemory

logger = logging.getLogger("AgenticSimulator")


class AgenticTradingSimulator:
    """End-to-end zero-lookahead 1-month fast-forward simulator."""

    def __init__(
        self,
        run_id: str,
        symbols: List[str],
        initial_capital: float = 100000.0,
        debate_policy: str = "smart",       # "smart" (triage top N + open pos) | "all" (every stock every hour)
        max_debates_per_hour: int = 3,
        max_debate_rounds: int = 3,
        bull_provider: str = "groq",
        bull_model: str = "openai/gpt-oss-120b",
        bear_provider: str = "groq",
        bear_model: str = "qwen/qwen3.8-27b",
        judge_provider: str = "groq",
        judge_model: str = "openai/gpt-oss-120b",
        analyst_provider: str = "groq",
        analyst_model: str = "openai/gpt-oss-20b",
        pacing_sleep_sec: float = 0.8
    ):
        # Strictly disable Alpaca inside simulator process
        os.environ["ALPACA_ENABLED"] = "false"

        self.run_id = run_id
        self.symbols = [s.strip().upper() for s in symbols if s.strip()]
        self.debate_policy = debate_policy
        self.max_debates_per_hour = max_debates_per_hour
        self.pacing_sleep_sec = pacing_sleep_sec

        self.run_dir = DATA_DIR / "sim_runs" / run_id
        self.conv_dir = self.run_dir / "conversations"
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.conv_dir.mkdir(parents=True, exist_ok=True)

        self.store = HistoricalMarketStore(self.symbols)
        self.memory = SimulationMemory(self.run_dir)
        self.broker = SimulationBroker(self.run_dir, initial_capital=initial_capital)
        self.debate_engine = AdversarialDebateEngine(
            bull_provider=bull_provider,
            bull_model=bull_model,
            bear_provider=bear_provider,
            bear_model=bear_model,
            judge_provider=judge_provider,
            judge_model=judge_model,
            analyst_provider=analyst_provider,
            analyst_model=analyst_model,
            max_debate_rounds=max_debate_rounds
        )
        self.all_debates_jsonl = self.conv_dir / "all_debates.jsonl"

    def _append_day_transcript(self, trade_date_str: str, md_chunk: str):
        fpath = self.conv_dir / f"{trade_date_str}_conversations.md"
        with open(fpath, "a", encoding="utf-8") as f:
            f.write(md_chunk + "\n\n")

    def _format_open_positions_summary(self, prices: Dict[str, float]) -> str:
        if not self.broker.positions:
            return "None open (100% cash)."
        lines = []
        for sym, pos in self.broker.positions.items():
            cur_p = float(prices.get(sym, pos["entry_price"]))
            sq = pos["signed_qty"]
            side = "LONG" if sq > 0 else "SHORT"
            unreal = (cur_p - pos["entry_price"]) * sq
            pct = ((cur_p - pos["entry_price"]) / pos["entry_price"] * 100.0) * (1 if sq > 0 else -1)
            lines.append(
                f"- {sym}: {side} {abs(sq)} sh @ ${pos['entry_price']:.2f} | Cur=${cur_p:.2f} | "
                f"PnL=${unreal:+.2f} ({pct:+.2f}%) | SL=${pos['stop_loss']:.2f} | TP=${pos['take_profit']:.2f}"
            )
        return "\n".join(lines)

    def run(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_days: Optional[int] = None,
        force_refresh_cache: bool = False
    ) -> Dict[str, Any]:
        """Executes the full simulation window."""
        self.store.prepare_universe(force_refresh=force_refresh_cache)
        trading_days = self.store.get_trading_days(start_date=start_date, end_date=end_date)
        if max_days and max_days > 0:
            trading_days = trading_days[-max_days:]
        if not trading_days:
            raise RuntimeError("No trading days selected in simulation range.")

        logger.info(
            f"=== STARTING AGENTIC FAST-FORWARD SIMULATION [{self.run_id}] ===\n"
            f"    Symbols: {self.symbols}\n"
            f"    Dates:   {trading_days[0]} to {trading_days[-1]} ({len(trading_days)} days)\n"
            f"    Capital: ${self.broker.initial_capital:,.2f} | Alpaca DISABLED (Local 2-Way Paper Ledger)\n"
            f"    Policy:  {self.debate_policy} (max {self.max_debates_per_hour} debates/hr, {self.debate_engine.max_debate_rounds} rounds max)"
        )

        # Anchor SPY start price at Day 0 pre-market/open
        first_open_dt = datetime.combine(trading_days[0], dt_time(9, 30), tzinfo=NY_TZ)
        spy_start_price = self.store.get_execution_fill_price("SPY", first_open_dt) or self.store.get_mark_to_market_price("SPY", first_open_dt)

        for day_idx, trade_day in enumerate(trading_days, start=1):
            d_str = trade_day.strftime("%Y-%m-%d")
            # Resume support: skip days that have already completed and recorded EOD day memory
            if any(rec.get("date") == d_str for rec in self.memory.day_memory):
                logger.info(f"Skipping already completed day {d_str} ({day_idx}/{len(trading_days)})")
                continue
            self._run_single_trading_day(trade_day, d_str, day_idx, len(trading_days))

        # Final performance summary
        last_close_dt = datetime.combine(trading_days[-1], dt_time(16, 0), tzinfo=NY_TZ)
        final_prices = {s: self.store.get_mark_to_market_price(s, last_close_dt) for s in self.symbols}
        spy_end_price = self.store.get_mark_to_market_price("SPY", last_close_dt)
        report = self.broker.compute_performance_report(final_prices, spy_start_price, spy_end_price)
        report["run_id"] = self.run_id
        report["symbols"] = self.symbols
        report["trading_days"] = [d.strftime("%Y-%m-%d") for d in trading_days]
        report["bull_stats"] = self.memory.bull.get("stats", {})
        report["bear_stats"] = self.memory.bear.get("stats", {})
        report["executor_stats"] = self.memory.executor.get("stats", {})

        summary_path = self.run_dir / "simulation_report.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

        logger.info(f"=== SIMULATION COMPLETE [{self.run_id}] ===")
        logger.info(json.dumps(report, indent=2))
        return report

    def _run_single_trading_day(self, trade_day, d_str: str, day_idx: int, total_days: int):
        premarket_dt = datetime.combine(trade_day, dt_time(8, 30), tzinfo=NY_TZ)
        eod_dt = datetime.combine(trade_day, dt_time(16, 5), tzinfo=NY_TZ)

        macro_open = self.store.get_macro_as_of(premarket_dt)
        premarket_prices = {s: self.store.get_mark_to_market_price(s, premarket_dt) for s in self.symbols}
        start_equity = self.broker.compute_equity(premarket_prices)

        logger.info(f"\n>>> DAY {day_idx}/{total_days}: {d_str} | Start Equity: ${start_equity:,.2f} | {macro_open['summary']}")
        self.memory.start_new_session(d_str, macro_open["summary"])
        self._append_day_transcript(
            d_str,
            f"# 📅 Trading Session: {d_str} (Day {day_idx}/{total_days})\n"
            f"**Start Equity:** `${start_equity:,.2f}` | **Macro Open:** `{macro_open['summary']}`\n\n---"
        )

        # =====================================================================
        # PHASE 1: 08:30 EST PRE-MARKET ANALYSIS ACROSS ALL STOCKS (Fundamental + Scores)
        # =====================================================================
        premarket_dossiers = {
            s: self.store.build_point_in_time_dossier(s, premarket_dt, is_premarket=True)
            for s in self.symbols
        }
        pm_parsed, pm_raw = self.debate_engine.run_premarket_all_stocks(
            trade_date=d_str,
            macro_summary=macro_open["summary"],
            day_memory=self.memory.format_day_memory_for_prompt(),
            positions_summary=self._format_open_positions_summary(premarket_prices),
            dossiers=premarket_dossiers
        )
        time.sleep(self.pacing_sleep_sec)

        pm_watchlist = pm_parsed.get("watchlist", [])
        self.memory.record_premarket_analysis(
            brief_md=pm_parsed.get("daily_macro_thesis", pm_raw[:800]),
            watchlist=pm_watchlist
        )
        watch_md = "\n".join([
            f"| **{w.get('symbol')}** | `{w.get('bias')}` | `{w.get('priority')}` | {w.get('plan')} |"
            for w in pm_watchlist
        ])
        self._append_day_transcript(
            d_str,
            f"## 🌅 08:30 EST Pre-Market Master Brief (1 Hour Before Open — All Stocks)\n"
            f"**Daily Macro Thesis:** {pm_parsed.get('daily_macro_thesis', 'N/A')}\n\n"
            f"| Symbol | Bias | Priority | Gameplan |\n|:---|:---:|:---:|:---|\n{watch_md}\n\n---"
        )

        # =====================================================================
        # PHASE 2: HOURLY REGULAR MARKET SESSION (09:30 .. 15:30 EST — Technical + Debates)
        # =====================================================================
        checkpoints = self.store.get_hourly_checkpoints(trade_day)
        prev_cp_dt: Optional[datetime] = None

        for cp_dt in checkpoints:
            cp_label = cp_dt.strftime("%Y-%m-%d %H:%M")

            # 2a. Check intrabar Stop-Loss / Take-Profit hits over [prev_cp_dt, cp_dt)
            if prev_cp_dt is not None and self.broker.positions:
                bar_windows = {
                    s: self.store.get_bar_window(s, prev_cp_dt, cp_dt)
                    for s in list(self.broker.positions.keys())
                }
                bracket_hits = self.broker.process_intrabar_brackets(bar_windows)
                for hit in bracket_hits:
                    logger.info(f"  [BRACKET HIT {hit['time']}] {hit['action']} {hit['quantity']} {hit['symbol']} @ ${hit['price']:.2f} | PnL=${hit['realized_pnl']:+.2f} | {hit['rationale']}")
                    self.memory.record_trade_event_today(hit)
                    self._append_day_transcript(
                        d_str,
                        f"> 🎯 **INTRABAR BRACKET TRIGGERED ({hit['time']}):** `{hit['action']} {hit['quantity']} {hit['symbol']}` @ `${hit['price']:.2f}` | **Realized PnL:** `${hit['realized_pnl']:+.2f}` (`{hit['pnl_pct']:+.2f}%`) — *{hit['rationale']}*"
                    )
            prev_cp_dt = cp_dt

            # 2b. Build causal hourly dossiers across ALL stocks
            hourly_dossiers = {
                s: self.store.build_point_in_time_dossier(s, cp_dt, is_premarket=False)
                for s in self.symbols
            }
            cur_prices = {s: hourly_dossiers[s]["quote"]["price"] for s in self.symbols}
            equity_now = self.broker.compute_equity(cur_prices)
            bp_now = self.broker.available_buying_power(cur_prices)
            macro_now = self.store.get_macro_as_of(cp_dt)

            # 2c. Select stocks to debate this hour
            triage_note = ""
            if self.debate_policy == "all":
                debate_syms = list(self.symbols)
                triage_md = f"**All-Stocks Mode:** Evaluating full debates across all {len(debate_syms)} symbols at {cp_label}."
            else:
                # Always ensure open positions can be triaged, plus high-signal breakouts
                triage_parsed, _ = self.debate_engine.run_hourly_triage(
                    as_of=cp_label,
                    macro_summary=macro_now["summary"],
                    session_memory=self.memory.format_session_memory_for_prompt(),
                    positions_summary=self._format_open_positions_summary(cur_prices),
                    open_count=len(self.broker.positions),
                    max_pos=self.broker.max_open_positions,
                    dossiers=hourly_dossiers,
                    max_debates_per_hour=self.max_debates_per_hour
                )
                time.sleep(self.pacing_sleep_sec)
                debate_syms = triage_parsed.get("debate_symbols", [])[:self.max_debates_per_hour]
                triage_note = triage_parsed.get("hourly_market_note", "")
                triage_details = triage_parsed.get("symbol_triage_notes", {})
                triage_md = f"**Hourly Technical Triage:** {triage_note}\n**Selected for Deep Debate:** `{', '.join(debate_syms)}`\n" + "\n".join([
                    f"- **{k}:** {v}" for k, v in triage_details.items()
                ])

            self.memory.record_hourly_snapshot(
                time_label=cp_dt.strftime("%H:%M"),
                triage_summary=triage_note or f"Debated {', '.join(debate_syms)}",
                symbol_states={s: hourly_dossiers[s]["quote"] for s in self.symbols}
            )
            self._append_day_transcript(
                d_str,
                f"## 🕒 {cp_dt.strftime('%H:%M EST')} Intraday Technical Scan (Equity: `${equity_now:,.2f}` | Open: `{len(self.broker.positions)}`)\n{triage_md}"
            )

            # 2d. Multi-Turn Bull vs Bear -> Execution Judge for each selected symbol
            for sym in debate_syms:
                dossier = hourly_dossiers[sym]
                # Refresh prices & buying power before each order inside same hour
                equity_now = self.broker.compute_equity(cur_prices)
                bp_now = self.broker.available_buying_power(cur_prices)
                pos_str = self.broker.get_position_summary_for_prompt(sym, cur_prices[sym])
                sess_ctx = self.memory.format_session_memory_for_prompt(sym) + "\nRecent Days:\n" + self.memory.format_day_memory_for_prompt(max_days=3)

                debate_res = self.debate_engine.run_stock_debate_and_order(
                    dossier=dossier,
                    bull_memory_str=self.memory.format_bull_memory(sym),
                    bear_memory_str=self.memory.format_bear_memory(sym),
                    executor_memory_str=self.memory.format_executor_memory(sym),
                    session_context_str=sess_ctx,
                    current_position_str=pos_str,
                    equity=equity_now,
                    buying_power=bp_now,
                    open_count=len(self.broker.positions),
                    max_pos=self.broker.max_open_positions,
                    session_mode="INTRADAY_TECHNICAL"
                )
                time.sleep(self.pacing_sleep_sec)

                dec = debate_res["decision"]
                act = str(dec.get("action", "HOLD")).upper()
                fill_price = self.store.get_execution_fill_price(sym, cp_dt) or cur_prices[sym]

                exec_res = self.broker.execute_decision(
                    sym=sym,
                    action=act,
                    market_price=fill_price,
                    allocation_pct=dec.get("allocation_pct", 10.0),
                    stop_loss=dec.get("stop_loss"),
                    take_profit=dec.get("take_profit"),
                    atr_14=dossier["technicals"]["atr"],
                    rationale=dec.get("reasoning", debate_res["debate_outcome"]),
                    ts=cp_label,
                    current_prices=cur_prices
                )

                actual_action = exec_res.get("action", act) if exec_res.get("status") == "FILLED" else "HOLD"
                self.memory.record_debate_outcome(
                    timestamp=cp_dt.strftime("%H:%M"),
                    symbol=sym,
                    winner=debate_res["winner"],
                    conceded_by=debate_res["conceded_by"],
                    rounds=debate_res["rounds_used"],
                    action_taken=actual_action,
                    confidence=int(dec.get("confidence", 50) or 50),
                    key_reason=str(dec.get("reasoning", ""))
                )
                if exec_res.get("status") == "FILLED":
                    self.memory.record_trade_event_today(exec_res)
                    logger.info(
                        f"  [{cp_dt.strftime('%H:%M')} FILL] {exec_res['action']} {exec_res['quantity']} {sym} @ ${exec_res['price']:.2f} "
                        f"| Debate={debate_res['winner']} (Conceded={debate_res['conceded_by']}, R={debate_res['rounds_used']}) "
                        f"| {dec.get('reasoning','')[:80]}"
                    )
                else:
                    logger.info(
                        f"  [{cp_dt.strftime('%H:%M')} {exec_res.get('status','HOLD')}] {sym} ({act}) | Debate={debate_res['winner']} (Conceded={debate_res['conceded_by']}, R={debate_res['rounds_used']})"
                    )

                # Persist structured JSONL for auditing
                with open(self.all_debates_jsonl, "a", encoding="utf-8") as jf:
                    jf.write(json.dumps({
                        "date": d_str,
                        "time": cp_dt.strftime("%H:%M"),
                        "symbol": sym,
                        "winner": debate_res["winner"],
                        "conceded_by": debate_res["conceded_by"],
                        "rounds": debate_res["rounds_used"],
                        "decision": dec,
                        "execution": exec_res,
                        "transcript": debate_res["transcript"]
                    }) + "\n")

                # Persist readable Markdown conversation log for manual human reading!
                turns_md = "\n\n".join([
                    f"**[Round {tr['round']} — {tr['speaker']} (`{tr['model']}`) | Tag: `{tr['tag']}`]**\n{tr['text']}"
                    for tr in debate_res["transcript"]
                ])
                self._append_day_transcript(
                    d_str,
                    f"### ⚔️ Debate: **{sym}** @ `${fill_price:.2f}` (`{cp_dt.strftime('%H:%M')}`)\n"
                    f"- **Outcome:** `{debate_res['debate_outcome']}`\n"
                    f"- **Position Prior:** `{pos_str}`\n\n"
                    f"{turns_md}\n\n"
                    f"**⚖️ AGENT 3 EXECUTION DECISION (`{debate_res['judge_model']}`):**\n"
                    f"- **Decision:** `{act}` (Status: `{exec_res.get('status')}`) | Allocation: `{dec.get('allocation_pct',0)}%` | Confidence: `{dec.get('confidence',0)}%`\n"
                    f"- **Execution Details:** `{json.dumps(exec_res)}`\n\n---"
                )

            # Hourly mark-to-market equity snapshot
            self.broker.record_equity_point(cp_label, cur_prices)

        # Check final closing bar [15:30, 16:00) brackets before closing out day
        if prev_cp_dt is not None and self.broker.positions:
            final_bar_windows = {
                s: self.store.get_bar_window(s, prev_cp_dt, eod_dt)
                for s in list(self.broker.positions.keys())
            }
            for hit in self.broker.process_intrabar_brackets(final_bar_windows):
                self.memory.record_trade_event_today(hit)
                self._append_day_transcript(
                    d_str,
                    f"> 🎯 **CLOSE-HOUR BRACKET TRIGGERED ({hit['time']}):** `{hit['action']} {hit['quantity']} {hit['symbol']}` @ `${hit['price']:.2f}` | PnL=`${hit['realized_pnl']:+.2f}`"
                )

        # =====================================================================
        # PHASE 3: END OF DAY MARK-TO-MARKET & ADAPTIVE MEMORY REFLECTION
        # =====================================================================
        eod_prices = {s: self.store.get_mark_to_market_price(s, eod_dt) for s in self.symbols}
        end_equity = self.broker.record_equity_point(f"{d_str} 16:00", eod_prices)
        daily_pnl = round(end_equity - start_equity, 2)
        daily_pnl_pct = round((daily_pnl / start_equity * 100.0), 2) if start_equity > 0 else 0.0

        spy_q_eod = self.store.get_quote_as_of("SPY", eod_dt)
        spy_daily_pct = float(spy_q_eod.get("pct_change") or 0.0)
        closed_today = [t for t in self.memory.session.get("trades_today", []) if "realized_pnl" in t]

        eod_parsed, _ = self.debate_engine.run_eod_reflection(
            trade_date=d_str,
            macro_summary=macro_open["summary"],
            start_equity=start_equity,
            end_equity=end_equity,
            spy_pct=spy_daily_pct,
            closed_trades_today=closed_today,
            open_positions_summary=self._format_open_positions_summary(eod_prices),
            debates_today=self.memory.session.get("debates_today", []),
            day_memory_str=self.memory.format_day_memory_for_prompt()
        )
        time.sleep(self.pacing_sleep_sec)

        day_record = {
            "date": d_str,
            "macro_regime": macro_open["regime"],
            "starting_equity": start_equity,
            "ending_equity": end_equity,
            "daily_pnl": daily_pnl,
            "daily_pnl_pct": daily_pnl_pct,
            "spy_pct": spy_daily_pct,
            "closed_trades_count": len(closed_today),
            "key_lesson": eod_parsed.get("key_day_lesson", "")
        }
        self.memory.record_eod_day_summary(
            day_record=day_record,
            bull_lessons_new=eod_parsed.get("bull_lessons", []),
            bear_lessons_new=eod_parsed.get("bear_lessons", []),
            executor_lessons_new=eod_parsed.get("executor_lessons", []),
            symbol_notes_bull=eod_parsed.get("symbol_notes_bull", {}),
            symbol_notes_bear=eod_parsed.get("symbol_notes_bear", {})
        )

        self._append_day_transcript(
            d_str,
            f"## 🌙 16:05 EST End-of-Day Reflection & Memory Consolidation\n"
            f"- **End Equity:** `${end_equity:,.2f}` (**Daily PnL:** `${daily_pnl:+.2f}` / `{daily_pnl_pct:+.2f}%` vs SPY `{spy_daily_pct:+.2f}%`)\n"
            f"- **Key Day Lesson:** {eod_parsed.get('key_day_lesson')}\n"
            f"- **Bull New Lessons:** {eod_parsed.get('bull_lessons')}\n"
            f"- **Bear New Lessons:** {eod_parsed.get('bear_lessons')}\n"
            f"- **Executor New Lessons:** {eod_parsed.get('executor_lessons')}\n"
        )
        logger.info(
            f"<<< END OF DAY {d_str}: Equity=${end_equity:,.2f} ({daily_pnl_pct:+.2f}% vs SPY {spy_daily_pct:+.2f}%) | Lesson: {eod_parsed.get('key_day_lesson','')[:90]}"
        )
