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

# Create the runtime identity only after privileged package installation. Keep
# /app root-owned: the application may write only to explicitly mounted paths
# or runtime tmpfs locations.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --no-create-home \
        --home-dir /nonexistent --shell /usr/sbin/nologin app

USER 10001:10001

EXPOSE 8000
CMD ["uvicorn", "kontur.presentation.api:app", "--host", "0.0.0.0", "--port", "8000"]
