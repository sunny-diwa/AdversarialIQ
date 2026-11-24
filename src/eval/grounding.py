"""
AdversarialIQ Agentic Architecture - Factuality & Grounding Evaluator
Inspects agent responses against live grounded financial data (quotes, technicals, SEC EDGAR, news)
to detect hallucinations, price discrepancies, and entity confusion.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from src.core.config import SP500_MAP

logger = logging.getLogger("GroundingEvaluator")


class FactualityGroundingEvaluator:
    """Evaluates whether agent output is rigorously grounded in real market data."""

    @classmethod
    def evaluate(
        cls,
        response_text: str,
        symbol: str,
        grounded_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[float, List[str], Dict[str, Any]]:
        """
        Evaluates agent response for factual accuracy and data grounding.
        Returns: (score [0-100], issues_list, audit_details)
        """
        sym = symbol.strip().upper()
        meta = SP500_MAP.get(sym, {})
        company_name = meta.get("name", sym)
        score = 100.0
        issues = []
        details = {}

        grounded = grounded_data or {}
        market_quote = grounded.get("quote", {})
        live_price = float(market_quote.get("price") or grounded.get("price") or 0.0)

        # 1. Entity Matching & Company Name Alignment
        # If response mentions another major company as the primary subject, flag confusion
        text_lower = response_text.lower()
        if sym in SP500_MAP:
            # Check for blatant ticker/name mismatches (e.g. discussing Apple when symbol is NVDA)
            other_leaders = {"AAPL": "Apple", "NVDA": "Nvidia", "MSFT": "Microsoft", "TSLA": "Tesla", "AMZN": "Amazon"}
            for other_sym, other_name in other_leaders.items():
                if other_sym != sym:
                    if f"{other_name.lower()} corporation" in text_lower and company_name.lower() not in text_lower:
                        score -= 25.0
                        issues.append(f"ENTITY_CONFUSION: Content references {other_name} instead of target {company_name}")

        # 2. Price Grounding & Hallucination Audit
        # Extract quoted prices like "$145.20" or "at $145"
        if live_price > 0:
            price_matches = re.findall(r"\$(\d+(?:\.\d{1,2})?)", response_text)
            detected_prices = [float(p) for p in price_matches]
            details["detected_prices"] = detected_prices
            details["grounded_price"] = live_price

            # If agent mentions a price that diverges by > 20% from actual without stating target/historical
            divergent_prices = []
            for dp in detected_prices:
                # Ignore very low numbers that might be ATR or share counts
                if dp < 5.0 and live_price > 50.0:
                    continue
                ratio = abs(dp - live_price) / live_price
                # If diverging by > 25%, check if text explicitly marks it as target, stop, or historical
                if ratio > 0.25:
                    surrounding = response_text[max(0, response_text.find(f"${dp}") - 30):response_text.find(f"${dp}") + 30].lower()
                    is_contextual = any(k in surrounding for k in ["target", "stop", "52w", "high", "low", "sma", "resistance", "support", "ath"])
                    if not is_contextual:
                        divergent_prices.append(dp)

            if divergent_prices:
                penalty = min(30.0, len(divergent_prices) * 15.0)
                score -= penalty
                issues.append(f"PRICE_DIVERGENCE: Mentioned price(s) {divergent_prices} diverge >25% from live quote (${live_price:.2f})")

        # 3. Technical Indicator Range Verifications
        # RSI must be between 0 and 100
        rsi_match = re.search(r"\bRSI(?:\s*(?:=|is|at|momentum)?)?\s*(\d+(?:\.\d+)?)", response_text, re.IGNORECASE)
        if rsi_match:
            rsi_val = float(rsi_match.group(1))
            details["cited_rsi"] = rsi_val
            if rsi_val < 0 or rsi_val > 100:
                score -= 20.0
                issues.append(f"INVALID_TECHNICAL_RANGE: Cited RSI {rsi_val} is outside [0, 100]")

        # 4. Empty / Vague Content Audit
        word_count = len(re.findall(r"\w+", response_text))
        details["word_count"] = word_count
        if word_count < 25 and not any(k in text_lower for k in ["hello", "hi", "help"]):
            score -= 30.0
            issues.append("INSUFFICIENT_SUBSTANCE: Response lacks quantitative detail or explanatory depth")

        final_score = max(0.0, min(100.0, score))
        details["grounding_score"] = final_score
        return final_score, issues, details
