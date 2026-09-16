# Трассируемость: требование ТЗ → артефакт → тест

Заполняется по мере реализации. Столбец «Состояние» принимает значения
`skeleton` / `in_progress` / `done`. `done` требует зелёного теста и метрики.

| Пункт ТЗ | Требование | Артефакт | Тест | Состояние |
|---|---|---|---|---|
| 1.3–1.4 | REST/JSON, OpenAPI 3.0, асинхронный pull, `process_id` | `contracts/openapi.yaml`, `presentation/api` | `test_api_contract.py` | skeleton |
| 1.5 | React + Node.js + Python ML, RabbitMQ | `web/`, `gateway/`, `backend/`, `docker-compose.yml` | `test_queue_contract.py` | skeleton |
| 3–5 | Разделы ПД, состав РД, состав ИД | `domain/nomenclature.py` | `test_nomenclature.py` | skeleton |
| 6 | Соответствие разделов матрицы и документации | `data/matrix/sections.json` | `test_matrix_registry.py` | skeleton |
| 7 | 12 модулей системы | `application/` | — | skeleton |
| 8 | Матрица 132 параметра, таблица `Params` | `data/matrix/`, `contracts/schemas/rule.schema.json` | `test_matrix_registry.py` | skeleton |
| 9.1 | Intake, OCR, NLP, CV, координаты, кеш, выбор редакции, дозагрузка | `application/l0_intake…l4_revision` | `test_coordinates.py`, `test_revision_resolver.py` | skeleton |
| 9.1 | Ошибки загрузки: формат, повреждение, 50 МБ, 200 МБ, таймаут | `application/l0_intake/errors.py` | `test_intake_errors.py` | skeleton |
| 9.1 | Статусы загрузки `*_UPLOADED/PARTIAL/MISSING` | `domain/statuses.py` | `test_state_machines.py` | skeleton |
| 9.2 | Сценарии FULL…PARTIALLY_LOADED, карточка доказательства, протокол | `application/l6_matrix`, `l7_findings` | `test_scenarios.py` | skeleton |
| 9.2 | Инкрементальное обновление при дозагрузке | `application/l7_findings/incremental.py` | `test_incremental.py` | skeleton |
| 9.3 | Верификация, reason_code, атомарность, финализация, отмена | `domain/review.py` | `test_review_state_machine.py` | skeleton |
| 9.3 | Юзабилити: ≤30 мин на протокол, ≤3 клика на находку | `web/`, `docs/USABILITY_PROTOCOL.md` | ручной протокол на 5 инспекторах | skeleton |
| 9.4 | GOLD, версии, разбиение по объектам, пороги публикации модели | `evaluation/gold.py`, `evaluation/release_gate.py` | `test_release_gate.py` | skeleton |
| 9.5 | SUSPICION, 4 подхода, дедупликация | `application/l7_findings/suspicion.py` | `test_suspicion.py` | skeleton |
| 9.6 | ИАИС «РиН»: только FINALIZED, УКЭП, 3 ретрая 1/5/15 мин, PENDING_SYNC | `infrastructure/adapters/rin/` | `test_rin_sync.py` | skeleton |
| 10 | 16 таблиц БД | `infrastructure/db/schema.sql` | `test_db_schema.py` | skeleton |
| 11 | Производительность, p95 ≤200 мс, 100 пользователей | `docs/PERFORMANCE.md`, k6-сценарий | нагрузочный прогон | skeleton |
| 12 | Аутентификация, RBAC, TLS 1.3, аудит, 152-ФЗ, антивирус | `core/security/` | `test_authz_matrix.py` | skeleton |
| 13 | JSON-логи, уровни, Prometheus/Grafana, ELK, алерты, checksum | `core/observability/` | `test_log_schema.py` | skeleton |
| 14 | Пороги приёмки и правила выборок | `evaluation/metrics.py` | `test_metrics.py` | skeleton |
| Прил. 1 | Полный перечень 132 параметров | `data/matrix/params.csv` | `test_matrix_registry.py` | **нет исходника** |
| Прил. 2 | Образец протокола | `contracts/schemas/protocol.schema.json` | `test_protocol_template.py` | **нет исходника** |

Приложения 1 и 2 в переданном PDF отсутствуют — запрос отправлен организатору
(`QUESTIONS_TO_ORGANIZER.md`, вопросы 1 и 2). До получения официальных файлов
матрица ведётся как черновик с пометкой `source: draft`.
