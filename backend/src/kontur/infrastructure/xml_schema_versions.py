"""XML schema version check against the normative registry (SOTA-K2).

Pure decision on whether an incoming XML document's schema version is accepted on a given
date. The registry lives in ``data/normative/registry.yaml`` (acts with ``act_type:
xml_schema``). Registry dates are ``verified: false`` until checked against the official
publication; callers must not present a rejection as a legal fact.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]

REGISTRY = Path(__file__).resolve().parents[4] / "data" / "normative" / "registry.yaml"

__all__ = ["XmlSchemaStatus", "XmlSchemaVerdict", "check_xml_schema_version", "load_xml_schemas"]


class XmlSchemaStatus(Enum):
    ACCEPTED = "ACCEPTED"
    OUTDATED = "OUTDATED"
    NOT_YET_IN_FORCE = "NOT_YET_IN_FORCE"
    UNKNOWN_VERSION = "UNKNOWN_VERSION"


@dataclass(frozen=True)
class XmlSchemaVerdict:
    status: XmlSchemaStatus
    schema_code: str
    version: str
    registry_id: str | None
    current_version: str | None
    verified: bool


def _date(value: Any) -> dt.date | None:
    return None if value is None else dt.date.fromisoformat(str(value))


def load_xml_schemas(path: Path = REGISTRY) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [a for a in data["acts"] if a.get("act_type") == "xml_schema"]


def _in_force(act: dict[str, Any], on: dt.date) -> bool:
    start, end = _date(act["effective_from"]), _date(act["effective_to"])
    return (start is None or start <= on) and (end is None or on <= end)


def check_xml_schema_version(
    schemas: list[dict[str, Any]], schema_code: str, version: str, on: dt.date
) -> XmlSchemaVerdict:
    """Status of ``schema_code``/``version`` on date ``on``; unknown versions fail closed."""
    same_code = [a for a in schemas if a["schema_code"] == schema_code]
    current = next((a for a in same_code if _in_force(a, on)), None)
    current_version = current["schema_version"] if current else None
    act = next((a for a in same_code if a["schema_version"] == version), None)
    if act is None:
        status = XmlSchemaStatus.UNKNOWN_VERSION
    elif _in_force(act, on):
        status = XmlSchemaStatus.ACCEPTED
    else:
        start = _date(act["effective_from"])
        before = start is not None and on < start
        status = XmlSchemaStatus.NOT_YET_IN_FORCE if before else XmlSchemaStatus.OUTDATED
    return XmlSchemaVerdict(
        status=status,
        schema_code=schema_code,
        version=version,
        registry_id=act["id"] if act else None,
        current_version=current_version,
        verified=bool(act and act["verified"]),
    )
