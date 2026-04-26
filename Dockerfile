FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml README.md ./
COPY jadwal ./jadwal

RUN pip install --no-cache-dir --upgrade pip build \
    && python -m build --wheel

FROM python:3.12-slim

WORKDIR /app
COPY --from=builder /build/dist/*.whl /tmp/

RUN pip install --no-cache-dir /tmp/*.whl \
    && rm /tmp/*.whl

EXPOSE 8000

# Healthcheck hits /healthz
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')"

CMD ["uvicorn", "jadwal.api:app", "--host", "0.0.0.0", "--port", "8000"]
