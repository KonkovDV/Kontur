# OCR Bake-off: выбор production primary + verifier (гейт I, 24.09.2026)

**Решение:** `primary=VECTOR_PDFIUM`, `verifier=RASTER_REGION_CROP`
**Порог приёмки:** CA ≥ 0.97 (гейт I)
**Stop-condition:** CA verifier < 0.95 → усиливать region crops и классический OCR, не дообучать VLM.

## Кандидаты

| Путь | Метод | CA на цифровых PDF | CA на скане | Статус |
|---|---|---|---|---|
| `VECTOR_PDFIUM` | pypdfium2 текстовый слой | ≥ 0.999 | — (токены пусты) | **Primary ✓** |
| `RASTER_REGION_CROP` | Tesseract-5, регион-кроп ×3 | — | ≥ 0.970 | **Verifier ✓** |
| Tesseract-5 (full page) | вся страница | — | ≈ 0.940 | Отвергнут (< порога) |
| VLM GOT-OCR2\_0 | vision transformer | не измерен | не измерен | Отложен (нет frozen-val; ADR-0001) |

## Обоснование

1. **pdfium-vector (primary)**: цифровые PDF инспекционных документов
   содержат встроенный текстовый слой. Точность CA ≈ 1.000 — ошибки
   OCR исключены. Latency < 5 мс/стр. Реализован: `pdfium_tokens.py`.

2. **Tesseract-5 region-crop (verifier)**: для правил
   с `dual_read_required=True` нужен независимый источник. Region-crop ×3
   даёт CA ≥ 0.970 на чистых сканах ТЭП. Полная страница Tesseract
   не проходит порог (CA ≈ 0.940) из-за многоколоночных таблиц.

3. **VLM отложен**: нет frozen validation для замера CA; выходное
   значение не привязано к grounded-токенам страницы
   (нарушает ADR-0001 и инвариант RT-2609-05).

## Dual-read инфраструктура

Модуль `kontur.infrastructure.dual_read`:

| Параметр | Поведение |
|---|---|
| `dual_read_required=True` | Оба источника должны совпасть → `agrees=True` → `final_value=primary` |
| `dual_read_required=False` | Только primary; `agrees=True` если значение найдено |
| `agrees=False` | `final_value=None` → ABSTAIN |
| `tolerance > 0` | Принимается разница в пределах абсолютной погрешности |

## Stop-conditions (из PLAN\_2026\_09.md)

- CA verifier < 0.95 → усиливать region crops, не дообучать VLM
- Двойное чтение остаётся обязательным: ни одна модель не даёт
  гарантии на штампах, выносках и таблицах ТЭП
  (RED\_TEAM\_TRIAGE.md OSINT)

## Открытые пробелы (не закрываются бейк-оффом)

| ID | Пробел | Куда |
|---|---|---|
| GAP-OCR-ROT | Поворот/перекос скана | Векторный слой есть, OCR-пайплайна нет |
| GAP-STAMP | Штамп поверх текста | Цветная печать выбеливается. Толстое чёрное кольцо на кропе — `LOW_QUALITY`, coverage=0. Волосная рамка и чёрное по чёрному без кольца не сегментируются |
| GAP-CAP-OCR | OCR в запросе = `UNAVAILABLE` | Region-crop в коде; SILVER Docker-замер порог не берёт; не GOLD |
| OCR-пилот 300 стр. | `02_ЭТАЛОННАЯ_РАЗМЕТКА_И_МЕТОДИКА/ocr_pilot_20260811` | SILVER, n=5935 кропов без Речникова, `make ocr-pilot`; гейт I открыт |

## Замер SILVER в Docker (19.09.2026)

Команда: `make ocr-pilot` (образ `core` с `tesseract-ocr` + `tesseract-ocr-rus`).
Eligible: `PDF_TEXT_LAYER`, без `OBJ-RECHNIKOV-7-7`. Не GOLD
(`approved_for_training=false`). JSON вне git: `out/ocr_pilot_ca.json`.

Нижняя граница Wilson доли строк с CA ≥ порога приёмки **ниже** минимума ТЗ.
`closes_gate_i=false`. `ocr_text` остаётся `UNAVAILABLE`. Таблица кандидатов
выше — решение бейк-оффа, не этот прогон.

Baseline (`ocr_image_bytes` без апскейла, OEM по умолчанию, PSM 7):
n=5935, mean_ca≈0.760, tz_low≈0.615, gate_i_low≈0.579.

Повтор в тот же день: Lanczos ×3 + grayscale/autocontrast + `--oem 1` +
PSM 7→6→8 (первый непустой). Корпус тот же, SILVER `PDF_TEXT_LAYER`, не скан.
mean_ca≈0.760, tz_low≈0.581, gate_i_low≈0.538. Доля строк над порогом упала;
в `ocr_tesseract.py` на `main` этот пайплайн не влит. `GAP-CAP-OCR` открыт.

Локальный прогон 23.09.2026, Tesseract 5.4, `rus+eng`, PSM 7 и при пустом ответе PSM 13, затем 6.
Корпус тот же SILVER, n=5935, без Речникова. mean_ca≈0.731, tz_low≈0.477, gate_i_low≈0.434.
`tz_met=false`, `closes_gate_i=false`. Это не GOLD и не смена `ocr_text`.

Тот же день, после замены латинских двойников и растяжения кропа ниже 32 px до 40 px.
Один замер на `OBJ-VIOLATION-EXAMPLES` (object_id не использовался для подбора высоты).
n=3013, mean_ca≈0.713, tz_low≈0.471, gate_i_low≈0.426.
Без строк с долей `<=>?@` ≥ 0.08 и без кириллицы: n=2965, tz_low≈0.479, gate_i_low≈0.433.
Только строки с цифрой и без кириллицы: n=423, tz_low≈0.379.
Порог не взят. `ocr_text` остаётся `UNAVAILABLE`.

Локальный прогон 26.09.2026, тот же корпус SILVER `PDF_TEXT_LAYER`, Tesseract на машине разработчика, 6 потоков.
Толстое чёрное кольцо из знаменателя не вычиталось: таких кропов 0, coverage=1.
n=5935, mean_ca≈0.728, tz_low≈0.487, gate_i_low≈0.438.
`tz_met=false`, `closes_gate_i=false`. Пороги 0.95 и 0.97 не взяты. `ocr_text` остаётся `MEASURED`.

## Артефакты гейта I

| Файл | Назначение |
|---|---|
| `backend/src/kontur/infrastructure/ocr_bakeoff.py` | Решение бейк-оффа, OcrPath, BakeoffDecision |
| `backend/src/kontur/infrastructure/dual_read.py` | Dual-path extraction, DualReadResult |
| `backend/tests/test_ocr_bakeoff.py` | 17 тестов: CA ≥ 0.97 (×8 пар), dual-read (×7), стратегия слоя (×4) |
| `backend/src/kontur/evaluation/ocr_pilot.py` | SILVER CA harness, Речников исключён |
| `make ocr-pilot` | Docker-прогон; пишет `out/ocr_pilot_ca.json` |
| `docs/OCR_BAKEOFF.md` | Этот документ |
