# Backend: FastAPI + LangGraph agents + OCR for Indian scripts
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Tesseract OCR with Indian language packs (reads scanned and legacy-font PDFs)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-eng tesseract-ocr-hin tesseract-ocr-mar tesseract-ocr-ben \
        tesseract-ocr-tam tesseract-ocr-tel tesseract-ocr-kan tesseract-ocr-mal tesseract-ocr-guj \
        tesseract-ocr-pan tesseract-ocr-ori tesseract-ocr-urd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data /models \
    && chown -R app:app /app/data /models
USER app

# data/: SQLite (if no Postgres), uploads, embedded Qdrant. /models: embedding model cache.
ENV DATA_DIR=/app/data \
    MODEL_CACHE_DIR=/models
VOLUME ["/app/data", "/models"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1

CMD ["uvicorn", "--factory", "app.main:create_app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
