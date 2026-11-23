"""
Langfuse Cloud Observability & Tracing Integration
Provides zero-latency, non-blocking telemetry export to Langfuse Cloud for:
1. LangChain Agents (via Langfuse CallbackHandler)
2. Adversarial Tribunal Debates (Bull, Bear, Judge traces)
3. Multi-Provider LLM Invocations (Groq, Gemini, Mistral, NVIDIA NIM, Ollama)
"""

import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("LangfuseTracker")

_LANGFUSE_CLIENT = None
_INIT_ATTEMPTED = False


def _get_env_config():
    pub = os.getenv("LANGFUSE_PUBLIC_KEY", "").strip()
    sec = os.getenv("LANGFUSE_SECRET_KEY", "").strip()
    host = os.getenv("LANGFUSE_HOST", "https://cloud.langfuse.com").strip()
    return pub, sec, host


def is_langfuse_configured() -> bool:
    pub, sec, _ = _get_env_config()
    return bool(pub and sec)


def get_langfuse_client():
    """Lazily initializes the Langfuse client if API keys are configured."""
    global _LANGFUSE_CLIENT, _INIT_ATTEMPTED
    if _LANGFUSE_CLIENT is not None:
        return _LANGFUSE_CLIENT

    if _INIT_ATTEMPTED:
        return None

    _INIT_ATTEMPTED = True
    pub, sec, host = _get_env_config()
    if not (pub and sec):
        logger.info("Langfuse Cloud API keys not detected in .env; tracing running in local mode.")
        return None

    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=pub,
            secret_key=sec,
            host=host
        )
        # Quick validation
        if hasattr(client, "auth_check"):
            try:
                client.auth_check()
                logger.info(f"Connected to Langfuse Cloud at {host}")
            except Exception as e:
                logger.warning(f"Langfuse auth check warning: {e}")
        _LANGFUSE_CLIENT = client
        return _LANGFUSE_CLIENT
    except Exception as e:
        logger.error(f"Failed to initialize Langfuse client: {e}")
        return None


def get_langfuse_callback(
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    tags: Optional[List[str]] = None
):
    """
    Returns a Langfuse CallbackHandler for LangChain agents if Langfuse is configured.
    Returns None if unconfigured so LangChain runs normally without overhead.
    """
    if not is_langfuse_configured():
        return None

    try:
        from langfuse.langchain import CallbackHandler

        pub, sec, host = _get_env_config()
        handler = CallbackHandler(
            public_key=pub,
            secret_key=sec,
            host=host,
            session_id=session_id or "adversarialiq-session",
            user_id=user_id or "trader",
            tags=tags or ["AdversarialIQ", "LangChain"]
        )
        return handler
    except Exception as e:
        logger.warning(f"Could not initialize Langfuse LangChain CallbackHandler: {e}")
        return None


def get_langfuse_status() -> Dict[str, Any]:
    """Returns connectivity and configuration status for the UI observability modal."""
    pub, sec, host = _get_env_config()
    configured = bool(pub and sec)

    client = get_langfuse_client() if configured else None
    connected = client is not None

    return {
        "configured": configured,
        "connected": connected,
        "host": host,
        "public_key_preview": (pub[:8] + "..." + pub[-4:]) if len(pub) > 12 else ("Configured" if pub else "Not Set"),
        "status_label": "CLOUD ACTIVE" if connected else ("KEYS PRESENT (CONNECTING)" if configured else "STANDBY / LOCAL ONLY")
    }


class LangfuseTracker:
    """Convenience helper to record direct traces and spans to Langfuse Cloud."""

    @classmethod
    def trace_generation(
        cls,
        name: str,
        model: str,
        prompt: str,
        completion: str,
        latency_ms: int,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ):
        """Asynchronously exports an LLM generation event to Langfuse."""
        client = get_langfuse_client()
        if not client:
            return

        try:
            # Approximate token counts
            p_tokens = max(1, len(prompt) // 4)
            c_tokens = max(1, len(completion) // 4)

            trace = client.trace(
                name=name,
                metadata=metadata or {},
                tags=tags or ["AdversarialIQ"]
            )
            trace.generation(
                name=f"{name}-{model}",
                model=model,
                input=prompt,
                output=completion,
                usage={
                    "prompt_tokens": p_tokens,
                    "completion_tokens": c_tokens,
                    "total_tokens": p_tokens + c_tokens
                },
                metadata={
                    "latency_ms": latency_ms,
                    **(metadata or {})
                }
            )
        except Exception as e:
            logger.debug(f"Langfuse generation trace record failed: {e}")

    @classmethod
    def trace_tribunal(
        cls,
        symbol: str,
        bull_thesis: str,
        bear_thesis: str,
        judge_ruling: str,
        conviction_score: int,
        action: str,
        risk_approved: bool,
        bracket: Optional[Dict[str, Any]] = None
    ):
        """Records a comprehensive multi-agent adversarial debate session to Langfuse."""
        client = get_langfuse_client()
        if not client:
            return

        try:
            trace = client.trace(
                name=f"Tribunal-{symbol}",
                tags=["Tribunal", "AdversarialIQ", action],
                metadata={
                    "symbol": symbol,
                    "conviction_score": conviction_score,
                    "recommended_action": action,
                    "risk_approved": risk_approved,
                    "bracket": bracket or {}
                }
            )

            # Agent Bull span
            trace.span(
                name=f"Bull-Advocate-{symbol}",
                input=f"Analyze {symbol} bullish setup",
                output=bull_thesis,
                metadata={"role": "Bull Prosecution"}
            )

            # Agent Bear span
            trace.span(
                name=f"Bear-Adversary-{symbol}",
                input=f"Cross-examine {symbol} risks",
                output=bear_thesis,
                metadata={"role": "Bear Defense"}
            )

            # Chief Judge span
            trace.span(
                name=f"Chief-Judge-Arbiter-{symbol}",
                input="Adjudicate Bull vs Bear arguments",
                output=judge_ruling,
                metadata={"role": "Chief Judge", "conviction": conviction_score, "action": action}
            )
        except Exception as e:
            logger.debug(f"Langfuse tribunal trace record failed: {e}")
