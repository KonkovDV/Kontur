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
| GAP-STAMP | Штамп поверх текста | Сегментация не реализована |

## Артефакты гейта I

| Файл | Назначение |
|---|---|
| `backend/src/kontur/infrastructure/ocr_bakeoff.py` | Решение бейк-оффа, OcrPath, BakeoffDecision |
| `backend/src/kontur/infrastructure/dual_read.py` | Dual-path extraction, DualReadResult |
| `backend/tests/test_ocr_bakeoff.py` | 17 тестов: CA ≥ 0.97 (×8 пар), dual-read (×7), стратегия слоя (×4) |
| `docs/OCR_BAKEOFF.md` | Этот документ |
