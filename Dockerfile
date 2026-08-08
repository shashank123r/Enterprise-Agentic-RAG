# ──────────────────────────────────────────────
# Stage 1: Build
# ──────────────────────────────────────────────
FROM python:3.13-slim AS builder

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
COPY app/ app/
RUN pip install --upgrade pip && \
    pip install build && \
    python -m build --wheel

# ──────────────────────────────────────────────
# Stage 2: Production Runtime
# ──────────────────────────────────────────────
FROM python:3.13-slim AS production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONHASHSEED=random

WORKDIR /app

RUN addgroup --system --gid 1001 rag && \
    adduser --system --uid 1001 --gid 1001 rag && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
        libpq-dev \
        libmagic1t64 \
        curl \
        tesseract-ocr \
        tesseract-ocr-eng \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/dist/*.whl .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir *.whl && \
    rm *.whl

COPY --chown=rag:rag alembic.ini .
COPY --chown=rag:rag alembic/ alembic/
COPY --chown=rag:rag app/ app/
COPY --chown=rag:rag scripts/ scripts/

RUN mkdir -p logs uploads data && \
    chown -R rag:rag logs uploads data

USER rag

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health/live || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4", "--loop", "uvloop"]
