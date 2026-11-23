"""
Global Configuration & Environment Settings for S&P 500 AI Trader Terminal
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Logging setup
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("SP500Trader")

# Directory Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STATIC_DIR = BASE_DIR / "static"
SP500_FILE = DATA_DIR / "sp500.json"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"

# Server Network Configuration
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))
ENV = os.environ.get("ENV", "development")
IS_DEV = ENV.lower() == "development"

# SEC EDGAR Identity (User-Agent header required by SEC fair access policy)
SEC_EDGAR_IDENTITY = os.environ.get("SEC_EDGAR_IDENTITY", "AdversarialIQ diwasunnyhack519@gmail.com")

# External Data Layer API Keys
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FINNHUB_API_KEY = os.environ.get("FINNHUB_API_KEY", "")

# AI Model Provider Credentials
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")

# Load S&P 500 Master Catalog
SP500_STOCKS: List[dict] = []
if SP500_FILE.exists():
    try:
        with open(SP500_FILE, "r", encoding="utf-8") as f:
            SP500_STOCKS = json.load(f)
        logger.info(f"Loaded {len(SP500_STOCKS)} S&P 500 stocks from catalog.")
    except Exception as e:
        logger.error(f"Error loading S&P 500 file: {e}")

SP500_MAP = {s["symbol"]: s for s in SP500_STOCKS}

# High-Liquidity Preset Universe for live scanner
SCANNER_PRESET_STOCKS = [
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "META", "TSLA", "BRK-B",
    "JPM", "V", "UNH", "XOM", "JNJ", "WMT", "PG", "MA", "LLY", "HD",
    "CVX", "MRK", "ABBV", "COST", "KO", "PEP", "AVGO", "BAC", "AMD",
    "TMO", "CSCO", "ADBE", "ORCL", "NFLX", "CRM", "INTC", "QCOM", "WFC"
]

# In-Memory Cache System
CACHE: Dict[str, dict] = {}
CACHE_TTL = {
    "quote": 2,           # 2 seconds
    "history": 15,        # 15 seconds
    "company": 60,        # 1 minute
    "sec_filings": 300,   # 5 minutes
    "insider": 300,       # 5 minutes
    "news": 60,           # 1 minute
    "macro": 120,         # 2 minutes
    "scanner": 20,        # 20 seconds
    "benchmarks": 3       # 3 seconds
}

def get_cached(key: str, ttl_seconds: int) -> Optional[Any]:
    entry = CACHE.get(key)
    if not entry:
        return None
    if time.time() - entry["timestamp"] > ttl_seconds:
        del CACHE[key]
        return None
    return entry["data"]

def set_cached(key: str, data: Any):
    CACHE[key] = {"data": data, "timestamp": time.time()}
