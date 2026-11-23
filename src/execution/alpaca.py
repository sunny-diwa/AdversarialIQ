"""
Alpaca US Paper Trading Integration Client
Connects to Alpaca US Paper Trading API (https://paper-api.alpaca.markets/v2)
for live account balances, position tracking, and institutional order execution with mandatory bracket legs.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional
import requests

from src.core.config import ALPACA_API_KEY, ALPACA_BASE_URL, ALPACA_SECRET_KEY

logger = logging.getLogger("AlpacaClient")


class AlpacaPaperClient:
    """Institutional Client for Alpaca US Paper Trading."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        self.api_key = (api_key or ALPACA_API_KEY).strip()
        self.secret_key = (secret_key or ALPACA_SECRET_KEY).strip()
        base = (base_url or ALPACA_BASE_URL).strip().rstrip("/")
        if base.endswith("/v2"):
            base = base[:-3]
        self.base_url = base

    def is_configured(self) -> bool:
        """Returns True if both API key and secret key are present."""
        return bool(self.api_key and self.secret_key)

    def _headers(self) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": self.api_key,
            "APCA-API-SECRET-KEY": self.secret_key,
            "Content-Type": "application/json",
            "User-Agent": "AdversarialIQ/1.0"
        }

    def ping(self) -> Dict[str, Any]:
        """Tests connection to Alpaca Paper Trading endpoint and measures latency."""
        start = time.time()
        if not self.is_configured():
            return {
                "status": "UNCONFIGURED",
                "latency_ms": 0,
                "provider": "Alpaca Paper Trading",
                "message": "Alpaca API keys not set. Running in Local Paper Ledger mode ($10,000 base)."
            }

        url = f"{self.base_url}/v2/account"
        try:
            res = requests.get(url, headers=self._headers(), timeout=5)
            latency = int((time.time() - start) * 1000)
            if res.status_code == 200:
                data = res.json()
                return {
                    "status": "LIVE",
                    "latency_ms": latency,
                    "provider": "Alpaca Paper Trading",
                    "account_number": data.get("account_number", ""),
                    "status_text": data.get("status", "ACTIVE"),
                    "buying_power": float(data.get("buying_power", 0)),
                    "portfolio_value": float(data.get("portfolio_value", 0)),
                    "cash": float(data.get("cash", 0)),
                    "message": f"Connected to Alpaca Paper Desk ({latency}ms). Account: {data.get('account_number')}"
                }
            elif res.status_code in (401, 403):
                return {
                    "status": "DOWN",
                    "latency_ms": latency,
                    "provider": "Alpaca Paper Trading",
                    "error": f"Authentication failed (HTTP {res.status_code}). Please verify ALPACA_API_KEY and ALPACA_SECRET_KEY."
                }
            else:
                return {
                    "status": "DOWN",
                    "latency_ms": latency,
                    "provider": "Alpaca Paper Trading",
                    "error": f"HTTP {res.status_code}: {res.text[:120]}"
                }
        except Exception as e:
            return {
                "status": "DOWN",
                "latency_ms": int((time.time() - start) * 1000),
                "provider": "Alpaca Paper Trading",
                "error": f"Connection error: {str(e)}"
            }

    def get_account(self) -> Optional[Dict[str, Any]]:
        """Fetches live paper trading account details from Alpaca."""
        if not self.is_configured():
            return None
        url = f"{self.base_url}/v2/account"
        try:
            res = requests.get(url, headers=self._headers(), timeout=6)
            if res.status_code == 200:
                d = res.json()
                return {
                    "id": d.get("id"),
                    "account_number": d.get("account_number"),
                    "status": d.get("status"),
                    "currency": d.get("currency", "USD"),
                    "cash": float(d.get("cash", 0.0)),
                    "portfolio_value": float(d.get("portfolio_value", 0.0)),
                    "equity": float(d.get("equity", 0.0)),
                    "buying_power": float(d.get("buying_power", 0.0)),
                    "initial_margin": float(d.get("initial_margin", 0.0)),
                    "daytrade_count": int(d.get("daytrade_count", 0)),
                    "last_equity": float(d.get("last_equity", 0.0))
                }
        except Exception as e:
            logger.error(f"Alpaca get_account error: {e}")
        return None

    def get_positions(self) -> List[Dict[str, Any]]:
        """Fetches all open positions from Alpaca paper account."""
        if not self.is_configured():
            return []
        url = f"{self.base_url}/v2/positions"
        try:
            res = requests.get(url, headers=self._headers(), timeout=6)
            if res.status_code == 200:
                raw_positions = res.json()
                positions = []
                for p in raw_positions:
                    qty = int(float(p.get("qty", 0)))
                    avg_entry = float(p.get("avg_entry_price", 0.0))
                    cur_price = float(p.get("current_price", avg_entry))
                    mkt_val = float(p.get("market_value", qty * cur_price))
                    cost_basis = float(p.get("cost_basis", qty * avg_entry))
                    unrealized_pl = float(p.get("unrealized_pl", mkt_val - cost_basis))
                    unrealized_pct = float(p.get("unrealized_plpc", 0.0)) * 100

                    positions.append({
                        "symbol": p.get("symbol", "").upper(),
                        "quantity": qty,
                        "avg_price": round(avg_entry, 2),
                        "current_price": round(cur_price, 2),
                        "cost_basis": round(cost_basis, 2),
                        "current_value": round(mkt_val, 2),
                        "unrealized_pnl": round(unrealized_pl, 2),
                        "unrealized_pct": round(unrealized_pct, 2),
                        "status": "UP" if unrealized_pl >= 0 else "DOWN",
                        "side": p.get("side", "long")
                    })
                return positions
        except Exception as e:
            logger.error(f"Alpaca get_positions error: {e}")
        return []

    def get_orders(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Fetches recent orders from Alpaca paper account."""
        if not self.is_configured():
            return []
        url = f"{self.base_url}/v2/orders?status=all&limit={limit}&nested=true"
        try:
            res = requests.get(url, headers=self._headers(), timeout=6)
            if res.status_code == 200:
                raw_orders = res.json()
                orders = []
                for o in raw_orders:
                    filled_qty = int(float(o.get("filled_qty", 0) or o.get("qty", 0)))
                    price = float(o.get("filled_avg_price", 0.0) or o.get("limit_price", 0.0) or 0.0)
                    orders.append({
                        "id": o.get("id"),
                        "timestamp": o.get("submitted_at", "")[:19].replace("T", " "),
                        "type": o.get("side", "").upper(),
                        "symbol": o.get("symbol", "").upper(),
                        "quantity": filled_qty,
                        "price": round(price, 2),
                        "total": round(filled_qty * price, 2),
                        "order_type": o.get("type", "market").upper(),
                        "status": o.get("status", "filled").upper(),
                        "rationale": "Alpaca Paper Order"
                    })
                return orders
        except Exception as e:
            logger.error(f"Alpaca get_orders error: {e}")
        return []

    def place_order(
        self,
        symbol: str,
        quantity: int,
        side: str,  # "buy" or "sell"
        order_type: str = "market",
        limit_price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        time_in_force: str = "day"
    ) -> Dict[str, Any]:
        """
        Submits order to Alpaca Paper Trading.
        If BUY and stop_loss/take_profit provided, submits mandatory bracket order.
        """
        if not self.is_configured():
            raise ValueError("Alpaca API credentials not configured in environment or settings.")

        url = f"{self.base_url}/v2/orders"
        body = {
            "symbol": symbol.upper(),
            "qty": int(quantity),
            "side": side.lower(),
            "type": order_type.lower(),
            "time_in_force": time_in_force.lower()
        }

        if order_type.lower() == "limit" and limit_price:
            body["limit_price"] = round(float(limit_price), 2)

        # Mandatory Bracket Order handling
        if (stop_loss or take_profit) and side.lower() == "buy":
            body["order_class"] = "bracket"
            if stop_loss:
                body["stop_loss"] = {"stop_price": round(float(stop_loss), 2)}
            if take_profit:
                body["take_profit"] = {"limit_price": round(float(take_profit), 2)}

        try:
            res = requests.post(url, headers=self._headers(), json=body, timeout=8)
            if res.status_code in (200, 201):
                order_data = res.json()
                fill_price = float(order_data.get("filled_avg_price", 0.0) or order_data.get("limit_price", 0.0) or 0.0)
                return {
                    "status": "SUCCESS",
                    "trade": {
                        "id": order_data.get("id"),
                        "timestamp": order_data.get("created_at", "")[:19].replace("T", " "),
                        "type": side.upper(),
                        "symbol": symbol.upper(),
                        "quantity": int(quantity),
                        "price": fill_price,
                        "total": round(int(quantity) * fill_price, 2),
                        "order_type": order_type.upper(),
                        "alpaca_order_id": order_data.get("id"),
                        "status": order_data.get("status", "accepted").upper(),
                        "rationale": "Alpaca Paper Desk Routing",
                        "bracket": {
                            "stop_loss": stop_loss,
                            "take_profit": take_profit,
                            "order_class": "bracket" if (stop_loss or take_profit) else "simple"
                        }
                    },
                    "message": f"Successfully routed {side.upper()} order for {quantity} shares of {symbol.upper()} to Alpaca Paper Desk with automated bracket protection."
                }
            else:
                error_detail = res.text
                try:
                    error_detail = res.json().get("message", res.text)
                except Exception:
                    pass
                raise ValueError(f"Alpaca Order Rejected (HTTP {res.status_code}): {error_detail}")
        except requests.RequestException as e:
            raise ValueError(f"Failed to communicate with Alpaca Paper API: {str(e)}")
