# Дополнительные материалы

**Ссылка для формы:** https://github.com/KonkovDV/Kontur/tree/main/submission/05-additional

Реестр доказательств Контура на 28.09.2026. У каждого числа указаны источник,
происхождение и граница толкования. Все числа получены на публичной разметке
разработки, синтетике или инженерных прогонах. Порогом раздела 14 ТЗ ни одно
из них не является. Гейты приёмки I/J/K/L открыты.

## Содержание

1. [Сводка](#1-сводка)
2. [Покрытие матрицы](#2-покрытие-матрицы)
3. [Публичный gold: пять повторов](#3-публичный-gold-пять-повторов)
4. [OCR](#4-ocr)
5. [Нагрузка и холодный запуск](#5-нагрузка-и-холодный-запуск)
6. [Пример JSON](#6-пример-json)
7. [Происхождение кода: CI влитых срезов](#7-происхождение-кода-ci-влитых-срезов)
8. [Ориентир 2026, не замер Контура](#8-ориентир-2026-не-замер-контура)
9. [Что не сделано](#9-что-не-сделано)
10. [Материалы](#10-материалы)

## 1. Сводка

| Замер | Значение | n | Источник | Чем не является |
|---|---|---|---|---|
| Покрытие матрицы | 55 executable, 72 extractor_missing, 1 advisory, 4 source_missing | 132 правила | [`coverage_snapshot.json`](../../data/matrix/coverage_snapshot.json) | Заявлением, что все параметры исполняются |
| Публичный gold, матрица | 0 попаданий, Wilson [0; 0,39] | 6 позитивов | [`GOLD_DIAGNOSIS.md`](../../docs/GOLD_DIAGNOSIS.md) | Порогом Recall |
| Публичный gold, свободный поиск | 0 попаданий, Wilson [0; 0,49] | 4 позитива | там же | Порогом Recall |
| OCR, eslav PP-OCRv5 | нижняя граница Wilson 0,663 доли строк с CA не ниже 0,95 | 5935 строк SILVER | [`OCR_BAKEOFF.md`](../../docs/OCR_BAKEOFF.md) | Замером на GOLD. Порог 0,95 не взят |
| k6 на `/status` | p50 7,12 мс, p95 18,26 мс, p99 32,80 мс, ошибок 0 | 6000 запросов, 100 VU × 60 с | [`PERFORMANCE.md`](../../docs/PERFORMANCE.md) | Промышленным SLA |
| Холодный запуск из tar | `healthz` 200, core и gateway `healthy` | 2 прогона, 27.09 и 28.09 | [`DEMO_COLD_START.md`](../../docs/DEMO_COLD_START.md) | Прогоном с вынутым кабелем на чистом Linux |
| Сценарий API учебного комплекта | 3 `CANDIDATE` → 2 подтверждены, 1 отклонён, протокол финализирован | синтетика | [`04-prototype`](../04-prototype/README.md#7-тот-же-сценарий-через-api) | Точностью: расхождения заложены в комплект |
| Сессии инспекторов | нет | 0 из 5 | [`USABILITY_RESULTS.md`](../../docs/USABILITY_RESULTS.md) | — |

Правило решения: порог считается взятым только по нижней границе 95%
интервала на frozen validation. Такой выборки нет.

## 2. Покрытие матрицы

Пересчитано по файлам [`data/matrix/rules/`](../../data/matrix/rules/). Правило
без рабочего экстрактора нарушения не выдаёт.

**По типу экстрактора**

| Тип | Правил | executable | extractor_missing | advisory | source_missing |
|---|---|---|---|---|---|
| `number` | 74 | 30 | 44 | 0 | 0 |
| `enum` | 19 | 10 | 9 | 0 | 0 |
| `exact_field` | 16 | 4 | 8 | 0 | 4 |
| `presence` | 12 | 0 | 11 | 1 | 0 |
| `multi_field` | 7 | 7 | 0 | 0 | 0 |
| `contour_area` | 2 | 2 | 0 | 0 | 0 |
| `element_table` | 1 | 1 | 0 | 0 | 0 |
| `geometry` | 1 | 1 | 0 | 0 | 0 |
| Итого | 132 | 55 | 72 | 1 | 4 |

**По разделу матрицы**

| Раздел | Правил | executable | Остальные |
|---|---|---|---|
| ПЗ | 23 | 23 | — |
| СПЗУ | 16 | 4 | 12 extractor_missing |
| АР | 14 | 5 | 9 extractor_missing |
| КР | 14 | 5 | 9 extractor_missing |
| ППМ | 13 | 4 | 9 extractor_missing |
| ОДИ | 9 | 0 | 9 extractor_missing |
| ПОС | 9 | 2 | 7 extractor_missing |
| ЗУ | 8 | 6 | 2 extractor_missing |
| ПОД | 8 | 1 | 6 extractor_missing, 1 advisory |
| ООС | 4 | 0 | 4 source_missing |
| ИОС4 | 4 | 2 | 2 extractor_missing |
| ИОС1, ИОС2 | 3 и 3 | 1 и 1 | 2 и 2 extractor_missing |
| ИОС3, ИОС5 | 2 и 1 | 0 | 2 и 1 extractor_missing |
| СМ | 1 | 1 | — |

Почему правила остались `extractor_missing` — поштучно в
[`number_family_triage.json`](../../data/matrix/number_family_triage.json),
[`class_ladder_triage.json`](../../data/matrix/class_ladder_triage.json) и
[`family_triage.json`](../../data/matrix/family_triage.json). Подсчёт объектов на
плане, площадь по нескольким контурам и таблица по элементам в `executable`
не переводились. Четыре правила ООС ссылаются на источники вне пакета
ПД/РД/ИД.

## 3. Публичный gold: пять повторов

Объект `OBJ-TYUMENSKAYA-5-GOLD-SEED`: 50 загруженных файлов, 46 ПД и 4 РД.
Разметка: 6 позитивов матрицы (IOS4-078 в помещениях 140, 142, 147, 198, 314;
IOS4-079 в помещении 012) и 4 позитива свободного поиска `FREE-HEATING-001`.
Это не frozen validation. Строки Новослободской помечены `score_eligible=false`
и в FPR не входят, поэтому FPR на этом счёте не определён.

Каждый повтор снимал одну ошибку цепочки и останавливался на следующей.
Пороги сравнения помещений ни в одном повторе не подбирались.

| Повтор | Код | Остановка | Матрица | Свободный поиск |
|---|---|---|---|---|
| До разделения пустых шифров | до `3fcedfe` | Все 132 правила: «несколько редакций без однозначного successor для PD» | 0 из 6 | 0 из 4 |
| После разделения | манифест `3fcedfe` | 103 раза «нет документа раздела», 29 раз «сведения об утверждении отсутствуют» | 0 из 6 | 0 из 4 |
| После `sole_head` | `c18cf8e` | «шифр части файлов стадии PD не прочитан» | 0 из 6 | 0 из 4 |
| После якоря шифра | код `d5e4a0e`, манифест `05e3470` | «якорь или число не найдены». В режиме `code` 1 из 6 за счёт помещения 600, которого нет в разметке | 0 из 6 | 0 из 4 |
| После метки и пар листов | код `3bc590f`, манифест `9bd8753` | «якорь или число не найдены». Помещение 600 в ответ не вышло | 0 из 6 | 0 из 4 |

Последний повтор: 132 правила, сбоев 0, пропусков 8, `pipeline_seconds` 1406,
`elapsed_seconds` 1656, `model_version` `tesseract-5.4.0.20240606`.
`git_sha` в манифесте — репозиторий в момент записи, а не импортированный код:
отсюда пары «код / манифест» в таблице.

## 4. OCR

Пилот SILVER: 5935 строк с текстовым слоем PDF, без объекта скрытого теста.
Эталон строки — текстовый слой, не ручная разметка. Замер в образе ядра 26.09.

| Движок | n | Средняя CA | Нижняя граница, CA ≥ 0,95 | Нижняя граница, CA ≥ 0,97 | Время |
|---|---|---|---|---|---|
| eslav PP-OCRv5 mobile | 5935 | 0,794 | 0,663 | 0,632 | 88 с, 1 поток |
| Tesseract 5.5 `rus+eng` | 5935 | 0,777 | 0,635 | 0,603 | 117 с, 6 потоков |

Нижняя граница — интервал Wilson для доли строк, прочитанных не хуже порога.
Пороги 0,95 и 0,97 не взяты, статус `ocr_text` — `MEASURED`. Часть промахов —
дефекты эталона: перевёрнутый текст вертикальных граф, невидимый служебный
слой, битая кодировка шрифта. Перерисовка в 300 dpi на выборке 593 строк
долю верных строк не подняла.

## 5. Нагрузка и холодный запуск

**k6.** 100 виртуальных пользователей 60 секунд опрашивают `/status` раз в
секунду. Прогон GitHub Actions `35463988098`, job `105952743651`: 6000 запросов,
0 ошибок, p50 7,12 мс, p95 18,26 мс, p99 32,80 мс. Это инженерный замер на
раннере CI, а не норматив пункта 11 ТЗ.

**Холодный запуск.** Windows, Docker Engine 29.8.0, Compose v5.5.1, 20 CPU.
Четыре образа приложения удалены, возвращены `docker load`, стенд поднят
с `pull_policy: never` и `--no-build`.

| Дата | Образы собраны с | tar, байт | SHA-256 tar | Результат |
|---|---|---|---|---|
| 27.09 | `438b63f` | 2606031360 | `60c7a93b…9a0c4e` | `healthz` 200 на `:8000` и `:3000` |
| 28.09 | `b6645cd` | 1811542016 | `f0333651…66b8e3` | `healthz` 200, core и gateway `healthy` |

Сеть хоста в обоих прогонах не отключалась. Tar в git не входит.

## 6. Пример JSON

Собран кодом из синтетического учебного комплекта, не из документов
организатора: `python scripts/export_submission_example.py`. Оба исхода
проходят `submission.schema.json` и `protocol.schema.json`, это держит тест
`test_submission_examples.py`.

| Папка | Исход |
|---|---|
| [`unattended/`](examples/unattended/submission.json) | Пакет без инспектора. 132 строки `COMPARISON_IMPOSSIBLE`, `violation_count` 0. [Протокол](examples/unattended/protocol.json) |
| [`after_etalon_select/`](examples/after_etalon_select/submission.json) | Инспектор назначил эталоном `f-pd`. PZ-001, KR-055 и AR-041 на проводе ответа — `VIOLATION_PRESENT`, внутри — `CANDIDATE`. Подтверждённых нарушений 0. [Протокол](examples/after_etalon_select/protocol.json) |

Одна строка ответа из `after_etalon_select/submission.json`:

```json
{
  "parameter_code": "PZ-001",
  "location": "объект",
  "violation_label": "VIOLATION_PRESENT",
  "evidence": [
    {"stage": "PD", "file_id": "f-pd", "pdf_page_number": 1},
    {"stage": "RD", "file_id": "f-rd", "pdf_page_number": 1}
  ],
  "pd_value": 1250.5,
  "rd_value": 1100.0,
  "protocol_status": "CRITICAL",
  "rationale": "расхождение -150.5 м²: ожидалось 1250.5, получено 1100.0"
}
```

| Поле | Что значит |
|---|---|
| `parameter_code` | Канонический трёхзначный код матрицы |
| `location` | Ключ точки. Номер помещения, если он есть; иначе «объект» |
| `violation_label` | Одна из четырёх меток схемы организатора |
| `evidence` | Стадия, файл и страница каждого фрагмента. Без него `VIOLATION_PRESENT` не выпускается |
| `pd_value`, `rd_value` | Нормализованные значения стадий |
| `protocol_status` | `CRITICAL` только при приоритете `HIGH` в правиле |
| `rationale` | Текст компаратора, не текст модели |

Протокол несёт `versions` (`git_sha`, `matrix_version`, `dataset_version`,
`model_version`) и `input_manifest.manifest_hash` по четырём файлам комплекта.
Подробнее — [`examples/README.md`](examples/README.md).

## 7. Происхождение кода: CI влитых срезов

Ruleset `main-pr-and-ci`, id 23890545: PR обязателен, 11 обязательных checks —
`backend`, `contracts`, `db`, `claims`, `frontend`, `container-config`,
`container-core`, `container-gateway`, `container-smoke`, `relay-container`,
`sync-lifecycle-db`. Обязательных ревью 0. Прогон считается зелёным, только если
у job `backend` `conclusion=success`, `runner_id` не 0 и шаги не пусты.

Срезы, которые меняли поведение 28.09:

| PR | Что | CI run | runner_id |
|---|---|---|---|
| [#258](https://github.com/KonkovDV/Kontur/pull/258) | Якорь шифра не втягивает файлы без шифра | [36374418984](https://github.com/KonkovDV/Kontur/actions/runs/36374418984) | 1000024312 |
| [#260](https://github.com/KonkovDV/Kontur/pull/260) | Счёт: схема, `score_eligible`, режим `location` | [36375114171](https://github.com/KonkovDV/Kontur/actions/runs/36375114171) | 1000024334 |
| [#262](https://github.com/KonkovDV/Kontur/pull/262) | DOCX: абзацы и таблицы | [36375592673](https://github.com/KonkovDV/Kontur/actions/runs/36375592673) | 1000024358 |
| [#264](https://github.com/KonkovDV/Kontur/pull/264) | Манифест: `object_id_basis`, `model_version` | [36376182725](https://github.com/KonkovDV/Kontur/actions/runs/36376182725) | 1000024380 |
| [#267](https://github.com/KonkovDV/Kontur/pull/267) | Пачка подтверждения только из `CANDIDATE` | [36377568436](https://github.com/KonkovDV/Kontur/actions/runs/36377568436) | 1000024439 |
| [#269](https://github.com/KonkovDV/Kontur/pull/269) | Шлюз: `FILE_TOO_LARGE`, `RATE_LIMITED`, healthcheck | [36378367595](https://github.com/KonkovDV/Kontur/actions/runs/36378367595) | 1000024475 |
| [#277](https://github.com/KonkovDV/Kontur/pull/277) | Все пары листов при сравнении помещений | [36416127035](https://github.com/KonkovDV/Kontur/actions/runs/36416127035) | 1000024578 |
| [#279](https://github.com/KonkovDV/Kontur/pull/279) | Ключ `location` — номер как в разметке | [36418156608](https://github.com/KonkovDV/Kontur/actions/runs/36418156608) | 1000024596 |
| [#281](https://github.com/KonkovDV/Kontur/pull/281) | Метка с индексом, повтор номера гасит только себя | [36422952328](https://github.com/KonkovDV/Kontur/actions/runs/36422952328) | 1000024621 |
| [#289](https://github.com/KonkovDV/Kontur/pull/289) | Пример JSON и тест схем | [36432688577](https://github.com/KonkovDV/Kontur/actions/runs/36432688577) | 1000024709 |

У #281 первый `container-smoke` упал по таймауту индекса пакетов Python
при сборке и прошёл повтором.

## 8. Ориентир 2026, не замер Контура

Источники уже названы в документации репозитория. Цифры чужих работ точностью
Контура не являются и в [`METRICS.md`](../../docs/METRICS.md) не переносятся.

| Источник | Что из него следует для Контура |
|---|---|
| AECV-Bench, arXiv:2601.04819 | Подсчёт дверей и окон на плане у моделей слабый. Такие правила остаются `extractor_missing` |
| Лидеры OmniDocBench v1.6: PaddleOCR-VL-1.6, MinerU2.5-Pro, Qwen3-VL | Корпус бенчмарка в основном китайско-английский, VLM-бэкенды требуют GPU. В офлайн-прогон на CPU не переносились |
| PP-OCRv6 (PaddleOCR 3.7.0) без русского языка | Стек OCR не менялся, для кириллицы остаётся eslav PP-OCRv5 |
| OWASP, инъекции через документ | PDF — недоверенный вход. Модель не пишет `finding_status` |
| Правило интервала в [`METRICS.md`](../../docs/METRICS.md) | Для доли — Wilson. При n меньше 30 интервал Вальда не используется |

Разбор источников — [`PLAN_2026_09_28_29.md`](../../docs/PLAN_2026_09_28_29.md),
раздел про SOTA, и [`RESEARCH_OSINT_2026.md`](../../docs/RESEARCH_OSINT_2026.md).

## 9. Что не сделано

| Пробел | Где отслеживается |
|---|---|
| Пять сессий инспекторов (Gate K) | [#77](https://github.com/KonkovDV/Kontur/issues/77), [`USABILITY_RESULTS.md`](../../docs/USABILITY_RESULTS.md) |
| Frozen validation и пороги раздела 14 | [`KNOWN_GAPS.md`](../../docs/KNOWN_GAPS.md), GAP-IOS4-VAL |
| OCR на уровне порога, GOLD по растру | [`OCR_BAKEOFF.md`](../../docs/OCR_BAKEOFF.md), GAP-CAP-OCR |
| Атомарное разделение находки, `split()` | [#83](https://github.com/KonkovDV/Kontur/issues/83) |
| Изоляция VLM от инъекций в документе | [#84](https://github.com/KonkovDV/Kontur/issues/84) |
| Разбор XML | [`KNOWN_GAPS.md`](../../docs/KNOWN_GAPS.md), GAP-DOCX-XML |
| Живой РиН, ACK, УКЭП, OIDC | [`ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) |
| Видео показа | человек |

## 10. Материалы

| Материал | Роль |
|---|---|
| [`03-presentation/`](../03-presentation/README.md) | Папка поля «Презентация»: PowerPoint и PDF |
| [`02-documentation/`](../02-documentation/README.md) | Досье: постановка, решения, методология, угрозы достоверности |
| [`04-prototype/`](../04-prototype/README.md) | Протокол воспроизведения стенда |
| [`openapi.yaml`](../../contracts/openapi.yaml) | Контракт API |
| [`submission.schema.json`](../../contracts/schemas/submission.schema.json) | Схема ответа участника |
| [`GOLD_DIAGNOSIS.md`](../../docs/GOLD_DIAGNOSIS.md) | Разбор каждого повтора публичного gold |
| [`KNOWN_GAPS.md`](../../docs/KNOWN_GAPS.md) | Реестр пробелов |
