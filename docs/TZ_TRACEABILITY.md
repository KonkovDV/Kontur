# Трассируемость: требование ТЗ → артефакт → тест

Заполняется по мере реализации. Столбец «Состояние» принимает значения
`skeleton` / `in_progress` / `done`. `done` требует зелёного теста и метрики.

| Пункт ТЗ | Требование | Артефакт | Тест | Состояние |
|---|---|---|---|---|
| 1.3–1.4 | REST/JSON, OpenAPI 3.1, асинхронный pull, `process_id` | `contracts/openapi.yaml`, `presentation/api.py` | `scripts/check_contracts.py` | skeleton |
| 1.5 | React + Node.js + Python, RabbitMQ | `web/`, `gateway/`, `backend/`, `docker-compose.yml` | — | skeleton |
| 3–5 | Разделы ПД, состав РД, состав ИД | `data/matrix/sections.json` | `test_matrix_registry.py` | skeleton |
| 6 | Соответствие разделов матрицы и документации | `data/matrix/sections.json` | `test_matrix_registry.py` | skeleton |
| 7 | 12 модулей системы | `application/` | — | skeleton |
| 8 | Матрица 132 параметра, таблица `Params` | `data/matrix/`, `contracts/schemas/rule.schema.json` | `test_matrix_registry.py` | in_progress |

| 9.1 | Intake, OCR, NLP, CV, координаты, кеш, выбор редакции, дозагрузка | `application/process_pipeline.py`, `pipeline.py`, `pdfium_tokens.py`, `passport.py`, `revision_resolver.py` | `test_process_pipeline.py`, `test_pipeline.py`, `test_pdf_tokens.py`, `test_passport.py` | in_progress (векторный каскад в HTTP; dual-read/region-crop в коде; `ocr_text=UNAVAILABLE` до GOLD; CV нет; связка ≥0,97 не измерена) |
| 9.1 | Ошибки загрузки: формат, повреждение, 50 МБ, 200 МБ, таймаут | `application/intake.py`, `application/retry_policy.py`, `presentation/api.py` | `test_intake.py`, `test_retry_policy.py`, `test_api.py` | in_progress |
| 9.1 | Статусы загрузки `PD_/RD_/ID_UPLOADED/PARTIAL/MISSING` | `domain/status_map.py` | `test_status_map.py` | skeleton |
| 9.2 | Сценарии FULL…PARTIALLY_LOADED; пустой пакет — ошибка | `application/scenarios.py` | `test_scenarios.py` | skeleton |
| 9.2 | Карточка доказательства, протокол, `MISSING_EVIDENCE` | `application/protocol.py`, `contracts/schemas/` | `test_pz001.py`, `scripts/check_contracts.py` | in_progress |
| 9.2 | Каскад L0–L9: безопасная остановка, L0 ≠ finding, нет автостатуса на L8–L9 | `application/pipeline.py`, `application/evaluate.py`, `application/process_pipeline.py` | `test_pipeline.py`, `test_pipeline_halt.py`, `test_process_pipeline.py`, `test_pz001.py` | in_progress (прогон после upload; OCR нет) |
| 9.2 | Инкрементальное обновление при дозагрузке | `application/runtime.py`, `presentation/api.py` | `test_upload_idempotency.py`, `test_process_store.py` | in_progress (повтор hash+stage не reopen и не pipeline; новый файл — полный прогон; FINALIZED → 409) |
| 9.3 | Верификация, reason_code, атомарность, финализация, отмена | `application/review.py`, `domain/state_machines.py`, `POST /verify` `/complete` `/finalize` `/unfinalize`, триггер `protocols_finalized_is_immutable` | `test_review.py`, `test_state_machines.py`, `test_api.py`, `db/checks.sql` § 1–3 | in_progress (очередь по HTTP; `split()` нет) |
| 9.3 | Юзабилити: ≤30 мин на протокол, ≤3 клика на находку | `web/`, `docs/USABILITY_PROTOCOL.md`, `docs/USABILITY_RESULTS.md` | ручной протокол на 5 инспекторах | in_progress (рекордер кликов есть; сессий нет; Gate K открыт) |
| 9.4 | GOLD, версии, разбиение по объектам, пороги публикации модели | `evaluation/release_gate.py`, CHECK `gold_label` и `gold_requires_expert` в `db/schema.sql` | `db/checks.sql` § 4–6, `test_schema_sql.py`, `test_release_gate.py` | in_progress (подпись и полный набор категорий блокируют публикацию) |
| 9.4 | Реестр поставки, карантин скрытого теста, изоляция по `object_id` | `data/dataset/package_manifest.json`, `gold_inventory.json`, `evaluation/dataset_package.py` | `test_dataset_package.py`, `test_gold_inventory.py`, `test_quarantine.py` | in_progress (публичный gold и пакет без ответов v2.0 зафиксированы; объект 10 распакован без gold; frozen val на 132 нет; архивы 11–18 на машине отсутствуют; SHA-256 исходных `.tar` pending) |
| 9.5 | SUSPICION, 4 подхода, дедупликация | `application/suspicion.py` | `test_suspicion.py` | in_progress (сигналы и дедупликация есть; в компаратор и протокол ТЗ не вшиты; сверка с нормой не является подходом) |
| 9.6 | ИАИС «РиН»: только `PROTOCOL_FINALIZED`, УКЭП, 3 ретрая | `application/retry_policy.py`, ограничение `sync_only_after_finalize` | `test_retry_policy.py`, `db/checks.sql` § 8 | in_progress (УКЭП и sandbox отсутствуют) |
| 10 | Таблицы БД | `infrastructure/db/schema.sql`, `infrastructure/db/process_store.py` | `test_schema_sql.py`, `test_process_store.py`, job `db` | in_progress (снимок процесса, `process_findings` / `process_files`, комплектность и `audit_log` есть; 8 из 16 таблиц сводки ещё нет) |
| 11 | Производительность, p95 ≤200 мс, 100 пользователей | `docs/PERFORMANCE.md`, `tests/load/k6_status.js`, `.github/workflows/gate-l.yml` | `test_k6_script_contract.py`, live job `gate-l-live-k6` | in_progress (GHA `/status` 100 VU × 60 с измерен; не production SLA; остальные операции п. 11 не замерены) |
| 12 | Аутентификация, RBAC, TLS 1.3, аудит, 152-ФЗ, антивирус | `presentation/rbac.py`, `presentation/auth.py`, `security` и `x-required-roles` в `contracts/openapi.yaml`, `audit_log` | `test_rbac.py`, `test_auth.py`, `test_api.py`, `test_api_jwt.py`, `scripts/check_contracts.py` | in_progress (JWT RS256/ES256: iss/aud/exp/nbf/sub/roles и claim `object_id`; legacy только при `KONTUR_ALLOW_INSECURE_DEV_AUTH`; нет JWKS/OIDC rotation, TLS 1.3 и антивируса) |
| 13 | JSON-логи, уровни, Prometheus/Grafana, ELK, алерты, checksum | `gateway/src/server.js` | — | skeleton |
| 14 | Пороги приёмки и правила выборок | `evaluation/metrics.py`, `evaluation/frozen_val.py` | `test_metrics.py`, `test_frozen_val.py`, `test_gold_inventory.py` | in_progress (Exact Match и IoU на синтетике; 15 публичных gold-проверок ≠ frozen val; пороги не измерены; см. ORGANIZER_GOLD.md) |
| Прил. 1 | Полный перечень 132 параметров | `data/matrix/source/parameter_catalog_132.jsonl`, `data/matrix/params.template.csv`, `data/matrix/rules/*.json` | `test_matrix_registry.py`, `test_pz001.py` | in_progress (132 schema-valid; executable только в разбивке `coverage_report`) |
| Прил. 2 | Образец протокола | `contracts/schemas/protocol.schema.json` | — | in_progress (образец найден: Приложение 2 docx) |
| Прил. 2 | Формат ответа участника (`submission_schema.json`) | `contracts/schemas/submission.schema.json`, `evaluation/submission.py` | `test_submission.py` | in_progress (формат `parameter_code` — вопрос 16) |

Приложения 1 и 2 **найдены в поставке 15.09.2026**
(`01_ПАКЕТ_УЧАСТНИКАМ_3_ОБЪЕКТА\...\00_ТЗ_И_ПРИЛОЖЕНИЯ`) и байт-в-байт
повторены 19.09.2026 в `ПАКЕТ_УЧАСТНИКАМ_БЕЗ_ОТВЕТОВ_v2.0`. Каталог импортирован
в `data/matrix/source/`, 132 правила собраны скриптом `scripts/compile_matrix.py`
со статусом `extractor_missing` — это schema-valid скелет, не исполняемые
проверки. Файла-подтверждения отправки организатору в репозитории нет.
Коды параметров — канонический трёхзначный формат (`PZ-001` … `SM-132`);
короткие формы из текстов (`AR-14`) — display-алиасы.

Прогон Red Team от 16.09.2026, триаж и открытые классы — [RED_TEAM_TRIAGE.md](RED_TEAM_TRIAGE.md).
SOTA и запрет «сверки с нормой» — [SOTA_AEROBIM_ANALYSIS.md](SOTA_AEROBIM_ANALYSIS.md),
[adr/0006-compare-documents-not-norms.md](adr/0006-compare-documents-not-norms.md).
Пробелы слоёв — [KNOWN_GAPS.md](KNOWN_GAPS.md).
