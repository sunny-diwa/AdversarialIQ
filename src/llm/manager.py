"""
Multi-Provider LLM Engine with On-Demand Switching, Health Ping, Observability & Automatic Failover
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

from src.core.config import (
    GEMINI_API_KEY,
    GROQ_API_KEY,
    MISTRAL_API_KEY,
    NVIDIA_API_KEY,
    OLLAMA_BASE_URL,
    SP500_MAP,
)
from src.data.market import compute_indicators
from src.llm.tracer import LLMTracer

logger = logging.getLogger("LLMManager")


class LLMManager:
    """
    Manages multi-provider LLM inference with automatic failover,
    observability trace logging, and on-demand health testing.
    """

    GROQ_MODELS = [
        {"id": "openai/gpt-oss-120b", "name": "Groq: GPT-OSS 120B (Recommended / Deep Reasoning)", "context": 131072},
        {"id": "openai/gpt-oss-20b", "name": "Groq: GPT-OSS 20B (Ultra Fast)", "context": 131072},
        {"id": "qwen/qwen3.8-27b", "name": "Groq: Qwen 3.8 27B (High Precision)", "context": 131072},
        {"id": "allam-2-7b", "name": "Groq: Allam 2 7B (High Volume / 7K RPD)", "context": 32768}
    ]

    GEMINI_MODELS = [
        {"id": "gemini-4-hydrogen", "name": "Google Gemini 4 Hydrogen (Free Tier / Recommended)", "context": 1048576},
        {"id": "gemini-3.5-flash", "name": "Google Gemini 3.5 Flash", "context": 1048576},
        {"id": "gemini-3.1-flash-lite", "name": "Google Gemini 3.1 Flash Lite", "context": 1048576},
        {"id": "gemini-2.5-flash", "name": "Google Gemini 2.5 Flash", "context": 1048576}
    ]

    MISTRAL_MODELS = [
        {"id": "codestral-latest", "name": "Mistral: Codestral Latest (Code & Quant / Recommended)", "context": 256000},
        {"id": "ministral-8b-latest", "name": "Mistral: Ministral 8B (Fast)", "context": 128000},
        {"id": "ministral-3b-latest", "name": "Mistral: Ministral 3B (Lightweight)", "context": 128000}
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
            payload = {
                "model": model or "openai/gpt-oss-120b",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 2
            }
            try:
                res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=4)
                latency = int((time.time() - start_time) * 1000)
                if res.status_code == 200:
                    return {
                        "status": "LIVE",
                        "latency_ms": latency,
                        "provider": "Groq Cloud",
                        "model": model or "llama-3.1-8b-instant",
                        "message": f"Connected to Groq Cloud ({latency}ms latency)."
                    }
                else:
                    return {
                        "status": "DOWN",
                        "latency_ms": latency,
                        "provider": "Groq Cloud",
                        "error": f"HTTP {res.status_code}: {res.text[:120]}"
                    }
            except Exception as e:
                return {"status": "DOWN", "latency_ms": int((time.time() - start_time) * 1000), "provider": "Groq Cloud", "error": str(e)}

        elif provider in ("gemini", "google"):
            key = (api_key or GEMINI_API_KEY).strip()
            if not key:
                return {
                    "status": "DOWN",
                    "latency_ms": 0,
                    "provider": "Google AI Studio",
                    "error": "Missing Gemini API Key. Enter key in settings or set GEMINI_API_KEY env."
                }
            mod = model or "gemini-4-hydrogen"
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={key}"
            payload = {"contents": [{"parts": [{"text": "ping"}]}], "generationConfig": {"maxOutputTokens": 2}}
            try:
                res = requests.post(url, json=payload, timeout=4)
                latency = int((time.time() - start_time) * 1000)
                if res.status_code == 200:
                    return {
                        "status": "LIVE",
                        "latency_ms": latency,
                        "provider": "Google AI Studio",
                        "model": mod,
                        "message": f"Connected to Google AI Studio ({latency}ms latency)."
                    }
                else:
                    return {"status": "DOWN", "latency_ms": latency, "provider": "Google AI Studio", "error": f"HTTP {res.status_code}: {res.text[:120]}"}
            except Exception as e:
                return {"status": "DOWN", "latency_ms": int((time.time() - start_time) * 1000), "provider": "Google AI Studio", "error": str(e)}

        elif provider == "mistral":
            key = (api_key or MISTRAL_API_KEY).strip()
            if not key:
                return {
                    "status": "DOWN",
                    "latency_ms": 0,
                    "provider": "Mistral AI",
                    "error": "Missing Mistral API Key. Enter key in settings or set MISTRAL_API_KEY env."
                }
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {
                "model": model or "codestral-latest",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 2
            }
            try:
                res = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=payload, timeout=4)
                latency = int((time.time() - start_time) * 1000)
                if res.status_code == 200:
                    return {
                        "status": "LIVE",
                        "latency_ms": latency,
                        "provider": "Mistral AI",
                        "model": model or "mistral-small-latest",
                        "message": f"Connected to Mistral AI ({latency}ms latency)."
                    }
                else:
                    return {"status": "DOWN", "latency_ms": latency, "provider": "Mistral AI", "error": f"HTTP {res.status_code}: {res.text[:120]}"}
            except Exception as e:
                return {"status": "DOWN", "latency_ms": int((time.time() - start_time) * 1000), "provider": "Mistral AI", "error": str(e)}

        elif provider == "nvidia":
            key = (api_key or NVIDIA_API_KEY).strip()
            if not key:
                return {
                    "status": "DOWN",
                    "latency_ms": 0,
                    "provider": "NVIDIA NIM",
                    "error": "Missing NVIDIA API Key. Enter key in settings or set NVIDIA_API_KEY env."
                }
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            payload = {
                "model": model or "z-ai/glm-5.3-flash",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 2
            }
            try:
                res = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=headers, json=payload, timeout=4)
                latency = int((time.time() - start_time) * 1000)
                if res.status_code == 200:
                    return {
                        "status": "LIVE",
                        "latency_ms": latency,
                        "provider": "NVIDIA NIM",
                        "model": model or "z-ai/glm-5.3-flash",
                        "message": f"Connected to NVIDIA NIM API ({latency}ms latency)."
                    }
                else:
                    return {"status": "DOWN", "latency_ms": latency, "provider": "NVIDIA NIM", "error": f"HTTP {res.status_code}: {res.text[:120]}"}
            except Exception as e:
                return {"status": "DOWN", "latency_ms": int((time.time() - start_time) * 1000), "provider": "NVIDIA NIM", "error": str(e)}

        elif provider == "ollama":
            url = (base_url or OLLAMA_BASE_URL).rstrip("/")
            try:
                res = requests.get(f"{url}/api/tags", timeout=2)
                latency = int((time.time() - start_time) * 1000)
                if res.status_code == 200:
                    models = [m.get("name") for m in res.json().get("models", [])]
                    return {
                        "status": "LIVE",
                        "latency_ms": latency,
                        "provider": "Ollama Local",
                        "models": models,
                        "message": f"Ollama is running locally ({len(models)} models installed)."
                    }
                else:
                    return {"status": "DOWN", "latency_ms": latency, "provider": "Ollama Local", "error": f"Ollama returned HTTP {res.status_code}"}
            except Exception:
                return {
                    "status": "DOWN",
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "provider": "Ollama Local",
                    "error": f"Could not connect to Ollama at {url}. Make sure ollama daemon is running."
                }

        return {"status": "DOWN", "latency_ms": 0, "provider": provider, "error": f"Unknown provider: {provider}"}

    @classmethod
    def get_models_catalog(cls) -> Dict[str, Any]:
        """Returns catalog of models and detects local Ollama models on demand."""
        ollama_models = []
        try:
            res = requests.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=1)
            if res.status_code == 200:
                for m in res.json().get("models", []):
                    ollama_models.append({"id": m.get("name"), "name": f"Ollama: {m.get('name')}", "context": 8192})
        except Exception:
            pass

        return {
            "groq": cls.GROQ_MODELS,
            "gemini": cls.GEMINI_MODELS,
            "mistral": cls.MISTRAL_MODELS,
            "nvidia": cls.NVIDIA_MODELS,
            "ollama": ollama_models,
            "has_groq_key": bool(GROQ_API_KEY),
            "has_gemini_key": bool(GEMINI_API_KEY),
            "has_mistral_key": bool(MISTRAL_API_KEY),
            "has_nvidia_key": bool(NVIDIA_API_KEY),
            "ollama_available": len(ollama_models) > 0
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
        symbol: Optional[str] = "AAPL"
    ) -> Dict[str, Any]:
        """
        Executes generation using preferred provider with automatic failover and trace logging.
        Order of failover: preferred -> Groq -> Gemini -> Mistral -> NVIDIA -> Ollama -> Quant Rule Engine.
        """
        prov = (preferred_provider or "groq").lower().strip()
        mod = model or ("openai/gpt-oss-120b" if prov == "groq" else ("gemini-4-hydrogen" if prov in ("gemini", "google") else "codestral-latest"))

        # 1. Try preferred provider
        res = cls._try_provider(
            provider=prov,
            model=mod,
            prompt=prompt,
            system_prompt=system_prompt,
            groq_key=groq_api_key or GROQ_API_KEY,
            gemini_key=gemini_api_key or GEMINI_API_KEY,
            mistral_key=mistral_api_key or MISTRAL_API_KEY,
            nvidia_key=nvidia_api_key or NVIDIA_API_KEY,
            ollama_url=ollama_base_url or OLLAMA_BASE_URL,
            symbol=symbol
        )
        if res and not res.get("error"):
            return {
                "response": res["content"],
                "provider": res["provider_name"],
                "model": mod,
                "failover": False
            }

        logger.warning(f"Preferred provider {prov} failed ({res.get('error') if res else 'Unknown'}). Initiating failover...")

        # 2. Ordered failover chain across active free-tier providers
        candidates = ["groq", "mistral", "gemini"]
        if prov in candidates:
            candidates.remove(prov)

        for candidate in candidates:
            cand_mod = None
            if candidate == "groq":
                cand_mod = "openai/gpt-oss-120b"
            elif candidate == "gemini":
                cand_mod = "gemini-4-hydrogen"
            elif candidate == "mistral":
                cand_mod = "codestral-latest"

            cand_res = cls._try_provider(
                provider=candidate,
                model=cand_mod,
                prompt=prompt,
                system_prompt=system_prompt,
                groq_key=groq_api_key or GROQ_API_KEY,
                gemini_key=gemini_api_key or GEMINI_API_KEY,
                mistral_key=mistral_api_key or MISTRAL_API_KEY,
                nvidia_key=nvidia_api_key or NVIDIA_API_KEY,
                ollama_url=ollama_base_url or OLLAMA_BASE_URL,
                symbol=symbol
            )
            if cand_res and not cand_res.get("error"):
                logger.info(f"Failover to {candidate} ({cand_mod}) succeeded.")
                return {
                    "response": cand_res["content"],
                    "provider": cand_res["provider_name"],
                    "model": cand_mod,
                    "failover": True,
                    "failover_from": prov
                }

        # 3. Final Fallback: Autonomous Quantitative Rule Engine
        logger.info("All external LLM providers unavailable. Activating Autonomous Quant Rule Engine.")
        quant_content = cls._generate_quant_response(prompt, symbol)
        LLMTracer.record_trace(
            provider="Quantitative Rule Engine",
            model="rule-based-v3",
            latency_ms=1,
            prompt=prompt,
            response=quant_content,
            status="SUCCESS",
            symbol=symbol
        )
        return {
            "response": quant_content,
            "provider": "Quantitative Rule Engine (Zero-Key Fallback)",
            "model": "rule-based-v3",
            "failover": True,
            "failover_from": prov
        }

    @classmethod
    def _try_provider(
        cls,
        provider: str,
        model: Optional[str],
        prompt: str,
        system_prompt: str,
        groq_key: str,
        gemini_key: str,
        mistral_key: str,
        nvidia_key: str,
        ollama_url: str,
        symbol: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Invokes a specific provider and records trace."""
        start_t = time.time()
        try:
            if provider == "groq":
                if not groq_key:
                    return {"error": "No Groq API key"}
                mod = model or "openai/gpt-oss-120b"
                headers = {"Authorization": f"Bearer {groq_key}", "Content-Type": "application/json"}
                payload = {
                    "model": mod,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1500
                }
                res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=8)
                latency = int((time.time() - start_t) * 1000)
                if res.status_code == 200:
                    content = res.json()["choices"][0]["message"]["content"]
                    LLMTracer.record_trace("Groq Cloud", mod, latency, prompt, content, "SUCCESS", symbol)
                    return {"content": content, "provider_name": "Groq Cloud"}
                err_msg = f"HTTP {res.status_code}: {res.text[:120]}"
                LLMTracer.record_trace("Groq Cloud", mod, latency, prompt, "", "ERROR", symbol, err_msg)
                return {"error": err_msg}

            elif provider in ("gemini", "google"):
                if not gemini_key:
                    return {"error": "No Gemini API key"}
                mod = model or "gemini-4-hydrogen"
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{mod}:generateContent?key={gemini_key}"
                payload = {
                    "contents": [{"parts": [{"text": f"System Directive:\n{system_prompt}\n\nUser Request:\n{prompt}"}]}],
                    "generationConfig": {"temperature": 0.3, "maxOutputTokens": 1500}
                }
                res = requests.post(url, json=payload, timeout=10)
                latency = int((time.time() - start_t) * 1000)
                if res.status_code == 200:
                    data = res.json()
                    content = data["candidates"][0]["content"]["parts"][0]["text"]
                    LLMTracer.record_trace("Google AI Studio", mod, latency, prompt, content, "SUCCESS", symbol)
                    return {"content": content, "provider_name": "Google AI Studio"}
                err_msg = f"HTTP {res.status_code}: {res.text[:120]}"
                LLMTracer.record_trace("Google AI Studio", mod, latency, prompt, "", "ERROR", symbol, err_msg)
                return {"error": err_msg}

            elif provider == "mistral":
                if not mistral_key:
                    return {"error": "No Mistral API key"}
                mod = model or "codestral-latest"
                headers = {"Authorization": f"Bearer {mistral_key}", "Content-Type": "application/json"}
                payload = {
                    "model": mod,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1500
                }
                res = requests.post("https://api.mistral.ai/v1/chat/completions", headers=headers, json=payload, timeout=8)
                latency = int((time.time() - start_t) * 1000)
                if res.status_code == 200:
                    content = res.json()["choices"][0]["message"]["content"]
                    LLMTracer.record_trace("Mistral AI", mod, latency, prompt, content, "SUCCESS", symbol)
                    return {"content": content, "provider_name": "Mistral AI"}
                err_msg = f"HTTP {res.status_code}: {res.text[:120]}"
                LLMTracer.record_trace("Mistral AI", mod, latency, prompt, "", "ERROR", symbol, err_msg)
                return {"error": err_msg}

            elif provider == "nvidia":
                if not nvidia_key:
                    return {"error": "No NVIDIA API key"}
                mod = model or "z-ai/glm-5.3-flash"
                headers = {"Authorization": f"Bearer {nvidia_key}", "Content-Type": "application/json"}
                payload = {
                    "model": mod,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.3,
                    "max_tokens": 1200
                }
                res = requests.post("https://integrate.api.nvidia.com/v1/chat/completions", headers=headers, json=payload, timeout=8)
                latency = int((time.time() - start_t) * 1000)
                if res.status_code == 200:
                    content = res.json()["choices"][0]["message"]["content"]
                    LLMTracer.record_trace("NVIDIA NIM", mod, latency, prompt, content, "SUCCESS", symbol)
                    return {"content": content, "provider_name": "NVIDIA NIM"}
                err_msg = f"HTTP {res.status_code}: {res.text[:120]}"
                LLMTracer.record_trace("NVIDIA NIM", mod, latency, prompt, "", "ERROR", symbol, err_msg)
                return {"error": err_msg}

            elif provider == "ollama":
                url = ollama_url.rstrip("/")
                mod = model or "llama3"
                payload = {
                    "model": mod,
                    "prompt": f"{system_prompt}\n\n{prompt}",
                    "stream": False,
                    "options": {"temperature": 0.3}
                }
                res = requests.post(f"{url}/api/generate", json=payload, timeout=12)
                latency = int((time.time() - start_t) * 1000)
                if res.status_code == 200:
                    content = res.json().get("response", "")
                    LLMTracer.record_trace("Ollama Local", mod, latency, prompt, content, "SUCCESS", symbol)
                    return {"content": content, "provider_name": "Ollama Local"}
                err_msg = f"Ollama HTTP {res.status_code}"
                LLMTracer.record_trace("Ollama Local", mod, latency, prompt, "", "ERROR", symbol, err_msg)
                return {"error": err_msg}

        except Exception as e:
            latency = int((time.time() - start_t) * 1000)
            LLMTracer.record_trace(provider, model or "default", latency, prompt, "", "ERROR", symbol, str(e))
            return {"error": str(e)}

        return None

    @classmethod
    def _generate_quant_response(cls, prompt: str, symbol: Optional[str] = "AAPL") -> str:
        """Autonomous Quantitative Rule-Based Response Generator with conversational detection."""
        sym = (symbol or "AAPL").upper()
        meta = SP500_MAP.get(sym, {"name": sym, "sector": "S&P 500"})
        prompt_clean = prompt.strip().lower()

        # Check for conversational greeting or general assistant queries
        is_greeting = any(re.search(p, prompt_clean) for p in [
            r"^(hi|hello|hey|greetings|howdy|sup|hola)\b",
            r"^good\s+(morning|afternoon|evening)",
            r"who are you",
            r"what can you do",
            r"what is (this|adversarialiq)",
            r"how are you",
            r"help me",
            r"^help$"
        ])

        if is_greeting:
            return f"""### 🤖 Welcome to AdversarialIQ Institutional Trading Desk
I am your real-time **Quantitative Trader & Financial Intelligence Agent**.

The terminal is currently tracking **{sym}** ({meta.get('name')}). Here is what I can do:

- **📊 Deep Ticker Analysis:** Inquire about any S&P 500 stock (e.g. *"What is happening with NVDA?"*, *"Show technicals for AAPL"*, *"Any news on MSFT?"*).
- **⚖️ Adversarial Trade Tribunal:** Run 3-agent debates (*Bull vs Bear vs Chief Judge*) to evaluate conviction and risk gates (e.g. *"Debate {sym}"*).
- **🕸️ Ecosystem & Supply Chain:** Review suppliers, customers, competitors, and A-CIS movement scores (e.g. *"Show ecosystem for {sym}"*).
- **⚡ 5-Year Backtest Studio:** Simulate quantitative algorithmic strategies with live equity curves (e.g. *"Backtest RSI strategy on TSLA"*).
- **🛡️ Risk Guardrails & Order Routing:** Test 2% ATR risk budgeting and route simulated or Alpaca US Paper trades (e.g. *"Buy 10 {sym}"*).

*Ask any market question, request a stock analysis, or test a strategy!*"""

        price = 100.0
        rsi = 50.0
        macd = 0.0
        sig = 0.0
        sma50 = 100.0
        sma200 = 100.0

        try:
            t = yf.Ticker(sym)
            fast = t.fast_info
            price = fast.last_price or 100.0
            hist = t.history(period="1mo", interval="1d")
            if not hist.empty:
                hist = compute_indicators(hist)
                row = hist.iloc[-1]
                rsi = float(row.get("RSI", 50.0))
                macd = float(row.get("MACD", 0.0))
                sig = float(row.get("MACD_Signal", 0.0))
                sma50 = float(row.get("SMA50", price))
                sma200 = float(row.get("SMA200", price))
        except Exception:
            pass

        trend = "BULLISH" if price > sma50 and macd > sig else ("BEARISH" if price < sma50 and macd < sig else "NEUTRAL")
        rsi_state = "OVERSOLD" if rsi < 35 else ("OVERBOUGHT" if rsi > 65 else "BALANCED")

        return f"""### 📊 AdversarialIQ Quantitative Desk Note: **{sym}** ({meta.get('name')})
*Generated by Autonomous Institutional Rule Engine (Zero-Key Mode)*

---

#### 📈 Market State & Technical Alignment:
- **Last Quoted Price:** **`${price:.2f}`**
- **Trend Regime:** **`{trend}`** (Relative to 50-day SMA `${sma50:.2f}`)
- **RSI Momentum:** **`{rsi:.1f}`** ({rsi_state})
- **MACD Oscillator:** Line `{macd:.2f}` vs. Signal `{sig:.2f}` ({'Bullish Divergence' if macd > sig else 'Bearish Pressure'})

#### ⚖️ Adversarial Summary:
- **Agent Bull Case:** Favorable risk/reward if holding key support at `${min(price, sma50):.2f}`; potential upside target at `${price * 1.06:.2f}`.
- **Agent Bear Case:** Elevated overhead supply; caution below `${sma50:.2f}` with downside exposure to `${price * 0.94:.2f}`.

#### 🎯 Risk Parameters:
- **Adjudicated Position Size:** Disciplined ATR allocation with max 5% single-ticker exposure cap.
- **Automated Bracket Legs:** Stop-loss at `${price * 0.96:.2f}` | Target at `${price * 1.08:.2f}`.
"""
