## Summary

Relates to #

-

## Agent bus

- [ ] Issue claimed (`kontur.agent_bus.v2`) before this branch
- [ ] One PR for that issue; no concurrent PR from another agent
- [ ] Host matches labels (`cloud-ok` vs `needs-local-files`)
- [ ] TOCTOU check: re-read issue comments after claim; no earlier claim from another agent

## Invariants (AGENTS.md 1–14)

- [ ] Автомат/LLM не пишет `CONFIRMED_VIOLATION`
- [ ] Предметные находки с evidence (или `MISSING_EVIDENCE` / `NOT_APPLICABLE`)
- [ ] Нет TEST_HIDDEN / Речников для порогов
- [ ] Нет production-инфры вместо конкурсного среза
- [ ] `coverage: executable` только при работающем экстракторе; Gate L не закрыт (k6 GHA ≠ production SLA)
- [ ] `scripts/check_claims.py` и релевантные pytest зелёные

## Path grounding (lesson from PR #118)

For every new import path or function name in this PR:

- [ ] Verified via `search_code` or `get_file_contents` that the symbol
  exists at the stated path **before** writing it
- [ ] No reference to `create_scanner_pdf()` — it does not exist
- [ ] `file_sha256` imported from `kontur.infrastructure.pdfium_tokens`,
  not from `intake` or any other module

## Test quality

For every new test function:

- [ ] Calls real pipeline function (no mock, no raw `hashlib`)
- [ ] No `pytest.skip` on the assertion path
- [ ] No `FPDFDoc_GetAttachmentCount` (GAP-EMB; skip at top with reason or omit)
- [ ] Assertions are specific (`assert a and b`, not `assert True` or `a or b`)
- [ ] Overlay: both objects at same `(x, y)`; rotation: `page.set_rotation(90)`
- [ ] Injection phrase fits 200×200 pt page before `assert tokens`

## CI verification

- [ ] `gh run view RUN_ID --json status,conclusion` → `completed` + `success`
- [ ] `backend` job: `runner_id != 0`, `runner_name` not empty, `steps` not empty
- [ ] `ci_run_id` URL recorded in `op=done` agent-bus comment
- [ ] Draft PR stays draft until the above passes

## Merge

Не мержить если: CI красный; OCR-хвост; Dependabot; PR «закрывает»
гейт I/J без Wilson на held-out val; `CONFIRMED_VIOLATION` от автомата/LLM;
фейковые тесты (`pytest.skip` = покрытие); path без grounding-проверки.
