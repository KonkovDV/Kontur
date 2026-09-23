# Copilot — Контур

Приватное конкурсное репо. Дедлайн 2026-09-29 23:59 МСК.
Продукт: сверка ПД/РД/ИД по 132 параметрам (задача №9, Мосгосстройнадзор).
UI: «Инспектор ИИ».

## Порядок чтения при входе

1. `AGENTS.md` — 14 инвариантов.
2. `docs/GH_AGENT_BUS.md` — claim-протокол v2, DAG, anti-patterns, test quality gate.
3. `docs/AGENT_HANDOFF.md` — срез 23.09.2026.
4. `data/dataset/agent_handoff.json` — гейты, `draft_prs`, `extractor_triage_complete`.
5. Тело issue — после claim.

## Всегда

- Один GitHub issue на одно изменение. Claim (`kontur.agent_bus.v2`) до правок.
  **Сразу после claim: перечитать комментарии issue ещё раз.**
  Убедиться, что agent = ваш ID (защита от TOCTOU-гонки).
- Контракт первичен: `contracts/` → схемы → код → тесты.
- Правила матрицы — данные в `data/matrix/`, не Python-ветви.
- Автомат и LLM не пишут `finding_status=CONFIRMED_VIOLATION`.
- Не открывать TEST_HIDDEN / `РАЗМЕЧЕННЫЙ_TEST__213` / Речников для порогов.
- Не мержить OCR-хвосты (`feat/ocr-gate-i-crop3x-oem1`, `2ddc2b3`).
- Не добавлять OIDC, TLS, RabbitMQ 4.x, observability, УКЭП,
  РиН без sandbox-контракта. Только конкурсный вертикальный срез.
- `files/` в gitignore. Облачные агенты не видят PDF. Пропускать `needs-local-files`.
- Overlay / `annotated_documents` — не источник скоринга.
- Не угадывать `RD_ID_MIXED` как RD+ID.
- `scripts/check_claims.py` должен проходить в 0.

## Триаж extractor_missing: барьер

**Все 83 `extractor_missing` полностью разобраны** по трём
триаж-документам. Без новых экстракторов (`geometry`,
`object_counting`, `per_element_table`, `semantic_candidate`) не
переводить правила в `executable`. См.:
`data/matrix/number_family_triage.json`,
`data/matrix/class_ladder_triage.json`,
`data/matrix/family_triage.json`.

## Качество тестов (60+ PR постмортем)

Тест реальный, если **все** из следующих:

- вызывает реальные функции пайплайна: `file_sha256`, `assess_pdf_bytes`,
  `evaluate_batch`, `flatten_tokens` ит.д., не mock
- `pytest.skip` не используется внутри ветви покрытия
- raw `hashlib` не заменяет `file_sha256()` из `intake.py`
- assert конкретен: `and`, не `or`; не `assert True`
- overlay: два объекта на одной y; ротация: PDF с `Rotate: 90`;
  сканер: через `create_scanner_pdf()`
- промпт-инъекция < 200 символов

## CI green — определение

`runner_id=0` + `steps=[]` **не CI**. Зелёный CI:

```text
gh run view RUN_ID --json status,conclusion,workflowName
# status=completed, conclusion=success, RUN_ID != 0
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
GHA k6 p95 не production SLA. Статичные JWT-ключи не OIDC.

## Структура

`backend/` Python ≭3.11, `gateway/` Node BFF, `web/` React inspector shell,
`data/` matrix и dumps, `docs/adr/` решения.
Предпочитать векторный текст перед OCR.
`coverage: executable` — только при работающем экстракторе.
`backend/tests/adversarial/` — adversarial-тесты (#80, draft PR #115,
ветка `feat/adversarial-pdf-pack`, HEAD `7ec43b7`).
