"""
Market Data & Technical Indicators Engine
Fetches real-time quotes, multi-timeframe candles, financial fundamentals,
and computes institutional technical indicators (SMA, EMA, Bollinger Bands, RSI, MACD, ATR 14).
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd
import yfinance as yf

from src.core.config import SP500_MAP, SP500_STOCKS, get_cached, set_cached

logger = logging.getLogger("MarketData")


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Computes technical indicator series on OHLCV DataFrame."""
    if df.empty or len(df) < 5:
        return df

    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # Simple Moving Averages
    df["SMA20"] = close.rolling(window=min(20, len(df))).mean().round(2)
    df["SMA50"] = close.rolling(window=min(50, len(df))).mean().round(2)
    if len(df) >= 200:
        df["SMA200"] = close.rolling(window=200).mean().round(2)
    else:
        df["SMA200"] = close.rolling(window=len(df)).mean().round(2)

    # Exponential Moving Averages
    df["EMA20"] = close.ewm(span=min(20, len(df)), adjust=False).mean().round(2)
    df["EMA12"] = close.ewm(span=min(12, len(df)), adjust=False).mean().round(2)
    df["EMA26"] = close.ewm(span=min(26, len(df)), adjust=False).mean().round(2)

    # Bollinger Bands (20, 2)
    std20 = close.rolling(window=min(20, len(df))).std()
    df["BB_Upper"] = (df["SMA20"] + 2 * std20).round(2)
    df["BB_Lower"] = (df["SMA20"] - 2 * std20).round(2)
    df["BB_Middle"] = df["SMA20"]

    # Relative Strength Index (RSI 14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=min(14, len(df))).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=min(14, len(df))).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = (100 - (100 / (1 + rs))).fillna(50.0).round(2)

    # Moving Average Convergence Divergence (MACD 12, 26, 9)
    df["MACD"] = (df["EMA12"] - df["EMA26"]).round(2)
    df["MACD_Signal"] = df["MACD"].ewm(span=min(9, len(df)), adjust=False).mean().round(2)
    df["MACD_Hist"] = (df["MACD"] - df["MACD_Signal"]).round(2)

    # Average True Range (ATR 14)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR"] = tr.rolling(window=min(14, len(df))).mean().round(2)

    return df


def fetch_benchmarks() -> List[Dict[str, Any]]:
    """Fetches real-time benchmark index quotes for top market ticker ribbon."""
    cached = get_cached("benchmarks", 3)
    if cached:
        return cached

    benchmarks = [
        {"symbol": "^GSPC", "name": "S&P 500", "fallback": 5890.25},
        {"symbol": "^DJI", "name": "DOW JONES", "fallback": 43400.10},
        {"symbol": "^IXIC", "name": "NASDAQ", "fallback": 18700.50},
        {"symbol": "^VIX", "name": "CBOE VIX", "fallback": 15.20},
        {"symbol": "CL=F", "name": "BRENT CRUDE", "fallback": 74.50}
    ]

    results = []
    for b in benchmarks:
        try:
            t = yf.Ticker(b["symbol"])
            fast = t.fast_info
            price = fast.last_price or b["fallback"]
            prev = fast.previous_close or price
            change = price - prev
            pct = (change / prev * 100) if prev else 0.0
            results.append({
                "symbol": b["symbol"],
                "name": b["name"],
                "price": round(price, 2),
                "change": round(change, 2),
                "pct_change": round(pct, 2),
                "status": "UP" if change >= 0 else "DOWN"
            })
        except Exception:
            results.append({
                "symbol": b["symbol"],
                "name": b["name"],
                "price": b["fallback"],
                "change": 0.0,
                "pct_change": 0.0,
                "status": "FLAT"
            })

    set_cached("benchmarks", results)
    return results


def fetch_stock_quote(symbol: str) -> Dict[str, Any]:
    """Fetches high-speed real-time quote and basic fundamentals for an S&P 500 stock."""
    sym = symbol.strip().upper()
    cache_key = f"quote_{sym}"
    cached = get_cached(cache_key, 2)
    if cached:
        return cached

    meta = SP500_MAP.get(sym, {"name": sym, "sector": "S&P 500", "sub_industry": ""})
    try:
        t = yf.Ticker(sym)
        fast = t.fast_info
        price = fast.last_price or 0.0
        prev = fast.previous_close or price
        change = price - prev
        pct = (change / prev * 100) if prev else 0.0

        info = {}
        try:
            info = t.info or {}
        except Exception:
            pass

        data = {
            "symbol": sym,
            "name": meta.get("name") or info.get("shortName") or sym,
            "sector": meta.get("sector") or info.get("sector") or "Unknown",
            "sub_industry": meta.get("sub_industry") or info.get("industry") or "",
            "price": round(price, 2),
            "prev_close": round(prev, 2),
            "open": round(fast.open or prev, 2),
            "day_high": round(fast.day_high or price, 2),
            "day_low": round(fast.day_low or price, 2),
            "change": round(change, 2),
            "pct_change": round(pct, 2),
            "volume": int(fast.last_volume or info.get("volume", 0)),
            "avg_volume_10d": int(fast.ten_day_average_volume or 0),
            "year_high": round(fast.year_high or 0.0, 2),
            "year_low": round(fast.year_low or 0.0, 2),
            "market_cap": fast.market_cap or info.get("marketCap", 0),
            "pe_ratio": round(info.get("trailingPE", 0) or 0, 2),
            "forward_pe": round(info.get("forwardPE", 0) or 0, 2),
            "dividend_yield": round((info.get("dividendYield", 0) or 0) * 100, 2),
            "beta": round(info.get("beta", 1.0) or 1.0, 2),
            "heavy_drop": pct <= -1.5,
            "heavy_gain": pct >= 1.5,
            "timestamp": datetime.now().strftime("%H:%M:%S EST")
        }
        set_cached(cache_key, data)
        return data
    except Exception as e:
        logger.error(f"Error fetching quote for {sym}: {e}")
        raise ValueError(f"Unable to fetch market quote for {sym}: {str(e)}")


def fetch_stock_technicals(symbol: str) -> Dict[str, Any]:
    """
    Dedicated method for quantitative risk gate and adversarial debate agents.
    Fetches real-time price, 14-day ATR, RSI, MACD, and moving averages.
    """
    sym = symbol.strip().upper()
    cache_key = f"technicals_{sym}"
    cached = get_cached(cache_key, 10)
    if cached:
        return cached

    price = 100.0
    atr = 2.0
    rsi = 50.0
    macd = 0.0
    sig = 0.0
    sma20 = 100.0
    sma50 = 100.0
    sma200 = 100.0
    bb_upper = 105.0
    bb_lower = 95.0

    try:
        t = yf.Ticker(sym)
        fast = t.fast_info
        price = float(fast.last_price or 100.0)
        hist = t.history(period="3mo", interval="1d")
        if not hist.empty and len(hist) >= 5:
            hist = compute_indicators(hist)
            row = hist.iloc[-1]
            atr_val = row.get("ATR")
            if pd.notna(atr_val) and float(atr_val) > 0:
                atr = float(atr_val)
            else:
                atr = max(round(price * 0.02, 2), 0.5)

            rsi = float(row.get("RSI", 50.0))
            macd = float(row.get("MACD", 0.0))
            sig = float(row.get("MACD_Signal", 0.0))
            sma20 = float(row.get("SMA20", price))
            sma50 = float(row.get("SMA50", price))
            sma200 = float(row.get("SMA200", price))
            bb_upper = float(row.get("BB_Upper", price * 1.05))
            bb_lower = float(row.get("BB_Lower", price * 0.95))
        else:
            atr = max(round(price * 0.02, 2), 0.5)
    except Exception as e:
        logger.warning(f"Error computing technicals for {sym}: {e}")
        atr = max(round(price * 0.02, 2), 0.5)

    res = {
        "symbol": sym,
        "price": round(price, 2),
        "atr": round(atr, 2),
        "rsi": round(rsi, 2),
        "macd": round(macd, 2),
        "macd_signal": round(sig, 2),
        "sma20": round(sma20, 2),
        "sma50": round(sma50, 2),
        "sma200": round(sma200, 2),
        "bb_upper": round(bb_upper, 2),
        "bb_lower": round(bb_lower, 2)
    }
    set_cached(cache_key, res)
    return res


def fetch_stock_history(symbol: str, period: str = "1mo") -> Dict[str, Any]:
    """
    Returns candlestick OHLCV data with pre-calculated technical indicators:
    SMA 20, SMA 50, SMA 200, EMA 20, Bollinger Bands, RSI, MACD, ATR.
    """
    sym = symbol.strip().upper()
    cache_key = f"hist_{sym}_{period}"
    cached = get_cached(cache_key, 15)
    if cached:
        return cached

    interval_map = {
        "1d": "5m",
        "5d": "15m",
        "1mo": "1d",
        "6mo": "1d",
        "1y": "1d",
        "5y": "1wk"
    }
    interval = interval_map.get(period, "1d")

    try:
        t = yf.Ticker(sym)
        fetch_period = "1y" if period in ["1mo", "6mo"] else ("5y" if period == "1y" else period)
        hist = t.history(period=fetch_period, interval=interval)

        if hist.empty:
            return {"symbol": sym, "period": period, "candles": [], "indicators": {}}

        hist = compute_indicators(hist)

        if period == "1mo":
            hist = hist.tail(25)
        elif period == "6mo":
            hist = hist.tail(126)
        elif period == "1y":
            hist = hist.tail(252)

        candles = []
        for index, row in hist.iterrows():
            ts = index.strftime("%Y-%m-%d %H:%M") if period in ["1d", "5d"] else index.strftime("%Y-%m-%d")
            candles.append({
                "time": ts,
                "open": round(float(row["Open"]), 2),
                "high": round(float(row["High"]), 2),
                "low": round(float(row["Low"]), 2),
                "close": round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
                "sma20": float(row["SMA20"]) if pd.notna(row.get("SMA20")) else None,
                "sma50": float(row["SMA50"]) if pd.notna(row.get("SMA50")) else None,
                "sma200": float(row["SMA200"]) if pd.notna(row.get("SMA200")) else None,
                "ema20": float(row["EMA20"]) if pd.notna(row.get("EMA20")) else None,
                "bb_upper": float(row["BB_Upper"]) if pd.notna(row.get("BB_Upper")) else None,
                "bb_lower": float(row["BB_Lower"]) if pd.notna(row.get("BB_Lower")) else None,
                "bb_middle": float(row["BB_Middle"]) if pd.notna(row.get("BB_Middle")) else None,
                "rsi": float(row["RSI"]) if pd.notna(row.get("RSI")) else None,
                "macd": float(row["MACD"]) if pd.notna(row.get("MACD")) else None,
                "macd_signal": float(row["MACD_Signal"]) if pd.notna(row.get("MACD_Signal")) else None,
                "macd_hist": float(row["MACD_Hist"]) if pd.notna(row.get("MACD_Hist")) else None,
                "atr": float(row["ATR"]) if pd.notna(row.get("ATR")) else None,
            })

        latest = candles[-1] if candles else {}
        summary = {
            "rsi": latest.get("rsi"),
            "macd": latest.get("macd"),
            "macd_signal": latest.get("macd_signal"),
            "atr": latest.get("atr"),
            "macd_trend": "BULLISH" if (latest.get("macd") or 0) > (latest.get("macd_signal") or 0) else "BEARISH",
            "rsi_state": "OVERSOLD (<30)" if (latest.get("rsi") or 50) <= 30 else ("OVERBOUGHT (>70)" if (latest.get("rsi") or 50) >= 70 else "NEUTRAL"),
            "sma20": latest.get("sma20"),
            "sma50": latest.get("sma50"),
            "sma200": latest.get("sma200"),
            "above_sma50": (latest.get("close") or 0) > (latest.get("sma50") or 0),
            "above_sma200": (latest.get("close") or 0) > (latest.get("sma200") or 0)
        }

        result = {
            "symbol": sym,
            "period": period,
            "interval": interval,
            "candles": candles,
            "summary": summary
        }
        set_cached(cache_key, result)
        return result
    except Exception as e:
        logger.error(f"Error fetching history for {sym}: {e}")
        return {"symbol": sym, "period": period, "candles": [], "summary": {}}


def fetch_company_details(symbol: str) -> Dict[str, Any]:
    """Comprehensive company profile, valuation metrics, and peer comparison."""
    sym = symbol.strip().upper()
    cache_key = f"company_{sym}"
    cached = get_cached(cache_key, 60)
    if cached:
        return cached

    meta = SP500_MAP.get(sym, {"name": sym, "sector": "Technology", "sub_industry": ""})
    try:
        t = yf.Ticker(sym)
        info = t.info or {}

        peers = [s["symbol"] for s in SP500_STOCKS if s.get("sector") == meta.get("sector") and s["symbol"] != sym][:5]

        data = {
            "symbol": sym,
            "name": meta.get("name") or info.get("shortName") or sym,
            "sector": meta.get("sector") or info.get("sector") or "Unknown",
            "industry": meta.get("sub_industry") or info.get("industry") or "Diversified",
            "summary": info.get("longBusinessSummary", "No institutional profile available."),
            "website": info.get("website", ""),
            "employees": info.get("fullTimeEmployees", 0),
            "ceo": info.get("companyOfficers", [{}])[0].get("name", "Executive Management") if info.get("companyOfficers") else "Executive Management",
            "valuation": {
                "market_cap": info.get("marketCap", 0),
                "enterprise_value": info.get("enterpriseValue", 0),
                "trailing_pe": round(info.get("trailingPE", 0) or 0, 2),
                "forward_pe": round(info.get("forwardPE", 0) or 0, 2),
                "peg_ratio": round(info.get("pegRatio", 0) or 0, 2),
                "price_to_sales": round(info.get("priceToSalesTrailing12Months", 0) or 0, 2),
                "price_to_book": round(info.get("priceToBook", 0) or 0, 2),
                "ev_to_ebitda": round(info.get("enterpriseToEbitda", 0) or 0, 2)
            },
            "financials": {
                "total_revenue": info.get("totalRevenue", 0),
                "gross_margins": round((info.get("grossMargins", 0) or 0) * 100, 2),
                "operating_margins": round((info.get("operatingMargins", 0) or 0) * 100, 2),
                "profit_margins": round((info.get("profitMargins", 0) or 0) * 100, 2),
                "ebitda": info.get("ebitda", 0),
                "net_income": info.get("netIncomeToCommon", 0),
                "free_cashflow": info.get("freeCashflow", 0),
                "debt_to_equity": round(info.get("debtToEquity", 0) or 0, 2)
            },
            "peers": peers
        }
        set_cached(cache_key, data)
        return data
    except Exception as e:
        logger.error(f"Error fetching company details for {sym}: {e}")
        return {
            "symbol": sym,
            "name": meta.get("name", sym),
            "sector": meta.get("sector", "S&P 500"),
            "industry": meta.get("sub_industry", ""),
            "summary": "Profile temporarily unavailable.",
            "valuation": {},
            "financials": {},
            "peers": []
        }
