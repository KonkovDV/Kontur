# Репозиторий

**Ссылка для формы:** https://github.com/KonkovDV/Kontur

Публичный репозиторий. Лицензия кода — Apache-2.0 (`LICENSE`).
Гейты I/J/K/L открыты.

## Структура

| Путь | Содержимое |
|---|---|
| [`backend/`](../../backend/) | Домен, сверка, API |
| [`gateway/`](../../gateway/) | Вход: лимиты размера и частоты |
| [`web/`](../../web/) | Экран инспектора |
| [`contracts/`](../../contracts/) | OpenAPI и JSON-схемы |
| [`data/matrix/`](../../data/matrix/) | 132 параметра как данные |
| [`docs/`](../../docs/) | Архитектура, метрики, пробелы |

## Сборка

Канон — [`README.md`](../../README.md). С корня клона:

```text
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
```

Проверка: http://127.0.0.1:3000/api/v1/healthz .
Перед сборкой задайте `KONTUR_GIT_SHA` равным `git rev-parse HEAD`:
каталог `.git` в образ не копируется.

`CONFIRMED_VIOLATION` пишет только инспектор. Модель поле `finding_status`
не меняет (ADR-0001).
