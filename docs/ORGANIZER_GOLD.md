# Публичный gold организатора ≠ frozen validation

Краткий бриф для аудита репозитория. Машиночитаемый источник —
[`data/dataset/gold_inventory.json`](../data/dataset/gold_inventory.json).
Счётчики в этом файле должны совпадать с JSON; при расхождении верен JSON,
тест `test_gold_inventory.py` падает.

**Вердикт (18.09.2026):** документы поставки получены. Гейт J **не** закрыт.
Публичный gold TRAIN_PUBLIC — seed для инженерии, не held-out validation
на 132 параметра и не замер 106 критических.

## Определения (не смешивать)

| Термин | Что это | Что это не |
|---|---|---|
| Поставка / `files/` | Архивы и распакованные каталоги организатора, вне git | Корпус метрик приёмки |
| TRAIN_PUBLIC | `OBJ-TYUMENSKAYA-5-GOLD-SEED` + `OBJ-NOVOSLOBODSKAYA` | Validation-сплит |
| Публичный gold | 15 строк `public_gold_checks.jsonl` | Frozen val на 132/106 |
| `AUTO_FIELD_CANDIDATE` | Автодетект полей (30 286 из 30 318 аннотаций) | Экспертный gold |
| TEST_HIDDEN | `OBJ-RECHNIKOV-7-7`, архив `РАЗМЕЧЕННЫЙ_TEST__213.zip` | Материал для порогов |
| Frozen val | Held-out по `object_id`, JSONL с `gold_positive` / `predicted_positive`, Wilson | Синтетика 16/20 и skip без env |

Разбиение train/validation в продукте — строго по `object_id`
(инвариант 9, `AGENTS.md`). У организатора в `split_policy.json` есть только
`TRAIN_PUBLIC` и `TEST_HIDDEN`. Поля `validation` в инвентаре — пустой список.

## Что лежит в открытом gold

Источник: `VALIDATION.json`, `annotations.jsonl`, `public_gold_checks.jsonl`
пакета `РАЗМЕЧЕННЫЙ_TRAIN_PUBLIC_203` (203 файла, split везде `TRAIN_PUBLIC`).

| Класс | n | Статус | Можно ли закрыть гейт J |
|---|---|---|---|
| `CONFIRMED_VIOLATION_EVIDENCE` | 20 | `FINAL_GOLD_EXISTENCE`, только Тюменская | Нет: 3 кода, не 106 |
| `MATRIX_FIELD` | 13 119 | все `AUTO_FIELD_CANDIDATE` | Нет |
| `DOCUMENT_FIELD` | 17 167 | метаданные штампа, auto | Нет (гейт C тоже не закрыт) |
| Публичные проверки | 15 | см. таблицу ниже | Нет, см. Wilson |

Публичные проверки:

| check_id | object_id | code | label | score_eligible |
|---|---|---|---|---|
| TRAIN-0001 | Тюменская | IOS4-079 | VIOLATION_PRESENT | да |
| TRAIN-0002…0005 | Тюменская | FREE-HEATING-001 | VIOLATION_PRESENT | да, **вне матрицы 132** |
| TRAIN-0006…0010 | Тюменская | IOS4-078 | VIOLATION_PRESENT | да |
| TRAIN-0011 | Новослободская | PZ-009 | NO_VIOLATION | нет |
| TRAIN-0012…0014 | Новослободская | KR-055 | NO_VIOLATION | нет |
| TRAIN-0015 | Новослободская | KR-058 | NO_VIOLATION | нет |

Итого для скоринга матрицы: **6** позитивов (`IOS4-079` ×1 + `IOS4-078` ×5).
Четыре из десяти `score_eligible` — `FREE-HEATING-001` (`MATRIX_GAP`, не
133-я строка). Пять `NO_VIOLATION` — `GOLD_READY_SECOND_REVIEW` и в скоринг
не входят. Паспорт: 0 подтверждённых отрицательных; UNLABELED ≠ NO_VIOLATION.

## Почему это не гейт J

Порог recall ТЗ — минимум приёмки 0,80, достигается **нижней** границей
Wilson 95 %, не точечной оценкой (`kontur.evaluation.metrics.meets_threshold`).
При нуле промахов нижняя граница ≥ 0,80 только с **n ≥ 16** позитивов
(`derived_constraints.perfect_n_min_to_meet_tz_recall`). Идеальные 6/6
порог не берут. 106 критических в gold нет.

Harness замера: `backend/src/kontur/evaluation/frozen_val.py`, opt-in через
`KONTUR_FROZEN_VAL_PATH`. Без пути тесты skip. Карантин — отказ, не skip.
Строка JSONL без `object_id` — ошибка. Синтетика 16/20 **не** закрывает порог
(`test_synthetic_16_of_20_does_not_meet_tz_recall`).
Прогон открытого train: `make train-public` / `train_public.py`. Исходные PDF,
не overlay; JSONL совместим с `load_frozen_val_jsonl`. Gold `RD_ID_MIXED`
(F0201) грузим только как RD, не как ID и не как оба; прочий MIXED skip.
Это не frozen val: `closes_gate_j` остаётся false даже при идеальном recall
на этих 6 строках.

Публиковать P/R/F1 и recall критических по этому gold нельзя
(`scripts/check_claims.py`, инвариант 12 `AGENTS.md`).

## Что поставка двигает вместо J

| Гейт | Роль файлов | Что ещё нужно |
|---|---|---|
| I | OCR-пилот 300 стр. в `02_ЭТАЛОННАЯ_РАЗМЕТКА_И_МЕТОДИКА/ocr_pilot_20260811` | Docker SILVER-замер (`make ocr-pilot`) порог не берёт; не GOLD; GAP-CAP-OCR открыт |
| K | Реальные PDF двух train-объектов; образец Приложения 2 найден | 5 инспекторов → `docs/USABILITY_RESULTS.md` (файла нет) |
| L | Ничего | Живой k6, запись в `PERFORMANCE.md` |
| A | Состав пакета известен | SHA-256 архивов = null; вопросы без артефакта отправки |

Архивы объектов 10–18 есть в [`package_manifest.json`](../data/dataset/package_manifest.json)
и **не** наблюдались в `files/` 18.09.2026. Их отсутствие на одной машине
не отменяет поставку; для frozen val они всё равно без публичного gold.

## Карантин

- `РАЗМЕЧЕННЫЙ_TEST__213` (два подчёркивания) и каталог
  `РАЗМЕЧЕННЫЙ_TEST_HIDDEN_ОРГАНИЗАТОР_213` — не открывать.
- 18.09.2026 в `files/` каталог скрытого теста распакован рядом с train.
  Это нарушение чек-листа Gate A «карантин не распакован». Перенести в
  `data/quarantine/`, не читать содержимое, не считать хеши ответов.
- Документы Речникова в открытом `01_ДОКУМЕНТАЦИЯ` — утечка корпуса, не
  ответов. Allowlist: только два TRAIN_PUBLIC `object_id`.

## Запрещено аудитору и агенту

1. Закрыть `GAP-IOS4-VAL` на основании «файлы прислали».
2. Объявить `MATRIX_FIELD` gold.
3. Смотреть скрытый тест «чтобы понять разметку».
4. Писать в README достигнутые проценты без frozen val, n и 95 % CI.
5. Смешивать coverage `executable` (гейт H) с заявлением, что вся матрица executable.
