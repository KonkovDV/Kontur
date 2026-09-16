# Трассируемость: требование ТЗ → артефакт → тест

Заполняется по мере реализации. Столбец «Состояние» принимает значения
`skeleton` / `in_progress` / `done`. `done` требует зелёного теста и метрики.

| Пункт ТЗ | Требование | Артефакт | Тест | Состояние |
|---|---|---|---|---|
| 1.3–1.4 | REST/JSON, OpenAPI 3.0, асинхронный pull, `process_id` | `contracts/openapi.yaml`, `presentation/api.py` | `scripts/check_contracts.py` | skeleton |
| 1.5 | React + Node.js + Python, RabbitMQ | `web/`, `gateway/`, `backend/`, `docker-compose.yml` | — | skeleton |
| 3–5 | Разделы ПД, состав РД, состав ИД | `data/matrix/sections.json` | `test_matrix_registry.py` | skeleton |
| 6 | Соответствие разделов матрицы и документации | `data/matrix/sections.json` | `test_matrix_registry.py` | skeleton |
| 7 | 12 модулей системы | `application/` | — | skeleton |
| 8 | Матрица 132 параметра, таблица `Params` | `data/matrix/`, `contracts/schemas/rule.schema.json` | `test_matrix_registry.py` | skeleton |
| 9.1 | Intake, OCR, NLP, CV, координаты, кеш, выбор редакции, дозагрузка | `application/pipeline.py` | `test_pipeline.py`, `test_coordinates.py` | skeleton |
| 9.1 | Ошибки загрузки: формат, повреждение, 50 МБ, 200 МБ, таймаут | `pipeline.INTAKE_REJECTION_CODES` | `test_status_map.py` | skeleton |
| 9.1 | Статусы загрузки `PD_/RD_/ID_UPLOADED/PARTIAL/MISSING` | `domain/status_map.py` | `test_status_map.py` | skeleton |
| 9.2 | Сценарии FULL…PARTIALLY_LOADED; пустой пакет — ошибка | `application/scenarios.py` | `test_scenarios.py` | skeleton |
| 9.2 | Карточка доказательства, протокол, `MISSING_EVIDENCE` | `contracts/schemas/` | `scripts/check_contracts.py` | skeleton |
| 9.2 | Каскад L0–L9: безопасная остановка, L0 ≠ finding, нет автостатуса на L8–L9 | `application/pipeline.py` | `test_pipeline.py`, `test_pipeline_halt.py` | in_progress |
| 9.2 | Инкрементальное обновление при дозагрузке | — | — | skeleton |
| 9.3 | Верификация, reason_code, атомарность, финализация, отмена | `application/review.py`, `domain/state_machines.py` | `test_review.py`, `test_state_machines.py` | skeleton |
| 9.3 | Юзабилити: ≤30 мин на протокол, ≤3 клика на находку | `web/` | ручной протокол на 5 инспекторах | skeleton |
| 9.4 | GOLD, версии, разбиение по объектам, пороги публикации модели | `evaluation/release_gate.py` | — | skeleton |
| 9.4 | Реестр поставки, карантин скрытого теста, изоляция по `object_id` | `data/dataset/package_manifest.json`, `data/dataset/objects.json`, `evaluation/dataset_package.py`, `docs/DATASET_PACKAGE.md` | `test_dataset_package.py`, `test_quarantine.py` | in_progress |
| 9.5 | SUSPICION, 4 подхода, дедупликация | — | — | skeleton |
| 9.6 | ИАИС «РиН»: только `PROTOCOL_FINALIZED`, УКЭП, 3 ретрая | — | — | skeleton |
| 10 | Таблицы БД | `infrastructure/db/schema.sql` | — | skeleton |
| 11 | Производительность, p95 ≤200 мс, 100 пользователей | `docs/PERFORMANCE.md` | нагрузочный прогон (не выполнен) | skeleton |
| 12 | Аутентификация, RBAC, TLS 1.3, аудит, 152-ФЗ, антивирус | — | — | skeleton |
| 13 | JSON-логи, уровни, Prometheus/Grafana, ELK, алерты, checksum | `gateway/src/server.js` | — | skeleton |
| 14 | Пороги приёмки и правила выборок | `evaluation/metrics.py` | `test_metrics.py` | skeleton |
| Прил. 1 | Полный перечень 132 параметров | `data/matrix/params.template.csv` | `test_matrix_registry.py` | **нет исходника** |
| Прил. 2 | Образец протокола | `contracts/schemas/protocol.schema.json` | — | **нет исходника** |

Приложения 1 и 2 в переданном PDF отсутствуют. Вопросы 1 и 2 записаны в
`QUESTIONS_TO_ORGANIZER.md`. Файла-подтверждения отправки организатору в
репозитории нет. До получения официальных файлов матрица ведётся как черновик
`source: draft`.

Возможные источники приложений найдены в пакете методики
(`02_ЭТАЛОННАЯ_РАЗМЕТКА_И_МЕТОДИКА.tar`: `lct_scoring_board_20260825`,
`hackathon_gold_20260811`, `ПАСПОРТ_РАЗМЕТКИ.pdf`) — см.
[`DATASET_PACKAGE.md`](DATASET_PACKAGE.md). Это материалы организатора, но не
подписанные приложения к ТЗ, поэтому статус строк не меняется до ответа.
