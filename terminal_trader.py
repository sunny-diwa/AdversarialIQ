#!/usr/bin/env python3
"""
S&P 500 Terminal Trader - Full-Fledged CLI Terminal Interface
ASCII Candlesticks, Multi-Indicator Analytics, Scanner & Agent REPL
"""

import argparse
import json
import os
import sys
import warnings
from datetime import datetime
from pathlib import Path

# Suppress pandas & yfinance deprecation warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import requests
import yfinance as yf
# Filter yfinance internal deprecation warnings
warnings.filterwarnings("ignore")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

console = Console()

SERVER_URL = os.environ.get("TERMINAL_SERVER_URL", "http://localhost:8080").rstrip("/")

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
SP500_FILE = DATA_DIR / "sp500.json"
PORTFOLIO_FILE = DATA_DIR / "portfolio.json"

SP500_MAP = {}
if SP500_FILE.exists():
    try:
        with open(SP500_FILE, "r", encoding="utf-8") as f:
            for s in json.load(f):
                SP500_MAP[s["symbol"]] = s
    except Exception:
        pass


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    close = df["Close"]
    high = df["High"]
    low = df["Low"]

    df["SMA20"] = close.rolling(20).mean()
    df["SMA50"] = close.rolling(50).mean()
    df["SMA200"] = close.rolling(200).mean() if len(df) >= 200 else close.rolling(len(df)).mean()

    # Bollinger Bands
    std20 = close.rolling(20).std()
    df["BB_Upper"] = df["SMA20"] + 2 * std20
    df["BB_Lower"] = df["SMA20"] - 2 * std20

    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    df["RSI"] = (100 - (100 / (1 + rs))).fillna(50.0)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    df["MACD"] = ema12 - ema26
    df["MACD_Signal"] = df["MACD"].ewm(span=9, adjust=False).mean()
    df["MACD_Hist"] = df["MACD"] - df["MACD_Signal"]

    return df


def render_ascii_candles(df: pd.DataFrame, height: int = 14, width: int = 42) -> str:
    """Renders a high-density ASCII / ANSI candlestick chart."""
    if df.empty:
        return "No price history available."

    tail = df.tail(width).copy()
    min_val = tail["Low"].min()
    max_val = tail["High"].max()
    val_range = max_val - min_val if max_val > min_val else 1.0

    lines = []
    # Render chart grid rows
    for r in range(height, -1, -1):
        price_level = min_val + (r / height) * val_range
        row_str = f"{price_level:7.2f} │ "
        for _, candle in tail.iterrows():
            o = candle["Open"]
            c = candle["Close"]
            h = candle["High"]
            l = candle["Low"]

            candle_min = min(o, c)
            candle_max = max(o, c)
            is_green = c >= o

            char = " "
            if l <= price_level <= h:
                if candle_min <= price_level <= candle_max:
                    char = "█" if is_green else "░"
                else:
                    char = "│"

            color = "green" if is_green else "red"
            row_str += f"[{color}]{char}[/{color}]"

        lines.append(row_str)

    lines.append("        └" + "─" * width)
    # Date markers
    start_date = tail.index[0].strftime("%b %d")
    end_date = tail.index[-1].strftime("%b %d")
    lines.append(f"         {start_date}" + " " * (width - len(start_date) - len(end_date) - 1) + f"{end_date}")

    return "\n".join(lines)


def display_stock_terminal(symbol: str):
    sym = symbol.strip().upper()
    console.print(f"\n[bold yellow]>>> FETCHING BLOOMBERG TERMINAL DATA FOR S&P 500: {sym} <<<[/bold yellow]\n")

    try:
        t = yf.Ticker(sym)
        hist = t.history(period="6mo", interval="1d")
        if hist.empty:
            console.print(f"[red]No data found for ticker {sym}. Ensure it is an S&P 500 symbol.[/red]")
            return

        fast = t.fast_info
        price = fast.last_price or hist["Close"].iloc[-1]
        prev = fast.previous_close or price
        chg = price - prev
        pct = (chg / prev * 100) if prev else 0.0

        hist = compute_indicators(hist)
        latest = hist.iloc[-1]

        rsi = float(latest["RSI"])
        macd = float(latest["MACD"])
        sig = float(latest["MACD_Signal"])
        sma20 = float(latest["SMA20"])
        sma50 = float(latest["SMA50"])
        bb_up = float(latest["BB_Upper"])
        bb_low = float(latest["BB_Lower"])

        company_meta = SP500_MAP.get(sym, {})
        sec_name = company_meta.get("sector", "S&P 500")

        # 1. Header Banner
        chg_color = "green" if chg >= 0 else "red"
        sign = "+" if chg >= 0 else ""
        header_text = Text()
        header_text.append(f"{sym} ", style="bold cyan")
        header_text.append(f"({company_meta.get('name', sym)}) - {sec_name}\n", style="bold white")
        header_text.append(f"LAST: ${price:.2f}  ", style="bold white")
        header_text.append(f"{sign}{chg:.2f} ({sign}{pct:.2f}%)  ", style=f"bold {chg_color}")
        header_text.append(f"DAY HIGH: ${fast.day_high or price:.2f}  DAY LOW: ${fast.day_low or price:.2f}  52W: ${fast.year_low or 0:.2f}-${fast.year_high or 0:.2f}", style="dim")

        console.print(Panel(header_text, title="[bold yellow]BLOOMBERG EQUITY TERMINAL[/bold yellow]", border_style="yellow"))

        # 2. Candlestick Chart
        chart_str = render_ascii_candles(hist, height=13, width=48)
        console.print(Panel(chart_str, title=f"[bold green]CANDLESTICK CHART & PRICE BANDS: {sym}[/bold green]", border_style="green"))

        # 3. Technical Indicator Table
        ind_table = Table(title="📊 TECHNICAL INDICATOR SUITE", header_style="bold magenta", border_style="dim")
        ind_table.add_column("Indicator", style="cyan")
        ind_table.add_column("Current Reading", justify="right")
        ind_table.add_column("Benchmark / Bands", justify="right")
        ind_table.add_column("Quant Signal", justify="center")

        rsi_signal = "[green]OVERSOLD (<35)[/green]" if rsi <= 35 else ("[red]OVERBOUGHT (>65)[/red]" if rsi >= 65 else "[dim]NEUTRAL[/dim]")
        ind_table.add_row("RSI (14)", f"{rsi:.1f}", "30.0 / 70.0", rsi_signal)

        macd_signal = "[green]BULLISH CROSS[/green]" if macd > sig else "[red]BEARISH TREND[/red]"
        ind_table.add_row("MACD (12,26,9)", f"{macd:.2f}", f"Signal: {sig:.2f}", macd_signal)

        ind_table.add_row("20 SMA", f"${sma20:.2f}", f"Price: ${price:.2f}", "[green]ABOVE[/green]" if price >= sma20 else "[red]BELOW[/red]")
        ind_table.add_row("50 SMA", f"${sma50:.2f}", f"Price: ${price:.2f}", "[green]ABOVE[/green]" if price >= sma50 else "[red]BELOW[/red]")
        ind_table.add_row("Bollinger Upper", f"${bb_up:.2f}", "+2.0 StdDev", "[red]RESISTANCE[/red]")
        ind_table.add_row("Bollinger Lower", f"${bb_low:.2f}", "-2.0 StdDev", "[green]SUPPORT[/green]")

        console.print(ind_table)

        # 4. Actionable Trade Setup
        recent_high = float(hist["High"].tail(20).max())
        recent_low = float(hist["Low"].tail(20).min())
        setup_panel = Panel(
            f"[bold]QUANT TRADE PLAN FOR {sym}:[/bold]\n"
            f"• [cyan]Recommended Entry:[/cyan] ${price:.2f}\n"
            f"• [red]Stop-Loss Level:[/red] ${recent_low * 0.985:.2f} (Below 20-Day Low)\n"
            f"• [green]Target Price:[/green] ${recent_high * 1.025:.2f} (Breakout Target)\n"
            f"• [yellow]Paper Trade Command:[/yellow] Type 'BUY {sym} <qty>' or 'SELL {sym} <qty>'",
            title="[bold cyan]TRADE EXECUTION SETUP[/bold cyan]",
            border_style="cyan"
        )
        console.print(setup_panel)

    except Exception as e:
        console.print(f"[red]Error analyzing {sym}: {e}[/red]")


def run_scanner_cli():
    console.print("\n[bold cyan]>>> RUNNING S&P 500 MULTI-INDICATOR SCANNER <<<[/bold cyan]\n")
    try:
        res = requests.get(f"{SERVER_URL}/api/scanner/run?strategy=all", timeout=15)
        if res.status_code == 200:
            data = res.json()
            table = Table(title=f"S&P 500 ACTIVE TECHNICAL SETUPS ({data.get('timestamp')})", header_style="bold yellow", border_style="dim")
            table.add_column("Symbol", style="bold cyan")
            table.add_column("Company", style="white")
            table.add_column("Sector", style="dim")
            table.add_column("Price", justify="right")
            table.add_column("Day Chg %", justify="right")
            table.add_column("RSI", justify="right")
            table.add_column("MACD", justify="right")
            table.add_column("Active Signals", style="yellow")

            for s in data.get("results", []):
                color = "green" if s["pct_change"] >= 0 else "red"
                sign = "+" if s["pct_change"] >= 0 else ""
                table.add_row(
                    s["symbol"],
                    s["name"][:18],
                    s["sector"][:14],
                    f"${s['price']:.2f}",
                    f"[{color}]{sign}{s['pct_change']:.2f}%[/{color}]",
                    f"{s['rsi']:.1f}",
                    f"{s['macd']:.2f}",
                    ", ".join(s["signals"][:2])
                )
            console.print(table)
        else:
            console.print(f"[red]Scanner server error: {res.text}[/red]")
    except Exception as e:
        console.print(f"[red]Cannot connect to server at {SERVER_URL}: {e}\nPlease start server first with: python server.py[/red]")


def display_portfolio_cli():
    console.print("\n[bold green]>>> S&P 500 PAPER TRADING PORTFOLIO LEDGER <<<[/bold green]\n")
    try:
        res = requests.get(f"{SERVER_URL}/api/portfolio/get", timeout=5)
        if res.status_code == 200:
            p = res.json()
            summary = Panel(
                f"[bold white]TOTAL PORTFOLIO EQUITY:[/bold white] [bold cyan]${p['total_equity']:,.2f}[/bold cyan]  |  "
                f"[bold white]CASH BALANCE:[/bold white] [green]${p['cash']:,.2f}[/green]  |  "
                f"[bold white]HOLDINGS:[/bold white] ${p['holdings_value']:,.2f}  |  "
                f"[bold white]TOTAL PnL:[/bold white] [{ 'green' if p['total_pnl'] >= 0 else 'red' }]${p['total_pnl']:,.2f} ({p['total_pnl_pct']:+.2f}%)[/{ 'green' if p['total_pnl'] >= 0 else 'red' }]\n"
                f"[dim]Risk Analytics: Win Rate: {p.get('win_rate', 0.0)}%  |  Profit Factor: {p.get('profit_factor', 1.0)}x  |  Max Concentration: {p.get('concentration_risk', 0.0)}% (Cap: 25%)  |  Cash: {p.get('cash_ratio', 100)}%[/dim]",
                title="[bold yellow]PORTFOLIO OVERVIEW ($10,000 BASELINE)[/bold yellow]",
                border_style="yellow"
            )
            console.print(summary)

            pos_table = Table(title="CURRENT HOLDINGS", header_style="bold cyan", border_style="dim")
            pos_table.add_column("Symbol", style="bold cyan")
            pos_table.add_column("Qty", justify="right")
            pos_table.add_column("Avg Price", justify="right")
            pos_table.add_column("Current Price", justify="right")
            pos_table.add_column("Cost Basis", justify="right")
            pos_table.add_column("Current Value", justify="right")
            pos_table.add_column("Unrealized PnL", justify="right")

            for pos in p.get("positions", []):
                pnl_color = "green" if pos["unrealized_pnl"] >= 0 else "red"
                pos_table.add_row(
                    pos["symbol"],
                    str(pos["quantity"]),
                    f"${pos['avg_price']:.2f}",
                    f"${pos['current_price']:.2f}",
                    f"${pos['cost_basis']:,.2f}",
                    f"${pos['current_value']:,.2f}",
                    f"[{pnl_color}]${pos['unrealized_pnl']:+,.2f} ({pos['unrealized_pct']:+.2f}%)[/{pnl_color}]"
                )
            console.print(pos_table)
    except Exception as e:
        console.print(f"[red]Error fetching portfolio: {e}[/red]")


def interactive_chat_repl():
    console.print("\n[bold yellow]===========================================================[/bold yellow]")
    console.print("[bold yellow]   ANTIGRAVITY S&P 500 AI TRADER AGENT (CLI CONSOLE)       [/bold yellow]")
    console.print("[dim]Ask for technical analysis, S&P 500 screening, or paper trade execution.[/dim]")
    console.print("[dim]Examples: 'Analyze NVDA setup', 'Buy 20 AAPL', 'Show my portfolio'[/dim]")
    console.print("[bold yellow]===========================================================[/bold yellow]\n")

    current_sym = "AAPL"
    while True:
        try:
            prompt = console.input(f"[bold cyan]TRADER [{current_sym}] > [/bold cyan]").strip()
            if not prompt:
                continue
            if prompt.lower() in ["exit", "quit", "q"]:
                break
            if prompt.upper() in SP500_MAP:
                current_sym = prompt.upper()
                display_stock_terminal(current_sym)
                continue

            # Query API
            try:
                res = requests.post(f"{SERVER_URL}/api/agent/chat", json={
                    "message": prompt,
                    "provider": "groq",
                    "current_symbol": current_sym
                }, timeout=20)
                if res.status_code == 200:
                    data = res.json()
                    console.print(Panel(data.get("response", ""), title=f"[bold green]AGENT RESPONSE ({data.get('provider', 'Quant')})[/bold green]", border_style="green"))
                else:
                    console.print(f"[red]Agent error: {res.text}[/red]")
            except Exception as e:
                console.print(f"[red]Connection error: {e}. Is server running at {SERVER_URL}?[/red]")

        except (KeyboardInterrupt, EOFError):
            console.print("\n[yellow]Exiting trader console.[/yellow]")
            break


def main():
    parser = argparse.ArgumentParser(description="S&P 500 Full-Fledged Terminal Trader")
    parser.add_argument("symbol", nargs="?", default=None, help="S&P 500 Ticker symbol (e.g. AAPL, NVDA, TSLA)")
    parser.add_argument("--scan", action="store_true", help="Run live S&P 500 multi-indicator scanner")
    parser.add_argument("--portfolio", action="store_true", help="View paper trading portfolio ledger")
    parser.add_argument("--chat", action="store_true", help="Launch interactive Trader Agent REPL")

    args = parser.parse_args()

    if args.scan:
        run_scanner_cli()
    elif args.portfolio:
        display_portfolio_cli()
    elif args.chat:
        interactive_chat_repl()
    elif args.symbol:
        display_stock_terminal(args.symbol)
    else:
        display_stock_terminal("AAPL")


if __name__ == "__main__":
    main()
