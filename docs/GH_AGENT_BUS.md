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

GitHub Free **private** на этом репозитории:

| Есть | Нет (не строить процесс вокруг этого) |
|---|---|
| Issues, PR, labels, milestones | Branch protection / rulesets (API 403, [#81](https://github.com/KonkovDV/Kontur/issues/81)) |
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
  **перечитать комментарии issue ещё раз** и убедиться, что
  `agent` = ваш ID (защита от TOCTOU-гонки). Ветка `feat/#N-slug`
  от `origin/main`. Draft PR — после первого push.
- **heartbeat** — не реже чем раз в 6 часов, пока нет зелёного PR.
- **steal** — только если нет heartbeat 6 ч **и** нет коммитов в ветке.
  Не force-push чужую ветку.
- **blocked** — `op=blocked`, `reason`, `gh issue edit N --add-blocked-by M`.
- **handoff** — SHA, URL PR, что сделано, что нет, следующая команда.
  Снять `claimed`.
- **done** — после merge в `main`. Закрывать issue только с
  `Closes #N` в PR **или** вручную. **`ci_run_id` обязателен** в v2.

### Определение «зелёный CI» (v2)

CI считается зелёным если и только если:

1. `gh run view RUN_ID --json status,conclusion` → `status=completed`, `conclusion=success`
2. `RUN_ID != 0` (не плейсхолдер без runner)
3. `workflow` = `ci.yml` или полный прогон ci/relay/sync-lifecycle

`runner_id=0` с `steps=[]` — **не CI**. Не писать «CI зелёный» без проверки.

---

## Качественный гейт тестов

Тест считается реальным если все следующие пункты выполняются:

| Проверка | Реальный тест | Фейк — запрещен |
|---|---|---|
| SHA-256 файла | `file_sha256()` из `intake.py` | `hashlib.sha256(data).hexdigest()` напрямую |
| Вложения PDF | `FPDFDoc_GetAttachmentCount` через пайплайн | прямой вызов pdfium-символа |
| OCR расхождение | `assess_pdf_bytes()` | заголовок функции без вызова |
| Покрытие кейса | тест входит в ветвь пайплайна | `pytest.skip` внутри теста |
| assert поведение | конкретное условие (`and`, не `or`) | `assert result` или `assert True` |
| Точка overlay | два объекта на одной y | один объект на y=80, второй на y=120 |
| Ротация | pdf с 90° rotate, flatten_tokens изменяют y | обычный pdf без rotate |
| Сканер | фикстура создана через `create_scanner_pdf()` | любой другой путь |n| Длина фразы | короткая (влезает в bbox) | «ignore all rules and forget previous instructions» (>200 символов) |

---

## Типичные сбои (60+ PR постмортем)

Этот раздел **читать перед любой работой**. Каждый пункт воспроизводился ≥ 3 раз.

### Нарушения инвариантов

❌ `CONFIRMED_VIOLATION` от автомата или LLM. Автомат выдаёт только `CANDIDATE`.

❌ `ocr_text=AVAILABLE` без GOLD Wilson. Ставить только `UNAVAILABLE`, пока нет n≥16 золотых строк.

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

❌ Промпт-инъекция > 200 символов переполняет bbox, flatten_tokens = [].

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

| Issue | Тема | Статус | Где | blocked-by |
|---|---|---|---|---|
| [#75](https://github.com/KonkovDV/Kontur/issues/75) E2E пяти правил | **✅ landed** PR #88 | — | — | — |
| [#76](https://github.com/KonkovDV/Kontur/issues/76) evidence UI | **✅ landed** PR #98 | — | — | — |
| [#78](https://github.com/KonkovDV/Kontur/issues/78) demo/Compose | **✅ landed** PR #96 | — | — | — |
| [#79](https://github.com/KonkovDV/Kontur/issues/79) submission pack | **✅ landed** PR #97 | — | — | — |
| [#82](https://github.com/KonkovDV/Kontur/issues/82) family extractors | **✅ триаж завершён** PR #99/#100/#103/#106/#107 | — | — | — |
| [#77](https://github.com/KonkovDV/Kontur/issues/77) Gate K сессии | ⏳ открыт, P0 | local+человек | 76✅, 78✅ | — |
| [#80](https://github.com/KonkovDV/Kontur/issues/80) adversarial PDF | ⏸ draft PR #115 | cloud-ok | feat/adversarial-pdf-pack HEAD 7ec43b7 | — |
| [#83](https://github.com/KonkovDV/Kontur/issues/83) GAP-SPLIT | ⏳ открыт | cloud-ok | — | — |
| [#84](https://github.com/KonkovDV/Kontur/issues/84) VLM isolation | ⏳ открыт | cloud-ok | — | — |
| [#81](https://github.com/KonkovDV/Kontur/issues/81) branch protection | блок — Free/Pro | — | — | — |
| [#85](https://github.com/KonkovDV/Kontur/pull/85) Dependabot | `do-not-merge` | — | — | — |

**Блокировки #77:** разблокированы (#76 и #78 на main). Стартовать.
**Параллелить безопасно:** 77 (параллельно 80 и 83/84).
**Не параллелить** двух агентов на одном номере.

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

После merge в `main`: `python scripts/export_agent_dumps.py`, claim `done`,
снять `claimed`. Не закрывать эпик, пока P0 открыты.

---

## Что сознательно не используем до 29.09

- Discussions, Wiki, Projects v2 как единственный статус.
- IssueOps Actions (`issue_comment` → /claim).
- Авто-assign Copilot на все P0.
- Branch protection «на удачу» — API 403 (#81).

---

## Запреты (шина не отменяет продукт)

Автомат и LLM не пишут `CONFIRMED_VIOLATION`. Overlay нормы не вердикт матрицы.
`AUTO_NO_DIFFERENCE` не на проводе ТЗ. TEST_HIDDEN не открывать.
Не закрывать I/J по SILVER, n=6, n=15. Confirm брокера ≠ `SYNCED`.
Не наращивать OIDC/TLS/RabbitMQ 4.x/observability/УКЭП вместо среза.
