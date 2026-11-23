"""
AdversarialIQ Historical Market Data Vault & 5-Year High-Speed Cache
Maintains pre-fetched, indexed 5-year daily OHLCV & technicals for 10 marquee S&P 500 stocks:
AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, BRK-B, JPM, V.
Enables sub-millisecond backtest execution without external network latency.
"""

import logging
import os
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from src.core.config import DATA_DIR, SP500_MAP

logger = logging.getLogger("BacktestDataStore")

HISTORICAL_DIR = DATA_DIR / "historical"
HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)

# 10 Marquee S&P 500 Leaders representing diversified economic sectors
MARQUEE_TICKERS = [
    {"symbol": "AAPL", "name": "Apple Inc.", "sector": "Information Technology", "cap": "Mega"},
    {"symbol": "MSFT", "name": "Microsoft Corporation", "sector": "Information Technology", "cap": "Mega"},
    {"symbol": "NVDA", "name": "NVIDIA Corporation", "sector": "Semiconductors", "cap": "Mega"},
    {"symbol": "AMZN", "name": "Amazon.com Inc.", "sector": "Consumer Discretionary", "cap": "Mega"},
    {"symbol": "GOOGL", "name": "Alphabet Inc.", "sector": "Communication Services", "cap": "Mega"},
    {"symbol": "META", "name": "Meta Platforms Inc.", "sector": "Communication Services", "cap": "Mega"},
    {"symbol": "TSLA", "name": "Tesla Inc.", "sector": "Automotive / Clean Energy", "cap": "Mega"},
    {"symbol": "BRK-B", "name": "Berkshire Hathaway Inc.", "sector": "Financials", "cap": "Mega"},
    {"symbol": "JPM", "name": "JPMorgan Chase & Co.", "sector": "Financials / Banking", "cap": "Large"},
    {"symbol": "V", "name": "Visa Inc.", "sector": "Financial Services / Payments", "cap": "Large"},
]


def compute_vectorized_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Computes full suite of vectorized technical indicators for algorithmic backtests."""
    df = df.copy()
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    # Moving averages
    df["SMA_20"] = close.rolling(window=20).mean()
    df["SMA_50"] = close.rolling(window=50).mean()
    df["SMA_200"] = close.rolling(window=200).mean()

    df["EMA_12"] = close.ewm(span=12, adjust=False).mean()
    df["EMA_26"] = close.ewm(span=26, adjust=False).mean()

    # MACD
    df["MACD"] = df["EMA_12"] - df["EMA_26"]
    df["MACD_SIGNAL"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_HIST"] = df["MACD"] - df["MACD_SIGNAL"]

    # RSI (14)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -1 * delta.clip(upper=0)
    avg_gain = gain.rolling(window=14).mean()
    avg_loss = loss.rolling(window=14).mean()
    rs = avg_gain / (avg_loss + 1e-9)
    df["RSI_14"] = 100 - (100 / (1 + rs))

    # Bollinger Bands (20, 2 std)
    rolling_std = close.rolling(window=20).std()
    df["BB_UPPER"] = df["SMA_20"] + (rolling_std * 2)
    df["BB_LOWER"] = df["SMA_20"] - (rolling_std * 2)

    # Average True Range (ATR 14)
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR_14"] = true_range.rolling(window=14).mean()

    # Daily Return
    df["Daily_Return"] = close.pct_change()

    return df


class BacktestDataStore:
    """Manages downloading, local caching, and rapid query of 5-year OHLCV data."""

    @classmethod
    def get_cache_path(cls, symbol: str) -> Path:
        clean_sym = symbol.strip().upper().replace("/", "_").replace(".", "_")
        return HISTORICAL_DIR / f"{clean_sym}_5y.csv"

    @classmethod
    def load_symbol_history(
        cls,
        symbol: str,
        period: str = "5y",
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """
        Loads 5-year OHLCV data with technical indicators from local cache.
        If cache is missing or stale (>24h), downloads from yfinance and caches locally.
        """
        sym = symbol.strip().upper()
        cache_path = cls.get_cache_path(sym)

        # 1. Check local cache freshness (valid for 24 hours)
        if not force_refresh and cache_path.exists():
            file_age = time.time() - os.path.getmtime(cache_path)
            if file_age < 86400:  # 24 hours
                try:
                    df = pd.read_csv(cache_path, index_col=0, parse_dates=True)
                    if not df.empty and len(df) > 500:
                        return df
                except Exception as e:
                    logger.warning(f"Error reading cache for {sym}: {e}, re-fetching")

        # 2. Fetch fresh 5y data from yfinance
        logger.info(f"Downloading 5-year historical data for {sym} via yfinance...")
        try:
            ticker = yf.Ticker(sym)
            raw = ticker.history(period="5y")
            if raw.empty:
                raise ValueError(f"No historical data returned for {sym}")

            # Keep required columns
            cols = [c for c in ["Open", "High", "Low", "Close", "Volume"] if c in raw.columns]
            df = raw[cols].copy()

            # Ensure timezone-naive index for portable CSV parsing
            if df.index.tz is not None:
                df.index = df.index.tz_localize(None)

            # Compute technical indicators
            enriched_df = compute_vectorized_indicators(df)

            # Cache to disk
            enriched_df.to_csv(cache_path)
            logger.info(f"Successfully cached {len(enriched_df)} bars of 5y data for {sym}")
            return enriched_df

        except Exception as e:
            logger.error(f"Failed to fetch historical data for {sym}: {e}")
            # If fetch fails but stale cache exists, return stale cache
            if cache_path.exists():
                return pd.read_csv(cache_path, index_col=0, parse_dates=True)
            raise e

    @classmethod
    def preload_all_marquee(cls, force_refresh: bool = False) -> Dict[str, Any]:
        """Preloads 5-year history for all 10 marquee stocks."""
        results = {}
        for item in MARQUEE_TICKERS:
            sym = item["symbol"]
            try:
                df = cls.load_symbol_history(sym, force_refresh=force_refresh)
                results[sym] = {
                    "status": "CACHED",
                    "rows": len(df),
                    "start_date": str(df.index[0])[:10],
                    "end_date": str(df.index[-1])[:10],
                    "last_close": round(float(df["Close"].iloc[-1]), 2)
                }
            except Exception as e:
                results[sym] = {"status": "FAILED", "error": str(e)}

        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "total_cached": sum(1 for r in results.values() if r.get("status") == "CACHED"),
            "details": results
        }

    @classmethod
    def get_marquee_catalog(cls) -> List[Dict[str, Any]]:
        """Returns catalog of marquee stocks with cache status."""
        catalog = []
        for item in MARQUEE_TICKERS:
            sym = item["symbol"]
            cache_file = cls.get_cache_path(sym)
            cached = cache_file.exists()
            last_updated = datetime.fromtimestamp(os.path.getmtime(cache_file)).strftime("%Y-%m-%d %H:%M") if cached else None

            catalog.append({
                **item,
                "cached": cached,
                "last_cached": last_updated
            })
        return catalog
