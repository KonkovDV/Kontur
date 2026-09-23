# Copilot — Контур

Приватное конкурсное репо. Дедлайн 2026-09-29 23:59 МСК.
Продукт: сверка ПД/РД/ИД по 132 параметрам (задача №10, Мосгосстройнадзор).
UI: «Инспектор ИИ».

## Порядок чтения при входе

1. `AGENTS.md` — 14 инвариантов.
2. `docs/GH_AGENT_BUS.md` — claim-протокол v2, DAG, anti-patterns, test quality gate.
3. `docs/AGENT_HANDOFF.md` — срез 23.09.2026.
4. `data/dataset/agent_handoff.json` — гейты, `draft_prs`, `extractor_triage_complete`,
   `pr_118_lesson` (уроки по галлюцинациям).
5. Тело issue — после claim.

## Всегда

- Один GitHub issue на одно изменение. Claim (`kontur.agent_bus.v2`) до правок.
  **Сразу после claim: перечитать комментарии issue.**
  Если более ранний `op=claim` от другого `agent` — остановиться.
- Контракт первичен: `contracts/` → схемы → код → тесты.
- Правила матрицы — данные в `data/matrix/`, не Python-ветви.
- Автомат и LLM не пишут `finding_status=CONFIRMED_VIOLATION`.
- Не открывать TEST_HIDDEN / `РАЗМЕЧЕННЫЙ_TEST__213` / Речников для порогов.
- Не мержить OCR-хвосты (`feat/ocr-gate-i-crop3x-oem1`, `2ddc2b3`).
- Не добавлять OIDC, TLS, RabbitMQ 4.x, observability, УКЭП,
  РиН без sandbox-контракта.
- `files/` в gitignore. Облачные агенты не видят PDF. Пропускать `needs-local-files`.
- Overlay / `annotated_documents` — не источник скоринга.
- Не угадывать `RD_ID_MIXED` как RD+ID.
- `scripts/check_claims.py` должен проходить в 0.

## Path grounding — обязательно (PR #118)

**Никогда не писать import-путь или имя функции без проверки
через `search_code` / `get_file_contents`.**

Известные факты (проверены PR #118):

- `file_sha256()` — в `kontur.infrastructure.pdfium_tokens`, не в `intake`
- `create_scanner_pdf()` **не существует**
- Тест на вложения `/EmbeddedFile` не писать (GAP-EMB: пайплайн не читает их)
- `closes_gate_l = false`: k6 на GHA — инженерный замер, не закрытие гейта, не production SLA

## Триаж extractor_missing: барьер

**Все 83 `extractor_missing` полностью разобраны.** Без новых
экстракторов (`geometry`, `object_counting`, `per_element_table`,
`semantic_candidate`) не переводить правила в `executable`.

## Качество тестов (60+ PR постмортем)

Тест реальный, если **все**:

- вызывает реальные функции пайплайна: `file_sha256`, `assess_pdf_bytes`,
  `evaluate_batch`, `flatten_tokens` ит.д., не mock
- `pytest.skip` не на пути assert
- raw `hashlib` не заменяет `file_sha256()` из `kontur.infrastructure.pdfium_tokens`
- вложения `/EmbeddedFile` не покрывать `FPDFDoc_GetAttachmentCount` (GAP-EMB)
- assert конкретен: `and`, не `or`; не `assert True`
- overlay: два объекта в одной `(x, y)`; ротация: `page.set_rotation(90)` и `frame.rotate == 90`
- инъекция: `stamp_pdf` из `backend/tests/pdf_fixtures.py`, фраза влезает в 200×200 pt,
  затем `assert tokens`

## CI green — определение

`runner_id=0` и `steps=[]` — раннер не назначался. Зелёный CI:

```text
gh run view RUN_ID --json status,conclusion
# → status=completed, conclusion=success
# и job backend: runner_id != 0, runner_name не пустой, steps не []
```

Не снимать draft PR и не писать «CI зелёный» без этой проверки.

## Валидация

```text
python -m pytest backend/tests -q
python scripts/check_claims.py
python scripts/check_contracts.py
```

Windows: нет `make`. JWT тесты: `KONTUR_ALLOW_INSECURE_DEV_AUTH` в
`backend/tests/conftest.py`.

CI: `.github/workflows/ci.yml` + `relay.yml`, `sync-lifecycle.yml`, `gate-l.yml`.
GHA k6 p95 не production SLA и не закрытие Gate L (`closes_gate_l = false`).
Статичные JWT-ключи не OIDC.

## Структура

`backend/` Python ≭3.11, `gateway/` Node BFF, `web/` React inspector shell,
`data/` matrix и dumps, `docs/adr/` решения.
Предпочитать векторный текст перед OCR.
`coverage: executable` — только при работающем экстракторе.
`backend/tests/adversarial/` — adversarial-тесты (#80, draft PR #115,
ветка `feat/adversarial-pdf-pack`, HEAD `7ec43b7`).
