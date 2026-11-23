"""
AdversarialIQ - S&P 500 AI Trading Syndicate & Bloomberg-Grade Trading Terminal
Modular institutional architecture.
"""

from src.core import (
    BASE_DIR,
    DATA_DIR,
    STATIC_DIR,
    SP500_FILE,
    PORTFOLIO_FILE,
    DB_FILE,
    HOST,
    PORT,
    ENV,
    IS_DEV,
    SEC_EDGAR_IDENTITY,
    ALPACA_API_KEY,
    ALPACA_SECRET_KEY,
    ALPACA_BASE_URL,
    GROQ_API_KEY,
    GEMINI_API_KEY,
    MISTRAL_API_KEY,
    NVIDIA_API_KEY,
    OLLAMA_BASE_URL,
    FRED_API_KEY,
    FINNHUB_API_KEY,
    SP500_STOCKS,
    SP500_MAP,
    SCANNER_PRESET_STOCKS,
    CACHE,
    get_cached,
    set_cached,
)

from src.data import (
    compute_indicators,
    fetch_benchmarks,
    fetch_stock_quote,
    fetch_stock_history,
    fetch_company_details,
    fetch_stock_technicals,
    fetch_sec_filings,
    fetch_insider_and_13f_activity,
    fetch_breaking_news,
    calculate_sentiment,
    tag_catalysts,
    fetch_macro_regime,
    fetch_earnings_calendar,
)

from src.risk import RiskGuardrail

from src.memory import (
    init_journal_db,
    log_trade_thesis,
    record_trade_close,
    get_recent_theses,
    get_journal_stats,
    save_reflection,
    retrieve_reflections,
    format_lessons_for_prompt,
)

from src.execution import (
    AlpacaPaperClient,
    load_portfolio,
    save_portfolio,
    reset_portfolio,
    get_portfolio_state,
    execute_order,
)

from src.llm import LLMManager, LLMTracer

from src.agents import (
    BullProsecutionCase,
    BearDefenseCase,
    ChiefJudgeRuling,
    RiskGateVerdict,
    TribunalState,
    AdversarialStateMachine,
    run_adversarial_trade_tribunal,
    get_daily_desk_briefing,
    PostMortemAgent,
    process_chat_message,
)

from src.scanner import scan_single_stock, run_sp500_scanner, get_market_movers

__all__ = [
    # Core
    "BASE_DIR", "DATA_DIR", "STATIC_DIR", "SP500_FILE", "PORTFOLIO_FILE", "DB_FILE",
    "HOST", "PORT", "ENV", "IS_DEV", "SEC_EDGAR_IDENTITY", "ALPACA_API_KEY",
    "ALPACA_SECRET_KEY", "ALPACA_BASE_URL", "GROQ_API_KEY", "GEMINI_API_KEY",
    "MISTRAL_API_KEY", "NVIDIA_API_KEY", "OLLAMA_BASE_URL", "FRED_API_KEY",
    "FINNHUB_API_KEY", "SP500_STOCKS", "SP500_MAP", "SCANNER_PRESET_STOCKS",
    "CACHE", "get_cached", "set_cached",
    # Data
    "compute_indicators", "fetch_benchmarks", "fetch_stock_quote", "fetch_stock_history",
    "fetch_company_details", "fetch_stock_technicals", "fetch_sec_filings",
    "fetch_insider_and_13f_activity", "fetch_breaking_news", "calculate_sentiment",
    "tag_catalysts", "fetch_macro_regime", "fetch_earnings_calendar",
    # Risk
    "RiskGuardrail",
    # Memory
    "init_journal_db", "log_trade_thesis", "record_trade_close", "get_recent_theses",
    "get_journal_stats", "save_reflection", "retrieve_reflections", "format_lessons_for_prompt",
    # Execution
    "AlpacaPaperClient", "load_portfolio", "save_portfolio", "reset_portfolio",
    "get_portfolio_state", "execute_order",
    # LLM
    "LLMManager", "LLMTracer",
    # Agents
    "BullProsecutionCase", "BearDefenseCase", "ChiefJudgeRuling", "RiskGateVerdict",
    "TribunalState", "AdversarialStateMachine", "run_adversarial_trade_tribunal",
    "get_daily_desk_briefing", "PostMortemAgent", "process_chat_message",
    # Scanner
    "scan_single_stock", "run_sp500_scanner", "get_market_movers",
]
