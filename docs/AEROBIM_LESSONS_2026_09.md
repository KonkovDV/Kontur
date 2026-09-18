# Уроки AeroBIM — аудит 2026-09

**Источник:** KonkovDV/AeroBIM HEAD `5289aca`  
**Цель:** выбрать лучшие идеи, которых нет в Kontur, перенести в проект  
**Дата:** 2026-09-18  

---

## 1. Capability Honesty Table (ADR-001 AeroBIM)

**Идея:** каждый endpoint отвечает за состояние движков.
**Принцип AeroBIM:** Silence is never success.

**Что сделано в Kontur:**
- `capabilities.py`: `kit_degraded()`, `engine_health_summary()`, `overall_kit_status()`
- `api.py`: `GET /api/v1/system/capabilities` — ok | degraded | skipped | failed
- LLM-advisory UNAVAILABLE -> `skipped` (не `failed`). ADR-003 AeroBIM.

**Mapping:**
| CapStatus | affects_verdict | label |
|---|---|---|
| AVAILABLE | any | `ok` |
| DEGRADED | any | `degraded` |
| UNAVAILABLE | True | `failed` |
| UNAVAILABLE | False | `skipped` |

---

## 2. source_id + evidence_refs (≤3 клика до источника)

**Идея AeroBIM:** persistence отказывает Finding без `source_id`. Инспектор всегда видит источник.

**Что сделано:** `Finding.source_id`, `evidence_refs`, `has_provenance`, soft UserWarning

**Формат source_id:** `"{stage}:p{page}:{fragment_id}"` (пример: `"pd:p12:frag-abc123"`)

**Вывод:** хард-валидация (ValueError) — следующий PR после RC freeze.

---

## 3. DisagreementKind (донор AeroBIM ConflictKind)

**Идея:** типизированная природа расхождения предотвращает дрейф в `rationale`.

| Значение | Пример |
|---|---|
| VALUE_DELTA | IOS4-078: 600×300 vs 400×250 мм |
| MISSING_IN_STAGE | Армирование есть в ПД, нет в РД |
| AMBIGUOUS_REFERENCE | Один код → несколько значений |
| FORMAT_MISMATCH | мм vs см без конвертации |

---

## 4. PDF Parse Timeout (wall-clock kill)

**Идея AeroBIM:** PROC-01 (subprocess + RLIMIT_CPU + Windows Job Object), закрыт 2026-09-05.

**Контур-решение:** `asyncio.wait_for` + ThreadPoolExecutor (чистый Python).

| Параметр | Значение по умолчанию |
|---|---|
| `KONTUR_PDF_PARSE_TIMEOUT_S` | 25.0 с |
| `KONTUR_PDF_PARSE_WORKERS` | 4 |

**Трейдофф:** поток продолжает работать после timeout (нет SIGKILL). Follow-up: subprocess isolation.

---

## 5. Где Kontur сильнее AeroBIM

| Область | Kontur | AeroBIM |
|---|---|---|
| Нормативная матрица | 132 параметра РФ | IDS (ISO 21597) |
| Сценарии | Gate F: 7 сценариев | opt-in |
| Процесс | 6-шаговая FSM + FINALIZED | summary.passed |
| Redis idempotency | SETNX | in-process |
| Appendix 2 | полный Protocol (PR #29) | минимальный |

---

## 6. P2 Backlog (нереализованные идеи)

- **Run versioning + revision diff** — `no_longer_reported != resolved`
- **Customer review pack CLI** — zip-пакет для заказчика
- **BCF T0->T1** — BCF импорт + Evidence ladder
- **IDS 1.0 export** — AeroBIM STUB-IDS-ASSIST-001
- **Subprocess isolation** — полный аналог PROC-01
- **`to_status()` engine_status** — добавить поле в process status endpoint
