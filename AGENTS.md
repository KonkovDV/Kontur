# AGENTS.md

Rules for automated contributors working in this repository. Read [CONTRIBUTING.md](CONTRIBUTING.md) first;
everything there applies here too.

## Hard rules

1. Never merge. Open a PR against `main`, get CI green, request review.
2. One PR = one finding. No PR chains; every PR targets `main`. Review fixes go into the same branch.
3. Rule **59/132**: do not grow the matrix with presence/enum stubs. Honesty over growth; status `partial`
   with the gap named beats a closed-looking item.
4. Do not touch `main` directly. Force-push (`--force-with-lease`) only to the PR branch you own or were
   asked to rebase.
5. No generated-by trailers, tool names, emoji, people's names or debug leftovers in code, commits or PRs.
6. Respect HOLD markers on PRs (for example, a dependency bump held until after a demo).

## Checks before asking for review

```bash
ruff check backend scripts && mypy --strict backend/src && pytest backend/tests -q
python scripts/check_claims.py && python scripts/check_contracts.py
(cd gateway && npm test) && (cd web && npx tsc --noEmit && npm test)
```

## Task status: aerobim.agent_bus.v1

Full spec: [KonkovDV/AeroBIM docs/GH_AGENT_BUS.md](https://github.com/KonkovDV/AeroBIM/blob/main/docs/GH_AGENT_BUS.md).

- Queue = issues labeled `agent-bus`. Code = pull requests only. Status = one JSON comment per operation;
  no second status channel.
- Operations: `claim`, `heartbeat`, `blocked`, `handoff`, `steal`, `done`.
- `claim`: first valid claim on an open issue without the `claimed` label wins; add `claimed`, re-read
  comments, stop if an earlier claim by another agent exists. `base_sha` must equal `origin/main`.
- `heartbeat` at least every 6 hours until the PR is green. `blocked` names the reason and issue numbers.
- `handoff`: SHA, PR URL, done/remaining; remove `claimed`.
- `steal` only after 6 hours of silence and an empty branch (`ahead_by=0`).
- `done`: PR URL, CI run, merge SHA, test-quality notes.

Comment format:

````markdown
### AGENT_BUS aerobim.agent_bus.v1
```json
{"schema": "aerobim.agent_bus.v1", "op": "claim", "issue": 1, "agent": "session-id",
 "host": "cloud", "base_sha": "<origin/main sha>", "branch": "feat/1-short-name",
 "until": "2026-10-16T12:00:00+03:00"}
```
````
