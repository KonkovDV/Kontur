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
| TRAIN_PUBLIC harness | `train_public.py`: исходные PDF, JSONL с `object_id`, 6/6 не закрывает J; MIXED не угадываем |
| #55 | Эталон только при заполненной графе «Утвердил»+ФИО; «Согласовано»/ГИП не approval |
| #56 | HTTP object scope обязателен (RT-H); unscoped → 403 на объектных операциях |
| #57 | Live Gate L k6 после upload; p95 на GHA измерен, не production SLA |
| #58 | JWT RS256/ES256 по умолчанию; legacy только с `KONTUR_ALLOW_INSECURE_DEV_AUTH` |
| #59 | Фактические байты upload: middleware считает `http.request`, файл читается чанками; 413 с `BATCH_LIMIT_EXCEEDED` / `FILE_TOO_LARGE`; смешанный accept/reject сохранён |
| #60 | non-root UID/GID 10001, read-only rootfs, `cap_drop: ALL`, `no-new-privileges`, порты только loopback; smoke tests контейнеров |
| upload retry | повтор hash+stage не `reopen_for_upload` и не pipeline; FINALIZED → 409; правка `runtime.py`/`api.py`, без monkeypatch |
| #62 | учебный рекордер Gate K: JSON `kontur-usability-v1`, `MISSING_EVIDENCE` нельзя CONFIRM/REJECT; сессий нет, гейт открыт |
| #64 | fail-closed Postgres finalize + атомарная versioned materialization (`protocol-{process_id}` / `-vN`, идемпотентный retry, конфликт при другом JSON). Не закрывает I/J/K |

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
| #54 as-is | `ocr_tesseract.py` одной строкой (invalid-syntax), CI backend FAILURE; «гейт I закрыт» до замера; tessdata-best нет в образе; `MIN_WORD_CONF` 40→35. Docker-прогон crop×3+oem1+autocontrast+PSM 7→6→8 на SILVER PDF_TEXT_LAYER: mean_ca тот же, tz_low и gate_i_low ниже, чем у текущего `main`. В прод не брали |
| #59 as-is | generic `{"detail":"request too large"}`, любой reject срывал mixed accept/reject, 429 admission, mypy `SpooledTemporaryFile`/`Any`; влит переписанный срез с кодами ТЗ |
| #61 as-is | import-time monkeypatch `ProcessRecord` из `presentation/__init__.py`; динамические флаги; Red Team BLOCK; backend CI FAILURE. Закрыт 20.09.2026. Идемпотентность влита прямой правкой `runtime.py`/`api.py` |
| #63 as-is | экспериментальная материализация: вырезан provenance, infrastructure импортировал `assemble_protocol`, version=1. Закрыт без merge 20.09.2026 |
| `feat/ocr-300dpi-step2-verifying` (`2ddc2b3`) | PR не открывался. Тот же усечённый push: `ocr_tesseract.py` одной строкой, 3161 байт. Заявлены wilson≥0.95 / tessdata-best / `MIN_WORD_CONF` 35. Не мержить |

Не публиковать F1/P/R и recall критических на frozen val. Поставка
организатора и 15 публичных gold-проверок **не** закрывают гейт J
([`ORGANIZER_GOLD.md`](ORGANIZER_GOLD.md)). Площадь A×B на синтетике не
закрывает гейт J. GHA k6 p95 измерен и **не** является production SLA.
Dry-run 132 — прогон движка на пустой комплектности, без заявления, что
вся матрица executable. Tesseract на PATH и `wilson(290, 300)` **не**
закрывают гейт I. JWT на HTTP — containment, не OIDC/JWKS.
