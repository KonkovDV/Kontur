<p align="center">
  <img src="Logo.png" alt="Логотип Контур" width="480">
</p>

<p align="center">
  <a href="https://github.com/KonkovDV/Kontur/raw/main/submission/03-presentation/Kontur.pptx"><img alt="Презентация в PowerPoint" src="https://img.shields.io/badge/%D0%9F%D1%80%D0%B5%D0%B7%D0%B5%D0%BD%D1%82%D0%B0%D1%86%D0%B8%D1%8F-PowerPoint-B7472A?style=for-the-badge&amp;logo=libreofficeimpress&amp;logoColor=white"></a>
  <a href="https://github.com/KonkovDV/Kontur/blob/main/submission/03-presentation/Kontur.pdf"><img alt="Презентация в PDF" src="https://img.shields.io/badge/%D0%9F%D1%80%D0%B5%D0%B7%D0%B5%D0%BD%D1%82%D0%B0%D1%86%D0%B8%D1%8F-PDF-EC1C24?style=for-the-badge&amp;logo=files&amp;logoColor=white"></a>
</p>

<p align="center">
  <a href="https://github.com/KonkovDV/Kontur/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/KonkovDV/Kontur/actions/workflows/ci.yml/badge.svg?branch=main"></a>
  <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?logo=python&amp;logoColor=white">
  <a href="docker-compose.offline.yml"><img alt="Docker Compose офлайн" src="https://img.shields.io/badge/Docker_Compose-offline-2496ED?logo=docker&amp;logoColor=white"></a>
  <a href="contracts/openapi.yaml"><img alt="OpenAPI 3.1" src="https://img.shields.io/badge/OpenAPI-3.1-6BA539?logo=openapiinitiative&amp;logoColor=white"></a>
  <img alt="Задача №10, Мосгосстройнадзор" src="https://img.shields.io/badge/%D0%B7%D0%B0%D0%B4%D0%B0%D1%87%D0%B0_%E2%84%9610-%D0%9C%D0%BE%D1%81%D0%B3%D0%BE%D1%81%D1%81%D1%82%D1%80%D0%BE%D0%B9%D0%BD%D0%B0%D0%B4%D0%B7%D0%BE%D1%80-520978">
  <a href="docs/METRICS.md"><img alt="132 параметра матрицы" src="https://img.shields.io/badge/матрица-132_параметра-520978"></a>
</p>

# Контур — «Инспектор ИИ»

Сервис камеральной сверки проектной (ПД), рабочей (РД) и исполнительной (ИД)
документации по матрице из 132 контролируемых параметров. Задача №10,
Мосгосстройнадзор.

Контур находит расхождение между стадиями и кладёт на карточку файл, страницу,
SHA-256 и область на листе. Подтверждает расхождение инспектор.

Репозиторий публичный, открытой лицензии на код нет: он передаётся заказчику
задачи. Замеры gold и OCR сняты 28.09.2026 и после правок штампа не повторялись.

**Для жюри:** [пакет формы](submission/README.md) ·
[досье](submission/02-documentation/README.md) ·
[протокол запуска](submission/04-prototype/README.md) ·
[реестр доказательств](submission/05-additional/README.md) ·
[пример JSON](submission/05-additional/examples/README.md) ·
[карта документов](docs/README.md)

## Содержание

- [Куда смотреть](#куда-смотреть)
- [Коротко](#коротко)
- [Задача заказчика](#задача-заказчика)
- [Как устроено](#как-устроено)
- [Редакция и знак триггера](#редакция-и-знак-триггера)
- [Запуск за пять минут](#запуск-за-пять-минут)
- [Сценарий на учебном комплекте](#сценарий-на-учебном-комплекте)
- [Состав](#состав)
- [Метрики](#метрики)
- [Границы, которые не нарушаются](#границы-которые-не-нарушаются)
- [Документы](#документы)

## Куда смотреть

1. Стенд — [запуск](#запуск-за-пять-минут), затем http://127.0.0.1:3000.
2. Учебный комплект — [сценарий](#сценарий-на-учебном-комплекте): эталон, три кандидата, протокол, очередь в РиН.
3. Замеры — [реестр](submission/05-additional/README.md) и [метрики](docs/METRICS.md).
4. Пункт ТЗ — [трассируемость](docs/TZ_TRACEABILITY.md).

Карта документов — [`docs/README.md`](docs/README.md). Покрытие и гейты — в таблице ниже и в [`docs/TZ_SCORECARD.md`](docs/TZ_SCORECARD.md).

## Коротко

Контур выбирает голову редакции, читает значение со страницы, сравнивает стадии по правилу матрицы и собирает карточку. Инспектор подтверждает или отклоняет. Протокол выходит в JSON, DOCX, XML и PDF.

Стенд поднимается одной командой и из офлайн-tar. Учебный комплект доходит до финализированного протокола. Рабочий экстрактор есть у 59 правил из 132. Ещё 68 ждут своего экстрактора, 4 смотрят во внешний источник, 1 справочное.

На публичной разметке Тюменской матрица дала 0 из 6, свободный поиск 0 из 4. OCR на SILVER: нижняя граница 0,663 при пороге 0,95. Гейты I, J, K и L в приёмке ещё впереди: нет frozen validation, пяти сессий и живого РиН.

## Задача заказчика

Инспектор получает комплект томов трёх стадий и сверяет их вручную: площадь
застройки в ПД и в РД, класс бетона, ширину проёма, сечение воздуховода.
Параметров 132, томов десятки, у тома бывает несколько редакций, часть листов —
скан без текстового слоя. Ошибка на этом пути бывает двух видов: пропущенное
расхождение и «нарушение», которое на деле вызвано неполным комплектом или
чужой редакцией.

Контур забирает на себя поиск по томам:

1. Находит голову редакции тома. Шифр штампа важнее имени файла. Если штамп
   шифра не дал, цепочку ПД и РД собирает имя без метки редакции.
2. Достаёт значение параметра из текстового слоя страницы. Если слоя нет —
   распознаёт страницу локально.
3. Сравнивает значения стадий по правилу матрицы и собирает доказательство.

Подпись под нарушением ставит инспектор. Пустая стадия получает статус `MISSING_EVIDENCE`. Непрочитанное значение получает `ABSTAIN` или `LOW_QUALITY`.

Единица результата — точка `object_id + parameter_code + location`
(ответ организатора 14). Сверяются ПД, РД и ИД между собой
([ADR-0006](docs/adr/0006-compare-documents-not-norms.md)).

## Как устроено

```mermaid
flowchart LR
    A[Загрузка ПД, РД, ИД] --> B[Голова редакции]
    B --> C[Экстрактор правила]
    C --> D[Компаратор матрицы]
    D --> E[Карточка: файл, страница, SHA-256, polygon]
    E --> F{Инспектор}
    F -->|подтвердить| G[CONFIRMED_VIOLATION]
    F -->|отклонить с причиной| H[NEGATIVE_VERIFIED]
    G --> I[Протокол JSON, DOCX, XML, PDF]
    H --> I
    I --> J[Очередь в РиН, mock]
```

| Шаг | Что делает | Решение |
|---|---|---|
| Редакция | Цепочка внутри шифра. Пустой шифр чужой том не прячет. Имя файла собирает цепочку только без шифра штампа. Подробности — ниже | [ADR-0003](docs/adr/0003-revision-resolver-before-comparison.md), [ADR-0017](docs/adr/0017-sole-head-without-stamp.md) |
| Извлечение | Сначала вектор страницы через pdfium, координаты после CropBox, MediaBox и Rotate. Пустой слой — локальный OCR: eslav PP-OCRv5, затем Tesseract. DOCX — абзацы и таблицы | [`OCR_BAKEOFF.md`](docs/OCR_BAKEOFF.md) |
| Правило | 132 параметра лежат данными в [`data/matrix/`](data/matrix/), не кодом. Правило без экстрактора остаётся `extractor_missing` и нарушения не выдаёт | [ADR-0004](docs/adr/0004-rules-are-data.md) |
| Вердикт | Допуск, округление, лестница классов, знак триггера. Разность десятичная. Модель не пишет `finding_status` | [ADR-0001](docs/adr/0001-llm-never-sets-verdict.md) |
| Доказательство | Предметная находка не сохраняется без `evidence_group_id`, SHA-256 источника, страницы и polygon | [ADR-0002](docs/adr/0002-evidence-group-is-the-unit.md) |
| Решение | Автомат останавливается на `CANDIDATE`. `CONFIRMED_VIOLATION` пишет только инспектор. Отклонение требует причины. Каждое решение — запись аудита с автором | [ADR-0005](docs/adr/0005-status-domains-are-separate.md) |
| Протокол | Материализуется атомарно с версией. В РиН уходит через outbox. Подтверждение брокера — не ACK РиН | [ADR-0009](docs/adr/0009-atomic-protocol-materialization.md), [ADR-0010](docs/adr/0010-outbox-relay-to-broker.md) |

## Редакция и знак триггера

Шифр в основной надписи важнее имени файла. Имя не подменяет прочитанный штамп.

На большом листе штамп — правый нижний угол 190×70 мм видимой страницы, форма 1 ГОСТ Р 21.101, с учётом поворота `/Rotate`. Из него читаются шифр комплекта (включая обозначения через дефис, косую черту и точку вида `2451.П.ДР.ГИ.ТЧ`), графа «Лист» и буква стадии: П, Р или И. У одностраничного документа с пустой графой «Лист» и «Листов 1» номер листа равен 1; дробный номер `6,1` приводится к `6.1`. Ссылки на ГОСТ, СП, сертификаты, номера экспертизы и марки изделий шифром комплекта не становятся. Вложенная надпись и подпись «Утвердил» выше угла остаются на чертеже. Второе чтение шифра берёт тот же первый лист.

Размер на чертеже, записанный как 500×300, скалярное правило пропускает. Произведение сторон остаётся у правила, которое само его просит. Сбой одного правила оставляет остальные строки матрицы: у сбойного качество низкое, нарушения нет.

Если штамп шифра пуст, проектная и рабочая стадии с одним именем собираются в одну цепочку. Из ключа убираются «кор», «изм», «ред» и копия «(1)». `КР1.pdf` и `КР1-кор3.pdf` — один том, голова — больший номер. «Корректировка №4» на титуле — номер редакции и важнее номера в имени того же файла.

Один номер у двух разных файлов — `CLARIFICATION_REQUIRED`. «Последний загруженный» не выбирается. «Изм» и «кор» между собой не упорядочиваются. Акты исполнительной документации по имени не схлопываются. Явная связь predecessor остаётся сильнее имени. Единственная голова ПД без штампа сравнивается с основанием `SOLE_HEAD`. Явный «не утв.» эталоном не становится.

Компаратор вычитает измерения десятичной дробью: 0,9 и 0,8 дают −0,1. Текст триггера матрицы задаёт знак. «Уменьшение» и «понижение» не делают кандидатом рост. «Увеличение» и «превышение» не делают кандидатом падение. «Расхождение», «изменение» и «подмена» оставляют кандидата в любую сторону. Противоположный знак — отсутствие срабатывания триггера, не `NEGATIVE_VERIFIED`.

Помещения сравниваются по всем парам листов выше порога правила. Спор одного номера гасит только его. Латинские B и P в метке читаются как В и П.

Повтор учебного комплекта повторяет идентификатор находки. Решение инспектора пишется в последний процесс, где такой переход ещё допустим. Повторный разбор того же процесса сохраняет решение, пока ожидаемое и фактическое значения не изменились. Изменились — карточка снова кандидат.

## Слова на экране

| Слово | Смысл |
|---|---|
| `CANDIDATE` | Расхождение подготовлено. Подтверждает его только инспектор |
| `CLARIFICATION_REQUIRED` | Редакция не выбрана однозначно: несколько голов, один номер у разных файлов или смесь «изм» и «кор». Сравнения по этой цепочке нет |
| `ABSTAIN` | Значение не прочитано или вердикты по одному помещению спорят. Это отказ, не соответствие |
| `LOW_QUALITY` | Строка не извлечена или правило не посчиталось. Нарушения здесь нет |
| `SOLE_HEAD` | Единственная голова ПД без штампа сравнивается. Штамп не переписывается |
| `MISSING_EVIDENCE` | Документа стадии нет. Это не нарушение |

## Откуда взяты решения

Цифры чужих бенчмарков к Контуру не приставлены. Разбор —
[`PLAN_2026_09_28_29.md`](docs/PLAN_2026_09_28_29.md),
[`RESEARCH_OSINT_2026.md`](docs/RESEARCH_OSINT_2026.md) и
[срез репозиториев 18.10](docs/research/competitors/OSINT-2026-10-18.md).

| Наблюдение | Решение в Контуре |
|---|---|
| Подсчёт однотипных объектов на плане у моделей слабый (AECV-Bench, arXiv:2601.04819) | Такие правила остаются `extractor_missing` |
| OmniDocBench v1.6 в основном китайско-английский, лидерам нужен GPU | Кириллица читается локальным eslav PP-OCRv5 на CPU |
| PP-OCRv6 русский не распознаёт | В образе веса eslav PP-OCRv5 |
| Текст PDF может быть инъекцией | Статус пишет компаратор |
| На новых объектах модели легко ставят «соответствует» (arXiv:2607.29058) | Вердикт у инспектора, выборки режутся по `object_id` |
| Облачные OCR и VLM в зачётный прогон не входят (ответ организатора 23) | Веса лежат в образе |
| На чертеже рядом с шириной проёма стоит размер 500×300 | Скалярное правило его пропускает. Площадь читает правило, которое само просит произведение сторон |
| В штампе рядом лежат «Лист», «Листов», ГОСТ и вложенная надпись | Номер листа — графа «Лист» в углу надписи. Стандарт и сертификат шифром комплекта не становятся |

## Запуск за пять минут

Нужны Docker Compose v2 и свободные порты на `127.0.0.1`: `3000`, `8000`,
`5432`, `6379`, `5672`, `15672`, `9000`, `9001`. GPU и GNU make не нужны.
Ядро по умолчанию ограничено 8 CPU и 8 ГБ. На машине меньше 8 CPU задайте
`KONTUR_CORE_CPUS`.

```text
docker compose -f docker-compose.yml -f docker-compose.demo.yml up -d --build
```

| Адрес | Что там |
|---|---|
| http://127.0.0.1:3000 | Экран инспектора |
| http://127.0.0.1:3000/api/v1/healthz | Проверка ядра через шлюз, 200 |
| http://127.0.0.1:8000/docs | Swagger ядра |
| http://127.0.0.1:8000/openapi.json | Контракт API |

Учебный токен: `inspector-1@OBJ-DEMO-COLD-START/INSPECTOR`. Это не учётная
запись промышленного контура. Защищённые маршруты без токена отвечают 401.
Перед сборкой задайте `KONTUR_GIT_SHA` — 40 символов `git rev-parse HEAD`:
каталог `.git` в образ не копируется. Сервер жюри открывает экран наружу
переменной `KONTUR_BIND=0.0.0.0`, базы и брокер остаются на `127.0.0.1`.

Без сети: `scripts/offline_bundle.sh` сохраняет собранные образы в tar с
`SHA256SUMS`, на целевой машине — `docker load` и тот же `up` с
`docker-compose.offline.yml` и `--no-build`. Записи прогонов 27.09 и 28.09 —
[`DEMO_COLD_START.md`](docs/DEMO_COLD_START.md). Сеть хоста в них не
отключалась. Это не чистая Linux-машина.

Без Docker:

```text
pip install -e "backend[dev]"
pytest backend/tests -q
python scripts/check_claims.py
```

Полный протокол со списком сервисов, проверкой после старта и неполадками —
[`submission/04-prototype`](submission/04-prototype/README.md).

## Сценарий на учебном комплекте

Кнопка «Учебный комплект» (или `python scripts/load_demo_kit.py`) кладёт
синтетические ПД, РД и ИД. Документы организатора на стенд не класть.

| Шаг | Действие | Что видно |
|---|---|---|
| 1 | Загрузить комплект | 132 находки. PZ-001, KR-055, AR-041 — `CLARIFICATION_REQUIRED`: в комплекте две редакции ПД |
| 2 | «Назначить эталоном» `f-pd` | Три `CANDIDATE`: площадь 1250,5 → 1100 м², класс бетона B30 → B25, проём 1,2 → 0,8 м |
| 3 | Открыть карточку | Правило, ожидание и факт, файл, страница, SHA-256, polygon на листе ПД и РД |
| 4 | Подтвердить PZ-001 и KR-055, отклонить AR-041 | `CONFIRMED_VIOLATION` ×2, `NEGATIVE_VERIFIED` ×1. Отклонение без `reason_code` — 409 |
| 5 | Завершить и финализировать | `PROTOCOL_FINALIZED`, `violation_count` 2. Незакрытый `CANDIDATE` финализацию блокирует |
| 6 | Скачать протокол | JSON, DOCX, XML, PDF из одного JSON. В карточке рядом с SHA-256 стоят статус утверждения фрагмента и причина решения |
| 7 | «Передать в РиН (mock)» | `PENDING_SYNC`. ACK РиН нет |

Шаги 1–7 пройдены через API на коде `main` 28.09, ответы записаны в
[протоколе запуска](submission/04-prototype/README.md#7-тот-же-сценарий-через-api).
Ответ участника на шагах 1 и 2 —
[`unattended`](submission/05-additional/examples/unattended/submission.json) и
[`after_etalon_select`](submission/05-additional/examples/after_etalon_select/submission.json).
От кандидата до записанного решения три действия: открыть, выбрать исход,
сохранить (ответ организатора 28). Сессии Gate K считаются отдельно.

## Состав

| В стенде | Дальше по ТЗ |
|---|---|
| Стенд одной командой, `healthz`, офлайн из tar | Прогон с физически отключённой сетью на чистом Linux |
| Голова редакции по шифру, цепочка имени при пустом шифре, `SOLE_HEAD`, выбор эталона инспектором | Frozen validation и пороги раздела 14 |
| Сравнение помещений по всем парам листов | FPR на публичном gold: отрицательных строк нет, доля не считается |
| 59 правил с экстрактором из 132 | 68 правил без экстрактора, 4 без источника, 1 advisory |
| Карточка: файл, страница, SHA-256, polygon | Пять сессий инспекторов (Gate K) |
| Решение инспектора, пачка только из `CANDIDATE`, аудит. `split()` есть в коде и автомат его не вызывает | Маршрута HTTP для `split()` нет ([#83](https://github.com/KonkovDV/Kontur/issues/83)) |
| Протокол JSON, DOCX, XML, PDF из одного JSON | Живой РиН, УКЭП, OIDC |
| DOCX: абзацы и таблицы. XML: текстовые узлы. Zip раскрывается до сверки | Схема пояснительной записки, вложения PDF, 7z, rar, DWG |
| Пакетный прогон и счёт с n и интервалом | OCR на уровне порога: статус `MEASURED` |
| Лимиты 50 МБ на файл и 200 МБ на пакет, `RATE_LIMITED` | VLM в сверке нет, изоляция VLM — [#84](https://github.com/KonkovDV/Kontur/issues/84) |

Покрытие по типам экстрактора и разделам матрицы —
[реестр доказательств](submission/05-additional/README.md#2-покрытие-матрицы).

## Метрики

Приёмка раздела 14 смотрит нижнюю границу 95% интервала на frozen validation.
Пороги: Character Accuracy 0,95, Exact Match 0,90, связка 0,95, локализация
0,95 при IoU 0,50, Precision 0,90, Recall 0,80, F1 0,85, FPR 0,10.
Frozen validation в репозитории нет. Ниже — то, что уже посчитано.

| Замер | Выборка | Значение |
|---|---|---|
| Матрица, режим location | публичный gold, n=6 | 0 из 6, Wilson [0; 0,39] |
| Свободный поиск | публичный gold, n=4 | 0 из 4, Wilson [0; 0,49] |
| OCR eslav PP-OCRv5 | SILVER, n=5935 | нижняя граница доли строк с CA ≥ 0,95 равна 0,663 |
| k6, `GET /status` | GitHub Actions, n=6000 | p95 18,26 мс |

Прогон gold и OCR сделан 28.09. Правки штампа, фильтра размеров и изоляции правил в этот счёт не входили.

На публичном gold числовой проход IOS4 остановился с текстом «якорь или число не найдены». Отрицательных строк в этом счёте нет, поэтому FPR там не считается. Ход пяти прогонов — [`GOLD_DIAGNOSIS.md`](docs/GOLD_DIAGNOSIS.md). Методика — [досье, разделы 8 и 9](submission/02-documentation/README.md#8-методология-измерений).

## Как оценивают и где это проверить

Рейтинг ставит организатор: 30 баллов экспертизы и 10 питча (ответ 13). При равенстве смотрят F1 и Recall. Таблица ниже — техническая доска ЛЦТ, максимум 20.

| Критерий доски | Баллы | Где проверить |
|---|---|---|
| Сквозной процесс ПД–РД–ИД | 4 | [Сценарий](#сценарий-на-учебном-комплекте), [протокол запуска](submission/04-prototype/README.md) |
| OCR и ключевые поля | 2 | [`OCR_BAKEOFF.md`](docs/OCR_BAKEOFF.md), реестр, раздел 4 |
| Связка документов | 1 | [ADR-0017](docs/adr/0017-sole-head-without-stamp.md), [`GOLD_DIAGNOSIS.md`](docs/GOLD_DIAGNOSIS.md) |
| Несоответствия | 3 | [Покрытие](submission/05-additional/README.md#2-покрытие-матрицы), [`data/matrix/`](data/matrix/) |
| Локализация и FPR | 2 | [`METRICS.md`](docs/METRICS.md), `python -m kontur.cli.score` |
| Доказательность | 3 | [ADR-0002](docs/adr/0002-evidence-group-is-the-unit.md), [пример JSON](submission/05-additional/examples/README.md) |
| Техническая готовность | 3 | [Запуск](#запуск-за-пять-минут), [`DEMO_COLD_START.md`](docs/DEMO_COLD_START.md), [CI](#качество-кода) |
| Сценарий инспектора | 2 | [Сценарий](#сценарий-на-учебном-комплекте). Сессий Gate K нет |

Пять полей формы на площадке i.moscow — репозиторий, документация,
презентация, прототип, дополнительные материалы — собраны в
[`submission/`](submission/README.md). Комплект технической проверки по
ответу О-2 (Dockerfile, compose, lock, веса, healthcheck, OpenAPI, пример JSON) —
[досье, раздел 3.1](submission/02-documentation/README.md#31-комплект-технической-проверки-ответ-о-2).

## Требования ТЗ и где их след

Построчная карта «пункт → артефакт → тест» и её статусы —
[`TZ_TRACEABILITY.md`](docs/TZ_TRACEABILITY.md). Статусы здесь не повышаются.

| Требование | Где в коде | Статус в карте |
|---|---|---|
| Матрица 132 параметров как данные (п. 8, прил. 1) | [`data/matrix/`](data/matrix/), [`rule.schema.json`](contracts/schemas/rule.schema.json) | in_progress: 59 executable |
| Разбор, OCR, координаты, выбор редакции (п. 9.1) | `application/process_pipeline.py`, `revision_resolver.py`, `infrastructure/pdfium_tokens.py` | in_progress: OCR `MEASURED` |
| Ошибки загрузки: формат, 50 МБ, 200 МБ, таймаут (п. 9.1) | `application/intake.py`, [`gateway/`](gateway/) | in_progress |
| Каскад остановок, карточка, протокол (п. 9.2) | `application/pipeline.py`, `evaluate.py`, `protocol.py` | in_progress |
| Решение, финализация, отмена (п. 9.3) | `application/review.py`, `domain/state_machines.py` | in_progress: `split()` нет |
| Разметка, карантин, разбиение по объекту (п. 9.4) | `evaluation/dataset_package.py`, `release_gate.py` | in_progress |
| Очередь в РиН (п. 9.6) | `infrastructure/outbox.py`, `sync_relay.py` | in_progress: sandbox РиН и УКЭП нет |
| Доступ и аудит (п. 12) | `presentation/auth.py`, `rbac.py` | in_progress: OIDC и TLS нет |
| Пороги и формат ответа (п. 14, прил. 2) | `evaluation/metrics.py`, `submission.py`, `cli/score.py` | in_progress: пороги не измерены |

Код ядра — [`backend/src/kontur/`](backend/src/kontur/).

## Границы, которые не нарушаются

- `CONFIRMED_VIOLATION` присваивает **только инспектор**. Система формирует
  `CANDIDATE` и карточку доказательства.
- LLM и VLM **никогда** не пишут итоговый статус находки.
- Предметная находка (`CANDIDATE`, `CONFIRMED_VIOLATION`, `NEGATIVE_VERIFIED`,
  внутренний `AUTO_NO_DIFFERENCE`) не сохраняется без `evidence_group_id`,
  источников с SHA-256 и координат. `MISSING_EVIDENCE` и `NOT_APPLICABLE`
  могут существовать без фрагментов.
- Отсутствие стадии, документа или доказательства — **не** нарушение:
  `MISSING_EVIDENCE`, `NOT_APPLICABLE`, `NOT_COMPARABLE`, `CLARIFICATION_REQUIRED`.
- Параметр не найден в загруженном документе — `LOW_QUALITY` или `ABSTAIN`,
  не нарушение и не «соответствует».
- Комплектность (`PD_UPLOADED`, `RD_PARTIAL`, `ID_MISSING`), процесс
  (`COMPLETED`, `FINALIZED`) и протокол (`VERIFICATION_COMPLETED`,
  `PROTOCOL_FINALIZED`) — разные проекции.
- Явная пометка «не утв.» эталоном не становится. `KONTUR_ETALON_POLICY=strict`
  возвращает поведение [ADR-0015](docs/adr/0015-missing-approval-is-clarification.md):
  ПД без сведений об утверждении — `CLARIFICATION_REQUIRED`.
- `AUTO_NO_DIFFERENCE` не уходит в протокол ТЗ и в РиН. На JSON участника
  совпадение уходит как `NO_VIOLATION`.
- Скрытый тест — карантин. `РАЗМЕЧЕННЫЙ_TEST__213.zip` и
  `РАЗМЕЧЕННЫЙ_TEST_HIDDEN_ОРГАНИЗАТОР_213` не открываются и для порогов не
  используются ([`DATASET_PACKAGE.md`](docs/DATASET_PACKAGE.md)).
- Официальный прогон локальный. Документы не уходят во внешние LLM, OCR и VLM.

Какой тест держит каждую границу —
[досье, раздел 7](submission/02-documentation/README.md#7-как-инварианты-держатся-кодом).

## Качество кода

В дереве сейчас 120 модулей ядра и 150 файлов `test_*.py`.

| Проверка | Где |
|---|---|
| `ruff check`, `mypy --strict`, `pytest` | job `backend` |
| Согласованность OpenAPI и JSON-схем | job `contracts`, [`check_contracts.py`](scripts/check_contracts.py) |
| Формулировки без заявлений о готовности | job `claims`, [`check_claims.py`](scripts/check_claims.py) |
| Схема БД, конкурентная финализация протокола, inbox на живой Postgres | job `db` |
| Типы TypeScript и тесты экрана | job `frontend` |
| Сборка и runtime-контракт образов, smoke core и gateway | jobs `container-*` |
| Relay и жизненный цикл синхронизации | `relay-container`, `sync-lifecycle-db` |

В `main` изменения попадают через pull request. Проверки из таблицы выше обязательны.

## Пакетный прогон и счёт

```text
docker compose --profile runner run --rm package-runner
```

Команда читает `input/` рядом с compose и пишет в `out/` (запись для uid 10001).
Без Docker:

```text
python -m kontur.cli.run_package --input <каталог> --out <каталог> [--pages-text]
python -m kontur.cli.score --submissions <каталог>
```

`run_package` читает `files_index.jsonl` или папки `<объект>/{ПД|РД|ИД}` и пишет
`submission_*.json`, `protocol_*.json`, `documents_*.json`, `fields_*.jsonl`,
`run_manifest.json`, с `--pages-text` — ещё слова страниц с bbox и движком.
Инспектор в пакете находки не подтверждает, `violation_count` остаётся 0.
Скрытый тест пропускается. Раскладка входа —
[`examples/demo_package/README.md`](examples/demo_package/README.md).

`score` проверяет ответ по `submission.schema.json`: невалидный ответ числа не
получает. Совпадение — `object_id`, код и `location`. Матрица и свободный поиск
считаются отдельно, с n и интервалом Wilson. Порог ТЗ команда не объявляет
взятым.

## Стек

| Часть | Технология |
|---|---|
| Ядро | Python 3.12 в образе (≥3.11 для разработки), FastAPI, pdfium |
| OCR | eslav PP-OCRv5 (ONNX, локальные веса), Tesseract |
| Шлюз | Node.js 22: лимиты размера и частоты, статика |
| Экран инспектора | React 18, TypeScript, Vite |
| Данные | PostgreSQL 16, Redis 7 (кеш паспортов), RabbitMQ 3.13, MinIO |
| Интеграция | Outbox с подтверждением брокера и transactional inbox. Брокер не есть РиН |

Базовые образы закреплены digest. Ядро и шлюз работают от пользователя 10001,
файловая система только на чтение, `cap_drop: ALL`, healthcheck.

## Карта репозитория

```text
contracts/      OpenAPI 3.1 (+ даунконверт 3.0) и JSON-схемы обмена — источник истины
backend/        Python: домен, сверка, инфраструктура, API, CLI пакетного прогона
gateway/        Node.js: вход, лимиты, раздача экрана
web/            React: экран инспектора с карточкой доказательства
data/matrix/    132 правила матрицы как данные, покрытие, триаж семейств
data/dataset/   Реестр поставки, публичный gold, карантин
vendor/ocr/     Локальные веса OCR
submission/     Пять полей формы сдачи
docs/           ADR, архитектура, метрики, трассируемость ТЗ, Red Team
```

## Документы

Для жюри:

| Тема | Файл |
|---|---|
| Пять полей формы сдачи | [`submission/README.md`](submission/README.md) |
| Досье: постановка, решения, методология | [`submission/02-documentation`](submission/02-documentation/README.md) |
| Архитектура и три контура | [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) |
| Метрики, n и интервал | [`docs/METRICS.md`](docs/METRICS.md) |
| Известные пробелы | [`docs/KNOWN_GAPS.md`](docs/KNOWN_GAPS.md) |
| Трассируемость ТЗ → артефакт → тест | [`docs/TZ_TRACEABILITY.md`](docs/TZ_TRACEABILITY.md) |
| Двенадцать модулей | [`docs/MODULES.md`](docs/MODULES.md) |
| Три контура готовности | [`docs/TZ_SCORECARD.md`](docs/TZ_SCORECARD.md) |
| Ответы организатора | [`docs/ORGANIZER_ANSWERS_2026_09_26.md`](docs/ORGANIZER_ANSWERS_2026_09_26.md) |
| Архитектурные решения | [`docs/adr/`](docs/adr/) |
| Разбор публичного gold | [`docs/GOLD_DIAGNOSIS.md`](docs/GOLD_DIAGNOSIS.md) |
| OCR bake-off | [`docs/OCR_BAKEOFF.md`](docs/OCR_BAKEOFF.md) |
| Холодный запуск | [`docs/DEMO_COLD_START.md`](docs/DEMO_COLD_START.md) |
| Состав переданного пакета данных | [`docs/DATASET_PACKAGE.md`](docs/DATASET_PACKAGE.md) |
| Публичный gold не frozen validation | [`docs/ORGANIZER_GOLD.md`](docs/ORGANIZER_GOLD.md) |
| Red Team и stop-ship | [`docs/RED_TEAM.md`](docs/RED_TEAM.md) |
| Производительность и нагрузка | [`docs/PERFORMANCE.md`](docs/PERFORMANCE.md) |
| Лицензии сторонних пакетов | [`docs/THIRD_PARTY_NOTICES.md`](docs/THIRD_PARTY_NOTICES.md) |

Для сопровождения:

| Тема | Файл |
|---|---|
| Оперативный план 28–29.09 | [`docs/PLAN_2026_09_28_29.md`](docs/PLAN_2026_09_28_29.md) |
| Пакет сдачи, машиночитаемый | [`docs/SUBMISSION_PACK.md`](docs/SUBMISSION_PACK.md) |
| Карантин датасета | [`docs/DATA_QUARANTINE.md`](docs/DATA_QUARANTINE.md) |
| Нормативный реестр | [`docs/NORMATIVE_REGISTRY.md`](docs/NORMATIVE_REGISTRY.md) |
| Вопросы организатору | [`docs/QUESTIONS_TO_ORGANIZER.md`](docs/QUESTIONS_TO_ORGANIZER.md) |
| OSINT Document AI, срез 28.09 | [`docs/RESEARCH_OSINT_2026.md`](docs/RESEARCH_OSINT_2026.md) |
| Публичные репозитории задачи №10, 18.10 | [`docs/research/competitors/OSINT-2026-10-18.md`](docs/research/competitors/OSINT-2026-10-18.md) |
| Донор архитектуры AeroBIM и переносы 08–15.10 | [`docs/SOTA_AEROBIM_ANALYSIS.md`](docs/SOTA_AEROBIM_ANALYSIS.md) |
| Карта всех документов | [`docs/README.md`](docs/README.md) |

## Права на код

Код Контура передаётся заказчику задачи. Открытой лицензии на него в
репозитории нет. Модели и пакеты третьих сторон остаются под лицензиями своих
авторов — [`docs/THIRD_PARTY_NOTICES.md`](docs/THIRD_PARTY_NOTICES.md).
