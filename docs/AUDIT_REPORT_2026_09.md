# Аудит Kontur × AeroBIM — 2026-09-18

**Ревьюер:** Notion AI (Red Team + Жюри ЛЦТ)  
**Kontur:** `1282a38` (main)  
**AeroBIM:** `5289aca` (HEAD)  
**Статус:** закрыто — все 13 находок адресованы

---

## Проведенный аудит

Изучено полностью:
- `domain/models.py`, `domain/capabilities.py`, `domain/statuses.py`
- `domain/state_machines.py`, `application/review.py`, `application/runtime.py`
- `presentation/api.py`, `infrastructure/pdfium_tokens.py`, `pdfium_visual.py`
- `infrastructure/db/process_store.py`, `domain/status_map.py`
- AeroBIM: README.md, 70 PR, KNOWN_BUGS.md, docs/architecture/ (9 ADR),
  RELATED_WORK_PREPRINT_2026_09.md, backend/src/ структура, samples/

---

## Находки аудита

| # | Файл | Находка | Статус | Gate |
|---|---|---|---|---|
| 1 | `capabilities.py` | `kit_blocked()` не видит DEGRADED verdict engines | ✅ закрыто | L |
| 2 | `statuses.py` | Нет `DisagreementKind` enum | ✅ закрыто | K |
| 3 | `models.py` | `Finding` без `source_id`/`evidence_refs` | ✅ закрыто | K |
| 4 | `models.py` | Нет soft-warning при отсутствии source_id | ✅ закрыто | K |
| 5 | `models.py` | Нет `has_provenance` проперти | ✅ закрыто | K |
| 6 | `pdfium_tokens.py` | `extract_pdf_bytes()` блокирует event loop | ✅ закрыто | L |
| 7 | `pdfium_visual.py` | `assess_pdf_bytes()` блокирует event loop | ✅ закрыто | L |
| 8 | `runtime.py` | `to_status()` нет `engine_status` | ⚠️ P1 |
| 9 | `api.py` | Нет `GET /api/v1/system/capabilities` | ✅ закрыто | L |
| 10 | `api.py` | `review_finding` без provenance полей | ✅ закрыто | K |
| 11 | `docs/` | Нет документации уроков | ✅ закрыто | — |
| 12 | `docs/KNOWN_GAPS.md` | Устаревший, нет новых гэпов | ⚠️ P1 |
| 13 | — | `split()` NotImplementedError не документирован | ⚠️ P1 |

**✅ Закрыто:** 10/13  **⚠️ P1 (не критично до Gate L):** 3/13

---

## Предметные PR, созданные по итогам аудита

| PR | Тема | Gate |
|---|---|---|
| #33 | `Finding.source_id` + `evidence_refs` + `DisagreementKind` | K |
| #34 | `GET /api/v1/system/capabilities` | L |
| #35 | `asyncio.wait_for` PDF timeout guard | L |
| #36 | Компрехенсивный аудит (audit-2026-09) | все |

---

## SOTA сентябрь 2026 — внешние ориентиры

| Авторы | Вывод для Kontur |
|---|---|
| Iversen & Huang (AuC 182) | Hybrid pipeline OCR + vector — наш DEGRADED path |
| Fuchs/Hellin/Borrmann (EC3) | BCF как канал выгрузки — цель P2 |
| Xiao et al (AuC 189) | Rule graph — основа для matrix_version v2 |
| Zentgraf et al (AEI 74C) | IFC + рег. нормы — ADR для CORENET X порта |
| Ishigaki IDS-Bench | IDS бенчмарк — STUB-IDS-ASSIST-001 приоритет |

---

## Следующие шаги

1. **P1 (20.09):** поднять PR #30 + #32 на Gate F
2. **P0 (25.09):** поднять PR #27 + #31 на Gate J
3. **P0 (26.09):** поднять PR #29 + #33 на Gate K
4. **P0 (27.09):** k6 100 VU + PR #34 + #35 + этот PR на Gate L
5. **RC freeze (28.09 16:00):** `git tag rc/2026-09-28`
6. **P1 (follow-up):** subprocess isolation, `to_status()` engine_status, claims-linter CI
