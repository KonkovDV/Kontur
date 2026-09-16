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
«AUTO_NO_DIFFERENCE попал в GOLD», «синхронизация началась до финализации».

## Закрыто в этом прогоне

| ID | Набор | Класс | Атака | Цена отказа | Исправление | Регрессия |
|---|---|---|---|---|---|---|
| RT-2609-01 | RT-E | S1 | Код параметра приходит из PDF с неразрывным дефисом, NBSP, полноширинными цифрами или кириллической «Р» вместо латинской «P» | Код не совпадает ни с одним из 132 правил: находка исчезает без сообщения об ошибке | NFKC, свёртка дефисов и пробелов, алиасы разделов (`ПЗ`/`СМ`/`ООС`), побуквенные омоглифы только если результат есть в матрице | `test_rule_codes.py::test_typography_from_pdf_does_not_silently_break_the_code`, `::test_cyrillic_section_aliases_beat_letter_homoglyphs`, `::test_homoglyph_fold_is_accepted_only_when_the_code_is_in_the_matrix` |
| RT-2609-02 | RT-E | S1 | Ответ участника собирается вручную в произвольном формате, без валидации по `submission_schema` | Формально работающая система получает неполный или нулевой скоринг | `evaluation/submission.py`: `build_check`, `build_submission`, единая константа `CONTEST_CODE_STYLE` | `test_submission.py::test_submission_payload_validates_against_organizer_schema` |
| RT-2609-03 | RT-B, RT-E | S1 | В ответ попадает нарушение без доказательства или со страницей `0` | Без файла и страницы находку нельзя сопоставить с эталоном; растёт доля ложных | fail-closed в `build_check` и `SubmissionEvidence.__post_init__` | `::test_violation_without_evidence_never_reaches_the_answer`, `::test_page_numbering_starts_at_one` |
| RT-2609-04 | RT-D | S0 | Находке подставляется доказательство другого правила или другой группы | Подмена доказательства — ложный юридический статус (stop-ship № 2) | сверка `rule_code` и `evidence_group_id` в `build_check` | `::test_evidence_of_another_rule_cannot_be_attached`, `::test_evidence_group_id_mismatch_is_refused` |
| RT-2609-05 | RT-C | S1 | Автоматический кандидат построен на значении, не подтверждённом токенами страницы; правило требует двойного чтения, второго чтения нет | Домысел распознавания превращается в заявленное нарушение (ADR-0001) | `_assert_groundedness`; `dual_read_required(rule)` читает флаг матрицы, `require_second_read` остаётся явным перекрытием | `::test_candidate_on_ungrounded_value_is_refused`, `::test_dual_read_requirement_is_enforced_when_asked`, `::test_dual_read_flag_on_the_rule_is_enough_without_a_caller_flag` |
| RT-2609-06 | RT-D | S2 | В одной группе доказательств две разные величины на одной стадии | В ответ уходит произвольно выбранное из двух значений | `stage_values` поднимает ошибку связки | `::test_two_values_on_one_stage_are_a_linkage_error` |
| RT-2609-07 | RT-A | S1 | Файл больше 50 МБ, пакет больше 200 МБ, `../` в имени, `pd.pdf.exe`, файл нулевой длины, ZIP под именем `.pdf` | Лимиты п. 9.1 жили как константы в обработчике и не проверялись; имя с разделителем пути — путь к записи вне каталога объекта (п. 12) | `application/intake.py`: проверки имени, формата, размера, сигнатуры и HTTP-коды 413/415/422/504 | `test_intake.py` (9 тестов) |
| RT-2609-08 | RT-G | S1 | Таймаут разбора и сбой передачи в РиН повторяются без ограничения либо теряются молча | «До двух повторов» (п. 9.1) и «1, 5, 15 минут» (п. 9.6) существовали только в тексте | `application/retry_policy.py`: конечные повторы, исчерпание даёт уведомление администратора, передача остаётся `PENDING_SYNC`, а не терминальным отказом | `test_retry_policy.py` |
| RT-2609-09 | RT-H | S1 | Контракт не требует аутентификации; администратор подтверждает нарушение и финализирует протокол | Обход полномочий (stop-ship № 3), нарушение п. 12 | `presentation/rbac.py` как единственный источник матрицы прав, `security`, `x-required-roles`, ответы 401/403 в OpenAPI, сверка контракта и кода в `check_contracts.py` | `test_rbac.py`, `scripts/check_contracts.py` |
| RT-2609-10 | RT-G | S0 | `UPDATE` или `DELETE` финализированного протокола | Протокол меняется после финализации без новой версии (stop-ship № 8) | триггер `protocols_finalized_is_immutable`; отмена финализации разрешена только с причиной в `kontur.unfinalize_reason` и только переходом в `VERIFICATION_COMPLETED` | `checks.sql` § 1–3 (job `db`) |
| RT-2609-11 | RT-E | S0 | В GOLD попадает машинный `AUTO_NO_DIFFERENCE`, метка без ответственного эксперта, отрицательный вердикт без кодированной причины | Обучение и приёмка на собственных машинных метках — самоподтверждение (п. 9.4) | CHECK на `gold_label`, ограничения `gold_requires_expert` и `negative_gold_requires_reason` | `checks.sql` § 4–6, `test_schema_sql.py::test_machine_status_cannot_become_a_gold_label` |
| RT-2609-12 | RT-G | S1 | Состояние процесса живёт только в памяти; выгрузка во внешнюю ИС начинается до финализации; счётчик повторов не ограничен | После перезапуска процесс невосстановим; п. 9.6 требует только финализированный протокол | таблица `processes`, ограничения `sync_only_after_finalize`, `finalized_needs_human`, границы счётчиков повторов | `checks.sql` § 8–10, `test_schema_sql.py::test_schema_freezes_process_state_and_finalization_invariants` |
| RT-2609-13 | RT-G | S2 | `schema.sql` никогда не исполнялся в CI (только строковые проверки), шаг `ruff` дублировался | Ошибка DDL обнаружилась бы при развёртывании, а не в CI | job `db` с Postgres 16 исполняет `schema.sql` и `checks.sql`; дубль шага удалён | `.github/workflows/ci.yml` |
| RT-2609-14 | RT-A | S3 | Перечень кодов отказа приёма дублировался в `pipeline` и в OpenAPI | Контракт и код разъезжаются незаметно | единый источник `intake.TZ_REJECTION_CODES`, реэкспорт в `pipeline`, сверка в `check_contracts.py` | `test_intake.py::test_rejection_codes_do_not_drift_from_the_contract` |
| RT-2609-22 | RT-G | S3 | Два конфигурационных файла ruff (`ruff.toml` и `backend/pyproject.toml`) по-разному определяли first-party для пакета `kontur` | Локальный прогон зеленел, CI краснел на тех же файлах: разница обнаружилась только после пуша | в корневой `ruff.toml` добавлен явный `src = ["backend/src", "."]`, оба способа вызова дают одинаковый результат | `ruff check backend scripts` и `ruff check --config ruff.toml backend scripts` |
| RT-2609-23 | RT-G | S0 | Дверь `kontur.unfinalize_reason` позволяла в том же `UPDATE` сменить `payload`, версии и хеш | Обход stop-ship № 8: протокол «отменили» и содержимое подменили одним запросом | триггер сравнивает все поля кроме `status`/`finalized_at`; правка payload даёт `KNT01` | `checks.sql` § 3 |
| RT-2609-24 | RT-E | S1 | Побуквенная свёртка `С`→C, `М`→M превращала `СМ-132` в `CM-132` и `ООС-098` в `OOC-098` | Находка либо пропадала, либо цеплялась к несуществующему коду | алиасы разделов; свёртка принимается только если код есть в матрице | `test_rule_codes.py`, `test_matrix_registry.py::test_cyrillic_section_prefixes_resolve_to_catalog_codes` |
| RT-2609-25 | RT-G | S1 | `sync_only_after_finalize` смотрел на `process_state`, а не на статус протокола | После отмены финализации процесс оставался `FINALIZED`, выгрузка в РиН снова была возможна | триггер `processes_sync_requires_finalized_protocol` (`KNT02`) | `checks.sql` § 13 |
| RT-2609-15 | RT-G, RT-H | S1 | Ручки API возвращали `NotImplementedError`; `intake`, RBAC и повторы жили только в pytest | Администратор мог бы вызвать юридические операции, лимиты п. 9.1 не держались на HTTP | FastAPI вызывает `evaluate_batch`, `authorize` и `next_sync_attempt`; протокол не выдумывается; Bearer-заглушка `actor_id/ROLE`, не JWT; процессы — in-memory до DAO | `test_api.py` |
| RT-2609-20 | RT-G | S3 | `registry.DEFAULT_ROOT` вычислялся во время импорта модуля | Модуль нельзя импортировать без каталога матрицы | путь ищется в конструкторе `FileRuleRegistry` | `test_matrix_registry.py::test_importing_registry_does_not_require_matrix_on_disk` |
| RT-2609-26 | RT-G | S2 | `checks.sql` § 9 ловил только `check_violation`, а триггер `KNT02` срабатывает раньше CHECK | Job `db` краснел на легальной проверке запрещённой выгрузки | в EXCEPTION добавлен `SQLSTATE 'KNT02'` | `checks.sql` § 9, `test_schema_sql.py` |

## Открыто

| ID | Класс | Находка | Почему не закрыто здесь | Следующий шаг |
|---|---|---|---|---|
| RT-2609-16 | S1 | П. 9.5 (SUSPICION, четыре подхода, дедупликация) и УКЭП из п. 9.6 — только текст | Нет артефакта и нет sandbox внешней ИС | модуль подозрений с дедупликацией по группе доказательств; требования к подписи — вопрос 14 организатору |
| RT-2609-17 | S2 | `release_gate.evaluate` не требует полного набора категорий; нет подписи ответственного и плана откатa | Политика публикации модели — решение владельца | требовать полный набор категорий и непустые интервалы, хранить подпись и rollback-план вместе с версией модели |
| RT-2609-18 | S2 | React и Node не проверяются в CI | Опция `limit`, которой нет в `http-proxy-middleware` v3, снята; `Content-Length` 413 стоит в Express. Job `frontend` всё ещё нет | lock-файлы, `npm ci` и `tsc --noEmit` в CI |
| RT-2609-19 | S2 | OpenAPI 3.0.3 ссылается на схемы JSON Schema 2020-12 с `type: [..., "null"]` | Смена версии контракта затрагивает генераторы клиентов | перейти на OpenAPI 3.1 либо держать 3.0-совместимые копии схем |
| RT-2609-21 | S3 | Нет протокола юзабилити п. 9.3 (время на протокол, число кликов на находку, пять инспекторов) | Нужны люди и сессии наблюдения | `docs/USABILITY_PROTOCOL.md` с формой замера |
| RT-2609-27 | S2 | HTTP-контур держит процессы в памяти процесса API, а не в таблице `processes` | Схема есть, DAO нет; после перезапуска процессы пропадают — это явно, не «состояние в очереди» | репозиторий процессов на Postgres по `schema.sql` |

## OSINT, привлечённый к прогону

Нормативная база:

- ГОСТ Р 21.101-2026 существует и опубликован: карточка Росстандарта
  (<https://protect.gost.ru/gost/details/17bc12e8-6579-4145-b141-56855e772e7f>),
  «Гарант» (<https://base.garant.ru/413848474/>). Предыдущая редакция —
  ГОСТ Р 21.101-2020 (<https://base.garant.ru/74691448/>). Вывод: вопрос 3
  организатору поставлен обоснованно, а вердикт по матрице и действующая норма
  обязаны жить раздельно (overlay), иначе протокол будет ссылаться на
  недействующую редакцию.

Распознавание и извлечение (что это меняет в коде):

- «Beyond Blind Compliance: Benchmarking Task Verification in OCR Reasoning»
  (arXiv:2609.00232, 31.08.2026) — модели склонны подтверждать формулировку
  задания вместо проверки факта. Прямое следствие для нас: ответ «соответствует»
  без grounded-токенов не имеет права стать находкой, поэтому
  `_assert_groundedness` вызывается до сборки строки ответа.
- «Visual Information Extraction from Documents via Classification-Guided Large
  Vision-Language Models» (arXiv:2607.22723, 22.07.2026) и «HunyuanOCR-1.5»
  (arXiv:2607.04884, 06.07.2026) — извлечение из документов остаётся
  чувствительным к типу страницы и разметке.
- Актуальные по загрузкам открытые OCR-модели на дату прогона:
  `datalab-to/chandra-ocr-2`, `deepseek-ai/DeepSeek-OCR`, `baidu/Unlimited-OCR`,
  `zai-org/GLM-OCR`, `datalab-to/surya-ocr-2`, `dots-studio/dots.ocr`,
  `PaddlePaddle/PP-OCRv5_server_det`, `stepfun-ai/GOT-OCR2_0`. Ни одна не даёт
  гарантии на штампах, выносках и таблицах ТЭП, поэтому двойное чтение остаётся
  обязательным, а `dual_read_required` из матрицы получил исполняемый смысл.

Не подтверждено открытыми источниками и потому не реализуется догадкой:
формат `parameter_code` в приёмке соревнования, регламент и требования к
подписи для ИАИС «РиН», трактовка мегабайта в лимитах п. 9.1. Все три вынесены
в [QUESTIONS_TO_ORGANIZER.md](QUESTIONS_TO_ORGANIZER.md).

## Замечание о нормализации

Для кодов параметров применяется NFKC со свёрткой дефисов, пробелов и
омоглифов: код — идентификатор, и его нельзя потерять из-за типографики.
Для значений при сравнении Exact Match остаётся NFC (вопрос 10): значение —
данные, и агрессивная нормализация там меняла бы смысл (например, полноширинные
и обычные цифры в шифре документа).
