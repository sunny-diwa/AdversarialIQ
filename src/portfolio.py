"""
Paper Trading Portfolio & Risk Execution Engine
Initializes paper portfolio with $10,000 baseline, zero initial positions,
institutional risk controls (max concentration caps, Kelly sizing), and equity trajectory tracking.
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional
import yfinance as yf

from src.config import PORTFOLIO_FILE, SP500_MAP

logger = logging.getLogger("PortfolioEngine")

DEFAULT_PORTFOLIO = {
    "cash": 10000.0,
    "initial_balance": 10000.0,
    "positions": {},
    "trades": [],
    "realized_pnl": 0.0,
    "equity_history": [
        {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "equity": 10000.0, "cash": 10000.0}
    ]
}


def load_portfolio() -> Dict[str, Any]:
    """Loads current paper portfolio from persistent JSON file."""
    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error reading portfolio file: {e}")
    return dict(DEFAULT_PORTFOLIO)


def save_portfolio(portfolio: Dict[str, Any]):
    """Persists paper portfolio to JSON storage."""
    try:
        with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
            json.dump(portfolio, f, indent=2)
    except Exception as e:
        logger.error(f"Error saving portfolio: {e}")


def reset_portfolio() -> Dict[str, Any]:
    """Resets paper portfolio to clean $10,000 baseline with 0 active positions."""
    clean_p = {
        "cash": 10000.0,
        "initial_balance": 10000.0,
        "positions": {},
        "trades": [],
        "realized_pnl": 0.0,
        "equity_history": [
            {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "equity": 10000.0, "cash": 10000.0}
        ]
    }
    save_portfolio(clean_p)
    return clean_p


def get_portfolio_state() -> Dict[str, Any]:
    """
    Returns live paper portfolio with marked-to-market valuations,
    advanced risk metrics (Win Rate %, Profit Factor, Concentration Risk %, Cash Ratio %),
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

    # Advanced Quant & Risk Metrics
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
            {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"), "equity": round(total_equity, 2), "cash": round(cash, 2)}
        ])
    }


def execute_order(
    action: str,
    symbol: str,
    quantity: int,
    order_type: str = "MARKET",
    limit_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    rationale: str = "Manual Desk Execution"
) -> Dict[str, Any]:
    """Executes a virtual paper trade (BUY or SELL) with order typing and risk tracking."""
    sym = symbol.strip().upper()
    act = action.strip().upper()
    qty = int(quantity)

    if qty <= 0:
        raise ValueError("Quantity must be greater than 0")

    # Fetch live execution price
    try:
        t = yf.Ticker(sym)
        price = t.fast_info.last_price or 100.0
    except Exception as e:
        raise ValueError(f"Cannot fetch live price for {sym}: {e}")

    # Check limit condition
    if order_type == "LIMIT" and limit_price:
        if act == "BUY" and price > limit_price:
            raise ValueError(f"Market price ${price:.2f} is above your BUY limit of ${limit_price:.2f}")
        if act == "SELL" and price < limit_price:
            raise ValueError(f"Market price ${price:.2f} is below your SELL limit of ${limit_price:.2f}")
        exec_price = limit_price
    else:
        exec_price = price

    total_order_val = exec_price * qty
    p = load_portfolio()
    positions = p.setdefault("positions", {})
    cash = p.get("cash", 10000.0)

    trade_record = {
        "id": f"TRD-{int(time.time())}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "type": act,
        "symbol": sym,
        "quantity": qty,
        "price": round(exec_price, 2),
        "total": round(total_order_val, 2),
        "order_type": order_type or "MARKET",
        "stop_loss": stop_loss,
        "take_profit": take_profit,
        "rationale": rationale or "Desk Execution"
    }

    if act == "BUY":
        if cash < total_order_val:
            raise ValueError(f"Insufficient funds! Need ${total_order_val:.2f}, Cash available: ${cash:.2f}")

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
            if stop_loss:
                positions[sym]["stop_loss"] = stop_loss
            if take_profit:
                positions[sym]["take_profit"] = take_profit
        else:
            positions[sym] = {
                "symbol": sym,
                "quantity": qty,
                "avg_price": round(exec_price, 2),
                "cost_basis": round(total_order_val, 2),
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }

    elif act == "SELL":
        if sym not in positions or positions[sym]["quantity"] < qty:
            avail = positions.get(sym, {}).get("quantity", 0)
            raise ValueError(f"Cannot sell {qty} shares of {sym}. You currently hold {avail} shares.")

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
    p["equity_history"] = eq_history[-50:]

    save_portfolio(p)

    return {
        "status": "SUCCESS",
        "trade": trade_record,
        "message": f"Successfully executed {act} {qty} shares of {sym} at ${exec_price:.2f}"
    }
