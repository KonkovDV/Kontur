# Шина агентов через GitHub

Как разным ИИ (Cursor, Copilot cloud, Copilot CLI, любой clone с `gh`)
согласовывать работу до **29.09.2026 23:59 МСК** без потери контекста
и без гонок на одном issue.

Не frozen val, не закрытие гейтов I/J/K, не заявление, что вся матрица
executable. Инварианты — [`../AGENTS.md`](../AGENTS.md). Срез —
[`GH_SITUATION_2026_09_21.md`](GH_SITUATION_2026_09_21.md). Машиночитаемый хэндоф —
[`../data/dataset/agent_handoff.json`](../data/dataset/agent_handoff.json).

---

## Зачем так, а не «чат в комментариях»

Репозиторий публичный, лицензия кода Apache-2.0. Ruleset `main-pr-and-ci`
(id 23890545) активен на `main`: PR обязателен, force-push и удаление ветки
запрещены, обязательны checks `backend`, `contracts`, `db`, `claims`,
`frontend`, `container-config`, `container-core`, `container-gateway`,
`container-smoke`, `relay-container`, `sync-lifecycle-db`. Число обязательных
ревью — 0 (соло-аккаунт). Это не закрытие гейтов I/J/K.

| Есть | Нет (не строить процесс вокруг этого) |
|---|---|
| Issues, PR, labels, milestones, ruleset `main-pr-and-ci` | Путать ruleset с закрытием гейтов I/J/K |
| Sub-issues (`gh issue edit --add-sub-issue`) | Обязательные ревьюеры, CODEOWNERS как enforcement |
| Issue dependencies (`--add-blocked-by`) | Несколько assignees на issue/PR |
| Actions ~2000 мин/мес | Wiki, private Pages |
| `gh agent-task` (Copilot cloud) | Merge queue без protection |
| `.github/copilot-instructions.md` | Discussions (**выключены** — не включать) |

SOTA 2026: иерархия issue, `blocked-by`, JSON `gh issue view --json
parent,subIssues,blockedBy,blocking`, `.github/copilot-instructions.md`,
`AGENTS.md`, custom agents `.github/agents/*.agent.md`, запуск облака
через `gh agent-task create` и `gh issue edit N --add-assignee @copilot`.

**Не** плодить второй канал (Discussions, Wiki, Project как
единственный статус, IssueOps-бот). JSON в комментарии дешевле.

---

## Четыре слоя (не смешивать)

1. **Git `main`** — истина кода и инвариантов. Handoff-файлы живут здесь.
2. **Issue** — очередь и почтовый ящик. Статус, claim, blocked, handoff — только сюда.
3. **Pull request** — единственная мутация кода. CI и ревю — здесь.
4. **Checks** — арбитр. Красный PR не мержить. Зелёный ≠ «можно закрыть гейт I/J».

Облачный Copilot **не видит** `files/`. PDF конкурсного
комплекта, объект 10, TRAIN_PUBLIC zip — только локальная машина.

---

## Читать при входе (90 секунд)

```text
git fetch origin && git checkout main && git pull --ff-only
gh issue list --search "label:contest-p0 is:open" --limit 20
gh issue view N --json title,labels,parent,subIssues,blockedBy,blocking,comments
```

Потом: этот файл → `AGENTS.md` → `docs/AGENT_HANDOFF.md` →
`data/dataset/agent_handoff.json` → тело issue `N`.
**Не начинать работу, пока не выполнен claim.**

Issue [#86](https://github.com/KonkovDV/Kontur/issues/86) и
[`GH_SITUATION_2026_09_21.md`](GH_SITUATION_2026_09_21.md) — снимок
**21.09** (29 executable / 103 extractor_missing). Текущая разбивка —
только `data/matrix/coverage_snapshot.json` и `coverage_counts` в
`agent_handoff.json` (на 23.09: 44 / 83 / 1 / 4).

Проверка свежести контекста (защита от context drift):

```text
git rev-parse HEAD
# Сравнить с export_git_sha в agent_handoff.json
# Если расходятся — перечитать AGENT_HANDOFF.md
```

Поиск свободной P0:

```text
gh issue list --search "label:contest-p0 is:open -label:claimed -label:frozen-infra"
```

---

## Протокол комментария `kontur.agent_bus.v2`

**v2 брать обратно-совместимым** с v1. v1 всё ещё валиден.
Новые поля v2: `ci_run_id`, `triage_state`, `test_quality_gate`.

Каждое служебное сообщение — **один** комментарий к issue с JSON-блоком.
Операции: `claim` | `heartbeat` | `blocked` | `handoff` | `steal` | `done`.

````markdown
### AGENT_BUS kontur.agent_bus.v2
```json
{
  "schema": "kontur.agent_bus.v2",
  "op": "claim",
  "issue": 76,
  "agent": "cursor-grok",
  "host": "local",
  "base_sha": "REPLACE_WITH_origin_main_sha",
  "branch": "feat/76-evidence-viewer",
  "until": "2026-09-24T14:00:00+03:00",
  "note": "две панели, без VLM",
  "triage_state": "83/83 extractor_missing разобраны, новых экстракторов не создавать"
}
```
````

````markdown
### AGENT_BUS kontur.agent_bus.v2
```json
{
  "schema": "kontur.agent_bus.v2",
  "op": "done",
  "issue": 76,
  "agent": "cursor-grok",
  "pr_url": "https://github.com/KonkovDV/Kontur/pull/98",
  "ci_run_id": "https://github.com/KonkovDV/Kontur/actions/runs/REAL_RUN_ID",
  "test_quality_gate": [
    "тесты вызывают реальные функции пайплайна, не mock",
    "нет pytest.skip = покрытия",
    "нет raw hashlib вместо file_sha256",
    "нет assert True или тривиальных assert"
  ],
  "sha": "MERGE_SHA",
  "note": "влит, закрываю issue"
}
```
````

### Правила

- **claim** — первый валидный JSON на открытом issue без метки `claimed`
  побеждает. **Сразу после:** `gh issue edit N --add-label claimed`,
  затем ещё раз прочитать комментарии. Если более ранний JSON с
  `op=claim` принадлежит другому `agent`, остановиться и не пушить.
  Повторное чтение только обнаруживает проигранную гонку, оно не
  делает запись атомарной. Ветка `feat/#N-slug` от `origin/main`.
  Draft PR — после первого push.
- **heartbeat** — не реже чем раз в 6 часов, пока нет зелёного PR.
- **steal** — только если нет heartbeat 6 ч **и** нет коммитов в ветке.
  Не force-push чужую ветку.
- **blocked** — `op=blocked`, `reason`, `gh issue edit N --add-blocked-by M`.
- **handoff** — SHA, URL PR, что сделано, что нет, следующая команда.
  Снять `claimed`.
- **done** — после merge в `main`. Закрывать issue только с
  `Closes #N` в PR **или** вручную. **`ci_run_id` обязателен** в v2.

### Определение «зелёный CI» (v2)

Ненулевой номер run ещё не прогон. Падения 23.09 имели обычный `databaseId`
и при этом `runner_id=0`, пустой `runner_name` и `steps=[]`.

CI на SHA зелёный, только если для job `backend` этого run:

1. `gh run view RUN_ID --json status,conclusion` → `completed` и `success`
2. у job: `runner_id` не 0, `runner_name` не пустой, `steps` не пустой

`runner_id=0` — раннер не назначался. Это не зелёный CI и не повод мержить.

---

## Качественный гейт тестов

Тест считается реальным если все следующие пункты выполняются:

| Проверка | Реальный тест | Фейк — запрещён |
|---|---|---|
| SHA-256 файла | `file_sha256()` из `kontur.infrastructure.pdfium_tokens` | `hashlib.sha256` вместо него, когда проверяется identity файла |
| Вложения PDF | не писать тест: пайплайн не читает `/EmbeddedFile` (GAP-EMB) | `FPDFDoc_GetAttachmentCount` и `pytest.skip`, если символа нет |
| Слой и растр | `assess_pdf_bytes()` | заголовок теста без вызова |
| Покрытие кейса | вызывается функция пайплайна (`evaluate_batch`, `extract_pdf_bytes`, `scan_tokens_for_injection`) | `pytest.skip` на пути assert |
| assert | оба текста, конкретное поле | `assert True`, `isinstance(bool)`, `a or b` когда достаточно одного |
| Overlay | два объекта в одной точке `(x, y)` и оба читаются | разные y или «хотя бы один» |
| Ротация | `page.set_rotation(90)` и `frame.rotate == 90`; нет метода — `pytest.skip` до assert | страница без rotate, тест всё равно зелёный |
| Инъекция в PDF | `stamp_pdf` из `backend/tests/pdf_fixtures.py`, фраза влезает в страницу 200×200 pt, затем `assert tokens` | длинная фраза даёт пустые токены и `is_clean=True` |

---

## Типичные сбои (60+ PR постмортем)

Этот раздел читать перед работой. Список собран по повторным PR.
Не каждый пункт случался трижды.

### Нарушения инвариантов

❌ `CONFIRMED_VIOLATION` от автомата или LLM. Автомат выдаёт только `CANDIDATE`.

❌ `ocr_text=AVAILABLE` без GOLD Wilson. Живой статус — `MEASURED`, пока нет n≥16 золотых строк.

❌ Monkeypatch `ProcessRecord` в import-time (PR #61). Не возвращать.

❌ Зашитые числа `29/103` в коде вместо инвариантов (все 5 ведёр = 132).

❌ `coverage: executable` для правила без работающего экстрактора.

❌ Overlay `annotated_documents` как источник скоринга.

❌ Не-gold `RD_ID_MIXED` как RD+ID.

### Протокол шины

❌ `runner_id=0` + `steps=[]` оценено как «CI зелёный». Смотреть фактический `run_id`.

❌ `Closes #N` в PR, где не все exit criteria закрыты. Использовать `Relates to #N`.

❌ Снять draft PR до живого CI-раннера.

❌ Попытка claim без повторного чтения комментариев (TOCTOU гонка).

### Триаж экстракторов

❌ Создавать новые экстракторы для `extractor_missing`. **Все 83 полностью
разобраны** по трём триаж-документам. Без новых
экстракторов (`geometry`, `object_counting`, `per_element_table`,
`semantic_candidate`) правила не переводить в `executable`.
См. `data/matrix/number_family_triage.json`,
`data/matrix/class_ladder_triage.json`, `data/matrix/family_triage.json`.

❌ Оценивать все правила семейства как `executable` потому, что
совпадает подпись параметра. Решение — по виду доказательства отдельно.

### Качество тестов

❌ `same_name`: raw `hashlib` вместо `file_sha256` + `UploadCandidate`.

❌ `wrong_text_layer`: нет `assess_pdf_bytes`, кириллица на Helvetica.

❌ `embedded`: `FPDFDoc_GetAttachmentCount` напрямую + `pytest.skip` = не покрытие.

❌ `overlay AND`: `assert x in tokens or y in tokens` — слабый assert.

❌ Длинная фраза на странице 200×200 pt (`stamp_pdf`) не влезает:
`flatten_tokens` пустой, сканер отвечает `is_clean=True`. Это не пойманная инъекция.

---

## Метки (маршрутизация)

| Метка | Смысл |
|---|---|
| `contest-p0` | Critical path к 29.09 |
| `contest-p1` | Можно, если P0 не простаивает |
| `claimed` | Есть живой claim |
| `needs-local-files` | Нужен `files/` — только локальный агент |
| `cloud-ok` | Можно `gh agent-task` / `@copilot` |
| `frozen-infra` | Не брать до подачи |
| `do-not-merge` | Ветка/PR есть, в `main` нельзя |
| `agent-bus` | Служебное (эпик, срез, сам протокол) |
| `handoff` | Снимок ситуации, не единица работы |

---

## DAG до подачи (срез 23.09.2026)

Эпик (parent): [#87](https://github.com/KonkovDV/Kontur/issues/87).

| Issue | Статус на 23.09 | Не делать |
|---|---|---|
| [#75](https://github.com/KonkovDV/Kontur/issues/75) E2E пяти правил | на `main`, PR #88 | не открывать заново |
| [#76](https://github.com/KonkovDV/Kontur/issues/76) evidence UI | на `main`, PR #98 | не открывать заново |
| [#78](https://github.com/KonkovDV/Kontur/issues/78) demo/Compose | на `main`, PR #96 | не открывать заново |
| [#79](https://github.com/KonkovDV/Kontur/issues/79) submission pack | на `main`, PR #97 | не открывать заново |
| [#82](https://github.com/KonkovDV/Kontur/issues/82) family extractors | триаж на `main`, PR #99/#100/#103/#106/#107 | не красить семейство целиком в `executable` |
| [#77](https://github.com/KonkovDV/Kontur/issues/77) Gate K | открыт, P0, нужен человек и `files/` | не закрывать рекордером |
| [#80](https://github.com/KonkovDV/Kontur/issues/80) adversarial PDF | пакет влит в #128, issue открыт | не `Closes`: нет skew, OCR, VLM, system prompt, вложений |
| [#83](https://github.com/KonkovDV/Kontur/issues/83) GAP-SPLIT | открыт, после RC freeze | не заменять `NotImplementedError` заглушкой `evidence_group_id`; `source_id` — file_id эталона |
| [#84](https://github.com/KonkovDV/Kontur/issues/84) VLM isolation | открыт | сканер вызывается из `_pages_from_blobs` и пишет `injection_clean`; статус находки не меняется; #84 не закрывать без VLM и запрета класть текст страницы в system prompt |
| [#81](https://github.com/KonkovDV/Kontur/issues/81) branch protection | ruleset закрывает критерий issue | не считать это закрытием гейтов I/J/K |
| [#86](https://github.com/KonkovDV/Kontur/issues/86) срез 21.09 | исторический, 29/103 | не брать оттуда текущее покрытие |
| Dependabot | #116 и #117 закрыты, диапазоны версий шлюза на `main` | не P0; `runner_id=0` — не прогон |

**#77** разблокирован: #76 и #78 уже на `main`. Стартовать может только локальный агент с `files/` и живыми сессиями.
**#83 не параллелить с работой до RC freeze.**
Двух агентов на одном номере не ставить.

---

## Облачный Copilot vs локальный Cursor

Custom agents в репозитории:

- `.github/agents/contest-slice.agent.md` — имплементер.
- `.github/agents/invariant-reviewer.agent.md` — ревьюер, не impl.
- `.github/copilot-instructions.md` — глобальные инструкции.

Запуск облака (человеком или оркестратором, не каждым воркером):

```text
gh agent-task create -F - --custom-agent contest-slice --base main
# stdin: текст issue + «не трогать files/, не писать CONFIRMED_VIOLATION»

gh issue edit 80 --add-assignee "@copilot"
```

Назначение `@copilot` **сразу** открывает PR.
Комментарии после assign облако **не** видит — steer в PR.

**Не назначать** Copilot на: 77 (локальные сессии), 81,
любой `frozen-infra`, 85 Dependabot.

`gh skill` **не** ставить из чужих репо: риск prompt-инъекции.

---

## PR

Шаблон: `.github/pull_request_template.md`.

- Заголовок: `feat(#N): …` / `fix(#N): …` / `docs: …`
- `Closes #N` — только когда **все** exit criteria закрыты.
  Иначе — `Relates to #N`.
- Draft, пока CI не зелёный (настоящий `run_id`, не `runner_id=0`).
- **Не мержить:** красный CI; OCR-хвосты `16f3a06`/`2ddc2b3`;
  #85; `CONFIRMED_VIOLATION` от автомата/LLM; «закрытие» I/J по SILVER;
  фейковые тесты (pytest.skip = покрытие).
- Ревью-агент пишет review comments, не создаёт impl-PR.

---

## Команды оркестратора

```text
gh issue create --title "…" --label "contest-p0,cloud-ok,agent-bus" --parent 87
gh issue edit 87 --add-sub-issue 75,76,78
gh issue edit 77 --add-blocked-by 76 --add-blocked-by 78
gh issue edit 79 --add-blocked-by 75
gh issue list --search "label:claimed is:open"
gh pr list --search "is:draft"
gh run list --branch main --limit 5
# Валидация CI-прогона:
gh run view RUN_ID --json status,conclusion,workflowName
```

После merge в `main`: handoff-комментарий и снять `claimed`. Не закрывать эпик,
пока P0 открыты. `export_agent_dumps.py` — по календарю 28.09, не после каждого PR.

---

## Что сознательно не используем до 29.09

- Discussions, Wiki, Projects v2 как единственный статус.
- IssueOps Actions (`issue_comment` → /claim).
- Авто-assign Copilot на все P0.
- Branch protection «на удачу». Ruleset `main-pr-and-ci` (id 23890545) уже
  активен; #81 закрыт по критерию ветки, не по гейту.

---

## Уроки Red Team 23.09

Не переносить эти ошибки в следующий слайс.

1. «Последний файл стадии» ≠ голова редакции. Сравнивать `resolve_revision`.
   Устаревший том с явным successor не эталон. Не угадывать successor по «ред. N»
   и не по порядку загрузки. Живой комплект: `GET /documents` после
   `select_revision` — `CURRENT`/`SUPERSEDED` по выбору инспектора, не upload.
2. Разные шифры одной стадии — не одна цепочка и не конфликт всего комплекта.
   Группировать `resolve_heads_by_identity`. Правило берёт документ раздела
   (`document_kind` / `section`), а не чужой том. Конфликт своего шифра не
   прятать за единственной головой чужого раздела.
3. Выбор инспектора не перекрывает «не утв.» и не помечает чужой шифр
   `SUPERSEDED`.
4. Живой экран без массового confirm. Рекордер Gate K пишет локальный JSON и
   не вызывает API рецензии — это не «массового подтверждения нет» вообще.
   Скачать протокол: `READY` → `verify` → `complete` → `finalize`. Прямой
   `complete` из `READY` — 409. Журнал — `GET /audit`, не только клики рекордера.
   Карточка PZ-001: PNG и polygon ПД/РД; пустая ИД — нет фрагмента. «Не утв.»
   кнопкой эталона не перекрывается. #80 закрыт; VLM остаётся в #84.
5. `runner_id=0` и пустые `steps` — не зелёный CI.
6. Не писать «main без ruleset / GitHub Free private / API 403», если
   `main-pr-and-ci` активен. Не закрывать гейты I/J/K/L ruleset'ом.
7. Не оставлять в шине «draft #115» и открытые Dependabot #116/#117 после
   влития #128. Adversarial-пакет не закрывает #80.
8. Не угадывать порядок редакций по «ред. 1 / ред. 2» без successor.
   Не угадывать, что голое число `1200` — миллиметры: перевод мм→м только
   при явном суффиксе. Площадь (`мм²`, `500×300`) не масштабировать как длину.
9. Не перекрашивать 83 `extractor_missing`. Не ставить `ocr_text=AVAILABLE`.
10. `export_agent_dumps.py` не гонять до 28.09; `export_git_sha` отстаёт нарочно.
    Не править руками `train_public_engineering.json`.

---

## Запреты (шина не отменяет продукт)

Автомат и LLM не пишут `CONFIRMED_VIOLATION`. Overlay нормы не вердикт матрицы.
`AUTO_NO_DIFFERENCE` не на проводе ТЗ. TEST_HIDDEN не открывать.
Не закрывать I/J по SILVER, n=6, n=15. Confirm брокера ≠ `SYNCED`.
Не наращивать OIDC/TLS/RabbitMQ 4.x/observability/УКЭП вместо среза.
Не считать две головы разных шифров конфликтом стадии. Не считать рекордер
Gate K живым API рецензии.
