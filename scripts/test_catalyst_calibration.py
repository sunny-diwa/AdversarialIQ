"""
Verification test for news sentiment, catalyst calibration, and ecosystem scores.
"""
from src.data.news import calculate_sentiment, tag_catalysts
from src.data.ecosystem import calculate_ecosystem_catalyst_scores

def run_tests():
    # 1. Test Sentiment Engine
    print("=== 1. Testing News Sentiment Engine ===")
    t1 = "NVIDIA Board Reinstates Jensen Huang as President, CEO and Director; Shares Surge +30%"
    s1 = calculate_sentiment(t1)
    c1 = tag_catalysts(t1)
    print("Bullish CEO Headline:", t1[:60])
    print("  Score:", s1["score"], "Label:", s1["label"], "Intensity:", s1.get("intensity"), "Catalysts:", c1)
    assert s1["label"] == "BULLISH" and s1["score"] >= 0.85
    assert "EXECUTIVE_LEADERSHIP" in c1

    t2 = "Company Board Abruptly Removes CEO Following Accounting Probe and Subpoena"
    s2 = calculate_sentiment(t2)
    c2 = tag_catalysts(t2)
    print("Bearish CEO Headline:", t2[:60])
    print("  Score:", s2["score"], "Label:", s2["label"], "Intensity:", s2.get("intensity"), "Catalysts:", c2)
    assert s2["label"] == "BEARISH" and s2["score"] <= -0.85
    assert "EXECUTIVE_LEADERSHIP" in c2

    # 2. Test Ecosystem Catalyst Scoring Engine on NVDA with Jensen Huang news
    print("\n=== 2. Testing Ecosystem Scoring Calibration for NVDA ===")
    nvda_quote = {
        "symbol": "NVDA", "price": 145.0, "prev_close": 142.0, "open": 144.0,
        "pct_change": 2.1, "volume": 65000000, "avg_volume_10d": 40000000,
        "premarket_gap_pct": 1.4
    }
    nvda_tech = {
        "sma20": 138.0, "sma50": 130.0, "sma200": 115.0,
        "rsi": 62.0, "atr": 4.5
    }
    suppliers = [
        {"symbol": "TSM", "name": "Taiwan Semiconductor", "pct_change": 1.8, "news_sentiment": "BULLISH", "criticality": "CRITICAL"}
    ]
    customers = [
        {"symbol": "MSFT", "name": "Microsoft", "pct_change": 1.2, "news_sentiment": "BULLISH", "revenue_share_pct": 18.0},
        {"symbol": "META", "name": "Meta Platforms", "pct_change": 1.5, "news_sentiment": "BULLISH", "revenue_share_pct": 14.0}
    ]
    competitors = [
        {"symbol": "AMD", "name": "Advanced Micro Devices", "pct_change": -0.8, "news_sentiment": "NEUTRAL", "threat_level": "HIGH"}
    ]

    nvda_news = {
        "overall_sentiment": {
            "score": 0.88,
            "label": "BULLISH",
            "has_executive_catalyst": True,
            "bullish_count": 4, "bearish_count": 0, "neutral_count": 1
        },
        "top_catalysts": ["EXECUTIVE_LEADERSHIP", "EARNINGS", "M&A_DEALS"]
    }

    meta = {"name": "NVIDIA Corporation", "sector": "Information Technology", "sub_industry": "Semiconductors"}

    scores = calculate_ecosystem_catalyst_scores(
        symbol="NVDA",
        meta=meta,
        quote_info=nvda_quote,
        tech_info=nvda_tech,
        suppliers=suppliers,
        customers=customers,
        competitors=competitors,
        news_info=nvda_news
    )

    print("NVDA Recalibrated Catalyst Scores:")
    print("  Movement Probability:", scores["movement_probability_score"], "(", scores["movement_label"], ")")
    print("  Up Score (Bullish Catalyst):", scores["up_score"])
    print("  Down Score (Bearish Catalyst):", scores["down_score"])
    print("  Dominant Bias:", scores["dominant_bias"])
    print("  Net Spread:", scores["net_directional_spread"])
    print("  Pre-Market Up Score:", scores["start_of_day"]["up_score"])

    up = scores["up_score"]
    down = scores["down_score"]
    mov = scores["movement_probability_score"]

    assert up >= 80.0, f"Expected up_score >= 80.0, got {up}"
    assert down <= 25.0, f"Expected down_score <= 25.0, got {down}"
    assert mov >= 75.0, f"Expected movement_prob >= 75.0, got {mov}"
    assert scores["dominant_bias"] == "BULLISH CATALYST"

    print("\n>>> ALL CALIBRATION CHECKS PASSED PERFECTLY! <<<")

if __name__ == "__main__":
    run_tests()
