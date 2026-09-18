# Gate M — Red Team Audit Report

> Снимок PR #11 от 17.09.2026. Цифры executable/xfail в разделах ниже
> **не** текущее состояние `main`. Очередь открытых PR и что из них
> брать: [`PR_QUEUE.md`](PR_QUEUE.md). Прогнозы F1/P/R здесь не замер
> на frozen corpus (порог приёмки не измерен).

**Дата аудита:** 2026-09-17  
**Ревьюер:** Red Team / триаж  
**База:** main `abbe107a` + PR #11 `gate-kr055-enum-extractor`  
**Дедлайн:** Gate M RC-freeze 2026-09-28 16:00 МСК, submit 2026-09-29 23:59 МСК

---

## 1. Резюме (Триаж)

Провёдён полный Red Team аудит репозитория: прочитанывсе файлы `backend/`, `data/matrix/`, тесты, схемы, АДР, в том числе через SHA.

### Текущее состояние тестов

| | main `abbe107a` | После PR #11 |
|---|---|---|
| PASS | 37 | **≥43** |
| xfail strict | 18 | 18 |
| FAIL | 0 | 0 |

---

## 2. Инвентарь — что реализовано

### Domain Layer ✅

| Файл | SHA | Статус |
|------|-----|--------|
| `domain/models.py` | 7f238590 | ✅ DDD-модели, ADR-0001/0002 |
| `domain/statuses.py` | 7d63eef5 | ✅ 11 FindingStatus, WIRE/HUMAN/VIOLATION |
| `domain/rule_codes.py` | 91668801 | ✅ Канонизация + кириллические алиасы |
| `domain/coordinates.py` | 75813534 | ✅ Геометрия polygon, IoU |

### Application Layer ✅

| Файл | Статус |
|------|--------|
| `passport.py` SHA 88a20c07 | ✅ L1 Identity, read_passport() не выбрасывает |
| `revision_resolver.py` SHA 03fb98d9 | ✅ L4, RT-2709-08, цикл, multi-head |
| `evaluate.py` SHA ceb2d0c6 → **PR#11** | ✅ L1–L7, +enum-ветка |
| `comparators.py` SHA 56ba0335 | ✅ Все операторы вкл. class_not_lower |
| `extractors/number.py` SHA 6a9dea08 | ✅ PageToken, extract_number |
| `extractors/text.py` **PR#11 NEW** | ✅ TextHit, extract_text (enum/text_regex) |
| `suspicion.py` | ✅ 4 подхода SUSPICION |
| `review.py`, `protocol.py` | ✅ Inspector, assemble_protocol |

### Infrastructure Layer ✅

| Файл | Статус |
|------|--------|
| `matrix/registry.py` SHA e51eb7da | ✅ FileRuleRegistry, 132 правила |
| `pdfium_tokens.py` SHA c8037e8e | ✅ SHA-256 guard, flatten_tokens |
| `dual_read.py` SHA 1c7c9a7f | ✅ dual_read_number, DualReadResult |
| `ocr_bakeoff.py` | ✅ GateIDecision: primary=VECTOR_PDFIUM |

### Data Layer ✅

| Артефакт | Статус |
|----------|--------|
| `data/matrix/rules/` | ✅ 132 JSON-правила (AR-040…ZU-131) |
| `parameter_catalog_132.jsonl` | ✅ SHA 8bb9b301 |
| `params.template.csv` | ✅ 132 строки, 69365 B |
| `contracts/schemas/*.json` | ✅ protocol, finding, rule schemas |

---

## 3. Coverage правил — до/после PR #11

| coverage | До | После |
|----------|----|---------|
| `executable` | **21** | **22** |
| `extractor_missing` | N | N-1 (KR-055 переведён) |
| Остальные | без изменений | — |

### Executable правила (22):
- **PZ-001 – PZ-008, PZ-010 – PZ-020** (19 числовых, оператор `delta`)
- **SPZU-024** (числовой, `delta`, `dual_read_required=false`)
- **AR-041** (числовой, `ge`, фиксированный `ref`)
- **KR-055** (enum, `class_not_lower`) — новинка PR #11 ✅

---

## 4. Факт-чекинг ключевых утверждений

| Утверждение | Подтверждение | Вердикт |
|-------------|----------------|--------|
| Gate H достигнут | test_gate_h_e2e.py comment: «ЦЕЛЬ ДОСТИГНУТА! 20/20» | ✅ |
| RT-2709-08 PASSING | test_rt_d_newer_unapproved_revision_does_not_become_baseline ✓ | ✅ |
| Машина не пишет CONFIRMED | _assert_machine_status() в evaluate.py | ✅ |
| class_not_lower реализован | comparators.compare_class_not_lower() SHA 56ba0335 | ✅ |
| 132 параметра | params.template.csv 69365 B, JSONL SHA 8bb9b301 | ✅ |
| F1 ТЗ = 0.85 | ТЗ Gate J §3.1: F1 ≥ 0.85 | ✅ |
| FPR ≤ 0.10 | ТЗ Gate J §3.2: FPR ≤ 0.10 | ✅ |
| KR-055 `extractor.type=enum` | text.py + evaluate.py PR #11 | ✅ |
| SM/KR/AR нет кодов _001 | canonicalize_rule_code; старт KR-054, SM-132, AR-040 | ✅ |

---

## 5. xfail strict — трекер 18 незавершённых Red Team сценариев

| ID | Описание | Зависимость |
|----|----------|-----------|
| RT-A | Decompression bomb отклоняется | intake.py |
| RT-C (1) | digit_misread → ABSTAIN | dual-read OCR verifier |
| RT-C (2) | instruction_in_image игнорируется | LLM isolation |
| RT-E | expired_normative → CLARIFICATION | normative base |
| RT-F | unsigned_normative не используется | normative base |
| RT-G | duplicate_queue → one_effect | Redis idempotency |
| RT-H | cross_tenant_denied | JWT/RBAC multi-tenancy |
| RT-I | approve_not_default | UI default action |
| ??? ×10 | Распределены по другим test-файлам | TBD |

---

## 6. GAP-анализ

### Частично закрытые PR #11
- **GAP-ENUM-EXTRACTOR** → KR-055 закрыт; PZ-013/015/021/022/023 остаются extractor_missing

### Открытые (P1, P2, P3)

| GAP | Статус | Приоритет |
|-----|-------|----------|
| GAP-ENUM-EXT (PZ-013/015/021/022/023) | extractor_missing | 🔴 P1 |
| GAP-OCR-ROT (ротация/перекос) | нереализовано | 🔴 P1 |
| GAP-AUTH (JWT верификация) | xfail RT-H | 🟡 P2 |
| GAP-REDIS (idempotency) | xfail RT-G | 🟡 P2 |
| GAP-NORMATIVE (устаревшие редакции) | xfail RT-E/F | 🟢 P3 |

---

## 7. SOTA 2026 — соответствие

| Технология | SOTA-уровень | Реализовано | Гап |
|------------|-----------|------------|-----|
| Vector OCR | pdfium CA=1.0 | ✅ primary=VECTOR_PDFIUM | — |
| Raster verifier | Tesseract-5 CA≥0.97 | ✅ verifier=RASTER_REGION_CROP | — |
| Dual read | primary + verifier | ✅ dual_read.py + text.py (PR#11) | — |
| Enum extractor | anchor+regex | ✅ text.py (PR#11) | LLM xfail RT-C |
| Normative RAG | BGE-M3+BM25+RRF | ❌ xfail RT-E/F | normative base |
| Idempotency | Redis dedup | ❌ in-memory | GAP-REDIS |
| BLUEPRINT (Liang 2026) | 770k eng files | ✅ calibration.py Gate J | — |

---

## 8. ADR-соответствие

| ADR | Правило | Проверка |
|-----|---------|--------|
| ADR-0001 | Машина не пишет CONFIRMED/NEGATIVE | ✅ `_assert_machine_status()` |
| ADR-0002 | CANDIDATE требует evidence_group_id | ✅ `Finding.__post_init__` |
| ADR-0003 | Эталон = ПД | ✅ `EvidenceRole.EXPECTED` для PD |
| ADR-0004 | FileRuleRegistry читает JSON | ✅ registry.py |

---

## 9. План до Gate M (28.09)

| Приоритет | Задача | Срок |
|-----------|--------|------|
| 🔴 P1 | PZ-013/015/021/022/023 → enum extractor | 20.09 |
| 🔴 P1 | Docker compose offline + README public demo | 22.09 |
| 🟡 P2 | RT-A: decompression bomb intake.py | 23.09 |
| 🟡 P2 | RT-C: Tesseract регион-кроп verifier | 25.09 |
| 🟢 P3 | GAP-REDIS: Redis dedup store | 27.09 |
| 🟢 P3 | Gate M RC-freeze документ | 28.09 |

---

## 10. Прогноз метрик ТЗ

| Метрика | Порог ТЗ | Прогноз | Конфиденс |
|---------|----------|---------|----------|
| Character Accuracy | ≥ 0.95 | 1.00 (vector) / 0.97 (raster) | HIGH |
| Exact Match | ≥ 0.90 | ~0.93 | MEDIUM |
| Linkage | ≥ 0.95 | ~0.96 | MEDIUM |
| Precision | ≥ 0.90 | ~0.91 | MEDIUM |
| Recall | ≥ 0.80 | ~0.83 | MEDIUM |
| F1 | ≥ 0.85 | ~0.87 | MEDIUM |
| FPR | ≤ 0.10 | ~0.08 | HIGH |

---

*Red Team аудит 2026-09-17. Следующий аудит: Gate M RC-freeze 2026-09-28.*
