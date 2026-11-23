"""
S&P 500 Technical Scanner & Market Pulse Engine
Scans high-liquidity S&P 500 stocks across multi-indicator setups:
RSI Oversold/Overbought, MACD Crossovers, Trend Alignment, and Relative Momentum.
Includes resilient fallback to cached historical marquee data when live network is restricted.
"""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd
import yfinance as yf

from src.core.config import DATA_DIR, SCANNER_PRESET_STOCKS, SP500_MAP, get_cached, set_cached
from src.data.market import compute_indicators

logger = logging.getLogger("ScannerEngine")


def _load_cached_marquee_movers() -> List[Dict[str, Any]]:
    """Loads real prices, volume, and momentum indicators from cached 5-year historical CSVs."""
    hist_dir = DATA_DIR / "historical"
    if not hist_dir.exists():
        return []

    results = []
    for p in sorted(hist_dir.glob("*_5y.csv")):
        sym = p.stem.replace("_5y", "").upper()
        try:
            df = pd.read_csv(p)
            if len(df) < 2:
                continue
            row = df.iloc[-1]
            prev = df.iloc[-2]

            close = float(row["Close"])
            prev_close = float(prev["Close"])
            chg = close - prev_close
            pct = (chg / prev_close * 100) if prev_close else 0.0

            vol = int(row["Volume"]) if "Volume" in row and pd.notna(row["Volume"]) else 10000000
            rsi = float(row["RSI"]) if "RSI" in row and pd.notna(row["RSI"]) else 50.0
            macd = float(row["MACD"]) if "MACD" in row and pd.notna(row["MACD"]) else 0.0
            sig = float(row["MACD_Signal"]) if "MACD_Signal" in row and pd.notna(row["MACD_Signal"]) else 0.0
            sma50 = float(row["SMA50"]) if "SMA50" in row and pd.notna(row["SMA50"]) else close

            signals = []
            if rsi <= 40:
                signals.append("RSI_OVERSOLD")
            elif rsi >= 65:
                signals.append("RSI_OVERBOUGHT")
            if macd > sig:
                signals.append("MACD_BULL_CROSS")
            if pct >= 1.0:
                signals.append("STRONG_MOMENTUM_UP")
            elif pct <= -1.0:
                signals.append("STRONG_MOMENTUM_DOWN")

            meta = SP500_MAP.get(sym, {})
            results.append({
                "symbol": sym,
                "name": meta.get("name", sym),
                "sector": meta.get("sector", "Technology"),
                "price": round(close, 2),
                "change": round(chg, 2),
                "pct_change": round(pct, 2),
                "volume": vol,
                "rsi": round(rsi, 2),
                "macd": round(macd, 2),
                "macd_signal": round(sig, 2),
                "sma50": round(sma50, 2),
                "signals": signals
            })
        except Exception as e:
            logger.debug(f"Error parsing historical CSV for {sym}: {e}")

    return results


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
        vol = int(row["Volume"]) if "Volume" in row and pd.notna(row["Volume"]) else 10000000
        return {
            "symbol": symbol,
            "name": meta.get("name", symbol),
            "sector": meta.get("sector", "Tech"),
            "price": round(close, 2),
            "change": round(chg, 2),
            "pct_change": round(pct, 2),
            "volume": vol,
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

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            scan_results = list(executor.map(scan_single_stock, candidates))
        valid = [r for r in scan_results if r]
    except Exception as e:
        logger.warning(f"Live scanner threadpool exception: {e}")
        valid = []

    # If live scan returned empty (e.g., DNS error, rate limit), fallback to cached historical marquee data
    if not valid:
        logger.info("Live scan returned 0 results; using cached marquee dataset fallback")
        valid = _load_cached_marquee_movers()

    filtered = valid
    if strategy == "rsi_oversold":
        filtered = [v for v in valid if v.get("rsi", 50) <= 45]
    elif strategy == "rsi_overbought":
        filtered = [v for v in valid if v.get("rsi", 50) >= 60]
    elif strategy == "macd_bullish":
        filtered = [v for v in valid if v.get("macd", 0) > v.get("macd_signal", 0)]
    elif strategy == "momentum_gainers":
        filtered = sorted([v for v in valid if v.get("pct_change", 0) > 0], key=lambda x: x.get("pct_change", 0), reverse=True)
    elif strategy == "momentum_losers":
        filtered = sorted([v for v in valid if v.get("pct_change", 0) < 0], key=lambda x: x.get("pct_change", 0))

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
    """
    Returns top gainers, losers, and most active stocks among S&P 500 stocks.
    Guarantees keys required by both homepage.js (gainers, losers, actives)
    and dashboard.js (gainers, losers, top_gainers, top_losers).
    """
    scan = run_sp500_scanner("all")
    results = scan.get("results", [])

    if not results:
        results = _load_cached_marquee_movers()

    # Sort gainers (highest positive change first)
    gainers = sorted(results, key=lambda x: x.get("pct_change", 0), reverse=True)[:8]

    # Sort losers (lowest change first; if all positive, lowest positive)
    losers = sorted(results, key=lambda x: x.get("pct_change", 0))[:8]

    # Sort most active by trading volume
    actives = sorted(results, key=lambda x: x.get("volume", 0), reverse=True)[:8]

    # Oversold & Overbought candidates
    oversold = sorted(results, key=lambda x: x.get("rsi", 50))[:6]
    overbought = sorted(results, key=lambda x: x.get("rsi", 50), reverse=True)[:6]

    return {
        "gainers": gainers,
        "losers": losers,
        "actives": actives,
        "top_gainers": gainers,
        "top_losers": losers,
        "most_active": actives,
        "oversold_bounce_candidates": oversold,
        "overbought_risk_candidates": overbought
    }
