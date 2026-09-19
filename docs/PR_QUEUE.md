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
| #42+#45 | GET `/audit` + OpenAPI `getAuditLog` + rbac; журнал в `audit_log` |
| #43 | сценарии `PD_ID_ONLY` / `RD_ID_ONLY` / SINGLE RD, SINGLE ID в `test_scenarios.py` |
| #44 | `attach_file` идемпотентен по hash+stage; повтор загрузки не дублирует `accepted` |
| #46 | dry-run 132 по `data/matrix/rules/` через `evaluate_rule`; без документов, без человеческих вердиктов |
| #47 | `process_findings` / `process_files` / completeness в `schema.sql` + `checks.sql` |
| #48 | `PostgresAuditStore` → `audit_log.process_id`; GET `/audit` после hydrate |
| #49 | путь замера Wilson-recall; 16/20 не закрывает порог; цифры не публикуем |
| #51 | k6: 100 VU / 60 с, p(95)<200 на теге `status`; контракт в `backend/tests`; без FormData |
| #52 | JSONL frozen val с `object_id`; skip без env; `tests/gate_j` не брали |
| OCR raster | `ocr_tesseract.py`: пустой растр → Tesseract fail-closed; `ocr_text` остаётся UNAVAILABLE |
| OCR region-crop | `ocr_region_crop` в `evaluate_rule`; harness `ocr_pilot.py` без Речникова; гейт I открыт |

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
| #46 as-is | `MATRIX_PATH=rules` без compile; `DocumentRef`/`PageToken` не с main; `tests/gate_k` не в pytest |
| #47 as-is | миграция вне `schema.sql`/`checks.sql` |
| #48 as-is | rbac без OpenAPI |
| #49 as-is | синтетический recall 16/20 = gold; `tests/gate_j` не собирается |
| #50 as-is | закрытие GAP-IOS4-VAL: поставка документов ≠ frozen val (см. `docs/ORGANIZER_GOLD.md`) |
| #51 as-is | `FormData` без импорта; `tests/load/test_k6_script_contract.py` не в pytest |
| #52 as-is | `kontur.evaluation.recall` нет; `tests/gate_j` не собирается; нет `object_id` |
| #53 as-is | CI `backend` FAILURE (ruff I001/F401); `ocr_text=AVAILABLE` по `shutil.which`; дубль CA/Wilson z=1.645; `wilson(290,300)` как PASS пилота; импорт несуществующего `pdf_fixtures`; полный кадр назван region-crop; domain→infrastructure |

Не публиковать F1/P/R и recall критических на frozen val. Поставка
организатора и 15 публичных gold-проверок **не** закрывают гейт J
([`ORGANIZER_GOLD.md`](ORGANIZER_GOLD.md)). Площадь A×B на синтетике не
закрывает гейт J. k6 p95 не измерен. Dry-run 132 — прогон движка на пустой
комплектности, без заявления, что вся матрица executable. Tesseract на
PATH и `wilson(290, 300)` **не** закрывают гейт I.
