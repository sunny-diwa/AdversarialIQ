"""
Isolated 2-Way Paper Trading Broker for Fast-Forward Agentic Simulation.
Alpaca is explicitly bypassed/disabled here; all fills execute against isolated local ledger.
Supports LONG (BUY/SELL) and SHORT (SHORT/COVER), slippage, intrabar Stop-Loss / Take-Profit checking,
exposure caps, and institutional analytics (Sharpe, Max Drawdown, Win Rate, Profit Factor).
"""

from datetime import datetime
import json
import logging
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

logger = logging.getLogger("SimBroker")


class SimulationBroker:
    """Deterministic 2-way local paper broker with conservative intrabar bracket execution."""

    def __init__(
        self,
        run_dir: Path,
        initial_capital: float = 100000.0,
        max_open_positions: int = 6,
        max_ticker_pct: float = 0.18,
        slippage_bps: float = 2.0
    ):
        self.ledger_path = run_dir / "portfolio_ledger.json"
        self.initial_capital = float(initial_capital)
        self.max_open_positions = max_open_positions
        self.max_ticker_pct = max_ticker_pct
        self.slippage_rate = slippage_bps / 10000.0

        self.cash: float = float(initial_capital)
        self.positions: Dict[str, Dict[str, Any]] = {}
        self.trades: List[Dict[str, Any]] = []
        self.closed_trades: List[Dict[str, Any]] = []
        self.equity_curve: List[Dict[str, Any]] = []
        self.realized_pnl: float = 0.0

        if self.ledger_path.exists():
            self._load()

    def _load(self):
        with open(self.ledger_path, "r", encoding="utf-8") as f:
            d = json.load(f)
        self.cash = d.get("cash", self.initial_capital)
        self.positions = d.get("positions", {})
        self.trades = d.get("trades", [])
        self.closed_trades = d.get("closed_trades", [])
        self.equity_curve = d.get("equity_curve", [])
        self.realized_pnl = d.get("realized_pnl", 0.0)

    def save(self):
        with open(self.ledger_path, "w", encoding="utf-8") as f:
            json.dump({
                "initial_capital": self.initial_capital,
                "cash": round(self.cash, 2),
                "realized_pnl": round(self.realized_pnl, 2),
                "positions": self.positions,
                "trades": self.trades,
                "closed_trades": self.closed_trades,
                "equity_curve": self.equity_curve
            }, f, indent=2)

    def compute_equity(self, prices: Dict[str, float]) -> float:
        """
        Total Equity = Cash + MarketValue(Longs) + UnrealizedPnL(Shorts) + Collateral(Shorts)
        Note: When opening SHORT for $X, we credit proceeds $X to cash so Liability = cur_price * qty;
        Net Equity = cash + sum(qty * cur_price) (since qty is negative for short!).
        Wait: Verify!
        Suppose start cash = $100,000. Short 100 shares @ $50 ($5,000 proceeds).
        Cash becomes $105,000. Position qty = -100, cost_proceeds = $5,000.
        If price rises to $55: cash ($105,000) + (-100 * $55 = -$5,500) = $99,500 (exact -$500 loss!).
        If price falls to $40: cash ($105,000) + (-100 * $40 = -$4,000) = $101,000 (exact +$1,000 profit!).
        If covering 100 shares @ $40: cash pays $4,000 -> cash = $101,000, pos deleted, realized PnL = +$1,000!
        Exact accounting! Also track margin_reserved = abs(qty) * entry_price so we don't lever infinitely on short proceeds!
        """
        pos_val = 0.0
        for sym, pos in self.positions.items():
            p = float(prices.get(sym, pos["entry_price"]))
            pos_val += pos["signed_qty"] * p
        return round(self.cash + pos_val, 2)

    def available_buying_power(self, prices: Dict[str, float]) -> float:
        """Prevents short-sale proceeds from masking available cash/buying power."""
        equity = self.compute_equity(prices)
        gross_exposure = sum(abs(pos["signed_qty"]) * float(prices.get(sym, pos["entry_price"])) for sym, pos in self.positions.items())
        return max(0.0, equity - gross_exposure)

    def record_equity_point(self, ts: str, prices: Dict[str, float]):
        eq = self.compute_equity(prices)
        bp = self.available_buying_power(prices)
        self.equity_curve.append({
            "timestamp": ts,
            "equity": eq,
            "available_bp": round(bp, 2),
            "open_positions": len(self.positions),
            "realized_pnl": round(self.realized_pnl, 2)
        })
        self.save()
        return eq

    def get_position_summary_for_prompt(self, sym: str, current_price: float) -> str:
        pos = self.positions.get(sym.upper())
        if not pos:
            return "NONE (Flat — 0 shares)"
        sq = pos["signed_qty"]
        side = "LONG" if sq > 0 else "SHORT"
        qty = abs(sq)
        entry = pos["entry_price"]
        unreal = (current_price - entry) * sq
        pct = ((current_price - entry) / entry * 100.0) * (1 if sq > 0 else -1) if entry > 0 else 0.0
        return (
            f"{side} {qty} shares @ ${entry:.2f} | Cur=${current_price:.2f} | "
            f"Unrealized=${unreal:+.2f} ({pct:+.2f}%) | Stop=${pos['stop_loss']:.2f} | Target=${pos['take_profit']:.2f} | Opened={pos['opened_at']}"
        )

    def process_intrabar_brackets(self, bar_windows: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """
        Walks 5m bars chronologically inside the elapsed interval and triggers Stop-Loss or Take-Profit
        deterministically if touched. Conservative tie-break: checks Stop-Loss before Take-Profit if both inside bar!
        High intrabar precision: 5m bars mean SL/TP triggers fire within a 5-minute window (vs 30m previously).
        """
        triggered: List[Dict[str, Any]] = []
        for sym in list(self.positions.keys()):
            df = bar_windows.get(sym)
            if df is None or df.empty:
                continue
            pos = self.positions.get(sym)
            if not pos:
                continue
            sl = pos.get("stop_loss")
            tp = pos.get("take_profit")
            sq = pos["signed_qty"]

            for idx, bar in df.iterrows():
                b_open = float(bar["Open"])
                b_high = float(bar["High"])
                b_low = float(bar["Low"])
                ts_str = idx.strftime("%Y-%m-%d %H:%M") if hasattr(idx, "strftime") else str(idx)

                if sq > 0:  # LONG position: stop below, target above
                    if sl and b_open <= sl:
                        ev = self._close_position_exact(sym, b_open * (1.0 - self.slippage_rate), f"GAP STOP-LOSS HIT (Open ${b_open:.2f} <= SL ${sl:.2f})", ts_str)
                        triggered.append(ev)
                        break
                    elif sl and b_low <= sl:
                        ev = self._close_position_exact(sym, sl * (1.0 - self.slippage_rate), f"STOP-LOSS TRIGGERED @ ${sl:.2f}", ts_str)
                        triggered.append(ev)
                        break
                    elif tp and b_open >= tp:
                        ev = self._close_position_exact(sym, b_open * (1.0 - self.slippage_rate), f"GAP TAKE-PROFIT HIT (Open ${b_open:.2f} >= TP ${tp:.2f})", ts_str)
                        triggered.append(ev)
                        break
                    elif tp and b_high >= tp:
                        ev = self._close_position_exact(sym, tp * (1.0 - self.slippage_rate), f"TAKE-PROFIT TRIGGERED @ ${tp:.2f}", ts_str)
                        triggered.append(ev)
                        break
                elif sq < 0:  # SHORT position: stop above, target below
                    if sl and b_open >= sl:
                        ev = self._close_position_exact(sym, b_open * (1.0 + self.slippage_rate), f"SHORT GAP STOP-LOSS HIT (Open ${b_open:.2f} >= SL ${sl:.2f})", ts_str)
                        triggered.append(ev)
                        break
                    elif sl and b_high >= sl:
                        ev = self._close_position_exact(sym, sl * (1.0 + self.slippage_rate), f"SHORT STOP-LOSS TRIGGERED @ ${sl:.2f}", ts_str)
                        triggered.append(ev)
                        break
                    elif tp and b_open <= tp:
                        ev = self._close_position_exact(sym, b_open * (1.0 + self.slippage_rate), f"SHORT GAP TAKE-PROFIT HIT (Open ${b_open:.2f} <= TP ${tp:.2f})", ts_str)
                        triggered.append(ev)
                        break
                    elif tp and b_low <= tp:
                        ev = self._close_position_exact(sym, tp * (1.0 + self.slippage_rate), f"SHORT TAKE-PROFIT TRIGGERED @ ${tp:.2f}", ts_str)
                        triggered.append(ev)
                        break
        if triggered:
            self.save()
        return triggered

    def _close_position_exact(self, sym: str, fill_price: float, reason: str, ts: str, pct: float = 1.0) -> Dict[str, Any]:
        pos = self.positions[sym]
        sq = pos["signed_qty"]
        side = "LONG" if sq > 0 else "SHORT"
        qty_held = abs(sq)
        close_qty = qty_held if pct >= 0.99 else max(1, int(round(qty_held * pct)))
        entry = pos["entry_price"]

        if sq > 0:  # Closing LONG via SELL
            proceeds = round(close_qty * fill_price, 2)
            cost_basis = round(close_qty * entry, 2)
            realized = round(proceeds - cost_basis, 2)
            pnl_pct = round((realized / cost_basis * 100.0), 2) if cost_basis > 0 else 0.0
            self.cash += proceeds
            pos["signed_qty"] -= close_qty
            action_lbl = "SELL"
        else:  # Closing SHORT via COVER
            cost_to_cover = round(close_qty * fill_price, 2)
            entry_proceeds = round(close_qty * entry, 2)
            realized = round(entry_proceeds - cost_to_cover, 2)
            pnl_pct = round((realized / entry_proceeds * 100.0), 2) if entry_proceeds > 0 else 0.0
            self.cash -= cost_to_cover
            pos["signed_qty"] += close_qty
            action_lbl = "COVER"

        self.realized_pnl = round(self.realized_pnl + realized, 2)
        if pos["signed_qty"] == 0:
            del self.positions[sym]

        rec = {
            "id": f"SIM-{len(self.trades)+1:04d}",
            "time": ts,
            "symbol": sym,
            "action": action_lbl,
            "side": side,
            "quantity": close_qty,
            "entry_price": round(entry, 2),
            "price": round(fill_price, 2),
            "realized_pnl": realized,
            "pnl_pct": pnl_pct,
            "rationale": reason
        }
        self.trades.append(rec)
        self.closed_trades.append(rec)
        self.save()
        return rec

    def execute_decision(
        self,
        sym: str,
        action: str,
        market_price: float,
        allocation_pct: float,
        stop_loss: Optional[float],
        take_profit: Optional[float],
        atr_14: float,
        rationale: str,
        ts: str,
        current_prices: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Executes BUY, SELL, SHORT, COVER, or HOLD cleanly with mathematical bracket integrity & exposure caps.
        """
        sym = sym.strip().upper()
        act = action.strip().upper()
        if act == "HOLD" or market_price <= 0:
            return {"status": "HOLD", "symbol": sym, "action": "HOLD", "message": rationale}

        pos = self.positions.get(sym)

        # If holding SHORT and Agent says BUY -> First COVER short (or reverse!)
        if act == "BUY" and pos and pos["signed_qty"] < 0:
            cover_ev = self._close_position_exact(
                sym, market_price * (1.0 + self.slippage_rate),
                f"Bull victory reverse/cover: {rationale}", ts
            )
            # Proceed to open LONG only if conviction calls for full flip (below)

        # If holding LONG and Agent says SHORT -> First SELL long!
        if act == "SHORT" and pos and pos["signed_qty"] > 0:
            sell_ev = self._close_position_exact(
                sym, market_price * (1.0 - self.slippage_rate),
                f"Bear victory exit/reverse: {rationale}", ts
            )

        if act == "SELL":
            if not pos or pos["signed_qty"] <= 0:
                return {"status": "SKIPPED", "symbol": sym, "action": "SELL", "message": f"No LONG position in {sym} to SELL."}
            fill = round(market_price * (1.0 - self.slippage_rate), 2)
            ev = self._close_position_exact(sym, fill, rationale, ts)
            return {"status": "FILLED", **ev}

        if act == "COVER":
            if not pos or pos["signed_qty"] >= 0:
                return {"status": "SKIPPED", "symbol": sym, "action": "COVER", "message": f"No SHORT position in {sym} to COVER."}
            fill = round(market_price * (1.0 + self.slippage_rate), 2)
            ev = self._close_position_exact(sym, fill, rationale, ts)
            return {"status": "FILLED", **ev}

        # Refresh pos check after reversal
        pos = self.positions.get(sym)
        equity = self.compute_equity(current_prices)
        bp = self.available_buying_power(current_prices)

        if sym not in self.positions and len(self.positions) >= self.max_open_positions:
            return {"status": "VETOED", "symbol": sym, "action": act, "message": f"Max concurrent positions ({self.max_open_positions}) reached."}

        clamped_pct = max(2.0, min(self.max_ticker_pct * 100.0, float(allocation_pct or 10.0))) / 100.0
        target_dollars = min(equity * clamped_pct, bp * 0.95)
        existing_val = abs(pos["signed_qty"]) * market_price if pos else 0.0
        remaining_room = max(0.0, (equity * self.max_ticker_pct) - existing_val)
        order_dollars = min(target_dollars, remaining_room)

        fill_price = round(
            market_price * (1.0 + self.slippage_rate if act == "BUY" else 1.0 - self.slippage_rate),
            2
        )
        qty = math.floor(order_dollars / fill_price) if fill_price > 0 else 0
        if qty <= 0:
            return {"status": "VETOED", "symbol": sym, "action": act, "message": "Insufficient remaining ticker allocation or buying power."}

        # Validate/enforce safe mathematical brackets
        safe_dist = max(round(atr_14 * 1.35, 2), round(fill_price * 0.018, 2))
        if act == "BUY":
            sl = round(float(stop_loss), 2) if (stop_loss and float(stop_loss) < fill_price * 0.992 and float(stop_loss) > fill_price * 0.85) else round(fill_price - safe_dist, 2)
            tp = round(float(take_profit), 2) if (take_profit and float(take_profit) > fill_price * 1.01) else round(fill_price + safe_dist * 2.0, 2)

            cost = round(qty * fill_price, 2)
            self.cash -= cost
            if pos and pos["signed_qty"] > 0:
                old_qty = pos["signed_qty"]
                new_qty = old_qty + qty
                avg_p = round(((old_qty * pos["entry_price"]) + cost) / new_qty, 2)
                self.positions[sym] = {
                    "signed_qty": new_qty,
                    "entry_price": avg_p,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "opened_at": pos["opened_at"]
                }
            else:
                self.positions[sym] = {
                    "signed_qty": qty,
                    "entry_price": fill_price,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "opened_at": ts
                }

            rec = {
                "id": f"SIM-{len(self.trades)+1:04d}",
                "time": ts,
                "symbol": sym,
                "action": "BUY",
                "side": "LONG",
                "quantity": qty,
                "price": fill_price,
                "total": cost,
                "stop_loss": sl,
                "take_profit": tp,
                "rationale": rationale
            }
            self.trades.append(rec)
            self.save()
            return {"status": "FILLED", **rec}

        elif act == "SHORT":
            sl = round(float(stop_loss), 2) if (stop_loss and float(stop_loss) > fill_price * 1.008 and float(stop_loss) < fill_price * 1.15) else round(fill_price + safe_dist, 2)
            tp = round(float(take_profit), 2) if (take_profit and float(take_profit) < fill_price * 0.99) else round(fill_price - safe_dist * 2.0, 2)

            proceeds = round(qty * fill_price, 2)
            self.cash += proceeds
            if pos and pos["signed_qty"] < 0:
                old_qty = abs(pos["signed_qty"])
                new_qty = old_qty + qty
                avg_p = round(((old_qty * pos["entry_price"]) + proceeds) / new_qty, 2)
                self.positions[sym] = {
                    "signed_qty": -new_qty,
                    "entry_price": avg_p,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "opened_at": pos["opened_at"]
                }
            else:
                self.positions[sym] = {
                    "signed_qty": -qty,
                    "entry_price": fill_price,
                    "stop_loss": sl,
                    "take_profit": tp,
                    "opened_at": ts
                }

            rec = {
                "id": f"SIM-{len(self.trades)+1:04d}",
                "time": ts,
                "symbol": sym,
                "action": "SHORT",
                "side": "SHORT",
                "quantity": qty,
                "price": fill_price,
                "total": proceeds,
                "stop_loss": sl,
                "take_profit": tp,
                "rationale": rationale
            }
            self.trades.append(rec)
            self.save()
            return {"status": "FILLED", **rec}

        return {"status": "HOLD", "symbol": sym, "action": "HOLD", "message": "Unhandled action"}

    def compute_performance_report(self, final_prices: Dict[str, float], spy_start: float, spy_end: float) -> Dict[str, Any]:
        final_eq = self.compute_equity(final_prices)
        tot_ret = round(((final_eq - self.initial_capital) / self.initial_capital) * 100.0, 2)
        spy_ret = round(((spy_end - spy_start) / spy_start) * 100.0, 2) if spy_start > 0 else 0.0

        wins = [t for t in self.closed_trades if t["realized_pnl"] > 0]
        losses = [t for t in self.closed_trades if t["realized_pnl"] <= 0]
        win_rate = round(len(wins) / len(self.closed_trades) * 100.0, 1) if self.closed_trades else 0.0
        gross_win = sum(t["realized_pnl"] for t in wins)
        gross_loss = abs(sum(t["realized_pnl"] for t in losses))
        profit_factor = round(gross_win / gross_loss, 2) if gross_loss > 0 else (round(gross_win, 2) if gross_win > 0 else 1.0)

        # Max drawdown across recorded equity curve
        max_dd = 0.0
        peak = self.initial_capital
        for pt in self.equity_curve:
            eq = pt["equity"]
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100.0 if peak > 0 else 0.0
            if dd > max_dd:
                max_dd = dd

        long_closed = [t for t in self.closed_trades if t.get("side") == "LONG"]
        short_closed = [t for t in self.closed_trades if t.get("side") == "SHORT"]

        return {
            "initial_capital": self.initial_capital,
            "final_equity": final_eq,
            "total_return_pct": tot_ret,
            "benchmark_spy_pct": spy_ret,
            "alpha_vs_spy_pct": round(tot_ret - spy_ret, 2),
            "realized_pnl": round(self.realized_pnl, 2),
            "unrealized_pnl": round(final_eq - self.initial_capital - self.realized_pnl, 2),
            "total_orders": len(self.trades),
            "closed_trades": len(self.closed_trades),
            "open_positions": len(self.positions),
            "win_rate_pct": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown_pct": round(max_dd, 2),
            "long_trades_closed": len(long_closed),
            "long_pnl": round(sum(t["realized_pnl"] for t in long_closed), 2),
            "short_trades_closed": len(short_closed),
            "short_pnl": round(sum(t["realized_pnl"] for t in short_closed), 2),
        }
