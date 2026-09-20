# Журнал Red Team: прогон 16.09.2026

Таксономия классов, каталоги атак `RT-A…RT-I` и список stop-ship — в
[RED_TEAM.md](RED_TEAM.md). Здесь фиксируется конкретный прогон: что атаковали,
что подтвердилось, что закрыто и чем это доказано.

Правило журнала: находка считается закрытой только если есть регрессия, которая
краснеет при откате исправления. Формулировка «исправлено» без такой проверки
оставляет находку открытой.

Базовая ревизия прогона: `49c3a5e` (импорт матрицы 132 правил, закрытие
fail-open каскада и финализации).

## Как воспроизвести

```bash
pip install -e "backend[dev]"
ruff check backend scripts
mypy --strict backend/src
pytest backend/tests -q
python scripts/check_contracts.py
# то же, что делает job `db` в CI: схема исполняется, ограничения проверяются
psql -v ON_ERROR_STOP=1 \
  -f backend/src/kontur/infrastructure/db/schema.sql \
  -f backend/src/kontur/infrastructure/db/checks.sql
```

Проверка «регрессия действительно ловит»: удалите из `schema.sql` триггер
`protocols_finalized_is_immutable`, CHECK `gold_label` или
`sync_only_after_finalize` и запустите `checks.sql` — скрипт падает с
сообщениями «финализированный протокол оказался изменяемым»,
«АУТО_НО_ДИФФЕРЕНЦЕ попал в GOLD», «синхронизация началась до финализации».

## Закрыто в этом прогоне

| ID | Набор | Класс | Атака | Цена отказа | Исправление | Регрессия |
|---|---|---|---|---|---|---|
| RT-2609-01 | RT-E | S1 | Код параметра приходит из PDF с неразрывным дефисом, NBSP, полноширокими цифрами или кириллической «Р» вместо латинской «P» | Код не совпадает ни с одним из 132 правил: находка исчезает без сообщения об ошибке | NFKC, свёртка дефисов и пробелов, алиасы разделов (`ПЗ`/`СМ`/`ООС`), побуквенные омоглифы только если результат есть в матрице | `test_rule_codes.py::test_typography_from_pdf_does_not_silently_break_the_code`, `::test_cyrillic_section_aliases_beat_letter_homoglyphs`, `::test_homoglyph_fold_is_accepted_only_when_the_code_is_in_the_matrix` |
| RT-2609-02 | RT-E | S1 | Ответ участника собирается вручную в произвольном формате, без валидации по `submission_schema` | Формально работающая система получает неполный или нулевой скоринг | `evaluation/submission.py`: `build_check`, `build_submission`, единая константа `CONTEST_CODE_STYLE` | `test_submission.py::test_submission_payload_validates_against_organizer_schema` |
| RT-2609-03 | RT-B, RT-E | S1 | В ответ попадает нарушение без доказательства или со страницей `0` | Без файла и страницы находку нельзя сопоставить с эталоном; растёт доля ложных | fail-closed в `build_check` и `SubmissionEvidence.__post_init__` | `::test_violation_without_evidence_never_reaches_the_answer`, `::test_page_numbering_starts_at_one` |
| RT-2609-04 | RT-D | S0 | Находке подставляется доказательство другого правила или другой группы | Подмена доказательства — ложный юридический статус (stop-ship № 2) | сверка `rule_code` и `evidence_group_id` в `build_check` | `::test_evidence_of_another_rule_cannot_be_attached`, `::test_evidence_group_id_mismatch_is_refused` |
| RT-2609-05 | RT-C | S1 | Автоматический кандидат построен на значении, не подтверждённом токенами страницы; правило требует двойного чтения, второго чтения нет | Домысел распознавания превращается в заявленное нарушение (ADR-0001) | `_assert_groundedness`; `dual_read_required(rule)` читает флаг матрицы, `require_second_read` остаётся явным перекрытием | `::test_candidate_on_ungrounded_value_is_refused`, `::test_dual_read_requirement_is_enforced_when_asked`, `::test_dual_read_flag_on_the_rule_is_enough_without_a_caller_flag` |
| RT-2609-06 | RT-D | S2 | В одной группе доказательств две разные величины на одной стадии | В ответ уходит произвольно выбранное из двух значений | `stage_values` поднимает ошибку связки | `::test_two_values_on_one_stage_are_a_linkage_error` |
| RT-2609-07 | RT-A | S1 | Файл больше 50 МБ, пакет больше 200 МБ, `../` в имени, `pd.pdf.exe`, нулевой файл, ZIP под именем `.pdf` | Лимиты п. 9.1 жили как константы в обработчике и не проверялись; имя с разделителем пути — путь к записи вне каталога объекта (п. 12) | `application/intake.py`: проверки имени, формата, размера, сигнатуры и HTTP-коды 413/415/422/504 | `test_intake.py` (9 тестов) |
| RT-2609-08 | RT-G | S1 | Таймаут разбора и сбой передачи в РиН повторяются без ограничения либо теряются молча | «До двух повторов» (п. 9.1) и «1, 5, 15 минут» (п. 9.6) существовали только в тексте | `application/retry_policy.py`: конечные повторы, исчерпание даёт уведомление администратора, передача остаётся `PENDING_SYNC` | `test_retry_policy.py` |
| RT-2609-09 | RT-H | S1 | Контракт не требует аутентификации; администратор подтверждает нарушение и финализирует протокол | Обход полномочий (stop-ship № 3), нарушение п. 12 | `presentation/rbac.py` как единственный источник матрицы прав, `security`, `x-required-roles`, ответы 401/403 в OpenAPI, сверка в `check_contracts.py` | `test_rbac.py`, `scripts/check_contracts.py` |
| RT-2609-10 | RT-G | S0 | `UPDATE` или `DELETE` финализированного протокола | Протокол меняется после финализации без новой версии (stop-ship № 8) | триггер `protocols_finalized_is_immutable`; отмена финализации разрешена только с причиной в `kontur.unfinalize_reason` и переходом в `VERIFICATION_COMPLETED` | `checks.sql` § 1–3 (job `db`) |
| RT-2609-11 | RT-E | S0 | В GOLD попадает машинный `AUTO_NO_DIFFERENCE`, метка без ответственного эксперта, отрицательный вердикт без кодированной причины | Обучение и приёмка на собственных машинных метках — самоподтверждение (п. 9.4) | CHECK на `gold_label`, ограничения `gold_requires_expert` и `negative_gold_requires_reason` | `checks.sql` § 4–6, `test_schema_sql.py::test_machine_status_cannot_become_a_gold_label` |
| RT-2609-12 | RT-G | S1 | Состояние процесса живёт только в памяти; выгрузка во внешнюю ИС начинается до финализации; счётчик повторов не ограничен | После перезапуска процесс невосстановим; п. 9.6 требует только финализированный протокол | таблица `processes`, ограничения `sync_only_after_finalize`, `finalized_needs_human`, границы счётчиков повторов | `checks.sql` § 8–10, `test_schema_sql.py::test_schema_freezes_process_state_and_finalization_invariants` |
| RT-2609-13 | RT-G | S2 | `schema.sql` никогда не исполнялся в CI (только строковые проверки), шаг `ruff` дублировался | Ошибка DDL обнаружилась бы при развёртывании, а не в CI | job `db` с Postgres 16 исполняет `schema.sql` и `checks.sql`; дубль шага удалён | `.github/workflows/ci.yml` |
| RT-2609-14 | RT-A | S3 | Перечень кодов отказа приёма дублировался в `pipeline` и в OpenAPI | Контракт и код разъезжаются незаметно | единый источник `intake.TZ_REJECTION_CODES`, реэкспорт в `pipeline`, сверка в `check_contracts.py` | `test_intake.py::test_rejection_codes_do_not_drift_from_the_contract` |
| RT-2609-22 | RT-G | S3 | Два конфигурационных файла ruff (разные first-party для `kontur`) | Локально зелено, CI красно | явный `src` в корневом `ruff.toml` | `ruff check backend scripts` |
| RT-2609-23 | RT-G | S0 | `kontur.unfinalize_reason` позволяла переписать payload в том же UPDATE | Обход stop-ship № 8 | триггер сравнивает все поля кроме `status`/`finalized_at` | `checks.sql` § 3 |
| RT-2609-24 | RT-E | S1 | Побуквенная свёртка `С`→C превращала `СМ-132` в `CM-132` | Находка исчезала или цеплялась к несуществующему коду | алиасы разделов; свёртка принимается только если код есть в матрице | `test_rule_codes.py`, `test_matrix_registry.py` |
| RT-2609-25 | RT-G | S1 | `sync_only_after_finalize` смотрел на `process_state` | После отмены финализации выгрузка в РиН снова возможна | триггер `processes_sync_requires_finalized_protocol` (`KNT02`) | `checks.sql` § 13 |
| RT-2609-15 | RT-G, RT-H | S1 | Ручки API возвращали `NotImplementedError` | Администратор мог вызвать юридические операции | FastAPI вызывает `evaluate_batch`, `authorize` и `next_sync_attempt` | `test_api.py` |
| RT-2609-20 | RT-G | S3 | `registry.DEFAULT_ROOT` вычислялся во время импорта | Модуль нельзя импортировать без каталога | путь ищется в конструкторе `FileRuleRegistry` | `test_matrix_registry.py::test_importing_registry_does_not_require_matrix_on_disk` |
| RT-2609-26 | RT-G | S2 | `checks.sql` § 9 не ловил `KNT02` | Job `db` краснел на легальной проверке | в EXCEPTION добавлен `SQLSTATE 'KNT02'` | `checks.sql` § 9 |

## Открыто

| ID | Класс | Находка | Почему не закрыто здесь | Следующий шаг |
|---|---|---|---|---|
| RT-2609-21 | S3 | Замер юзабилити п. 9.3 не проведён | Форма есть в `docs/USABILITY_PROTOCOL.md`; нет сессий с инспекторами | провести 5 сессий до гейта K |

## Прогон 17.09.2026 (гейт C)

Базовая ревизия: `6fca626` (merge PR #2). Предмет: паспорт, PDF-токены, Exact Match,
координаты страницы. KR-055, РиН, DAO, UI не атаковались.

### Закрыто в этом прогоне

| ID | Набор | Класс | Атака | Цена отказа | Исправление | Регрессия |
|---|---|---|---|---|---|---|
| RT-2709-01 | RT-D | S1 | Файл переименован/перемещён; identity берётся из имени | Чужой/новый документ при том же содержимом | `file_sha256` содержимого; путь не в хеш | `test_pdf_tokens.py::test_same_bytes_keep_identity_under_rename` |
| RT-2709-02 | RT-D | S1 | Стадия в штампе ПД, в имени файла РД — система выбирает одну | Неверный эталон редакции (stop-ship № 4) | конфликт обнуляет `doc_stage` | `test_passport.py::test_stamp_and_filename_stage_conflict_clears_stage` |
| RT-2709-03 | RT-D | S1 | Шифр из имени файла, в штампе его нет | Ложный паспорт | `document_code` только из токенов | `::test_filename_is_not_used_as_document_code` |
| RT-2709-04 | RT-A | S1 | Повреждённый/пустой PDF принимается как пустая страница | Тихий пропуск объекта | `extract_pdf_bytes` бросает `ValueError` | `test_pdf_tokens.py::test_corrupt_pdf_is_an_error_not_empty_success` |
| RT-2709-05 | RT-B | S2 | Текст вне CropBox в доказательствах | Находка на невидимом фрагменте | токен вне CropBox отбрасывается | `::test_text_outside_cropbox_is_not_a_token` |
| RT-2709-06 | RT-E | S2 | Exact Match шифра после casefold | Ложное совпадение ключевых полей (вопрос 10) | `normalize_key_field` без casefold; порог по Wilson | `test_metrics.py::test_key_field_exact_match_is_case_sensitive_in_ciphers` |
| RT-2709-08 | RT-D | S2 | Новая неутверждённая редакция становится эталоном | Ложные нарушения по всему объекту (stop-ship № 4) | `resolve_revision` берёт только APPROVED | `test_revision_resolver.py::test_unapproved_newer_revision_does_not_become_baseline` |
| RT-2609-17 | RT-G | S2 | Публикация без категорий и без подписи | Скоринг-гейт 59/100 | `PublicationSignature` и `REQUIRED_CATEGORIES` блокируют `evaluate` | `test_release_gate.py` |

### Открыто после прогона

| ID | Класс | Находка | Почему не закрыто | Следующий шаг |
|---|---|---|---|---|
| RT-2709-09 | S3 | Character Accuracy / CER не реализованы | Не смешивать с Exact Match | E1 после bake-off OCR |

Остальные пробелы — [KNOWN_GAPS.md](KNOWN_GAPS.md).
Порог Exact Match ≥0,92 на validation v0 не атаковался: выборки нет, метрика есть.

## Прогон 17.09.2026 (п. 9.5 SUSPICION)

### Закрыто

| ID | Набор | Класс | Атака | Цена отказа | Исправление | Регрессия |
|---|---|---|---|---|---|---|
| RT-2609-16 | RT-E | S1 | Подозрение без `evidence_group_id`, спам дублей, автомат пишет CONFIRMED | Ложный юридический статус | `SuspicionSignal` со статусом SUSPICION; дедупликация; CONFIRMED отвергается | `test_suspicion.py` |

УКЭП и sandbox ИАИС «РиН» (п. 9.6) этим модулем не закрываются.

## Прогон 17.09.2026 (вечер, main)

### Закрыто

| ID | Набор | Класс | Атака | Цена отказа | Исправление | Регрессия |
|---|---|---|---|---|---|---|
| RT-2709-07 | RT-B | S1 | Белый/скрытый текст в CropBox читается как штамп | Ложный паспорт, ложная находка | СКО яркости vs текстовый слой; `text_render_agreement=False` обнуляет штамп | `test_visual_text.py`, `test_rt_suites.py::test_rt_b_hidden_text_layer_blocks_automatic_finding` |
| RT-2609-27 | RT-G | S2 | Процесс только в RAM | После рестарта теряется состояние выгрузки | `ProcessStore` + снимок; Postgres-адаптер; находки не персистируются | `test_process_store.py` |

`text_render_agreement=True` ставится только после выборки пикселей. ИАИС «РиН» не вызывается.

## Прогон 17.09.2026 (вечер, CI/контракт/CER)

### Закрыто

| ID | Набор | Класс | Атака | Цена отказа | Исправление | Регрессия |
|---|---|---|---|---|---|---|
| RT-2609-19 | RT-G | S2 | OpenAPI 3.0.3 → JSON Schema 2020-12; `format: binary` ломало генераторы клиентов | SDK падали на multipart | Bump до 3.1.0; `contentMediaType` вместо `format: binary` | `contracts/openapi.yaml` (671d8b8) |
| RT-2609-18 | RT-G | S2 | Фронтенд (React + TypeScript) не проверялся в CI | Ошибки типов не обнаруживались до деплоя | Job `frontend`: `npm ci` + `npx tsc --noEmit` | `.github/workflows/ci.yml` |
| RT-2709-09 | RT-C | S3 | `character_accuracy()` бросала `NotImplementedError("E1")`; CER недоступен | Метрика гейта I отсутствует | Wagner–Fischer CER; CA = 1 − CER ∈ [0; 1]; NFC + схлопывание пробелов | `test_metrics.py::test_character_accuracy_*` — 8 кейсов (ea75e70, bee1a1b) |

## OSINT, привлечённый к прогону

Нормативная база:

- ГОСТ Р 21.101-2026 существует и опубликован: карточка Росстандарта
  (<https://protect.gost.ru/gost/details/17bc12e8-6579-4145-b141-56855e772e7f>),
  «Гарант» (<https://base.garant.ru/413848474/>). Предыдущая редакция —
  ГОСТ Р 21.101-2020 (<https://base.garant.ru/74691448/>). Вывод: вопрос 3
  организатору поставлен обоснованно, а вердикт по матрице и действующая норма
  обязаны жить раздельно (overlay).

Распознавание и извлечение (что это меняет в коде):

- «Без слепого соответствия» (arXiv:2609.00232, 31.08.2026) — модели склонны подтверждать
  формулировку задания вместо проверки факта. Ответ «соответствует» без
  grounded-токенов не имеет права стать находкой; `_assert_groundedness`
  вызывается до сборки строки ответа.
- Актуальные открытые OCR-модели: `datalab-to/chandra-ocr-2`, `deepseek-ai/DeepSeek-OCR`,
  `baidu/Unlimited-OCR`, `zai-org/GLM-OCR`, `datalab-to/surya-ocr-2`,
  `dots-studio/dots.ocr`, `PaddlePaddle/PP-OCRv5_server_det`, `stepfun-ai/GOT-OCR2_0`.
  Ни одна не даёт гарантии на штампах, выносках и таблицах ТЭП, поэтому
  двойное чтение остаётся обязательным.

Не подтверждено открытыми источниками и потому не реализуется догадкой:
формат `parameter_code` в приёмке соревнования, регламент и требования к подписи
для ИАИС «РиН», трактовка мегабайта в лимитах п. 9.1. Все три —
[QUESTIONS_TO_ORGANIZER.md](QUESTIONS_TO_ORGANIZER.md).

## Замечание о нормализации

Для кодов параметров применяется NFKC со свёрткой дефисов, пробелов и
омоглифов: код — идентификатор, и его нельзя потерять из-за типографики.
Для значений при сравнении Exact Match остаётся NFC (вопрос 10): значение —
данные, и агрессивная нормализация там меняла бы смысл.
Для character_accuracy применяется NFC + схлопывание повторных пробелов;
регистр не сворачивается (ТЗ п. 9.1).
