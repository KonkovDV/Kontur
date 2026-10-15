# Contributing to Kontur

## Workflow

- Code changes go to `main` only through a pull request. Never push to `main`.
- One PR = one finding. A review fix goes into the same PR's branch, not into a new PR stacked on top.
- No PR chains: every PR targets `main`. If work depends on an unmerged PR, wait or fold it into that PR.
- Authors do not merge their own PRs. Merge happens after an independent review and green CI.
- A red PR is not merged. "CI green" is not a claim that a TZ item is closed.
- Rebase on `origin/main` before asking for review; force-push only your own PR branch (`--force-with-lease`).

## Checks (same as `.github/workflows/ci.yml`)

```bash
pip install -e "backend[dev]"
ruff check backend scripts
mypy --strict backend/src
pytest backend/tests -q
python -m kontur.evaluation.build_gold --check
python scripts/check_contracts.py      # needs: pip install jsonschema pyyaml
python scripts/check_claims.py         # honesty of public wording

(cd gateway && npm ci && npm test)
(cd web && npm ci && npx tsc --noEmit && npm test)

docker compose config --quiet
docker compose -f docker-compose.yml -f docker-compose.offline.yml config --quiet
```

Postgres-backed checks (`check_protocol_concurrency.py`, `check_inbox.py`, `check_integrity_pg_live.py`)
run in CI jobs `db` / `sync-lifecycle-db`; locally they need `KONTUR_DB_URL` and the schema from
`backend/src/kontur/infrastructure/db/schema.sql`.

Shortcuts: `make lint`, `make types`, `make check`, `make test-fast`, `make test`.

## Prohibited

- Growing the parameter matrix beyond **59/132** with presence/enum stubs. Honesty over growth.
- Overclaiming: no "PRESENT", "closed", "exactly-once", "delivered" unless a test proves it. Use `partial`
  with a stated gap in `docs/TZ_TRACEABILITY.md` / `docs/TZ_GAP_CLOSURE.md`.
- Stacked PRs, self-merge, merging red CI.
- Generated-by trailers, tool or assistant names, emoji, people's names, and debug leftovers
  (`print`/`console.log`, commented-out code) in code, commits or PR text.
- Secrets in the repository.

## Task status protocol

Task status follows `aerobim.agent_bus.v1`
([GH_AGENT_BUS.md](https://github.com/KonkovDV/AeroBIM/blob/main/docs/GH_AGENT_BUS.md)), summarized in
[AGENTS.md](AGENTS.md).
