# Уроки AeroBIM — аудит 2026-09

**Источник:** KonkovDV/AeroBIM HEAD `5289aca`  
**Цель:** выбрать лучшие идеи, которых нет в Kontur, перенести в проект  
**Дата:** 2026-09-18  

---

## 1. Capability Honesty Table (ADR-001 AeroBIM)

**Идея:** каждый endpoint отвечает за состояние движков. Молчание ≠ успех.

**Чем AeroBIM лучше:** у AeroBIM `SIGNOFF_PROFILE` проходит через capability check до каждого протокола.

**Что сделано в Kontur:**
- `capabilities.py`: `kit_degraded()`, `engine_health_summary()`, `overall_kit_status()`
- `api.py`: `GET /api/v1/system/capabilities` — ok | degraded | skipped | failed
- PR #34: endpoint, PR audit: `kit_degraded()` + `engine_health_summary()`

**Принцип:** LLM-advisory UNAVAILABLE → `skipped` (не `failed`). ADR-003 AeroBIM.

---

## 2. source_id + evidence_refs — ≤3 клика до источника

**Идея:** AeroBIM persistence отказывает Finding без `source_id`. Инспектор всегда видит источник.

**Что сделано:** `Finding.source_id`, `evidence_refs`, `has_provenance`
- Soft UserWarning (не ValueError) — обратная совместимость
- PR #33, PR audit: `models.py`

**Вывод:** хард-валидация (ValueError если нет source_id) — следующий PR.

---

## 3. DisagreementKind — таксономия расхождений

**Идея:** AeroBIM `ConflictKind` — типизированная природа расхождения. Без неё — свободный текст в `rationale`.

**Что сделано:** `statuses.DisagreementKind` (VALUE_DELTA, MISSING_IN_STAGE, AMBIGUOUS_REFERENCE, FORMAT_MISMATCH)

**Пример:** IOS4-078 (600×300 vs 400×250 мм) → `VALUE_DELTA`

---

## 4. PDF Parse Timeout — wall-clock kill

**Идея:** AeroBIM PROC-01 (закрыт 2026-09-05): subprocess + RLIMIT_CPU.

**Что сделано:** `infrastructure/pdf_guard.py` — `asyncio.wait_for` + ThreadPoolExecutor
- `KONTUR_PDF_PARSE_TIMEOUT_S` (default 25.0)
- `KONTUR_PDF_PARSE_WORKERS` (default 4)
- PR #35, PR audit: `pdf_guard.py`

**Ограничение:** поток продолжает работать (нет SIGKILL). Follow-up: subprocess isolation.

---

## 5. Где Kontur сильнее AeroBIM

| Область | Kontur | AeroBIM |
|---|---|---|
| Нормативная матрица | 132 параметра РФ | IDS (ISO 21597) |
| Сценарии комплектности | Gate F: 7 сценариев | opt-in |
| Состояние процесса | 6-шаговая машина + FINALIZED | summary.passed |
| Redis idempotency | SETNX защита | in-process BackgroundTasks |
| Appendix 2 | полный Protocol (PR #29) | минимальный |

---

## 6. Нереализованные идеи (P2 backlog)

- **Run versioning + revision diff** — `no_longer_reported ≠ resolved`
- **Customer review pack CLI** — AeroBIM генерирует зип-пакет для заказчика
- **BCF T0→T1** — BCF импорт требует полный Evidence ladder
- **IDS 1.0 export** — AeroBIM STUB-IDS-ASSIST-001 (LOW, активен)
- **Subprocess isolation** — полный аналог PROC-01
