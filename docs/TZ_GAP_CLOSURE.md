# TZ_GAP_CLOSURE — план закрытия незакрытых требований ТЗ (до 30.10.2026)

Срез: `main@5c768c9`, 15.10.2026. Источник: Red Team brief «топ-20» (Ваня) + `data/dataset/tz_scorecard.json` (generated_on 2026-10-15).
Это инженерный план, **не** процент выполнения ТЗ и **не** P/R/F1. Gate I/J/K/L = false.

## 0. Базовая линия (scorecard, факт)

| Счётчик | Значение |
|---|---|
| declared | 132 |
| executable | **59** (было 55 до #350) |
| extractor_missing | 68 |
| source_missing | 4 |
| advisory | 1 |
| Gate I / J / K / L | false / false / false / false |

Редакция ТЗ: новый PDF побайтно совпадает с прежним текстом — дельты требований нет.

## 0.1 Статус пунктов топ-20 на 15.10

| # | Пункт | Статус |
|---|---|---|
| 1 | EM 5 полей штампа с n + 95% CI | **частично**: per-field EM + Wilson CI в `evaluation/metrics.py` (#352), отчёт на SILVER, не GOLD; экстракторы полей — в работе |
| — | W1 ведомости КР/ИОС3/ИОС4 (`element_table`) | **сделано** (#350, 55→59 executable) |
| 2–7 | связка ≥0,95, конфликт ревизий, PPM-102, ODI-115, SPZU-034, bbox на Rotate | **частично**: #2 `score_document_linkage`; #3 ветки ревизий; #7 stamp crop+Rotate; #4–#6 остаются extractor_missing (graphic) |
| 8–16, 18–20 | W2/W3 | открыто, по порядку §2 |
| 17 | SBERT-якоря | **отложено** (SOTA-обзор: Defer до буфера после W1/W2) |
| HITL | zoom-to-bbox, J/K, чипы уверенности | сделано (#355/#356); пороги UI uncalibrated (#359) |
| — | Stamp crop без VLM | **сделано**: `stamp_crop_box` / `stamp_region_polygon`, crop_box в passport |

Правило: любое изменение `executable` — только с экстрактором, 5 ветками триажа и фикстурами; JURY_ONEPAGER обновляется тем же PR.

## 1. Ранжирование
Критерии: влияние на жюри и приёмку (доска 20 баллов: живой сценарий и evidence до ~12, метрики до ~7–8), трудоёмкость, риск сломать durable/hardening. Размеры: S ≤ 0,5 дня, M 1–2 дня, L 3+ дня.

### W1. exact_field и ключевые поля штампа (уже запланировано)
| # | Требование ТЗ (ссылка + цитата) | Статус и доказательство | Что сделать | Файлы | Тест / приёмка | Размер |
|---|---|---|---|---|---|---|
| 1 | §9.1 п.1, §14.3 «Ключевые поля»: «Exact Match для ключевых полей (шифр, стадия, редакция, номер листа/страницы, номер помещения или элемента) — не ниже 0,90» | Есть паспорт документа (`application/passport.py`, `metrics.py`), но поштучного EM по 5 полям в scorecard нет; acceptance `gold_ocr` = unmet | Экстракторы штампа для 5 полей с dual-read (векторный слой + OCR) и нормализацией: NFC, пробелы, знаки шифра не удалять. Если поле не найдено, LOW_QUALITY/ABSTAIN | `application/passport.py`, `application/normalize.py`, `infrastructure/pdfium_tokens.py`, `evaluation/metrics.py` | Фикстуры «найдено / нет / нечитаемо» на каждое поле; отчёт EM по полям с n и 95% CI на SILVER, явно помеченный как не GOLD | M |
| 2 | §14.3 «Связка документов»: «Доля evidence_group с точным выбором object_id, стадии, шифра и актуальной редакции ≥ 0,95» | **метрика есть**: `score_document_linkage` (Wilson, quota=30); порог ≥0,95 не заявляем без n | Подключить к scorecard при размеченной выборке | `evaluation/metrics.py`, `cli/score.py` | Unit-тест на синтетику: верная связка, чужая стадия, устаревшая редакция | S |
| 3 | §9.1 «Выбор актуальной редакции»: «При конфликте редакций… CLARIFICATION_REQUIRED… Устаревшая редакция не может использоваться как эталон» | **ветки покрыты тестами W1** (strict UNKNOWN, две головы, разрыв pred/succ) | — | `application/revision_resolver.py`, тесты | Каждая ветка даёт CLARIFICATION_REQUIRED и не даёт CANDIDATE | S |
| 4 | Прил.1 / §8, PPM-102 «Деление здания на пожарные отсеки» | exact_field, **остаётся extractor_missing** (graphic triage) | Не переводим в executable: непрерывность стены ≠ текст «отсек № N» | `application/extractors/` (семейство exact_field), `data/matrix/rules` | 5 веток (AUTO_NO_DIFFERENCE/CANDIDATE/MISSING_EVIDENCE/LOW_QUALITY/ABSTAIN) по правилу триажа | S–M |
| 5 | ODI-115 «Технические параметры и наличие инвалидных подъемников» | exact_field, **остаётся extractor_missing** (text_composite) | Честный missing до semantic/table extractor | то же | Фикстуры спецификаций; при отсутствии в тексте MISSING_EVIDENCE | M |
| 6 | SPZU-034 «Точки и координаты подключения внешних сетей» | exact_field, **остаётся extractor_missing** (graphic) | Координатная сетка; regex по тексту недостаточен | то же, `family_triage.json` | Решение по правилу 1–5 из EXTRACTOR_FAMILY_TRIAGE задокументировано | S (триаж) / M |
| 7 | §9.1 п.4: «Координаты приводятся к диапазону [0;1]… после учёта CropBox, MediaBox и Rotate» (для доказательств ключевых полей) | Есть в `pdfium_*`; **stamp crop + Rotate тест** | pdfium нормализует; `stamp_crop_*` в [0;1] | `tests/test_coordinates.py` | Rotate 90/180/270 + сдвинутый CropBox → bbox в [0;1], IoU ≥ 0,5 с эталоном | S |

Остальные exact_field (AR-043, PPM-106: дуга створки; POS-085, SPZU-035, SPZU-039: графика) остаются `extractor_missing`. Доказательство там геометрическое, а не текстовое (см. EXTRACTOR_FAMILY_TRIAGE).

### W2. Комплектность, протокол, инкремент
| # | Требование | Статус и доказательство | Что сделать | Файлы | Тест / приёмка | Размер |
|---|---|---|---|---|---|---|
| 8 | §9.1 «отдельный контроль комплектности»; Прил.1, presence: ZU-129, KR-063, AR-053, POD-092, ODI-120 и др. (11) | presence: executable 0, missing 11 | Presence-экстрактор с каталогом документов (§3–5 ТЗ). Начать с ZU-129 и KR-063, где есть явные заголовки разделов | `application/extractors/`, `data/matrix/sections.json` | Фикстуры «раздел есть / нет / есть, но нечитаем»; отсутствие → MISSING_EVIDENCE, не нарушение | M |
| 9 | §9.2 «Инкрементальное обновление… только по тем параметрам, для которых появились новые данные. Предыдущая версия протокола сохраняется»; §11 п.9 ≤ 1 мин | `evaluation/tz11.py`: `"incremental": False` → row 9 unmet; в `application/` логики нет | Diff реестра файлов → набор затронутых параметров → пересчёт только их; версия протокола +1, старая в истории | `application/process_pipeline.py`, `infrastructure/db/process_store.py` | Дозагрузка 1 файла ИД пересчитывает только зависимые коды; решения инспектора по остальным не сброшены; замер времени | L |
| 10 | §9.2 п.4 + Прил.2: раздельные таблицы (1) комплектность, (2) кандидаты, (3) подтверждённые, (4) NEGATIVE_VERIFIED, (5) гипотезы; разделы «Статус загрузки» и «Тип проверки» | `protocol_export.py` есть; соответствие Прил.2 не проверено тестом | Сверить секции с образцом Прил.2, добавить недостающие поля карточки (SHA-256 каждого источника, approval_status, reason) | `application/protocol_export.py` | Snapshot-тест JSON/PDF: все 5 таблиц и 2 раздела; генерация ≤ 30 с (§11 п.5) | M |
| 11 | Enum (9): KR-062 «Диаметр рабочей арматуры», IOS1-068 «Номиналы автоматов ВРУ/ГРЩ» и др. | enum: missing 9 (`enum_family_triage.json`) | Закрытые справочники (сортамент Ø, ряд номиналов). Начать с KR-062 и IOS1-068 | `application/extractors/`, справочники | 5 веток; вне справочника → LOW_QUALITY | M |
| 12 | §9.3 п.4: «Финализация разрешена только после обработки всех CANDIDATE…»; п.5 «после финализации дозагрузка и изменения статусов невозможны»; отмена → «VERIFICATION_COMPLETED» с причиной в аудите | Части есть (unfinalize, RBAC); сквозной red-team тест на инвариант не найден | E2E: finalize с открытым CANDIDATE → 409; upload после FINALIZED → 409; unfinalize без причины → 422; запись в аудит | `presentation/api.py`, тесты | 3 негативных теста зелёные | S |
| 13 | §9.6: в РиН «только подтверждённые инспектором записи… вместе с версиями протокола, Матрицы, модели и реестром входных файлов»; ретраи 1/5/15 мин | `rin_sandbox` = partial (LOCAL_ONLY без URL) | Проверить payload (только CONFIRMED_VIOLATION + версии + manifest) и расписание ретраев | `infrastructure/sync_relay.py` | Тест: SUSPICION/CANDIDATE в payload не попадают; 5xx → задержки 1/5/15 → PENDING_SYNC | S |

### W3. Number-семейство, NLP, эксплуатация
| # | Требование | Статус и доказательство | Что сделать | Файлы | Тест / приёмка | Размер |
|---|---|---|---|---|---|---|
| 14 | number: AR-042 «Высота путей эвакуации и проёмов», AR-047 «Габариты тамбуров» | number: missing 44 (`number_family_triage.json`: kept 40) | Отметки и размеры из векторного слоя разрезов с допуском | `application/extractors/`, `pdfium_vectors.py` | 5 веток + допуск ±; синтетика | M |
| 15 | number: IOS4-076 «Диаметры магистралей отопления», IOS4-077 «Параметры радиаторов» (gold-кандидаты, ROADMAP W3) | missing | Спецификации ОВ: таблицы, Ду/мощность | то же | Фикстуры спецификаций; сравнение ПД↔РД | M |
| 16 | KR-054 «Шаг и привязка координационных осей» | missing | Оси и размерные цепочки из векторов | то же, `drawing_scale.py` | Синтетический план осей; сдвиг 100 мм → CANDIDATE | M–L |
| 17 | §9.1 п.2: «семантических якорей… Sentence-BERT (all-MiniLM-L6-v2) или совместимые аналоги» | grep `all-MiniLM`/Sentence/embedding в `backend/src` → 0 | Офлайн-модель якорей только для поиска фрагмента-кандидата; не арбитр. Проверить лицензию и офлайн-compose | `application/` (anchor), `vendor/` | Тест: якорь находит раздел при перефразе; ML-анализ параметра ≤ 500 мс (§11 п.7) | M |
| 18 | §13 п.1: JSON-логи с полями timestamp, level, service, message, request_id, user_id | Отдельного модуля не нашёл (grep) | Единый JSON-formatter backend и gateway + request_id сквозной | `backend/src/kontur/…/logging`, `gateway/src/server.js` | Тест: лог-строка — валидный JSON со всеми 6 полями | S |
| 19 | §13 п.4–5: метрики (RPS, latency, 5xx, очередь RabbitMQ, сессии) + Prometheus/Grafana | scorecard `observability_otel` = unmet | `/metrics` (prometheus_client), опционально compose-профиль Prometheus+Grafana с 1 дашбордом | `presentation/api.py`, `docker-compose.yml` (профиль) | `curl /metrics` отдаёт счётчики; профиль не ломает offline/demo compose | M |
| 20 | §13 п.8: «Ежедневная проверка контрольных сумм (хешей) файлов в хранилище» | grep integrity/verify → нет | Job: пересчитать SHA-256 объектов из object store против реестра; расхождение → ERROR + аудит | `infrastructure/` (object store), `scripts/` | Тест: подмена байта блоба → алерт | S |

## 2. Порядок до 30.10
1. **16–20.10:** W1 #1–#3, #7. Это максимальный вес для жюри (EM ключевых полей + связка), затем #4–#6.
2. **21–25.10:** W2 #8, #10, #12, #13. #9 (L) только если W1 закрыт, иначе честно unmet в tz11.
3. **26–29.10:** W3: #18, #20 (S), #19, затем 1–2 number-правила (#14/#15). #16, #17 по остатку.
4. **30.10:** заморозка, пересборка scorecard (`scripts/export_agent_dumps.py`), JURY_ONEPAGER только с новыми фактическими числами.

## 3. Чего НЕ делать
- Не переводить правило в `executable` из-за «экстрактор семейства есть». Только 5 условий из EXTRACTOR_FAMILY_TRIAGE + фикстуры на все 5 веток.
- Не писать «% ТЗ», «132/132», «Gate I/J закрыт», «CA ≥ 0,95» без n, 95% CI и GOLD. SILVER ≠ GOLD.
- Не подбирать пороги на hidden test (§14.2 «подбор порога по hidden test запрещён»).
- Не выдавать машинный CONFIRMED_VIOLATION (§9.2: «присваивается исключительно инспектором»).
- Не прятать `extractor_missing` в UI и протоколе. MISSING_EVIDENCE ≠ нарушение.
- Не заявлять доступность 99,9% (как достигнутый SLA), 100 пользователей, RTO/RPO (§11 п.11–14): у нас измерение, а не production.
- Не трогать durable/hardening (wiring, object store, clamd/auth gates) в PR экстракторов. Один PR — одно семейство.
- Не делать мажорные Dependabot-апгрейды (PG18, React 19, Py 3.14) до финала.

## 4. Изменения ТЗ относительно прошлой версии
Не обнаружено: файл идентичен прежнему `tz.pdf.txt`. Если Марио ждал новую редакцию, вероятно, загружен тот же PDF. Стоит перепроверить исходник.
