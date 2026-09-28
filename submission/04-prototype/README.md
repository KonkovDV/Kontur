# Прототип

**Ссылка для формы:** https://github.com/KonkovDV/Kontur/tree/main/submission/04-prototype

Публичного адреса стенда нет. Прототип — этот репозиторий.
Ответ организатора О-2: проверка идёт из комплекта, ссылка решением
не оценивается. Внешние LLM, OCR и VLM в зачётный прогон не входят.

## Запуск

С корня клона, Docker Compose v2:

```text
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
```

Открыть http://127.0.0.1:3000 .
Проверка: http://127.0.0.1:3000/api/v1/healthz .
Учебный токен: `inspector-1@OBJ-DEMO-COLD-START/INSPECTOR`.
Кнопка «Учебный комплект» кладёт синтетические ПД, РД и ИД.
Документы организатора на стенд не класть.

До выбора эталона правила PZ-001, KR-055 и AR-041 в
`CLARIFICATION_REQUIRED`. После выбора инспектора те же три кода —
кандидаты, не подтверждённые нарушения.

Пакетный прогон без экрана, каталоги `input` и `out` рядом с compose:

```text
docker compose --profile runner run --rm package-runner
```

Инспектор находки в этой команде не подтверждает. `violation_count` остаётся 0.

## Что видно

Карточка: файл, страница, SHA-256, polygon. Решение инспектора пишется
в аудит. Пачкой подтверждаются только отмеченные `CANDIDATE`.
Подтверждение брокера не является ACK РиН.

## Границы

DWG — `UNSUPPORTED_FORMAT`. Архив — `ARCHIVE_NOT_EXPANDED`.
XML принимается и не разбирается (`ACCEPTED_UNPARSED`).
DOCX читается абзацами и таблицами. Холодный запуск 27.09 и 28.09
записан в [`DEMO_COLD_START.md`](../../docs/DEMO_COLD_START.md):
сеть хоста не отключалась.
