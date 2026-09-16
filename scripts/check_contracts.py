"""Контракты разбираются и согласованы между собой.

Два провода статусов сверяются раздельно (ADR-0005):
процесс п. 9.1 и протокол п. 9.3. Комплектность на проводе — с префиксом стадии.
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
from kontur.application.intake import (  # noqa: E402
    EXTRA_REJECTION_CODES,
    TZ_REJECTION_CODES,
    RejectionReason,
)
from kontur.domain.models import DocStage  # noqa: E402
from kontur.domain.status_map import PROTOCOL_STATUS, tz_upload_status  # noqa: E402
from kontur.domain.statuses import (  # noqa: E402
    WIRE_FINDING_STATUSES,
    Completeness,
    FindingStatus,
    ProcessState,
    ReasonCode,
    Scenario,
    SyncState,
)
from kontur.presentation.rbac import REQUIRED_ROLES  # noqa: E402

#: HTTP-методы, которые в этой спецификации могут нести операцию.
METHODS = frozenset({"get", "post", "put", "patch", "delete"})


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
    completeness = process_props["completeness"]["properties"]

    pairs = [
        ("ProcessStatus.process_state", process_props["process_state"]["enum"], ProcessState),
        ("ProcessStatus.scenario", process_props["scenario"]["enum"], Scenario),
        ("SyncState", components["SyncState"]["enum"], SyncState),
        ("ReviewDecision.reason_code", review_props["reason_code"]["enum"], ReasonCode),
    ]
    for name, contract_values, enum in pairs:
        if set(contract_values) != {member.value for member in enum}:
            problems.append(f"{name}: контракт и домен расходятся")

    for stage, key in ((DocStage.PD, "pd"), (DocStage.RD, "rd"), (DocStage.ID, "id")):
        expected = {tz_upload_status(stage, state) for state in Completeness}
        if set(completeness[key]["enum"]) != expected:
            problems.append(f"completeness.{key}: не совпадает с tz_upload_status")

    if set(process_props["protocol_status"]["enum"]) != set(PROTOCOL_STATUS.values()):
        problems.append("protocol_status: не совпадает с PROTOCOL_STATUS")

    if FindingStatus.AUTO_NO_DIFFERENCE in WIRE_FINDING_STATUSES:
        problems.append("AUTO_NO_DIFFERENCE не должен быть на проводе ТЗ")

    protocol_schema = json.loads((SCHEMAS / "protocol.schema.json").read_text(encoding="utf-8"))
    if set(protocol_schema["properties"]["status"]["enum"]) != set(PROTOCOL_STATUS.values()):
        problems.append("protocol.schema.json status: расходится с проекцией п. 9.3")

    finding_schema = json.loads((SCHEMAS / "finding.schema.json").read_text(encoding="utf-8"))
    contract_statuses = set(finding_schema["properties"]["finding_status"]["enum"])
    if contract_statuses != {member.value for member in FindingStatus}:
        problems.append("finding_status: контракт и домен расходятся")

    actions = set(review_props["action"]["enum"])
    if actions != {"CONFIRM", "REJECT", "REQUEST_CLARIFICATION"}:
        problems.append("ReviewDecision.action: SPLIT не должен быть атомарным действием")
    if "comment" not in components["ReviewDecision"].get("required", []):
        problems.append("ReviewDecision.comment обязателен по п. 9.3")
    finalize = spec["paths"]["/processes/{process_id}/finalize"]["post"]
    if "requestBody" not in finalize:
        problems.append("finalize без inspector_id в теле запроса")
    if "/processes/{process_id}/unfinalize" not in spec["paths"]:
        problems.append("нет POST unfinalize")

    rejection_enum = set(components["RejectionReason"]["properties"]["reason_code"]["enum"])
    if rejection_enum != {member.value for member in RejectionReason}:
        problems.append("RejectionReason: контракт и application.intake расходятся")
    if not TZ_REJECTION_CODES <= rejection_enum:
        problems.append("RejectionReason: потерян код отказа из ТЗ п. 9.1")
    if not EXTRA_REJECTION_CODES <= rejection_enum:
        problems.append("RejectionReason: расширение кодов не объявлено в контракте")

    if not spec.get("security"):
        problems.append("нет глобального security: ТЗ п. 12 требует аутентификации")
    if "bearerAuth" not in spec["components"].get("securitySchemes", {}):
        problems.append("нет securitySchemes.bearerAuth: чем подписан запрос — не описано")

    operations: dict[str, dict[str, object]] = {}
    for path, item in spec["paths"].items():
        for method, operation in item.items():
            if method not in METHODS:
                continue
            operation_id = operation.get("operationId")
            if operation_id is None:
                problems.append(f"{method.upper()} {path}: нет operationId")
                continue
            operations[operation_id] = operation
            responses = operation.get("responses", {})
            for code in ("401", "403"):
                if code not in responses:
                    problems.append(f"{operation_id}: нет ответа {code} (ТЗ п. 12)")
            declared = operation.get("x-required-roles")
            if not declared:
                problems.append(f"{operation_id}: не заданы x-required-roles")
                continue
            expected = REQUIRED_ROLES.get(operation_id)
            if expected is None:
                problems.append(f"{operation_id}: операции нет в rbac.REQUIRED_ROLES")
            elif set(declared) != {role.value for role in expected}:
                problems.append(f"{operation_id}: роли контракта и rbac расходятся")
    orphans = sorted(set(REQUIRED_ROLES) - set(operations))
    if orphans:
        problems.append(f"матрица прав описывает несуществующие операции: {', '.join(orphans)}")

    title = spec["info"]["title"]
    if title != "Инспектор ИИ":
        problems.append(f"OpenAPI title: {title!r}, ожидается «Инспектор ИИ»")

    for problem in problems:
        print(problem)
    if problems:
        return 1
    print("contracts: схемы валидны, два провода статусов согласованы")
    return 0


if __name__ == "__main__":
    sys.exit(main())
