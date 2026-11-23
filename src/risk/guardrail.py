"""
Deterministic Risk & Position-Sizing Guardrail (Non-LLM)
Institutional Python Risk Management Gate executed between LLM Adversarial Debates and Alpaca Execution.
Guarantees 100% deterministic mathematical sizing, eliminates LLM math hallucination, and caps portfolio downside.

Core Mandates:
1. ATR-Based Position Sizing: Sizes trades using 14-day ATR risking fixed 0.5% - 1.0% of equity.
2. Exposure Caps: Max 5% of portfolio per ticker, max 20% in a single GICS sector, max 5 open positions.
3. Earnings Blackout Filter: Automatic 48h blackout veto or 50% position halving.
4. Mandatory Bracket Orders: Strictly calculates take-profit (2:1 R/R) and stop-loss legs.
"""

import logging
import math
from typing import Any, Dict, List, Optional

from src.core.config import SP500_MAP
from src.data.calendar import fetch_earnings_calendar
from src.data.macro import fetch_macro_regime
from src.data.market import fetch_stock_technicals

logger = logging.getLogger("RiskGuardrail")


class RiskGuardrail:
    """Institutional Non-LLM Risk Manager Gate."""

    MAX_TICKER_PCT = 0.05       # Max 5% of total portfolio equity in one stock
    MAX_SECTOR_PCT = 0.20       # Max 20% of total portfolio equity in one GICS sector
    MAX_OPEN_POSITIONS = 5      # Max 5 concurrent active positions
    DEFAULT_RISK_PCT = 0.01     # 1% equity risk per trade
    CAUTIOUS_RISK_PCT = 0.005   # 0.5% equity risk in volatile / risk-off macro regimes
    MIN_RR_RATIO = 2.0          # Minimum 2:1 Reward-to-Risk ratio for bracket orders

    @classmethod
    def evaluate_order(
        cls,
        symbol: str,
        action: str,  # BUY or SELL
        equity: float,
        current_positions: Dict[str, Any],
        requested_shares: Optional[int] = None,
        conviction_score: Optional[int] = 50,
        manual_override: bool = False
    ) -> Dict[str, Any]:
        """
        Runs the full deterministic risk assessment pipeline.
        Calculates ATR-based sizing, checks exposure caps, verifies earnings calendar,
        and outputs mandatory bracket order legs.
        """
        sym = symbol.strip().upper()
        act = action.strip().upper()
        meta = SP500_MAP.get(sym, {"name": sym, "sector": "Other"})
        sector = meta.get("sector", "Other")

        # Normalize positions whether passed as a dict or list
        if isinstance(current_positions, list):
            pos_dict = {p.get("symbol", "").upper(): p for p in current_positions if isinstance(p, dict) and p.get("symbol")}
        elif isinstance(current_positions, dict):
            pos_dict = dict(current_positions)
        else:
            pos_dict = {}

        # 1. Fetch live market technicals (Price & 14-day ATR)
        technicals = fetch_stock_technicals(sym)
        price = technicals.get("price", 100.0)
        atr_14 = technicals.get("atr", max(round(price * 0.02, 2), 0.5))

        # 2. Fetch Macro Regime to determine dynamic risk percentage
        macro = fetch_macro_regime()
        macro_regime = macro.get("regime", "NEUTRAL")
        risk_pct = cls.CAUTIOUS_RISK_PCT if macro_regime in ("CAUTIOUS", "RISK_OFF") else cls.DEFAULT_RISK_PCT

        # 3. Check Earnings Calendar Filter
        calendar_info = fetch_earnings_calendar(sym)
        blackout_status = calendar_info.get("blackout_status", "CLEAR")
        size_multiplier = calendar_info.get("size_multiplier", 1.0)

        veto_reasons: List[str] = []
        warnings: List[str] = []

        # If selling, closing or trimming existing position
        if act == "SELL":
            pos = pos_dict.get(sym)
            available_qty = pos.get("quantity", 0) if pos else 0
            if available_qty <= 0:
                veto_reasons.append(f"Cannot SELL {sym}: No active position held in portfolio.")
                approved = False
                final_shares = 0
            else:
                final_shares = min(requested_shares or available_qty, available_qty)
                approved = True
            
            return {
                "approved": approved,
                "symbol": sym,
                "action": act,
                "sector": sector,
                "price": round(price, 2),
                "equity": round(equity, 2),
                "raw_shares": requested_shares or 0,
                "adjusted_shares": final_shares,
                "total_consideration": round(final_shares * price, 2),
                "stop_loss": None,
                "take_profit": None,
                "veto_reasons": veto_reasons,
                "warnings": warnings,
                "risk_checks": {
                    "action": "SELL_POSITION_REDUCTION",
                    "available_shares": available_qty
                }
            }

        # --- BUY ORDERS: STRICT RISK CONTROLS ---

        # Check 1: Earnings Blackout Window
        if blackout_status == "VETO_BLACKOUT":
            veto_reasons.append(f"Earnings Blackout Veto: {calendar_info.get('reason')}")
        elif blackout_status in ("WARNING_HALVE_SIZE", "POST_EARNINGS_VOLATILITY"):
            warnings.append(f"Earnings Proximity Warning: {calendar_info.get('reason')}")

        # Check 2: Max Concurrent Positions Cap
        num_positions = len(pos_dict)
        is_new_ticker = sym not in pos_dict
        if is_new_ticker and num_positions >= cls.MAX_OPEN_POSITIONS:
            veto_reasons.append(
                f"Portfolio Cap Veto: Maximum open position limit ({cls.MAX_OPEN_POSITIONS}) reached. "
                f"Current active positions: {', '.join(pos_dict.keys())}. Close an existing position first."
            )

        # Check 3: ATR-Based Position Sizing
        # Dollar risk budget = Equity * risk_pct (e.g. $10,000 * 0.01 = $100)
        risk_budget_dollars = equity * risk_pct
        # Stop Distance = max(1.5 * ATR, 1.5% of price)
        stop_distance = max(round(atr_14 * 1.5, 2), round(price * 0.015, 2))
        
        # Calculate base shares from volatility
        raw_atr_shares = max(1, math.floor(risk_budget_dollars / stop_distance)) if stop_distance > 0 else 1

        # Check 4: Conviction Score Sizing Modifier
        # If conviction is low (<50), reject or size down
        if conviction_score and conviction_score < 45 and not manual_override:
            veto_reasons.append(f"Judicial Conviction Veto: Score {conviction_score}/100 is below the 45-point threshold.")

        # Apply earnings multiplier (e.g. 0.5x if within 48h)
        sized_shares = max(1, math.floor(raw_atr_shares * size_multiplier))

        # Check 5: Max 5% of Portfolio Per Ticker Cap
        max_ticker_allocation = equity * cls.MAX_TICKER_PCT
        existing_val = pos_dict.get(sym, {}).get("current_value", 0.0) if sym in pos_dict else 0.0
        remaining_ticker_cap = max(0.0, max_ticker_allocation - existing_val)
        max_shares_by_ticker_cap = math.floor(remaining_ticker_cap / price) if price > 0 else 0

        if sized_shares > max_shares_by_ticker_cap:
            warnings.append(
                f"Position clamped by 5% single-ticker exposure cap: Reduced from {sized_shares} to {max_shares_by_ticker_cap} shares."
            )
            sized_shares = max_shares_by_ticker_cap

        # Check 6: Max 20% Sector Exposure Cap
        current_sector_val = 0.0
        for p_sym, p_data in pos_dict.items():
            p_sector = SP500_MAP.get(p_sym, {}).get("sector", "Other")
            if p_sector == sector:
                current_sector_val += float(p_data.get("current_value", 0.0) or (p_data.get("quantity", 0) * price))

        max_sector_allocation = equity * cls.MAX_SECTOR_PCT
        remaining_sector_cap = max(0.0, max_sector_allocation - current_sector_val)
        max_shares_by_sector_cap = math.floor(remaining_sector_cap / price) if price > 0 else 0

        if sized_shares > max_shares_by_sector_cap:
            warnings.append(
                f"Position clamped by 20% {sector} sector exposure cap: Reduced to {max_shares_by_sector_cap} shares."
            )
            sized_shares = max_shares_by_sector_cap

        # If user explicitly requested shares, clamp to our safe mathematical limit
        if requested_shares and requested_shares > 0:
            if requested_shares > sized_shares and sized_shares > 0:
                warnings.append(
                    f"Requested shares ({requested_shares}) exceeded mathematical risk cap. Clamped to {sized_shares} shares."
                )
            elif requested_shares < sized_shares:
                sized_shares = requested_shares

        # Check 7: Minimum shares & Cash check
        total_trade_cost = round(sized_shares * price, 2)
        if sized_shares <= 0:
            veto_reasons.append("Exposure Cap Veto: Insufficient remaining capital headroom under 5% ticker or 20% sector caps.")

        if total_trade_cost > equity:
            veto_reasons.append(f"Margin Veto: Trade cost (${total_trade_cost:.2f}) exceeds total portfolio equity (${equity:.2f}).")

        # Mandatory Bracket Orders: calculate automated stop loss and take profit
        stop_loss_price = round(price - stop_distance, 2)
        take_profit_price = round(price + (stop_distance * cls.MIN_RR_RATIO), 2)

        approved = len(veto_reasons) == 0 and sized_shares > 0

        final_shares = sized_shares if approved else 0
        final_cost = round(final_shares * price, 2)
        portfolio_pct = round((final_cost / equity * 100), 2) if equity > 0 else 0.0

        return {
            "approved": approved,
            "symbol": sym,
            "action": act,
            "sector": sector,
            "price": round(price, 2),
            "equity": round(equity, 2),
            "raw_shares": raw_atr_shares,
            "adjusted_shares": final_shares,
            "total_consideration": final_cost,
            "portfolio_allocation_pct": portfolio_pct,
            "stop_loss": stop_loss_price,
            "take_profit": take_profit_price,
            "risk_reward_ratio": f"1 : {cls.MIN_RR_RATIO:.1f}",
            "stop_distance": round(stop_distance, 2),
            "atr_14": round(atr_14, 2),
            "macro_regime": macro_regime,
            "risk_budget_dollars": round(risk_budget_dollars, 2),
            "veto_reasons": veto_reasons,
            "warnings": warnings,
            "risk_checks": {
                "atr_sizing_applied": True,
                "ticker_cap_5pct_limit": round(max_ticker_allocation, 2),
                "sector_cap_20pct_limit": round(max_sector_allocation, 2),
                "current_sector_exposure": round(current_sector_val, 2),
                "max_open_positions_cap": cls.MAX_OPEN_POSITIONS,
                "current_open_positions": num_positions,
                "earnings_blackout_status": blackout_status,
                "earnings_blackout_reason": calendar_info.get("reason"),
                "mandatory_bracket_order": {
                    "order_class": "bracket",
                    "stop_loss": {"stop_price": stop_loss_price},
                    "take_profit": {"limit_price": take_profit_price}
                }
            }
        }
