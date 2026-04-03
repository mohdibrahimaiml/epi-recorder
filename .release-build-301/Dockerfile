FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    EPI_GATEWAY_STORAGE_DIR=/data

WORKDIR /app

COPY pyproject.toml README.md LICENSE setup.py MANIFEST.in /app/
COPY epi_core /app/epi_core
COPY epi_cli /app/epi_cli
COPY epi_gateway /app/epi_gateway
COPY epi_recorder /app/epi_recorder
COPY epi_viewer_static /app/epi_viewer_static
COPY web_viewer /app/web_viewer

RUN pip install . && mkdir -p /data

EXPOSE 8787

HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/ready', timeout=4)"

CMD ["python", "-m", "uvicorn", "epi_gateway.main:app", "--host", "0.0.0.0", "--port", "8787"]
