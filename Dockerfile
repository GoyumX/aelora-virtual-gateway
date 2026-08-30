FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    AELORA_GATEWAY_HOST=0.0.0.0 \
    AELORA_GATEWAY_PORT=4100 \
    AELORA_GATEWAY_DB=/app/data/gateway.db \
    AELORA_GATEWAY_RELOAD=false

WORKDIR /app

RUN apt-get update \
    && apt-get install --no-install-recommends --yes gosu \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system aelora \
    && adduser --system --ingroup aelora aelora

COPY pyproject.toml README.md ./
COPY src ./src
COPY docker-entrypoint.sh /usr/local/bin/gateway-entrypoint
RUN python -m pip install --no-cache-dir . \
    && mkdir -p /app/data \
    && chown aelora:aelora /app/data \
    && chmod 0755 /usr/local/bin/gateway-entrypoint

EXPOSE 4100

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import os,urllib.request; p=os.getenv('PORT',os.getenv('AELORA_GATEWAY_PORT','4100')); urllib.request.urlopen(f'http://127.0.0.1:{p}/api/health',timeout=3)"]

ENTRYPOINT ["/usr/local/bin/gateway-entrypoint"]
CMD ["aelora-virtual-gateway"]
