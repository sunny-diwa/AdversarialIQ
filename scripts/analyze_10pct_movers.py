"""
Analysis script: Evaluates if AdversarialIQ catches >10% daily moves.
Tests dynamic screening rank, A-CIS catalyst scores, and execution decisions.
"""

from datetime import datetime, time as dt_time
import pandas as pd
from zoneinfo import ZoneInfo
from src.sim.historical_store import HistoricalMarketStore

NY_TZ = ZoneInfo("America/New_York")


def analyze_big_movers():
    store = HistoricalMarketStore(symbols=["SPY", "TSM", "DLTR", "ADI", "HPE", "DELL", "TXN", "SNDK", "MU", "MPWR", "LITE", "FLEX"])
    
    # Target big mover events on 2026-11-23 and 2026-11-24
    test_events = [
        {"date": "2026-11-23", "symbol": "TSM", "type": "LONG (+14.1%)", "actual_pct": 14.08},
        {"date": "2026-11-24", "symbol": "DLTR", "type": "LONG (+11.2%)", "actual_pct": 11.18},
        {"date": "2026-11-24", "symbol": "ADI", "type": "SHORT/AVOID (-17.4%)", "actual_pct": -17.37},
        {"date": "2026-11-24", "symbol": "HPE", "type": "SHORT/AVOID (-16.3%)", "actual_pct": -16.31},
        {"date": "2026-11-24", "symbol": "DELL", "type": "SHORT/AVOID (-11.8%)", "actual_pct": -11.83},
        {"date": "2026-11-24", "symbol": "TXN", "type": "SHORT/AVOID (-11.3%)", "actual_pct": -11.25},
        {"date": "2026-11-24", "symbol": "SNDK", "type": "SHORT/AVOID (-11.1%)", "actual_pct": -11.13},
        {"date": "2026-11-24", "symbol": "MU", "type": "SHORT/AVOID (-11.0%)", "actual_pct": -11.01},
        {"date": "2026-11-24", "symbol": "MPWR", "type": "SHORT/AVOID (-10.8%)", "actual_pct": -10.77},
        {"date": "2026-11-24", "symbol": "LITE", "type": "SHORT/AVOID (-10.5%)", "actual_pct": -10.52},
    ]

    results = []

    for ev in test_events:
        sym = ev["symbol"]
        d_str = ev["date"]
        d = datetime.strptime(d_str, "%Y-%m-%d").date()

        # Checkpoint 1: Pre-Market 08:30 EST
        dt_pre = datetime.combine(d, dt_time(8, 30), tzinfo=NY_TZ)
        top10_pre = store.rank_universe_by_movement_score(dt_pre, top_n=20, is_premarket=True)
        top10_syms_pre = [x["symbol"] for x in top10_pre]
        rank_pre = top10_syms_pre.index(sym) + 1 if sym in top10_syms_pre else ">20"
        
        # Checkpoint 2: Open 09:30 EST
        dt_open = datetime.combine(d, dt_time(9, 30), tzinfo=NY_TZ)
        top10_open = store.rank_universe_by_movement_score(dt_open, top_n=20, is_premarket=False)
        top10_syms_open = [x["symbol"] for x in top10_open]
        rank_open = top10_syms_open.index(sym) + 1 if sym in top10_syms_open else ">20"

        # Checkpoint 3: First Hour Intraday 10:30 EST
        dt_1030 = datetime.combine(d, dt_time(10, 30), tzinfo=NY_TZ)
        top10_1030 = store.rank_universe_by_movement_score(dt_1030, top_n=10, is_premarket=False)
        top10_syms_1030 = [x["symbol"] for x in top10_1030]
        rank_1030 = top10_syms_1030.index(sym) + 1 if sym in top10_syms_1030 else ">10"

        # Build point-in-time dossier at 09:30 to inspect A-CIS catalyst scores
        dossier = store.build_point_in_time_dossier(sym, dt_open, is_premarket=False)
        cat_scores = dossier.get("catalyst_scores", {})
        
        up_sc = cat_scores.get("up_score", 0.0)
        down_sc = cat_scores.get("down_score", 0.0)
        mov_prob = cat_scores.get("movement_probability_score", 0.0)
        dominant = cat_scores.get("dominant_bias", "NEUTRAL")

        # Did we catch it in Top 10 at any of the morning decision points?
        caught_in_top10 = (rank_pre != ">20" and rank_pre <= 10) or (rank_open != ">20" and rank_open <= 10) or (rank_1030 != ">10" and rank_1030 <= 10)

        # Did directional bias match?
        if ev["actual_pct"] > 0:
            direction_match = (dominant == "BULLISH CATALYST" or up_sc > down_sc)
            trade_action = "BUY / LONG" if direction_match else "MISSED / FLAT"
        else:
            direction_match = (dominant == "BEARISH CATALYST" or down_sc > up_sc)
            trade_action = "SHORT / PROTECT" if direction_match else "VETO / FLAT"

        results.append({
            "symbol": sym,
            "date": d_str,
            "type": ev["type"],
            "pct": ev["actual_pct"],
            "rank_0830": rank_pre,
            "rank_0930": rank_open,
            "rank_1030": rank_1030,
            "mov_prob": mov_prob,
            "up_score": up_sc,
            "down_score": down_sc,
            "dominant_bias": dominant,
            "caught_top10": "YES" if caught_in_top10 else "NO",
            "trade_action": trade_action
        })

    print("\n" + "=" * 125)
    print(f"{'SYMBOL':<6} | {'DATE':<10} | {'MOVE TYPE':<22} | {'08:30':<6} | {'09:30':<6} | {'10:30':<6} | {'TOP10?':<7} | {'UP':<5} | {'DOWN':<5} | {'BIAS':<22} | {'ACTION'}")
    print("=" * 125)

    for r in results:
        print(f"{r['symbol']:<6} | {r['date']:<10} | {r['type']:<22} | {str(r['rank_0830']):<6} | {str(r['rank_0930']):<6} | {str(r['rank_1030']):<6} | {r['caught_top10']:<7} | {r['up_score']:<5.1f} | {r['down_score']:<5.1f} | {r['dominant_bias']:<22} | {r['trade_action']}")

    print("=" * 125)


if __name__ == "__main__":
    analyze_big_movers()
