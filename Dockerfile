FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AELORA_GATEWAY_HOST=0.0.0.0 \
    AELORA_GATEWAY_PORT=4100 \
    AELORA_GATEWAY_DB=/app/data/gateway.db \
    AELORA_GATEWAY_RELOAD=false

WORKDIR /app

RUN addgroup --system aelora && adduser --system --ingroup aelora aelora

COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir . && mkdir -p /app/data && chown -R aelora:aelora /app/data

USER aelora
EXPOSE 4100
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:4100/api/health', timeout=3)"]

CMD ["aelora-virtual-gateway"]
