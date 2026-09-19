# Errata аудиторского отчёта «~46–47% ТЗ»

Снимок, на который опирался отчёт, — `main` после
[`d5e25cf`](https://github.com/KonkovDV/Kontur/commit/d5e25cf). Этот файл
**не** публикует встречный процент реализации. Взвешенный балл ТЗ без frozen
val, n и Wilson не считается (инвариант 12, `scripts/check_claims.py`).

Отчёт полезен как радар дыр. Как итог приёмки — нет: смешаны контракт,
executable-слайс и замер.

## Вердикт

Инфраструктура API/RBAC/state machine/audit на `main` сильная. Главная функция
продукта — камеральная сверка ПД↔РД↔ИД с решением инспектора, не
«автоматическая сверка 132 параметров». `CONFIRMED_VIOLATION` пишет только
человек (ADR-0001).

## Ошибки факта

| Утверждение отчёта | Факт |
|---|---|
| Итог ~46–47% ТЗ | Не метрика. Нет весов ТЗ, нет замера на frozen val |
| Матрица 90%, YAML-каталог | 132 schema-valid **JSON** в `data/matrix/rules/`. `executable` — только `coverage_report` |
| OpenAPI 3.0 | `contracts/openapi.yaml` — **3.1.0** |
| 6 состояний процесса включают VERIFICATION_COMPLETED / PROTOCOL_FINALIZED | Это **провод протокола** (ADR-0005). Процесс: `PENDING`…`COMPLETED`/`FINALIZED` |
| Persistence = PR #47 / #48 | As-is отклонены; на main — срезы в `schema.sql` |
| `recall.py` | Файла нет. Harness: `kontur.evaluation.frozen_val` |
| Frozen val «корпуса нет» | Документы TRAIN_PUBLIC и 15 публичных gold-проверок есть. Held-out val на 132/106 нет. [`ORGANIZER_GOLD.md`](ORGANIZER_GOLD.md) |
| SUSPICION 8% = GAP-FREE-SEARCH, «логики нет» | Два объекта. `suspicion.py` — 4 подхода п. 9.5. `FREE-HEATING-001` — `MATRIX_GAP` |
| «Реального сравнения нет» | Не было **проводки в HTTP**. Компаратор `evaluate_rule` / `compare_against_pd` есть. С 19.09 каскад вызывается после upload (векторный слой) |
| Нет Sentence-BERT = нет NLP | Вердикт детерминированный (ADR-0001). Дыра — OCR/таблицы в запросе, не BERT |
| Дообучение 18% как High для приёмки | Скоринг конкурса — F1/локализация/статус, не weekly fine-tune |

## Что в отчёте совпадает с репозиторием

Живого OCR в запросе как **принятого слоя** нет (`GAP-CAP-OCR`): адаптер
Tesseract на пустом растре может вызваться, capabilities остаются
`UNAVAILABLE`, CA на пилоте не измерена. Гейт J не закрыт. p95 на стенде не
измерен. UI — каркас. Prometheus/ELK нет. TLS/УКЭП/антивирус нет. РиН — mock.
CV чертежа: геометрия есть, детектора линий нет.

## Что нельзя делать по этому отчёту

- Класть 46% в README или презентацию.
- Добавлять 133-е правило ради free-search.
- Открывать TEST_HIDDEN «чтобы поднять recall».
- Подключать облачный LLM/BERT как писателя `finding_status`.
- Объявлять гейт I закрытым бейк-оффом, бинарником Tesseract или
  `wilson(290, 300)` без прогона `ocr_pilot_20260811`.

Операционный план: [`WORK_PLAN.md`](WORK_PLAN.md).
