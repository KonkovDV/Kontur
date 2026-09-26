"""DOCX, XML и PDF протокола из провода ТЗ.

PDF собирает reportlab. Шрифт DejaVu в образе, на Windows — Arial.
WeasyPrint не используется.

Текст разделов наш. Образец Приложения 2 организатора сюда не копируется.
AUTO_NO_DIFFERENCE на этот провод не попадает.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from io import BytesIO
from pathlib import Path
from xml.etree import ElementTree as ET

from docx import Document
from lxml import etree  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]

from kontur.domain.models import EvidenceGroup
from kontur.evaluation.agent_dumps import repo_root

TABLES: tuple[str, ...] = (
    "completeness",
    "candidates",
    "confirmed",
    "negative_verified",
    "suspicions",
    "missing_evidence",
    "needs_attention",
)
_TITLES: dict[str, str] = {
    "completeness": "Комплектность",
    "candidates": "Кандидаты",
    "confirmed": "Подтверждённые нарушения",
    "negative_verified": "Нарушение не подтверждено",
    "suspicions": "Подозрения",
    "missing_evidence": "Нет доказательств",
    "needs_attention": "Требует внимания",
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


_FACT_KEYS: tuple[tuple[str, str], ...] = (
    ("expected_value", "Ожидаемое"),
    ("actual_value", "Фактическое"),
    ("delta", "Дельта"),
    ("tolerance", "Допуск"),
    ("file_hash", "SHA-256"),
    ("doc_stage", "Стадия"),
    ("document_code", "Шифр"),
    ("revision", "Редакция"),
    ("approval_basis", "Основание утверждения"),
    ("page", "Страница"),
    ("polygon_norm", "Полигон"),
)


def _fact_pairs(
    row: Mapping[str, object],
    cards: Mapping[str, Mapping[str, object]] | None,
) -> list[tuple[str, str]]:
    extra: Mapping[str, object] = {}
    if cards is not None:
        found = cards.get(_text(row.get("finding_id")))
        if isinstance(found, Mapping):
            extra = found
    pairs: list[tuple[str, str]] = []
    for key, _title in _FACT_KEYS:
        value = extra.get(key, row.get(key))
        if value is None or value == "":
            continue
        pairs.append((key, _text(value)))
    return pairs


def _tolerance_text(rule: Mapping[str, object] | None) -> str:
    if not isinstance(rule, Mapping):
        return ""
    comparator = rule.get("comparator")
    if not isinstance(comparator, dict):
        return ""
    parts: list[str] = []
    if "tolerance_abs" in comparator:
        parts.append(f"abs {comparator['tolerance_abs']}")
    if "tolerance_rel" in comparator:
        parts.append(f"rel {comparator['tolerance_rel']}")
    return ", ".join(parts)


def cards_from_groups(
    protocol: Mapping[str, object],
    groups: Mapping[str, EvidenceGroup],
    rules: Mapping[str, Mapping[str, object]] | None = None,
) -> dict[str, dict[str, str]]:
    """Поля карточки, которых нет в finding.schema.json: файл, страница, полигон."""

    built: dict[str, dict[str, str]] = {}
    for name in TABLES:
        for row in _rows(protocol, name):
            group_id = row.get("evidence_group_id")
            group = groups.get(group_id) if isinstance(group_id, str) else None
            if group is None or not group.fragments:
                continue
            finding_id = _text(row.get("finding_id"))
            rule = None if rules is None else rules.get(_text(row.get("rule_code")))
            fragments = group.fragments
            built[finding_id] = {
                "file_hash": "; ".join(item.document.file_hash for item in fragments),
                "doc_stage": "; ".join(item.document.doc_stage.value for item in fragments),
                "document_code": "; ".join(item.document.document_code for item in fragments),
                "revision": "; ".join(item.document.revision for item in fragments),
                "approval_basis": "; ".join(
                    item.document.approval_basis.value for item in fragments
                ),
                "page": "; ".join(str(item.page) for item in fragments),
                "polygon_norm": json.dumps(
                    [
                        [[float(x), float(y)] for x, y in item.polygon_norm]
                        for item in fragments
                    ],
                    ensure_ascii=False,
                ),
                "tolerance": _tolerance_text(rule),
            }
    return built


def _upload(protocol: Mapping[str, object]) -> tuple[str, str, str]:
    raw = protocol.get("upload_status")
    if not isinstance(raw, dict):
        raise ValueError("upload_status")
    return _text(raw.get("pd")), _text(raw.get("rd")), _text(raw.get("id"))


def render_docx(
    protocol: Mapping[str, object],
    cards: Mapping[str, Mapping[str, object]] | None = None,
) -> bytes:
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
    card_count = 0
    for name in TABLES:
        for row in _rows(protocol, name):
            card_count += 1
            document.add_paragraph(
                f"{_text(row.get('rule_code'))} / {_text(row.get('finding_id'))}"
            )
            document.add_paragraph(_text(row.get("rationale")))
            for key, value in _fact_pairs(row, cards):
                title = dict(_FACT_KEYS)[key]
                document.add_paragraph(f"{title}: {value}")
            refs = row.get("evidence_refs")
            if isinstance(refs, list):
                for ref in refs:
                    document.add_paragraph(f"Доказательство: {_text(ref)}")
    if card_count == 0:
        document.add_paragraph("Карточек нет.")
    document.add_paragraph(f"Число нарушений: {_text(protocol.get('violation_count'))}")
    buffer = BytesIO()
    document.save(buffer)
    payload = buffer.getvalue()
    if _FORBIDDEN.encode() in payload:
        raise ValueError(f"{_FORBIDDEN} попал в DOCX")
    return payload


def render_xml(
    protocol: Mapping[str, object],
    cards: Mapping[str, Mapping[str, object]] | None = None,
) -> bytes:
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
    card_root = ET.SubElement(root, "evidence_cards")
    for row in card_rows:
        card = ET.SubElement(
            card_root,
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
        for key, value in _fact_pairs(row, cards):
            ET.SubElement(card, key).text = value
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


def _pdf_font() -> str:
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    )
    for path in candidates:
        if path.is_file():
            if "KonturSans" not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont("KonturSans", str(path)))
            return "KonturSans"
    return "Helvetica"


def render_pdf(
    protocol: Mapping[str, object],
    cards: Mapping[str, Mapping[str, object]] | None = None,
) -> bytes:
    """PDF из той же модели, что DOCX: разделы, строки, карточки."""

    font = _pdf_font()
    buffer = BytesIO()
    sheet = canvas.Canvas(buffer)
    sheet.setFont(font, 11)
    y = 800

    def line(text: str, size: int = 11) -> None:
        nonlocal y
        if y < 48:
            sheet.showPage()
            y = 800
        sheet.setFont(font, size)
        sheet.drawString(40, y, text[:180])
        y -= 16

    line("Протокол проверки", 16)
    line(f"Объект: {_text(protocol.get('object_id'))}")
    line(f"Протокол: {_text(protocol.get('protocol_id'))}")
    line(f"Статус протокола: {_text(protocol.get('status'))}")
    line("Статус загрузки документов", 14)
    pd, rd, identity = _upload(protocol)
    line(f"ПД {pd}  РД {rd}  ИД {identity}")
    line("Тип проверки", 14)
    line(_text(protocol.get("scenario")))
    for name in TABLES:
        line(_TITLES[name], 14)
        for row in _rows(protocol, name):
            line(
                f"{_text(row.get('finding_id'))}  {_text(row.get('rule_code'))}  "
                f"{_text(row.get('finding_status'))}"
            )
    line("Карточки доказательств", 14)
    card_count = 0
    for name in TABLES:
        for row in _rows(protocol, name):
            card_count += 1
            line(f"{_text(row.get('rule_code'))} / {_text(row.get('finding_id'))}")
            line(_text(row.get("rationale")))
            for key, value in _fact_pairs(row, cards):
                title = dict(_FACT_KEYS)[key]
                line(f"{title}: {value}")
            refs = row.get("evidence_refs")
            if isinstance(refs, list):
                for ref in refs:
                    line(f"Доказательство: {_text(ref)}")
    if card_count == 0:
        line("Карточек нет.")
    line(f"Число нарушений: {_text(protocol.get('violation_count'))}")
    sheet.save()
    payload = buffer.getvalue()
    if not payload.startswith(b"%PDF"):
        raise ProtocolPdfUnavailable("PDF протокола не собран")
    if _FORBIDDEN.encode() in payload:
        raise ValueError(f"{_FORBIDDEN} попал в PDF")
    return payload
