"""Синтетический учебный комплект. Не пакет организатора и не скрытый тест."""

from __future__ import annotations

from kontur.application.runtime import AcceptedFile, ProcessRecord, ProcessWorkspace
from kontur.domain.models import DocStage
from kontur.domain.statuses import Completeness
from kontur.infrastructure.pdfium_tokens import file_sha256
from kontur.infrastructure.synthetic_pdf import cyrillic_pdf

DEMO_OBJECT_ID = "OBJ-DEMO-COLD-START"
ETALON_FILE_ID = "f-pd"
DRAFT_FILE_ID = "f-pd-draft"

_STAMP = (("Утвердил", 20.0, 20.0), ("Иванов И.И.", 90.0, 20.0))
_LABEL_X = 20.0
_VALUE_X = 200.0
_VALUE_DY = -4.0
_ROWS: tuple[tuple[str, float], ...] = (
    ("Площадь застройки", 210.0),
    ("Класс бетона", 190.0),
    ("Ширина проема", 170.0),
)
_PD_VALUES = (
    ("Площадь застройки", "1250,5"),
    ("Класс бетона", "B30"),
    ("Ширина проема", "1,2"),
)
_RD_VALUES = (
    ("Площадь застройки", "1100"),
    ("Класс бетона", "B25"),
    ("Ширина проема", "0,8"),
)
_STALE_VALUES = (
    ("Площадь застройки", "9999"),
    ("Класс бетона", "B10"),
    ("Ширина проема", "0,4"),
)


def _sheet(values: tuple[tuple[str, str], ...], *, stamp: bool) -> bytes:
    lines: list[tuple[str, float, float]] = []
    if stamp:
        lines.extend(_STAMP)
    for (label, _), (_, y) in zip(values, _ROWS, strict=True):
        lines.append((label, _LABEL_X, y))
    for (_, value), (_, y) in zip(values, _ROWS, strict=True):
        lines.append((value, _VALUE_X, y + _VALUE_DY))
    return cyrillic_pdf(lines)


def demo_sheet_files() -> tuple[tuple[str, DocStage, str, bytes], ...]:
    """Черновик ПД, утверждённая ПД, РД и ИД. Две ПД одного содержания шифра."""

    draft = _sheet(_STALE_VALUES, stamp=False)
    approved = _sheet(_PD_VALUES, stamp=True)
    rd = _sheet(_RD_VALUES, stamp=True)
    identity = _sheet(_PD_VALUES, stamp=True)
    return (
        (DRAFT_FILE_ID, DocStage.PD, "pd-draft.pdf", draft),
        (ETALON_FILE_ID, DocStage.PD, "pd-approved.pdf", approved),
        ("f-rd", DocStage.RD, "rd.pdf", rd),
        ("f-id", DocStage.ID, "id.pdf", identity),
    )


def install_demo_kit(workspace: ProcessWorkspace, object_id: str) -> ProcessRecord:
    """Положить комплект и прогнать матрицу. Эталон не выбирает."""

    record = workspace.create(
        object_id,
        {
            DocStage.PD: Completeness.UPLOADED,
            DocStage.RD: Completeness.UPLOADED,
            DocStage.ID: Completeness.UPLOADED,
        },
    )
    for file_id, stage, filename, payload in demo_sheet_files():
        workspace.attach_file(
            record,
            AcceptedFile(
                file_id=file_id,
                file_hash=file_sha256(payload),
                filename=filename,
                doc_stage=stage,
                size_bytes=len(payload),
            ),
        )
        workspace.keep_blob(record, file_id, payload)
    workspace.run_matrix_pipeline(record)
    return record
