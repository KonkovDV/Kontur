# Changelog

All notable changes to **Контур — «Инспектор ИИ»** are documented here.  
Format: [Keep a Changelog](https://keepachangelog.com/ru/1.1.0/)  
Versioning: gate-based (семантическое версионирование введётся с RC-freeze)

---

## [0.5.0-rc] — RC-freeze 2026-09-28

> xfail: 18 → **0** (все 9 Red Team oracle реализованы)  
> executable правил: 1 → **27/132** (20.5%)  
> stop-ship: 0/12 → **10/12** безусловно, 2 условно  
> Gate J: P=1.00 / R=0.90 / F1=0.947 (прогноз F1≈0.87 на n=213)

### Безопасность (Security)

- **PR #17** `infrastructure/access_control.py`  
  RT-H: `check_object_access()` — pure function, `AccessDeniedError`,
  cross-tenant предотвращён.  
  Stop-ship п.1 закрыт. 10 тестов.

- **PR #13** `infrastructure/intake.py`  
  RT-A: ZIP-бомба (ratio > 100×), corrupt PDF, FILE_TOO_LARGE (50 МБ), заголовки без распаковки.  
  `validate_intake()` никогда не выбрасывает. 13 тестов.

- **PR #15** `infrastructure/injection_scan.py`  
  RT-C №²2: `scan_tokens_for_injection()` EN+RU паттерны,  
  скользящее окно WINDOW_SIZE=5. Никогда не выбрасывает.

- **PR #16** `infrastructure/cache.py`  
  RT-G: Redis idempotency `kontur:passport:v1:{sha256}`, TTL=3600.  
  Safe degradation при `ConnectionError`. Stop-ship п.11 закрыт. 14 тестов.

- **PR #18** RT-I: UI аффордансы — «Подтвердить» last, no autofocus, no accessKey.  
  Stop-ship п.3 закрыт. Двухуровневая защита: oracle независим + file-проверка.

- **PR #19** `infrastructure/normative_db.py`  
  RT-E: `NormativeStatus.EXPIRED` (expired revision ≠ VIOLATION).  
  RT-F: `NormativeStatus.NOT_SIGNED` (unsigned chunk not used as rule source).  
  `NormativeDB.get_valid_revision()`, `is_revision_expired()` — pure, SHA-256. 11 тестов.

### Добавлено (Added)

- **PR #8** `evaluation/calibration.py`  
  Gate J: `ConfidenceSignals`, `aggregate_confidence()` (weighted geom. mean),  
  `run_calibration_pass()`, `select_operating_point()`.  
  Gold-15: P=1.00 / R=0.90 / F1=0.947 — Gate J пройден.  
  SOTA: ExtractConf (ACL 2025), Group-Conditional CRC (ICML 2026).  
  9 классов 35+ тестов. `data/gold/public_gold_checks.jsonl` (15 золотых проверок).

- **PR #9** Gate K: `protocol_service.py` (+326 строк), `web/src/App.tsx`,  
  `tests/test_gate_k_protocol.py` (509 строк, 9 классов).  
  UI: ≤3 клика/находку, BoundingBox overlay, PDF Canvas 60% + EvidenceCard 40%.  
  SOTA: HCAI DSS Review (Cai et al. 2026), BLUEPRINT (Liang et al. 2026).

- **PR #10** `bff/server.js` (Express.js, Circuit Breaker opossum v8),  
  `bff/openapi.yaml` (5 endpoint), `tests/k6_gate_l_load.js`.  
  Gate L: p95 ≤ 200ms @ 100 VU; spike 150 VU; `GET /api/v1/catalog` p95 ≤ 50ms.  
  Graceful shutdown SIGTERM, pull-model ИАИС «РиН».

- **PR #11** `extractors/text.py` (TextHit, extract_text, anchor→regex→dual-read).  
  KR-055: `class_not_lower` — первый enum-руль. executable: 21 → 22.  
  `docs/GATE_M_REDTEAM_AUDIT.md` v1 (устарел заменён v2 в PR #20).

- **PR #12** PZ-013/015/021/022/023 — пожарные классы (ФЗ-123) и энергоэффективность (ФЗ-261).  
  executable: 22 → **27**. `tests/test_pz_enum_e2e.py` (20 тестов).

- **PR #14** `docker-compose.yml` (healthcheck, restart, pinned images),  
  `docker-compose.offline.yml`, `scripts/docker-pull.sh`, `Makefile`.  
  Gate M offline: `make offline-pull` + `make offline-up` + `make test`.

- **PR #20** `docs/GATE_M_REDTEAM_AUDIT.md` v2 (12 разделов, 13 PR, SOTA 2026).  
  README.md: Состояние 27/132, xfail=0, PR-таблица #8–#20.

### Изменено (Changed)

- **PR #11** `evaluate.py`: `_TEXT_EXTRACTOR_TYPES`, `_dual_read_required()`,  
  text-ветка в `evaluate_rule()`. Обратная совместимость с числовой веткой сохранена.

- **PRs #13/#15/#16/#17/#18/#19** `tests/adversarial/test_rt_suites.py`:  
  xfail 18 → 7 → 5 → 4 → 3 → 2 → **0**.

- **PR #20** `README.md`: раздел «Состояние» полностью переписан (был: «131 extractor_missing», стало: 27/132, xfail=0, PR-таблица).

### Исправлено (Fixed)

- **PR #12** `extractors/text.py`: `_regex_from_rule()` — `regex=null` возвращает `None` вместо `ValueError` (стабильная деградация).

- **PR #12** `data/matrix/rules/PZ-013.json`: `extractor.type` `enum` → `number` (вместимость = число); `comparator.operator` `class_not_lower` → `ge`.

- **PR #12** `data/matrix/rules/PZ-015/021/022/023.json`: `extractor.regex` `null` → корректные регекспы; `comparator.value` добавлен в соответствии с нормативными значениями.

- **PR #16 коммит 2**: удалён `_mock_client` из `cache.py` (непреднамеренный test fixture не должен быть в production коде).

---

## [0.4.0] — 2026-09-17 (вечер)

> Gate L: BFF Gateway, OpenAPI 3.0, k6

- `bff/server.js`, `bff/openapi.yaml`, `tests/k6_gate_l_load.js` (Впервые)

---

## [0.3.0] — 2026-09-17 (день)

> Gate K: Protocol Viewer, HCAI ≤3 clicks

- `protocol_service.py` (350 строк), `App.tsx`, `test_gate_k_protocol.py` (509 строк)
- Исправлены 5 багов: assync→async, URL-meatObjectURL, BBox height, x0<x1 guard, PDF stub

---

## [0.2.0] — 2026-09-17 (день)

> Gate J: Калибровка уверенности

- `calibration.py`, `test_gate_j_calibration.py` (35+ тестов)
- `data/gold/public_gold_checks.jsonl` (15 золотых проверок)
- `docs/GATE_J_CALIBRATION.md`

---

## [0.1.0] — 2026-09-17 (день)

> Gate H: ≥20 исполняемых правил

- `extractors/text.py`, `evaluate.py` text-ветка, KR-055 executable
- PZ-013/015/021/022/023: fire classes и энергоэффективность
- executable: 21 → 22 → 27

---

## [0.0.5] — 2026-09-17 (утро)

> Гейт E/F: `revision_resolver.py`, `release_gate`, `suspicion.py`, ADR-0006

---

## [0.0.4] — 2026-09-17

> Гейт D: `coordinates.py` Sutherland–Hodgman IoU, `evidence_localization_interval()`

---

## [0.0.3] — 2026-09-17

> Гейт C: `passport.py`, `pdfium_tokens.py`, `metrics.py` Exact Match NFC

---

## [0.0.2] — 2026-09-16

> Гейт B: API/status заморожены; ADR-0001–0006; 132 правила; `PZ-001` executable

---

## [0.0.1] — 2026-09-15

> Гейт A: карантин `TEST_213`; SHA-256; `docs/DATASET_PACKAGE.md`; `docs/DATA_QUARANTINE.md`

---

## [RC-freeze Checklist]

Выполнить перед `git tag rc/2026-09-28`:

- [x] Все xfail удалены (0 осталось)
- [x] Stop-ship 1–11 закрыты
- [x] Docker offline работает (`make offline-up`)
- [x] PR #8–#20 созданы
- [ ] PR #8–#20 squash-merged в main
- [ ] `make test` на чистой машине: 0 FAIL, xfail=0
- [ ] `git tag rc/2026-09-28 -m "Gate M RC freeze"`
- [ ] `git push origin rc/2026-09-28`
- [ ] CHANGELOG.md в main
- [ ] Резервное видео записано
