# Copilot — Контур

Private contest repo. Deadline 2026-09-29 23:59 MSK. Product: PD/RD/ID
reconciliation for Mosgosstroynadzor task 10. UI name «Инспектор ИИ».

Read first: `AGENTS.md`, `docs/GH_AGENT_BUS.md`, `docs/GH_SITUATION_2026_09_21.md`,
`data/dataset/agent_handoff.json`. Do not invent a second process.

## Always

- One GitHub issue per change. Claim it (`kontur.agent_bus.v1`) before editing.
- Contract first: `contracts/` → schemas → code → tests.
- Matrix rules live in `data/matrix/`, not in Python branches.
- Automata and models never write `finding_status=CONFIRMED_VIOLATION`.
- Do not open TEST_HIDDEN / `РАЗМЕЧЕННЫЙ_TEST__213` / Rechnikov for thresholds.
- Do not merge leftover OCR (`feat/ocr-gate-i-crop3x-oem1`, `2ddc2b3`).
- Do not add OIDC, TLS termination, RabbitMQ 4.x, observability, УКЭП, or
  Rin without a sandbox contract. Contest vertical slice only.
- `files/` is gitignored. Cloud agents cannot see contest PDFs. Skip issues
  labeled `needs-local-files`.
- Overlay / `annotated_documents` is not a scoring source. Do not guess
  non-gold `RD_ID_MIXED`.
- Never publish acceptance metrics as achieved. `scripts/check_claims.py` must pass.

## Validate

```text
python -m pytest backend/tests -q
python scripts/check_claims.py
python scripts/check_contracts.py
```

Windows has no `make`. JWT tests use `KONTUR_ALLOW_INSECURE_DEV_AUTH` in
`backend/tests/conftest.py`.

CI: `.github/workflows/ci.yml` plus `relay.yml`, `sync-lifecycle.yml`, `gate-l.yml`.
Do not treat GHA k6 p95 as production SLA. Do not treat JWT static keys as OIDC.

## Layout

`backend/` Python ≥3.11, `gateway/` Node BFF, `web/` React inspector shell,
`data/` matrix and dumps, `docs/adr/` decisions. Prefer vector text over OCR.
`coverage: executable` only when an extractor exists.
