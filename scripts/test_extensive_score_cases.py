"""
Comprehensive Multi-Case Scoring Engine Benchmark Suite.
Tests 12 realistic financial scenarios across fundamental catalysts, leadership shocks,
supply-chain spillovers, earnings events, regulatory actions, and counter-trend regimes.
"""

from typing import Dict, Any, List
from src.data.news import calculate_sentiment, tag_catalysts
from src.data.ecosystem import calculate_ecosystem_catalyst_scores


def run_test_case(name: str, headline: str, quote: Dict[str, Any], tech: Dict[str, Any],
                  suppliers: List[Dict[str, Any]], customers: List[Dict[str, Any]],
                  competitors: List[Dict[str, Any]], expected_bias: str,
                  min_primary_score: float, min_vol_prob: float = 0.0) -> Dict[str, Any]:
    
    # 1. Compute Sentiment
    sent = calculate_sentiment(headline) if headline else {"score": 0.0, "label": "NEUTRAL", "intensity": "LOW"}
    cats = tag_catalysts(headline) if headline else ["GENERAL_NEWS"]
    
    news_obj = {
        "overall_sentiment": {
            "score": sent["score"],
            "label": sent["label"],
            "has_executive_catalyst": ("EXECUTIVE_LEADERSHIP" in cats),
            "bullish_count": 1 if sent["label"] == "BULLISH" else 0,
            "bearish_count": 1 if sent["label"] == "BEARISH" else 0,
            "neutral_count": 1 if sent["label"] == "NEUTRAL" else 0
        },
        "top_catalysts": cats,
        "article_count": 1
    }

    meta = {"name": f"{quote.get('symbol', 'SYM')} Inc", "sector": "Technology", "sub_industry": "Equities"}

    scores = calculate_ecosystem_catalyst_scores(
        symbol=quote.get("symbol", "SYM"),
        meta=meta,
        quote_info=quote,
        tech_info=tech,
        suppliers=suppliers,
        customers=customers,
        competitors=competitors,
        news_info=news_obj
    )

    up = scores["up_score"]
    down = scores["down_score"]
    spread = scores["net_directional_spread"]
    mov = scores["movement_probability_score"]
    bias = scores["dominant_bias"]

    # Validations
    passed = True
    errors = []

    if expected_bias == "BULLISH CATALYST":
        if bias != "BULLISH CATALYST":
            passed = False
            errors.append(f"Expected BULLISH CATALYST, got {bias}")
        if up < min_primary_score:
            passed = False
            errors.append(f"Up score {up} < minimum {min_primary_score}")
    elif expected_bias == "BEARISH CATALYST":
        if bias != "BEARISH CATALYST":
            passed = False
            errors.append(f"Expected BEARISH CATALYST, got {bias}")
        if down < min_primary_score:
            passed = False
            errors.append(f"Down score {down} < minimum {min_primary_score}")
    elif expected_bias == "BALANCED / DUAL-SIDED VOLATILITY":
        if bias != "BALANCED / DUAL-SIDED VOLATILITY":
            passed = False
            errors.append(f"Expected BALANCED, got {bias}")

    if min_vol_prob > 0.0 and mov < min_vol_prob:
        passed = False
        errors.append(f"Movement prob {mov} < minimum {min_vol_prob}")

    return {
        "case_name": name,
        "passed": passed,
        "headline_sentiment": f"{sent['score']} ({sent['label']})",
        "movement_prob": mov,
        "up_score": up,
        "down_score": down,
        "net_spread": spread,
        "dominant_bias": bias,
        "errors": errors
    }


def main():
    cases = []

    # Case 1: CEO Reinstatement (NVDA - Jensen Huang)
    cases.append(run_test_case(
        name="1. Historic CEO Reinstatement (NVDA Jensen Huang)",
        headline="NVIDIA Board Reinstates Jensen Huang as President, CEO and Director; Shares Surge +30%",
        quote={"symbol": "NVDA", "price": 145.0, "prev_close": 142.0, "open": 144.0, "pct_change": 2.1, "volume": 50000000, "avg_volume_10d": 35000000},
        tech={"sma20": 138.0, "sma50": 130.0, "sma200": 115.0, "rsi": 62.0, "atr": 4.5},
        suppliers=[{"symbol": "TSM", "pct_change": 2.0, "news_sentiment": "BULLISH", "criticality": "CRITICAL"}],
        customers=[{"symbol": "MSFT", "pct_change": 1.5, "news_sentiment": "BULLISH", "revenue_share_pct": 18.0}],
        competitors=[{"symbol": "AMD", "pct_change": -1.0, "news_sentiment": "NEUTRAL", "threat_level": "HIGH"}],
        expected_bias="BULLISH CATALYST",
        min_primary_score=88.0,
        min_vol_prob=80.0
    ))

    # Case 2: CEO Fired / Corporate Fraud Shock
    cases.append(run_test_case(
        name="2. CEO Fired & Accounting Fraud Shock",
        headline="Board Abruptly Fires CEO Following Accounting Fraud and DOJ Criminal Subpoena",
        quote={"symbol": "CORP", "price": 50.0, "prev_close": 55.0, "open": 49.0, "pct_change": -9.1, "volume": 25000000, "avg_volume_10d": 10000000},
        tech={"sma20": 56.0, "sma50": 58.0, "sma200": 60.0, "rsi": 22.0, "atr": 2.5},
        suppliers=[{"symbol": "SUP", "pct_change": -3.0, "news_sentiment": "BEARISH", "criticality": "HIGH"}],
        customers=[{"symbol": "CUST", "pct_change": -2.0, "news_sentiment": "BEARISH", "revenue_share_pct": 20.0}],
        competitors=[{"symbol": "COMP", "pct_change": 4.0, "news_sentiment": "BULLISH", "threat_level": "HIGH"}],
        expected_bias="BEARISH CATALYST",
        min_primary_score=88.0,
        min_vol_prob=80.0
    ))

    # Case 3: Cloud Earnings Blowout & Capex Raise
    cases.append(run_test_case(
        name="3. Cloud Earnings Blowout & Capex Raise",
        headline="Commercial Cloud Revenue Jumps 38% Beating All Wall Street Targets; Azure Capex Raised",
        quote={"symbol": "MSFT", "price": 430.0, "prev_close": 418.0, "open": 428.0, "pct_change": 2.9, "volume": 32000000, "avg_volume_10d": 20000000},
        tech={"sma20": 420.0, "sma50": 415.0, "sma200": 400.0, "rsi": 66.0, "atr": 7.0},
        suppliers=[{"symbol": "NVDA", "pct_change": 3.5, "news_sentiment": "BULLISH", "criticality": "CRITICAL"}],
        customers=[{"symbol": "ENT1", "pct_change": 1.2, "news_sentiment": "BULLISH", "revenue_share_pct": 12.0}],
        competitors=[{"symbol": "GOOGL", "pct_change": -0.5, "news_sentiment": "NEUTRAL", "threat_level": "HIGH"}],
        expected_bias="BULLISH CATALYST",
        min_primary_score=80.0,
        min_vol_prob=70.0
    ))

    # Case 4: Severe Earnings Miss & Guidance Cut
    cases.append(run_test_case(
        name="4. Severe Earnings Miss & Guidance Cut",
        headline="Company Slashes Full-Year Guidance by 25% Citing Datacenter Customer Share Losses",
        quote={"symbol": "INTC", "price": 28.0, "prev_close": 31.0, "open": 28.5, "pct_change": -9.7, "volume": 60000000, "avg_volume_10d": 30000000},
        tech={"sma20": 32.0, "sma50": 33.0, "sma200": 36.0, "rsi": 28.0, "atr": 1.2},
        suppliers=[{"symbol": "SUP1", "pct_change": -2.0, "news_sentiment": "BEARISH", "criticality": "HIGH"}],
        customers=[{"symbol": "CUST1", "pct_change": 0.5, "news_sentiment": "NEUTRAL", "revenue_share_pct": 15.0}],
        competitors=[{"symbol": "NVDA", "pct_change": 3.0, "news_sentiment": "BULLISH", "threat_level": "EXTREME"}],
        expected_bias="BEARISH CATALYST",
        min_primary_score=80.0,
        min_vol_prob=70.0
    ))

    # Case 5: Critical Upstream Bottleneck Halts Production
    cases.append(run_test_case(
        name="5. Critical Upstream Supplier Bottleneck",
        headline="",  # No direct news
        quote={"symbol": "TECH", "price": 100.0, "prev_close": 100.5, "open": 100.0, "pct_change": -0.5, "volume": 10000000, "avg_volume_10d": 10000000},
        tech={"sma20": 100.0, "sma50": 98.0, "sma200": 95.0, "rsi": 50.0, "atr": 2.0},
        suppliers=[{"symbol": "FAB", "pct_change": -12.5, "news_sentiment": "BEARISH", "criticality": "EXTREME"}],
        customers=[{"symbol": "BUYER", "pct_change": -1.0, "news_sentiment": "NEUTRAL", "revenue_share_pct": 20.0}],
        competitors=[{"symbol": "PEER", "pct_change": 1.0, "news_sentiment": "NEUTRAL", "threat_level": "MEDIUM"}],
        expected_bias="BEARISH CATALYST",
        min_primary_score=40.0,
        min_vol_prob=50.0
    ))

    # Case 6: Customer Demand Shock / Massive Capex Deployment
    cases.append(run_test_case(
        name="6. Enterprise Customer Capex Surge Spillover",
        headline="Component Demand Solid Ahead of Enterprise Datacenter Buildouts",
        quote={"symbol": "MU", "price": 115.0, "prev_close": 113.0, "open": 114.5, "pct_change": 1.8, "volume": 20000000, "avg_volume_10d": 15000000},
        tech={"sma20": 110.0, "sma50": 105.0, "sma200": 98.0, "rsi": 58.0, "atr": 3.2},
        suppliers=[{"symbol": "CHEM", "pct_change": 0.5, "news_sentiment": "NEUTRAL", "criticality": "MEDIUM"}],
        customers=[
            {"symbol": "NVDA", "pct_change": 4.5, "news_sentiment": "BULLISH", "revenue_share_pct": 25.0},
            {"symbol": "MSFT", "pct_change": 2.5, "news_sentiment": "BULLISH", "revenue_share_pct": 20.0}
        ],
        competitors=[{"symbol": "SKHX", "pct_change": 1.0, "news_sentiment": "NEUTRAL", "threat_level": "HIGH"}],
        expected_bias="BULLISH CATALYST",
        min_primary_score=70.0,
        min_vol_prob=60.0
    ))

    # Case 7: FDA Blockbuster Drug Approval (Biotech)
    cases.append(run_test_case(
        name="7. FDA Phase 3 Breakthrough Therapy Approval",
        headline="FDA Grants Full Breakthrough Therapy Approval for Landmark Oncology Drug with Global Patent",
        quote={"symbol": "BIOT", "price": 220.0, "prev_close": 205.0, "open": 218.0, "pct_change": 7.3, "volume": 12000000, "avg_volume_10d": 3000000},
        tech={"sma20": 208.0, "sma50": 200.0, "sma200": 190.0, "rsi": 68.0, "atr": 5.5},
        suppliers=[{"symbol": "LAB", "pct_change": 1.0, "news_sentiment": "NEUTRAL", "criticality": "LOW"}],
        customers=[{"symbol": "DIST", "pct_change": 2.0, "news_sentiment": "BULLISH", "revenue_share_pct": 30.0}],
        competitors=[{"symbol": "RIVAL", "pct_change": -3.0, "news_sentiment": "BEARISH", "threat_level": "HIGH"}],
        expected_bias="BULLISH CATALYST",
        min_primary_score=82.0,
        min_vol_prob=75.0
    ))

    # Case 8: Antitrust & DOJ Monopolization Lawsuit
    cases.append(run_test_case(
        name="8. DOJ Antitrust Lawsuit & Subpoena",
        headline="Department of Justice Files Major Antitrust Lawsuit Seeking Structural Breakup and Massive Penalties",
        quote={"symbol": "MEGA", "price": 170.0, "prev_close": 176.0, "open": 171.0, "pct_change": -3.4, "volume": 35000000, "avg_volume_10d": 22000000},
        tech={"sma20": 174.0, "sma50": 172.0, "sma200": 165.0, "rsi": 44.0, "atr": 3.8},
        suppliers=[{"symbol": "SUPP", "pct_change": -0.8, "news_sentiment": "NEUTRAL", "criticality": "LOW"}],
        customers=[{"symbol": "ADVT", "pct_change": -1.5, "news_sentiment": "BEARISH", "revenue_share_pct": 25.0}],
        competitors=[{"symbol": "PEER1", "pct_change": 2.5, "news_sentiment": "BULLISH", "threat_level": "HIGH"}],
        expected_bias="BEARISH CATALYST",
        min_primary_score=78.0,
        min_vol_prob=70.0
    ))

    # Case 9: M&A Buyout Cash Offer at 45% Premium
    cases.append(run_test_case(
        name="9. M&A Buyout Agreement at 45% Premium",
        headline="Strategic Buyer Signs Definitive Agreement to Acquire Outstanding Shares at 45% Premium",
        quote={"symbol": "TGT", "price": 42.0, "prev_close": 32.0, "open": 41.5, "pct_change": 31.2, "volume": 45000000, "avg_volume_10d": 5000000},
        tech={"sma20": 33.0, "sma50": 34.0, "sma200": 35.0, "rsi": 78.0, "atr": 1.5},
        suppliers=[],
        customers=[],
        competitors=[],
        expected_bias="BULLISH CATALYST",
        min_primary_score=85.0,
        min_vol_prob=85.0
    ))

    # Case 10: Baseline Consolidation / Low Beta Quiescent Day
    cases.append(run_test_case(
        name="10. Baseline Consolidation / Zero News Quiescence",
        headline="",
        quote={"symbol": "UTIL", "price": 65.0, "prev_close": 65.1, "open": 65.0, "pct_change": -0.15, "volume": 2000000, "avg_volume_10d": 2200000},
        tech={"sma20": 65.2, "sma50": 65.0, "sma200": 64.8, "rsi": 49.5, "atr": 0.8},
        suppliers=[],
        customers=[],
        competitors=[],
        expected_bias="BALANCED / DUAL-SIDED VOLATILITY",
        min_primary_score=0.0,
        min_vol_prob=0.0
    ))

    # Case 11: Counter-Trend Test (Bearish Technicals Overridden by Jensen Huang News)
    cases.append(run_test_case(
        name="11. Counter-Trend: Bearish 5m Trend Overridden by CEO Return",
        headline="NVIDIA Board Reinstates Jensen Huang as President, CEO and Director; Shares Surge +30%",
        quote={"symbol": "NVDA", "price": 120.0, "prev_close": 122.0, "open": 119.0, "pct_change": -1.6, "volume": 80000000, "avg_volume_10d": 40000000},
        # Technicals are in a deep downtrend: below all SMAs, RSI low
        tech={"sma20": 130.0, "sma50": 135.0, "sma200": 140.0, "rsi": 32.0, "atr": 4.5},
        suppliers=[{"symbol": "TSM", "pct_change": 1.5, "news_sentiment": "BULLISH", "criticality": "CRITICAL"}],
        customers=[{"symbol": "MSFT", "pct_change": 2.0, "news_sentiment": "BULLISH", "revenue_share_pct": 20.0}],
        competitors=[],
        expected_bias="BULLISH CATALYST",
        min_primary_score=85.0,  # Fundamental catalyst MUST override bearish technicals!
        min_vol_prob=80.0
    ))

    # Case 12: Overbought Trap Test (Bullish 5m Trend Overridden by CEO Fired)
    cases.append(run_test_case(
        name="12. Overbought Trap: Bullish 5m Trend Overridden by CEO Fired",
        headline="Board Abruptly Fires CEO Following Accounting Fraud and DOJ Criminal Subpoena",
        quote={"symbol": "HIGH", "price": 250.0, "prev_close": 248.0, "open": 249.0, "pct_change": 0.8, "volume": 15000000, "avg_volume_10d": 12000000},
        # Technicals are at all-time highs: above all SMAs, RSI 78
        tech={"sma20": 240.0, "sma50": 230.0, "sma200": 210.0, "rsi": 78.0, "atr": 5.0},
        suppliers=[],
        customers=[],
        competitors=[{"symbol": "PEER", "pct_change": 3.0, "news_sentiment": "BULLISH", "threat_level": "HIGH"}],
        expected_bias="BEARISH CATALYST",
        min_primary_score=85.0,  # Fundamental shock MUST override overbought technicals!
        min_vol_prob=80.0
    ))

    # Print Report Table
    print("\n" + "=" * 115)
    print(f"{'CASE NAME':<48} | {'SENTIMENT':<16} | {'MOV PROB':<9} | {'UP':<5} | {'DOWN':<5} | {'SPREAD':<7} | {'STATUS'}")
    print("=" * 115)

    all_passed = True
    for c in cases:
        status = "PASSED" if c["passed"] else f"FAILED: {c['errors']}"
        if not c["passed"]:
            all_passed = False
        print(f"{c['case_name']:<48} | {c['headline_sentiment']:<16} | {c['movement_prob']:<9.1f} | {c['up_score']:<5.1f} | {c['down_score']:<5.1f} | {c['net_spread']:<+7.1f} | {status}")

    print("=" * 115)
    if all_passed:
        print("\n>>> ALL 12 FINANCIAL CALIBRATION SCENARIOS PASSED PERFECTLY! <<<")
    else:
        print("\n>>> SOME CASES FAILED! CHECK DIAGNOSTICS ABOVE. <<<")
        exit(1)


if __name__ == "__main__":
    main()
