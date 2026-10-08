"""Таблица ТЗ п. 11: значение, лимит, допуск, вердикт.

Так же, как `tools/timings.py` у a13: строка без числа печатается как
«не измерено» и не проходит ворота. Число, снятое не в том режиме
(не все 132 параметра, не 100 пользователей, чертёж без замера), —
«не измеримо», а не пропуск. Допуск построчный, как в их таблице:
лимит ТЗ из `docs/PERFORMANCE.md`, допуск — запас той же строки.

Гейт L закрывается только когда закрыта каждая строка. Одна строка
сверх лимита и допуска — fail, даже если остальные ещё не сняты.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

IN_LIMIT = "in_limit"
IN_TOLERANCE = "in_tolerance"
OVER = "over"
UNMEASURED = "unmeasured"
NOT_QUOTABLE = "not_quotable"
CLAIMED = "claimed"

VERDICT_RU = {
    IN_LIMIT: "в лимите",
    IN_TOLERANCE: "в допуске",
    OVER: "НЕ ПРОЙДЕНО",
    UNMEASURED: "не измерено",
    NOT_QUOTABLE: "не измеримо",
    CLAIMED: "заявляется",
}

DURATION = "duration"
MINIMUM = "minimum"
CLAIM = "claimed"

Unmet = Callable[[Mapping[str, Any]], str]


def _compare_unmet(measurement: Mapping[str, Any]) -> str:
    total = measurement.get("parameters_total")
    expected = measurement.get("parameters_expected")
    if total is None or expected is None:
        return "число параметров не заявлено: строка 4 считается по всем 132"
    if int(expected) < 132 or int(total) < int(expected):
        return f"проверки получили {int(total)} из {int(expected)}, нужно 132"
    pending = measurement.get("pending_raster")
    if pending is None:
        return "pending_raster не заявлен"
    if int(pending) > 0:
        return f"остались незавершённые растровые проверки: {int(pending)}"
    return ""


def _api_unmet(measurement: Mapping[str, Any]) -> str:
    vu = measurement.get("vu")
    if vu is None or int(vu) < 100:
        return "строка 10 считается при 100 виртуальных пользователях"
    if measurement.get("endpoint") != "status":
        return "строка 10 считается по GET /status после пайплайна"
    return ""


def _drawing_unmet(measurement: Mapping[str, Any]) -> str:
    if measurement.get("drawing_measured") is not True:
        return "строка 8 считается только по замеру одного чертежа"
    return ""


def _incremental_unmet(measurement: Mapping[str, Any]) -> str:
    if measurement.get("incremental") is not True:
        return "строка 9 считается по инкрементальному обновлению; полная пересборка не цитируется"
    return ""


def _pdf_unmet(measurement: Mapping[str, Any]) -> str:
    pages = measurement.get("pages")
    if isinstance(pages, bool) or not isinstance(pages, int) or not 1 <= pages <= 100:
        return "строка 2 считается по PDF от 1 до 100 страниц"
    if measurement.get("text_layer") is not True:
        return "строка 2 считается по PDF с текстовым слоем"
    if measurement.get("synthetic") is True:
        return "синтетический текстовый PDF не цитируется как строка 2"
    return ""


@dataclass(frozen=True, slots=True)
class Row:
    row_id: str
    scenario: str
    limit_s: float | None
    tolerance_s: float | None = None
    kind: str = DURATION
    unit: str = "с"
    unmet: Unmet | None = None

    @property
    def budget_s(self) -> float | None:
        if self.limit_s is None:
            return None
        return self.limit_s + (self.tolerance_s or 0.0)


ROWS: tuple[Row, ...] = (
    Row("1", "Загрузка 10 файлов по 50 МБ", 120.0, 30.0),
    Row("2", "Распознавание PDF до 100 страниц", 180.0, 30.0, unmet=_pdf_unmet),
    Row("3", "Полный анализ комплекта до 500 страниц", 600.0, 60.0),
    Row("4", "Сравнение 132 параметров", 120.0, 30.0, unmet=_compare_unmet),
    Row("5", "Формирование протокола", 30.0, 10.0),
    Row("6", "Отправка в ИАИС РиН", 30.0, 10.0),
    Row("7", "NLP-анализ одного параметра", 0.5, 0.1),
    Row("8", "CV-анализ одного чертежа", 30.0, 10.0, unmet=_drawing_unmet),
    Row("9", "Инкрементальное обновление протокола", 60.0, 15.0, unmet=_incremental_unmet),
    Row("10", "Отклик API, 95-й процентиль", 0.2, 0.05, unmet=_api_unmet),
    Row("11", "Одновременная работа пользователей", 100.0, None, kind=MINIMUM, unit="чел."),
    Row("12", "Доступность системы", None, None, kind=CLAIM, unit="%"),
    Row("13", "Восстановление после сбоя", 3600.0, None, kind=CLAIM),
    Row("14", "Потеря данных", 900.0, None, kind=CLAIM),
    Row("15", "Цикл верификации протокола", 1800.0, 600.0),
)

ROW_BY_ID = {row.row_id: row for row in ROWS}


@dataclass(frozen=True, slots=True)
class Result:
    row: Row
    value: float | None
    verdict: str
    note: str = ""
    blocked_reason: str = ""

    def as_json(self) -> dict[str, object]:
        return {
            "row": self.row.row_id,
            "scenario": self.row.scenario,
            "value_s": self.value,
            "limit_s": self.row.limit_s,
            "tolerance_s": self.row.tolerance_s,
            "budget_s": self.row.budget_s,
            "verdict": self.verdict,
            "verdict_ru": VERDICT_RU[self.verdict],
            "note": self.note,
            "blocked_reason": self.blocked_reason,
        }


def judge(row: Row, value: float | None, measurement: Mapping[str, Any] | None) -> str:
    """Вердикт одной строки. Пустое значение не бывает пропуском."""

    if row.kind == CLAIM and value is None:
        return CLAIMED
    if value is None:
        return UNMEASURED
    declared = measurement or {}
    if row.unmet is not None and row.unmet(declared):
        return NOT_QUOTABLE
    return _against_budget(row, value)


def _against_budget(row: Row, value: float) -> str:
    if row.limit_s is None:
        return UNMEASURED
    if row.kind == MINIMUM:
        return IN_LIMIT if value >= row.limit_s else OVER
    if value <= row.limit_s:
        return IN_LIMIT
    budget = row.budget_s if row.budget_s is not None else row.limit_s
    return IN_TOLERANCE if value <= budget else OVER


def _read_measurement(raw: Any) -> tuple[float | None, str, dict[str, Any]]:
    if raw is None:
        return None, "", {}
    if isinstance(raw, Mapping):
        value = raw.get("value")
        note = str(raw.get("note") or "")
        return (None if value is None else float(value), note, dict(raw))
    return float(raw), "", {}


def evaluate(measurements: Mapping[str, Any] | None = None) -> list[Result]:
    """Все 15 строк. Пропущенный ключ остаётся в таблице."""

    source = dict(measurements or {})
    results: list[Result] = []
    for row in ROWS:
        value, note, declared = _read_measurement(source.get(row.row_id))
        verdict = judge(row, value, declared)
        blocked = ""
        if verdict == NOT_QUOTABLE and row.unmet is not None:
            blocked = row.unmet(declared)
        results.append(
            Result(
                row=row,
                value=value,
                verdict=verdict,
                note=note,
                blocked_reason=blocked,
            )
        )
    return results


def timings_evidence(results: Sequence[Result]) -> dict[str, object]:
    """Вход гейта L. Неполный набор не помечается measured."""

    over = [item.row.row_id for item in results if item.verdict in {OVER, NOT_QUOTABLE}]
    open_rows = [item.row.row_id for item in results if item.verdict in {UNMEASURED, CLAIMED}]
    within = not over and not open_rows
    return {
        "measured": within or bool(over),
        "within_limits": within,
        "over": over,
        "unmeasured": open_rows,
        "rows": [item.as_json() for item in results],
    }


def render_table(results: Sequence[Result]) -> str:
    lines = ["ТЗ п. 11 — значение / лимит / допуск / вердикт", ""]
    for item in results:
        limit = "—" if item.row.limit_s is None else _format_limit(item.row)
        if item.row.tolerance_s is None:
            tolerance = "—"
        else:
            tolerance = _format_span(item.row.tolerance_s, item.row.unit)
        value = "—" if item.value is None else _format_span(item.value, item.row.unit)
        verdict = VERDICT_RU[item.verdict]
        lines.append(f"{item.row.row_id:>2}  {value:>16}  {limit:>12}  {tolerance:>10}  {verdict}")
        if item.blocked_reason:
            lines.append(f"    {item.blocked_reason}")
        elif item.note:
            lines.append(f"    {item.note}")
    evidence = timings_evidence(results)
    open_rows = [
        item.row.row_id for item in results if item.verdict in {UNMEASURED, CLAIMED}
    ]
    lines.append("")
    lines.append(
        "гейт L: "
        + ("в лимите" if evidence["within_limits"] is True else "не закрыт")
        + f", без замера: {', '.join(open_rows) or '—'}"
    )
    return "\n".join(lines)


def _format_limit(row: Row) -> str:
    if row.kind == MINIMUM and row.limit_s is not None:
        return f">= {row.limit_s:.0f} {row.unit}"
    assert row.limit_s is not None
    return _format_span(row.limit_s, row.unit)


def _format_span(value: float, unit: str) -> str:
    if unit == "с" and value < 0.001:
        return f"{value * 1_000_000:.0f} мкс"
    if unit == "с" and value < 1:
        return f"{value * 1000:.0f} мс"
    if unit == "с" and value >= 60:
        return f"{value / 60:.0f} мин"
    if unit == "с":
        return f"{value:.1f} с"
    return f"{value:.0f} {unit}"


def _text_layer_pdf(page_count: int) -> bytes:
    """PDF с одной латинской строкой на странице. Не чертёж и не скан."""

    import ctypes
    import io

    import pypdfium2 as pdfium  # type: ignore[import-untyped]
    import pypdfium2.raw as pdfium_c  # type: ignore[import-untyped]

    pdf = pdfium.PdfDocument.new()
    try:
        for index in range(page_count):
            page = pdf.new_page(400, 400)
            obj = pdfium_c.FPDFPageObj_NewTextObj(pdf, b"Helvetica", 12)
            raw = f"PAGE {index + 1}\x00".encode("utf-16-le")
            chars = (ctypes.c_ushort * (len(raw) // 2)).from_buffer_copy(raw)
            pdfium_c.FPDFText_SetText(obj, chars)
            pdfium_c.FPDFPageObj_Transform(obj, 1, 0, 0, 1, 40, 40)
            pdfium_c.FPDFPage_InsertObject(page, obj)
            pdfium_c.FPDFPage_GenerateContent(page)
        buffer = io.BytesIO()
        pdf.save(buffer)
        return buffer.getvalue()
    finally:
        pdf.close()


def _time_pdf_recognition(page_count: int = 100) -> dict[str, object]:
    from kontur.infrastructure.pdfium_tokens import extract_pdf_bytes

    data = _text_layer_pdf(page_count)
    started = perf_counter()
    document = extract_pdf_bytes(data, max_pages=page_count)
    elapsed = perf_counter() - started
    recognized = len(document.pages)
    text_pages = sum(1 for page in document.pages if page.has_embedded_text)
    return {
        "value": elapsed,
        "pages": recognized,
        "text_layer": text_pages == recognized and recognized > 0,
        "synthetic": True,
        "note": (
            f"локально: {recognized} страниц текстового слоя, по одной строке; "
            "не альбом чертежей и не сканы"
        ),
    }


def measure_local() -> dict[str, dict[str, object]]:
    """Строки, которые снимаются в процессе: протокол и один параметр.

    Остальные строки эта функция не заполняет. Старый прогон k6 сюда
    не подставляется: это другой стенд и не норматив п. 11.
    """

    return {
        "2": _time_pdf_recognition(),
        "5": {
            "value": _time_protocol(),
            "note": "локально: сборка протокола, JSON, DOCX, XML и PDF одного объекта",
        },
        "7": {
            "value": _time_one_parameter(),
            "note": "локально: extract_number одного параметра на векторных токенах",
        },
        "9": {
            "value": _time_protocol(),
            "incremental": False,
            "note": (
                "локально: повторная полная сборка протокола; "
                "отдельного инкрементального пути нет"
            ),
        },
    }


def _time_protocol() -> float:
    from kontur.application.protocol import (
        assemble_protocol,
        canonical_protocol_json,
        protocol_for_http,
    )
    from kontur.application.protocol_export import render_docx, render_pdf, render_xml
    from kontur.application.scenarios import CompletenessMap
    from kontur.domain.models import DocStage
    from kontur.domain.statuses import Completeness

    completeness: CompletenessMap = {
        DocStage.PD: Completeness.UPLOADED,
        DocStage.RD: Completeness.MISSING,
        DocStage.ID: Completeness.MISSING,
    }
    started = perf_counter()
    payload = assemble_protocol(
        protocol_id="protocol-tz11",
        object_id="obj-tz11",
        findings=(),
        completeness=completeness,
        files=[],
        versions={"matrix_version": "draft-0", "model_version": "none"},
        input_manifest_hash="a" * 64,
    )
    wire = protocol_for_http(payload)
    canonical_protocol_json(payload)
    render_docx(wire)
    render_xml(wire)
    render_pdf(wire)
    return perf_counter() - started


def _time_one_parameter() -> float:
    from kontur.application.extractors.number import PageToken, extract_number

    def token(text: str, x: float) -> PageToken:
        polygon = ((x, 0.4), (x + 0.08, 0.4), (x + 0.08, 0.43), (x, 0.43))
        return PageToken(text=text, page=1, polygon_source=polygon, polygon_norm=polygon)

    tokens = (
        token("площадь", 0.10),
        token("здания", 0.20),
        token("1200", 0.32),
    )
    extractor: dict[str, object] = {"type": "number", "anchors": ["площадь здания"]}
    comparator: dict[str, object] = {"unit_target": "м²"}
    rule: dict[str, object] = {
        "code": "TZ11-NLP",
        "unit": "м²",
        "extractor": extractor,
        "comparator": comparator,
    }
    extract_number(tokens, rule)
    started = perf_counter()
    hit = extract_number(tokens, rule)
    elapsed = perf_counter() - started
    if hit is None:
        raise RuntimeError("extract_number не прочитал контрольную строку")
    return elapsed


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    measurements: dict[str, Any] = {}
    if "--from-json" in args:
        index = args.index("--from-json")
        if index + 1 >= len(args):
            print("usage: python -m kontur.evaluation.tz11 [--from-json file]", file=sys.stderr)
            return 2
        loaded = json.loads(Path(args[index + 1]).read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            print("ожидался объект измерений", file=sys.stderr)
            return 2
        measurements.update(loaded)
    else:
        measurements.update(measure_local())
    results = evaluate(measurements)
    print(render_table(results))
    print(json.dumps(timings_evidence(results), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
