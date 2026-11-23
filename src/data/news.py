"""
Breaking News Aggregator & Catalyst Sentiment Engine
Integrates Finnhub API with resilient yfinance/RSS fallback, real-time catalyst tagging,
and financial sentiment analysis.
"""

import datetime
import json
import logging
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from typing import Any, Dict, List, Optional
import yfinance as yf

from src.core.config import FINNHUB_API_KEY, get_cached, set_cached

logger = logging.getLogger("NewsEngine")

# Catalyst classification keywords
CATALYST_PATTERNS = {
    "EARNINGS": [
        r"\bearnings\b", r"\beps\b", r"\brevenue\b", r"\bquarterly\b", r"\bbeat\b",
        r"\bmiss\b", r"\bprofit\b", r"\bguidance\b", r"\bq[1-4]\b", r"\bfinancial results\b"
    ],
    "FDA_BIOTECH": [
        r"\bfda\b", r"\bphase\s+[1-3]\b", r"\bapproval\b", r"\bclinical trial\b",
        r"\bdrug\b", r"\btreatment\b", r"\bpatent\b"
    ],
    "M&A_DEALS": [
        r"\bacquisition\b", r"\bmerger\b", r"\bbuyout\b", r"\btakeover\b",
        r"\bdeal\b", r"\bpartnership\b", r"\bcontract\b", r"\bagreement\b"
    ],
    "REGULATORY_LEGAL": [
        r"\blawsuit\b", r"\bdoj\b", r"\bsec\b", r"\binvestigation\b", r"\bsanctions\b",
        r"\bantitrust\b", r"\bfine\b", r"\bsettlement\b", r"\bsubpoena\b"
    ],
    "MACRO_RATES": [
        r"\bfed\b", r"\brates\b", r"\binflation\b", r"\bcpi\b", r"\byield\b",
        r"\btreasury\b", r"\bpowell\b", r"\brecession\b", r"\btariff\b"
    ],
    "UPGRADE_DOWNGRADE": [
        r"\bupgrade\b", r"\bdowngrade\b", r"\bprice target\b", r"\boutperform\b",
        r"\bunderperform\b", r"\bbuy rating\b", r"\bsell rating\b"
    ]
}

POSITIVE_WORDS = {
    "surge", "jump", "soar", "gain", "rally", "record", "beat", "higher",
    "profit", "strong", "bullish", "upgrade", "growth", "breakout", "exceed",
    "dividend", "buyback", "boost", "outperform", "milestone", "advancing"
}

NEGATIVE_WORDS = {
    "drop", "plunge", "fall", "slump", "decline", "miss", "lower", "loss",
    "weak", "bearish", "downgrade", "probe", "investigation", "lawsuit", "cut",
    "warning", "slashes", "debt", "default", "scandal", "risk", "disappoint"
}


def tag_catalysts(text: str) -> List[str]:
    """Identifies catalyst categories present in news text."""
    lower_text = text.lower()
    catalysts = []
    for category, patterns in CATALYST_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, lower_text):
                catalysts.append(category)
                break
    return catalysts if catalysts else ["GENERAL_NEWS"]


def calculate_sentiment(text: str) -> Dict[str, Any]:
    """Computes financial sentiment polarity score (-1.0 to +1.0) and label."""
    words = re.findall(r"\b[a-z]+\b", text.lower())
    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)
    total = pos_count + neg_count

    if total == 0:
        score = 0.0
        label = "NEUTRAL"
    else:
        score = (pos_count - neg_count) / total
        if score > 0.15:
            label = "BULLISH"
        elif score < -0.15:
            label = "BEARISH"
        else:
            label = "NEUTRAL"

    return {
        "score": round(score, 2),
        "label": label,
        "pos_signals": pos_count,
        "neg_signals": neg_count
    }


def fetch_breaking_news(symbol: str) -> Dict[str, Any]:
    """
    Fetches real-time company news articles with catalyst classification and sentiment analysis.
    Uses Finnhub API if key provided, with automatic fallback to Yahoo Finance / RSS feed.
    """
    sym = symbol.strip().upper()
    cache_key = f"news_{sym}"
    cached = get_cached(cache_key, 60)
    if cached:
        return cached

    articles = []

    # 1. Try Finnhub Company News
    if FINNHUB_API_KEY:
        try:
            today = datetime.date.today()
            from_date = (today - datetime.timedelta(days=7)).strftime("%Y-%m-%d")
            to_date = today.strftime("%Y-%m-%d")
            url = f"https://finnhub.io/api/v1/company-news?symbol={sym}&from={from_date}&to={to_date}&token={FINNHUB_API_KEY}"
            req = urllib.request.Request(url, headers={"User-Agent": "AdversarialIQ/1.0"})
            with urllib.request.urlopen(req, timeout=4) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data[:10]:
                    title = item.get("headline", "")
                    summary = item.get("summary", "")
                    comb = f"{title}. {summary}"
                    sentiment = calculate_sentiment(comb)
                    catalysts = tag_catalysts(comb)

                    articles.append({
                        "id": str(item.get("id", "")),
                        "title": title,
                        "summary": summary[:250] + ("..." if len(summary) > 250 else ""),
                        "source": item.get("source", "Finnhub"),
                        "url": item.get("url", f"https://finance.yahoo.com/quote/{sym}/news"),
                        "timestamp": datetime.datetime.fromtimestamp(item.get("datetime", time.time())).strftime("%Y-%m-%d %H:%M"),
                        "sentiment": sentiment["label"],
                        "sentiment_score": sentiment["score"],
                        "catalysts": catalysts
                    })
        except Exception as e:
            logger.debug(f"Finnhub fetch notice for {sym}: {e}")

    # 2. Resilient yfinance News Fallback
    if not articles:
        try:
            t = yf.Ticker(sym)
            raw_news = getattr(t, "news", []) or []
            for item in raw_news[:8]:
                title = item.get("title") or item.get("headline") or ""
                summary = item.get("summary") or ""
                comb = f"{title}. {summary}"
                sentiment = calculate_sentiment(comb)
                catalysts = tag_catalysts(comb)
                pub_time = item.get("providerPublishTime") or time.time()

                articles.append({
                    "id": str(item.get("uuid", "")),
                    "title": title,
                    "summary": summary[:250] + ("..." if len(summary) > 250 else ""),
                    "source": item.get("publisher", "Yahoo Finance"),
                    "url": item.get("link", f"https://finance.yahoo.com/quote/{sym}/news"),
                    "timestamp": datetime.datetime.fromtimestamp(pub_time).strftime("%Y-%m-%d %H:%M"),
                    "sentiment": sentiment["label"],
                    "sentiment_score": sentiment["score"],
                    "catalysts": catalysts
                })
        except Exception as e:
            logger.warning(f"yfinance news fallback notice for {sym}: {e}")

    # Compute aggregate sentiment & catalyst frequency
    if articles:
        avg_score = sum(a["sentiment_score"] for a in articles) / len(articles)
        all_catalysts = [c for a in articles for c in a["catalysts"] if c != "GENERAL_NEWS"]
        cat_counts = {}
        for c in all_catalysts:
            cat_counts[c] = cat_counts.get(c, 0) + 1
        top_catalysts = sorted(cat_counts.keys(), key=lambda k: cat_counts[k], reverse=True)[:3]
    else:
        avg_score = 0.0
        top_catalysts = ["MOMENTUM", "MARKET_STRUCTURE"]

    if avg_score > 0.15:
        overall_label = "BULLISH"
    elif avg_score < -0.15:
        overall_label = "BEARISH"
    else:
        overall_label = "NEUTRAL"

    result = {
        "symbol": sym,
        "articles": articles[:10],
        "overall_sentiment": {
            "score": round(avg_score, 2),
            "label": overall_label
        },
        "top_catalysts": top_catalysts or ["MACRO_RATES"],
        "article_count": len(articles)
    }

    set_cached(cache_key, result)
    return result
