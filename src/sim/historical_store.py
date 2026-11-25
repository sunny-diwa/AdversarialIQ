"""
Point-in-Time Historical Market, News, Macro, Earnings & 4D Ecosystem Store.
Enforces strict `<= as_of_dt` causal filtering (zero lookahead bias) across:
- Daily OHLCV (1y history for SMA20/SMA50/SMA200/ATR14 anchoring)
- Intraday 5m prepost=True bars (pre-market 04:00-09:29 + regular session 09:30-16:00 NY time)
  → yfinance supports up to 60 days of 5m history (period="1mo" with prepost=True)
  → 5m bars drive RSI-14, MACD(12,26,9), ATR-14, VWAP, Bollinger Bands, Stochastic, Williams %R
  → Daily bars remain as the higher-timeframe structural anchor (SMA20/50/200, Daily ATR, Daily RSI)
- Finnhub Company News (chunked daily to bypass 250-article truncation cap)
- FRED Historical Macro Series (DGS10, DGS2, VIXCLS, CPIAUCSL, FEDFUNDS)
- Historical Earnings Calendar (48h blackout windows)
- Live Point-in-Time A-CIS 4D Ecosystem & Start-of-Day Catalyst Scores
"""

from datetime import datetime, date, time as dt_time, timedelta
import json
import logging
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

from src.core.config import DATA_DIR, FINNHUB_API_KEY, FRED_API_KEY, SP500_MAP
from src.data.ecosystem import CURATED_ECOSYSTEMS, fetch_company_ecosystem
from src.data.market import compute_indicators, get_shares_outstanding
from src.data.news import calculate_sentiment, tag_catalysts, _clean_rss_text
from src.data.sec_edgar import fetch_insider_and_13f_activity, fetch_sec_filings

logger = logging.getLogger("SimHistoricalStore")
NY_TZ = ZoneInfo("America/New_York")
UTC_TZ = ZoneInfo("UTC")

SIM_CACHE_DIR = DATA_DIR / "sim_cache"


class HistoricalMarketStore:
    """
    Zero-lookahead historical data & scoring engine cached cleanly on disk.
    """

    def __init__(self, symbols: List[str], cache_dir: Optional[Path] = None):
        self.symbols = [s.strip().upper() for s in symbols if s.strip()]
        self.cache_dir = cache_dir or SIM_CACHE_DIR
        (self.cache_dir / "daily").mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "intraday").mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "news").mkdir(parents=True, exist_ok=True)
        (self.cache_dir / "fundamentals").mkdir(parents=True, exist_ok=True)

        self.daily_dfs: Dict[str, pd.DataFrame] = {}
        self.intraday_dfs: Dict[str, pd.DataFrame] = {}
        self.news_by_sym: Dict[str, List[Dict[str, Any]]] = {}
        self.sec_by_sym: Dict[str, Dict[str, Any]] = {}
        self.insider_by_sym: Dict[str, Dict[str, Any]] = {}
        self.macro_df: pd.DataFrame = pd.DataFrame()
        self.earnings_events: Dict[str, List[datetime]] = {}
        self._dependency_symbols: List[str] = []

    def _collect_dependency_symbols(self) -> List[str]:
        deps = set(self.symbols)
        deps.add("SPY")
        for sym in self.symbols:
            if sym in CURATED_ECOSYSTEMS:
                eco = CURATED_ECOSYSTEMS[sym]
                for group in ("upstream_suppliers", "downstream_customers", "competitors"):
                    for item in eco.get(group, []):
                        dsym = item.get("symbol", "").strip().upper()
                        # Strictly accept only real US equity tickers (1-5 uppercase letters)
                        if dsym and dsym.isalpha() and 1 <= len(dsym) <= 5 and dsym != "CRWV" and not dsym.endswith(".KS") and not dsym.endswith(".TW"):
                            deps.add(dsym)
        return sorted(list(deps))

    def prepare_universe(self, force_refresh: bool = False):
        """Pre-fetches and caches all OHLCV, Finnhub news, FRED macro, and earnings data."""
        self._dependency_symbols = self._collect_dependency_symbols()
        logger.info(
            f"Preparing historical store for {len(self.symbols)} primary symbols "
            f"({len(self._dependency_symbols)} total incl. ecosystem dependencies)..."
        )

        # 1. Daily + 5m prepost=True candles
        for sym in self._dependency_symbols:
            self._load_or_fetch_daily(sym, force_refresh=force_refresh)
            self._load_or_fetch_intraday(sym, force_refresh=force_refresh)

        # Determine simulation window from SPY 5m candles
        trading_days = self.get_trading_days()
        if not trading_days:
            raise RuntimeError("No historical trading days found in SPY 5m intraday data.")
        start_d = trading_days[0] - timedelta(days=5)
        end_d = trading_days[-1]

        # 2. Historical Finnhub news for primary symbols & top ecosystem nodes
        news_syms = list(dict.fromkeys(self.symbols + [
            "TSM", "ASML", "MU", "AMD", "AVGO", "INTC", "QCOM", "ORCL"
        ]))
        for sym in news_syms:
            self._load_or_fetch_finnhub_news(sym, start_d, end_d, force_refresh=force_refresh)

        # 3. Historical FRED macro series
        self._load_or_fetch_macro(start_d - timedelta(days=30), end_d, force_refresh=force_refresh)

        # 4. Historical Earnings Calendar
        self._load_or_fetch_earnings(start_d - timedelta(days=20), end_d + timedelta(days=20), force_refresh=force_refresh)

        # 5. Fundamentals (SEC EDGAR & Insider baseline per primary symbol)
        for sym in self.symbols:
            self._load_or_fetch_fundamentals(sym, force_refresh=force_refresh)

        logger.info(
            f"Historical store ready! Trading window: {trading_days[0]} to {trading_days[-1]} "
            f"({len(trading_days)} sessions)."
        )

    def _load_or_fetch_fundamentals(self, sym: str, force_refresh: bool = False):
        fpath = self.cache_dir / "fundamentals" / f"{sym}.json"
        if fpath.exists() and not force_refresh:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.sec_by_sym[sym] = data.get("sec", {})
                self.insider_by_sym[sym] = data.get("insider", {})
                return
            except Exception:
                pass
        sec = fetch_sec_filings(sym)
        ins = fetch_insider_and_13f_activity(sym)
        self.sec_by_sym[sym] = sec
        self.insider_by_sym[sym] = ins
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump({"sec": sec, "insider": ins}, f, indent=2)

    def _load_or_fetch_daily(self, sym: str, force_refresh: bool = False):
        fpath = self.cache_dir / "daily" / f"{sym}.csv"
        if fpath.exists() and not force_refresh:
            try:
                df = pd.read_csv(fpath, index_col=0)
                df.index = pd.to_datetime(df.index).tz_localize(None)
                if not df.empty:
                    self.daily_dfs[sym] = df.sort_index()
                    return
            except Exception:
                pass

        try:
            df = yf.Ticker(sym).history(period="1y", interval="1d")
            if df is not None and not df.empty:
                df.index = pd.to_datetime(df.index).tz_localize(None)
                df = compute_indicators(df)
                df.to_csv(fpath)
                self.daily_dfs[sym] = df
        except Exception as e:
            logger.warning(f"Failed daily history fetch for {sym}: {e}")

    def _load_or_fetch_intraday(self, sym: str, force_refresh: bool = False):
        """
        Fetches and caches 5-minute OHLCV bars with premarket (prepost=True).
        yfinance supports up to 60 days of 5m data, so period='1mo' is safe.
        5m bars drive all intraday technical indicators (RSI-14, MACD, ATR-14, VWAP, BB, Stoch).
        """
        fpath = self.cache_dir / "intraday" / f"{sym}_5m.csv"
        # Also migrate any old 30m cache: if 5m file doesn't exist but 30m does, skip 30m (don't load it)
        if fpath.exists() and not force_refresh:
            try:
                df = pd.read_csv(fpath, index_col=0)
                if not df.empty:
                    # Parse mixed DST offsets cleanly via UTC then convert to NY_TZ
                    df.index = pd.to_datetime(df.index, utc=True).tz_convert(NY_TZ)
                    self.intraday_dfs[sym] = df.sort_index()
                    return
            except Exception:
                pass

        try:
            df = yf.Ticker(sym).history(period="1mo", interval="5m", prepost=True)
            if df is not None and not df.empty:
                if df.index.tz is None:
                    df.index = pd.to_datetime(df.index).tz_localize(NY_TZ)
                else:
                    df.index = df.index.tz_convert(NY_TZ)
                df = df.sort_index()
                df.to_csv(fpath)
                self.intraday_dfs[sym] = df
                logger.info(f"  Cached {len(df)} 5m bars for {sym} ({df.index[0].date()} → {df.index[-1].date()})")
        except Exception as e:
            logger.warning(f"Failed 5m intraday fetch for {sym}: {e}")

    def _load_or_fetch_finnhub_news(
        self, sym: str, start_d: date, end_d: date, force_refresh: bool = False
    ):
        fpath = self.cache_dir / "news" / f"{sym}.json"
        if fpath.exists() and not force_refresh:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    items = json.load(f)
                if isinstance(items, list) and len(items) > 0:
                    self.news_by_sym[sym] = items
                    return
            except Exception:
                pass

        if not FINNHUB_API_KEY:
            self.news_by_sym[sym] = []
            return

        logger.info(f"Fetching daily-chunked Finnhub news archive for {sym} ({start_d}..{end_d})...")
        all_articles: List[Dict[str, Any]] = []
        seen_keys = set()

        # Fetch in 2-day sliding windows so busy tickers never clip at Finnhub's ~250 cap
        cur = start_d
        while cur <= end_d:
            nxt = min(end_d, cur + timedelta(days=1))
            url = (
                f"https://finnhub.io/api/v1/company-news?"
                f"symbol={sym}&from={cur.strftime('%Y-%m-%d')}&to={nxt.strftime('%Y-%m-%d')}&token={FINNHUB_API_KEY}"
            )
            retries = 2
            for attempt in range(retries + 1):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "AdversarialIQ/1.0"})
                    with urllib.request.urlopen(req, timeout=8) as resp:
                        raw = json.loads(resp.read().decode("utf-8"))
                    if isinstance(raw, list):
                        for item in raw:
                            title = _clean_rss_text(item.get("headline", ""))
                            if not title:
                                continue
                            norm = re.sub(r"[^\w\s]", "", title.lower())
                            if norm in seen_keys:
                                continue
                            seen_keys.add(norm)
                            summary = _clean_rss_text(item.get("summary", "")) or title
                            comb = f"{title}. {summary}"
                            sent = calculate_sentiment(comb)
                            cats = tag_catalysts(comb)
                            unix_ts = int(item.get("datetime", 0) or 0)
                            if unix_ts <= 0:
                                continue
                            dt_ny = datetime.fromtimestamp(unix_ts, tz=UTC_TZ).astimezone(NY_TZ)
                            all_articles.append({
                                "id": str(item.get("id", f"fh_{sym}_{len(all_articles)}")),
                                "title": title,
                                "headline": title,
                                "summary": summary[:280] + ("..." if len(summary) > 280 else ""),
                                "source": item.get("source", "Finnhub"),
                                "url": item.get("url", ""),
                                "unix_ts": unix_ts,
                                "timestamp": dt_ny.strftime("%Y-%m-%d %H:%M"),
                                "sentiment": sent["label"],
                                "sentiment_score": sent["score"],
                                "catalysts": cats
                            })
                    break
                except urllib.error.HTTPError as he:
                    if he.code == 429 and attempt < retries:
                        logger.debug(f"Finnhub 429 for {sym}, cooling down 5s...")
                        time.sleep(5.0)
                    else:
                        logger.debug(f"Finnhub news HTTP notice for {sym} ({cur}): {he}")
                        break
                except Exception as e:
                    logger.debug(f"Finnhub news error for {sym} ({cur}): {e}")
                    break

            time.sleep(1.05)  # Polite 57 req/min staying safely below Finnhub 60/min cap
            cur = nxt + timedelta(days=1)

        all_articles.sort(key=lambda x: x["unix_ts"], reverse=True)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(all_articles, f, indent=2)
        self.news_by_sym[sym] = all_articles
        logger.info(f"  Cached {len(all_articles)} unique Finnhub articles for {sym}.")

    def _load_or_fetch_macro(self, start_d: date, end_d: date, force_refresh: bool = False):
        fpath = self.cache_dir / "macro_series.csv"
        if fpath.exists() and not force_refresh:
            try:
                df = pd.read_csv(fpath, index_col=0, parse_dates=True)
                if not df.empty:
                    self.macro_df = df.sort_index()
                    return
            except Exception:
                pass

        series_data = {}
        if FRED_API_KEY:
            try:
                from fredapi import Fred
                fred = Fred(api_key=FRED_API_KEY)
                obs_start = start_d.strftime("%Y-%m-%d")
                for sid in ["DGS10", "DGS2", "VIXCLS", "CPIAUCSL", "FEDFUNDS"]:
                    try:
                        s = fred.get_series(sid, observation_start=obs_start)
                        if s is not None and not s.empty:
                            s.index = pd.to_datetime(s.index).tz_localize(None)
                            series_data[sid] = s.dropna()
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"FRED macro series error: {e}")

        if series_data:
            df = pd.DataFrame(series_data).sort_index().ffill().bfill()
            df.to_csv(fpath)
            self.macro_df = df
        else:
            self.macro_df = pd.DataFrame()

    def _load_or_fetch_earnings(self, start_d: date, end_d: date, force_refresh: bool = False):
        fpath = self.cache_dir / "earnings_calendar.json"
        if fpath.exists() and not force_refresh:
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for sym, dlist in raw.items():
                    self.earnings_events[sym] = [datetime.fromisoformat(d) for d in dlist]
                return
            except Exception:
                pass

        events: Dict[str, List[str]] = {}
        for sym in self.symbols:
            dts: List[str] = []
            if FINNHUB_API_KEY:
                try:
                    url = (
                        f"https://finnhub.io/api/v1/calendar/earnings?"
                        f"from={start_d.strftime('%Y-%m-%d')}&to={end_d.strftime('%Y-%m-%d')}&symbol={sym}&token={FINNHUB_API_KEY}"
                    )
                    res = requests.get(url, timeout=6)
                    if res.status_code == 200:
                        for row in res.json().get("earningsCalendar", []):
                            d_str = row.get("date")
                            hour = (row.get("hour") or "amc").lower()
                            t_str = "07:30:00" if hour == "bmo" else "16:05:00"
                            if d_str:
                                dts.append(f"{d_str}T{t_str}-05:00")
                    time.sleep(0.4)
                except Exception:
                    pass
            events[sym] = sorted(list(set(dts)))
            self.earnings_events[sym] = [datetime.fromisoformat(d) for d in events[sym]]

        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(events, f, indent=2)

    def get_trading_days(self, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[date]:
        """Returns ordered list of regular market trading days found in SPY 5m data."""
        spy_df = self.intraday_dfs.get("SPY")
        if spy_df is None or spy_df.empty:
            return []

        # Keep days that actually have regular cash session bars (09:30 - 15:30 NY time)
        reg = spy_df[(spy_df.index.time >= dt_time(9, 30)) & (spy_df.index.time < dt_time(16, 0))]
        days = sorted(list(set(reg.index.date)))

        # Require at least 12 regular 5m bars in the session (handles holidays/partial days safely)
        # A full 6.5h session = 78 bars; 12 is a loose minimum (~1h of data)
        valid_days = []
        for d in days:
            cnt = len(reg[reg.index.date == d])
            if cnt >= 12:
                if start_date and d.strftime("%Y-%m-%d") < start_date:
                    continue
                if end_date and d.strftime("%Y-%m-%d") > end_date:
                    continue
                valid_days.append(d)
        return valid_days

    def get_hourly_checkpoints(self, trade_day: date) -> List[datetime]:
        """
        Returns the 7 regular cash-session hourly decision checkpoints for `trade_day`:
        09:30, 10:30, 11:30, 12:30, 13:30, 14:30, 15:30 NY time (where SPY 5m data exists).
        """
        spy_df = self.intraday_dfs.get("SPY")
        checkpoints = []
        candidates = [
            dt_time(9, 30), dt_time(10, 30), dt_time(11, 30),
            dt_time(12, 30), dt_time(13, 30), dt_time(14, 30), dt_time(15, 30)
        ]
        if spy_df is None or spy_df.empty:
            return [datetime.combine(trade_day, t, tzinfo=NY_TZ) for t in candidates]

        day_bars = spy_df[spy_df.index.date == trade_day]
        max_bar_time = day_bars.index.max() if not day_bars.empty else None

        for t in candidates:
            dt_cp = datetime.combine(trade_day, t, tzinfo=NY_TZ)
            # Only schedule checkpoint if SPY actually traded at/after that timestamp
            if max_bar_time is not None and dt_cp <= max_bar_time + timedelta(minutes=5):
                # Ensure a 5m bar exists at or after this checkpoint
                has_bar = not day_bars[day_bars.index >= dt_cp].empty
                if has_bar:
                    checkpoints.append(dt_cp)
        return checkpoints

    def get_bar_window(self, sym: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
        """Returns 5m bars for [start_dt, end_dt) to check intrabar High/Low bracket hits with high precision."""
        df = self.intraday_dfs.get(sym)
        if df is None or df.empty:
            return pd.DataFrame()
        return df[(df.index >= start_dt) & (df.index < end_dt)]

    def get_execution_fill_price(self, sym: str, decision_dt: datetime) -> Optional[float]:
        """
        Causal fill price: decision made at `decision_dt` executes at the Open of the bar
        starting at `decision_dt` (or the closest subsequent bar's Open).
        """
        df = self.intraday_dfs.get(sym)
        if df is None or df.empty:
            return None
        after = df[df.index >= decision_dt]
        if not after.empty:
            return round(float(after.iloc[0]["Open"]), 2)
        before = df[df.index < decision_dt]
        if not before.empty:
            return round(float(before.iloc[-1]["Close"]), 2)
        return None

    def get_mark_to_market_price(self, sym: str, as_of_dt: datetime) -> float:
        """Latest completed close <= as_of_dt."""
        q = self.get_quote_as_of(sym, as_of_dt)
        return float(q.get("price") or 100.0)

    def get_quote_as_of(self, sym: str, as_of_dt: datetime) -> Dict[str, Any]:
        """Strictly causal quote as of `as_of_dt` using only bars strictly completed BEFORE `as_of_dt`."""
        sym = sym.strip().upper()
        meta = SP500_MAP.get(sym, {"name": sym, "sector": "Unknown", "sub_industry": ""})
        d_df = self.daily_dfs.get(sym)
        i_df = self.intraday_dfs.get(sym)

        cur_day = as_of_dt.date()
        is_premarket = as_of_dt.time() < dt_time(9, 30)

        # Previous trading day daily bar strictly BEFORE cur_day
        prev_close = 100.0
        avg_vol_10d = 20_000_000
        year_high = 0.0
        year_low = 0.0
        if d_df is not None and not d_df.empty:
            prior_daily = d_df[d_df.index.date < cur_day]
            if not prior_daily.empty:
                prev_close = float(prior_daily.iloc[-1]["Close"])
                avg_vol_10d = int(prior_daily.tail(10)["Volume"].mean())
                year_high = round(float(prior_daily["High"].max()), 2)
                year_low = round(float(prior_daily["Low"].min()), 2)

        # Completed 30m bars strictly BEFORE as_of_dt (note: bar stamped 10:00 covers 10:00-10:30, completed at 10:30)
        price = prev_close
        open_p = prev_close
        day_high = prev_close
        day_low = prev_close
        session_vol = 0
        premarket_gap_pct = 0.0

        if i_df is not None and not i_df.empty:
            bars_before = i_df[i_df.index < as_of_dt]
            if not bars_before.empty:
                price = float(bars_before.iloc[-1]["Close"])
                today_bars = bars_before[bars_before.index.date == cur_day]
                if not today_bars.empty:
                    if is_premarket:
                        premarket_gap_pct = round(((price - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
                        open_p = float(today_bars.iloc[0]["Open"])
                        day_high = float(today_bars["High"].max())
                        day_low = float(today_bars["Low"].min())
                        session_vol = int(today_bars["Volume"].sum())
                    else:
                        reg_today = today_bars[today_bars.index.time >= dt_time(9, 30)]
                        pre_today = today_bars[today_bars.index.time < dt_time(9, 30)]
                        if not reg_today.empty:
                            open_p = float(reg_today.iloc[0]["Open"])
                            day_high = float(reg_today["High"].max())
                            day_low = float(reg_today["Low"].min())
                            session_vol = int(reg_today["Volume"].sum())
                        elif not pre_today.empty:
                            # At 09:30 exact open before 09:30 bar finishes, use last pre-market close
                            open_p = price
                            day_high = float(pre_today["High"].max())
                            day_low = float(pre_today["Low"].min())
                            session_vol = int(pre_today["Volume"].sum())
                        if pre_today is not None and not pre_today.empty:
                            premarket_gap_pct = round(((float(pre_today.iloc[-1]["Close"]) - prev_close) / prev_close) * 100.0, 2) if prev_close > 0 else 0.0
                        elif open_p > 0 and prev_close > 0:
                            premarket_gap_pct = round(((open_p - prev_close) / prev_close) * 100.0, 2)

        change = price - prev_close
        pct_change = (change / prev_close * 100.0) if prev_close > 0 else 0.0
        mcap = int(price * get_shares_outstanding(sym, price))

        return {
            "symbol": sym,
            "name": meta.get("name", sym),
            "sector": meta.get("sector", "Unknown"),
            "sub_industry": meta.get("sub_industry", ""),
            "price": round(price, 2),
            "prev_close": round(prev_close, 2),
            "open": round(open_p, 2),
            "day_high": round(day_high, 2),
            "day_low": round(day_low, 2),
            "change": round(change, 2),
            "pct_change": round(pct_change, 2),
            "premarket_gap_pct": premarket_gap_pct,
            "volume": session_vol,
            "avg_volume_10d": max(1, avg_vol_10d),
            "year_high": year_high,
            "year_low": year_low,
            "market_cap": mcap,
            "timestamp": as_of_dt.strftime("%Y-%m-%d %H:%M %Z")
        }

    def get_technicals_as_of(self, sym: str, as_of_dt: datetime) -> Dict[str, Any]:
        """
        Computes strict causal technical indicators as of `as_of_dt`:
        - DAILY anchor: SMA20, SMA50, SMA200, Daily ATR-14, Daily RSI (from prior closed daily bars)
        - 5-MINUTE intraday: RSI-14, MACD(12,26,9), ATR-14, VWAP (session), Bollinger Bands(20,2),
          Stochastic %K, Williams %R, 1-bar return, 3-bar return, intraday volume ratio
          All strictly using 5m bars with timestamps < as_of_dt.
        """
        sym = sym.strip().upper()
        q = self.get_quote_as_of(sym, as_of_dt)
        price = float(q["price"])
        cur_day = as_of_dt.date()

        # 1. Daily structural indicators from days < cur_day (higher-timeframe anchor)
        d_df = self.daily_dfs.get(sym)
        sma20_d = sma50_d = sma200_d = price
        atr_daily = max(round(price * 0.025, 2), 0.5)
        rsi_daily = 50.0
        prior_5d_pct = 0.0
        if d_df is not None and not d_df.empty:
            prior = d_df[d_df.index.date < cur_day]
            if not prior.empty:
                last_d = prior.iloc[-1]
                sma20_d = float(last_d.get("SMA20", price) or price)
                sma50_d = float(last_d.get("SMA50", price) or price)
                sma200_d = float(last_d.get("SMA200", price) or price)
                atr_daily = float(last_d.get("ATR", atr_daily) or atr_daily)
                rsi_daily = float(last_d.get("RSI", 50.0) or 50.0)
                if len(prior) >= 6:
                    c5 = float(prior.iloc[-6]["Close"])
                    prior_5d_pct = round(((float(last_d["Close"]) - c5) / c5) * 100.0, 2) if c5 > 0 else 0.0

        # 2. 5-minute intraday bars strictly < as_of_dt (regular session bars only for oscillators)
        # We use regular session bars to avoid pre-market thin wicks distorting RSI/MACD
        i_df = self.intraday_dfs.get(sym)
        rsi_5m = rsi_daily         # fall back to daily RSI if insufficient 5m data
        macd = macd_sig = macd_hist = 0.0
        atr_5m = round(atr_daily * 0.25, 2)   # 5m ATR is ~¼ of daily ATR as rough prior
        bb_upper = round(price * 1.015, 2)
        bb_lower = round(price * 0.985, 2)
        stoch_k = 50.0
        williams_r = -50.0
        vwap_today = price
        ret_1bar_pct = 0.0    # return over last 5-min bar
        ret_12bar_pct = 0.0   # return over last ~1h (12 × 5m)
        ret_36bar_pct = 0.0   # return over last ~3h (36 × 5m)
        vol_ratio_5m = 1.0    # current 5m bar volume vs rolling 20-bar mean

        if i_df is not None and not i_df.empty:
            # Regular session bars strictly before as_of_dt
            bars_hist = i_df[
                (i_df.index < as_of_dt) &
                (i_df.index.time >= dt_time(9, 30)) &
                (i_df.index.time < dt_time(16, 0))
            ]

            # Need at least 26 bars for MACD to be stable (26 EMA period)
            if len(bars_hist) >= 26:
                bars_hist = compute_indicators(bars_hist)
                row = bars_hist.iloc[-1]
                rsi_5m   = float(row.get("RSI", rsi_daily) or rsi_daily)
                macd     = float(row.get("MACD", 0.0) or 0.0)
                macd_sig = float(row.get("MACD_Signal", 0.0) or 0.0)
                macd_hist = float(row.get("MACD_Hist", 0.0) or 0.0)
                atr_5m   = float(row.get("ATR", atr_5m) or atr_5m)
                bb_upper = float(row.get("BB_Upper", bb_upper) or bb_upper)
                bb_lower = float(row.get("BB_Lower", bb_lower) or bb_lower)
                stoch_k  = float(row.get("STOCH_K", 50.0) or 50.0)
                williams_r = float(row.get("WILLIAMS_R", -50.0) or -50.0)

                # Short-term returns on 5m candle closes
                if len(bars_hist) >= 2:
                    prev_1bar = float(bars_hist.iloc[-2]["Close"])
                    ret_1bar_pct = round(((price - prev_1bar) / prev_1bar) * 100.0, 2) if prev_1bar > 0 else 0.0
                if len(bars_hist) >= 13:
                    prev_12bar = float(bars_hist.iloc[-13]["Close"])
                    ret_12bar_pct = round(((price - prev_12bar) / prev_12bar) * 100.0, 2) if prev_12bar > 0 else 0.0
                if len(bars_hist) >= 37:
                    prev_36bar = float(bars_hist.iloc[-37]["Close"])
                    ret_36bar_pct = round(((price - prev_36bar) / prev_36bar) * 100.0, 2) if prev_36bar > 0 else 0.0

                # 5m volume ratio: current bar vol vs rolling 20-bar mean (excluding current)
                if len(bars_hist) > 1:
                    avg_v = float(bars_hist.iloc[:-1].tail(20)["Volume"].mean())
                    cur_v = float(row.get("Volume", 0))
                    if avg_v > 0 and cur_v > 0:
                        vol_ratio_5m = round(cur_v / avg_v, 2)

            # Session VWAP: strictly today's regular session 5m bars < as_of_dt
            today_reg = bars_hist[bars_hist.index.date == cur_day] if not bars_hist.empty else pd.DataFrame()
            if not today_reg.empty and today_reg["Volume"].sum() > 0:
                typ = (today_reg["High"] + today_reg["Low"] + today_reg["Close"]) / 3.0
                vwap_today = round(float((typ * today_reg["Volume"]).sum() / today_reg["Volume"].sum()), 2)

        return {
            "symbol": sym,
            "price": round(price, 2),
            "prev_close": q["prev_close"],
            "pct_change": q["pct_change"],
            "premarket_gap_pct": q["premarket_gap_pct"],
            # 5-minute short-term returns
            "ret_1bar_pct": ret_1bar_pct,     # last 5m candle return
            "ret_1h_pct": ret_12bar_pct,      # ~1h return (12 × 5m), aliased for prompt compatibility
            "ret_3h_pct": ret_36bar_pct,      # ~3h return (36 × 5m), aliased for prompt compatibility
            "ret_12bar_pct": ret_12bar_pct,
            "ret_36bar_pct": ret_36bar_pct,
            "prior_5d_pct": prior_5d_pct,
            # ATR at both timeframes
            "atr": round(atr_daily, 2),       # Daily ATR (structural stop sizing)
            "atr_5m": round(atr_5m, 2),       # 5m ATR (intrabar stop precision)
            "atr_1h": round(atr_5m * 2.5, 2), # Rough 1h ATR proxy (aliased for prompt compat)
            # Oscillators (5m candles)
            "rsi": round(rsi_5m, 2),          # 5m RSI-14
            "rsi_daily": round(rsi_daily, 2), # Daily RSI-14 (structural context)
            "macd": round(macd, 2),
            "macd_signal": round(macd_sig, 2),
            "macd_hist": round(macd_hist, 2),
            # Daily SMAs (structural anchor)
            "sma20": round(sma20_d, 2),
            "sma50": round(sma50_d, 2),
            "sma200": round(sma200_d, 2),
            # 5-minute VWAP & Bands
            "vwap": round(vwap_today, 2),
            "above_vwap": price >= vwap_today,
            "bb_upper": round(bb_upper, 2),
            "bb_lower": round(bb_lower, 2),
            # Momentum oscillators (5m)
            "stoch_k": round(stoch_k, 2),
            "williams_r": round(williams_r, 2),
            "vol_ratio_intraday": vol_ratio_5m,
            # Metadata
            "bar_timeframe": "5m",
        }

    def get_news_as_of(self, sym: str, as_of_dt: datetime, lookback_hours: int = 48, limit: int = 8) -> Dict[str, Any]:
        """Strictly causal real Finnhub news published in [as_of_dt - lookback_hours, as_of_dt]."""
        sym = sym.strip().upper()
        cutoff_hi = int(as_of_dt.timestamp())
        cutoff_lo = int((as_of_dt - timedelta(hours=lookback_hours)).timestamp())

        meta = SP500_MAP.get(sym, {"name": sym})
        comp_words = [w.lower() for w in re.findall(r"[A-Za-z]+", meta.get("name", sym)) if len(w) > 3 and w.lower() not in ("corp", "corporation", "inc", "platforms", "holdings", "group")]
        comp_words.append(sym.lower())

        raw_list = self.news_by_sym.get(sym, [])
        in_window = [a for a in raw_list if cutoff_lo <= a.get("unix_ts", 0) <= cutoff_hi]

        # Score relevance: prioritize headlines mentioning ticker/company name first!
        def _rel_score(art: Dict[str, Any]) -> Tuple[int, int]:
            text = (art.get("title", "") + " " + art.get("summary", "")).lower()
            mentions = sum(1 for w in comp_words if w in text)
            return (1 if mentions > 0 else 0, art.get("unix_ts", 0))

        in_window.sort(key=_rel_score, reverse=True)
        selected = in_window[:limit]

        if selected:
            avg_score = sum(a["sentiment_score"] for a in selected) / len(selected)
            bullish_count = sum(1 for a in selected if a["sentiment"] == "BULLISH")
            bearish_count = sum(1 for a in selected if a["sentiment"] == "BEARISH")
            neutral_count = sum(1 for a in selected if a["sentiment"] == "NEUTRAL")
            all_cats = [c for a in selected for c in a.get("catalysts", []) if c != "GENERAL_NEWS"]
            cat_counts = {}
            for c in all_cats:
                cat_counts[c] = cat_counts.get(c, 0) + 1
            top_cats = sorted(cat_counts.keys(), key=lambda k: cat_counts[k], reverse=True)[:3] or ["GENERAL_NEWS"]
            label = "BULLISH" if avg_score > 0.15 else ("BEARISH" if avg_score < -0.15 else "NEUTRAL")
        else:
            avg_score = 0.0
            bullish_count = bearish_count = neutral_count = 0
            top_cats = ["NONE_RECENT"]
            label = "NEUTRAL"

        return {
            "symbol": sym,
            "articles": selected,
            "overall_sentiment": {
                "score": round(avg_score, 2),
                "label": label,
                "bullish_count": bullish_count,
                "bearish_count": bearish_count,
                "neutral_count": neutral_count
            },
            "top_catalysts": top_cats,
            "article_count": len(selected)
        }

    def get_macro_as_of(self, as_of_dt: datetime) -> Dict[str, Any]:
        """Strictly causal FRED macro regime as of `as_of_dt`."""
        dgs10, dgs2, vix, cpi_yoy, fed_funds = 4.45, 4.25, 16.0, 2.7, 4.75
        if not self.macro_df.empty:
            prior = self.macro_df[self.macro_df.index.date <= as_of_dt.date()]
            if not prior.empty:
                row = prior.iloc[-1]
                dgs10 = float(row.get("DGS10", dgs10) or dgs10)
                dgs2 = float(row.get("DGS2", dgs2) or dgs2)
                vix = float(row.get("VIXCLS", vix) or vix)
                fed_funds = float(row.get("FEDFUNDS", fed_funds) or fed_funds)

        spread = round((dgs10 - dgs2) * 100.0, 1)
        curve_status = "INVERTED" if spread < -5 else ("FLAT" if spread <= 15 else "NORMAL")
        if vix < 14:
            regime = "RISK_ON"
            vol_status = "LOW VOLATILITY"
        elif vix <= 19:
            regime = "NEUTRAL"
            vol_status = "MODERATE VOLATILITY"
        elif vix <= 28:
            regime = "CAUTIOUS"
            vol_status = "HIGH VOLATILITY"
        else:
            regime = "RISK_OFF"
            vol_status = "EXTREME VOLATILITY"

        return {
            "regime": regime,
            "curve_status": curve_status,
            "volatility_status": vol_status,
            "summary": f"US 10Y: {dgs10:.2f}% | 10Y-2Y Spread: {spread:+.1f} bps ({curve_status}) | VIX: {vix:.2f} ({vol_status})",
            "indicators": {
                "source": "FRED Historical",
                "dgs10": round(dgs10, 2),
                "dgs2": round(dgs2, 2),
                "yield_spread_bps": spread,
                "cpi_yoy": cpi_yoy,
                "fed_funds": round(fed_funds, 2),
                "vix": round(vix, 2)
            }
        }

    def get_earnings_as_of(self, sym: str, as_of_dt: datetime) -> Dict[str, Any]:
        """Checks historical earnings proximity strictly relative to `as_of_dt`."""
        sym = sym.strip().upper()
        events = self.earnings_events.get(sym, [])
        best_diff_h = None
        best_date_str = None
        for ev in events:
            ev_ny = ev.astimezone(NY_TZ) if ev.tzinfo else ev.replace(tzinfo=NY_TZ)
            diff_h = (ev_ny - as_of_dt).total_seconds() / 3600.0
            if -24 <= diff_h <= 240:
                best_diff_h = diff_h
                best_date_str = ev_ny.strftime("%Y-%m-%d")
                break

        if best_diff_h is not None:
            if 0 <= best_diff_h <= 24:
                status, action, mult = "VETO_BLACKOUT", "VETO", 0.0
                reason = f"Earnings announcement in {best_diff_h:.1f}h ({best_date_str}). Binary risk blackout."
            elif 24 < best_diff_h <= 48:
                status, action, mult = "WARNING_HALVE_SIZE", "HALVE", 0.5
                reason = f"Earnings in {best_diff_h:.1f}h ({best_date_str}). Size halved (50%)."
            elif -24 <= best_diff_h < 0:
                status, action, mult = "POST_EARNINGS_VOLATILITY", "HALVE", 0.5
                reason = f"Reported earnings {abs(best_diff_h):.1f}h ago ({best_date_str}). High post-earnings drift/volatility."
            else:
                status, action, mult = "CLEAR", "CLEAR", 1.0
                reason = f"Next earnings on {best_date_str} ({best_diff_h/24:.1f}d away)."
            return {
                "symbol": sym,
                "has_earnings_soon": -24 <= best_diff_h <= 48,
                "hours_to_earnings": round(best_diff_h, 1),
                "earnings_date": best_date_str,
                "blackout_status": status,
                "action": action,
                "size_multiplier": mult,
                "reason": reason
            }

        return {
            "symbol": sym,
            "has_earnings_soon": False,
            "hours_to_earnings": None,
            "earnings_date": None,
            "blackout_status": "CLEAR",
            "action": "CLEAR",
            "size_multiplier": 1.0,
            "reason": "No earnings event within [-24h, +10d]."
        }

    def build_point_in_time_dossier(self, sym: str, as_of_dt: datetime, is_premarket: bool = False) -> Dict[str, Any]:
        """
        Constructs the complete causal market/fundamental/technical/news/A-CIS score dossier
        as of `as_of_dt`.
        """
        sym = sym.strip().upper()
        as_of_date_str = as_of_dt.strftime("%Y-%m-%d")
        quote = self.get_quote_as_of(sym, as_of_dt)
        tech = self.get_technicals_as_of(sym, as_of_dt)
        news = self.get_news_as_of(sym, as_of_dt, lookback_hours=48, limit=6)
        macro = self.get_macro_as_of(as_of_dt)
        earnings = self.get_earnings_as_of(sym, as_of_dt)
        sec_raw = self.sec_by_sym.get(sym) or fetch_sec_filings(sym, as_of_date=as_of_date_str)
        sec = json.loads(json.dumps(sec_raw))
        if sec.get("filings"):
            sec["filings"] = [f for f in sec["filings"] if not f.get("filing_date") or str(f["filing_date"])[:10] <= as_of_date_str]

        ins_raw = self.insider_by_sym.get(sym) or fetch_insider_and_13f_activity(sym, as_of_date=as_of_date_str)
        insider = json.loads(json.dumps(ins_raw))
        txs = [t for t in insider.get("transactions", []) if not t.get("date") or str(t["date"])[:10] <= as_of_date_str]
        buys = sum(1 for t in txs if "BUY" in str(t.get("type", "")).upper())
        sells = sum(1 for t in txs if "SELL" in str(t.get("type", "")).upper())
        insider["transactions"] = txs
        insider["form4_transactions"] = txs
        insider["recent_buys_count"] = buys
        insider["recent_sells_count"] = sells
        insider["cluster_verdict"] = (
            f"BULLISH CLUSTER ({buys} Buys)" if buys > sells and buys > 0
            else (f"ROUTINE SELLING ({sells} Sells)" if sells > buys * 2 and sells >= 3 else "NEUTRAL")
        )

        ecosystem = fetch_company_ecosystem(
            symbol=sym,
            quote_override=quote,
            tech_override=tech,
            news_override=news,
            quote_fn=lambda s: self.get_quote_as_of(s, as_of_dt),
            news_fn=lambda s: self.get_news_as_of(s, as_of_dt, lookback_hours=48, limit=3),
            use_gemini_grounding=False,
            as_of_label=as_of_dt.strftime("%Y-%m-%d %H:%M %Z")
        )

        return {
            "symbol": sym,
            "company_name": ecosystem.get("company_name", sym),
            "sector": ecosystem.get("sector", "Technology"),
            "as_of": as_of_dt.strftime("%Y-%m-%d %H:%M %Z"),
            "is_premarket": is_premarket,
            "quote": quote,
            "technicals": tech,
            "news": news,
            "macro": macro,
            "earnings": earnings,
            "sec": sec,
            "insider": insider,
            "ecosystem": ecosystem,
            "catalyst_scores": ecosystem.get("catalyst_scores", {})
        }
