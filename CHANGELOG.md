# Changelog

## Unreleased

### Deprecated

- `finding.schema.json`: находка без `normative_refs` или без `evidence_group_id`.
  Сейчас оба поля необязательны, и контракт до демо 30.10 не меняется. После демо они станут
  обязательными для находок со статусами, требующими доказательства; изменение выйдет отдельным
  PR с записью в этом файле. Сколько правил и находок пока без этих полей, показывает
  предупреждение CI `scripts/report_traceability_gaps.py` (см. `docs/FINDING_FIELDS.md`).
