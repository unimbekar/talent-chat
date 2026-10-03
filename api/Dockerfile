FROM python:3.12-slim-bookworm

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /uvx /bin/
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    FASTEMBED_CACHE_PATH=/opt/fastembed \
    HF_HOME=/opt/fastembed \
    PATH="/app/.venv/bin:$PATH"

COPY api/pyproject.toml api/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='nomic-ai/nomic-embed-text-v1.5', cache_dir='/opt/fastembed')" \
    && mkdir -p /app/.cache \
    && find /opt/fastembed -name tokenizer.json -exec cp {} /app/.cache/tokenizer.json \; \
    && test -s /app/.cache/tokenizer.json
RUN apt-get update \
    && apt-get install -y --no-install-recommends antiword \
    && rm -rf /var/lib/apt/lists/*
COPY api/app ./app
COPY api/alembic ./alembic
COPY api/alembic.ini ./alembic.ini
COPY api/pyproject.toml api/uv.lock ./
COPY configs /app/configs
RUN uv sync --frozen --no-dev
COPY api/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
