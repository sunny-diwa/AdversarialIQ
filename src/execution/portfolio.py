"""
Paper Trading Portfolio & Risk Execution Engine
Supports Alpaca US Paper Trading API (https://paper-api.alpaca.markets/v2) with
seamless fallback to Local Simulated Paper Ledger ($10,000 baseline, zero initial positions).
Strictly integrates Non-LLM Risk Guardrails, mandatory bracket orders, and thesis reflection logging.
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional
import yfinance as yf

from src.core.config import PORTFOLIO_FILE, SP500_MAP
from src.execution.alpaca import AlpacaPaperClient
from src.memory.journal import record_trade_close
from src.risk.guardrail import RiskGuardrail

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


def get_portfolio_state(alpaca_key: Optional[str] = None, alpaca_secret: Optional[str] = None) -> Dict[str, Any]:
    """
    Returns live paper portfolio with marked-to-market valuations,
    advanced risk metrics (Win Rate %, Profit Factor, Concentration Risk %, Cash Ratio %),
    and equity trajectory history.
    Syncs with Alpaca Paper Trading API if configured.
    """
    alpaca = AlpacaPaperClient(api_key=alpaca_key, secret_key=alpaca_secret)
    p = load_portfolio()
    trades = p.get("trades", [])

    if alpaca.is_configured():
        alpaca_acct = alpaca.get_account()
        if alpaca_acct:
            cash = alpaca_acct["cash"]
            total_equity = alpaca_acct["portfolio_value"] or alpaca_acct["equity"] or cash
            alpaca_positions = alpaca.get_positions()
            holdings = []
            total_holdings_val = 0.0

            for pos in alpaca_positions:
                sym = pos["symbol"]
                cost_b = pos["cost_basis"]
                mkt_v = pos["current_value"]
                total_holdings_val += mkt_v
                holdings.append({
                    "symbol": sym,
                    "name": SP500_MAP.get(sym, {}).get("name", sym),
                    "quantity": pos["quantity"],
                    "avg_price": pos["avg_price"],
                    "current_price": pos["current_price"],
                    "cost_basis": cost_b,
                    "current_value": mkt_v,
                    "unrealized_pnl": pos["unrealized_pnl"],
                    "unrealized_pct": pos["unrealized_pct"],
                    "status": "UP" if pos["unrealized_pnl"] >= 0 else "DOWN"
                })

            init_balance = p.get("initial_balance", 10000.0)
            total_pnl = total_equity - init_balance
            total_pnl_pct = (total_pnl / init_balance * 100) if init_balance else 0.0

            # Advanced metrics
            closed_trades = [t for t in trades if t.get("type") == "SELL" and "pnl" in t]
            wins = [t for t in closed_trades if t.get("pnl", 0) > 0]
            losses = [t for t in closed_trades if t.get("pnl", 0) <= 0]
            win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0.0
            gross_wins = sum(t.get("pnl", 0) for t in wins)
            gross_losses = abs(sum(t.get("pnl", 0) for t in losses))
            profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else (round(gross_wins, 2) if gross_wins > 0 else 1.0)

            max_stock_val = max([h["current_value"] for h in holdings], default=0.0)
            concentration_risk = round((max_stock_val / total_equity * 100), 1) if total_equity else 0.0
            cash_ratio = round((cash / total_equity * 100), 1) if total_equity else 100.0

            return {
                "source": "Alpaca US Paper Trading",
                "account_number": alpaca_acct.get("account_number"),
                "status": alpaca_acct.get("status", "ACTIVE"),
                "cash": round(cash, 2),
                "total_equity": round(total_equity, 2),
                "holdings_value": round(total_holdings_val, 2),
                "total_pnl": round(total_pnl, 2),
                "total_pnl_pct": round(total_pnl_pct, 2),
                "realized_pnl": round(p.get("realized_pnl", 0.0), 2),
                "positions_count": len(holdings),
                "positions": holdings,
                "trades": trades[-20:],
                "win_rate": round(win_rate, 1),
                "profit_factor": profit_factor,
                "concentration_risk": concentration_risk,
                "cash_ratio": cash_ratio,
                "equity_history": p.get("equity_history", [])[-25:],
                "initial_balance": init_balance
            }

    # Fallback to local paper trading ledger ($10,000 base)
    cash = p.get("cash", 10000.0)
    raw_positions = p.get("positions", {})
    holdings = []
    total_holdings_val = 0.0

    for sym, pos in raw_positions.items():
        qty = pos.get("quantity", 0)
        avg_price = pos.get("avg_price", 0.0)
        cost_basis = pos.get("cost_basis", qty * avg_price)

        cur_price = avg_price
        try:
            t = yf.Ticker(sym)
            cur_price = float(t.fast_info.last_price or avg_price)
        except Exception:
            pass

        current_val = round(qty * cur_price, 2)
        total_holdings_val += current_val
        unrealized = round(current_val - cost_basis, 2)
        unrealized_pct = round((unrealized / cost_basis * 100), 2) if cost_basis else 0.0

        holdings.append({
            "symbol": sym,
            "name": SP500_MAP.get(sym, {}).get("name", sym),
            "quantity": qty,
            "avg_price": round(avg_price, 2),
            "current_price": round(cur_price, 2),
            "cost_basis": round(cost_basis, 2),
            "current_value": current_val,
            "unrealized_pnl": unrealized,
            "unrealized_pct": unrealized_pct,
            "status": "UP" if unrealized >= 0 else "DOWN",
            "stop_loss": pos.get("stop_loss"),
            "take_profit": pos.get("take_profit")
        })

    total_equity = round(cash + total_holdings_val, 2)
    init_balance = p.get("initial_balance", 10000.0)
    total_pnl = round(total_equity - init_balance, 2)
    total_pnl_pct = round((total_pnl / init_balance * 100), 2) if init_balance else 0.0

    closed_trades = [t for t in trades if t.get("type") == "SELL" and "pnl" in t]
    wins = [t for t in closed_trades if t.get("pnl", 0) > 0]
    losses = [t for t in closed_trades if t.get("pnl", 0) <= 0]
    win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0.0
    gross_wins = sum(t.get("pnl", 0) for t in wins)
    gross_losses = abs(sum(t.get("pnl", 0) for t in losses))
    profit_factor = round(gross_wins / gross_losses, 2) if gross_losses > 0 else (round(gross_wins, 2) if gross_wins > 0 else 1.0)

    max_stock_val = max([h["current_value"] for h in holdings], default=0.0)
    concentration_risk = round((max_stock_val / total_equity * 100), 1) if total_equity else 0.0
    cash_ratio = round((cash / total_equity * 100), 1) if total_equity else 100.0

    return {
        "source": "Local Simulated Desk ($10,000 Base)",
        "cash": round(cash, 2),
        "total_equity": total_equity,
        "holdings_value": round(total_holdings_val, 2),
        "total_pnl": total_pnl,
        "total_pnl_pct": total_pnl_pct,
        "realized_pnl": round(p.get("realized_pnl", 0.0), 2),
        "positions_count": len(holdings),
        "positions": holdings,
        "trades": trades[-20:],
        "win_rate": round(win_rate, 1),
        "profit_factor": profit_factor,
        "concentration_risk": concentration_risk,
        "cash_ratio": cash_ratio,
        "equity_history": p.get("equity_history", [])[-25:],
        "initial_balance": init_balance
    }


def execute_order(
    action: str,  # BUY or SELL
    symbol: str,
    quantity: int,
    order_type: str = "MARKET",
    limit_price: Optional[float] = None,
    stop_loss: Optional[float] = None,
    take_profit: Optional[float] = None,
    rationale: str = "Quantitative Desk Execution",
    alpaca_key: Optional[str] = None,
    alpaca_secret: Optional[str] = None
) -> Dict[str, Any]:
    """
    Executes trade execution through Non-LLM Risk Guardrail.
    Enforces mandatory bracket legs and logs post-mortem reflection when a trade closes.
    """
    act = action.upper().strip()
    sym = symbol.upper().strip()
    qty = int(quantity)

    if qty <= 0:
        raise ValueError("Order quantity must be a positive integer greater than 0.")

    alpaca = AlpacaPaperClient(api_key=alpaca_key, secret_key=alpaca_secret)
    p = load_portfolio()
    current_equity = p.get("cash", 10000.0) + sum(pos.get("cost_basis", 0) for pos in p.get("positions", {}).values())

    if alpaca.is_configured():
        acct = alpaca.get_account()
        if acct:
            current_equity = acct.get("portfolio_value", current_equity)

    # 1. Evaluate with Non-LLM Risk Guardrail
    gate = RiskGuardrail.evaluate_order(
        symbol=sym,
        action=act,
        equity=current_equity,
        current_positions=p.get("positions", {}),
        requested_shares=qty,
        manual_override=True
    )

    if not gate["approved"]:
        reasons = "; ".join(gate["veto_reasons"])
        raise ValueError(f"Trade Vetoed by Risk Guardrail: {reasons}")

    # Use clamped/safe share quantity and bracket legs
    safe_qty = gate["adjusted_shares"]
    exec_price = gate["price"]
    final_stop_loss = stop_loss or gate.get("stop_loss")
    final_take_profit = take_profit or gate.get("take_profit")

    # 2. Route to Alpaca Paper Desk if configured
    if alpaca.is_configured():
        try:
            return alpaca.place_order(
                symbol=sym,
                quantity=safe_qty,
                side=act.lower(),
                order_type=order_type.lower(),
                limit_price=limit_price,
                stop_loss=final_stop_loss,
                take_profit=final_take_profit
            )
        except Exception as e:
            logger.warning(f"Alpaca routing notice ({e}); falling back to local simulated execution.")

    # 3. Local Desk Paper Execution
    cash = p.get("cash", 10000.0)
    positions = p.get("positions", {})
    trades = p.get("trades", [])
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if act == "BUY":
        total_cost = round(safe_qty * exec_price, 2)
        if total_cost > cash:
            raise ValueError(f"Insufficient cash reserves (${cash:,.2f}) for trade cost (${total_cost:,.2f}).")

        cash -= total_cost
        if sym in positions:
            existing = positions[sym]
            new_qty = existing["quantity"] + safe_qty
            new_cost = existing["cost_basis"] + total_cost
            positions[sym] = {
                "quantity": new_qty,
                "avg_price": round(new_cost / new_qty, 2),
                "cost_basis": round(new_cost, 2),
                "stop_loss": final_stop_loss,
                "take_profit": final_take_profit
            }
        else:
            positions[sym] = {
                "quantity": safe_qty,
                "avg_price": exec_price,
                "cost_basis": total_cost,
                "stop_loss": final_stop_loss,
                "take_profit": final_take_profit
            }

        trade_record = {
            "id": f"TRD-{int(time.time()*1000)}",
            "timestamp": now_str,
            "type": "BUY",
            "symbol": sym,
            "quantity": safe_qty,
            "price": exec_price,
            "total": total_cost,
            "order_type": order_type.upper(),
            "status": "FILLED",
            "rationale": rationale,
            "bracket": {
                "stop_loss": final_stop_loss,
                "take_profit": final_take_profit
            }
        }
        trades.append(trade_record)

    elif act == "SELL":
        if sym not in positions or positions[sym]["quantity"] < safe_qty:
            available = positions.get(sym, {}).get("quantity", 0)
            raise ValueError(f"Insufficient position in {sym}. Available: {available} shares, Requested: {safe_qty}.")

        pos = positions[sym]
        avg_cost = pos["avg_price"]
        proceeds = round(safe_qty * exec_price, 2)
        cost_of_shares = round(safe_qty * avg_cost, 2)
        realized = round(proceeds - cost_of_shares, 2)
        pnl_pct = round((realized / cost_of_shares * 100), 2) if cost_of_shares else 0.0

        cash += proceeds
        pos["quantity"] -= safe_qty
        pos["cost_basis"] = round(pos["quantity"] * avg_cost, 2)
        if pos["quantity"] == 0:
            del positions[sym]

        p["realized_pnl"] = round(p.get("realized_pnl", 0.0) + realized, 2)

        trade_record = {
            "id": f"TRD-{int(time.time()*1000)}",
            "timestamp": now_str,
            "type": "SELL",
            "symbol": sym,
            "quantity": safe_qty,
            "price": exec_price,
            "total": proceeds,
            "order_type": order_type.upper(),
            "pnl": realized,
            "pnl_pct": pnl_pct,
            "status": "FILLED",
            "rationale": rationale
        }
        trades.append(trade_record)

        # Record trade close in SQLite memory journal and post-mortem reflection
        try:
            closed_rec = record_trade_close(sym, exec_price, realized)
            if closed_rec:
                from src.agents.post_mortem import PostMortemAgent
                PostMortemAgent.analyze_trade(closed_rec)
        except Exception as e:
            logger.debug(f"Post-mortem trigger notice: {e}")

    # Update equity history
    total_val = cash + sum(pos["cost_basis"] for pos in positions.values())
    eq_history = p.get("equity_history", [])
    eq_history.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "equity": round(total_val, 2),
        "cash": round(cash, 2)
    })
    p["equity_history"] = eq_history[-50:]
    p["cash"] = round(cash, 2)
    p["positions"] = positions
    p["trades"] = trades
    save_portfolio(p)

    return {
        "status": "SUCCESS",
        "trade": trade_record,
        "message": f"Successfully executed {act} {safe_qty} shares of {sym} at ${exec_price:.2f}."
    }
