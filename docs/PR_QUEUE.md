# Очередь PR — закрыта, остаётся только `main`

Разбор 18.09.2026. Уникальные честные куски влиты в `main`. GitHub-merge
красных PR целиком не делаем: они независимо от `main` и ломают инварианты.

## Что вошло в `main`

| PR | Решение |
|---|---|
| #11 KR-055, #12 PZ enum/number | overrides + enum/text экстрактор |
| #13 zip-бомба | только `CORRUPTED_FILE` в `application/intake.py` |
| #14 Docker | Makefile, offline compose, `docker-pull.sh` |
| #15–#19 RT модули | injection/cache/access/normative + оракулы; не README и не xfail=0 |
| #23 IOS4-078/079 | overrides + compile, не правка generated `rules/` в обход |
| #24 RT-G | `put_finding` по `evidence_group_id`; review ищет по `finding_id` |
| #25 | имя фикстуры dual-read в override IOS4-078 + E2E `ABSTAIN` |
| #26 | skip frozen val без `KONTUR_FROZEN_VAL_PATH`; без `pytestmark` |
| #28 факты | неофициальные пометки созвона — только как черновик, без ложных GAP |
| #33/#36 provenance | `source_id` / `evidence_refs` / `disagreement_kind` в схеме, без UserWarning |
| #34/#36 capabilities | `kit_degraded` / `engine_health_summary` / `GET /system/capabilities` |
| #35/#36 pdf_guard | `asyncio.wait_for` + ThreadPool, `TimeoutError`, без SIGKILL |
| #37 | замки на реальный API: нет `BLOCKED`/`process_id`/`UserWarning`; `split()` = `NotImplementedError` |
| #38 | IOS4-078: `multiply_dimensions` + compile `rules/`; площадь A×B на синтетике |
| #39 | GET `/protocol` через `assemble_protocol`; статус п. 9.3; AUTO_NO_DIFFERENCE не на проводе |
| #40 | MemoryProcessStore: `save_finding`/`load_findings`; без CONFIRMED_VIOLATION без инспектора |
| #41 | `tests/load/k6_status.js` без порога p95; CI k6 не запускает |
| #42+#45 | GET `/audit` + OpenAPI `getAuditLog` + rbac; GAP-EDIT открыт |
| #43 | сценарии `PD_ID_ONLY` / `RD_ID_ONLY` / SINGLE RD, SINGLE ID в `test_scenarios.py` |
| #44 | `attach_file` идемпотентен по hash+stage; повтор загрузки не дублирует `accepted` |

## Что не брали

| PR | Почему |
|---|---|
| #8 Gate J | base64, пороги на n=15 |
| #9 Gate K | `COMPLIANT`, отдельный `kontur.protocol` |
| #10 Gate L BFF | дубль gateway, OpenAPI 3.0.3 |
| #13 целиком | коды вне контракта |
| #20 / #21 docs | xfail=0 и 27 executable до merge |
| #22 / #27 Redis SETNX | не встроен в пайплайн; при ошибке Redis отбрасывает находку |
| #29 protocol_export | дубль `FindingStatus`; `AUTO_NO_DIFFERENCE` на проводе ТЗ |
| #30 scenarios rewrite | ломает `CompletenessMap` / `detect_scenario` на main |
| #31 free-search evaluator | статус `FREE_SEARCH`, находки без evidence, не тот JSON |
| #32 claim_finding_slot | импорт несуществующей функции в sync `put_finding` |
| #33 UserWarning | предупреждение не заменяет контракт |
| #34 engine_status.py | дубль `domain/capabilities.py` |
| #36 as-is | ruff UP041/B904/I001/E501; влит очищенный срез |
| #37 as-is | ruff I001/F401; 383 строки дубля уже зелёных тестов; grep `KNOWN_GAPS.md` |
| #38 as-is | override без compile; нет `multiply_dimensions` в `rule.schema.json`; GAP закрыт при неизмеренном recall |
| #39 as-is | смешал `COMPLETED` процесса со статусом протокола; AUTO_NO_DIFFERENCE мог уйти в JSON ТЗ |
| #40 as-is | `CONFIRMED_VIOLATION` без инспектора ломает `Finding.__post_init__` |
| #42 as-is | unicode-escape всего `api.py`; `getAuditLog` без OpenAPI |
| #45 as-is | ложное закрытие GAP-EDIT; опечатка «отклён» |
| #46 | dry-run: `MATRIX_PATH=rules` без compile; `DocumentRef`/`PageToken` не с main; `tests/gate_k` не в pytest |
| #47 | миграция `process_findings` без `schema.sql`/`checks.sql` (db job миграции не гоняет) |
| #48 | PostgresAuditStore без проводки в `schema.sql`; rbac без OpenAPI |
| #49 | синтетический recall 16/20 = gold; порог Wilson не выполнен; `tests/gate_j` не собирается |
| #50 | ложные закрытия GAP-EDIT / PROCESS-FINDINGS / IOS4-VAL |

Не публиковать F1/P/R и recall критических на frozen val. Площадь A×B на
синтетике не закрывает гейт J. k6 p95 не измерен.
