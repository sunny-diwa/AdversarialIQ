"""
Breaking News Aggregator & Catalyst Sentiment Engine
Integrates Finnhub API with resilient yfinance/RSS fallback, real-time catalyst tagging,
and financial sentiment analysis.
"""

import datetime
import logging
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
import json
from typing import Any, Dict, List, Optional
import yfinance as yf

from src.config import FINNHUB_API_KEY, get_cached, set_cached

logger = logging.getLogger("NewsEngine")

# Catalyst classification keywords
CATALYST_PATTERNS = {
    "EARNINGS": [
        r"\bearnings\b", r"\beps\b", r"\brevenue\b", r"\bquarterly\b", r"\bbeat\b",
        r"\bmiss\b", r"\bprofit\b", r"\bguidance\b", r"\bq[1-4]\b", r"\bfinancial results\b"
    ],
    "M&A / DEAL": [
        r"\bacquisition\b", r"\bacquire\b", r"\bmerger\b", r"\bbuyout\b", r"\btakeover\b",
        r"\bdeal\b", r"\bstake\b", r"\bpartnership\b", r"\bjoint venture\b"
    ],
    "PRODUCT / AI": [
        r"\blaunch\b", r"\bproduct\b", r"\bai\b", r"\bchip\b", r"\bgpu\b", r"\bpatent\b",
        r"\bfda\b", r"\bapproval\b", r"\bclinical\b", r"\bplatform\b", r"\bcloud\b"
    ],
    "REGULATORY / LEGAL": [
        r"\bsec\b", r"\blawsuit\b", r"\binvestigation\b", r"\bfine\b", r"\bsubpoena\b",
        r"\bantitrust\b", r"\bdoj\b", r"\bprobe\b", r"\bregulation\b", r"\bsettlement\b"
    ],
    "ANALYST / RATING": [
        r"\bupgrade\b", r"\bdowngrade\b", r"\bprice target\b", r"\boverweight\b",
        r"\bunderweight\b", r"\bbuy rating\b", r"\bsell rating\b", r"\binitiates\b"
    ],
    "MACRO / INDUSTRY": [
        r"\bfed\b", r"\brates\b", r"\btariff\b", r"\binflation\b", r"\bsector\b", r"\bgdp\b"
    ]
}

# Financial sentiment lexicons
POSITIVE_WORDS = {
    "surge", "surges", "surged", "jump", "jumps", "jumped", "soar", "soars", "soared",
    "rally", "rallies", "rallied", "beat", "beats", "beating", "outperform", "outperformed",
    "gain", "gains", "gained", "record", "high", "upgrade", "upgrades", "upgraded",
    "bullish", "profit", "profitable", "growth", "strong", "stronger", "boost", "boosts",
    "breakthrough", "expansion", "dividend", "buyback", "positive", "exceed", "exceeds"
}

NEGATIVE_WORDS = {
    "slump", "slumps", "slumped", "drop", "drops", "dropped", "plunge", "plunges", "plunged",
    "fall", "falls", "fallen", "decline", "declines", "declined", "miss", "misses", "missed",
    "underperform", "loss", "losses", "cut", "cuts", "cutting", "downgrade", "downgrades",
    "downgraded", "bearish", "warning", "warns", "warned", "lawsuit", "investigation",
    "probe", "fine", "fined", "fraud", "risk", "risks", "weak", "weaker", "negative"
}


def tag_catalyst(text: str) -> str:
    """Classify the catalyst type from headline/summary text."""
    lower_text = text.lower()
    for category, patterns in CATALYST_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, lower_text):
                return category
    return "GENERAL"


def analyze_sentiment(text: str) -> Dict[str, Any]:
    """
    Score sentiment polarity based on financial dictionary scoring.
    Returns sentiment label ('BULLISH', 'BEARISH', 'NEUTRAL') and score (-1.0 to 1.0).
    """
    words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)

    total_matched = pos_count + neg_count
    if total_matched == 0:
        return {"label": "NEUTRAL", "score": 0.0, "pos": 0, "neg": 0}

    score = (pos_count - neg_count) / max(1, total_matched)
    # Apply thresholding
    if score >= 0.2:
        label = "BULLISH"
    elif score <= -0.2:
        label = "BEARISH"
    else:
        label = "NEUTRAL"

    return {"label": label, "score": round(score, 2), "pos": pos_count, "neg": neg_count}


def fetch_finnhub_news(symbol: str, api_key: str, days: int = 7) -> Optional[List[dict]]:
    """Fetch company news directly from Finnhub API."""
    if not api_key:
        return None
    try:
        today = datetime.date.today()
        from_date = (today - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
        to_date = today.strftime("%Y-%m-%d")
        url = (
            f"https://finnhub.io/api/v1/company-news?"
            f"symbol={symbol.upper()}&from={from_date}&to={to_date}&token={api_key}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "AdversarialIQ/1.0"})
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode())
                if isinstance(data, list) and len(data) > 0:
                    articles = []
                    for item in data[:20]:
                        headline = item.get("headline", "")
                        summary = item.get("summary", "")
                        combined = f"{headline} {summary}"
                        sent = analyze_sentiment(combined)
                        catalyst = tag_catalyst(combined)
                        articles.append({
                            "id": str(item.get("id", "")),
                            "headline": headline,
                            "summary": summary,
                            "source": item.get("source", "Finnhub"),
                            "url": item.get("url", "#"),
                            "datetime": item.get("datetime", int(time.time())),
                            "sentiment": sent["label"],
                            "sentiment_score": sent["score"],
                            "catalyst": catalyst
                        })
                    return articles
    except Exception as e:
        logger.warning(f"Finnhub API fetch failed for {symbol}: {e}")
    return None


def fetch_yfinance_news(symbol: str) -> List[dict]:
    """Resilient fallback: fetch news via yfinance."""
    articles = []
    try:
        ticker = yf.Ticker(symbol)
        raw_news = getattr(ticker, "news", []) or []
        for i, item in enumerate(raw_news[:20]):
            content = item.get("content", {}) if isinstance(item, dict) and "content" in item else item
            headline = content.get("title", "") or item.get("title", "")
            summary = content.get("summary", "") or item.get("summary", "")
            url = content.get("canonicalUrl", {}).get("url", "") or item.get("link", "#")
            pub_date = content.get("pubDate", "") or item.get("providerPublishTime", int(time.time()))
            publisher = content.get("provider", {}).get("displayName", "") or item.get("publisher", "Market Wire")

            if not headline:
                continue

            combined = f"{headline} {summary}"
            sent = analyze_sentiment(combined)
            catalyst = tag_catalyst(combined)

            articles.append({
                "id": str(item.get("uuid", f"yf_{i}")),
                "headline": headline,
                "summary": summary,
                "source": publisher,
                "url": url,
                "datetime": pub_date,
                "sentiment": sent["label"],
                "sentiment_score": sent["score"],
                "catalyst": catalyst
            })
    except Exception as e:
        logger.error(f"yfinance news fallback failed for {symbol}: {e}")

    return articles


def fetch_rss_news(symbol: str) -> List[dict]:
    """Fallback to Google Finance / News RSS feed when other providers fail."""
    articles = []
    try:
        url = f"https://news.google.com/rss/search?q={symbol.upper()}+stock+nasdaq+nyse&hl=en-US&gl=US&ceid=US:en"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=4) as response:
            if response.status == 200:
                xml_data = response.read()
                root = ET.fromstring(xml_data)
                items = root.findall(".//item")
                for i, item in enumerate(items[:15]):
                    title = item.findtext("title", "")
                    link = item.findtext("link", "#")
                    pub_date = item.findtext("pubDate", "")
                    source = item.findtext("source", "Market News")

                    sent = analyze_sentiment(title)
                    catalyst = tag_catalyst(title)

                    articles.append({
                        "id": f"rss_{i}",
                        "headline": title,
                        "summary": title,
                        "source": source,
                        "url": link,
                        "datetime": pub_date,
                        "sentiment": sent["label"],
                        "sentiment_score": sent["score"],
                        "catalyst": catalyst
                    })
    except Exception as e:
        logger.debug(f"RSS fallback failed for {symbol}: {e}")
    return articles


def fetch_breaking_news(symbol: str, api_key: Optional[str] = None) -> Dict[str, Any]:
    """
    Main entry point: fetches breaking news, tags catalysts, and scores sentiment.
    Uses in-memory cache with 60s TTL to preserve rate limits.
    """
    symbol = symbol.upper()
    cache_key = f"news_{symbol}"
    cached = get_cached(cache_key, 60)
    if cached:
        return cached

    key = api_key or FINNHUB_API_KEY
    provider = "finnhub"
    articles = fetch_finnhub_news(symbol, key) if key else None

    if not articles:
        provider = "yfinance"
        articles = fetch_yfinance_news(symbol)

    if not articles:
        provider = "google_news_rss"
        articles = fetch_rss_news(symbol)

    # Compute aggregate sentiment
    total = len(articles)
    bullish_count = sum(1 for a in articles if a["sentiment"] == "BULLISH")
    bearish_count = sum(1 for a in articles if a["sentiment"] == "BEARISH")
    neutral_count = sum(1 for a in articles if a["sentiment"] == "NEUTRAL")

    avg_score = 0.0
    if total > 0:
        avg_score = sum(a["sentiment_score"] for a in articles) / total

    overall_label = "NEUTRAL"
    if avg_score >= 0.15 or (bullish_count > bearish_count * 1.5 and bullish_count >= 2):
        overall_label = "BULLISH"
    elif avg_score <= -0.15 or (bearish_count > bullish_count * 1.5 and bearish_count >= 2):
        overall_label = "BEARISH"

    # Identify top catalysts
    catalyst_counts: Dict[str, int] = {}
    for a in articles:
        c = a.get("catalyst", "GENERAL")
        if c != "GENERAL":
            catalyst_counts[c] = catalyst_counts.get(c, 0) + 1

    top_catalysts = sorted(catalyst_counts.keys(), key=lambda k: catalyst_counts[k], reverse=True)

    result = {
        "symbol": symbol,
        "provider": provider,
        "total_articles": total,
        "overall_sentiment": {
            "label": overall_label,
            "score": round(avg_score, 2),
            "bullish_count": bullish_count,
            "bearish_count": bearish_count,
            "neutral_count": neutral_count
        },
        "top_catalysts": top_catalysts[:3],
        "articles": articles
    }

    set_cached(cache_key, result)
    return result
