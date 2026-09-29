# Прототип

**Ссылка для формы:** https://github.com/KonkovDV/Kontur/tree/main/submission/04-prototype

Протокол воспроизведения стенда Контура. Публичного адреса нет: прототип —
этот репозиторий. Ответ организатора О-2: техническая проверка идёт из
комплекта, ссылка на стенд решением не оценивается. Документы не уходят во
внешние LLM, OCR и VLM. Гейты приёмки I/J/K/L открыты.

## Содержание

1. [Что показывает прототип](#1-что-показывает-прототип)
2. [Среда](#2-среда)
3. [Состав стенда](#3-состав-стенда)
4. [Запуск](#4-запуск)
5. [Проверка после старта](#5-проверка-после-старта)
6. [Сценарий инспектора](#6-сценарий-инспектора)
7. [Тот же сценарий через API](#7-тот-же-сценарий-через-api)
8. [Пакетный прогон и счёт](#8-пакетный-прогон-и-счёт)
9. [Границы прототипа](#9-границы-прототипа)
10. [Неполадки](#10-неполадки)
11. [Остановка](#11-остановка)

## 1. Что показывает прототип

Полную цепочку на синтетическом учебном комплекте: загрузка трёх стадий,
выбор эталона, сравнение по правилу матрицы, карточка доказательства, решение
инспектора, финализация, протокол в четырёх форматах и постановка в очередь РиН.

Прототип не показывает точность на документах заказчика. Учебный комплект
собран так, чтобы в нём было три расхождения: он проверяет цепочку, а не
качество распознавания. Замеры на публичной разметке — в
[`05-additional`](../05-additional/README.md).

## 2. Среда

| Что | Требование |
|---|---|
| Docker | Docker Engine и Compose v2 |
| Порты на `127.0.0.1` | `3000`, `8000`, `5432`, `6379`, `5672`, `15672`, `9000`, `9001` |
| CPU | ядро по умолчанию ограничено 8 CPU. На машине меньше 8 CPU задайте `KONTUR_CORE_CPUS` |
| Память | лимиты контейнеров в сумме около 11,8 ГБ, из них ядро 8 ГБ (`KONTUR_CORE_MEM_LIMIT`) |
| GPU | не нужен, драйвер NVIDIA в образ не входит |
| Сеть | нужна только для первой сборки образов. Запуск из tar — без сети |

## 3. Состав стенда

| Сервис | Роль | Порт | Healthcheck |
|---|---|---|---|
| `gateway` | Вход, лимиты 50 МБ на файл и 200 МБ на пакет, `RATE_LIMITED`, раздача экрана | `3000` | да |
| `core` | Ядро: разбор, сверка, API, протокол | `8000` | да |
| `postgres` | Процессы, находки, аудит, outbox | `5432` | да |
| `redis` | Кеш паспортов документов по SHA-256 файла | `6379` | да |
| `rabbitmq` | Брокер очереди в сторону РиН | `5672`, `15672` | да |
| `minio` | Объектное хранилище в составе стенда. Ядро в этом срезе к нему не обращается | `9000`, `9001` | да |
| `outbox-relay` | Публикация протокола в брокер | — | — |
| `inbox-consumer` | Приём сообщений после commit | — | — |

Все порты привязаны к `127.0.0.1`. Экран можно открыть наружу только
переменной `KONTUR_BIND=0.0.0.0`: базы и брокер остаются на loopback.
Ядро и шлюз работают от пользователя 10001, файловая система только на чтение,
`cap_drop: ALL`. Базовые образы закреплены digest.

## 4. Запуск

### 4.1 Сборка из клона

```text
git clone https://github.com/KonkovDV/Kontur.git
cd Kontur
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
```

Перед сборкой задайте `KONTUR_GIT_SHA` — 40 символов `git rev-parse HEAD`.
Каталог `.git` в образ не копируется. Без переменной манифест прогона пишет
пустой `git_sha`.

Файл `docker-compose.demo.yml` включает учебный токен без подписи. Он нужен
только для стенда на loopback.

### 4.2 Без сети, из tar

На машине с сетью `scripts/offline_bundle.sh` сохраняет собранные образы в tar
и пишет `SHA256SUMS`. На целевой машине:

```text
docker load -i kontur_images.tar
docker compose -f docker-compose.yml -f docker-compose.demo.yml -f docker-compose.offline.yml up -d --no-build
```

`pull_policy: never` запрещает обращение к registry: нет образа — ошибка, а не
скачивание. Веса OCR уже внутри образа. Записи прогонов 27.09 и 28.09 —
[`DEMO_COLD_START.md`](../../docs/DEMO_COLD_START.md). Сеть хоста в них не
отключалась.

### 4.3 Без Docker

```text
pip install -e "backend[dev]"
pytest backend/tests -q
python scripts/check_claims.py
```

## 5. Проверка после старта

| Проверка | Ожидаемый ответ |
|---|---|
| http://127.0.0.1:3000/api/v1/healthz | 200, `{"status":"ok"}` |
| http://127.0.0.1:8000/docs | 200, Swagger ядра |
| http://127.0.0.1:8000/openapi.json | 200, контракт API |
| `GET /api/v1/system/capabilities` без токена | 401, `authentication required` |
| `docker compose ps` | `core` и `gateway` в состоянии `healthy` |
| http://127.0.0.1:3000 | экран с плашкой «учебный стенд» |

401 без токена — ожидаемое поведение: защищённые маршруты требуют роль и
`object_id`.

## 6. Сценарий инспектора

Учебный токен: `inspector-1@OBJ-DEMO-COLD-START/INSPECTOR`. Документы
организатора на стенд не класть.

| Шаг | Действие | Что видно | Что это доказывает |
|---|---|---|---|
| 1 | «Учебный комплект» | Процесс `READY`, сценарий `PARTIALLY_LOADED`, 132 находки. PZ-001, KR-055, AR-041 — `CLARIFICATION_REQUIRED` | В комплекте две редакции ПД. Автомат не выбирает эталон сам |
| 2 | «Назначить эталоном» файл `f-pd` | Три `CANDIDATE`: площадь 1250,5 → 1100 м², класс бетона B30 → B25, проём 1,2 → 0,8 м | Сравнение идёт от эталона, выбранного человеком. Выбор пишется в аудит |
| 3 | Открыть карточку | Правило, ожидание и факт, файл, страница, SHA-256, polygon на листе ПД и РД | У предметной находки есть доказательство |
| 4 | Подтвердить PZ-001 и KR-055, отклонить AR-041 | `CONFIRMED_VIOLATION` ×2, `NEGATIVE_VERIFIED` ×1 | Нарушение подтверждает только человек. Отклонение без причины не принимается |
| 5 | Завершить и финализировать | `COMPLETED` → `FINALIZED`, протокол `PROTOCOL_FINALIZED`, `violation_count` 2 | Незакрытый `CANDIDATE` финализацию блокирует |
| 6 | Скачать протокол | JSON, DOCX, XML, PDF | Четыре формата из одного JSON |
| 7 | «Передать в РиН (mock)» | `sync_state` `PENDING_SYNC` | Очередь поставлена. ACK РиН нет, `SYNCED` не выставляется |

Отмеченные `CANDIDATE` можно подтвердить пачкой, до 50 за раз, с одним
комментарием. Массового отклонения нет. Каждая находка получает свою запись
аудита.

Ответ участника на шагах 1 и 2 в виде файлов:
[`unattended`](../05-additional/examples/unattended/submission.json) и
[`after_etalon_select`](../05-additional/examples/after_etalon_select/submission.json).

Время сценария и число кликов здесь не замер Gate K. Пяти сессий
инспекторов нет.

## 7. Тот же сценарий через API

Проверено 28.09.2026 на коде `main` `4daef54`: FastAPI TestClient, маршруты ядра,
учебный токен. Через шлюз адреса те же, с префиксом `http://127.0.0.1:3000`.
Заголовок каждого защищённого запроса:
`Authorization: Bearer inspector-1@OBJ-DEMO-COLD-START/INSPECTOR`.
В теле действий `inspector_id` равен субъекту токена, `inspector-1`.

| Запрос | Тело | Наблюдённый ответ |
|---|---|---|
| `GET /api/v1/healthz` | — | 200 |
| `POST /api/v1/demo/kit` | — | 200, `process_id`, `etalon_file_id` `f-pd` |
| `GET /api/v1/processes/{id}/findings` | — | 200, 132 находки, `CANDIDATE` 0 |
| `POST /api/v1/processes/{id}/revisions/f-pd/select` | `inspector_id`, `comment` | 200 |
| `GET /api/v1/processes/{id}/findings` | — | 200, `CANDIDATE` 3 |
| `GET /api/v1/processes/{id}/findings/{finding_id}/evidence-card` | — | 200, `kontur.evidence_card.v1` |
| `POST /api/v1/findings/{finding_id}/review` | `action` `CONFIRM`, `inspector_id`, `comment` | 200, `CONFIRMED_VIOLATION` |
| `POST /api/v1/findings/{finding_id}/review` | `action` `REJECT` без `reason_code` | 409, `REJECT requires reason_code` |
| `POST /api/v1/findings/{finding_id}/review` | `action` `REJECT`, `reason_code` `APPROVED_CHANGE_EXISTS` | 200, `NEGATIVE_VERIFIED` |
| `POST /api/v1/processes/{id}/complete` | `inspector_id` | 200, `COMPLETED` |
| `POST /api/v1/processes/{id}/finalize` | `inspector_id` | 200, `FINALIZED` |
| `GET /api/v1/processes/{id}/protocol` | — | 200, `PROTOCOL_FINALIZED`, версия 1, `violation_count` 2 |
| `GET …/protocol.docx`, `.xml`, `.pdf` | — | 200 каждый |
| `GET /api/v1/processes/{id}/audit` | — | 200: `PIPELINE`, `SELECT_REVISION`, `PIPELINE`, `REVIEW`, `START_VERIFICATION`, `REVIEW`, `REVIEW`, `COMPLETE_VERIFICATION`, `FINALIZE` |
| `POST /api/v1/inspection/{id}` | — | 202, `sync_state` `PENDING_SYNC` |

Полный контракт — [`openapi.yaml`](../../contracts/openapi.yaml) или Swagger на `:8000/docs`.
Пачка кандидатов — `POST /api/v1/processes/{id}/findings/confirm` с
`finding_ids`, только роли инспектора и супервизора.

## 8. Пакетный прогон и счёт

Каталоги `input/` и `out/` рядом с compose. `out/` доступен на запись uid 10001.

```text
docker compose --profile runner run --rm package-runner
```

Без Docker:

```text
python -m kontur.cli.run_package --input <каталог> --out <каталог> [--pages-text]
python -m kontur.cli.score --submissions <каталог>
```

Вход — `files_index.jsonl` или папки `<объект>/{ПД|РД|ИД}`. Раскладка —
[`examples/demo_package/README.md`](../../examples/demo_package/README.md).

| Выход | Содержимое |
|---|---|
| `submission_<объект>.json` | Ответ участника по `submission.schema.json` |
| `protocol_<объект>.json` | Черновик протокола по `protocol.schema.json` |
| `documents_<объект>.json` | Файлы, SHA-256, стадии, размеры |
| `fields_<объект>.jsonl` | Паспорт каждого тома: шифр, редакция, основание шифра |
| `pages_text_<объект>.jsonl` | С `--pages-text`: слова, bbox, `engine` (`vector` или `ocr`) |
| `run_manifest.json` | Версии, `object_id_basis`, пропуски, сбои, время, гейты `false` |

Инспектор в пакетном прогоне находки не подтверждает, `violation_count` 0.
Скрытый тест пропускается. `RD_ID_MIXED` стадией не назначается.
Таймаут разбора PDF — 600 с на файл, если не задан `KONTUR_PDF_PARSE_TIMEOUT_S`.
`score` не выдаёт числа ответу вне схемы и порог ТЗ взятым не объявляет.

## 9. Границы прототипа

| Вход | Что происходит |
|---|---|
| PDF | Текстовый слой; пустой слой — локальный OCR |
| DOCX | Абзацы и таблицы. Рамки, content control и колонтитулы помечаются пропущенными |
| XML | Принимается, не разбирается: `ACCEPTED_UNPARSED` |
| Архив | `ARCHIVE_NOT_EXPANDED`: распаковать до загрузки |
| DWG | `UNSUPPORTED_FORMAT`, организатор его не требует |
| Файл больше 50 МБ | `FILE_TOO_LARGE` на шлюзе |
| Пакет больше 200 МБ | `BATCH_LIMIT_EXCEEDED` |

Не построено: живой РиН и его ACK, УКЭП, OIDC, VLM, атомарное разделение
находки. 72 правила матрицы без экстрактора нарушения не выдают.

## 10. Неполадки

| Симптом | Причина | Что сделать |
|---|---|---|
| `core` не стартует на ноутбуке | Лимит 8 CPU больше, чем есть у машины | `KONTUR_CORE_CPUS=4` или меньше |
| Контейнер ядра убит по памяти | Лимит 8 ГБ больше свободной памяти | Уменьшить `KONTUR_CORE_MEM_LIMIT` |
| `port is already allocated` | Порт на `127.0.0.1` занят | Освободить порт из таблицы раздела 2 |
| Пустой `git_sha` в манифесте | Не задан `KONTUR_GIT_SHA` | Задать и пересобрать образ |
| Пакетный прогон не пишет в `out/` | Нет записи для uid 10001 | Выдать права на `out/` |
| Первая сборка падает по таймауту индекса пакетов | Сеть до индекса Python нестабильна | Повторить сборку; в CI такой сбой уходит повтором |
| Офлайн-запуск: образ не найден | `pull_policy: never` и образ не загружен | `docker load` из tar |
| 401 на API | Нет заголовка `Authorization` | Учебный токен из раздела 6 |
| 404 на `/api/v1/demo/kit` | Стенд поднят без `docker-compose.demo.yml` | Добавить этот файл в команду `up` |

## 11. Остановка

```text
docker compose -f docker-compose.yml -f docker-compose.demo.yml down
```

`down -v` дополнительно удаляет тома базы, брокера и хранилища вместе с
процессами и аудитом. Использовать только для полного сброса стенда.
