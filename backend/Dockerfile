FROM python:3.12-slim

# Закрытый контур: без обращений к внешним сервисам в рантайме.
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-rus \
        tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/src ./src
COPY data/matrix ./data/matrix
RUN pip install --no-cache-dir -e . "pytesseract>=0.3.10" "Pillow>=10"

EXPOSE 8000
CMD ["uvicorn", "kontur.presentation.api:app", "--host", "0.0.0.0", "--port", "8000"]
