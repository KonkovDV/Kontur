# Документация

**Ссылка для формы:** https://github.com/KonkovDV/Kontur/tree/main/submission/02-documentation

Техническое досье Контура для жюри задачи №10. Срез 28.09.2026.
Гейты приёмки I/J/K/L открыты. Покрытие матрицы — 55 executable,
72 extractor_missing, 1 advisory, 4 source_missing из 132. Это не заявление,
что все параметры исполняются.

## Содержание

1. [Постановка](#1-постановка)
2. [Как читать](#2-как-читать)
3. [Требования и где их доказательство](#3-требования-и-где-их-доказательство)
4. [Архитектурные решения](#4-архитектурные-решения)
5. [Модель статусов](#5-модель-статусов)
6. [Контракты](#6-контракты)
7. [Как инварианты держатся кодом](#7-как-инварианты-держатся-кодом)
8. [Методология измерений](#8-методология-измерений)
9. [Угрозы достоверности](#9-угрозы-достоверности)
10. [Воспроизводимость](#10-воспроизводимость)
11. [Словарь](#11-словарь)

## 1. Постановка

**Объект.** Комплект одного строительного объекта: тома проектной (ПД),
рабочей (РД) и исполнительной (ИД) документации в PDF и DOCX. XML принимается
по контракту (ответ организатора 10).

**Предмет.** Расхождение значения контролируемого параметра между стадиями.
Параметров 132, они заданы матрицей организатора. Сверяются документы между
собой, а не проект с нормой ([ADR-0006](../../docs/adr/0006-compare-documents-not-norms.md)).

**Единица результата.** Точка `object_id + parameter_code + location`
(ответ организатора 14). Для каждой точки ответ участника несёт одну из
четырёх меток: `VIOLATION_PRESENT`, `NO_VIOLATION`, `MISSING_DOCUMENT`,
`COMPARISON_IMPOSSIBLE` ([`submission.schema.json`](../../contracts/schemas/submission.schema.json)).

**Эталон.** Последняя применимая утверждённая редакция ПД в цепочке
predecessor/successor (ответы 11 и 12). РД и ИД утверждения не требуют:
берётся последняя редакция шифра.

**Кто решает.** Автомат доходит до `CANDIDATE` и карточки доказательства.
`CONFIRMED_VIOLATION` и `NEGATIVE_VERIFIED` пишет инспектор
([ADR-0001](../../docs/adr/0001-llm-never-sets-verdict.md)). Модель, если
появится, может предложить кандидата и черновик объяснения, но не статус.

**Что вне задачи.** Проверка проекта по СНиП и СанПиН. Автономный надзор
без человека. Промышленные OIDC, TLS, УКЭП и живой РиН (ответ организатора 18:
на хакатоне это не блокер).

## 2. Как читать

| Время | Путь |
|---|---|
| 5 минут | [`README.md`](../../README.md) → [`ARCHITECTURE.md`](../../docs/ARCHITECTURE.md) → [`METRICS.md`](../../docs/METRICS.md) → [`KNOWN_GAPS.md`](../../docs/KNOWN_GAPS.md) |
| 30 минут | Разделы 3–9 этого файла, затем [`TZ_TRACEABILITY.md`](../../docs/TZ_TRACEABILITY.md) и [`GOLD_DIAGNOSIS.md`](../../docs/GOLD_DIAGNOSIS.md) |
| Аудит | Раздел 7: инвариант → модуль → тест. Затем [`RED_TEAM.md`](../../docs/RED_TEAM.md) и [`RED_TEAM_TRIAGE.md`](../../docs/RED_TEAM_TRIAGE.md) |
| Запуск | [`04-prototype`](../04-prototype/README.md) |
| Доказательства и примеры | [`05-additional`](../05-additional/README.md) |

## 3. Требования и где их доказательство

### 3.1 Комплект технической проверки (ответ О-2)

| Требование | Где в репозитории |
|---|---|
| Репозиторий | https://github.com/KonkovDV/Kontur |
| Dockerfile | [`backend/Dockerfile`](../../backend/Dockerfile), [`backend/Dockerfile.relay`](../../backend/Dockerfile.relay), [`gateway/Dockerfile`](../../gateway/Dockerfile) |
| Compose | [`docker-compose.yml`](../../docker-compose.yml), [`docker-compose.demo.yml`](../../docker-compose.demo.yml), [`docker-compose.offline.yml`](../../docker-compose.offline.yml) |
| Lock | [`backend/requirements.lock`](../../backend/requirements.lock), [`web/package-lock.json`](../../web/package-lock.json), [`gateway/package-lock.json`](../../gateway/package-lock.json) |
| Локальные веса | [`vendor/ocr/`](../../vendor/ocr/), хеши — [`ocr_weights.lock.json`](../../backend/src/kontur/infrastructure/ocr_weights.lock.json) |
| Команда запуска | [`README.md`](../../README.md) |
| Healthcheck | core и gateway в [`docker-compose.yml`](../../docker-compose.yml) |
| OpenAPI | [`openapi.yaml`](../../contracts/openapi.yaml) (3.1), [`openapi-3.0.yaml`](../../contracts/openapi-3.0.yaml) (даунконверт) |
| Пример JSON | [`05-additional/examples/`](../05-additional/examples/README.md) |

Публичная ссылка на стенд решением не оценивается. Официальный прогон
локальный, внешние LLM, OCR и VLM в зачёт не идут (ответы О-2 и 23).

### 3.2 Разделы ТЗ

Построчная карта «пункт → артефакт → тест» и её статусы — только в
[`TZ_TRACEABILITY.md`](../../docs/TZ_TRACEABILITY.md). Здесь статусы не повышаются.

| Блок ТЗ | Пункты в карте |
|---|---|
| Контракт API и состав стенда | 1.3–1.5 |
| Матрица и разделы документов | 3–8, приложение 1 |
| Разбор, извлечение, каскад остановок, карточка | 9.1–9.2 |
| Решение инспектора, финализация, юзабилити | 9.3 |
| Разметка, карантин скрытого теста, разбиение | 9.4 |
| Подозрение вне 132 правил | 9.5 |
| Очередь в РиН | 9.6 |
| Хранение, доступ, аудит | 10, 12 |
| Производительность | 11 |
| Пороги приёмки, формат ответа | 14, приложение 2 |

### 3.3 Ответы организатора, которые меняют реализацию

Полная таблица — [`ORGANIZER_ANSWERS_2026_09_26.md`](../../docs/ORGANIZER_ANSWERS_2026_09_26.md).

| Ответ | Что следует для кода |
|---|---|
| 9 | Файл больше 50 МБ и пакет больше 200 МБ — явный отказ, не тихий пропуск |
| 10 | Обязательны PDF и DOCX. XML принимается. DWG не требуется |
| 11, 12 | Эталон — утверждённая ПД в цепочке. Неоднозначность — `CLARIFICATION_REQUIRED` |
| 14 | Совпадение считается по точке с `location` |
| 18 | Раздел 14 — пороги будущей системы. Промышленные SLA, УКЭП и живой РиН не блокируют MVP |
| 23 | Зачётный прогон локальный. Лицензия модели должна разрешать использование |
| 28 | Не больше трёх действий от кандидата до записанного решения |

## 4. Архитектурные решения

Полные тексты — [`docs/adr/`](../../docs/adr/).

**Вердикт и доказательство**

| ADR | Решение |
|---|---|
| [0001](../../docs/adr/0001-llm-never-sets-verdict.md) | Модель не пишет вердикт и `finding_status` |
| [0002](../../docs/adr/0002-evidence-group-is-the-unit.md) | Единица результата — `evidence_group`: SHA-256, страница, polygon |
| [0006](../../docs/adr/0006-compare-documents-not-norms.md) | Сверка ПД↔РД↔ИД, не проект против нормы |

**Редакция и эталон.** Решение менялось, история сохранена.

| ADR | Решение | Статус |
|---|---|---|
| [0003](../../docs/adr/0003-revision-resolver-before-comparison.md) | Редакция выбирается до сравнения | принято |
| [0007](../../docs/adr/0007-approval-requires-explicit-evidence.md) | Утверждение требует явного доказательства | принято |
| [0013](../../docs/adr/0013-approval-sources-pending-written-answer.md) | Новые источники утверждения ждут письменного ответа | заменён 0015 |
| [0014](../../docs/adr/0014-package-default-etalon.md) | ПД комплекта — эталон без явного отказа | пункт 1 заменён 0015 |
| [0015](../../docs/adr/0015-missing-approval-is-clarification.md) | Нет сведений об утверждении — не эталон | режим `KONTUR_ETALON_POLICY=strict` |
| [0017](../../docs/adr/0017-sole-head-without-stamp.md) | Единственная голова ПД без штампа сравнивается с плашкой | умолчание с 27.09 |

**Данные и статусы**

| ADR | Решение |
|---|---|
| [0004](../../docs/adr/0004-rules-are-data.md) | 132 параметра — данные, покрытие публикуется разбивкой |
| [0005](../../docs/adr/0005-status-domains-are-separate.md) | Шесть словарей статусов, не одна простыня |
| [0016](../../docs/adr/0016-completeness-needs-a-register.md) | Полнота комплекта считается по реестру ожидаемого состава |

**Доступ и интеграция**

| ADR | Решение | Статус |
|---|---|---|
| [0008](../../docs/adr/0008-object-scope-is-mandatory.md) | На HTTP обязателен `object_id` | принято |
| [0009](../../docs/adr/0009-atomic-protocol-materialization.md) | Протокол материализуется атомарно с версией | принято |
| [0010](../../docs/adr/0010-outbox-relay-to-broker.md) | Outbox доставляет брокеру, не в РиН | принято |
| [0011](../../docs/adr/0011-sync-lifecycle-and-manual-retry.md) | Жизненный цикл брокера не есть доставка в РиН | предложено |
| [0012](../../docs/adr/0012-transactional-inbox.md) | Inbox подтверждает сообщение после commit | принято |

## 5. Модель статусов

По [ADR-0005](../../docs/adr/0005-status-domains-are-separate.md): пять хранимых
машин и одна проекция. Их смешение — главный источник ложного нарушения
вида «нет ИД — значит нарушение».

| Словарь | Значения | Замечание |
|---|---|---|
| Комплектность | `UPLOADED`, `PARTIAL`, `MISSING`; на проводе `PD_/RD_/ID_` | Нет стадии — не нарушение |
| Процесс | `PENDING → PARSING → READY → VERIFYING → COMPLETED → FINALIZED` | Из `FINALIZED` выход только через `unfinalize` с причиной |
| Протокол | `READY`, `VERIFYING`, `VERIFICATION_COMPLETED`, `PROTOCOL_FINALIZED` | Проекция процесса, не вторая машина |
| Находка | `CANDIDATE → CONFIRMED_VIOLATION`, `NEGATIVE_VERIFIED`, `CLARIFICATION_REQUIRED`; отдельно `SUSPICION` | Внутренний `AUTO_NO_DIFFERENCE` в протокол ТЗ не уходит |
| Качество данных | `MISSING_EVIDENCE`, `NOT_APPLICABLE`, `NOT_COMPARABLE`, `LOW_QUALITY`, `ABSTAIN` | Не нарушение и не «соответствует» |
| Синхронизация | `NOT_REQUESTED`, `PENDING_SYNC`, `SYNCING`, `SYNCED`, `RETRY_WAIT`, `FAILED_TERMINAL` | `SYNCED` зарезервирован за ACK РиН, его нет |

В число нарушений протокола входит ровно один статус — `CONFIRMED_VIOLATION`.

## 6. Контракты

Источник истины — [`contracts/`](../../contracts/). Правка идёт в порядке
контракт → схема → код → тест. Согласованность проверяет
[`check_contracts.py`](../../scripts/check_contracts.py) в job `contracts`.

| Файл | Что фиксирует |
|---|---|
| [`openapi.yaml`](../../contracts/openapi.yaml) | Маршруты, роли `x-required-roles`, object scope |
| [`rule.schema.json`](../../contracts/schemas/rule.schema.json) | Правило матрицы: источники, экстрактор, оператор, допуск, отказы |
| [`finding.schema.json`](../../contracts/schemas/finding.schema.json) | Находка и её статус |
| [`evidence_group.schema.json`](../../contracts/schemas/evidence_group.schema.json) | Группа доказательств и фрагменты |
| [`evidence_card.schema.json`](../../contracts/schemas/evidence_card.schema.json) | Карточка для экрана инспектора |
| [`document_passport.schema.json`](../../contracts/schemas/document_passport.schema.json) | Паспорт тома: шифр, редакция, штамп, слой |
| [`protocol.schema.json`](../../contracts/schemas/protocol.schema.json) | Протокол по образцу приложения 2 |
| [`protocol-export.xsd`](../../contracts/schemas/protocol-export.xsd) | XML-выгрузка протокола |
| [`submission.schema.json`](../../contracts/schemas/submission.schema.json) | Ответ участника соревнования |
| [`submission_pack.schema.json`](../../contracts/schemas/submission_pack.schema.json) | Машиночитаемый пакет провенанса |

## 7. Как инварианты держатся кодом

Инвариант проверяется тестом, а не только текстом.

| Инвариант | Тест |
|---|---|
| Автомат не пишет `CONFIRMED_VIOLATION` и `NEGATIVE_VERIFIED` | `test_state_machines.py`: `test_machine_cannot_confirm_violation`, `test_machine_cannot_write_negative_verified` |
| Нет доказательства — не нарушение | `test_state_machines.py`: `test_missing_evidence_never_becomes_violation` |
| Нарушение без доказательства не попадает в ответ | `test_submission.py`: `test_violation_without_evidence_never_reaches_the_answer` |
| Чужое доказательство к находке не приклеивается | `test_submission.py`: `test_evidence_of_another_rule_cannot_be_attached` |
| Пачкой подтверждаются только `CANDIDATE` | `test_review.py`: `test_mass_confirm_only_candidates_and_refuses_the_whole_batch` |
| `split()` не выдаётся за атомарное действие | `test_review.py`: `test_split_is_unimplemented_until_each_part_has_evidence` |
| Финализация только человеком | `test_review.py`: `test_finalize_process_requires_human_and_audit` |
| Явный «не утв.» не перекрывается выбором | `test_revision_resolver.py`: `test_inspector_overlay_does_not_override_not_approved` |
| `SOLE_HEAD` не переписывает штамп | `test_sole_head.py` |
| Скрытый тест в карантине | `test_dataset_package.py`: `test_hidden_test_stays_quarantined`; `test_quarantine.py` |
| Невалидный ответ не получает счёта | `test_score_cli.py`: `test_invalid_submission_does_not_receive_a_score` |
| Ноль отрицательных строк не печатается как FPR 0 | `test_score_cli.py`: `test_zero_negatives_are_not_printed_as_zero_fpr` |
| Пример JSON проходит схемы | `test_submission_examples.py` |
| Формулировки без заявлений о готовности | [`check_claims.py`](../../scripts/check_claims.py), job `claims` |

Тесты лежат в [`backend/tests/`](../../backend/tests/). CI зелёный, только если
job `backend` имеет `conclusion=success`, `runner_id` не 0 и непустые шаги.

## 8. Методология измерений

**Пороги.** Раздел 14 ТЗ 1.1 — минимумы приёмки: Character Accuracy не ниже
0,95, Exact Match полей не ниже 0,90, связка документов не ниже 0,95,
локализация не ниже 0,95 при IoU не ниже 0,50, Precision не ниже 0,90,
Recall не ниже 0,80, F1 не ниже 0,85, FPR не выше 0,10. Гармоника P=0,90 и
R=0,80 ≈ 0,847: такая пара порог F1 не закрывает.

**Правило решения.** Порог считается взятым только по нижней границе 95%
интервала на frozen validation. Для доли используется интервал Wilson.
Интервал Вальда при малом n не применяется. Даже 16 попаданий из 16 дают
нижнюю границу около 0,81, и только с такого n порог полноты вообще
достижим; 6 из 6 дают около 0,61.

**Разбиение.** Train и validation разделяются по `object_id`, не по страницам.
Скрытый тест в выбор порогов, prompt и regex не входит.

**Единица счёта.** По умолчанию `object_id + parameter_code + location`.
Строка с `score_eligible=false` в FPR и в попадание не входит. Позитив без
метки в разметке — отдельная строка `unlabeled_positive`, не ложное и не
истинное срабатывание. Локализация засчитывается по файлу и странице той же
строки разметки; IoU считается только там, где у разметки есть polygon.
Интервал F1 бутстрепом не выводится при числе кластеров меньше 10.

**Раздельные метрики.** Character Accuracy, CER и Exact Match полей не
смешиваются. Матрица и свободный поиск считаются отдельно.

Текущие числа и их статус — [`METRICS.md`](../../docs/METRICS.md). Все они
получены на публичной разметке разработки и порогом ТЗ не являются.

## 9. Угрозы достоверности

| Угроза | Как проявляется | Что с этим сделано |
|---|---|---|
| Малая выборка | Публичный gold: 6 позитивов матрицы и 4 свободного поиска на одном объекте | Числа публикуются с n и интервалом, порог не заявляется |
| Счёт in-sample | Та же разметка видна при разработке | Пороги комнат по этим строкам не подбирались; остановка записана как есть в [`GOLD_DIAGNOSIS.md`](../../docs/GOLD_DIAGNOSIS.md) |
| Нет отрицательных строк в счёте | Строки Новослободской `score_eligible=false` | FPR печатается как «не определён», не как 0 |
| Нет полигонов в разметке | Знаменатель IoU пуст | Локализация помечена «не определена» |
| OCR на SILVER | Пилот n=5935 по текстовому слою, без растрового GOLD | Статус `ocr_text` — `MEASURED`, не `AVAILABLE` |
| Синтетика учебного комплекта | Кандидаты PZ-001, KR-055, AR-041 заложены в комплект | Комплект показывает цепочку, а не точность |
| Холодный запуск | Windows Docker, сеть хоста не отключалась | Так и записано в [`DEMO_COLD_START.md`](../../docs/DEMO_COLD_START.md) |
| Состав скрытого теста неизвестен | Доля типов правил в матрице не равна доле нарушений в тесте | Прогноз на скрытый тест не публикуется |
| SHA в манифесте | `git_sha()` читает репозиторий в момент записи, а не импортированный код | Расхождение объяснено в разделах `GOLD_DIAGNOSIS.md` |

## 10. Воспроизводимость

Каждый результат несёт `matrix_version`, `dataset_version`, `model_version`,
`input_manifest_hash` и git SHA. `model_version` — имя доступного движка OCR,
иначе `none`; SHA весов без проверенного файла не пишется.

| Что закреплено | Чем |
|---|---|
| Зависимости Python | `backend/requirements.lock` с хешами |
| Web и gateway | `package-lock.json`, установка `npm ci` |
| Базовые образы | digest в `FROM` и в `docker-compose.yml` |
| Веса OCR | файлы в `vendor/ocr/`, хеши в `ocr_weights.lock.json`, сборка не скачивает |
| SHA образа | `KONTUR_GIT_SHA` при сборке |

| Что пересобрать | Команда |
|---|---|
| Пример JSON | `python scripts/export_submission_example.py` |
| Пакет провенанса | `python scripts/export_submission_pack.py` |
| Счёт публичного gold | `python -m kontur.cli.score --submissions <каталог>` |
| Офлайн-комплект образов | `scripts/offline_bundle.sh` |

## 11. Словарь

| Термин | Значение |
|---|---|
| ПД, РД, ИД | Проектная, рабочая и исполнительная документация |
| Шифр | Обозначение документа в основной надписи. Ключ цепочки редакций |
| Голова редакции | Файл шифра, у которого нет successor в пуле пригодных редакций |
| Эталон | Голова ПД, с которой сравниваются РД и ИД |
| `SOLE_HEAD` | Основание эталона: единственная голова ПД без штампа и без другой утверждённой редакции |
| `evidence_group` | Группа фрагментов одной находки: файл, SHA-256, страница, polygon |
| `CANDIDATE` | Расхождение, найденное автоматом. Ждёт решения инспектора |
| `SUSPICION` | Гипотеза вне 132 правил, свободный поиск |
| `extractor_missing` | Правило матрицы без рабочего экстрактора. Нарушения не выдаёт |
| Frozen validation | Замороженная размеченная выборка для приёмки. Пока отсутствует |
