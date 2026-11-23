"""
S&P 500 Technical Scanner & Market Pulse Engine
Scans high-liquidity S&P 500 stocks across multi-indicator setups:
RSI Oversold/Overbought, MACD Crossovers, Trend Alignment, and Relative Momentum.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd
import yfinance as yf

from src.core.config import SCANNER_PRESET_STOCKS, SP500_MAP, get_cached, set_cached
from src.data.market import compute_indicators

logger = logging.getLogger("ScannerEngine")


def scan_single_stock(symbol: str) -> Optional[Dict[str, Any]]:
    """Fetches history and computes scan signals for a single stock."""
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="3mo", interval="1d")
        if hist.empty or len(hist) < 15:
            return None

        hist = compute_indicators(hist)
        row = hist.iloc[-1]
        prev_row = hist.iloc[-2] if len(hist) > 1 else row

        close = float(row["Close"])
        prev_close = float(prev_row["Close"])
        chg = close - prev_close
        pct = (chg / prev_close * 100) if prev_close else 0.0

        rsi = float(row["RSI"]) if pd.notna(row.get("RSI")) else 50.0
        macd = float(row["MACD"]) if pd.notna(row.get("MACD")) else 0.0
        sig = float(row["MACD_Signal"]) if pd.notna(row.get("MACD_Signal")) else 0.0
        sma50 = float(row["SMA50"]) if pd.notna(row.get("SMA50")) else close
        sma200 = float(row["SMA200"]) if pd.notna(row.get("SMA200")) else close

        signals = []
        if rsi <= 35:
            signals.append("RSI_OVERSOLD")
        if rsi >= 65:
            signals.append("RSI_OVERBOUGHT")
        if macd > sig and float(prev_row.get("MACD", 0)) <= float(prev_row.get("MACD_Signal", 0)):
            signals.append("MACD_BULL_CROSS")
        if sma50 > sma200:
            signals.append("BULLISH_TREND")
        if pct >= 1.5:
            signals.append("STRONG_MOMENTUM_UP")
        if pct <= -1.5:
            signals.append("STRONG_MOMENTUM_DOWN")

        meta = SP500_MAP.get(symbol, {})
        return {
            "symbol": symbol,
            "name": meta.get("name", symbol),
            "sector": meta.get("sector", "Tech"),
            "price": round(close, 2),
            "change": round(chg, 2),
            "pct_change": round(pct, 2),
            "rsi": round(rsi, 2),
            "macd": round(macd, 2),
            "macd_signal": round(sig, 2),
            "sma50": round(sma50, 2),
            "signals": signals
        }
    except Exception:
        return None


def run_sp500_scanner(strategy: str = "all") -> Dict[str, Any]:
    """Runs parallel scan across S&P 500 candidates and filters by requested strategy."""
    cache_key = f"scan_{strategy}"
    cached = get_cached(cache_key, 20)
    if cached:
        return cached

    candidates = SCANNER_PRESET_STOCKS

    with ThreadPoolExecutor(max_workers=8) as executor:
        scan_results = list(executor.map(scan_single_stock, candidates))

    valid = [r for r in scan_results if r]

    filtered = valid
    if strategy == "rsi_oversold":
        filtered = [v for v in valid if v["rsi"] <= 40]
    elif strategy == "rsi_overbought":
        filtered = [v for v in valid if v["rsi"] >= 60]
    elif strategy == "macd_bullish":
        filtered = [v for v in valid if v["macd"] > v["macd_signal"]]
    elif strategy == "momentum_gainers":
        filtered = sorted([v for v in valid if v["pct_change"] > 0], key=lambda x: x["pct_change"], reverse=True)
    elif strategy == "momentum_losers":
        filtered = sorted([v for v in valid if v["pct_change"] < 0], key=lambda x: x["pct_change"])

    res = {
        "strategy": strategy,
        "scanned_universe_count": len(candidates),
        "matches_count": len(filtered),
        "timestamp": datetime.now().strftime("%H:%M:%S EST"),
        "results": filtered[:25]
    }
    set_cached(cache_key, res)
    return res


def get_market_movers() -> Dict[str, Any]:
    """Returns top gainers, losers, and most active stocks among S&P 500 presets."""
    scan = run_sp500_scanner("all")
    results = scan.get("results", [])

    gainers = sorted([r for r in results if r["pct_change"] > 0], key=lambda x: x["pct_change"], reverse=True)[:5]
    losers = sorted([r for r in results if r["pct_change"] < 0], key=lambda x: x["pct_change"])[:5]
    oversold = [r for r in results if r["rsi"] <= 40][:5]
    overbought = [r for r in results if r["rsi"] >= 65][:5]

    return {
        "top_gainers": gainers,
        "top_losers": losers,
        "oversold_bounce_candidates": oversold,
        "overbought_risk_candidates": overbought
    }
