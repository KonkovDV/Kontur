"""Контракты разбираются и согласованы между собой.

Проверяется, что схемы валидны как JSON Schema, OpenAPI читается, а перечисления
статусов в контракте совпадают с доменом. Расхождение контракта и кода —
типовая причина того, что в протокол попадает статус, которого нет в машине
состояний.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMAS = ROOT / "contracts" / "schemas"
OPENAPI = ROOT / "contracts" / "openapi.yaml"

sys.path.insert(0, str(ROOT / "backend" / "src"))
from kontur.domain.statuses import (  # noqa: E402
    Completeness,
    FindingStatus,
    ProcessState,
    ReasonCode,
    Scenario,
    SyncState,
)


def main() -> int:
    problems: list[str] = []

    for path in sorted(SCHEMAS.glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
        except jsonschema.SchemaError as exc:
            problems.append(f"{path.name}: {exc.message}")

    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    components = spec["components"]["schemas"]

    process_props = components["ProcessStatus"]["properties"]
    review_props = components["ReviewDecision"]["properties"]
    pairs = [
        ("ProcessStatus.process_state", process_props["process_state"]["enum"], ProcessState),
        ("ProcessStatus.scenario", process_props["scenario"]["enum"], Scenario),
        ("CompletenessState", components["CompletenessState"]["enum"], Completeness),
        ("SyncState", components["SyncState"]["enum"], SyncState),
        ("ReviewDecision.reason_code", review_props["reason_code"]["enum"], ReasonCode),
    ]
    for name, contract_values, enum in pairs:
        if set(contract_values) != {member.value for member in enum}:
            problems.append(f"{name}: контракт и домен расходятся")

    finding_schema = json.loads((SCHEMAS / "finding.schema.json").read_text(encoding="utf-8"))
    contract_statuses = set(finding_schema["properties"]["finding_status"]["enum"])
    if contract_statuses != {member.value for member in FindingStatus}:
        problems.append("finding_status: контракт и домен расходятся")

    for problem in problems:
        print(problem)
    if problems:
        return 1
    print("contracts: схемы валидны, перечисления совпадают с доменом")
    return 0


if __name__ == "__main__":
    sys.exit(main())
