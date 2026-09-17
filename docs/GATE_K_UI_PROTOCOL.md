# Gate K — UI/Protocol Specification

> **Deadline:** 26.09.2026 | **Branch:** `gate-k-ui-protocol` | **PR:** #9

---

## 1. Назначение (Gate K Core Constraint)

Гейт K устанавливает фундаментальное ограничение на количество кликов до любого файндинга:

```python
# EvidenceCard.__post_init__ (protocol_service.py)
MAX_CLICKS = 3
if self.clicks_to_navigate > MAX_CLICKS:
    raise ValueError(
        f"Gate K: clicks_to_navigate={self.clicks_to_navigate} > {MAX_CLICKS}."
    )
```

Источник: **HCAI DSS Review 2026** (Cai et al.) — национальный стандарт DSS ≤ 3 клика.

---

## 2. SOTA 2026 — основа архитектуры

| # | Публикация | Год | Применение в Gate K |
|---|---|---|---|
| 1 | **HCAI DSS Review** (Cai et al.) | 2026 | ≤ 3 clicks/finding — core constraint |
| 2 | **Evidence-based XAI Construction** (Zhang et al., §4.2) | 2026 | EvidenceCard + BoundingBox design |
| 3 | **BLUEPRINT** (Liang et al.) | 2026 | Blueprint-aware evidence linking, dual-panel |
| 4 | **ExtractConf** (ACL 2025) | 2025 | Weighted geometric mean confidence scoring |
| 5 | **Risk-Controlled Generative OCR** | 2026 | CRC abstention, CA ≥ 0.97 threshold |
| 6 | **Group-Conditional CRC** (ICML 2026) | 2026 | Per-rule coverage for 106 critical params |
| 7 | **Reading or Guessing?** (EMNLP 2025) | 2025 | Digit hallucination guard via dual-read |
| 8 | **ARCHER** (Ribeiro et al.) | 2025 | Human-in-the-loop annotation design |

### 2.1 Требования HCAI DSS Review 2026

- ≤ 3 клика до любого finding в любой среде пользователя
- PDF-first: PDF — центральная панель, не вспомогательная
- Ознакомление (Familiarity): демо-данные при загрузке без PDF
- Фильтрация по severity в один клик

### 2.2 Требования Evidence-based XAI §4.2

- `EvidenceCard` = `rule_code` + `severity` + `status` + `BoundingBox` + OCR-сниппет
- `BoundingBox` — нормализованные координаты [0,1]×[0,1], page ≥ 1
- Каждый сниппет: `confidence` (ExtractConf) + `character_accuracy` (Gate I)

---

## 3. Архитектура UI (frontend/index.html)

### 3.1 Двухпанельный дизайн

```
+-------------------------------+--------------------+
|   LEFT  60% — PDF Viewer     |  RIGHT 40%         |
|                               |  Evidence Cards    |
|  [PDF Canvas]                 |  BoundingBox over  |
|  Click on bbox → modal (3)   |  severity filter   |
+-------------------------------+--------------------+
```

### 3.2 Протокол этапов (≤ 3 клика)

| Клик | Действие | Код |
|---|---|---|
| **1** | Выбор нарушения в списке (right panel) | `handleCardClick(idx)` |
| **2** | PDF прыгает на страницу + SVG bbox-подсветка | `jumpToPdfPage()` + `drawBbox()` |
| **3** | Клик на bbox → full-screen OCR-сниппет с CA/conf | `openSnippetModal()` |

### 3.3 Критические исправления (Red Team аудит)

| Баг | Проблема | Исправление |
|---|---|---|
| `assync function` | SyntaxError | → `async function` (3 места) |
| BBox height typo | Неверный SVG rect | → `(bbox.y1 - bbox.y0) * H` |
| `URL-meatObjectURL` | TypeError runtime | → `file.arrayBuffer()` + PDF.js |
| `create_or_update_file` | Файлы = 1 строка (raw-b64) | → `push_files` с raw-текстом |

---

## 4. Нормативная карта

| Документ | Применение |
|---|---|
| ГОСТ Р 21.101-2026 | SPDS-стандарт: масштаб, штамп, состав ПД |
| Приказ Минстроя №369/пр (01.03.2026) | Перечень параметров экспертизы |
| ПП Москвы №2078-ПП | Требования Мосгосстройнадзора |
| ПП РФ №87 | Состав ПД (11 разделов) |

---

## 5. Scoring (ТЗ §9.4)

```
Score = F1×60 + loc×15 + value_status×15 + integrity×10
```

- Recall по 106 critical params = **1.00** (иначе cap 59/100)
- Любой BLOCKER → `overall_passed = False`, penalty = 10.0

### Gate J → K thresholds

| Метрика | Gate J | ТЗ |
|---|---|---|
| Precision | ≥ 0.93 | ≥ 0.90 |
| Recall | ≥ 0.83 | ≥ 0.80 |
| F1 | ≥ 0.88 | ≥ 0.85 |
| FPR | ≤ 0.07 | ≤ 0.10 |
| Critical recall | = 1.00 | = 1.00 |

---

## 6. OCR Pipeline (Gate I)

| Этап | Модель | CA | Назначение |
|---|---|---|---|
| Primary | pdfium vector | ≈ 1.000 | Векторные PDF |
| Verifier | Tesseract-5 region-crop ×3 | ≥ 0.97 | Подтверждение |
| Abstain | — | < 0.97 | Расхождение + Low CA |

---

## 7. Каталог 132 параметров

| Группа | Коды | Назначение |
|---|---|---|
| PZ | 001–023 | Раздел ПЗ |
| SPZU | 024–039 | Спец. условия |
| AR | 040–053 | Архитектура |
| KR | 054–067 | Конструктив |
| IOS1 | 068–070 | Водоснабжение |
| IOS2 | 071–073 | Канализация |
| IOS3 | 074–075 | Отопление |
| IOS4 | 076–079 | Вентиляция |
| IOS5 | 080 | Электроснабжение |
| POS | 081–089 | ПОС |
| POD | 090–097 | Постпроектная |
| OOS | 098–101 | Оценка сметы |
| PPM | 102–114 | Пожарная безопасность |
| ODI | 115–123 | Доступность МГН |
| ZU | 124–131 | Земельный участок |
| SM | 132 | Сметный расчёт |

---

## 8. Open GAPs

| ID | Описание | Разблокирует |
|---|---|---|
| GAP-ENUM-EXTRACTOR | Enum/numeric extractor | PZ-013,015,021-023; KR-055 |
| GAP-OCR-ROT | Детектор поворота скана | Все сканы |
| GAP-STAMP | Сегментация штампа | PZ-001 edge cases |
| GAP-BFF | Node.js BFF gateway | Gate L (27.09) |
| GAP-LOAD | k6 load tests | Gate L (27.09) |

---

## 9. Связанные файлы

```
backend/src/kontur/protocol/protocol_service.py  — engine 350 lines
backend/tests/test_gate_k_protocol.py            — 9 classes, 509 lines
frontend/index.html                              — PDF-first UI, 461 lines
docs/GATE_K_UI_PROTOCOL.md                       — этот файл
data/parameter_catalog_132.jsonl                 — полный каталог
backend/src/kontur/evaluation/calibration.py     — Gate J engine
```

---

## 10. Gate L Preview (27.09.2026)

- Node.js BFF Express.js ~200 строк
- OpenAPI 3.0 YAML
- Pull-model для ИАИС «РиН»
- k6: p95 ≤ 200 ms @ 100 VUs
- Circuit breaker + graceful shutdown

---

*Red Team аудит 17.09.2026. Все баги исправлены. Дедлайн Gate K: 26.09.2026.*
