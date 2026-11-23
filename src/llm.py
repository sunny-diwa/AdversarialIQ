"""
Multi-Provider LLM Engine with On-Demand Switching, Health Ping & Automatic Failover
Supports Groq Cloud API, Local Ollama, and Autonomous Institutional Quant Engine.
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional
import requests

from src.config import GROQ_API_KEY, OLLAMA_BASE_URL

logger = logging.getLogger("SP500Trader.LLM")

class LLMManager:
    """
    Manages LLM providers with automatic failover and on-demand health testing.
    Protects user rate limits by strictly avoiding continuous background polling.
    """

    GROQ_MODELS = [
        {"id": "llama-3.3-70b-versatile", "name": "Groq: Llama 3.3 70B (Recommended)", "context": 128000},
        {"id": "llama-3.1-8b-instant", "name": "Groq: Llama 3.1 8B (Ultra Fast)", "context": 128000},
        {"id": "mixtral-8x7b-32768", "name": "Groq: Mixtral 8x7B (32k Context)", "context": 32768}
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
                        "error": f"HTTP {res.status_code} from {url}"
                    }
            except Exception as e:
                return {
                    "status": "DOWN",
                    "latency_ms": int((time.time() - start_time) * 1000),
                    "provider": "Ollama Local",
                    "error": f"Ollama unreachable at {url} ({str(e)}). Is 'ollama serve' running?"
                }

        return {"status": "DOWN", "error": f"Unknown provider '{provider}'"}

    @classmethod
    def generate(
        cls,
        prompt: str,
        system_prompt: str,
        preferred_provider: str = "groq",
        model: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        ollama_base_url: Optional[str] = None,
        fallback_quant_func: Optional[Any] = None,
        target_symbol: str = "AAPL"
    ) -> Dict[str, Any]:
        """
        Executes conversational inference with automatic fallback:
        Preferred Provider -> Secondary Provider -> Autonomous Quant Engine.
        """
        provider = preferred_provider.lower().strip()
        errors = []

        # Attempt 1: Groq Cloud
        if provider == "groq":
            key = (groq_api_key or GROQ_API_KEY).strip()
            if key:
                try:
                    headers = {
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json"
                    }
                    body = {
                        "model": model or "llama-3.3-70b-versatile",
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 1200
                    }
                    res = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=body, timeout=16)
                    if res.status_code == 200:
                        content = res.json()["choices"][0]["message"]["content"]
                        return {
                            "response": content,
                            "provider": "Groq Cloud",
                            "model": model or "llama-3.3-70b-versatile",
                            "failover": False
                        }
                    else:
                        errors.append(f"Groq HTTP {res.status_code}: {res.text[:100]}")
                        logger.warning(f"Groq API error ({res.status_code}); triggering automatic failover...")
                except Exception as e:
                    errors.append(f"Groq error: {str(e)}")
                    logger.warning(f"Groq request exception ({e}); triggering automatic failover...")
            else:
                errors.append("Groq API key not provided; failing over to local or rule engine.")

        # Attempt 2: Local Ollama (if preferred or failed over from Groq)
        if provider in ["ollama", "groq"]:
            url = (ollama_base_url or OLLAMA_BASE_URL).rstrip("/")
            try:
                body = {
                    "model": model if provider == "ollama" else "llama3",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    "stream": False
                }
                res = requests.post(f"{url}/api/chat", json=body, timeout=20)
                if res.status_code == 200:
                    content = res.json().get("message", {}).get("content", "")
                    return {
                        "response": content,
                        "provider": "Ollama Local",
                        "model": body["model"],
                        "failover": provider != "ollama",
                        "note": "Automatically failed over to Ollama Local." if provider != "ollama" else None
                    }
                else:
                    errors.append(f"Ollama HTTP {res.status_code}")
            except Exception as e:
                errors.append(f"Ollama connection failed: {str(e)}")

        # Attempt 3: Ultimate Autonomous Quant Rule-Engine Fallback (Always Works)
        logger.info(f"Using Autonomous Quant Engine fallback for {target_symbol}. Prior errors: {errors}")
        if fallback_quant_func:
            fallback_res = fallback_quant_func(prompt, target_symbol)
            response_text = fallback_res.get("response", "Quant analysis complete.")
        else:
            response_text = f"Quantitative rule engine active for {target_symbol}."

        failover_note = "Auto-switched to Autonomous Quant Engine (Groq/Ollama reached rate limits or offline)." if provider != "quant" else None

        return {
            "response": response_text,
            "provider": "Quantitative Rule Engine (Autonomous)",
            "failover": provider != "quant",
            "note": failover_note,
            "system_errors": errors if errors else None
        }

    @classmethod
    def get_models_catalog(cls) -> Dict[str, Any]:
        """Returns detected local Ollama models and available Groq models."""
        ollama_models = []
        try:
            res = requests.get(f"{OLLAMA_BASE_URL.rstrip('/')}/api/tags", timeout=2)
            if res.status_code == 200:
                for m in res.json().get("models", []):
                    name = m.get("name")
                    ollama_models.append({"id": name, "name": f"Ollama: {name} (Local)"})
        except Exception:
            pass

        return {
            "groq": cls.GROQ_MODELS,
            "ollama": ollama_models
        }
