"""
LLM Observability & Structured Trace Logger
Records and indexes every prompt, response, latency, token estimation, and failover event.
Provides real-time tracing metrics for the AdversarialIQ Terminal and API.
"""

import collections
import logging
import sqlite3
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from src.core.config import DB_FILE

logger = logging.getLogger("LLMTracer")

# In-memory fast ring buffer for last 200 traces
_TRACE_BUFFER = collections.deque(maxlen=200)


def init_trace_db():
    """Initializes SQLite table for persistent LLM observability traces."""
    with sqlite3.connect(str(DB_FILE)) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS llm_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trace_id TEXT UNIQUE,
                timestamp TEXT NOT NULL,
                provider TEXT NOT NULL,
                model TEXT NOT NULL,
                latency_ms INTEGER NOT NULL,
                prompt_tokens_est INTEGER NOT NULL,
                completion_tokens_est INTEGER NOT NULL,
                symbol TEXT,
                status TEXT NOT NULL, -- SUCCESS, FAILOVER, ERROR
                prompt_preview TEXT,
                response_preview TEXT,
                error_message TEXT
            )
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_traces_provider ON llm_traces(provider);
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_traces_timestamp ON llm_traces(timestamp);
        """)
        conn.commit()


try:
    init_trace_db()
except Exception as e:
    logger.error(f"Error initializing trace database: {e}")


class LLMTracer:
    """Manages recording and querying LLM operational traces."""

    @classmethod
    def record_trace(
        cls,
        provider: str,
        model: str,
        latency_ms: int,
        prompt: str,
        response: str,
        status: str = "SUCCESS",
        symbol: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> Dict[str, Any]:
        """Records a new inference trace in both memory ring-buffer and persistent SQLite."""
        trace_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Approximate token count (1 token ~= 4 chars)
        prompt_tokens = max(1, len(prompt) // 4)
        completion_tokens = max(1, len(response) // 4)

        record = {
            "trace_id": trace_id,
            "timestamp": timestamp,
            "provider": provider,
            "model": model,
            "latency_ms": int(latency_ms),
            "prompt_tokens_est": prompt_tokens,
            "completion_tokens_est": completion_tokens,
            "total_tokens_est": prompt_tokens + completion_tokens,
            "symbol": symbol or "MARKET",
            "status": status.upper(),
            "prompt_preview": prompt[:160] + ("..." if len(prompt) > 160 else ""),
            "response_preview": response[:200] + ("..." if len(response) > 200 else ""),
            "error_message": error_message or ""
        }

        # Append to fast ring buffer
        _TRACE_BUFFER.appendleft(record)

        # Persist to SQLite
        try:
            with sqlite3.connect(str(DB_FILE)) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO llm_traces (
                        trace_id, timestamp, provider, model, latency_ms,
                        prompt_tokens_est, completion_tokens_est, symbol,
                        status, prompt_preview, response_preview, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    trace_id, timestamp, provider, model, int(latency_ms),
                    prompt_tokens, completion_tokens, symbol or "MARKET",
                    status.upper(), record["prompt_preview"], record["response_preview"],
                    error_message or ""
                ))
                conn.commit()
        except Exception as e:
            logger.debug(f"Trace persistence notice: {e}")

        return record

    @classmethod
    def get_traces(cls, limit: int = 50, provider: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns recent execution traces from ring buffer with optional provider filtering."""
        traces = list(_TRACE_BUFFER)
        if provider:
            p = provider.lower().strip()
            traces = [t for t in traces if p in t["provider"].lower()]
        return traces[:limit]

    @classmethod
    def get_metrics(cls) -> Dict[str, Any]:
        """Computes aggregate observability metrics across recent invocations."""
        traces = list(_TRACE_BUFFER)
        if not traces:
            return {
                "total_calls": 0,
                "avg_latency_ms": 0,
                "total_tokens_est": 0,
                "success_rate_pct": 100.0,
                "provider_breakdown": {}
            }

        total_calls = len(traces)
        avg_latency = sum(t["latency_ms"] for t in traces) / total_calls
        total_tokens = sum(t["total_tokens_est"] for t in traces)
        success_count = sum(1 for t in traces if t["status"] in ("SUCCESS", "FAILOVER"))
        success_rate = (success_count / total_calls * 100)

        providers: Dict[str, int] = {}
        for t in traces:
            p = t["provider"]
            providers[p] = providers.get(p, 0) + 1

        return {
            "total_calls": total_calls,
            "avg_latency_ms": round(avg_latency, 1),
            "total_tokens_est": total_tokens,
            "success_rate_pct": round(success_rate, 1),
            "provider_breakdown": providers
        }
