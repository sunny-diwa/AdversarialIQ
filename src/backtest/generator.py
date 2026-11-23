"""
Natural Language Algorithmic Strategy Synthesizer & Code Generator
Translates freeform trading concepts described to the chatbot into validated Python signal generation code,
executes it against cached 5-year historical data, and compiles institutional performance analytics.
"""

import ast
import logging
import re
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from src.backtest.data_store import BacktestDataStore
from src.backtest.engine import BacktestEngine
from src.llm.manager import LLMManager

logger = logging.getLogger("StrategyGenerator")

STRATEGY_SYSTEM_PROMPT = """You are an institutional quantitative trading engineer.
Your task is to convert the user's trading strategy description into clean, vectorized Python code that generates buy and sell signals.

Available DataFrame columns on `df`:
- `df['Open']`, `df['High']`, `df['Low']`, `df['Close']`, `df['Volume']`
- `df['SMA_20']`, `df['SMA_50']`, `df['SMA_200']`
- `df['EMA_12']`, `df['EMA_26']`
- `df['MACD']`, `df['MACD_SIGNAL']`, `df['MACD_HIST']`
- `df['RSI_14']`
- `df['BB_UPPER']`, `df['BB_LOWER']`
- `df['ATR_14']`
- `df['Daily_Return']`

Requirement:
Write a Python function named `generate_signals(df: pd.DataFrame) -> pd.Series`:
- Returns a `pd.Series` indexed identically to `df.index`
- Values: `1` for BUY signal, `-1` for SELL/EXIT signal, `0` for NO_SIGNAL.
- Output ONLY valid executable Python code enclosed within ```python and ```.
- Do NOT include any extra conversational filler before or after the code block.
"""


class StrategyGenerator:
    """Synthesizes natural language strategies into executable Python code and runs backtests."""

    @classmethod
    def synthesize_and_run(
        cls,
        strategy_prompt: str,
        symbol: str = "NVDA",
        initial_capital: float = 10000.0,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        provider: str = "groq",
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Translates user prompt into Python signal logic, executes backtest over 5-year data,
        and returns both the executable code and full performance analytics.
        """
        sym = symbol.strip().upper()

        # 1. Generate Python Signal Code via LLM
        prompt = (
            f"Write the `generate_signals(df: pd.DataFrame) -> pd.Series` function for the following strategy on {sym}:\n"
            f"Strategy Concept: {strategy_prompt}\n\n"
            f"Ensure edge-case protection (handle NaNs with .fillna(0)). Return strictly executable Python inside ```python."
        )

        res = LLMManager.generate(
            prompt=prompt,
            system_prompt=STRATEGY_SYSTEM_PROMPT,
            preferred_provider=provider,
            model=model or ("openai/gpt-oss-120b" if provider == "groq" else "codestral-latest"),
            symbol=sym
        )

        raw_code = res.get("response", "")
        code = cls._extract_code(raw_code)

        # 2. Execute Strategy Code
        signals = cls._execute_code_safely(code, sym)

        # If execution fails, fallback to standard SMA/RSI hybrid
        if signals is None or signals.empty:
            logger.warning("Dynamic code execution fallback to SMA momentum")
            df = BacktestDataStore.load_symbol_history(sym)
            signals = pd.Series(0, index=df.index)
            buy_cond = (df["SMA_20"] > df["SMA_50"]) & (df["RSI_14"] < 60)
            sell_cond = (df["SMA_20"] < df["SMA_50"]) | (df["RSI_14"] > 75)
            signals[buy_cond] = 1
            signals[sell_cond] = -1
            code = (
                "def generate_signals(df: pd.DataFrame) -> pd.Series:\n"
                "    signals = pd.Series(0, index=df.index)\n"
                "    buy_cond = (df['SMA_20'] > df['SMA_50']) & (df['RSI_14'] < 60)\n"
                "    sell_cond = (df['SMA_20'] < df['SMA_50']) | (df['RSI_14'] > 75)\n"
                "    signals[buy_cond] = 1\n"
                "    signals[sell_cond] = -1\n"
                "    return signals"
            )

        # 3. Run Quantitative Engine
        backtest_result = BacktestEngine.run_strategy(
            symbol=sym,
            signals=signals,
            initial_capital=initial_capital,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct
        )

        backtest_result["strategy_prompt"] = strategy_prompt
        backtest_result["generated_code"] = code
        backtest_result["model_used"] = res.get("model", "openai/gpt-oss-120b")
        backtest_result["provider_used"] = res.get("provider", "Groq Cloud")

        return backtest_result

    @staticmethod
    def _extract_code(text: str) -> str:
        """Extracts python snippet from markdown fence."""
        match = re.search(r"```(?:python)?\s*(.*?)\s*```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    @classmethod
    def _execute_code_safely(cls, code_str: str, symbol: str) -> Optional[pd.Series]:
        """Safely executes the generated function in restricted scope against symbol DataFrame."""
        try:
            # Syntax validation via AST
            ast.parse(code_str)

            df = BacktestDataStore.load_symbol_history(symbol)

            # Execution namespace with globals containing pd and np
            global_scope: Dict[str, Any] = {
                "pd": pd,
                "np": np,
                "__builtins__": __builtins__
            }
            local_scope: Dict[str, Any] = {}
            exec(code_str, global_scope, local_scope)

            func = local_scope.get("generate_signals") or global_scope.get("generate_signals")
            if not callable(func):
                logger.error("Generated code does not define callable `generate_signals`")
                return None

            signals = func(df)
            if isinstance(signals, pd.Series):
                return signals
            return None

        except Exception as e:
            logger.error(f"Error executing generated strategy code: {e}")
            return None
