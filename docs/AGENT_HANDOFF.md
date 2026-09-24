# Handoff для следующего ИИ

Срез **23.09.2026**. Бриф для ИИ с GitHub: [`GH_SITUATION_2026_09_21.md`](GH_SITUATION_2026_09_21.md).
Несколько ИИ на одном репо: [`GH_AGENT_BUS.md`](GH_AGENT_BUS.md).
HEAD смотреть `git rev-parse origin/main`.
Машиночитаемый пакет — не scorecard приёмки. Гейты I/J/K **открыты**.
Инженерный замер Gate L на GitHub-hosted runner есть; production SLA нет.
Порог ТЗ не публиковать без нижней границы Wilson на held-out validation.

**Freeze инфры до 29.09:** не добавлять OIDC/TLS/RabbitMQ 4.x/observability/УКЭП/РиН
без sandbox. Critical path — конкурсный вертикальный срез (evidence UI, Gate K,
пять правил), не транспорт. Issues [#75](https://github.com/KonkovDV/Kontur/issues/75)–[#84](https://github.com/KonkovDV/Kontur/issues/84).
Открытых продуктовых PR нет. Adversarial-пакет влит в #128; #80 закрыт.
Оставшиеся VLM и system prompt — открытый #84. Weekly Dependabot (#85) — не P0.
На origin рабочая линия — `main`. OCR-хвосты `16f3a06` / `2ddc2b3` не мержить.

## Допуск 23.09.2026

Репозиторий `KonkovDV/Kontur` публичный. Лицензия кода — Apache-2.0 (`LICENSE`, `docs/THIRD_PARTY_NOTICES.md`).
Вопросы 20–22 не отправлены: связи с жюри нет; решения ниже приняты по записи сессии 16.09 и доске оценивания.
Скрытый тест не открывать. Эталон ПД без штампа — ADR-0014 (`PACKAGE_DEFAULT`). Индекс и «В производство работ» не утверждение.
`export_git_sha` в `agent_handoff.json` отстаёт от HEAD нарочно.
Живой экран инспектора: загрузка по стадии, комплект, «Назначить эталоном», список `GET .../findings`, три панели с PNG и polygon, решение по одной находке. На живом экране массового подтверждения нет. Учебный рекордер Gate K пишет локальный JSON по отмеченным кандидатам и не вызывает API рецензии. РиН на экране — `sync_state`, не ACK. Gate K не закрыт.

## Читать в этом порядке

1. [`AGENTS.md`](../AGENTS.md) — инварианты 1–14.
2. [`GH_AGENT_BUS.md`](GH_AGENT_BUS.md) — claim на issue до правок.
3. [`data/dataset/agent_handoff.json`](../data/dataset/agent_handoff.json) — гейты, запреты, команды, draft_prs, extractor_triage_complete.
4. [`data/matrix/coverage_snapshot.json`](../data/matrix/coverage_snapshot.json) — разбивка `executable` / `extractor_missing` / `advisory` / `source_missing` (coverage, не вся матрица executable). Сейчас 44 / 83 / 1 / 4 из 132.
4a. [`data/matrix/family_triage.json`](../data/matrix/family_triage.json) и [`docs/EXTRACTOR_FAMILY_TRIAGE.md`](EXTRACTOR_FAMILY_TRIAGE.md) — поштучное решение по 28 правилам семейств `exact_field` / `presence`: какой вид доказательства нужен и почему графика не стала текстом.
4b. [`data/matrix/class_ladder_triage.json`](../data/matrix/class_ladder_triage.json) и [`docs/CLASS_LADDER_TRIAGE.md`](CLASS_LADDER_TRIAGE.md) — разбор 23 «классоподобных» правил: 5 переведены в `executable` через `enum` + `class_not_lower`, 13 осознанно оставлены `extractor_missing` с указанием причины (инвертированная лестница, набор признаков, таблица, допуск в обе стороны).
4c. [`data/matrix/number_family_triage.json`](../data/matrix/number_family_triage.json) и [`docs/NUMBER_FAMILY_TRIAGE.md`](NUMBER_FAMILY_TRIAGE.md) — разбор 57 числовых правил: 6 переведены в `executable`, 51 оставлено `extractor_missing` с кодом причины (обмер по чертежу, подсчёт объектов, площадь по контуру, таблица по элементам).
5. [`data/dataset/gold_inventory.json`](../data/dataset/gold_inventory.json) — публичный gold ≠ frozen val.
6. [`data/dataset/gold_evidence_files.json`](../data/dataset/gold_evidence_files.json) — какие PDF gold грузить: F0171 как PD, F0201 `RD_ID_MIXED` только как RD.
7. [`data/dataset/train_public_index_stats.json`](../data/dataset/train_public_index_stats.json) — 203 файла, стадии, join исходных PDF.
8. [`data/dataset/train_public_engineering.json`](../data/dataset/train_public_engineering.json) и `train_public_pred.jsonl` — gold-evidence прогон 24.09: 0 попаданий из 6. PD+RD загружены. IOS4-078 и IOS4-079 — `LOW_QUALITY` («PD: якорь или число не найдены»). Порог ТЗ не берётся и не публикуется.
9. [`docs/WORK_PLAN.md`](WORK_PLAN.md), [`docs/KNOWN_GAPS.md`](KNOWN_GAPS.md), [`docs/PR_QUEUE.md`](PR_QUEUE.md), [`docs/TZ_SCORECARD.md`](TZ_SCORECARD.md), [`docs/RESEARCH_OSINT_2026.md`](RESEARCH_OSINT_2026.md). [`docs/GH_SITUATION_2026_09_21.md`](GH_SITUATION_2026_09_21.md) и issue [#86](https://github.com/KonkovDV/Kontur/issues/86) — снимок 21.09 (29/103), не текущее покрытие. Живая шина — [`docs/GH_AGENT_BUS.md`](GH_AGENT_BUS.md).

Пересборка: `python scripts/export_agent_dumps.py` или `make agent-dumps`.
Локальный скоринг: `python -m kontur.evaluation.train_public` (на Windows нет `make`).

## Что уже на `main`

Шаги 0–2 плана: HTTP-пайплайн, OCR `ocr_text` = `MEASURED` (гейт I открыт), очередь READY→VERIFYING→COMPLETED.
Шаг 3: harness `train_public.py`, gold MIXED→RD только для файлов из `gold_evidence_files.json`.
Снимок `train_public_engineering.json` от 24.09 (выгрузка `python -m kontur.evaluation.train_public`): `n_read=2`, `hits=0`, IOS4-078 и IOS4-079 — `LOW_QUALITY` («PD: якорь или число не найдены»). Это не CANDIDATE и не закрытие гейта J.
F0201: заполненная графа «Утвердил» + ФИО → `APPROVED`. F0171: обложка тома, в штампе нет «утв.»/«Утвердил»+ФИО. Заголовок «Согласовано» не эталон.
Гейт J открыт. Wilson 6/6 всё равно ниже порога (нужно n≥16).
`GAP-K6-P95` закрыт живым k6 на GHA (100 VU × 60 с, n=6000, p95=18,26 мс). Это не production SLA.
HTTP-вход: проверенный JWT (RS256/ES256). Legacy `actor@object/ROLE` только при
`KONTUR_ALLOW_INSECURE_DEV_AUTH`. Статический публичный ключ ≠ OIDC/JWKS.
Разбор PDF — в дочернем процессе; таймаут убивает child, не поток API.
Контейнеры core/gateway: non-root 10001, read-only rootfs, `cap_drop: ALL`,
порты на loopback (PR #60). Повтор идентичной загрузки (hash+stage) не
открывает процесс заново и не гоняет pipeline; `FINALIZED` → 409.
`web/` и `gateway/` зафиксированы `package-lock.json`; CI frontend — `npm ci`.
Триаж семейств `exact_field` / `presence`: AR-052, POS-087, POD-091, ZU-130
переведены в `executable` (закрытые текстовые шаблоны, фикстуры на
AUTO_NO_DIFFERENCE / CANDIDATE / MISSING_EVIDENCE / LOW_QUALITY / ABSTAIN),
POD-095 — `advisory` (`presence` не способен выдать CANDIDATE), OOS-098…0101 —
`source_missing` (АИС «ОСИГ», РНИС, «Мобильный КПТС», ГРОО вне пакета ПД/РД/ИД).
`_downgrade_for_coverage` в `evaluate.py` понижает CANDIDATE до `low_quality`
для `advisory` / `source_missing` / `not_applicable`. Gate J не закрыт.
Учебный рекордер Gate K в `web/` пишет JSON `kontur-usability-v1`; сессий нет,
`closes_gate_k` false. `MISSING_EVIDENCE` нельзя подтвердить как нарушение.
Ruleset `main-pr-and-ci` (id 23890545) активен на `main`: PR, запрет
force-push и удаления, обязательные checks `ci.yml`, `relay-container` и
`sync-lifecycle-db`. Обязательных ревью 0. Это не закрытие гейтов I/J/K.
Force-push не используем.
PostgreSQL `save()` финализации fail-closed (PR #64): без атомарной
материализации INSERT placeholder запрещён. Payload собирается в
application-слое, JSON пишется в той же транзакции, что и процесс;
`UNIQUE (object_id, version)`; повтор с тем же каноническим JSON идемпотентен,
расхождение — конфликт. Без `connection.transaction()` финализация отклоняется.
PR #65 влит: advisory lock объекта, `FOR UPDATE` процесса/находок/протоколов,
`payload_sha256`, `integration_outbox` PENDING, ADR-0009. Live Postgres: retry
идемпотенен, гонка version fail-closed, outbox `SKIP LOCKED`. Crash-before-commit
нет. Outbox relay (ADR-0010) публикует в брокер с confirms и паузами 1/5/15 мин;
это не РиН и не exactly-once. HTTP по-прежнему inline L1–L7. PR #66 закрыт красным
(FK `objects.id`); правка на `main`. PR #67 влит: отдельный `outbox-relay`
UID 10001, quorum queue, compose `kontur` не guest; classic
`AmqpConfirmedPublisher` снят. PR #68 влит: claim→`SYNCING`, nack→`RETRY_WAIT`,
исчерпание outbox `FAILED_TERMINAL` / процесс `PENDING_SYNC`, ручной retry с
`actor_id`, audit `SYNC_RETRY_EXHAUSTED` / `SYNC_MANUAL_RETRY`. Publisher
confirm **не** ставит `SYNCED` (ADR-0011). Transactional inbox (ADR-0012 / PR #69,
#71): уникальный `event_id`, persist затем `await ack/nack`, prefetch 1,
poison/DLX; `x-delivery-count` — число прошлых неуспехов. PR #70 уточняет
контракт JWT/object-scope без смены runtime. PR #72 пинит негативные
инварианты OpenAPI тестами. PR #73: `inbox-consumer` UID 10001, push
`queue.iterator()`, reconnect сессии после ambiguous settlement без
повторного nack той же доставки. Не бизнес-ACK РиН. Инспектор может
назначить загруженный файл эталоном (`POST .../revisions/{file_id}/select`):
штамп не подменяется, `NOT_APPROVED` нельзя перекрыть, автомат не пишет
`CONFIRMED_VIOLATION`. PR #74 влит: mem/cpu/pids у всех восьми Compose-сервисов;
CI сверяет точные байты и запрещает `deploy.resources`; это не production
capacity. Продуктовая очередь PR пуста. #85 Dependabot — не P0. Репетиция #78:
синтетические PDF, три CANDIDATE, confirm/reject, protocol v1, outbox PENDING
(`test_demo_cold_start.py`, `docs/DEMO_COLD_START.md`). Не Polar, не видео,
не гейт K. Пакет сдачи #79: `docs/SUBMISSION_PACK.md`,
`python scripts/export_submission_pack.py`. Backlog GitHub:
#76 evidence UI, #77 Gate K,
#80 закрыт (adversarial-пакет в #128). Не открывать заново: VLM и запрет
класть текст страницы в system prompt — это #84. `runner_id=0` = не настоящий CI-прогон.
#81 branch protection (ruleset `main-pr-and-ci` закрывает критерий; не гейт),
#82 family extractors (**все 83 `extractor_missing` разобраны** по трём триаж-док.; новых правил без геометрии нет), #83 split,
#84 VLM isolation.
GAP-EMB добавлен в `docs/KNOWN_GAPS.md` на ветке `feat/adversarial-pdf-pack` (commit `7ec43b7`).

Поставка 20.09.2026: в `files/` есть `ПАКЕТ_УЧАСТНИКАМ_БЕЗ_ОТВЕТОВ_v2.0`
(checksums 18/18) и распакованный объект `10_Полярная_25_СОШ±1100к7` (~20,9 ГБ,
ПД/РД/ИД, без gold). Нет frozen val, GOLD OCR, объектов 11–18, SHA исходных
`.tar`, утверждённого ПД для F0171. Объект 10 не TRAIN_PUBLIC и не закрывает
гейт J. Закрытый zip организатора и `РАЗМЕЧЕННЫЙ_TEST__213` не открывать для порогов.

## Что нельзя

- Вливать `feat/ocr-gate-i-crop3x-oem1` (`16f3a06`) и
  `feat/ocr-300dpi-step2-verifying` (`2ddc2b3`, усечённый `ocr_tesseract.py`).
- Открывать TEST_HIDDEN / `РАЗМЕЧЕННЫЙ_TEST__213` / Речников для порогов.
- Распаковывать `ПАКЕТ_ОРГАНИЗАТОРА_ЗАКРЫТЫЙ_v2.0.zip` для порогов, prompt и regex.
- Считать пакет без ответов v2.0 frozen val или закрытием гейта J.
- Закрывать `GAP-IOS4-VAL` по 15 строкам gold или SILVER CA.
- Ставить `ocr_text=AVAILABLE` без GOLD Wilson.
- Угадывать не-gold `RD_ID_MIXED` как RD+ID. Overlay `annotated_documents` не источник скоринга.
- Считать заголовок ГОСТ «Согласовано» / строку «ГИП» утверждением редакции.
- Писать `CONFIRMED_VIOLATION` автоматом или LLM.
- Возвращать import-time monkeypatch `ProcessRecord` из закрытого PR #61.
- Возвращать экспериментальный PR #63: provenance в `finding_to_schema` не
  вырезать, infrastructure не импортирует `assemble_protocol`.
- Требовать `payload.kind = materialized` или `assembled=true` в JSON ТЗ:
  `protocol.schema.json` с `additionalProperties: false` такие поля не содержит
  (ADR-0009). Guard выгрузки — `PROTOCOL_FINALIZED` + hex `payload_sha256`.
- Не открывать #80 заново: пакет влит, VLM остаётся в #84. `runner_id=0` — не настоящий прогон.
- Переводить `extractor_missing` в `executable` без нового экстрактора: все 83 разобраны, блокер документирован.
- Считать разные шифры одной стадии конфликтом всего комплекта или одним
  последним файлом стадии. Не угадывать порядок по «ред. N» без successor.
  Не переводить голое число в мм. Не считать последний загруженный файл
  эталоном, если задан successor.

## Следующие слайсы

1. Конкурсный вертикальный срез (не 132/132): эталон, комплект по шифрам,
   фикстуры Д1 (`test_d1_extractor_fixtures.py`), evidence UI, Gate K.
   Видео — человек. Polar не gold. Демо #78 и пакет #79 уже в коде.
2. GOLD OCR и frozen val: кодом гейты I и J не закрыть.
3. Пять сессий → `USABILITY_RESULTS.md` (гейт K / `RT-2609-21` открыт).
4. Семейства `exact_field` / `presence`: триаж всех 28 правил сделан
   (`family_triage.json`, `EXTRACTOR_FAMILY_TRIAGE.md`), 4 правила стали
   `executable`, 1 `advisory`, 4 `source_missing`. Осталось 19 правил, и им нужен
   **не** текстовый экстрактор: 14 — `geometry` (вектор чертежа, подсчёт,
   пересечение зон), 5 — разбор ячейки таблицы / `semantic_candidate`.
   Не помечать их `executable` по совпадению подписи с названием параметра.
4a. Лестницы классов «не ниже»: разобраны все 23 правила, у которых оператор
   `class_not_lower` или в `unit` стоит «Класс»/«Марка». Пять стали `executable`
   (KR-056 марка стали, KR-057 класс арматуры, PPM-103 предел огнестойкости,
   PPM-107 класс КМ, ZU-124 класс энергоэффективности); улучшение класса в РД —
   не нарушение, понижение — `CANDIDATE`. Кириллические омоглифы в марках
   сворачиваются (`comparators.fold_homoglyphs`), латинская `I` не тронута, чтобы
   не сломать римские цифры PZ-022. Остальные 13 требуют другого экстрактора —
   причины в `class_ladder_triage.json`.
4b. Числовое семейство: разобраны все 57 правил с `extractor.type = number`,
   остававшихся `extractor_missing`. Шесть стали `executable` (ZU-125, ZU-127,
   ZU-128, ZU-131 — теплотехника и энергопаспорт; SM-132 — итог ССР; PPM-114 —
   расход НПВ). Операторы и допуски не менялись, менялся только экстрактор.
   Остальные 51 требуют обмера по чертежу, подсчёта объектов, площади по контуру
   или таблицы по элементам — коды причин в `number_family_triage.json`.
   **Все 83 `extractor_missing` полностью разобраны по трём триаж-документам.
   Без новых экстракторов (`geometry`, `object_counting`, `per_element_table`,
   `semantic_candidate`) переводить правила в `executable` нельзя.**
5. `split()` (GAP-SPLIT) до демо.
6. Sandbox РиН, HTTP `submitted/confirmed/ambiguous` и бизнес-ACK → `SYNCED` — нет.
7. JWKS/OIDC, TLS 1.3, антивирус, observability — **freeze** до подачи.
8. Если PAT когда-либо светился в issue/PR/логе — отозвать в GitHub Settings
   → Developer settings → Personal access tokens; не вставлять токен в чат.

Гейты I и J кодом не закрыть: нет GOLD OCR и нет frozen val на 106 критических.
