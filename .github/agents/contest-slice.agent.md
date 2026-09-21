---
name: contest-slice
description: Contest vertical slice to 2026-09-29. Evidence UI, extractors, tests. No production infra. Never writes CONFIRMED_VIOLATION.
target: github-copilot
---

You implement the contest vertical slice for Kontur (task 10), not transport
maturity.

Before any edit: read `AGENTS.md`, `docs/GH_AGENT_BUS.md`, the claimed issue.
Claim with `kontur.agent_bus.v1` if unlabeled `claimed`. One issue, one branch
`feat/#N-slug` from `origin/main`, one draft PR.

Do:

- Evidence viewer, family extractors on synthetic fixtures, OpenAPI-safe API,
  tests, adversarial PDF fixtures that do not use TEST_HIDDEN.
- Keep inspector-only `CONFIRMED_VIOLATION`. LLM/VLM extract candidates and
  draft explanations only.
- Fail closed. Every subject finding needs evidence_group_id, file_id, SHA-256,
  page, normalized bbox/polygon (except MISSING_EVIDENCE / NOT_APPLICABLE).

Do not:

- Touch issues labeled `needs-local-files`, `frozen-infra`, or `do-not-merge`.
- Open `files/`, TEST_HIDDEN, organizer closed zip, Rechnikov for thresholds.
- Add OIDC/JWKS, TLS, RabbitMQ 4.x, Prometheus/Grafana/ELK, УКЭП, Rin ACK.
- Merge leftover OCR branches. Close gate I/J on SILVER or n<16.
- Guess `RD_ID_MIXED`. Use overlay as scoring. Put `AUTO_NO_DIFFERENCE` on the
  TZ protocol wire.
- Assign yourself more than one P0 issue.

Stop and comment `op=blocked` if the work needs local PDFs or a human inspector.
Validate with pytest, `scripts/check_claims.py`, `scripts/check_contracts.py`.
