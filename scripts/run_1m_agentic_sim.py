#!/usr/bin/env python3
"""
CLI Runner for AdversarialIQ 1-Month Agentic Fast-Forward Trading Simulation.
- Disables Alpaca routing cleanly (`ALPACA_ENABLED=false`)
- Pre-Market (08:30 EST) all-stock fundamental + news + Start-of-Day A-CIS score scan
- Hourly regular-session (09:30..15:30 EST) technical analysis & Multi-Turn Bull vs Bear -> Execution Agent 3
- Maintains private Bull/Bear/Executor memory, Intra-Day Session memory & Cross-Day memory
- Emits complete transcripts in data/sim_runs/<run_id>/conversations/ for manual inspection!
"""

import argparse
from datetime import datetime
import json
import os
import sys
from pathlib import Path

# Ensure workspace root on sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

# Disable Alpaca before importing config/clients
os.environ["ALPACA_ENABLED"] = "false"

from src.sim.simulator import AgenticTradingSimulator

DEFAULT_SYMBOLS = ["NVDA", "AAPL", "MSFT", "TSLA", "AMZN", "META", "GOOGL", "AMD"]


def main():
    parser = argparse.ArgumentParser(description="Run AdversarialIQ 1-Month Agentic Fast-Forward Simulation")
    parser.add_argument("--run-id", type=str, default=f"sim_{datetime.now().strftime('%Y%m%d_%H%M%S')}", help="Unique run directory ID")
    parser.add_argument("--symbols", type=str, default=",".join(DEFAULT_SYMBOLS), help="Comma-separated ticker universe")
    parser.add_argument("--capital", type=float, default=100000.0, help="Initial paper capital (USD)")
    parser.add_argument("--max-days", type=int, default=None, help="Limit to most recent N trading days (e.g. 1 for smoke test)")
    parser.add_argument("--start-date", type=str, default=None, help="Optional YYYY-MM-DD start date")
    parser.add_argument("--end-date", type=str, default=None, help="Optional YYYY-MM-DD end date")
    parser.add_argument("--debate-policy", choices=["smart", "all"], default="smart", help="'all' debates every symbol every hour; 'smart' runs hourly LLM triage across all stocks and debates top candidates")
    parser.add_argument("--max-debates-per-hour", type=int, default=3, help="Max debates per hour in 'smart' mode")
    parser.add_argument("--max-rounds", type=int, default=3, help="Max Bull/Bear back-and-forth rounds per debate")
    parser.add_argument("--bull-provider", type=str, default="groq")
    parser.add_argument("--bull-model", type=str, default="openai/gpt-oss-120b")
    parser.add_argument("--bear-provider", type=str, default="groq")
    parser.add_argument("--bear-model", type=str, default="qwen/qwen3.8-27b")
    parser.add_argument("--judge-provider", type=str, default="groq")
    parser.add_argument("--judge-model", type=str, default="openai/gpt-oss-120b")
    parser.add_argument("--analyst-provider", type=str, default="groq")
    parser.add_argument("--analyst-model", type=str, default="openai/gpt-oss-20b")
    parser.add_argument("--pacing", type=float, default=1.2, help="Seconds sleep between major LLM blocks to smooth TPM")
    parser.add_argument("--refresh-cache", action="store_true", help="Force re-download historical data cache")
    parser.add_argument("--dynamic-universe", action="store_true", default=True, help="Dynamically rank entire S&P 500 universe by Movement Score at each checkpoint and select Top N")
    parser.add_argument("--top-n", type=int, default=10, help="Number of highest-movement S&P 500 stocks to select dynamically")

    args = parser.parse_args()
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    sim = AgenticTradingSimulator(
        run_id=args.run_id,
        symbols=symbols,
        initial_capital=args.capital,
        debate_policy=args.debate_policy,
        max_debates_per_hour=args.max_debates_per_hour,
        max_debate_rounds=args.max_rounds,
        bull_provider=args.bull_provider,
        bull_model=args.bull_model,
        bear_provider=args.bear_provider,
        bear_model=args.bear_model,
        judge_provider=args.judge_provider,
        judge_model=args.judge_model,
        analyst_provider=args.analyst_provider,
        analyst_model=args.analyst_model,
        pacing_sleep_sec=args.pacing,
        dynamic_universe=args.dynamic_universe,
        top_n_candidates=args.top_n
    )

    report = sim.run(
        start_date=args.start_date,
        end_date=args.end_date,
        max_days=args.max_days,
        force_refresh_cache=args.refresh_cache
    )
    print("\n================ SIMULATION REPORT ================")
    print(json.dumps(report, indent=2))
    print(f"\nConversations saved under: data/sim_runs/{args.run_id}/conversations/")


if __name__ == "__main__":
    main()
