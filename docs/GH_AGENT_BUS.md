# Шина агентов через GitHub

Как разным ИИ (Cursor, Copilot cloud, Copilot CLI, любой clone с `gh`)
согласовывать работу до **29.09.2026 23:59 МСК** без потери контекста
и без гонок на одном issue.

Не frozen val, не закрытие гейтов I/J/K, не заявление, что вся матрица
executable. Инварианты — [`../AGENTS.md`](../AGENTS.md). Срез —
[`GH_SITUATION_2026_09_21.md`](GH_SITUATION_2026_09_21.md).

## Зачем так, а не «чат в комментариях»

GitHub Free **private** на этом репозитории:

| Есть | Нет (не строить процесс вокруг этого) |
|---|---|
| Issues, PR, labels, milestones | Branch protection / rulesets (API 403, [#81](https://github.com/KonkovDV/Kontur/issues/81)) |
| Sub-issues (parent/child, `gh issue edit --add-sub-issue`) | Обязательные ревьюеры, CODEOWNERS как enforcement |
| Issue dependencies (`--add-blocked-by` / `--add-blocking`) | Несколько assignees на issue/PR |
| Projects включены как флаг репо | Wiki, private Pages |
| Actions ~2000 мин/мес | Discussions (сейчас **выключены** — не включать) |
| `gh agent-task` (Copilot cloud, preview) | Merge queue без protection |

SOTA на 2026 (документация GitHub + CLI 2.94+/2.96): иерархия issue,
`blocked-by`, JSON `gh issue view --json parent,subIssues,blockedBy,blocking`,
`.github/copilot-instructions.md`, `AGENTS.md`, custom agents
`.github/agents/*.agent.md`, запуск облака через `gh agent-task create`
и `gh issue edit N --add-assignee @copilot`.

Этого достаточно. **Не** плодить второй канал (Discussions, Wiki, Project
как единственный статус, IssueOps-бот на `issue_comment`). Минуты Actions
уже ест CI; бот «/claim» сжигает квоту и дублирует комментарий.

## Четыре слоя (не смешивать)

1. **Git `main`** — истина кода и инвариантов. Handoff-файлы живут здесь,
   чтобы GH-only clone их видел.
2. **Issue** — очередь и почтовый ящик. Статус работы, claim, blocked,
   handoff — только сюда. Один issue = одна единица работы.
3. **Pull request** — единственная мутация кода. Ревью и CI — здесь.
   Не писать «я взял задачу» только в PR: следующий ИИ смотрит Issues.
4. **Checks** — арбитр. Красный PR не мержить. Зелёный ≠ «можно закрыть
   гейт I/J».

Облачный Copilot **не видит** `files/` (gitignore). PDF конкурсного
комплекта, объект 10, TRAIN_PUBLIC zip — только локальная машина.
Issue с меткой `needs-local-files` облаку не назначать.

## Читать при входе (90 секунд)

```text
git fetch origin && git checkout main && git pull --ff-only
gh issue list --search "label:contest-p0 is:open" --limit 20
gh issue view N --json title,labels,parent,subIssues,blockedBy,blocking,comments
```

Потом: этот файл → `AGENTS.md` → `docs/GH_SITUATION_2026_09_21.md` →
тело issue `N`. Не начинать работу, пока не выполнен **claim**.

Поиск свободной P0:

```text
gh issue list --search "label:contest-p0 is:open -label:claimed -label:frozen-infra is:unblocked"
```

`is:blocked` / `is:unblocked` — фильтры GitHub Issue Dependencies (GA, 2025).

## Протокол комментария `kontur.agent_bus.v1`

Каждое служебное сообщение — **один** комментарий к issue, с JSON-блоком.
Так любой агент парсит без NLP.

Операции: `claim` | `heartbeat` | `blocked` | `handoff` | `steal` | `done`.

````markdown
### AGENT_BUS kontur.agent_bus.v1
```json
{
  "schema": "kontur.agent_bus.v1",
  "op": "claim",
  "issue": 76,
  "agent": "cursor-grok",
  "host": "local",
  "base_sha": "REPLACE_WITH_origin_main_sha",
  "branch": "feat/76-evidence-viewer",
  "until": "2026-09-21T18:00:00+03:00",
  "note": "две панели, без VLM"
}
```
````

Правила:

- **claim** — первый валидный JSON на открытом issue без метки `claimed`
  побеждает. Сразу: `gh issue edit N --add-label claimed` и ветка
  `feat/#N-slug` от `origin/main`. Draft PR — после первого push.
- **heartbeat** — не реже чем раз в 6 часов, пока нет зелёного PR.
  Иначе claim считается протухшим.
- **steal** — только если нет heartbeat 6 ч **и** нет коммитов в ветке
  за это время. Комментарий `steal` + новый claim. Не force-push чужую ветку.
- **blocked** — `op=blocked`, поле `reason`, при необходимости
  `gh issue edit N --add-blocked-by M`. Метка `blocked` не дублирует
  native dependency: dependency первична.
- **handoff** — агент останавливается: SHA, URL PR, что сделано, что нет,
  следующая команда. Снять `claimed`, если работу не продолжает никто.
- **done** — после merge в `main`. Закрывать issue только с
  `Closes #N` в PR **или** вручную после проверки, что на `main` есть SHA.

Запрещено: второй параллельный PR на тот же issue; merge в `main` в обход
PR; force-push `main`; назначение `@copilot` на issue с
`needs-local-files` или `frozen-infra`.

## Метки (маршрутизация)

Free private не даёт нескольких assignees — метки заменяют «кто взял».

| Метка | Смысл |
|---|---|
| `contest-p0` | Critical path к 29.09 |
| `contest-p1` | Можно, если P0 не простаивает |
| `claimed` | Есть живой claim |
| `needs-local-files` | Нужен каталог `files/` — только локальный агент |
| `cloud-ok` | Можно `gh agent-task` / `@copilot` |
| `frozen-infra` | Не брать до подачи (OIDC/TLS/observability/УКЭП/РиН) |
| `do-not-merge` | Ветка/PR существует, в `main` нельзя |
| `agent-bus` | Служебное (эпик, срез, этот протокол) |
| `handoff` | Снимок ситуации, не единица работы |

## DAG до подачи

Эпик (parent): [#87](https://github.com/KonkovDV/Kontur/issues/87). Дети:

| Issue | Полоса | Где | blocked-by |
|---|---|---|---|
| [#75](https://github.com/KonkovDV/Kontur/issues/75) E2E пяти правил | P0 | local | — |
| [#76](https://github.com/KonkovDV/Kontur/issues/76) evidence UI | P0 | cloud-ok | — |
| [#78](https://github.com/KonkovDV/Kontur/issues/78) demo/Compose | P0 | local | — |
| [#77](https://github.com/KonkovDV/Kontur/issues/77) Gate K сессии | P0 | local+человек | 76, 78 |
| [#79](https://github.com/KonkovDV/Kontur/issues/79) submission pack | P0 | mix | 75 |
| [#80](https://github.com/KonkovDV/Kontur/issues/80) adversarial PDF | P1 | cloud-ok | — |
| [#82](https://github.com/KonkovDV/Kontur/issues/82) family extractors | P1 | cloud-ok | — |
| [#84](https://github.com/KonkovDV/Kontur/issues/84) изоляция VLM | P1 | cloud-ok | — |
| [#83](https://github.com/KonkovDV/Kontur/issues/83) GAP-SPLIT | не path | cloud-ok | — |
| [#81](https://github.com/KonkovDV/Kontur/issues/81) branch protection | человек / Pro | — | — |
| [#85](https://github.com/KonkovDV/Kontur/pull/85) Dependabot | `do-not-merge` | — | — |
| [#86](https://github.com/KonkovDV/Kontur/issues/86) срез | `handoff` | читать | не child эпика |

Параллелить безопасно: **76 ∥ 75 ∥ 78 ∥ 80**. Не параллелить двух агентов
на одном номере. [#77](https://github.com/KonkovDV/Kontur/issues/77) не
стартовать, пока UI и холодный Compose не на `main`.

## Облачный Copilot vs локальный Cursor

Custom agents в репозитории (после merge в default branch):

- `.github/agents/contest-slice.agent.md` — продуктовый срез, freeze инфры.
- `.github/agents/invariant-reviewer.agent.md` — ревью инвариантов, не impl.

Запуск облака **человеком или оркестратором**, не каждым воркером:

```text
gh agent-task create -F - --custom-agent contest-slice --base main
# stdin: текст issue + «не трогать files/, не писать CONFIRMED_VIOLATION»

gh issue edit 76 --add-assignee "@copilot"
```

Назначение `@copilot` **сразу** открывает PR (документация GitHub:
assign issue → always creates a pull request). Комментарии к issue
после assign облако **не** видит — steer в PR.

Не назначать Copilot на: 75, 77, 78 (локальные PDF/UI-сессии), 81, 85,
любой `frozen-infra`.

`gh skill` (preview) **не** ставить из чужих репозиториев без чтения
SKILL.md: риск промпт-инъекции в агента.

## PR

Шаблон: `.github/pull_request_template.md`.

- Заголовок: `feat(#76): …` / `fix(#N): …` / `docs: …`
- В теле: `Closes #N` только когда единица работы действительно закрыта.
  Иначе `Relates to #N`.
- Draft, пока CI не зелёный.
- Не мержить: красный CI; OCR-хвосты `16f3a06` / `2ddc2b3`; #85;
  PR, где автомат/LLM пишет `CONFIRMED_VIOLATION`; «закрытие» I/J по SILVER.
- Ревью-агент пишет **review comments**, не новый impl-PR.

На Free private нет required reviewers — зелёный CI не замена
`AGENTS.md`. Человек или invariant-reviewer смотрит инварианты 1–14.

## Что сознательно не используем до 29.09

- **Discussions** — второй inbox, агенты его пропускают.
- **Wiki** — нет на Free private; дубль git-доков.
- **Projects v2 как источник статуса** — `GITHUB_TOKEN` не ходит в Projects;
  нужен `project` scope. Labels + milestone + sub-issues достаточно.
- **IssueOps Actions** (`issue_comment` → /claim) — квота минут и ещё один
  parser. JSON в комментарии дешевле.
- **Авто-assign Copilot на все P0** — сломает локальные задачи и инварианты.
- **Включать branch protection «на удачу»** — уже 403; это #81, не critical path.

## Команды оркестратора

```text
gh issue create --title "…" --label "contest-p0,cloud-ok,agent-bus" --parent 87
gh issue edit 87 --add-sub-issue 75,76,78
gh issue edit 77 --add-blocked-by 76 --add-blocked-by 78
gh issue edit 79 --add-blocked-by 75
gh issue list --search "label:claimed is:open"
gh pr list --search "is:draft"
gh run list --branch main --limit 5
```

После merge в `main`: `python scripts/export_agent_dumps.py`, claim `done`,
снять `claimed`. Не закрывать эпик, пока P0 открыты.

## Запреты (шина не отменяет продукт)

Автомат и LLM не пишут `CONFIRMED_VIOLATION`. Overlay нормы не вердикт
матрицы. `AUTO_NO_DIFFERENCE` не на проводе ТЗ. TEST_HIDDEN не открывать.
Не закрывать I/J по SILVER, n=6, n=15. Confirm брокера ≠ `SYNCED`.
Не наращивать OIDC/TLS/RabbitMQ 4.x/observability/УКЭП вместо среза.
