"""
S&P 500 AI Trading Terminal & Multi-Agent Syndicate Server
Production FastAPI Application orchestrating:
1. Real-time Market Data & Technicals (yfinance)
2. SEC EDGAR 10-K/10-Q/8-K Filings & MD&A (edgartools)
3. SEC Form 4 Insider Trades & 13F Ownership
4. Breaking News & Catalyst Sentiment (Finnhub & RSS)
5. Macroeconomic Regime & Treasury Yield Curve (FRED & CBOE)
6. Institutional Paper Trading Portfolio ($10,000 Starting Base)
7. Multi-Persona TradingAgents Syndicate & On-Demand LLM Engine
"""

import logging
import os
import warnings
from typing import Dict, List, Optional
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.agent_syndicate import (
    get_daily_desk_briefing,
    get_multi_agent_debate,
    process_chat_message,
)
from src.config import (
    HOST,
    IS_DEV,
    PORT,
    SP500_MAP,
    SP500_STOCKS,
    STATIC_DIR,
)
from src.llm import LLMManager
from src.macro import fetch_macro_regime
from src.market_data import (
    fetch_benchmarks,
    fetch_company_details,
    fetch_stock_history,
    fetch_stock_quote,
)
from src.news import fetch_breaking_news
from src.portfolio import (
    execute_order,
    get_portfolio_state,
    load_portfolio,
    reset_portfolio,
)
from src.scanner import get_market_movers, run_sp500_scanner
from src.sec_edgar import fetch_insider_and_13f_activity, fetch_sec_filings

# Suppress warnings
warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("SP500Trader.Server")

app = FastAPI(
    title="AdversarialIQ - S&P 500 AI Trading Terminal",
    description="Institutional AI Syndicate & Bloomberg-Grade Trading Terminal",
    version="4.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Request Schemas
# -----------------------------------------------------------------------------
class TradeRequest(BaseModel):
    action: str  # BUY or SELL
    symbol: str
    quantity: int
    order_type: Optional[str] = "MARKET"
    limit_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    rationale: Optional[str] = "Manual Desk Execution"


class ChatRequest(BaseModel):
    message: str
    provider: Optional[str] = "groq"
    model: Optional[str] = "llama-3.3-70b-versatile"
    groq_api_key: Optional[str] = ""
    ollama_base_url: Optional[str] = "http://localhost:11434"
    current_symbol: Optional[str] = "AAPL"


class PingRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


# -----------------------------------------------------------------------------
# Universe & Catalog Endpoints
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
    """Returns all 11 GICS sectors with constituent counts and sample leaders."""
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
    """Live S&P 500, Dow Jones, Nasdaq, VIX, and Oil benchmarks ribbon."""
    return fetch_benchmarks()


# -----------------------------------------------------------------------------
# Stock Market Data Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/stock/{symbol}/quote")
async def get_stock_quote(symbol: str):
    """Fast real-time quote for an S&P 500 stock."""
    try:
        return fetch_stock_quote(symbol)
    except Exception as e:
        logger.error(f"Error fetching quote for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stock/{symbol}/history")
async def get_stock_history(
    symbol: str,
    period: str = Query("1mo", regex="^(1d|5d|1mo|6mo|1y|5y)$")
):
    """Returns candlestick OHLCV data with pre-calculated technical indicators."""
    return fetch_stock_history(symbol, period)


@app.get("/api/stock/{symbol}/company")
async def get_company_details(symbol: str):
    """Comprehensive company profile, valuation metrics, and sector peer comparison."""
    try:
        return fetch_company_details(symbol)
    except Exception as e:
        logger.error(f"Error fetching company details for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# -----------------------------------------------------------------------------
# Multi-Layer Data Integrations (SEC, Insider 13F, News, Macro)
# -----------------------------------------------------------------------------
@app.get("/api/stock/{symbol}/sec")
async def get_sec_filings(symbol: str):
    """Fetches SEC EDGAR 10-K, 10-Q, 8-K filings, MD&A, and Risk Factors via edgartools."""
    try:
        return fetch_sec_filings(symbol)
    except Exception as e:
        logger.error(f"Error fetching SEC filings for {symbol}: {e}")
        return {"error": str(e), "symbol": symbol, "filings": []}


@app.get("/api/stock/{symbol}/insider")
async def get_insider_activity(symbol: str):
    """Fetches SEC Form 4 insider transactions, executive cluster signals, and 13F ownership."""
    try:
        return fetch_insider_and_13f_activity(symbol)
    except Exception as e:
        logger.error(f"Error fetching insider activity for {symbol}: {e}")
        return {"error": str(e), "symbol": symbol, "cluster_verdict": "NEUTRAL"}


@app.get("/api/stock/{symbol}/news")
async def get_stock_news(symbol: str):
    """Fetches real-time company breaking news, catalyst tags, and financial sentiment polarity."""
    try:
        return fetch_breaking_news(symbol)
    except Exception as e:
        logger.error(f"Error fetching news for {symbol}: {e}")
        return {"error": str(e), "symbol": symbol, "articles": []}


@app.get("/api/macro/regime")
async def get_macro_regime():
    """Fetches macroeconomic indicators, 10Y-2Y yield curve spread, and volatility regime."""
    try:
        return fetch_macro_regime()
    except Exception as e:
        logger.error(f"Error fetching macro regime: {e}")
        return {"error": str(e), "regime": "NEUTRAL"}


# -----------------------------------------------------------------------------
# S&P 500 Scanner & Market Pulse
# -----------------------------------------------------------------------------
@app.get("/api/scanner/run")
async def run_scanner(strategy: str = "all"):
    """Scans S&P 500 stocks across technical setups (RSI oversold/overbought, MACD crosses, trend)."""
    return run_sp500_scanner(strategy)


@app.get("/api/market/movers")
async def get_movers():
    """Returns S&P 500 top gainers, top losers, and most active stocks."""
    return get_market_movers()


# -----------------------------------------------------------------------------
# Paper Trading Portfolio ($10,000 Clean Baseline)
# -----------------------------------------------------------------------------
@app.get("/api/portfolio/get")
async def get_portfolio():
    """Returns live paper portfolio with risk metrics (Win Rate, Profit Factor, Concentration Cap)."""
    return get_portfolio_state()


@app.post("/api/portfolio/trade")
async def post_trade(req: TradeRequest):
    """Executes a virtual paper trade (BUY or SELL) with order typing and risk tracking."""
    try:
        res = execute_order(
            action=req.action,
            symbol=req.symbol,
            quantity=req.quantity,
            order_type=req.order_type or "MARKET",
            limit_price=req.limit_price,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
            rationale=req.rationale or "Manual Desk Execution"
        )
        return res
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Trade execution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/portfolio/reset")
async def reset_portfolio_endpoint():
    """Resets paper trading account to $10,000 cash balance and 0 positions."""
    reset_portfolio()
    return {"status": "SUCCESS", "message": "Portfolio reset to clean $10,000 cash balance with 0 positions."}


# -----------------------------------------------------------------------------
# AI Agent Syndicate & On-Demand LLM Health Check
# -----------------------------------------------------------------------------
@app.get("/api/agent/models")
async def get_models():
    """Detects available Ollama local models and provides recommended Groq models."""
    return LLMManager.get_models_catalog()


@app.post("/api/agent/provider/ping")
async def ping_provider_endpoint(req: PingRequest):
    """
    On-Demand Health Tester: sends a lightweight 1-token request ONLY when user switches or tests a provider.
    Strictly avoids background polling loops to preserve rate limits.
    """
    return LLMManager.ping_provider(
        provider=req.provider,
        model=req.model,
        api_key=req.api_key,
        base_url=req.base_url
    )


@app.get("/api/agent/debater")
async def get_debate(symbol: str = "AAPL"):
    """TradingAgents Multi-Persona Syndicate Debate (Bull Analyst vs Bear Risk Officer vs CRO)."""
    return get_multi_agent_debate(symbol)


@app.get("/api/agent/briefing")
async def get_briefing():
    """FinGPT Morning Desk Intelligence Note across S&P 500."""
    scan_res = run_sp500_scanner(strategy="all")
    return get_daily_desk_briefing(scan_res.get("results", []))


@app.post("/api/agent/chat")
async def chat_endpoint(req: ChatRequest):
    """Chatbot Trader Agent endpoint with full multi-layer context and automatic failover."""
    return process_chat_message(
        message=req.message,
        provider=req.provider or "groq",
        model=req.model or "llama-3.3-70b-versatile",
        groq_api_key=req.groq_api_key or "",
        ollama_base_url=req.ollama_base_url or "http://localhost:11434",
        current_symbol=req.current_symbol or "AAPL"
    )


# -----------------------------------------------------------------------------
# Static Frontend Serving
# -----------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
async def serve_home():
    return FileResponse(STATIC_DIR / "index.html")


if __name__ == "__main__":
    logger.info(f"Starting S&P 500 Trader Terminal on http://{HOST}:{PORT}")
    uvicorn.run("server:app", host=HOST, port=PORT, reload=IS_DEV)
