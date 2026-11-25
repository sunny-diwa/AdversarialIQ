"""
Interactive Multi-Turn Adversarial Debate Orchestrator (Pre-Market, Hourly Triage, Bull vs Bear, Agent 3 Judge, EOD Audit).
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from src.core.prompt_loader import load_prompt
from src.llm.manager import LLMManager

logger = logging.getLogger("SimAdversarialDebate")


def extract_json_object(raw_text: str) -> Optional[Dict[str, Any]]:
    """Extracts the outermost JSON object cleanly even if wrapped in markdown fences."""
    if not raw_text:
        return None
    cleaned = raw_text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", cleaned, re.DOTALL | re.IGNORECASE)
    if fence_match:
        cleaned = fence_match.group(1)
    else:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end > start:
            cleaned = cleaned[start:end + 1]
    try:
        return json.loads(cleaned)
    except Exception:
        # Remove trailing commas before closing braces/brackets
        try:
            repaired = re.sub(r",\s*([}\]])", r"\1", cleaned)
            return json.loads(repaired)
        except Exception:
            return None


def parse_verdict_tag(text: str, allow_concede: bool = True) -> str:
    """Extracts MAINTAIN or CONCEDE from an agent's closing line."""
    if not text:
        return "MAINTAIN"
    matches = re.findall(r"VERDICT[_\s]*TAG\W*(CONCEDE|MAINTAIN)", text, re.IGNORECASE)
    tag = matches[-1].upper() if matches else "MAINTAIN"
    if not allow_concede and tag == "CONCEDE":
        return "MAINTAIN"
    return tag


def format_dossier_block(dossier: Dict[str, Any], session_mode: str = "INTRADAY_TECHNICAL") -> str:
    """Formats point-in-time dossier into a crisp, high-signal block respecting token budgets."""
    q = dossier.get("quote", {})
    t = dossier.get("technicals", {})
    n = dossier.get("news", {})
    m = dossier.get("macro", {})
    e = dossier.get("earnings", {})
    sec = dossier.get("sec", {})
    ins = dossier.get("insider", {})
    eco = dossier.get("ecosystem", {})
    sc = dossier.get("catalyst_scores", {})
    sod = sc.get("start_of_day", {})
    tsc = sc.get("technical_scorecard", {})

    price = float(q.get("price", 100.0))
    arts = n.get("articles", [])
    news_lines = "\n".join([
        f"  * [{a.get('timestamp','')[-5:]} | {a.get('sentiment')} ({a.get('sentiment_score'):+.2f})] {a.get('title')}"
        for a in arts[:4]
    ]) or "  * No fresh ticker news in past 48h."

    sup_str = ", ".join([f"{s.get('symbol')}({s.get('pct_change',0):+.1f}%)" for s in eco.get("upstream_suppliers", [])[:3]]) or "N/A"
    cus_str = ", ".join([f"{c.get('symbol')}({c.get('pct_change',0):+.1f}%)" for c in eco.get("downstream_customers", [])[:3]]) or "N/A"
    cmp_str = ", ".join([f"{cp.get('symbol')}({cp.get('pct_change',0):+.1f}%)" for cp in eco.get("competitors", [])[:3]]) or "N/A"

    mda_snip = (sec.get("mda_summary") or "")[:220]
    risk_snip = (sec.get("risk_factors_summary") or "")[:200]

    return f"""[PRICE & SESSION]: Price=${price:.2f} | PrevClose=${q.get('prev_close',price):.2f} | DayChg={q.get('pct_change',0):+.2f}% | PreMktGap={q.get('premarket_gap_pct',0):+.2f}% | 1hChg={t.get('ret_1h_pct',0):+.2f}% | 3hChg={t.get('ret_3h_pct',0):+.2f}% | 5dPrior={t.get('prior_5d_pct',0):+.2f}%
[HOURLY TECHNICALS]: RSI1h={t.get('rsi',50):.1f} (DailyRSI={t.get('rsi_daily',50):.1f}) | MACD={t.get('macd',0):.2f} vs Sig={t.get('macd_signal',0):.2f} (Hist={t.get('macd_hist',0):+.2f}) | VWAP=${t.get('vwap',price):.2f} ({'ABOVE' if t.get('above_vwap') else 'BELOW'}) | SMA20=${t.get('sma20',price):.2f} SMA50=${t.get('sma50',price):.2f} SMA200=${t.get('sma200',price):.2f} | BB=[${t.get('bb_lower',price):.2f}, ${t.get('bb_upper',price):.2f}] | StochK={t.get('stoch_k',50):.1f} | DailyATR=${t.get('atr',2):.2f} (1hATR=${t.get('atr_1h',1):.2f}) | 1hVolRatio={t.get('vol_ratio_intraday',1.0):.2f}x
[CALCULATED A-CIS SCORES]: LiveUp={sc.get('up_score',50)} vs LiveDown={sc.get('down_score',50)} (Spread={sc.get('net_directional_spread',0):+.1f}, Bias={sc.get('dominant_bias')}) | MovProb={sc.get('movement_probability_score',50)}/100 | TechScorecard(Trend={tsc.get('trend_score',50)}, Mom={tsc.get('momentum_score',50)}, Composite={tsc.get('composite_bias','NEUTRAL')}) | StartOfDay(Up={sod.get('up_score',50)} vs Down={sod.get('down_score',50)}, Gap={sod.get('open_gap_pct',0):+.2f}%)
[4D ECOSYSTEM]: Suppliers=[{sup_str}] | Customers=[{cus_str}] | Competitors=[{cmp_str}]
[FUNDAMENTALS & MACRO]: Macro={m.get('summary')} | Earnings={e.get('blackout_status')} ({e.get('reason')}) | InsiderForm4={ins.get('cluster_verdict')} (Buys={ins.get('recent_buys_count',0)}/Sells={ins.get('recent_sells_count',0)}) | SEC MD&A: {mda_snip} | Risks: {risk_snip}
[REAL FINNHUB NEWS <= {dossier.get('as_of')}]: Overall={n.get('overall_sentiment',{}).get('label','NEUTRAL')} ({n.get('overall_sentiment',{}).get('score',0):+.2f})
{news_lines}"""


class AdversarialDebateEngine:
    """Runs multi-model interactive LLM reasoning & debates with strict_llm guarantees."""

    def __init__(
        self,
        bull_provider: str = "groq",
        bull_model: str = "openai/gpt-oss-120b",
        bear_provider: str = "groq",
        bear_model: str = "qwen/qwen3.8-27b",
        judge_provider: str = "groq",
        judge_model: str = "openai/gpt-oss-120b",
        analyst_provider: str = "groq",
        analyst_model: str = "openai/gpt-oss-20b",
        max_debate_rounds: int = 3
    ):
        self.bull_provider = bull_provider
        self.bull_model = bull_model
        self.bear_provider = bear_provider
        self.bear_model = bear_model
        self.judge_provider = judge_provider
        self.judge_model = judge_model
        self.analyst_provider = analyst_provider
        self.analyst_model = analyst_model
        self.max_debate_rounds = max(2, max_debate_rounds)

    def run_premarket_all_stocks(
        self,
        trade_date: str,
        macro_summary: str,
        day_memory: str,
        positions_summary: str,
        dossiers: Dict[str, Dict[str, Any]]
    ) -> Tuple[Dict[str, Any], str]:
        """Step 1 (08:30 EST): 1h before open fundamental + score analysis across ALL stocks."""
        digest_lines = []
        for sym, d in dossiers.items():
            q = d["quote"]
            sc = d["catalyst_scores"]
            sod = sc.get("start_of_day", {})
            n = d["news"]
            e = d["earnings"]
            t = d["technicals"]
            ins = d["insider"]
            top_hl = n["articles"][0]["title"][:95] if n.get("articles") else "No fresh breaking headlines"
            digest_lines.append(
                f"- {sym}: Price=${q['price']:.2f} (Prev=${q['prev_close']:.2f}, PreMktGap={q['premarket_gap_pct']:+.2f}%, 5d={t['prior_5d_pct']:+.2f}%) | "
                f"SOD_Score(Up={sod.get('up_score',50)} vs Down={sod.get('down_score',50)}, GapImpulse={sod.get('movement_probability_score',50)}, {sod.get('dominant_bias')}) | "
                f"DailyRSI={t['rsi_daily']:.1f} SMA20=${t['sma20']:.2f} SMA50=${t['sma50']:.2f} | "
                f"Earnings={e['blackout_status']} | Insider={ins.get('cluster_verdict')} | NewsSent={n['overall_sentiment']['label']}({n['overall_sentiment']['score']:+.2f}) \"{top_hl}\""
            )

        sys_p = load_prompt("simulation/premarket_all_stocks_system.txt")
        usr_p = load_prompt(
            "simulation/premarket_all_stocks_user.txt",
            trade_date=trade_date,
            macro_summary=macro_summary,
            day_memory=day_memory,
            positions_summary=positions_summary or "No open positions.",
            stocks_digest="\n".join(digest_lines)
        )

        res = LLMManager.generate(
            prompt=usr_p,
            system_prompt=sys_p,
            preferred_provider=self.analyst_provider,
            model=self.analyst_model,
            symbol="PREMARKET",
            temperature=0.25,
            max_tokens=1600,
            strict_llm=True,
            max_retries=3
        )
        raw = res["response"]
        parsed = extract_json_object(raw) or {
            "daily_macro_thesis": raw[:280],
            "watchlist": [
                {"symbol": sym, "bias": "NEUTRAL", "priority": idx + 1, "plan": "Monitor opening bell"}
                for idx, sym in enumerate(dossiers.keys())
            ]
        }
        return parsed, raw

    def run_hourly_triage(
        self,
        as_of: str,
        macro_summary: str,
        session_memory: str,
        positions_summary: str,
        open_count: int,
        max_pos: int,
        dossiers: Dict[str, Dict[str, Any]],
        max_debates_per_hour: int = 3
    ) -> Tuple[Dict[str, Any], str]:
        """Every 1h during open market: technical triage scan across ALL stocks in universe."""
        rows = []
        for sym, d in dossiers.items():
            t = d["technicals"]
            q = d["quote"]
            sc = d["catalyst_scores"]
            n = d["news"]
            rows.append(
                f"- {sym}: Price=${q['price']:.2f} (Day={q['pct_change']:+.2f}%, 1h={t['ret_1h_pct']:+.2f}%, 3h={t['ret_3h_pct']:+.2f}%) | "
                f"RSI1h={t['rsi']:.1f} MACD_Hist={t['macd_hist']:+.2f} VWAP=${t['vwap']:.2f}({'ABV' if t['above_vwap'] else 'BLW'}) | "
                f"SMA20=${t['sma20']:.2f} SMA50=${t['sma50']:.2f} 1hVol={t['vol_ratio_intraday']:.2f}x | "
                f"A-CIS(Up={sc.get('up_score',50)}/Dn={sc.get('down_score',50)} Spread={sc.get('net_directional_spread',0):+.1f} Mov={sc.get('movement_probability_score',50)}) | "
                f"News={n['overall_sentiment']['label']}({n['overall_sentiment']['score']:+.2f})"
            )

        sys_p = load_prompt("simulation/hourly_triage_system.txt")
        usr_p = load_prompt(
            "simulation/hourly_triage_user.txt",
            as_of=as_of,
            macro_summary=macro_summary,
            session_memory=session_memory,
            positions_summary=positions_summary or "None open.",
            open_count=str(open_count),
            max_pos=str(max_pos),
            stocks_technical_table="\n".join(rows),
            max_debates_per_hour=str(max_debates_per_hour)
        )

        try:
            res = LLMManager.generate(
                prompt=usr_p,
                system_prompt=sys_p,
                preferred_provider=self.analyst_provider,
                model=self.analyst_model,
                symbol="TRIAGE",
                temperature=0.2,
                max_tokens=1000,
                strict_llm=True,
                max_retries=5
            )
            raw = res["response"]
            parsed = extract_json_object(raw) or {}
        except Exception as e:
            logger.warning(f"Hourly triage LLM failed after retries: {e}. Using deterministic ranking.")
            raw = f"Triage fallback: {e}"
            parsed = {}
        valid_syms = set(dossiers.keys())
        chosen = [s.upper() for s in parsed.get("debate_symbols", []) if isinstance(s, str) and s.upper() in valid_syms]
        if not chosen:
            # Deterministic high-movement fallback if triage returned empty list
            ranked = sorted(
                dossiers.keys(),
                key=lambda s: abs(dossiers[s]["catalyst_scores"].get("net_directional_spread", 0)) + abs(dossiers[s]["technicals"].get("ret_1h_pct", 0)) * 5,
                reverse=True
            )
            chosen = ranked[:max_debates_per_hour]
        parsed["debate_symbols"] = chosen[:max_debates_per_hour]
        return parsed, raw

    def run_stock_debate_and_order(
        self,
        dossier: Dict[str, Any],
        bull_memory_str: str,
        bear_memory_str: str,
        executor_memory_str: str,
        session_context_str: str,
        current_position_str: str,
        equity: float,
        buying_power: float,
        open_count: int,
        max_pos: int,
        session_mode: str = "INTRADAY_TECHNICAL"
    ) -> Dict[str, Any]:
        """
        Executes true multi-turn Bull vs Bear debate until one CONCEDES (or max rounds hit),
        then passes complete transcript + scores to Agent 3 (Execution Manager) to decide exact order.
        """
        sym = dossier["symbol"]
        comp = dossier["company_name"]
        as_of = dossier["as_of"]
        dossier_block = format_dossier_block(dossier, session_mode=session_mode)

        bull_sys = load_prompt("simulation/bull_debate_system.txt", symbol=sym, company_name=comp)
        bear_sys = load_prompt("simulation/bear_debate_system.txt", symbol=sym, company_name=comp)

        bull_history: List[Dict[str, str]] = []
        bear_history: List[Dict[str, str]] = []
        transcript: List[Dict[str, Any]] = []

        winner = "STALEMATE"
        conceded_by: Optional[str] = None
        rounds_used = 0

        # Round 1: Bull Opens
        bull_open_usr = load_prompt(
            "simulation/bull_debate_user.txt",
            symbol=sym,
            as_of=as_of,
            session_mode=session_mode,
            bull_memory=bull_memory_str,
            session_context=session_context_str,
            dossier_block=dossier_block
        )
        try:
            r1_bull = LLMManager.generate(
                prompt=bull_open_usr,
                system_prompt=bull_sys,
                preferred_provider=self.bull_provider,
                model=self.bull_model,
                symbol=sym,
                temperature=0.35,
                max_tokens=1100,
                strict_llm=True,
                max_retries=5
            )
            bull_msg = r1_bull["response"]
            bull_model_used = r1_bull["model"]
        except Exception as e:
            logger.warning(f"Bull R1 LLM failed after retries for {sym}: {e}")
            bull_msg = f"Bull Thesis: Point-in-time momentum and ecosystem positioning indicate upside resilience for {sym}. VERDICT_TAG: MAINTAIN"
            bull_model_used = "fallback_prosecutor"

        bull_history.append({"role": "user", "content": bull_open_usr})
        bull_history.append({"role": "assistant", "content": bull_msg})
        transcript.append({
            "round": 1, "speaker": "BULL", "model": bull_model_used,
            "tag": "MAINTAIN", "text": bull_msg
        })

        # Round 1: Bear Challenges Bull
        bear_open_usr = load_prompt(
            "simulation/bear_debate_user.txt",
            symbol=sym,
            as_of=as_of,
            session_mode=session_mode,
            bear_memory=bear_memory_str,
            session_context=session_context_str,
            dossier_block=dossier_block,
            opponent_message=bull_msg
        )
        try:
            r1_bear = LLMManager.generate(
                prompt=bear_open_usr,
                system_prompt=bear_sys,
                preferred_provider=self.bear_provider,
                model=self.bear_model,
                symbol=sym,
                temperature=0.35,
                max_tokens=1100,
                strict_llm=True,
                max_retries=5
            )
            bear_msg = r1_bear["response"]
            bear_model_used = r1_bear["model"]
        except Exception as e:
            logger.warning(f"Bear R1 LLM failed after retries for {sym}: {e}")
            bear_msg = f"Bear Thesis: Technical exhaustion and overhead supply pressure challenge upside in {sym}. VERDICT_TAG: MAINTAIN"
            bear_model_used = "fallback_challenger"

        bear_history.append({"role": "user", "content": bear_open_usr})
        bear_history.append({"role": "assistant", "content": bear_msg})
        transcript.append({
            "round": 1, "speaker": "BEAR", "model": bear_model_used,
            "tag": "MAINTAIN", "text": bear_msg
        })
        rounds_used = 1

        # Interactive Rebuttal Loop (Rounds 2..max_debate_rounds) Until Defeat Accepted!
        for rnd in range(2, self.max_debate_rounds + 1):
            rounds_used = rnd

            # Bull Rebuts Bear -> Can Concede!
            bull_reb_usr = load_prompt(
                "simulation/bull_rebuttal_user.txt",
                opponent_message=bear_msg,
                round_num=str(rnd)
            )
            try:
                r_bull = LLMManager.generate(
                    prompt=bull_reb_usr,
                    system_prompt=bull_sys,
                    messages=bull_history,
                    preferred_provider=self.bull_provider,
                    model=self.bull_model,
                    symbol=sym,
                    temperature=0.3,
                    max_tokens=1000,
                    strict_llm=True,
                    max_retries=5
                )
                bull_msg = r_bull["response"]
                bull_mod = r_bull["model"]
            except Exception as e:
                logger.warning(f"Bull Rebuttal R{rnd} LLM failed after retries for {sym}: {e}")
                bull_msg = f"Bull holds stance based on established point-in-time metrics. VERDICT_TAG: MAINTAIN"
                bull_mod = "fallback_prosecutor"

            bull_tag = parse_verdict_tag(bull_msg, allow_concede=True)
            bull_history.append({"role": "user", "content": bull_reb_usr})
            bull_history.append({"role": "assistant", "content": bull_msg})
            transcript.append({
                "round": rnd, "speaker": "BULL", "model": bull_mod,
                "tag": bull_tag, "text": bull_msg
            })
            if bull_tag == "CONCEDE":
                winner = "BEAR"
                conceded_by = "BULL"
                break

            # Bear Rebuts Bull -> Can Concede!
            bear_reb_usr = load_prompt(
                "simulation/bear_rebuttal_user.txt",
                opponent_message=bull_msg,
                round_num=str(rnd)
            )
            try:
                r_bear = LLMManager.generate(
                    prompt=bear_reb_usr,
                    system_prompt=bear_sys,
                    messages=bear_history,
                    preferred_provider=self.bear_provider,
                    model=self.bear_model,
                    symbol=sym,
                    temperature=0.3,
                    max_tokens=1000,
                    strict_llm=True,
                    max_retries=5
                )
                bear_msg = r_bear["response"]
                bear_mod = r_bear["model"]
            except Exception as e:
                logger.warning(f"Bear Rebuttal R{rnd} LLM failed after retries for {sym}: {e}")
                bear_msg = f"Bear maintains skepticism against overhead resistance. VERDICT_TAG: MAINTAIN"
                bear_mod = "fallback_challenger"

            bear_tag = parse_verdict_tag(bear_msg, allow_concede=True)
            bear_history.append({"role": "user", "content": bear_reb_usr})
            bear_history.append({"role": "assistant", "content": bear_msg})
            transcript.append({
                "round": rnd, "speaker": "BEAR", "model": bear_mod,
                "tag": bear_tag, "text": bear_msg
            })
            if bear_tag == "CONCEDE":
                winner = "BULL"
                conceded_by = "BEAR"
                break

        # Format full debate transcript & compact calculated score summary for Execution Agent 3
        transcript_text = "\n\n".join([
            f"[Round {t['round']} - {t['speaker']} ({t['model']}) | {t['tag']}]:\n{t['text']}"
            for t in transcript
        ])
        if winner == "BULL":
            debate_outcome = f"BULL WON (Agent Bear ACCEPTED DEFEAT in Round {rounds_used})"
        elif winner == "BEAR":
            debate_outcome = f"BEAR WON (Agent Bull ACCEPTED DEFEAT in Round {rounds_used})"
        else:
            debate_outcome = f"CONTESTED STALEMATE after {rounds_used} rounds (Neither side conceded)"

        price = float(dossier["quote"]["price"])
        atr = float(dossier["technicals"]["atr"])
        sc = dossier["catalyst_scores"]
        t = dossier["technicals"]
        score_summary = (
            f"A-CIS Up={sc.get('up_score',50)} vs Down={sc.get('down_score',50)} (Spread={sc.get('net_directional_spread',0):+.1f}, {sc.get('dominant_bias')}) | "
            f"MovProb={sc.get('movement_probability_score',50)} | RSI1h={t['rsi']:.1f} VWAP=${t['vwap']:.2f}({'ABOVE' if t['above_vwap'] else 'BELOW'}) MACD_Hist={t['macd_hist']:+.2f} | "
            f"SMA20=${t['sma20']:.2f} SMA50=${t['sma50']:.2f}"
        )

        # Agent 3: Execution Portfolio Manager Decision
        exec_sys = load_prompt("simulation/execution_judge_system.txt", symbol=sym, price=f"{price:.2f}")
        exec_usr = load_prompt(
            "simulation/execution_judge_user.txt",
            symbol=sym,
            price=f"{price:.2f}",
            atr=f"{atr:.2f}",
            earnings_status=f"{dossier['earnings']['blackout_status']} ({dossier['earnings']['reason']})",
            as_of=as_of,
            session_mode=session_mode,
            equity=f"{equity:,.2f}",
            buying_power=f"{buying_power:,.2f}",
            open_count=str(open_count),
            max_pos=str(max_pos),
            current_position=current_position_str,
            executor_memory=executor_memory_str,
            session_context=session_context_str,
            score_summary=score_summary,
            debate_outcome=debate_outcome,
            rounds_used=str(rounds_used),
            conceded_by=conceded_by or "NONE",
            debate_transcript=transcript_text
        )

        try:
            r_exec = LLMManager.generate(
                prompt=exec_usr,
                system_prompt=exec_sys,
                preferred_provider=self.judge_provider,
                model=self.judge_model,
                symbol=sym,
                temperature=0.15,
                max_tokens=1100,
                strict_llm=True,
                max_retries=5
            )
            judge_model_used = r_exec.get("model", self.judge_model)
            exec_json = extract_json_object(r_exec["response"]) or {
                "action": "HOLD",
                "allocation_pct": 0.0,
                "stop_loss": price,
                "take_profit": price,
                "confidence": 40,
                "reasoning": f"Fallback parse notice; raw response: {r_exec['response'][:180]}"
            }
        except Exception as e:
            logger.warning(f"Judge LLM failed after retries for {sym}: {e}. Falling back to safe HOLD.")
            judge_model_used = "safe_hold_fallback"
            exec_json = {
                "action": "HOLD",
                "allocation_pct": 0.0,
                "stop_loss": price,
                "take_profit": price,
                "confidence": 35,
                "reasoning": f"Safety HOLD: Judge LLM rate-limited after retries ({str(e)[:100]}). Flat risk maintained."
            }

        return {
            "symbol": sym,
            "as_of": as_of,
            "session_mode": session_mode,
            "price": price,
            "winner": winner,
            "conceded_by": conceded_by,
            "rounds_used": rounds_used,
            "debate_outcome": debate_outcome,
            "transcript": transcript,
            "decision": exec_json,
            "judge_raw": r_exec["response"] if "r_exec" in locals() and r_exec else "safe_hold_fallback",
            "judge_model": judge_model_used
        }

    def run_eod_reflection(
        self,
        trade_date: str,
        macro_summary: str,
        start_equity: float,
        end_equity: float,
        spy_pct: float,
        closed_trades_today: List[Dict[str, Any]],
        open_positions_summary: str,
        debates_today: List[Dict[str, Any]],
        day_memory_str: str
    ) -> Tuple[Dict[str, Any], str]:
        """End-of-Day self-critique & adaptive lesson writer across all 3 private agent memories."""
        daily_pnl_pct = ((end_equity - start_equity) / start_equity * 100.0) if start_equity > 0 else 0.0

        closed_lines = "\n".join([
            f"- {t['action']} {t['symbol']} (Side={t['side']}): Entry=${t['entry_price']:.2f} Exit=${t['price']:.2f} -> PnL=${t['realized_pnl']:+.2f} ({t['pnl_pct']:+.2f}%) | {t['rationale']}"
            for t in closed_trades_today
        ]) or "No trades closed today."

        debate_lines = "\n".join([
            f"- {d['time']} {d['symbol']}: Winner={d['winner']} (Conceded={d['conceded_by']}) -> {d['action']} ({d['confidence']}%) | {d['reason']}"
            for d in debates_today[-12:]
        ]) or "No debates executed today."

        sys_p = load_prompt("simulation/eod_reflection_system.txt")
        usr_p = load_prompt(
            "simulation/eod_reflection_user.txt",
            trade_date=trade_date,
            macro_summary=macro_summary,
            start_equity=f"{start_equity:,.2f}",
            end_equity=f"{end_equity:,.2f}",
            daily_pnl_pct=daily_pnl_pct,
            spy_pct=spy_pct,
            closed_trades_summary=closed_lines,
            open_positions_summary=open_positions_summary or "Flat (100% cash).",
            debates_today_summary=debate_lines,
            day_memory=day_memory_str
        )

        try:
            res = LLMManager.generate(
                prompt=usr_p,
                system_prompt=sys_p,
                preferred_provider=self.judge_provider,
                model=self.judge_model,
                symbol="EOD",
                temperature=0.2,
                max_tokens=1200,
                strict_llm=True,
                max_retries=5
            )
            raw = res["response"]
            parsed = extract_json_object(raw) or {
                "key_day_lesson": f"EOD equity ${end_equity:,.2f} ({daily_pnl_pct:+.2f}% vs SPY {spy_pct:+.2f}%).",
                "bull_lessons": [],
                "bear_lessons": [],
                "executor_lessons": [],
                "symbol_notes_bull": {},
                "symbol_notes_bear": {}
            }
        except Exception as e:
            logger.warning(f"EOD reflection LLM failed after retries: {e}. Falling back to default lesson.")
            raw = f"EOD fallback: {e}"
            parsed = {
                "key_day_lesson": f"Session closed with equity ${end_equity:,.2f} ({daily_pnl_pct:+.2f}% vs SPY {spy_pct:+.2f}%). Execution discipline maintained flat exposure.",
                "bull_lessons": ["High volatility sessions require confirmed 5m volume follow-through before entry."],
                "bear_lessons": ["Defensive cash preservation protects equity during indecisive macro churn."],
                "executor_lessons": ["Discipline in contested stalemates avoids unnecessary churn and spread loss."],
                "symbol_notes_bull": {},
                "symbol_notes_bear": {}
            }
        return parsed, raw
