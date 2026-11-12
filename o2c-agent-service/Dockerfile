# Multi-stage Python build — non-root runtime image
FROM python:3.12-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/* && pip install "poetry>=2.0,<3"
COPY pyproject.toml poetry.lock* ./
RUN poetry config virtualenvs.in-project true \
    && poetry install --only main --no-root --no-interaction

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN groupadd -r appgroup && useradd -r -g appgroup -u 1001 appuser
COPY --from=builder /build/.venv /app/.venv
COPY src/ /app/src/
COPY policies/ /app/policies/
COPY knowledge/ /app/knowledge/
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH="/app/src"
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
CMD ["uvicorn", "o2c_agent_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
