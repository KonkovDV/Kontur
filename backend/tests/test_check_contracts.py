"""Regression tests for OpenAPI contract validation invariants."""

from __future__ import annotations

import copy

import pytest
import yaml

from scripts.check_contracts import (
    OPENAPI,
    OPERATION_METHODS,
    iter_operations,
    validate_openapi,
)


@pytest.fixture(scope="module")
def current_spec() -> dict[str, object]:
    spec = yaml.safe_load(OPENAPI.read_text(encoding="utf-8"))
    assert isinstance(spec, dict)
    return spec


def _operation(spec: dict[str, object], operation_id: str) -> dict[str, object]:
    for _, _, operation in iter_operations(spec):
        if operation.get("operationId") == operation_id:
            return operation
    raise AssertionError(f"operation not found: {operation_id}")


def test_current_openapi_is_valid(current_spec: dict[str, object]) -> None:
    assert validate_openapi(copy.deepcopy(current_spec)) == []


def test_operation_methods_are_complete_and_ignore_path_parameters() -> None:
    expected = {
        "get",
        "put",
        "post",
        "delete",
        "options",
        "head",
        "patch",
        "trace",
    }
    spec: dict[str, object] = {
        "paths": {
            "/all-methods": {
                "parameters": [{"name": "shared", "in": "query"}],
                **{
                    method: {"operationId": f"operation-{method}"}
                    for method in expected
                },
            }
        }
    }

    discovered = {method for _, method, _ in iter_operations(spec)}

    assert OPERATION_METHODS == frozenset(expected)
    assert discovered == expected


def test_second_public_endpoint_is_rejected(current_spec: dict[str, object]) -> None:
    spec = copy.deepcopy(current_spec)
    _operation(spec, "getSystemCapabilities")["security"] = []

    problems = validate_openapi(spec)

    assert any(
        "security: [] должна иметь ровно операция healthz" in problem
        and "getSystemCapabilities" in problem
        for problem in problems
    )


def test_duplicate_operation_id_is_rejected(current_spec: dict[str, object]) -> None:
    spec = copy.deepcopy(current_spec)
    _operation(spec, "getProcessStatus")["operationId"] = "uploadDocuments"

    problems = validate_openapi(spec)

    assert any("дубликат operationId: uploadDocuments" in problem for problem in problems)


def test_upload_401_must_reference_unauthorized(
    current_spec: dict[str, object],
) -> None:
    spec = copy.deepcopy(current_spec)
    upload = _operation(spec, "uploadDocuments")
    responses = upload["responses"]
    assert isinstance(responses, dict)
    responses["401"] = {"$ref": "#/components/responses/Forbidden"}

    problems = validate_openapi(spec)

    assert any(
        "uploadDocuments: ответ 401 должен ссылаться на Unauthorized" in problem
        for problem in problems
    )


def test_operation_security_cannot_drift_from_global(
    current_spec: dict[str, object],
) -> None:
    spec = copy.deepcopy(current_spec)
    _operation(spec, "uploadDocuments")["security"] = [
        {"bearerAuth": ["unexpected-scope"]}
    ]

    problems = validate_openapi(spec)

    assert any(
        "uploadDocuments: effective security должен совпадать с глобальным" in problem
        for problem in problems
    )
