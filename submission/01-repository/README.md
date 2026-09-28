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
не меняет ([ADR-0001](../../docs/adr/0001-llm-never-sets-verdict.md)).

## Что фиксирует сборку

Лицензия — Apache-2.0, [`LICENSE`](../../LICENSE). Сторонние пакеты —
[`THIRD_PARTY_NOTICES.md`](../../docs/THIRD_PARTY_NOTICES.md).
Зависимости Python — [`backend/requirements.lock`](../../backend/requirements.lock).
Web и gateway — [`web/package-lock.json`](../../web/package-lock.json),
[`gateway/package-lock.json`](../../gateway/package-lock.json).
Веса OCR лежат в [`vendor/ocr/`](../../vendor/ocr/), сверка хешей —
[`ocr_weights.lock.json`](../../backend/src/kontur/infrastructure/ocr_weights.lock.json).

Workflows: [`ci.yml`](../../.github/workflows/ci.yml),
[`relay.yml`](../../.github/workflows/relay.yml),
[`sync-lifecycle.yml`](../../.github/workflows/sync-lifecycle.yml),
[`gate-l.yml`](../../.github/workflows/gate-l.yml).
Ruleset `main-pr-and-ci`, id 23890545: PR обязателен, force-push и удаление
ветки запрещены, обязательных ревью 0. Зелёный job `backend` — это
`conclusion=success`, `runner_id` не 0, непустые `runner_name` и `steps`.
Ruleset гейты I/J/K не закрывает.
