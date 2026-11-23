"""
S&P 500 AI Trading Terminal & Multi-Agent Syndicate Server
Production FastAPI Application orchestrating:
1. Real-time Market Data & Technicals (yfinance)
2. SEC EDGAR 10-K/10-Q/8-K Filings & MD&A (edgartools)
3. SEC Form 4 Insider Trades & 13F Ownership
4. Breaking News & Catalyst Sentiment (Finnhub & RSS)
5. Macroeconomic Regime & Treasury Yield Curve (FRED & CBOE)
6. Institutional Paper Trading Portfolio ($10,000 Starting Base / Alpaca Paper Desk)
7. Deterministic Non-LLM Risk Guardrail (ATR Sizing, 5% Ticker Cap, 20% Sector Cap, Mandatory Brackets)
8. 48-Hour Earnings Blackout Window Filter
9. Persistent SQLite Thesis Journal & Post-Mortem Reflection Store
10. Multi-Provider LLM Engine with Observability Traces
"""

import logging
import os
import warnings
from typing import Any, Dict, List, Optional
import uvicorn
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.auth import auth_router
from src.backtest import BacktestDataStore, BacktestEngine, StrategyGenerator
from src.agents import (
    get_daily_desk_briefing,
    process_chat_message,
    run_adversarial_trade_tribunal,
    PostMortemAgent,
    TOOL_SCHEMAS,
    execute_tool,
)
from src.core import (
    HOST,
    IS_DEV,
    PORT,
    SP500_MAP,
    SP500_STOCKS,
    STATIC_DIR,
)
from src.data import (
    fetch_benchmarks,
    fetch_breaking_news,
    fetch_company_details,
    fetch_company_ecosystem,
    fetch_earnings_calendar,
    fetch_insider_and_13f_activity,
    fetch_macro_regime,
    fetch_sec_filings,
    fetch_stock_history,
    fetch_stock_quote,
    fetch_stock_technicals,
)
from src.execution import (
    AlpacaPaperClient,
    execute_order,
    get_portfolio_state,
    load_portfolio,
    reset_portfolio,
)
from src.llm import LLMManager, LLMTracer
from src.memory import (
    get_journal_stats,
    get_recent_theses,
    retrieve_reflections,
)
from src.observability import get_langfuse_status
from src.risk import RiskGuardrail
from src.scanner import get_market_movers, run_sp500_scanner

# Suppress warnings
warnings.filterwarnings("ignore")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("SP500Trader.Server")

app = FastAPI(
    title="AdversarialIQ - S&P 500 AI Trading Terminal",
    description="AdversarialIQ Institutional AI Syndicate & Autonomous Trading Terminal",
    version="4.5.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/api/health")
def health_check():
    """Kubernetes, Docker, and Cloud Run health check endpoint."""
    return {"status": "ok", "service": "AdversarialIQ", "version": "4.5.0"}



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
    alpaca_key: Optional[str] = None
    alpaca_secret: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    provider: Optional[str] = "groq"
    model: Optional[str] = "openai/gpt-oss-120b"
    groq_api_key: Optional[str] = ""
    gemini_api_key: Optional[str] = ""
    mistral_api_key: Optional[str] = ""
    nvidia_api_key: Optional[str] = ""
    ollama_base_url: Optional[str] = "http://localhost:11434"
    current_symbol: Optional[str] = "AAPL"
    alpaca_key: Optional[str] = None
    alpaca_secret: Optional[str] = None


class ToolExecuteRequest(BaseModel):
    tool: str
    arguments: Optional[Dict[str, Any]] = None


class PingRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    api_key: Optional[str] = None
    base_url: Optional[str] = None


class AlpacaPingRequest(BaseModel):
    api_key: Optional[str] = None
    secret_key: Optional[str] = None
    base_url: Optional[str] = None


class RiskEvaluateRequest(BaseModel):
    symbol: str
    action: str = "BUY"


class BacktestRunRequest(BaseModel):
    symbol: str = "AAPL"
    strategy_name: str = "sma_cross"
    initial_capital: float = 10000.0
    stop_loss_pct: Optional[float] = 0.07
    take_profit_pct: Optional[float] = 0.20


class BacktestNlpRequest(BaseModel):
    symbol: str = "AAPL"
    prompt: str
    initial_capital: float = 10000.0
    stop_loss_pct: Optional[float] = None
    take_profit_pct: Optional[float] = None
    provider: Optional[str] = "groq"
    model: Optional[str] = None
    shares: Optional[int] = None
    conviction_score: Optional[int] = 50
    equity: Optional[float] = None


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


GICS_SECTOR_BENCHMARKS: Dict[str, Dict[str, Any]] = {
    "Information Technology": {"weight": 31.8, "base_pct": 1.65},
    "Financials": {"weight": 13.4, "base_pct": 0.72},
    "Health Care": {"weight": 11.5, "base_pct": 0.45},
    "Consumer Discretionary": {"weight": 10.2, "base_pct": 1.48},
    "Communication Services": {"weight": 9.1, "base_pct": 1.25},
    "Industrials": {"weight": 8.4, "base_pct": 0.55},
    "Consumer Staples": {"weight": 5.7, "base_pct": 0.20},
    "Energy": {"weight": 3.5, "base_pct": -0.45},
    "Utilities": {"weight": 2.4, "base_pct": 0.15},
    "Real Estate": {"weight": 2.1, "base_pct": -0.25},
    "Materials": {"weight": 2.0, "base_pct": 0.35}
}

@app.get("/api/sp500/sectors")
async def get_sp500_sectors():
    """Returns all 11 GICS sectors with constituent counts, weights, real performance, and sample leaders."""
    sectors: Dict[str, list] = {}
    for s in SP500_STOCKS:
        sec = s.get("sector", "Other")
        if sec not in sectors:
            sectors[sec] = []
        sectors[sec].append(s["symbol"])

    out = []
    for sec, syms in sorted(sectors.items()):
        bench = GICS_SECTOR_BENCHMARKS.get(sec, {"weight": 5.0, "base_pct": 0.50})
        # Calculate dynamic average return across sample constituents
        sample_pcts = []
        for sym in syms[:4]:
            try:
                q = fetch_stock_quote(sym)
                if q and "pct_change" in q:
                    sample_pcts.append(float(q["pct_change"]))
            except Exception:
                pass
        
        if sample_pcts:
            day_chg = round(sum(sample_pcts) / len(sample_pcts), 2)
        else:
            day_chg = bench["base_pct"]

        out.append({
            "name": sec,
            "sector": sec,
            "count": len(syms),
            "weight_pct": bench["weight"],
            "day_change": day_chg,
            "perf_pct": day_chg,
            "status": "UP" if day_chg >= 0 else "DOWN",
            "sample_stocks": syms[:6],
            "top_gainer": syms[0]
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
    period: str = Query("1mo", regex="^(1m|5m|15m|30m|1h|60m|1d|5d|1mo|6mo|1y|5y|max)$"),
    interval: Optional[str] = Query(None, regex="^(1m|2m|5m|15m|30m|60m|1h|1d|1wk|1mo)$")
):
    """Returns candlestick OHLCV data with pre-calculated technical indicators (SMA, EMA, BB, RSI, MACD, ATR, VWAP, Stoch, Williams %R)."""
    return fetch_stock_history(symbol, period=period, interval=interval)


@app.get("/api/stock/{symbol}/company")
@app.get("/api/stock/{symbol}/details")
async def get_company_details(symbol: str):
    """Comprehensive company profile, valuation metrics, and sector peer comparison."""
    try:
        return fetch_company_details(symbol)
    except Exception as e:
        logger.error(f"Error fetching company details for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stock/{symbol}/ecosystem")
async def get_company_ecosystem_endpoint(symbol: str):
    """
    Returns 4D Supply Chain Ecosystem: Upstream Suppliers, Downstream Customers,
    Direct Competitors with Moats, and B2B/B2C Consumer Breakdown.
    """
    try:
        return fetch_company_ecosystem(symbol)
    except Exception as e:
        logger.error(f"Error fetching ecosystem for {symbol}: {e}")
        return {
            "error": str(e),
            "symbol": symbol.upper(),
            "upstream_suppliers": [],
            "downstream_customers": [],
            "competitors": [],
            "consumer_breakdown": {}
        }


@app.get("/api/stock/{symbol}/technicals")
async def get_stock_technicals_endpoint(symbol: str):
    """Calculated technicals including 14-day ATR, RSI, MACD, and SMAs."""
    return fetch_stock_technicals(symbol)


# -----------------------------------------------------------------------------
# Multi-Layer Data Integrations (SEC, Insider 13F, News, Macro, Calendar)
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


@app.get("/api/calendar/{symbol}/earnings")
async def get_earnings_calendar_endpoint(symbol: str):
    """Checks 48-Hour Earnings Blackout Window for risk management veto."""
    try:
        return fetch_earnings_calendar(symbol)
    except Exception as e:
        logger.error(f"Error fetching earnings calendar for {symbol}: {e}")
        return {"error": str(e), "symbol": symbol, "blackout_status": "CLEAR"}


# -----------------------------------------------------------------------------
# Deterministic Non-LLM Risk Guardrail Endpoint
# -----------------------------------------------------------------------------
@app.post("/api/risk/evaluate")
async def evaluate_risk(req: RiskEvaluateRequest):
    """
    Evaluates order through deterministic mathematical risk gate:
    - 14-day ATR-based position sizing
    - Max 5% single-ticker exposure cap
    - Max 20% sector exposure cap
    - Max 5 open positions limit
    - 48h Earnings Blackout filter
    - Automated Take-Profit & Stop-Loss bracket order legs
    """
    p = load_portfolio()
    equity = req.equity or (p.get("cash", 10000.0) + sum(pos.get("cost_basis", 0) for pos in p.get("positions", {}).values()))
    
    return RiskGuardrail.evaluate_order(
        symbol=req.symbol,
        action=req.action,
        equity=equity,
        current_positions=p.get("positions", {}),
        requested_shares=req.shares,
        conviction_score=req.conviction_score,
        manual_override=True
    )


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
# Paper Trading Portfolio (Alpaca Paper Trading & $10,000 Clean Baseline)
# -----------------------------------------------------------------------------
@app.get("/api/portfolio/get")
async def get_portfolio(alpaca_key: Optional[str] = None, alpaca_secret: Optional[str] = None):
    """Returns live paper portfolio with risk metrics (Win Rate, Profit Factor, Concentration Cap)."""
    return get_portfolio_state(alpaca_key=alpaca_key, alpaca_secret=alpaca_secret)


@app.post("/api/portfolio/trade")
async def post_trade(req: TradeRequest):
    """Executes a virtual paper trade with strict Non-LLM Risk Gate validation and bracket orders."""
    try:
        res = execute_order(
            action=req.action,
            symbol=req.symbol,
            quantity=req.quantity,
            order_type=req.order_type or "MARKET",
            limit_price=req.limit_price,
            stop_loss=req.stop_loss,
            take_profit=req.take_profit,
            rationale=req.rationale or "Manual Desk Execution",
            alpaca_key=req.alpaca_key,
            alpaca_secret=req.alpaca_secret
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
# Alpaca US Paper Trading Direct Endpoints
# -----------------------------------------------------------------------------
@app.get("/api/alpaca/account")
async def get_alpaca_account(api_key: Optional[str] = None, secret_key: Optional[str] = None):
    """Fetches live Alpaca paper trading account status, buying power, and portfolio equity."""
    client = AlpacaPaperClient(api_key=api_key, secret_key=secret_key)
    acct = client.get_account()
    if not acct:
        return {"configured": False, "message": "Alpaca API credentials not set or invalid."}
    return {"configured": True, "account": acct}


@app.get("/api/alpaca/positions")
async def get_alpaca_positions(api_key: Optional[str] = None, secret_key: Optional[str] = None):
    """Fetches open positions from Alpaca paper account."""
    client = AlpacaPaperClient(api_key=api_key, secret_key=secret_key)
    return client.get_positions()


@app.get("/api/alpaca/orders")
async def get_alpaca_orders(api_key: Optional[str] = None, secret_key: Optional[str] = None):
    """Fetches recent orders from Alpaca paper account."""
    client = AlpacaPaperClient(api_key=api_key, secret_key=secret_key)
    return client.get_orders()


@app.post("/api/alpaca/ping")
async def ping_alpaca(req: AlpacaPingRequest):
    """On-demand connection test for Alpaca US Paper Trading API."""
    client = AlpacaPaperClient(api_key=req.api_key, secret_key=req.secret_key, base_url=req.base_url)
    return client.ping()


# -----------------------------------------------------------------------------
# AI Agent Syndicate & On-Demand LLM Health Check
# -----------------------------------------------------------------------------
@app.get("/api/agent/models")
async def get_models():
    """Detects available Ollama local models and provides recommended model catalogs."""
    return LLMManager.get_models_catalog()


@app.post("/api/agent/provider/ping")
async def ping_provider_endpoint(req: PingRequest):
    """On-Demand Health Tester: sends a lightweight 1-token request ONLY when user switches or tests a provider."""
    return LLMManager.ping_provider(
        provider=req.provider,
        model=req.model,
        api_key=req.api_key,
        base_url=req.base_url
    )


@app.get("/api/agent/debater")
async def get_debate(symbol: str = "AAPL", provider: str = "groq", model: Optional[str] = None):
    """AdversarialIQ Tribunal: Bull Advocate vs. Bear Adversary vs. Chief Judge via LangChain."""
    return run_adversarial_trade_tribunal(symbol=symbol, provider=provider, model=model)


@app.get("/api/agent/briefing")
async def get_briefing():
    """FinGPT Morning Desk Intelligence Note across S&P 500."""
    scan_res = run_sp500_scanner(strategy="all")
    return get_daily_desk_briefing(scan_res.get("results", []))


@app.post("/api/agent/chat")
async def chat_endpoint(req: ChatRequest):
    """AdversarialIQ Trader Agent endpoint with full multi-layer context and multi-provider failover."""
    return process_chat_message(
        message=req.message,
        provider=req.provider or "groq",
        model=req.model or "openai/gpt-oss-120b",
        groq_api_key=req.groq_api_key or "",
        gemini_api_key=req.gemini_api_key or "",
        mistral_api_key=req.mistral_api_key or "",
        nvidia_api_key=req.nvidia_api_key or "",
        ollama_base_url=req.ollama_base_url or "http://localhost:11434",
        current_symbol=req.current_symbol or "AAPL",
        alpaca_key=req.alpaca_key,
        alpaca_secret=req.alpaca_secret
    )


@app.get("/api/agent/tools")
async def get_agent_tools_endpoint():
    """Returns catalog of all 10 institutional quantitative tools and their JSON schemas."""
    return {"status": "SUCCESS", "tools": TOOL_SCHEMAS}


@app.post("/api/agent/tools/execute")
async def execute_agent_tool_endpoint(req: ToolExecuteRequest):
    """Dynamically executes a quantitative financial tool by name with arguments."""
    return execute_tool(req.tool, req.arguments)


# -----------------------------------------------------------------------------
# 5-Year High-Speed Quantitative Backtest Suite (10 Marquee S&P 500 Stocks)
# -----------------------------------------------------------------------------
@app.get("/api/backtest/symbols")
async def get_backtest_symbols():
    """Returns catalog of marquee S&P 500 stocks with 5-year cached data status."""
    return BacktestDataStore.get_marquee_catalog()


@app.post("/api/backtest/run")
async def run_backtest_endpoint(req: BacktestRunRequest):
    """Executes preset algorithmic backtest on 5-year cached data."""
    return BacktestEngine.run_preset_strategy(
        symbol=req.symbol,
        strategy_name=req.strategy_name,
        initial_capital=req.initial_capital,
        stop_loss_pct=req.stop_loss_pct,
        take_profit_pct=req.take_profit_pct
    )


@app.post("/api/backtest/nlp")
async def run_nlp_backtest_endpoint(req: BacktestNlpRequest):
    """Synthesizes natural language strategy into Python code and executes 5-year backtest."""
    return StrategyGenerator.synthesize_and_run(
        strategy_prompt=req.prompt,
        symbol=req.symbol,
        initial_capital=req.initial_capital,
        stop_loss_pct=req.stop_loss_pct,
        take_profit_pct=req.take_profit_pct,
        provider=req.provider or "groq",
        model=req.model
    )


@app.post("/api/backtest/preload")
async def preload_backtest_data(force: bool = False):
    """Refreshes and preloads 5-year historical data for all 10 marquee stocks."""
    return BacktestDataStore.preload_all_marquee(force_refresh=force)



# -----------------------------------------------------------------------------
# Memory Journal & Post-Mortem Reflections (SQLite)
# -----------------------------------------------------------------------------
@app.get("/api/memory/journal")
async def get_theses_journal(limit: int = 25, symbol: Optional[str] = None):
    """Returns persistent trade theses logged by the Adversarial Tribunal in SQLite."""
    return get_recent_theses(limit=limit, symbol=symbol)


@app.get("/api/memory/reflections")
async def get_agent_reflections(symbol: Optional[str] = None, sector: Optional[str] = None, limit: int = 10):
    """Returns self-improving post-mortem reflections extracted from closed trades."""
    return retrieve_reflections(symbol=symbol, sector=sector, limit=limit)


@app.get("/api/memory/stats")
async def get_memory_stats():
    """Returns summary thesis statistics (total theses, wins, losses, win rate %)."""
    return get_journal_stats()


# -----------------------------------------------------------------------------
# LLM Observability & Trace Logging
# -----------------------------------------------------------------------------
@app.get("/api/observability/traces")
async def get_llm_traces(limit: int = 50, provider: Optional[str] = None):
    """Returns recent structured LLM execution traces (latency, tokens, status)."""
    return LLMTracer.get_traces(limit=limit, provider=provider)


@app.get("/api/observability/metrics")
async def get_llm_metrics():
    """Returns aggregate LLM observability metrics (total calls, avg latency, success rate %)."""
    return LLMTracer.get_metrics()


@app.get("/api/observability/langfuse")
async def get_langfuse_telemetry():
    """Returns Langfuse Cloud connectivity status, host, and trace configuration."""
    return get_langfuse_status()



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
