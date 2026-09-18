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

Не публиковать F1/P/R и recall критических на frozen val. Площадь A×B на
синтетике не закрывает гейт J.
