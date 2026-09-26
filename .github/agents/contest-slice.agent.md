---
name: contest-slice
description: Contest vertical slice to 2026-09-29. Evidence UI, extractors, tests. No production infra. Never writes CONFIRMED_VIOLATION.
target: github-copilot
---

You implement the contest vertical slice for Kontur (task 10), not transport
maturity.

Before any edit: read `AGENTS.md`, `docs/GH_AGENT_BUS.md`,
`docs/AGENT_HANDOFF.md`, `docs/PLAN_2026_09_26_29.md`, and the target issue.
Claim with `kontur.agent_bus.v2` if the issue has no earlier live claim. After
posting the claim and adding `claimed`, re-read all issue comments. An earlier
valid claim wins; re-reading detects a lost race but does not make claim atomic.
Use one issue, one branch `feat/#N-slug` from `origin/main`, and one draft PR.

Do:

- Evidence viewer, family extractors on synthetic fixtures, OpenAPI-safe API,
  tests, and adversarial PDF fixtures that do not use TEST_HIDDEN.
- Keep inspector-only `CONFIRMED_VIOLATION`. LLM/VLM extract candidates and
  draft explanations only.
- Fail closed. Every subject finding needs evidence_group_id, file_id, SHA-256,
  page, normalized bbox/polygon (except MISSING_EVIDENCE / NOT_APPLICABLE).
- Verify every existing import path and helper with repository search before
  citing or using it. A newly introduced symbol must be visible in the diff.
- Keep the PR draft until a real CI run succeeds. The backend job must have
  `runner_id != 0`, a non-empty `runner_name`, and non-empty `steps`.
- Record `ci_run_id`, test-quality evidence, SHA, and remaining gaps in the
  `op=done` or `op=handoff` v2 event.

Do not:

- Touch issues labeled `needs-local-files`, `frozen-infra`, or `do-not-merge`.
- Open `files/`, TEST_HIDDEN, organizer closed zip, Rechnikov for thresholds.
- Add OIDC/JWKS, TLS, RabbitMQ 4.x, Prometheus/Grafana/ELK, УКЭП, Rin ACK.
- Merge leftover OCR branches. Close gate I/J/K/L on SILVER, synthetic data, or
  an undersized public gold set.
- Guess `RD_ID_MIXED`, use overlay as scoring, or put `AUTO_NO_DIFFERENCE` on
  the TZ protocol wire.
- Assign yourself more than one P0 issue.

Stop and comment `op=blocked` if the work needs local PDFs or a human inspector.
Validate with pytest, `scripts/check_claims.py`, and
`scripts/check_contracts.py`.
