# Аудит Kontur x AeroBIM — 2026-09-18

**Kontur:** `1282a38` (main) | **AeroBIM:** `5289aca` (HEAD)  
**Статус:** 10/13 закрыто, 3/13 P1

---

## Находки аудита

| # | Файл | Находка | Статус | Gate |
|---|---|---|---|---|
| 1 | `capabilities.py` | `kit_blocked()` не видит DEGRADED | ✅ | L |
| 2 | `statuses.py` | Нет `DisagreementKind` | ✅ | K |
| 3 | `models.py` | `Finding` без `source_id`/`evidence_refs` | ✅ | K |
| 4 | `models.py` | Нет soft-warning | ✅ | K |
| 5 | `models.py` | Нет `has_provenance` | ✅ | K |
| 6 | `pdfium_tokens.py` | Нет timeout, блокирует loop | ✅ | L |
| 7 | `pdfium_visual.py` | Нет timeout, блокирует loop | ✅ | L |
| 8 | `runtime.py` | `to_status()` без `engine_status` | ⚠️ P1 | — |
| 9 | `api.py` | Нет `GET /system/capabilities` | ✅ | L |
| 10 | `api.py` | `review_finding` без provenance | ✅ | K |
| 11 | `docs/` | Нет документации уроков | ✅ | — |
| 12 | `KNOWN_GAPS.md` | Устаревший | ⚠️ P1 | — |
| 13 | `review.py` | `split()` NotImplementedError недокументирован | ⚠️ P1 | — |

---

## PR по итогам аудита

| PR | Тема | Gate |
|---|---|---|
| #33 | `Finding.source_id` + `evidence_refs` + `DisagreementKind` | K |
| #34 | `GET /api/v1/system/capabilities` | L |
| #35 | `asyncio.wait_for` PDF timeout | L |
| **#36** | **Компрехенсивный аудит** | все |

---

## Следующие шаги

1. **20.09 Gate F:** мерж PR #30 + #32
2. **25.09 Gate J:** мерж PR #27 + #31
3. **26.09 Gate K:** мерж PR #29 + #33
4. **27.09 Gate L:** k6 100 VU + мерж PR #34 + #35 + #36
5. **28.09 16:00 RC freeze:** `git tag rc/2026-09-28`

## SOTA сентябрь 2026

| Авторы | Вывод |
|---|---|
| Iversen & Huang (AuC 182) | Hybrid OCR+vector → наш DEGRADED path |
| Fuchs/Hellin/Borrmann (EC3) | BCF канал выгрузки → P2 |
| Xiao et al (AuC 189) | Rule graph → matrix_version v2 |
| Zentgraf et al (AEI 74C) | IFC + рег. нормы → CORENET X port |
| Ishigaki IDS-Bench | IDS benchmark → STUB-IDS-ASSIST-001 приоритет |
