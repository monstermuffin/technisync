FROM python:3.9-slim as builder

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

FROM python:3.9-slim

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.9/site-packages /usr/local/lib/python3.9/site-packages
COPY --from=builder /app .

RUN mkdir -p /data

ENV DB_PATH=/data/dns_sync.db
ENV CONFIG_PATH=/app/config.yaml

CMD ["python", "main.py"]