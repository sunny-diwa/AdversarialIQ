"""
Multi-Provider LLM Engine with On-Demand Switching, Health Ping & Automatic Failover
Supports:
1. Groq Cloud API (Llama 3.3 70B, Llama 3.1 8B, Mixtral 8x7B)
2. Google AI Studio / Gemini API (Gemini 2.0 Flash, Gemini 1.5 Pro, Gemini 1.5 Flash)
3. Mistral AI (mistral-small-latest, mistral-large-latest, codestral-latest)
4. NVIDIA NIM API (z-ai/glm-5.3-flash, meta/llama-3.3-70b-instruct, mistralai/mistral-large-2-instruct)
5. Ollama Local Daemon (Local on-device inference)
6. Autonomous Quantitative Rule Engine (Zero external keys required)
"""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
import requests
import yfinance as yf

from src.config import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    MISTRAL_API_KEY,
    NVIDIA_API_KEY,
    OLLAMA_BASE_URL,
    SP500_MAP,
)
from src.market_data import compute_indicators

logger = logging.getLogger("SP500Trader.LLM")


class LLMManager:
    """
    Manages multi-provider LLM inference with automatic failover and on-demand health testing.
    Protects user rate limits by strictly avoiding continuous background polling.
    """

    GROQ_MODELS = [
        {"id": "llama-3.3-70b-versatile", "name": "Groq: Llama 3.3 70B (Recommended)", "context": 128000},
        {"id": "llama-3.1-8b-instant", "name": "Groq: Llama 3.1 8B (Ultra Fast)", "context": 128000},
        {"id": "mixtral-8x7b-32768", "name": "Groq: Mixtral 8x7B (32k Context)", "context": 32768}
    ]

    GEMINI_MODELS = [
        {"id": "gemini-2.0-flash", "name": "Google Gemini 2.0 Flash (Recommended)", "context": 1048576},
        {"id": "gemini-1.5-flash", "name": "Google Gemini 1.5 Flash (Fast)", "context": 1048576},
        {"id": "gemini-1.5-pro", "name": "Google Gemini 1.5 Pro (Deep Reasoning)", "context": 2097152}
    ]

    MISTRAL_MODELS = [
        {"id": "mistral-small-latest", "name": "Mistral Small (Fast / Efficient)", "context": 32768},
        {"id": "mistral-large-latest", "name": "Mistral Large (High Precision)", "context": 128000},
        {"id": "codestral-latest", "name": "Mistral Codestral (Code & Quant)", "context": 256000}
    ]

    NVIDIA_MODELS = [
        {"id": "z-ai/glm-5.3-flash", "name": "NVIDIA: GLM 5.3 Flash (Ultra Fast)", "context": 128000},
        {"id": "meta/llama-3.3-70b-instruct", "name": "NVIDIA: Llama 3.3 70B Instruct", "context": 128000},
        {"id": "mistralai/mistral-large-2-instruct", "name": "NVIDIA: Mistral Large 2", "context": 128000}
    ]

    @classmethod
    def ping_provider(
        cls,
        provider: str,
        model: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Sends a single lightweight ping request to verify provider connectivity on demand.
        Triggered ONLY when user selects/switches a provider in settings.
        """
        provider = provider.lower().strip()
        start_time = time.time()

        if provider == "quant":
            return {
                "status": "LIVE",
                "latency_ms": 1,
                "provider": "Quantitative Rule Engine",
                "model": "rule-based-v3",
                "message": "Autonomous engine is active and ready with zero API keys required."
            }

        elif provider == "groq":
            key = (api_key or GROQ_API_KEY).strip()
            if not key:
                return {
                    "status": "DOWN",
                    "latency_ms": 0,
                    "provider": "Groq Cloud",
                    "error": "Missing Groq API Key. Enter key in settings or set GROQ_API_KEY env."
                }

            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            body = {
                "model": model or "llama-3.1-8b-instant",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 2
            }
            try:
                res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body, timeout=5)
                latency = int((time.time() - start_time) * 1000)
                if res.status_code == 200:
                    return {
                        "status": "LIVE",
                        "latency_ms": latency,
                        "provider": "Groq Cloud",
                        "model": model or "llama-3.1-8b-instant",
                        "message": f"Connected to Groq Cloud ({latency}ms roundtrip)."
                    }
                elif res.status_code == 429:
                    return {
                        "status": "DOWN",
                        "latency_ms": latency,
                        "provider": "Groq Cloud",
                        "error": "Rate limit exceeded (HTTP 429). Will fail over automatically."
                    }
                else:
                    return {
                        "status": "DOWN",
                        "latency_ms": latency,
                        "provider": "Groq Cloud",
                        "error": f"HTTP {res.status_code}: {res.text[:120]}"
                    }
            except Exception as e:
                return {
                    "status": "DOWN",
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "provider": "Groq Cloud",
                    "error": f"Connection error: {str(e)}"
                }

        elif provider in ("gemini", "google"):
            key = (api_key or GEMINI_API_KEY).strip()
            if not key:
                return {
                    "status": "DOWN",
                    "latency_ms": 0,
                    "provider": "Google AI Studio (Gemini)",
                    "error": "Missing Gemini API Key. Enter key in settings or set GEMINI_API_KEY env."
                }

            use_model = model or "gemini-2.0-flash"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent?key={key}"
            body = {
                "contents": [{"parts": [{"text": "ping"}]}],
                "generationConfig": {"maxOutputTokens": 2}
            }
            try:
                res = requests.post(url, json=body, timeout=5)
                latency = int((time.time() - start_time) * 1000)
                if res.status_code == 200:
                    return {
                        "status": "LIVE",
                        "latency_ms": latency,
                        "provider": "Google AI Studio (Gemini)",
                        "model": use_model,
                        "message": f"Connected to Google Gemini ({latency}ms roundtrip)."
                    }
                else:
                    return {
                        "status": "DOWN",
                        "latency_ms": latency,
                        "provider": "Google AI Studio (Gemini)",
                        "error": f"HTTP {res.status_code}: {res.text[:120]}"
                    }
            except Exception as e:
                return {
                    "status": "DOWN",
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "provider": "Google AI Studio (Gemini)",
                    "error": f"Connection error: {str(e)}"
                }

        elif provider == "mistral":
            key = (api_key or MISTRAL_API_KEY).strip()
            if not key:
                return {
                    "status": "DOWN",
                    "latency_ms": 0,
                    "provider": "Mistral AI",
                    "error": "Missing Mistral API Key. Enter key in settings or set MISTRAL_API_KEY env."
                }

            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            body = {
                "model": model or "mistral-small-latest",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 2
            }
            try:
                res = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=body, timeout=5)
                latency = int((time.time() - start_time) * 1000)
                if res.status_code == 200:
                    return {
                        "status": "LIVE",
                        "latency_ms": latency,
                        "provider": "Mistral AI",
                        "model": model or "mistral-small-latest",
                        "message": f"Connected to Mistral AI ({latency}ms roundtrip)."
                    }
                else:
                    return {
                        "status": "DOWN",
                        "latency_ms": latency,
                        "provider": "Mistral AI",
                        "error": f"HTTP {res.status_code}: {res.text[:120]}"
                    }
            except Exception as e:
                return {
                    "status": "DOWN",
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "provider": "Mistral AI",
                    "error": f"Connection error: {str(e)}"
                }

        elif provider in ("nvidia", "nim"):
            key = (api_key or NVIDIA_API_KEY).strip()
            if not key:
                return {
                    "status": "DOWN",
                    "latency_ms": 0,
                    "provider": "NVIDIA NIM API",
                    "error": "Missing NVIDIA API Key. Enter key in settings or set NVIDIA_API_KEY env."
                }

            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json"
            }
            body = {
                "model": model or "z-ai/glm-5.3-flash",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 2
            }
            try:
                res = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=headers, json=body, timeout=5)
                latency = int((time.time() - start_time) * 1000)
                if res.status_code == 200:
                    return {
                        "status": "LIVE",
                        "latency_ms": latency,
                        "provider": "NVIDIA NIM API",
                        "model": model or "z-ai/glm-5.3-flash",
                        "message": f"Connected to NVIDIA NIM API ({latency}ms roundtrip)."
                    }
                else:
                    return {
                        "status": "DOWN",
                        "latency_ms": latency,
                        "provider": "NVIDIA NIM API",
                        "error": f"HTTP {res.status_code}: {res.text[:120]}"
                    }
            except Exception as e:
                return {
                    "status": "DOWN",
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "provider": "NVIDIA NIM API",
                    "error": f"Connection error: {str(e)}"
                }

        elif provider == "ollama":
            url = (base_url or OLLAMA_BASE_URL).rstrip("/")
            try:
                res = requests.get(f"{url}/api/tags", timeout=3)
                latency = int((time.time() - start_time) * 1000)
                if res.status_code == 200:
                    models = [m.get("name") for m in res.json().get("models", [])]
                    return {
                        "status": "LIVE",
                        "latency_ms": latency,
                        "provider": "Ollama Local",
                        "models_found": models,
                        "message": f"Connected to local Ollama daemon ({len(models)} local models found)."
                    }
                else:
                    return {
                        "status": "DOWN",
                        "latency_ms": latency,
                        "provider": "Ollama Local",
                        "error": f"Ollama daemon returned HTTP {res.status_code}"
                    }
            except Exception as e:
                return {
                    "status": "DOWN",
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "provider": "Ollama Local",
                    "error": f"Local Ollama is offline at {url}. Start with 'ollama serve'."
                }

        return {"status": "UNKNOWN", "provider": provider, "error": f"Unknown provider '{provider}'"}

    @classmethod
    def get_models_catalog(cls) -> Dict[str, Any]:
        """Returns detected local Ollama models alongside cloud catalogs."""
        ollama_models = []
        try:
            resp = requests.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=1.5)
            if resp.status_code == 200:
                for m in resp.json().get("models", []):
                    ollama_models.append({
                        "id": m["name"],
                        "name": f"Ollama Local: {m['name']}"
                    })
        except Exception:
            pass

        return {
            "groq": cls.GROQ_MODELS,
            "gemini": cls.GEMINI_MODELS,
            "mistral": cls.MISTRAL_MODELS,
            "nvidia": cls.NVIDIA_MODELS,
            "ollama": ollama_models,
            "ollama_online": len(ollama_models) > 0
        }

    @classmethod
    def generate(
        cls,
        prompt: str,
        system_prompt: str,
        preferred_provider: str = "groq",
        model: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        mistral_api_key: Optional[str] = None,
        nvidia_api_key: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
        symbol: str = "AAPL"
    ) -> Dict[str, Any]:
        """
        Executes prompt across selected provider with automatic failover chain:
        Preferred -> Groq -> Gemini -> Mistral -> NVIDIA -> Ollama -> Quant Rule-Engine
        """
        prov = preferred_provider.lower().strip()

        # 1. Try Groq Cloud
        if prov == "groq":
            key = (groq_api_key or GROQ_API_KEY).strip()
            if key:
                try:
                    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                    body = {
                        "model": model or "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.25,
                        "max_tokens": 1200
                    }
                    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body, timeout=18)
                    if res.status_code == 200:
                        content = res.json()["choices"][0]["message"]["content"]
                        return {"response": content, "provider": "Groq Cloud", "model": model}
                    logger.warning(f"Groq API returned HTTP {res.status_code}, attempting failover...")
                except Exception as e:
                    logger.warning(f"Groq invocation failed: {e}, attempting failover...")

        # 2. Try Google Gemini
        if prov in ("gemini", "google") or (prov != "quant" and (gemini_api_key or GEMINI_API_KEY)):
            key = (gemini_api_key or GEMINI_API_KEY).strip()
            if key:
                use_model = model if (prov in ("gemini", "google") and model) else "gemini-2.0-flash"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent?key={key}"
                body = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "systemInstruction": {"parts": [{"text": system_prompt}]},
                    "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1200}
                }
                try:
                    res = requests.post(url, json=body, timeout=18)
                    if res.status_code == 200:
                        content = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                        return {"response": content, "provider": "Google Gemini", "model": use_model}
                except Exception as e:
                    logger.warning(f"Gemini invocation failed: {e}")

        # 3. Try Mistral AI
        if prov == "mistral" or (prov != "quant" and (mistral_api_key or MISTRAL_API_KEY)):
            key = (mistral_api_key or MISTRAL_API_KEY).strip()
            if key:
                use_model = model if (prov == "mistral" and model) else "mistral-small-latest"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                body = {
                    "model": use_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.2,
                    "max_tokens": 1200
                }
                try:
                    res = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=body, timeout=18)
                    if res.status_code == 200:
                        content = res.json()["choices"][0]["message"]["content"]
                        return {"response": content, "provider": "Mistral AI", "model": use_model}
                except Exception as e:
                    logger.warning(f"Mistral invocation failed: {e}")

        # 4. Try NVIDIA NIM API
        if prov in ("nvidia", "nim") or (prov != "quant" and (nvidia_api_key or NVIDIA_API_KEY)):
            key = (nvidia_api_key or NVIDIA_API_KEY).strip()
            if key:
                use_model = model if (prov in ("nvidia", "nim") and model) else "z-ai/glm-5.3-flash"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                body = {
                    "model": use_model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1200
                }
                try:
                    res = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=headers, json=body, timeout=18)
                    if res.status_code == 200:
                        content = res.json()["choices"][0]["message"]["content"]
                        return {"response": content, "provider": "NVIDIA NIM", "model": use_model}
                except Exception as e:
                    logger.warning(f"NVIDIA invocation failed: {e}")

        # 5. Try Ollama Local
        if prov == "ollama" or (prov != "quant"):
            base = (ollama_base_url or OLLAMA_BASE_URL).rstrip("/")
            try:
                res = requests.post(
                    f"{base}/api/chat",
                    json={
                        "model": model or "llama3",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "stream": False
                    },
                    timeout=20
                )
                if res.status_code == 200:
                    content = res.json().get("message", {}).get("content", "")
                    if content:
                        return {"response": content, "provider": "Ollama Local", "model": model or "llama3"}
            except Exception:
                pass

        # 6. Built-in Quantitative Rule Engine Fallback
        quant_res = cls._fallback_quant_agent(prompt, symbol)
        return {
            "response": quant_res["response"],
            "provider": "Quantitative Rule Engine (Autonomous)",
            "failover": True,
            "symbol": symbol
        }

    @classmethod
    def _fallback_quant_agent(cls, prompt: str, default_symbol: str) -> Dict[str, Any]:
        """Built-in Institutional Quantitative Analyst Engine."""
        sym = default_symbol.upper()
        words = re.findall(r"\b[A-Z]{1,5}\b", prompt.upper())
        for w in words:
            if w in SP500_MAP:
                sym = w
                break

        try:
            t = yf.Ticker(sym)
            hist = t.history(period="6mo", interval="1d")
            fast = t.fast_info
            price = fast.last_price or 100.0
            prev = fast.previous_close or price
            chg = price - prev
            pct = (chg / prev * 100) if prev else 0.0

            hist = compute_indicators(hist)
            latest = hist.iloc[-1]
            rsi = float(latest.get("RSI", 50.0))
            macd = float(latest.get("MACD", 0.0))
            sig = float(latest.get("MACD_Signal", 0.0))
            sma20 = float(latest.get("SMA20", price))
            sma50 = float(latest.get("SMA50", price))
            bb_up = float(latest.get("BB_Upper", price * 1.05))
            bb_low = float(latest.get("BB_Lower", price * 0.95))

            recent_high = float(hist["High"].tail(20).max())
            recent_low = float(hist["Low"].tail(20).min())

            score = 0
            reasons = []

            if rsi < 35:
                score += 2
                reasons.append(f"RSI is oversold at {rsi:.1f} (Mean-reversion bounce opportunity)")
            elif rsi > 65:
                score -= 2
                reasons.append(f"RSI is overbought at {rsi:.1f} (Extended momentum)")
            else:
                reasons.append(f"RSI is neutral at {rsi:.1f}")

            if macd > sig:
                score += 2
                reasons.append(f"MACD line ({macd:.2f}) is bullish above Signal ({sig:.2f})")
            else:
                score -= 2
                reasons.append(f"MACD line ({macd:.2f}) is bearish below Signal ({sig:.2f})")

            if price > sma50:
                score += 1
                reasons.append(f"Trading above 50-day SMA (${sma50:.2f}) - Uptrend intact")
            else:
                score -= 1
                reasons.append(f"Trading below 50-day SMA (${sma50:.2f}) - Short-term supply resistance")

            verdict = "STRONG BUY" if score >= 3 else ("BUY" if score >= 1 else ("NEUTRAL / HOLD" if score == 0 else ("SELL" if score >= -2 else "STRONG SELL")))

            entry = price
            stop_loss = round(recent_low * 0.985, 2)
            target = round(recent_high * 1.02, 2)
            rr_ratio = round(abs(target - entry) / max(0.01, abs(entry - stop_loss)), 2)

            reply = f"""### 📊 Institutional Quantitative Trader Analysis: **{sym}**

**Current Price:** `${price:.2f}` ({'+' if chg >= 0 else ''}{chg:.2f} / {'+' if pct >= 0 else ''}{pct:.2f}%)  
**Composite Technical Verdict:** **`{verdict}`** (Quant Score: {score}/5)

---

#### 📈 Key Technical Indicators:
- **RSI (14):** `{rsi:.1f}` — {'🟢 Oversold' if rsi <= 35 else ('🔴 Overbought' if rsi >= 65 else '⚪ Neutral')}
- **MACD (12,26,9):** `{macd:.2f}` vs Signal `{sig:.2f}` ({'🟢 Bullish Crossover' if macd > sig else '🔴 Bearish Alignment'})
- **Moving Averages:** 20 SMA: `${sma20:.2f}` | 50 SMA: `${sma50:.2f}`
- **Bollinger Bands:** Upper: `${bb_up:.2f}` | Lower: `${bb_low:.2f}`

#### 🎯 Actionable Trading Setup:
- **Recommended Entry:** `${entry:.2f}`
- **Stop Loss:** `${stop_loss:.2f}` (Below 20D Low)
- **Target Price:** `${target:.2f}` (Near Resistance)
- **Risk / Reward Ratio:** `1 : {rr_ratio}`

#### 💡 Analyst Insights:
- {'; '.join(reasons)}.
- To route an order to your paper desk, say: `Buy {sym} <quantity>` or `Sell {sym} <quantity>`.
"""
            return {"response": reply, "symbol": sym, "data": {"price": price, "verdict": verdict}}
        except Exception as e:
            return {"response": f"Quant analysis error for {sym}: {e}", "symbol": sym}
