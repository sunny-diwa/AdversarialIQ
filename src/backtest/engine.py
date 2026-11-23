"""
AdversarialIQ Vectorized & Event-Driven Quantitative Backtest Engine
Computes institutional performance metrics (Sharpe, Sortino, Max Drawdown, Alpha, Win Rate, Profit Factor)
and generates time-series equity curves against Buy & Hold benchmarks over 5-year data.
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from src.backtest.data_store import BacktestDataStore

logger = logging.getLogger("BacktestEngine")


class BacktestEngine:
    """Institutional backtesting engine with bracket simulation and portfolio analytics."""

    @classmethod
    def run_strategy(
        cls,
        symbol: str,
        signals: pd.Series,
        initial_capital: float = 10000.0,
        stop_loss_pct: Optional[float] = None,
        take_profit_pct: Optional[float] = None,
        slippage_bps: float = 5.0,  # 5 bps (0.05%) slippage/fee per trade
        period_years: float = 5.0
    ) -> Dict[str, Any]:
        """
        Executes a strategy against cached 5-year historical data.
        signals: pd.Series indexed by datetime with values 1 (BUY), -1 (SELL/EXIT), 0 (HOLD/NO_SIGNAL)
        """
        df = BacktestDataStore.load_symbol_history(symbol)
        if df.empty:
            raise ValueError(f"No historical data available for {symbol}")

        # Align signals with DataFrame index
        aligned_signals = signals.reindex(df.index).fillna(0)

        close = df["Close"].values
        dates = [str(d)[:10] for d in df.index]
        n_bars = len(df)

        capital = float(initial_capital)
        shares = 0
        entry_price = 0.0
        entry_idx = 0

        equity_curve = []
        trades = []

        slippage_rate = slippage_bps / 10000.0

        for i in range(n_bars):
            cur_price = float(close[i])
            sig = int(aligned_signals.iloc[i])
            cur_date = dates[i]

            # 1. Check existing position for Stop-Loss / Take-Profit exit
            if shares > 0:
                pnl_pct = (cur_price - entry_price) / entry_price
                exit_reason = None

                if stop_loss_pct and pnl_pct <= -abs(stop_loss_pct):
                    exit_reason = f"STOP LOSS (-{abs(stop_loss_pct)*100:.1f}%)"
                elif take_profit_pct and pnl_pct >= abs(take_profit_pct):
                    exit_reason = f"TAKE PROFIT (+{abs(take_profit_pct)*100:.1f}%)"
                elif sig == -1:
                    exit_reason = "SIGNAL EXIT (SELL)"

                if exit_reason:
                    fill_price = cur_price * (1 - slippage_rate)
                    proceeds = shares * fill_price
                    realized_pnl = proceeds - (shares * entry_price)
                    capital += proceeds

                    trades.append({
                        "entry_date": dates[entry_idx],
                        "exit_date": cur_date,
                        "entry_price": round(entry_price, 2),
                        "exit_price": round(fill_price, 2),
                        "shares": shares,
                        "pnl": round(realized_pnl, 2),
                        "pnl_pct": round(((fill_price - entry_price) / entry_price) * 100, 2),
                        "hold_days": i - entry_idx,
                        "reason": exit_reason
                    })
                    shares = 0
                    entry_price = 0.0

            # 2. Check for new BUY entry signal
            elif sig == 1 and capital > 100:
                fill_price = cur_price * (1 + slippage_rate)
                # Allocate 95% of liquid capital
                alloc_capital = capital * 0.95
                shares_to_buy = int(alloc_capital // fill_price)

                if shares_to_buy > 0:
                    cost = shares_to_buy * fill_price
                    capital -= cost
                    shares = shares_to_buy
                    entry_price = fill_price
                    entry_idx = i

            # 3. Mark to Market Equity
            portfolio_val = capital + (shares * cur_price)
            equity_curve.append(portfolio_val)

        # Close open position at end of backtest period for terminal accounting
        if shares > 0:
            final_price = float(close[-1])
            realized_pnl = (shares * final_price) - (shares * entry_price)
            capital += shares * final_price
            trades.append({
                "entry_date": dates[entry_idx],
                "exit_date": dates[-1],
                "entry_price": round(entry_price, 2),
                "exit_price": round(final_price, 2),
                "shares": shares,
                "pnl": round(realized_pnl, 2),
                "pnl_pct": round(((final_price - entry_price) / entry_price) * 100, 2),
                "hold_days": n_bars - 1 - entry_idx,
                "reason": "END OF BACKTEST HORIZON"
            })
            shares = 0

        final_equity = capital
        equity_series = pd.Series(equity_curve, index=df.index)

        # 4. Compute Metrics
        total_return_pct = ((final_equity - initial_capital) / initial_capital) * 100
        benchmark_initial = float(close[0])
        benchmark_final = float(close[-1])
        benchmark_return_pct = ((benchmark_final - benchmark_initial) / benchmark_initial) * 100
        alpha_pct = total_return_pct - benchmark_return_pct

        # Daily returns of strategy
        strat_daily_ret = equity_series.pct_change().dropna()
        ann_volatility_pct = float(strat_daily_ret.std() * np.sqrt(252) * 100) if len(strat_daily_ret) > 0 else 0.0

        # Sharpe Ratio (assumes 4.0% annualized risk-free rate)
        rf_daily = 0.04 / 252
        excess_ret = strat_daily_ret - rf_daily
        sharpe_ratio = round(float(np.sqrt(252) * (excess_ret.mean() / (strat_daily_ret.std() + 1e-9))), 2)

        # Sortino Ratio (downside deviation)
        downside_ret = strat_daily_ret[strat_daily_ret < 0]
        sortino_ratio = round(float(np.sqrt(252) * (excess_ret.mean() / (downside_ret.std() + 1e-9))), 2) if len(downside_ret) > 0 else 0.0

        # Max Drawdown
        running_max = equity_series.cummax()
        drawdowns = (equity_series - running_max) / running_max
        max_drawdown_pct = round(float(drawdowns.min() * 100), 2)

        # Trade Statistics
        total_trades = len(trades)
        wins = [t for t in trades if t["pnl"] > 0]
        losses = [t for t in trades if t["pnl"] <= 0]
        win_rate_pct = round((len(wins) / total_trades * 100), 1) if total_trades > 0 else 0.0

        gross_profit = sum(t["pnl"] for t in wins)
        gross_loss = abs(sum(t["pnl"] for t in losses))
        profit_factor = round(gross_profit / (gross_loss + 1e-9), 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 1.0)
        avg_trade_pnl_pct = round(float(np.mean([t["pnl_pct"] for t in trades])), 2) if total_trades > 0 else 0.0
        avg_hold_days = round(float(np.mean([t["hold_days"] for t in trades])), 1) if total_trades > 0 else 0.0

        # Downsample equity curve to ~120 points for fast, smooth web rendering
        step = max(1, n_bars // 120)
        sampled_dates = dates[::step]
        sampled_equity = [round(e, 2) for e in equity_curve[::step]]
        sampled_benchmark = [round(initial_capital * (close[k] / benchmark_initial), 2) for k in range(0, n_bars, step)]

        # Ensure last bar is included
        if dates[-1] not in sampled_dates:
            sampled_dates.append(dates[-1])
            sampled_equity.append(round(equity_curve[-1], 2))
            sampled_benchmark.append(round(initial_capital * (benchmark_final / benchmark_initial), 2))

        return {
            "symbol": symbol,
            "period": f"{dates[0]} to {dates[-1]} (5 Years)",
            "initial_capital": initial_capital,
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(total_return_pct, 2),
            "benchmark_return_pct": round(benchmark_return_pct, 2),
            "alpha_pct": round(alpha_pct, 2),
            "annualized_volatility_pct": round(ann_volatility_pct, 2),
            "sharpe_ratio": sharpe_ratio,
            "sortino_ratio": sortino_ratio,
            "max_drawdown_pct": max_drawdown_pct,
            "total_trades": total_trades,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate_pct": win_rate_pct,
            "profit_factor": profit_factor,
            "avg_trade_pnl_pct": avg_trade_pnl_pct,
            "avg_hold_days": avg_hold_days,
            "equity_chart": {
                "labels": sampled_dates,
                "strategy_equity": sampled_equity,
                "benchmark_equity": sampled_benchmark
            },
            "recent_trades": trades[-20:]  # Last 20 trades
        }

    @classmethod
    def run_preset_strategy(
        cls,
        symbol: str,
        strategy_name: str,
        initial_capital: float = 10000.0,
        stop_loss_pct: Optional[float] = 0.07,
        take_profit_pct: Optional[float] = 0.20
    ) -> Dict[str, Any]:
        """Runs one of the standardized institutional algorithmic presets."""
        df = BacktestDataStore.load_symbol_history(symbol)
        signals = pd.Series(0, index=df.index)

        strat = strategy_name.lower().strip()

        if strat in ("sma_cross", "golden_cross"):
            # Buy when SMA 20 crosses above SMA 50, exit when crosses below
            buy_cond = (df["SMA_20"] > df["SMA_50"]) & (df["SMA_20"].shift(1) <= df["SMA_50"].shift(1))
            sell_cond = (df["SMA_20"] < df["SMA_50"]) & (df["SMA_20"].shift(1) >= df["SMA_50"].shift(1))
            signals[buy_cond] = 1
            signals[sell_cond] = -1

        elif strat in ("rsi_reversal", "rsi_oversold"):
            # Buy when RSI < 35, exit when RSI > 65
            buy_cond = (df["RSI_14"] < 35) & (df["RSI_14"].shift(1) >= 35)
            sell_cond = (df["RSI_14"] > 65) & (df["RSI_14"].shift(1) <= 65)
            signals[buy_cond] = 1
            signals[sell_cond] = -1

        elif strat in ("macd_momentum", "macd_trend"):
            # Buy when MACD crosses above Signal, exit when crosses below
            buy_cond = (df["MACD"] > df["MACD_SIGNAL"]) & (df["MACD"].shift(1) <= df["MACD_SIGNAL"].shift(1))
            sell_cond = (df["MACD"] < df["MACD_SIGNAL"]) & (df["MACD"].shift(1) >= df["MACD_SIGNAL"].shift(1))
            signals[buy_cond] = 1
            signals[sell_cond] = -1

        elif strat in ("bollinger_bands", "bb_mean_reversion"):
            # Buy when Close touches lower band, exit when touches upper band
            buy_cond = (df["Close"] <= df["BB_LOWER"])
            sell_cond = (df["Close"] >= df["BB_UPPER"])
            signals[buy_cond] = 1
            signals[sell_cond] = -1

        elif strat in ("atr_breakout", "breakout"):
            # 20-day high breakout with ATR expansion
            rolling_20_high = df["High"].rolling(20).max()
            buy_cond = (df["Close"] >= rolling_20_high.shift(1))
            sell_cond = (df["Close"] < df["SMA_50"])
            signals[buy_cond] = 1
            signals[sell_cond] = -1

        else:
            # Default to SMA Cross
            buy_cond = (df["SMA_20"] > df["SMA_50"]) & (df["SMA_20"].shift(1) <= df["SMA_50"].shift(1))
            sell_cond = (df["SMA_20"] < df["SMA_50"]) & (df["SMA_20"].shift(1) >= df["SMA_50"].shift(1))
            signals[buy_cond] = 1
            signals[sell_cond] = -1

        result = cls.run_strategy(
            symbol=symbol,
            signals=signals,
            initial_capital=initial_capital,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct
        )
        result["strategy_name"] = strategy_name
        return result
