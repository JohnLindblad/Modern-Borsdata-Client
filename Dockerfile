FROM python:3.12-slim

ENV PYTHONPATH=/app/src \
    PORT=8000 \
    HOST=0.0.0.0 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt requirements-http.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-http.txt

COPY src ./src

RUN useradd --system --create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import sys, urllib.request; \
body = urllib.request.urlopen(f'http://127.0.0.1:{__import__(\"os\").environ.get(\"PORT\", \"8000\")}/health', timeout=3).read().decode().strip(); \
sys.exit(0 if body == 'ok' else 1)"

CMD ["python", "-m", "mcp_server.http_app"]
