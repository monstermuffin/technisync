FROM python:3.12-slim AS builder

ENV POETRY_NO_INTERACTION=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

WORKDIR /app

COPY pyproject.toml poetry.toml poetry.lock ./

RUN pip install poetry==1.8.3 --no-cache-dir &&\
    poetry install --without dev --no-root &&\
    rm -rf $POETRY_CACHE_DIR

FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    DB_PATH=/data/dns_sync.db \
    CONFIG_PATH=/app/config.yaml

WORKDIR /app

COPY --from=builder ${VIRTUAL_ENV} ${VIRTUAL_ENV}
COPY main.py .
COPY technisync ./technisync/

RUN mkdir -p /data

VOLUME ["/data"]

ENTRYPOINT ["python", "main.py"]
