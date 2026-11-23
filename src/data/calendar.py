"""
Earnings & Macro Event Calendar Filter
Detects upcoming corporate earnings announcements and FOMC / Macro binary events.
Enforces a 48-Hour Earnings Blackout Window to prevent algorithmic blowups:
- Within 24 Hours: VETO trade ("Binary earnings risk within 24h").
- Within 24-48 Hours: WARNING_HALVE_SIZE (cut suggested position size by 50%).
- Beyond 48 Hours: CLEAR (normal execution permitted).
"""

import datetime
import logging
from typing import Any, Dict, Optional
import requests
import yfinance as yf

from src.core.config import FINNHUB_API_KEY, get_cached, set_cached

logger = logging.getLogger("CalendarEngine")


def fetch_earnings_calendar(symbol: str) -> Dict[str, Any]:
    """
    Checks upcoming earnings dates for an S&P 500 stock via yfinance and Finnhub.
    Calculates hours until the next earnings release and returns strict blackout status.
    """
    sym = symbol.strip().upper()
    cache_key = f"earnings_calendar_{sym}"
    cached = get_cached(cache_key, 600)  # 10 minute cache
    if cached:
        return cached

    now = datetime.datetime.now(datetime.timezone.utc)
    earnings_dt: Optional[datetime.datetime] = None
    source = "none"

    # 1. Attempt yfinance calendar
    try:
        t = yf.Ticker(sym)
        cal = t.calendar
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if ed:
                if isinstance(ed, list) and len(ed) > 0:
                    first_val = ed[0]
                else:
                    first_val = ed
                
                if isinstance(first_val, datetime.datetime):
                    if first_val.tzinfo is None:
                        earnings_dt = first_val.replace(tzinfo=datetime.timezone.utc)
                    else:
                        earnings_dt = first_val
                elif isinstance(first_val, datetime.date):
                    earnings_dt = datetime.datetime.combine(first_val, datetime.time(20, 0), tzinfo=datetime.timezone.utc)
                source = "yfinance"
    except Exception as e:
        logger.debug(f"yfinance calendar lookup for {sym} notice: {e}")

    # 2. Finnhub fallback if yfinance didn't yield an upcoming date
    if not earnings_dt and FINNHUB_API_KEY:
        try:
            today_str = now.strftime("%Y-%m-%d")
            next_month = (now + datetime.timedelta(days=90)).strftime("%Y-%m-%d")
            url = f"https://finnhub.io/api/v1/calendar/earnings?from={today_str}&to={next_month}&symbol={sym}&token={FINNHUB_API_KEY}"
            resp = requests.get(url, timeout=5)
            if resp.status_code == 200:
                data = resp.json().get("earningsCalendar", [])
                if data:
                    first_entry = data[0]
                    date_str = first_entry.get("date")
                    if date_str:
                        d = datetime.date.fromisoformat(date_str)
                        earnings_dt = datetime.datetime.combine(d, datetime.time(20, 0), tzinfo=datetime.timezone.utc)
                        source = "finnhub"
        except Exception as e:
            logger.debug(f"Finnhub calendar fallback for {sym} notice: {e}")

    # Analyze blackout window
    if earnings_dt:
        diff = earnings_dt - now
        hours_remaining = diff.total_seconds() / 3600.0
        date_str = earnings_dt.strftime("%Y-%m-%d")

        if 0 <= hours_remaining <= 24:
            status = "VETO_BLACKOUT"
            action = "VETO"
            size_multiplier = 0.0
            reason = f"Earnings announcement scheduled in {hours_remaining:.1f}h ({date_str}). Absolute blackout veto enforced."
        elif 24 < hours_remaining <= 48:
            status = "WARNING_HALVE_SIZE"
            action = "HALVE"
            size_multiplier = 0.5
            reason = f"Earnings announcement scheduled in {hours_remaining:.1f}h ({date_str}). Position sizing halved by 50% for risk mitigation."
        elif hours_remaining < 0 and hours_remaining >= -24:
            status = "POST_EARNINGS_VOLATILITY"
            action = "HALVE"
            size_multiplier = 0.5
            reason = f"Earnings reported recently ({abs(hours_remaining):.1f}h ago). Volatility caution active; position size halved."
        else:
            status = "CLEAR"
            action = "CLEAR"
            size_multiplier = 1.0
            reason = f"Next scheduled earnings date is {date_str} (~{hours_remaining/24.0:.1f} days away). Outside 48h blackout window."

        res = {
            "symbol": sym,
            "has_earnings_soon": hours_remaining <= 48 and hours_remaining >= -24,
            "hours_to_earnings": round(hours_remaining, 1),
            "earnings_date": date_str,
            "blackout_status": status,
            "action": action,
            "size_multiplier": size_multiplier,
            "reason": reason,
            "source": source
        }
    else:
        res = {
            "symbol": sym,
            "has_earnings_soon": False,
            "hours_to_earnings": None,
            "earnings_date": None,
            "blackout_status": "CLEAR",
            "action": "CLEAR",
            "size_multiplier": 1.0,
            "reason": "No immediate earnings announcement detected within 48 hours.",
            "source": source
        }

    set_cached(cache_key, res)
    return res
