# extract-api runtime image. Text + pre-extracted PDF only (no OCR), so no system
# OCR libraries are installed by design.
FROM ghcr.io/astral-sh/uv:0.11.21 AS uv

FROM python:3.13-slim

WORKDIR /app

# Keep Docker's lock reader aligned with CI. The final image contains only the
# copied binary, not the uv image layers.
COPY --from=uv /uv /usr/local/bin/uv

# The base image already supplies Python 3.13. Do not silently download another
# interpreter while building the image.
ENV UV_PYTHON_DOWNLOADS=0 \
    PATH="/app/.venv/bin:$PATH"

# --locked rejects a stale lock instead of resolving the project ranges. Runtime
# images omit development dependencies and install the application non-editably.
COPY pyproject.toml uv.lock README.md ./
COPY LICENSE RELICENSING.md ./
COPY LICENSES ./LICENSES
COPY api ./api
COPY schemas ./schemas
COPY llm ./llm
COPY harness ./harness
RUN uv sync --locked --no-dev --no-editable --python 3.13

# The service writes its idempotency database under /data. Create it before dropping
# privileges so a keyed request cannot fail lazily with a SQLite permission error.
RUN groupadd --gid 10001 extract \
    && useradd --uid 10001 --gid extract --no-create-home --shell /usr/sbin/nologin extract \
    && install --directory --owner=extract --group=extract /data

ENV IDEMPOTENCY_DB_PATH=/data/idempotency.sqlite

USER extract

EXPOSE 8200

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8200/healthz').status==200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8200"]
