"""DOCX и XML протокола из провода ТЗ. PDF в образе нет (GAP-PROTOCOL-PDF).

Текст разделов наш. Образец Приложения 2 организатора сюда не копируется.
AUTO_NO_DIFFERENCE на этот провод не попадает.
"""

from __future__ import annotations

from collections.abc import Mapping
from io import BytesIO
from xml.etree import ElementTree as ET

from docx import Document
from lxml import etree  # type: ignore[import-untyped]

from kontur.evaluation.agent_dumps import repo_root

TABLES: tuple[str, ...] = (
    "completeness",
    "candidates",
    "confirmed",
    "negative_verified",
    "suspicions",
)
_TITLES: dict[str, str] = {
    "completeness": "Комплектность",
    "candidates": "Кандидаты",
    "confirmed": "Подтверждённые нарушения",
    "negative_verified": "Нарушение не подтверждено",
    "suspicions": "Подозрения",
}
_FORBIDDEN = "AUTO_NO_DIFFERENCE"


class ProtocolPdfUnavailable(RuntimeError):
    """WeasyPrint в образе нет. Пустой PDF не подменяет документ."""


def _text(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _rows(protocol: Mapping[str, object], name: str) -> list[Mapping[str, object]]:
    sections = protocol.get("sections")
    if not isinstance(sections, dict):
        raise ValueError("protocol.sections")
    if "preliminary_no_difference" in sections:
        raise ValueError("карман AUTO_NO_DIFFERENCE на провод протокола не выходит")
    raw = sections.get(name, [])
    if not isinstance(raw, list):
        raise ValueError(f"sections.{name}")
    rows: list[Mapping[str, object]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError(f"sections.{name}: строка не объект")
        if item.get("finding_status") == _FORBIDDEN:
            raise ValueError(f"{_FORBIDDEN} не сериализуется в протокол ТЗ")
        rows.append(item)
    return rows


def _upload(protocol: Mapping[str, object]) -> tuple[str, str, str]:
    raw = protocol.get("upload_status")
    if not isinstance(raw, dict):
        raise ValueError("upload_status")
    return _text(raw.get("pd")), _text(raw.get("rd")), _text(raw.get("id"))


def render_docx(protocol: Mapping[str, object]) -> bytes:
    """Документ Word: статус загрузки, тип проверки, пять таблиц, карточки."""

    document = Document()
    document.add_heading("Протокол проверки", level=0)
    document.add_paragraph(f"Объект: {_text(protocol.get('object_id'))}")
    document.add_paragraph(f"Протокол: {_text(protocol.get('protocol_id'))}")
    document.add_paragraph(f"Статус протокола: {_text(protocol.get('status'))}")
    document.add_heading("Статус загрузки документов", level=1)
    pd, rd, identity = _upload(protocol)
    upload = document.add_table(rows=2, cols=3)
    for index, title in enumerate(("ПД", "РД", "ИД")):
        upload.rows[0].cells[index].text = title
    for index, value in enumerate((pd, rd, identity)):
        upload.rows[1].cells[index].text = value
    document.add_heading("Тип проверки", level=1)
    document.add_paragraph(_text(protocol.get("scenario")))
    for name in TABLES:
        document.add_heading(_TITLES[name], level=1)
        rows = _rows(protocol, name)
        table = document.add_table(rows=1, cols=3)
        for index, title in enumerate(("Находка", "Параметр", "Статус")):
            table.rows[0].cells[index].text = title
        for row in rows:
            cells = table.add_row().cells
            cells[0].text = _text(row.get("finding_id"))
            cells[1].text = _text(row.get("rule_code"))
            cells[2].text = _text(row.get("finding_status"))
    document.add_heading("Карточки доказательств", level=1)
    cards = 0
    for name in TABLES:
        for row in _rows(protocol, name):
            cards += 1
            document.add_paragraph(
                f"{_text(row.get('rule_code'))} / {_text(row.get('finding_id'))}"
            )
            document.add_paragraph(_text(row.get("rationale")))
            refs = row.get("evidence_refs")
            if isinstance(refs, list):
                for ref in refs:
                    document.add_paragraph(f"Доказательство: {_text(ref)}")
    if cards == 0:
        document.add_paragraph("Карточек нет.")
    document.add_paragraph(f"Число нарушений: {_text(protocol.get('violation_count'))}")
    buffer = BytesIO()
    document.save(buffer)
    payload = buffer.getvalue()
    if _FORBIDDEN.encode() in payload:
        raise ValueError(f"{_FORBIDDEN} попал в DOCX")
    return payload


def render_xml(protocol: Mapping[str, object]) -> bytes:
    """XML по contracts/schemas/protocol-export.xsd. lxml проверяет схему."""

    pd, rd, identity = _upload(protocol)
    root = ET.Element(
        "protocol",
        {
            "protocol_id": _text(protocol.get("protocol_id")),
            "object_id": _text(protocol.get("object_id")),
            "status": _text(protocol.get("status")),
        },
    )
    ET.SubElement(root, "upload_status", {"pd": pd, "rd": rd, "id": identity})
    ET.SubElement(root, "check_type").text = _text(protocol.get("scenario"))
    tables = ET.SubElement(root, "tables")
    card_rows: list[Mapping[str, object]] = []
    for name in TABLES:
        table = ET.SubElement(tables, "table", {"name": name})
        for row in _rows(protocol, name):
            card_rows.append(row)
            node = ET.SubElement(
                table,
                "row",
                {
                    "finding_id": _text(row.get("finding_id")),
                    "rule_code": _text(row.get("rule_code")),
                    "finding_status": _text(row.get("finding_status")),
                },
            )
            rationale = _text(row.get("rationale"))
            if rationale:
                ET.SubElement(node, "rationale").text = rationale
    cards = ET.SubElement(root, "evidence_cards")
    for row in card_rows:
        card = ET.SubElement(
            cards,
            "card",
            {
                "finding_id": _text(row.get("finding_id")),
                "rule_code": _text(row.get("rule_code")),
            },
        )
        rationale = _text(row.get("rationale"))
        if rationale:
            ET.SubElement(card, "rationale").text = rationale
        refs = row.get("evidence_refs")
        if isinstance(refs, list):
            for ref in refs:
                ET.SubElement(card, "evidence_ref").text = _text(ref)
    count = protocol.get("violation_count")
    if not isinstance(count, int) or count < 0:
        raise ValueError("violation_count")
    ET.SubElement(root, "violation_count").text = str(count)
    raw = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if not isinstance(raw, bytes):
        raise TypeError("XML протокола")
    if _FORBIDDEN.encode() in raw:
        raise ValueError(f"{_FORBIDDEN} попал в XML")
    schema_path = repo_root() / "contracts" / "schemas" / "protocol-export.xsd"
    schema = etree.XMLSchema(etree.parse(schema_path))
    if not schema.validate(etree.fromstring(raw)):
        raise ValueError(f"XML протокола не проходит XSD: {schema.error_log.last_error}")
    return raw


def render_pdf(_protocol: Mapping[str, object]) -> bytes:
    """PDF не собирается: в образе нет pango/harfbuzz для WeasyPrint."""

    raise ProtocolPdfUnavailable(
        "PDF протокола нет (GAP-PROTOCOL-PDF): WeasyPrint не установлен в образе"
    )
