# =============================================================================
# AdversarialIQ - Production Cloud Container Image
# Multi-stage secure build with non-root app user and lightweight footprint
# =============================================================================

FROM python:3.12-slim as builder

WORKDIR /app

# Install build dependencies for C extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    git \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Final runtime image
FROM python:3.12-slim

WORKDIR /app

# Install runtime curl for healthchecks
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy installed python wheels from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Create non-root application user
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Copy application source code
COPY --chown=appuser:appgroup src/ /app/src/
COPY --chown=appuser:appgroup static/ /app/static/
COPY --chown=appuser:appgroup server.py /app/server.py
COPY --chown=appuser:appgroup terminal_trader.py /app/terminal_trader.py

# Create data directory for persistent SQLite ledgers with proper permissions
RUN mkdir -p /app/data && chown -R appuser:appgroup /app/data /app

USER appuser

EXPOSE 8080

# Health check probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8080/api/health || exit 1

CMD ["uvicorn", "server.py:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2"]
