## Summary

Relates to #

- 

## Agent bus

- [ ] Issue claimed (`kontur.agent_bus.v1`) before this branch
- [ ] One PR for that issue
- [ ] Host matches labels (`cloud-ok` vs `needs-local-files`)

## Invariants

- [ ] Автомат/LLM не пишут `CONFIRMED_VIOLATION`
- [ ] Предметные находки с evidence (или `MISSING_EVIDENCE` / `NOT_APPLICABLE`)
- [ ] Нет TEST_HIDDEN / Речников для порогов
- [ ] Нет production-инфры вместо конкурсного среза
- [ ] `scripts/check_claims.py` и релевантные pytest зелёные

## Merge

Не мержить если CI красный, это OCR-хвост, Dependabot #85, или PR «закрывает»
гейт I/J без Wilson на held-out val.
