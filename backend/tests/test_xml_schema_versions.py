"""SOTA-K2: XML schema version in the normative registry."""

from __future__ import annotations

import datetime as dt

from kontur.infrastructure.xml_schema_versions import (
    XmlSchemaStatus,
    check_xml_schema_version,
    load_xml_schemas,
)

SCHEMAS = load_xml_schemas()


def _status(version: str, on: str) -> XmlSchemaStatus:
    return check_xml_schema_version(SCHEMAS, "П9", version, dt.date.fromisoformat(on)).status


def test_01_06_rejected_after_switch_to_01_07() -> None:
    assert _status("01.06", "2026-06-11") is XmlSchemaStatus.OUTDATED
    assert _status("01.07", "2026-06-11") is XmlSchemaStatus.ACCEPTED


def test_01_06_accepted_before_switch() -> None:
    assert _status("01.06", "2026-06-10") is XmlSchemaStatus.ACCEPTED
    assert _status("01.07", "2026-06-10") is XmlSchemaStatus.NOT_YET_IN_FORCE


def test_unknown_version_fails_closed() -> None:
    verdict = check_xml_schema_version(SCHEMAS, "П9", "09.99", dt.date(2026, 10, 16))
    assert verdict.status is XmlSchemaStatus.UNKNOWN_VERSION
    assert verdict.current_version == "01.07"


def test_registry_dates_are_not_marked_verified() -> None:
    verdict = check_xml_schema_version(SCHEMAS, "П9", "01.07", dt.date(2026, 10, 16))
    assert verdict.verified is False
