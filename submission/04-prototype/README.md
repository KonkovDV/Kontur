# Прототип

**Ссылка для формы:** https://github.com/KonkovDV/Kontur/tree/main/submission/04-prototype

Публичного адреса стенда нет. Прототип — этот репозиторий.
Ответ организатора О-2: проверка идёт из комплекта, ссылка решением
не оценивается. Внешние LLM, OCR и VLM в зачётный прогон не входят.
Время сценария ниже — не сессия Gate K и не порог «не больше 30 минут».

## Что нужно

Docker Compose v2. Свободные порты на `127.0.0.1`: `3000`, `8000`, `5432`,
`6379`, `5672`, `9000`. GPU не нужен.

## Три способа поднять

Сборка из клона, канон в [`README.md`](../../README.md):

```text
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
```

Офлайн, когда образы уже в tar: `docker load`, затем

```text
docker compose -f docker-compose.yml -f docker-compose.demo.yml -f docker-compose.offline.yml up -d --no-build
```

Запись 27.09 и 28.09 — [`DEMO_COLD_START.md`](../../docs/DEMO_COLD_START.md).
Сеть хоста в тех прогонах не отключалась.

Без Docker, из корня клона:

```text
pip install -e "backend[dev]"
pytest backend/tests -q
```

## Куда смотреть

Проверено на локальном стенде 28.09.

| Адрес | Ответ |
|---|---|
| http://127.0.0.1:3000 | экран инспектора |
| http://127.0.0.1:3000/api/v1/healthz | 200 |
| http://127.0.0.1:8000/docs | 200, Swagger |
| http://127.0.0.1:8000/openapi.json | 200 |
| API без токена | 401, это ожидаемо |

Учебный токен: `inspector-1@OBJ-DEMO-COLD-START/INSPECTOR`.
Документы организатора на стенд не класть.

## Сценарий на учебном комплекте

Кнопка «Учебный комплект» кладёт синтетические ПД, РД и ИД.

1. До выбора эталона PZ-001, KR-055 и AR-041 в `CLARIFICATION_REQUIRED`.
   Так выглядит пакетный прогон без инспектора:
   [`unattended/submission.json`](../05-additional/examples/unattended/submission.json).
2. «Назначить эталоном» файл `f-pd`. Те же три кода становятся `CANDIDATE`.
   В карточке файл, страница, SHA-256 и polygon.
   Ответ после выбора, ещё без решения инспектора:
   [`after_etalon_select/submission.json`](../05-additional/examples/after_etalon_select/submission.json).
3. Подтвердить или отклонить с причиной. Автор пишется в аудит.
   Пачкой подтверждаются только отмеченные `CANDIDATE`.
4. Завершить проверку, финализировать. Протокол скачивается как JSON, DOCX, XML и PDF.
5. «Передать в РиН (mock)» ставит очередь `PENDING_SYNC`. ACK РиН нет.

Автомат на этих шагах не пишет `CONFIRMED_VIOLATION`.

## Пакет без экрана

Каталоги `input` и `out` рядом с compose. `out` доступен на запись uid 10001.

```text
docker compose --profile runner run --rm package-runner
```

Инспектор находки не подтверждает, `violation_count` остаётся 0.
Счёт каталога: `python -m kontur.cli.score --submissions <каталог>`.
Порог ТЗ эта команда не объявляет взятым.

## Если не стартует

Перед сборкой `KONTUR_GIT_SHA` равен `git rev-parse HEAD`: `.git` в образ не копируется.
Занятый порт на `127.0.0.1` мешает `up`. Первый `build` ходит в индекс пакетов.
Повторный smoke в CI уже падал по таймауту этого индекса и проходил со второй попытки.

## Границы

DWG — `UNSUPPORTED_FORMAT`. Архив — `ARCHIVE_NOT_EXPANDED`.
XML принимается и не разбирается (`ACCEPTED_UNPARSED`).
DOCX читается абзацами и таблицами.
Подтверждение брокера не является ACK РиН.
