# extract-api runtime image. Text + pre-extracted PDF only (no OCR), so no system
# OCR libraries are installed by design.
FROM python:3.13-slim

WORKDIR /app

# Install dependencies from the pinned project metadata.
COPY pyproject.toml README.md ./
COPY api ./api
COPY schemas ./schemas
COPY llm ./llm
COPY harness ./harness
RUN pip install --no-cache-dir .

EXPOSE 8200

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8200/healthz').status==200 else 1)"

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8200"]
