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
| 8 | Матрица 132 параметра, таблица `Params` | `data/matrix/`, `contracts/schemas/rule.schema.json` | `test_matrix_registry.py` | in_progress |

| 9.1 | Intake, OCR, NLP, CV, координаты, кеш, выбор редакции, дозагрузка | `application/pipeline.py`, `domain/coordinates.py`, `infrastructure/pdfium_tokens.py`, `application/passport.py` | `test_pipeline.py`, `test_coordinates.py`, `test_pdf_tokens.py`, `test_passport.py` | in_progress (паспорт и PDF-токены есть; OCR/CV/кеш/редакции нет) |
| 9.1 | Ошибки загрузки: формат, повреждение, 50 МБ, 200 МБ, таймаут | `application/intake.py`, `application/retry_policy.py`, `presentation/api.py` | `test_intake.py`, `test_retry_policy.py`, `test_api.py` | in_progress |
| 9.1 | Статусы загрузки `PD_/RD_/ID_UPLOADED/PARTIAL/MISSING` | `domain/status_map.py` | `test_status_map.py` | skeleton |
| 9.2 | Сценарии FULL…PARTIALLY_LOADED; пустой пакет — ошибка | `application/scenarios.py` | `test_scenarios.py` | skeleton |
| 9.2 | Карточка доказательства, протокол, `MISSING_EVIDENCE` | `application/protocol.py`, `contracts/schemas/` | `test_pz001.py`, `scripts/check_contracts.py` | in_progress |
| 9.2 | Каскад L0–L9: безопасная остановка, L0 ≠ finding, нет автостатуса на L8–L9 | `application/pipeline.py`, `application/evaluate.py` | `test_pipeline.py`, `test_pipeline_halt.py`, `test_pz001.py` | in_progress |
| 9.2 | Инкрементальное обновление при дозагрузке | — | — | skeleton |
| 9.3 | Верификация, reason_code, атомарность, финализация, отмена | `application/review.py`, `domain/state_machines.py`, триггер `protocols_finalized_is_immutable` | `test_review.py`, `test_state_machines.py`, `db/checks.sql` § 1–3 | in_progress |
| 9.3 | Юзабилити: ≤30 мин на протокол, ≤3 клика на находку | `web/` | ручной протокол на 5 инспекторах | skeleton |
| 9.4 | GOLD, версии, разбиение по объектам, пороги публикации модели | `evaluation/release_gate.py`, CHECK `gold_label` и `gold_requires_expert` в `db/schema.sql` | `db/checks.sql` § 4–6, `test_schema_sql.py` | in_progress (пропуск категории в `release_gate` не блокирует публикацию — RT-2609-17) |
| 9.4 | Реестр поставки, карантин скрытого теста, изоляция по `object_id` | `data/dataset/package_manifest.json`, `data/dataset/objects.json`, `evaluation/dataset_package.py`, `docs/DATASET_PACKAGE.md` | `test_dataset_package.py`, `test_quarantine.py` | in_progress |
| 9.5 | SUSPICION, 4 подхода, дедупликация | `application/suspicion.py` | `test_suspicion.py` | in_progress (сигналы и дедупликация есть; в компаратор и протокол ТЗ не вшиты; сверка с нормой не является подходом) |
| 9.6 | ИАИС «РиН»: только `PROTOCOL_FINALIZED`, УКЭП, 3 ретрая | `application/retry_policy.py`, ограничение `sync_only_after_finalize` | `test_retry_policy.py`, `db/checks.sql` § 8 | in_progress (УКЭП и sandbox отсутствуют) |
| 10 | Таблицы БД | `infrastructure/db/schema.sql` (добавлена `processes`) | `test_schema_sql.py`, job `db` исполняет `schema.sql` и `checks.sql` | in_progress (8 из 16 таблиц сводки ещё нет) |
| 11 | Производительность, p95 ≤200 мс, 100 пользователей | `docs/PERFORMANCE.md` | нагрузочный прогон (не выполнен) | skeleton |
| 12 | Аутентификация, RBAC, TLS 1.3, аудит, 152-ФЗ, антивирус | `presentation/rbac.py`, `presentation/auth.py`, `security` и `x-required-roles` в `contracts/openapi.yaml`, `audit_log` | `test_rbac.py`, `test_api.py`, `scripts/check_contracts.py` | in_progress (Bearer-заглушка, не JWT; TLS и антивирус ещё нет) |
| 13 | JSON-логи, уровни, Prometheus/Grafana, ELK, алерты, checksum | `gateway/src/server.js` | — | skeleton |
| 14 | Пороги приёмки и правила выборок | `evaluation/metrics.py` | `test_metrics.py` | in_progress (Exact Match ключей реализован; порог не измерен на frozen corpus; Character Accuracy — `NotImplemented`) |
| Прил. 1 | Полный перечень 132 параметров | `data/matrix/source/parameter_catalog_132.jsonl`, `data/matrix/params.template.csv`, `data/matrix/rules/*.json` | `test_matrix_registry.py`, `test_pz001.py` | in_progress (132 schema-valid; `PZ-001` executable, остальные extractor_missing) |
| Прил. 2 | Образец протокола | `contracts/schemas/protocol.schema.json` | — | in_progress (образец найден: Приложение 2 docx) |
| Прил. 2 | Формат ответа участника (`submission_schema.json`) | `contracts/schemas/submission.schema.json`, `evaluation/submission.py` | `test_submission.py` | in_progress (формат `parameter_code` — вопрос 16) |

Приложения 1 и 2 **найдены в поставке 15.09.2026**
(`01_ПАКЕТ_УЧАСТНИКАМ_3_ОБЪЕКТА\...\00_ТЗ_И_ПРИЛОЖЕНИЯ`). Каталог импортирован
в `data/matrix/source/`, 132 правила собраны скриптом `scripts/compile_matrix.py`
со статусом `extractor_missing` — это schema-valid скелет, не исполняемые
проверки. Файла-подтверждения отправки организатору в репозитории нет.
Коды параметров — канонический трёхзначный формат (`PZ-001` … `SM-132`);
короткие формы из текстов (`AR-14`) — display-алиасы.

Прогон Red Team от 16.09.2026, триаж и открытые классы — [RED_TEAM_TRIAGE.md](RED_TEAM_TRIAGE.md).
