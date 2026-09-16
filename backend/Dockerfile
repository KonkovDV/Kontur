FROM python:3.12-slim

# Закрытый контур: без обращений к внешним сервисам в рантайме.
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

EXPOSE 8000
CMD ["uvicorn", "kontur.presentation.api:app", "--host", "0.0.0.0", "--port", "8000"]
