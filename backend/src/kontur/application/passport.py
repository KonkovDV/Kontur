"""L1 Identity: основная надпись и метаданные файла.

Ключ Exact Match (ТЗ п. 14.3, вопрос 10): `document_code`, `revision`, `sheet`.
NFC и схлопывание пробелов; регистр в шифре значим. Пустое поле остаётся
null — не подставляем имя файла как шифр. Конфликт штампа и имени не
разрешается в пользу более нового: это `needs_clarification`.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from kontur.application.extractors.number import PageToken
from kontur.application.normalize import fold_label, normalize_key_field
from kontur.domain.geometry import bbox_from_polygon, reading_key
from kontur.domain.models import ApprovalStatus, DocStage

_HASH = re.compile(r"^[a-f0-9]{64}$")

_CODE = re.compile(
    r"(?:шифр|обозначение|\bshifr\b|\bcode\b)\s*[:.]?\s*"
    r"([A-ZА-Я0-9][A-ZА-Я0-9./\-_]{2,})",
    re.IGNORECASE,
)
_CODE_BARE = re.compile(r"\b(\d{3,8}-[A-ZА-Я]{1,6}(?:-\d{1,4})?)\b", re.IGNORECASE)
_REV = re.compile(r"(?:изм\.?|ред\.?|rev\.?)\s*[:.]?\s*(\d{1,3})\b", re.IGNORECASE)
_SHEET = re.compile(
    r"(?:лист|sheet)\s*[:.]?\s*([A-ZА-Я0-9][A-ZА-Я0-9.\-]{0,12})",
    re.IGNORECASE,
)
_STAGE_LABELED = re.compile(
    r"(?:стадия|stadia|stage)\s*[:.]?\s*(пд|рд|ид|pd|rd|id)\b",
    re.IGNORECASE,
)
_STAGE_TOKEN = re.compile(r"(?:^|[_\-\s./])(pd|rd|id|пд|рд|ид)(?:[_\-\s./]|$)", re.IGNORECASE)
_APPROVED = re.compile(r"\b(?:утв(?:ержд\w*)?|approved|согласован[оа]?)\b", re.IGNORECASE)
_NOT_APPROVED = re.compile(r"\b(?:не\s+утв|not\s+approved|черновик)\b", re.IGNORECASE)
_DATE = re.compile(r"\b(\d{2})[.](\d{2})[.](\d{4})\b")

_STAGE_MAP = {
    "pd": DocStage.PD,
    "пд": DocStage.PD,
    "rd": DocStage.RD,
    "рд": DocStage.RD,
    "id": DocStage.ID,
    "ид": DocStage.ID,
}

KEY_FIELDS: tuple[str, ...] = ("document_code", "revision", "sheet")


@dataclass(frozen=True, slots=True)
class DocumentPassport:
    file_id: str
    file_hash: str
    doc_stage: DocStage | None
    pages: int
    layer_kind: str
    document_code: str | None = None
    revision: str | None = None
    sheet: str | None = None
    discipline: str | None = None
    approval_status: ApprovalStatus = ApprovalStatus.UNKNOWN
    approval_date: date | None = None
    object_id: str | None = None
    rotate: int = 0
    media_box: tuple[float, ...] | None = None
    crop_box: tuple[float, ...] | None = None
    has_embedded_text: bool = False
    text_render_agreement: bool | None = None
    extraction_confidence: float | None = None
    needs_clarification: bool = False
    clarification_reason: str | None = None

    def to_schema(self) -> dict[str, object]:
        stage = self.doc_stage.value if self.doc_stage is not None else "UNKNOWN"
        quality: dict[str, object] = {
            "layer_kind": self.layer_kind,
            "rotate": self.rotate,
            "has_embedded_text": self.has_embedded_text,
            "has_ocr_layer": False,
            "text_render_agreement": self.text_render_agreement,
        }
        if self.media_box is not None:
            quality["media_box"] = list(self.media_box)
        if self.crop_box is not None:
            quality["crop_box"] = list(self.crop_box)
        payload: dict[str, object] = {
            "file_id": self.file_id,
            "file_hash": self.file_hash,
            "object_id": self.object_id,
            "doc_stage": stage,
            "discipline": self.discipline,
            "document_code": self.document_code,
            "revision": self.revision,
            "approval_status": self.approval_status.value,
            "approval_date": self.approval_date.isoformat() if self.approval_date else None,
            "sheet": self.sheet,
            "pages": self.pages,
            "predecessor_file_id": None,
            "successor_file_id": None,
            "quality": quality,
            "extraction_confidence": self.extraction_confidence,
        }
        return payload


def _join(tokens: Sequence[PageToken]) -> str:
    ordered = sorted(tokens, key=lambda item: reading_key(item.page, item.polygon_norm))
    return " ".join(item.text for item in ordered if item.text.strip())


def _stamp_tokens(tokens: Sequence[PageToken]) -> tuple[PageToken, ...]:
    """Нижняя четверть первой страницы: типичное место основной надписи ГОСТ."""

    first_page = [item for item in tokens if item.page == 1]
    pool: Sequence[PageToken] = first_page or tokens
    bottom = [
        item for item in pool if bbox_from_polygon(item.polygon_norm)[1] >= 0.70
    ]
    return tuple(bottom) if bottom else tuple(pool)


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    return normalize_key_field(match.group(1))


def _stage_from_text(text: str, *, labeled_only: bool) -> DocStage | None:
    if labeled_only:
        match = _STAGE_LABELED.search(text)
        if match is None:
            return None
        return _STAGE_MAP[fold_label(match.group(1)).replace(" ", "")]
    match = _STAGE_TOKEN.search(f" {text} ")
    if match is None:
        return None
    return _STAGE_MAP[fold_label(match.group(1))]


def stage_from_filename(filename: str) -> DocStage | None:
    match = _STAGE_TOKEN.search(f" {filename} ")
    if match is None:
        return None
    return _STAGE_MAP[fold_label(match.group(1))]


def _approval(text: str) -> tuple[ApprovalStatus, date | None]:
    parsed_date: date | None = None
    date_match = _DATE.search(text)
    if date_match is not None:
        try:
            parsed_date = datetime(
                int(date_match.group(3)),
                int(date_match.group(2)),
                int(date_match.group(1)),
            ).date()
        except ValueError:
            parsed_date = None
    if _NOT_APPROVED.search(text):
        return ApprovalStatus.NOT_APPROVED, parsed_date
    if _APPROVED.search(text):
        return ApprovalStatus.APPROVED, parsed_date
    return ApprovalStatus.UNKNOWN, parsed_date


def read_passport(
    tokens: Sequence[PageToken],
    *,
    file_id: str,
    file_hash: str,
    filename: str | None = None,
    pages: int = 1,
    layer_kind: str = "vector",
    rotate: int = 0,
    media_box: tuple[float, ...] | None = None,
    crop_box: tuple[float, ...] | None = None,
    object_id: str | None = None,
) -> DocumentPassport:
    """Прочитать паспорт. Не заполняет шифр из имени файла."""

    if _HASH.fullmatch(file_hash) is None:
        raise ValueError("file_hash паспорта обязан быть SHA-256")
    has_text = any(item.text.strip() for item in tokens)
    if layer_kind == "vector" and not has_text:
        layer_kind = "raster"
    region = _stamp_tokens(tokens) if tokens else ()
    blob = _join(region)
    full = _join(tokens)
    search = blob or full

    code = _first(_CODE, search) or _first(_CODE_BARE, search)
    revision = _first(_REV, search)
    sheet = _first(_SHEET, search)
    stage = _stage_from_text(search, labeled_only=True) or _stage_from_text(
        search, labeled_only=False
    )
    name_stage = stage_from_filename(filename) if filename else None
    needs = False
    reason: str | None = None
    if stage is not None and name_stage is not None and stage is not name_stage:
        needs = True
        reason = (
            f"стадия в штампе {stage.value}, в имени файла {name_stage.value}: "
            "эталон не выбирается"
        )
        stage = None
    elif stage is None and name_stage is not None:
        stage = name_stage
    if has_text and code is None:
        needs = True
        reason = reason or "шифр в основной надписи не найден"
    approval, approval_date = _approval(search)
    filled = sum(1 for item in (code, revision, sheet) if item)
    confidence = None
    if has_text:
        confidence = filled / len(KEY_FIELDS)
    # Детектора скрытого текста нет: согласие слоёв неизвестно, не True (RT-B).
    agreement: bool | None = None
    return DocumentPassport(
        file_id=file_id,
        file_hash=file_hash,
        doc_stage=stage,
        pages=pages,
        layer_kind=layer_kind,
        document_code=code,
        revision=revision,
        sheet=sheet,
        approval_status=approval,
        approval_date=approval_date,
        object_id=object_id,
        rotate=rotate,
        media_box=media_box,
        crop_box=crop_box,
        has_embedded_text=has_text,
        text_render_agreement=agreement,
        extraction_confidence=confidence,
        needs_clarification=needs,
        clarification_reason=reason,
    )
