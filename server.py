import json
import logging
import math
import os
import re
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import requests
import uvicorn
import yfinance as yf
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# Suppress yfinance internal deprecation warnings
warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("SP500Trader")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
SP500_FILE = DATA_DIR / "sp500.json"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"

app = FastAPI(title="S&P 500 Trader Agent & Bloomberg Terminal", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load S&P 500 catalog
SP500_STOCKS: List[dict] = []
if SP500_FILE.exists():
    try:
        with open(SP500_FILE, "r", encoding="utf-8") as f:
            SP500_STOCKS = json.load(f)
        logger.info(f"Loaded {len(SP500_STOCKS)} S&P 500 stocks.")
    except Exception as e:
        logger.error(f"Error loading S&P 500 file: {e}")

SP500_MAP = {s["symbol"]: s for s in SP500_STOCKS}

# In-memory fast cache
CACHE: Dict[str, dict] = {}
CACHE_TTL = {
    "quote": 2,          # 2 seconds
    "history": 15,       # 15 seconds
    "company": 60,       # 1 minute
    "benchmarks": 3,     # 3 seconds
    "scanner": 20        # 20 seconds
}

def get_cached(key: str, ttl: int):
    entry = CACHE.get(key)
    if entry and (time.time() - entry["timestamp"] < ttl):
        return entry["data"]
    return None

def set_cached(key: str, data):
    CACHE[key] = {"data": data, "timestamp": time.time()}

# -----------------------------------------------------------------------------
# Portfolio Management Helper
# -----------------------------------------------------------------------------
def load_portfolio() -> dict:
    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "cash": 10000.0,
        "initial_balance": 10000.0,
        "positions": {},
        "trades": [],
        "realized_pnl": 0.0,
        "equity_history": [
            {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "equity": 10000.0, "cash": 10000.0}
        ]
    }

def save_portfolio(p: dict):
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f, indent=2)

# -----------------------------------------------------------------------------
# Technical Indicator Computation
# -----------------------------------------------------------------------------
def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or len(df) < 5:
        return df

    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # Moving Averages
    df["SMA20"] = close.rolling(window=min(20, len(df))).mean().round(2)
    df["SMA50"] = close.rolling(window=min(50, len(df))).mean().round(2)
    if len(df) >= 200:
        df["SMA200"] = close.rolling(window=200).mean().round(2)
    else:
        df["SMA200"] = close.rolling(window=len(df)).mean().round(2)
    
    df["EMA20"] = close.ewm(span=min(20, len(df)), adjust=False).mean().round(2)
    df["EMA12"] = close.ewm(span=min(12, len(df)), adjust=False).mean().round(2)
    df["EMA26"] = close.ewm(span=min(26, len(df)), adjust=False).mean().round(2)

    # Bollinger Bands (20, 2)
    std20 = close.rolling(window=min(20, len(df))).std()
    df["BB_Upper"] = (df["SMA20"] + 2 * std20).round(2)
    df["BB_Lower"] = (df["SMA20"] - 2 * std20).round(2)
    df["BB_Middle"] = df["SMA20"]

    # RSI (14)
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=min(14, len(df))).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=min(14, len(df))).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = (100 - (100 / (1 + rs))).fillna(50.0).round(2)

    # MACD (12, 26, 9)
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

# -----------------------------------------------------------------------------
# REST API Endpoints
# -----------------------------------------------------------------------------

@app.get("/api/sp500/list")
async def get_sp500_list(search: str = ""):
    """Returns the S&P 500 stock universe, optionally filtered by symbol or name."""
    q = search.strip().upper()
    if not q:
        return SP500_STOCKS
    results = [
        s for s in SP500_STOCKS
        if q in s["symbol"].upper() or q in s["name"].upper() or q in s["sector"].upper()
    ]
    return results[:50]

@app.get("/api/sp500/sectors")
async def get_sp500_sectors():
    """Returns all 11 GICS sectors with stock counts and sample leaders."""
    sectors: Dict[str, list] = {}
    for s in SP500_STOCKS:
        sec = s.get("sector", "Other")
        if sec not in sectors:
            sectors[sec] = []
        sectors[sec].append(s["symbol"])
    
    out = []
    for sec, syms in sorted(sectors.items()):
        out.append({
            "sector": sec,
            "count": len(syms),
            "sample_stocks": syms[:6]
        })
    return out

@app.get("/api/benchmarks")
async def get_benchmarks():
    """Live S&P 500 and US Market benchmarks ribbon."""
    cached = get_cached("benchmarks", CACHE_TTL["benchmarks"])
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

@app.get("/api/stock/{symbol}/quote")
async def get_stock_quote(symbol: str):
    """Fast live quote for an S&P 500 stock."""
    sym = symbol.strip().upper()
    cache_key = f"quote_{sym}"
    cached = get_cached(cache_key, CACHE_TTL["quote"])
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
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/stock/{symbol}/history")
async def get_stock_history(
    symbol: str,
    period: str = Query("1mo", regex="^(1d|5d|1mo|6mo|1y|5y)$")
):
    """
    Returns candlestick OHLCV data with pre-calculated indicators:
    SMA 20, SMA 50, SMA 200, EMA 20, Bollinger Bands, RSI, MACD, ATR.
    """
    sym = symbol.strip().upper()
    cache_key = f"hist_{sym}_{period}"
    cached = get_cached(cache_key, CACHE_TTL["history"])
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
        # Fetch slightly more history to let moving averages warm up
        fetch_period = "1y" if period in ["1mo", "6mo"] else ("5y" if period == "1y" else period)
        hist = t.history(period=fetch_period, interval=interval)
        
        if hist.empty:
            return {"symbol": sym, "period": period, "candles": [], "indicators": {}}

        hist = compute_indicators(hist)

        # Slice to requested period
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
            })

        latest = candles[-1] if candles else {}
        summary = {
            "rsi": latest.get("rsi"),
            "macd": latest.get("macd"),
            "macd_signal": latest.get("macd_signal"),
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

@app.get("/api/stock/{symbol}/company")
async def get_company_details(symbol: str):
    """
    Comprehensive company profile, financial metrics, and S&P 500 peer comparison.
    """
    sym = symbol.strip().upper()
    cache_key = f"comp_{sym}"
    cached = get_cached(cache_key, CACHE_TTL["company"])
    if cached:
        return cached

    meta = SP500_MAP.get(sym, {"name": sym, "sector": "Information Technology", "sub_industry": ""})
    sector = meta.get("sector")

    try:
        t = yf.Ticker(sym)
        info = t.info or {}

        # S&P 500 peer selection (same sector)
        peer_symbols = [
            s["symbol"] for s in SP500_STOCKS
            if s.get("sector") == sector and s["symbol"] != sym
        ][:5]

        peers = []
        for p_sym in peer_symbols:
            try:
                pt = yf.Ticker(p_sym)
                p_fast = pt.fast_info
                p_price = p_fast.last_price or 0.0
                p_prev = p_fast.previous_close or p_price
                p_chg = p_price - p_prev
                p_pct = (p_chg / p_prev * 100) if p_prev else 0.0
                peers.append({
                    "symbol": p_sym,
                    "name": SP500_MAP.get(p_sym, {}).get("name", p_sym),
                    "price": round(p_price, 2),
                    "change": round(p_chg, 2),
                    "pct_change": round(p_pct, 2),
                    "market_cap": round((p_fast.market_cap or 0) / 1e9, 2)
                })
            except Exception:
                pass

        data = {
            "symbol": sym,
            "name": meta.get("name") or info.get("shortName") or sym,
            "sector": sector,
            "sub_industry": meta.get("sub_industry") or info.get("industry") or "",
            "summary": info.get("longBusinessSummary", "S&P 500 constituent."),
            "ceo": info.get("companyOfficers", [{}])[0].get("name", "Executive Leadership") if info.get("companyOfficers") else "Executive Leadership",
            "employees": info.get("fullTimeEmployees", 0),
            "city": f"{info.get('city', '')}, {info.get('country', 'USA')}",
            "website": info.get("website", ""),
            "valuation": {
                "market_cap_b": round((info.get("marketCap", 0) or 0) / 1e9, 2),
                "enterprise_value_b": round((info.get("enterpriseValue", 0) or 0) / 1e9, 2),
                "trailing_pe": round(info.get("trailingPE", 0) or 0, 2),
                "forward_pe": round(info.get("forwardPE", 0) or 0, 2),
                "peg_ratio": round(info.get("pegRatio", 0) or 0, 2),
                "price_to_book": round(info.get("priceToBook", 0) or 0, 2),
                "price_to_sales": round(info.get("priceToSalesTrailing12Months", 0) or 0, 2),
                "ev_to_ebitda": round(info.get("enterpriseToEbitda", 0) or 0, 2)
            },
            "profitability": {
                "profit_margin": round((info.get("profitMargins", 0) or 0) * 100, 2),
                "operating_margin": round((info.get("operatingMargins", 0) or 0) * 100, 2),
                "gross_margin": round((info.get("grossMargins", 0) or 0) * 100, 2),
                "roe": round((info.get("returnOnEquity", 0) or 0) * 100, 2),
                "roa": round((info.get("returnOnAssets", 0) or 0) * 100, 2)
            },
            "financial_health": {
                "total_cash_b": round((info.get("totalCash", 0) or 0) / 1e9, 2),
                "total_debt_b": round((info.get("totalDebt", 0) or 0) / 1e9, 2),
                "debt_to_equity": round(info.get("debtToEquity", 0) or 0, 2),
                "current_ratio": round(info.get("currentRatio", 0) or 0, 2),
                "free_cash_flow_b": round((info.get("freeCashflow", 0) or 0) / 1e9, 2)
            },
            "peers": peers
        }
        set_cached(cache_key, data)
        return data
    except Exception as e:
        logger.error(f"Error fetching company details for {sym}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------------------------------------------------------------
# S&P 500 Live Scanner Engine
# -----------------------------------------------------------------------------
SCANNER_PRESET_STOCKS = [
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "BRK-B",
    "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "PG", "MA", "LLY", "HD",
    "CVX", "MRK", "ABBV", "COST", "KO", "PEP", "AVGO", "BAC", "AMD",
    "TMO", "CSCO", "ADBE", "ORCL", "NFLX", "CRM", "INTC", "QCOM", "WFC"
]

@app.get("/api/scanner/run")
async def run_sp500_scanner(strategy: str = "all"):
    """
    Scans S&P 500 stocks across technical setups:
    - rsi_oversold: RSI <= 35
    - rsi_overbought: RSI >= 65
    - macd_bullish: MACD crossed above Signal
    - momentum_gainers: Top % gainers
    - momentum_losers: Top % losers
    - golden_cross: SMA 50 > SMA 200
    """
    cached = get_cached(f"scan_{strategy}", CACHE_TTL["scanner"])
    if cached:
        return cached

    # Scan universe
    candidates = SCANNER_PRESET_STOCKS

    results = []

    def scan_stock(symbol: str):
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

            # Signals
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

    with ThreadPoolExecutor(max_workers=8) as executor:
        scan_results = list(executor.map(scan_stock, candidates))

    valid = [r for r in scan_results if r]

    # Filter by strategy
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

    output = {
        "timestamp": datetime.now().strftime("%H:%M:%S EST"),
        "count": len(filtered),
        "results": filtered[:25]
    }
    set_cached(f"scan_{strategy}", output)
    return output

@app.get("/api/market/movers")
async def get_market_movers():
    """
    Returns S&P 500 top gainers, top losers, and most active stocks in a single high-speed cached call.
    Ideal for Homepage market pulse and Stock Page side-by-side overview.
    """
    cache_key = "market_movers"
    cached = get_cached(cache_key, CACHE_TTL["scanner"])
    if cached:
        return cached

    # Run scan across preset universe
    scan_res = await run_sp500_scanner(strategy="all")
    all_stocks = scan_res.get("results", [])

    gainers = sorted([s for s in all_stocks if s.get("pct_change", 0) > 0], key=lambda x: x["pct_change"], reverse=True)[:10]
    losers = sorted([s for s in all_stocks if s.get("pct_change", 0) < 0], key=lambda x: x["pct_change"])[:10]
    actives = sorted(all_stocks, key=lambda x: abs(x.get("pct_change", 0)), reverse=True)[:10]

    result = {
        "timestamp": datetime.now().strftime("%H:%M:%S EST"),
        "total_scanned": len(all_stocks),
        "gainers": gainers,
        "losers": losers,
        "actives": actives
    }
    set_cached(cache_key, result)
    return result

# -----------------------------------------------------------------------------
# Paper Trading Portfolio Endpoints ($10,000 Starting Environment)
# -----------------------------------------------------------------------------
class TradeRequest(BaseModel):
    action: str  # BUY or SELL
    symbol: str
    quantity: int
    order_type: Optional[str] = "MARKET"   # MARKET, LIMIT, STOP_LIMIT
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    rationale: Optional[str] = "Manual Desk Execution"

@app.get("/api/portfolio/get")
async def get_portfolio_state():
    """
    Returns live paper portfolio with marked-to-market valuations,
    advanced risk metrics (Win Rate, Profit Factor, Concentration Risk, Cash Ratio),
    and equity trajectory history.
    """
    p = load_portfolio()
    positions = p.get("positions", {})
    init_balance = p.get("initial_balance", 10000.0)
    cash = p.get("cash", 10000.0)

    holdings = []
    total_holdings_val = 0.0

    for sym, pos in positions.items():
        qty = pos.get("quantity", 0)
        avg_price = pos.get("avg_price", 0.0)
        cost_basis = qty * avg_price

        # Fetch live price
        current_price = avg_price
        try:
            fast = yf.Ticker(sym).fast_info
            current_price = fast.last_price or avg_price
        except Exception:
            pass

        current_val = qty * current_price
        unrealized_pnl = current_val - cost_basis
        unrealized_pct = (unrealized_pnl / cost_basis * 100) if cost_basis else 0.0
        total_holdings_val += current_val

        holdings.append({
            "symbol": sym,
            "name": SP500_MAP.get(sym, {}).get("name", sym),
            "quantity": qty,
            "avg_price": round(avg_price, 2),
            "current_price": round(current_price, 2),
            "cost_basis": round(cost_basis, 2),
            "current_value": round(current_val, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "unrealized_pct": round(unrealized_pct, 2),
            "stop_loss": pos.get("stop_loss"),
            "take_profit": pos.get("take_profit"),
            "status": "UP" if unrealized_pnl >= 0 else "DOWN"
        })

    total_equity = cash + total_holdings_val
    total_pnl = total_equity - init_balance
    total_pnl_pct = (total_pnl / init_balance * 100) if init_balance else 0.0

    # Advanced Quant & Risk Metrics (TradingAgents Risk Desk)
    trades = p.get("trades", [])
    closed_trades = [t for t in trades if t.get("type") == "SELL" and "pnl" in t]
    wins = [t for t in closed_trades if t.get("pnl", 0) > 0]
    losses = [t for t in closed_trades if t.get("pnl", 0) <= 0]

    win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0.0
    gross_wins = sum(t.get("pnl", 0) for t in wins)
    gross_losses = abs(sum(t.get("pnl", 0) for t in losses))
    profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else (round(gross_wins, 2) if gross_wins > 0 else 1.0)

    # Max single stock concentration %
    max_stock_val = max([h["current_value"] for h in holdings], default=0.0)
    concentration_risk = round((max_stock_val / total_equity * 100), 1) if total_equity else 0.0
    cash_ratio = round((cash / total_equity * 100), 1) if total_equity else 100.0
    invested_ratio = round(100.0 - cash_ratio, 1)

    return {
        "cash": round(cash, 2),
        "holdings_value": round(total_holdings_val, 2),
        "total_equity": round(total_equity, 2),
        "initial_balance": round(init_balance, 2),
        "realized_pnl": round(p.get("realized_pnl", 0.0), 2),
        "unrealized_pnl": round(total_holdings_val - sum(h["cost_basis"] for h in holdings), 2),
        "total_pnl": round(total_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        "win_rate": round(win_rate, 1),
        "profit_factor": profit_factor,
        "total_trades": len(trades),
        "concentration_risk": concentration_risk,
        "cash_ratio": cash_ratio,
        "invested_ratio": invested_ratio,
        "positions": holdings,
        "recent_trades": trades[-15:],
        "equity_history": p.get("equity_history", [
            {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "equity": round(total_equity, 2)}
        ])
    }

@app.post("/api/portfolio/trade")
async def execute_trade(req: TradeRequest):
    """Executes a virtual paper trade (BUY or SELL) with order typing and risk tracking."""
    sym = req.symbol.strip().upper()
    action = req.action.strip().upper()
    qty = int(req.quantity)

    if qty <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than 0")

    # Get live execution price
    try:
        t = yf.Ticker(sym)
        price = t.fast_info.last_price or 100.0
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot fetch price for {sym}: {e}")

    # Limit order price checking
    if req.order_type == "LIMIT" and req.limit_price:
        if action == "BUY" and price > req.limit_price:
            raise HTTPException(status_code=400, detail=f"Market price ${price:.2f} is above your BUY limit of ${req.limit_price:.2f}")
        if action == "SELL" and price < req.limit_price:
            raise HTTPException(status_code=400, detail=f"Market price ${price:.2f} is below your SELL limit of ${req.limit_price:.2f}")
        exec_price = req.limit_price
    else:
        exec_price = price

    total_order_val = exec_price * qty
    p = load_portfolio()
    positions = p.setdefault("positions", {})
    cash = p.get("cash", 10000.0)

    trade_record = {
        "id": f"TRD-{int(time.time())}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": action,
        "symbol": sym,
        "quantity": qty,
        "price": round(exec_price, 2),
        "total": round(total_order_val, 2),
        "order_type": req.order_type or "MARKET",
        "stop_loss": req.stop_loss,
        "take_profit": req.take_profit,
        "rationale": req.rationale or "Manual Desk Execution"
    }

    if action == "BUY":
        if cash < total_order_val:
            raise HTTPException(status_code=400, detail=f"Insufficient funds! Need ${total_order_val:.2f}, Cash available: ${cash:.2f}")
        
        # Deduct cash
        p["cash"] = cash - total_order_val
        if sym in positions:
            prev_qty = positions[sym]["quantity"]
            prev_cost = positions[sym]["cost_basis"]
            new_qty = prev_qty + qty
            new_cost = prev_cost + total_order_val
            positions[sym]["quantity"] = new_qty
            positions[sym]["cost_basis"] = new_cost
            positions[sym]["avg_price"] = new_cost / new_qty
            if req.stop_loss:
                positions[sym]["stop_loss"] = req.stop_loss
            if req.take_profit:
                positions[sym]["take_profit"] = req.take_profit
        else:
            positions[sym] = {
                "symbol": sym,
                "quantity": qty,
                "avg_price": round(exec_price, 2),
                "cost_basis": round(total_order_val, 2),
                "stop_loss": req.stop_loss,
                "take_profit": req.take_profit,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    elif action == "SELL":
        if sym not in positions or positions[sym]["quantity"] < qty:
            avail = positions.get(sym, {}).get("quantity", 0)
            raise HTTPException(status_code=400, detail=f"Cannot sell {qty} shares of {sym}. You currently hold {avail} shares.")

        pos = positions[sym]
        avg_cost = pos["avg_price"]
        pnl = (exec_price - avg_cost) * qty
        trade_record["pnl"] = round(pnl, 2)
        trade_record["pnl_pct"] = round((pnl / (avg_cost * qty) * 100), 2) if avg_cost else 0.0

        p["realized_pnl"] = p.get("realized_pnl", 0.0) + pnl
        p["cash"] = cash + total_order_val

        new_qty = pos["quantity"] - qty
        if new_qty == 0:
            del positions[sym]
        else:
            pos["quantity"] = new_qty
            pos["cost_basis"] = new_qty * avg_cost

    p.setdefault("trades", []).append(trade_record)

    # Update equity history trajectory
    holdings_val = sum(pos["quantity"] * pos["avg_price"] for pos in positions.values())
    current_equity = p["cash"] + holdings_val
    eq_history = p.setdefault("equity_history", [])
    eq_history.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "equity": round(current_equity, 2),
        "cash": round(p["cash"], 2)
    })
    # Keep last 50 data points
    p["equity_history"] = eq_history[-50:]

    save_portfolio(p)

    return {
        "status": "SUCCESS",
        "trade": trade_record,
        "message": f"Successfully executed {action} {qty} shares of {sym} at ${exec_price:.2f}"
    }

@app.post("/api/portfolio/reset")
async def reset_portfolio():
    """Resets paper trading account to $10,000 cash balance and 0 positions."""
    p = {
        "cash": 10000.0,
        "initial_balance": 10000.0,
        "positions": {},
        "trades": [],
        "realized_pnl": 0.0,
        "equity_history": [
            {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "equity": 10000.0, "cash": 10000.0}
        ]
    }
    save_portfolio(p)
    return {"status": "SUCCESS", "message": "Portfolio reset to clean $10,000 cash balance with 0 positions."}

# -----------------------------------------------------------------------------
# TradingAgents Multi-Persona Debate & FinGPT Intelligence Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/agent/debater")
async def get_multi_agent_debate(symbol: str = "AAPL"):
    """
    Simulates TradingAgents Multi-Persona Syndicate Debate:
    1. Bullish Researcher Agent
    2. Bearish Researcher Agent
    3. Chief Risk Officer (CRO) Kelly & Position Sizing for $10,000 account
    4. Synthesized Trader Verdict
    """
    sym = symbol.strip().upper()
    try:
        t = yf.Ticker(sym)
        fast = t.fast_info
        price = fast.last_price or 100.0
        hist = t.history(period="3mo", interval="1d")
        hist = compute_indicators(hist)
        latest = hist.iloc[-1] if not hist.empty else {}

        rsi = float(latest.get("RSI", 50))
        macd = float(latest.get("MACD", 0))
        sig = float(latest.get("MACD_Signal", 0))
        sma50 = float(latest.get("SMA50", price))

        # Position sizing calculations for $10,000 account:
        # Risk 2% of portfolio = $200 max risk per trade
        stop_dist = max(price * 0.04, 1.0)
        risk_2pct = 200.0
        suggested_qty = max(1, int(risk_2pct / stop_dist))
        alloc_val = suggested_qty * price

        bull_points = []
        bear_points = []

        if rsi < 40:
            bull_points.append(f"RSI reading of {rsi:.1f} indicates oversold conditions and potential mean reversion.")
        else:
            bear_points.append(f"RSI at {rsi:.1f} indicates momentum is elevated or consolidating.")

        if macd > sig:
            bull_points.append(f"MACD line ({macd:.2f}) is above signal line ({sig:.2f}), confirming positive short-term momentum.")
        else:
            bear_points.append(f"MACD line ({macd:.2f}) is trailing below signal line ({sig:.2f}), signaling downward pressure.")

        if price >= sma50:
            bull_points.append(f"Trading above 50-day SMA (${sma50:.2f}), maintaining intermediate bull trend structure.")
        else:
            bear_points.append(f"Trading below 50-day SMA (${sma50:.2f}), facing institutional overhead supply.")

        meta = SP500_MAP.get(sym, {})
        conviction = 7 if (price >= sma50 and macd > sig) else (4 if rsi <= 35 else 5)

        return {
            "symbol": sym,
            "company": meta.get("name", sym),
            "price": round(price, 2),
            "bull_case": {
                "persona": "🐂 Bullish Momentum Analyst",
                "thesis": f"Favorable risk/reward setup in {sym} supported by market liquidity.",
                "points": bull_points or ["Constructive consolidation near key support levels."]
            },
            "bear_case": {
                "persona": "🐻 Bearish Macro & Risk Analyst",
                "thesis": f"Downside vulnerability in {sym} due to multiple compression or resistance.",
                "points": bear_points or ["Broader macro volatility and sector rotation risks."]
            },
            "risk_assessment": {
                "persona": "🛡️ Chief Risk Officer (CRO)",
                "account_equity": 10000.0,
                "risk_tolerance_pct": "2.0% ($200.00)",
                "recommended_stop_loss": round(price - stop_dist, 2),
                "recommended_target": round(price + (stop_dist * 2.2), 2),
                "recommended_shares": suggested_qty,
                "capital_required": round(alloc_val, 2),
                "portfolio_exposure_pct": round((alloc_val / 10000.0 * 100), 1),
                "concentration_verdict": "SAFE (<25% Cap)" if alloc_val <= 2500.0 else "WARNING: High Allocation"
            },
            "verdict": {
                "action": "BUY" if conviction >= 6 else ("SELL / HEDGE" if conviction <= 4 else "HOLD / NEUTRAL"),
                "conviction_score": f"{conviction}/10"
            }
        }
    except Exception as e:
        logger.error(f"Error in multi-agent debater for {sym}: {e}")
        return {"error": str(e), "symbol": sym}

@app.get("/api/agent/briefing")
async def get_daily_desk_briefing():
    """
    FinGPT-style Morning / Desk Intelligence Note across S&P 500:
    Regime analysis, high-conviction setups, and portfolio risk briefing.
    """
    p = load_portfolio()
    movers = await run_sp500_scanner(strategy="all")
    results = movers.get("results", [])

    top_buys = [s for s in results if s.get("pct_change", 0) > 0 and s.get("rsi", 50) < 60][:3]
    top_hedges = [s for s in results if s.get("pct_change", 0) < 0][:2]

    return {
        "date": datetime.now().strftime("%A, %B %d, %Y"),
        "timestamp": datetime.now().strftime("%H:%M:%S EST"),
        "market_regime": "NEUTRAL / SELECTIVE MOMENTUM",
        "portfolio_health": {
            "account_equity": p.get("cash", 10000.0) + sum(pos.get("cost_basis", 0) for pos in p.get("positions", {}).values()),
            "active_positions_count": len(p.get("positions", {})),
            "cash_reserves": p.get("cash", 10000.0),
            "risk_profile": "CONSERVATIVE / DISCIPLINED ($10K BASE)"
        },
        "top_setups": top_buys,
        "watch_out": top_hedges
    }

# -----------------------------------------------------------------------------
# Chatbot Trader Agent Engine (Groq / Ollama / Fallback Quant Rule-Engine)
# -----------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str
    provider: Optional[str] = "groq"         # "groq" or "ollama" or "quant"
    model: Optional[str] = "llama-3.3-70b-versatile"
    groq_api_key: Optional[str] = ""
    ollama_base_url: Optional[str] = "http://localhost:11434"
    current_symbol: Optional[str] = "AAPL"

@app.get("/api/agent/models")
async def detect_models():
    """Detects available Ollama local models and provides recommended Groq models."""
    groq_models = [
        {"id": "llama-3.3-70b-versatile", "name": "Groq: Llama 3.3 70B (Recommended)"},
        {"id": "llama-3.1-8b-instant", "name": "Groq: Llama 3.1 8B (Ultra Fast)"},
        {"id": "mixtral-8x7b-32768", "name": "Groq: Mixtral 8x7B (32k Context)"},
        {"id": "gemma2-9b-it", "name": "Groq: Gemma 2 9B"}
    ]

    ollama_models = []
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=1.5)
        if resp.status_code == 200:
            tags = resp.json().get("models", [])
            for m in tags:
                ollama_models.append({
                    "id": m["name"],
                    "name": f"Ollama Local: {m['name']}"
                })
    except Exception:
        pass

    return {
        "groq": groq_models,
        "ollama": ollama_models,
        "ollama_online": len(ollama_models) > 0
    }

def fallback_quant_agent(prompt: str, symbol: str) -> dict:
    """
    Built-in Institutional Quantitative Analyst Engine.
    Executes technical calculations and delivers structured trading recommendations
    when LLM keys are absent.
    """
    sym = symbol.upper()
    # Check if prompt mentions a specific S&P 500 ticker
    words = re.findall(r"\b[A-Z]{1,5}\b", prompt.upper())
    for w in words:
        if w in SP500_MAP:
            sym = w
            break

    try:
        t = yf.Ticker(sym)
        hist = t.history(period="6mo", interval="1d")
        fast = t.fast_info
        price = fast.last_price or 100.0
        prev = fast.previous_close or price
        chg = price - prev
        pct = (chg / prev * 100) if prev else 0.0

        hist = compute_indicators(hist)
        latest = hist.iloc[-1]
        rsi = float(latest.get("RSI", 50.0))
        macd = float(latest.get("MACD", 0.0))
        sig = float(latest.get("MACD_Signal", 0.0))
        sma20 = float(latest.get("SMA20", price))
        sma50 = float(latest.get("SMA50", price))
        bb_up = float(latest.get("BB_Upper", price * 1.05))
        bb_low = float(latest.get("BB_Lower", price * 0.95))

        # Support & Resistance
        recent_high = float(hist["High"].tail(20).max())
        recent_low = float(hist["Low"].tail(20).min())

        # Determine signal
        score = 0
        reasons = []

        if rsi < 35:
            score += 2
            reasons.append(f"RSI is oversold at {rsi:.1f} (Mean-reversion bounce opportunity)")
        elif rsi > 65:
            score -= 2
            reasons.append(f"RSI is overbought at {rsi:.1f} (Extended momentum)")
        else:
            reasons.append(f"RSI is neutral at {rsi:.1f}")

        if macd > sig:
            score += 2
            reasons.append(f"MACD line ({macd:.2f}) is bullish above Signal ({sig:.2f})")
        else:
            score -= 2
            reasons.append(f"MACD line ({macd:.2f}) is bearish below Signal ({sig:.2f})")

        if price > sma50:
            score += 1
            reasons.append(f"Trading above 50-day SMA (${sma50:.2f}) - Uptrend intact")
        else:
            score -= 1
            reasons.append(f"Trading below 50-day SMA (${sma50:.2f}) - Short-term pressure")

        verdict = "STRONG BUY" if score >= 3 else ("BUY" if score >= 1 else ("NEUTRAL / HOLD" if score == 0 else ("SELL" if score >= -2 else "STRONG SELL")))

        # Strategy setup
        entry = price
        stop_loss = round(recent_low * 0.985, 2)
        target = round(recent_high * 1.02, 2)
        rr_ratio = round(abs(target - entry) / max(0.01, abs(entry - stop_loss)), 2)

        reply = f"""### 📊 Institutional Quantitative Trader Analysis: **{sym}**

**Current Price:** `${price:.2f}` ({'+' if chg >= 0 else ''}{chg:.2f} / {'+' if pct >= 0 else ''}{pct:.2f}%)  
**Composite Technical Verdict:** **`{verdict}`** (Quant Score: {score}/5)

---

#### 📈 Key Technical Indicators:
- **RSI (14):** `{rsi:.1f}` — {'🟢 Oversold' if rsi <= 35 else ('🔴 Overbought' if rsi >= 65 else '⚪ Neutral')}
- **MACD (12,26,9):** `{macd:.2f}` vs Signal `{sig:.2f}` ({'🟢 Bullish Crossover' if macd > sig else '🔴 Bearish Alignment'})
- **Moving Averages:** 20 SMA: `${sma20:.2f}` | 50 SMA: `${sma50:.2f}`
- **Bollinger Bands:** Upper: `${bb_up:.2f}` | Lower: `${bb_low:.2f}`

#### 🎯 Actionable Trading Setup:
- **Recommended Entry:** `${entry:.2f}`
- **Stop Loss:** `${stop_loss:.2f}` (Below 20D Low)
- **Target Price:** `${target:.2f}` (Near Resistance)
- **Risk / Reward Ratio:** `1 : {rr_ratio}`

#### 💡 Analyst Insights:
- {'; '.join(reasons)}.
- To execute a simulated paper trade, type: `BUY {sym} <quantity>` or `SELL {sym} <quantity>`.
"""
        return {"response": reply, "symbol": sym, "data": {"price": price, "verdict": verdict}}
    except Exception as e:
        return {"response": f"Quant analysis error for {sym}: {e}", "symbol": sym}

@app.post("/api/agent/chat")
async def chat_with_agent(req: ChatRequest):
    """
    Main Chatbot Trader Agent endpoint.
    Orchestrates Groq, Ollama, and Tool calls (Paper Trading & Technical analysis).
    """
    prompt = req.message.strip()
    provider = (req.provider or "groq").lower()
    symbol = (req.current_symbol or "AAPL").upper()

    # 1. Detect if the user wants to execute a paper trade directly through chat:
    # E.g.: "Buy 25 shares of NVDA", "Sell 10 AAPL"
    trade_match = re.search(r"\b(BUY|SELL)\s+(\d+)\s+(?:SHARES\s+OF\s+)?([A-Z]{1,5})\b", prompt.upper())
    if trade_match:
        action, qty_str, trade_sym = trade_match.groups()
        try:
            trade_res = await execute_trade(TradeRequest(action=action, symbol=trade_sym, quantity=int(qty_str)))
            return {
                "response": f"✅ **Paper Trade Executed Successfully!**\n\n- **Action:** `{action}`\n- **Symbol:** `{trade_sym}`\n- **Quantity:** `{qty_str}` shares\n- **Fill Price:** `${trade_res['trade']['price']:.2f}`\n- **Total Consideration:** `${trade_res['trade']['total']:.2f}`\n\n*Your portfolio ledger has been updated.*",
                "trade": trade_res["trade"]
            }
        except HTTPException as e:
            return {"response": f"⚠️ **Trade Rejected:** {e.detail}"}

    # 2. Extract mentioned ticker if any
    tickers = re.findall(r"\b[A-Z]{1,5}\b", prompt.upper())
    target_sym = symbol
    for t in tickers:
        if t in SP500_MAP:
            target_sym = t
            break

    # 3. Detect Syndicate Multi-Agent Debate intent (TradingAgents Model)
    if any(k in prompt.lower() for k in ["debate", "bull vs bear", "syndicate", "cro", "adversarial"]):
        deb = await get_multi_agent_debate(target_sym)
        bull = deb.get("bull_case", {})
        bear = deb.get("bear_case", {})
        cro = deb.get("risk_assessment", {})
        verdict = deb.get("verdict", {})

        bull_text = "\n".join([f"  • {p}" for p in bull.get("points", [])])
        bear_text = "\n".join([f"  • {p}" for p in bear.get("points", [])])

        debate_md = f"""### 🥊 Multi-Agent Syndicate Debate: **{target_sym}** (${deb.get('price', 0):.2f})
*TradingAgents Adversarial Institutional Framework*

---

#### {bull.get('persona', '🐂 Bull Analyst')}
> *"{bull.get('thesis', '')}"*
{bull_text}

#### {bear.get('persona', '🐻 Bear Analyst')}
> *"{bear.get('thesis', '')}"*
{bear_text}

---

#### {cro.get('persona', '🛡️ Chief Risk Officer (CRO)')}
- **Account Capital Baseline:** `${cro.get('account_equity', 10000.0):,.2f}` (Disciplined Paper Account)
- **Max Account Risk Per Trade:** `{cro.get('risk_tolerance_pct', '2% ($200)')}`
- **Recommended Position Sizing:** **`{cro.get('recommended_shares', 10)} shares`** (`${cro.get('capital_required', 0):,.2f}` exposure)
- **Stop-Loss Protection:** `${cro.get('recommended_stop_loss', 0):.2f}`
- **Profit Target:** `${cro.get('recommended_target', 0):.2f}`
- **Concentration Risk Check:** **`{cro.get('concentration_verdict', 'SAFE')}`** ({cro.get('portfolio_exposure_pct', 0)}% of account)

---

### ⚖️ Final Synthesized Verdict: **`{verdict.get('action', 'HOLD')}`**
**Conviction Score:** `{verdict.get('conviction_score', '5/10')}`  
*Say `Buy {cro.get('recommended_shares', 10)} {target_sym}` to execute this trade on your paper desk.*
"""
        return {"response": debate_md, "provider": "TradingAgents Syndicate"}

    # 4. Detect Daily Desk Briefing intent (FinGPT Model)
    if any(k in prompt.lower() for k in ["brief", "briefing", "morning note", "desk report"]):
        brief = await get_daily_desk_briefing()
        buys = brief.get("top_setups", [])
        buys_text = "\n".join([f"  • **{b['symbol']}** (${b['price']:.2f}): RSI `{b['rsi']}`, MACD `{b['macd']:.2f}` — Signals: `{', '.join(b['signals'][:2])}`" for b in buys]) or "  • Consolidating markets; awaiting breakout confirmation."

        briefing_md = f"""### 📋 S&P 500 Daily Desk Intelligence Brief
**Date:** {brief.get('date')} | **Wire Time:** {brief.get('timestamp')}  
**Macro Market Regime:** **`{brief.get('market_regime')}`**

---

#### 💼 Portfolio Health & Risk Parameters ($10K Base):
- **Account Status:** Active Capital `${brief.get('portfolio_health', {}).get('account_equity', 10000.0):,.2f}`
- **Cash Reserves:** `${brief.get('portfolio_health', {}).get('cash_reserves', 10000.0):,.2f}`
- **Risk Posture:** `{brief.get('portfolio_health', {}).get('risk_profile')}`

#### 🎯 High-Conviction S&P 500 Opportunities:
{buys_text}

---
*Ask: `Debate <SYMBOL>` to trigger multi-agent cross-examination on any candidate.*
"""
        return {"response": briefing_md, "provider": "FinGPT Desk Intelligence"}

    # Fetch live context for the LLM
    context_data = ""
    try:
        t = yf.Ticker(target_sym)
        fast = t.fast_info
        c_price = fast.last_price or 0.0
        c_prev = fast.previous_close or c_price
        c_pct = ((c_price - c_prev) / c_prev * 100) if c_prev else 0.0
        
        hist = t.history(period="1mo", interval="1d")
        if not hist.empty:
            hist = compute_indicators(hist)
            row = hist.iloc[-1]
            rsi = row.get("RSI", 50.0)
            macd = row.get("MACD", 0.0)
            sig = row.get("MACD_Signal", 0.0)
            sma20 = row.get("SMA20", c_price)
            sma50 = row.get("SMA50", c_price)
            context_data = f"""
LIVE MARKET CONTEXT FOR {target_sym}:
- Price: ${c_price:.2f} ({'+' if c_pct >= 0 else ''}{c_pct:.2f}%)
- RSI (14): {rsi:.1f}
- MACD: {macd:.2f} | Signal: {sig:.2f}
- 20 SMA: ${sma20:.2f} | 50 SMA: ${sma50:.2f}
- 52W High: ${fast.year_high or 0:.2f} | 52W Low: ${fast.year_low or 0:.2f}
- Sector: {SP500_MAP.get(target_sym, {}).get('sector', 'S&P 500')}
"""
    except Exception:
        pass

    system_prompt = f"""You are the Antigravity S&P 500 AI Trader Agent, an institutional quantitative hedge fund trader and technical analyst.
You specialize strictly in S&P 500 equities.
You analyze technical indicators (RSI, MACD, Bollinger Bands, Moving Averages), fundamental valuation, market sentiment, and provide clear trade setups (Entry, Target, Stop Loss).
Keep responses structured, concise, and professional using markdown tables, bullet points, and exact numbers.
If the user asks to execute a paper trade, instruct them they can say 'Buy <qty> <symbol>' or 'Sell <qty> <symbol>'.

{context_data}
"""

    # 3. Provider execution:
    # A) Groq
    groq_api_key = (req.groq_api_key or os.environ.get("GROQ_API_KEY", "")).strip()
    if provider == "groq" and groq_api_key:
        try:
            headers = {
                "Authorization": f"Bearer {groq_api_key}",
                "Content-Type": "application/json"
            }
            body = {
                "model": req.model or "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.3,
                "max_tokens": 1024
            }
            res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body, timeout=15)
            if res.status_code == 200:
                answer = res.json()["choices"][0]["message"]["content"]
                return {"response": answer, "provider": "Groq", "model": req.model}
            else:
                logger.warning(f"Groq error: {res.text}")
        except Exception as e:
            logger.error(f"Groq call failed: {e}")

    # B) Ollama Local
    if provider == "ollama":
        try:
            base_url = (req.ollama_base_url or os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")).rstrip("/")
            body = {
                "model": req.model or "llama3",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "stream": False
            }
            res = requests.post(f"{base_url}/api/chat", json=body, timeout=25)
            if res.status_code == 200:
                answer = res.json().get("message", {}).get("content", "")
                return {"response": answer, "provider": "Ollama Local", "model": req.model}
        except Exception as e:
            logger.warning(f"Ollama call failed: {e}")

    # C) Fallback Smart Quantitative Rule-Based Engine
    quant_result = fallback_quant_agent(prompt, target_sym)
    return {
        "response": quant_result["response"],
        "provider": "Quantitative Rule Engine (Autonomous)",
        "note": "For custom LLM dialogue, enter your Groq API key or connect Ollama in Settings."
    }

# Mount static directory
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def root():
    return FileResponse(STATIC_DIR / "index.html")

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    is_dev = os.environ.get("ENV", "development").lower() == "development"
    uvicorn.run("server:app", host=host, port=port, reload=is_dev)
