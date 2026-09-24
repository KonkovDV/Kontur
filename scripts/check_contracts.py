"""Контракты разбираются и согласованы между собой.

Два провода статусов сверяются раздельно (ADR-0005):
процесс п. 9.1 и протокол п. 9.3. Комплектность на проводе — с префиксом стадии.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
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

#: Полный набор HTTP-методов операций OpenAPI 3.1.
OPERATION_METHODS = frozenset(
    {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
)
GLOBAL_SECURITY = [{"bearerAuth": []}]
PUBLIC_OPERATIONS = frozenset({"healthz"})
NON_OBJECT_PROTECTED_OPERATIONS = frozenset({"getSystemCapabilities"})
OBJECT_BOUND_OPERATIONS = frozenset(
    {
        "uploadDocuments",
        "getProcessStatus",
        "loadDemoKit",
        "getProcessDocuments",
        "listProcessFindings",
        "getFilePagePng",
        "getProtocol",
        "getProtocolDocx",
        "getProtocolXml",
        "getProtocolPdf",
        "getAuditLog",
        "getEvidenceCard",
        "reviewFinding",
        "startVerification",
        "completeVerification",
        "finalizeProtocol",
        "unfinalizeProtocol",
        "selectRevision",
        "syncInspection",
    }
)
UNAUTHORIZED_REF = {"$ref": "#/components/responses/Unauthorized"}
FORBIDDEN_REF = {"$ref": "#/components/responses/Forbidden"}
ERROR_RESPONSE_REF = "#/components/schemas/ErrorResponse"


def iter_operations(
    spec: dict[str, object],
) -> Iterator[tuple[str, str, dict[str, object]]]:
    """Обойти только операции, игнорируя метаданные Path Item."""

    paths = spec["paths"]
    assert isinstance(paths, dict)
    for path, item in paths.items():
        assert isinstance(path, str)
        assert isinstance(item, dict)
        for method, operation in item.items():
            if method not in OPERATION_METHODS:
                continue
            assert isinstance(operation, dict)
            yield path, method, operation


def validate_openapi(spec: dict[str, object]) -> list[str]:
    """Проверить OpenAPI и вернуть все найденные расхождения."""

    problems: list[str] = []
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

    actions = set(review_props["action"]["enum"])
    if actions != {"CONFIRM", "REJECT", "REQUEST_CLARIFICATION"}:
        problems.append(
            "ReviewDecision.action: SPLIT не должен быть атомарным действием"
        )
    if "comment" not in components["ReviewDecision"].get("required", []):
        problems.append("ReviewDecision.comment обязателен по п. 9.3")
    for path, label in (
        ("/processes/{process_id}/verify", "verify"),
        ("/processes/{process_id}/complete", "complete"),
        ("/processes/{process_id}/finalize", "finalize"),
        ("/processes/{process_id}/revisions/{file_id}/select", "select revision"),
    ):
        if path not in spec["paths"]:
            problems.append(f"нет POST {label}")
            continue
        operation = spec["paths"][path]["post"]
        if "requestBody" not in operation:
            problems.append(f"{label} без inspector_id в теле запроса")
    if "/processes/{process_id}/unfinalize" not in spec["paths"]:
        problems.append("нет POST unfinalize")
    pdf = spec["paths"]["/processes/{process_id}/protocol.pdf"]["get"]["responses"]
    if "200" not in pdf:
        problems.append("protocol.pdf: рабочий ответ должен быть 200, не 501")
    if "501" in pdf and "200" not in pdf:
        problems.append("protocol.pdf: 501 описан вместо рабочего PDF")

    rejection_enum = set(components["RejectionReason"]["properties"]["reason_code"]["enum"])
    if rejection_enum != {member.value for member in RejectionReason}:
        problems.append("RejectionReason: контракт и application.intake расходятся")
    if not TZ_REJECTION_CODES <= rejection_enum:
        problems.append("RejectionReason: потерян код отказа из ТЗ п. 9.1")
    if not EXTRA_REJECTION_CODES <= rejection_enum:
        problems.append("RejectionReason: расширение кодов не объявлено в контракте")

    if not spec.get("security"):
        problems.append("нет глобального security: ТЗ п. 12 требует аутентификации")
    if spec.get("security") != GLOBAL_SECURITY:
        problems.append("глобальный security должен быть ровно [{bearerAuth: []}]")

    security_schemes = spec["components"].get("securitySchemes", {})
    if "bearerAuth" not in security_schemes:
        problems.append("нет securitySchemes.bearerAuth: подпись запроса не описана")
    else:
        bearer = security_schemes["bearerAuth"]
        if bearer.get("type") != "http":
            problems.append("bearerAuth.type должен быть http")
        scheme = bearer.get("scheme")
        if not isinstance(scheme, str) or scheme.casefold() != "bearer":
            problems.append("bearerAuth.scheme должен быть bearer без учёта регистра")
        if bearer.get("bearerFormat") != "JWT":
            problems.append("bearerAuth.bearerFormat должен быть JWT")
        description = bearer.get("description", "")
        for token in ("RS256", "ES256", "object_id"):
            if token not in description:
                problems.append(f"bearerAuth.description не содержит {token}")

    operations: dict[str, dict[str, object]] = {}
    public_by_security: set[str] = set()
    for path, method, operation in iter_operations(spec):
        operation_id = operation.get("operationId")
        if operation_id is None:
            problems.append(f"{method.upper()} {path}: нет operationId")
            continue
        if operation_id in operations:
            problems.append(f"дубликат operationId: {operation_id}")
            continue
        operations[operation_id] = operation

        if operation.get("security") == []:
            public_by_security.add(operation_id)
            if operation.get("x-required-roles"):
                problems.append(
                    f"{operation_id}: публичная операция не должна задавать роли"
                )
            responses = operation.get("responses", {})
            if "401" in responses or "403" in responses:
                problems.append(f"{operation_id}: публичная операция не должна иметь 401/403")
            continue

        effective_security = operation.get("security", spec.get("security"))
        if effective_security != GLOBAL_SECURITY:
            problems.append(
                f"{operation_id}: effective security должен совпадать с глобальным"
            )
        responses = operation.get("responses", {})
        if responses.get("401") != UNAUTHORIZED_REF:
            problems.append(f"{operation_id}: ответ 401 должен ссылаться на Unauthorized")
        if responses.get("403") != FORBIDDEN_REF:
            problems.append(f"{operation_id}: ответ 403 должен ссылаться на Forbidden")
        declared = operation.get("x-required-roles")
        if not declared:
            problems.append(f"{operation_id}: не заданы x-required-roles")
            continue
        expected = REQUIRED_ROLES.get(operation_id)
        if expected is None:
            problems.append(f"{operation_id}: операции нет в rbac.REQUIRED_ROLES")
        elif set(declared) != {role.value for role in expected}:
            problems.append(f"{operation_id}: роли контракта и rbac расходятся")

    if public_by_security != PUBLIC_OPERATIONS:
        problems.append(
            "security: [] должна иметь ровно операция healthz, получено "
            f"{sorted(public_by_security)}"
        )

    expected_operations = (
        PUBLIC_OPERATIONS | NON_OBJECT_PROTECTED_OPERATIONS | OBJECT_BOUND_OPERATIONS
    )
    if set(operations) != expected_operations:
        missing = sorted(expected_operations - set(operations))
        extra = sorted(set(operations) - expected_operations)
        problems.append(f"operationId partition: отсутствуют {missing}, лишние {extra}")

    protected = set(operations) - PUBLIC_OPERATIONS
    if protected != set(REQUIRED_ROLES):
        missing = sorted(set(REQUIRED_ROLES) - protected)
        extra = sorted(protected - set(REQUIRED_ROLES))
        problems.append(f"protected operationId: отсутствуют {missing}, лишние {extra}")

    orphans = sorted(set(REQUIRED_ROLES) - set(operations))
    if orphans:
        problems.append(
            "матрица прав описывает несуществующие операции: " + ", ".join(orphans)
        )

    responses = spec["components"].get("responses", {})
    for name in ("Unauthorized", "Forbidden"):
        schema = (
            responses.get(name, {})
            .get("content", {})
            .get("application/json", {})
            .get("schema")
        )
        if schema != {"$ref": ERROR_RESPONSE_REF}:
            problems.append(f"components.responses.{name} должен ссылаться на ErrorResponse")

    error_response = components.get("ErrorResponse", {})
    if "detail" not in error_response.get("required", []):
        problems.append("ErrorResponse должен требовать detail")
    if error_response.get("properties", {}).get("detail") != {"type": "string"}:
        problems.append("ErrorResponse.detail должен иметь type string")
    if error_response.get("additionalProperties") is not False:
        problems.append("ErrorResponse.additionalProperties должен быть false")

    title = spec["info"]["title"]
    if title != "Инспектор ИИ":
        problems.append(f"OpenAPI title: {title!r}, ожидается «Инспектор ИИ»")

    return problems


def main() -> int:
    problems: list[str] = []

    for path in sorted(SCHEMAS.glob("*.json")):
        schema = json.loads(path.read_text(encoding="utf-8"))
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
        except jsonschema.SchemaError as exc:
            problems.append(f"{path.name}: {exc.message}")

    protocol_schema = json.loads((SCHEMAS / "protocol.schema.json").read_text(encoding="utf-8"))
    if set(protocol_schema["properties"]["status"]["enum"]) != set(PROTOCOL_STATUS.values()):
        problems.append("protocol.schema.json status: расходится с проекцией п. 9.3")

    finding_schema = json.loads((SCHEMAS / "finding.schema.json").read_text(encoding="utf-8"))
    contract_statuses = set(finding_schema["properties"]["finding_status"]["enum"])
    if contract_statuses != {member.value for member in FindingStatus}:
        problems.append("finding_status: контракт и домен расходятся")

    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    problems.extend(validate_openapi(spec))

    for problem in problems:
        print(problem)
    if problems:
        return 1
    print("contracts: схемы валидны, JWT/RBAC и два провода статусов согласованы")
    return 0


if __name__ == "__main__":
    sys.exit(main())
