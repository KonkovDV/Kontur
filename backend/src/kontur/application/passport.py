"""L1 Identity: основная надпись и метаданные файла.

Ключ Exact Match (ТЗ п. 14.3, вопрос 10): `document_code`, `revision`, `sheet`.
NFC и схлопывание пробелов; регистр в шифре значим. Пустой штамп остаётся
null. Обозначение из имени файла пишется в `identity_code` с
`code_basis=FILENAME` и не становится `document_code`. Конфликт штампа и
имени не выбирает имя: это `needs_clarification`. Раздел из индекса
пишется в `discipline` и не становится общим шифром томов.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum

from kontur.application.extractors.number import PageToken
from kontur.application.normalize import fold_label, normalize_key_field
from kontur.domain.geometry import bbox_from_polygon, reading_key
from kontur.domain.models import ApprovalBasis, ApprovalStatus, DocStage

_HASH = re.compile(r"^[a-f0-9]{64}$")

_CODE = re.compile(
    r"(?:шифр|обозначение|\bshifr\b|\bcode\b)\s*[:.]?\s*"
    r"([A-ZА-Я0-9][A-ZА-Я0-9./\-_]{2,})",
    re.IGNORECASE,
)
_CODE_BARE = re.compile(r"\b(\d{3,8}-[A-ZА-Я]{1,6}(?:-\d{1,4})?)\b", re.IGNORECASE)
# ГОСТ 21.101 на листах комплекта: АНО/150321/1-П-АР, не имя файла.
_CODE_DESIGNATION = re.compile(
    r"(?<![\w/])([A-ZА-ЯЁ]{2,12}/\d{3,8}/\d{1,4}-[A-ZА-ЯЁ]{1,6}-"
    r"[A-ZА-ЯЁ]{1,8}\d{0,4}(?:\.\d+){0,4})(?!\w)",
    re.IGNORECASE,
)
_REV = re.compile(
    r"(изм\.?|ред\.?|rev\.?|корректировк\w*)\s*[:.]?\s*(?:№\s*)?(\d{1,3})\b",
    re.IGNORECASE,
)
# «Листов» не номер листа: после «лист» не должно идти «ов».
_SHEET = re.compile(
    r"(?<![\w])(?:лист|sheet)(?!ов)\s*[:.]?\s*(\d{1,3}(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_SHEET_LABEL = re.compile(r"^(?:лист|sheet)\.?$", re.IGNORECASE)
_SHEET_COUNT = re.compile(r"^листов\.?:?$", re.IGNORECASE)
_SHEET_NUMBER = re.compile(r"^\d{1,3}(?:\.\d{1,2})?$")
_STAGE_LABELED = re.compile(
    r"(?:стадия|stadia|stage)\s*[:.]?\s*(пд|рд|ид|pd|rd|id|п|р|и)\b",
    re.IGNORECASE,
)
_STAGE_LABEL = re.compile(r"^(?:стадия|stage)\.?$", re.IGNORECASE)
_STAGE_WORD = re.compile(r"^(?:пд|рд|ид|pd|rd|id|п|р|и)\.?$", re.IGNORECASE)
_STAGE_TOKEN = re.compile(r"(?:^|[_\-\s./])(pd|rd|id|пд|рд|ид)(?:[_\-\s./]|$)", re.IGNORECASE)
_NOT_APPROVED = re.compile(r"\b(?:не\s+утв|not\s+approved|черновик)\b", re.IGNORECASE)
_DATE = re.compile(r"\b(\d{2})[.](\d{2})[.](\d{4})\b")
_APPROVAL_LABEL_PREFIX = re.compile(
    r"^(?:утвердил|утвержд[её]н[аоы]?|approved|утв\.?)\s*[:.]?\s*(.*)$",
    re.IGNORECASE,
)
_PERSON_NAME = re.compile(
    r"(?:"
    r"[A-ZА-ЯЁ][a-zа-яё\-]+\s+[A-ZА-ЯЁ]\.\s*[A-ZА-ЯЁ]\.?)"
    r"|(?:[A-ZА-ЯЁ][a-zа-яё\-]+\s+[A-ZА-ЯЁ][a-zа-яё\-]+"
    r"(?:\s+[A-ZА-ЯЁ][a-zа-яё\-]+)?)"
)
_STAMP_Y0 = 0.70
_APPROVAL_ROW_DY = 0.04
_APPROVAL_MAX_DX = 0.40
# Форма 1 ГОСТ Р 21.101: основная надпись 185×55 мм в правом нижнем углу.
# Запас закрывает рамку и строку изменений, не четверть листа А0.
_TITLE_BLOCK_WIDTH_MM = 190.0
_TITLE_BLOCK_HEIGHT_MM = 70.0
_PT_TO_MM = 25.4 / 72.0
_STANDARD_CODE = re.compile(
    r"^(?:гост|gost|снип|snip|санпин|sanpin|росс|еаэс|eaэс|pocc|ra\.ru|ru\.)"
    r"|^(?:сп|sp)\d"
    r"|^(?:рф-)?\d+(?:-\d+){3,}",
)

# Детерминированный crop основной надписи ГОСТ (без VLM): нижняя полоса листа.
# Нормализованные координаты после CropBox/MediaBox/Rotate, Y вниз.

_STAGE_MAP = {
    "pd": DocStage.PD,
    "пд": DocStage.PD,
    "п": DocStage.PD,
    "rd": DocStage.RD,
    "рд": DocStage.RD,
    "р": DocStage.RD,
    "id": DocStage.ID,
    "ид": DocStage.ID,
    "и": DocStage.ID,
}

KEY_FIELDS: tuple[str, ...] = ("document_code", "revision", "sheet")
_ROOM_NO = re.compile(
    r"(?<![\w])(?:пом(?:ещени\w*)?|комн(?:ата)?)\.?\s*(?:№\s*)?(\d{1,4}(?:\.\d{1,2})?)",
    re.IGNORECASE,
)
_ELEMENT_NO = re.compile(
    r"(?<![\w])элемент\w*\s*(?:№\s*)?([0-9A-ZА-ЯЁ][0-9A-ZА-ЯЁ.\-]{0,16})",
    re.IGNORECASE,
)


class KeyFieldState(StrEnum):
    """Исход чтения одного ключевого поля. Это не finding_status."""

    FOUND = "found"
    ABSENT = "absent"
    UNREADABLE = "unreadable"


@dataclass(frozen=True, slots=True)
class KeyFieldValue:
    state: KeyFieldState
    value: str | None = None


@dataclass(frozen=True, slots=True)
class StampKeyFields:
    """Пять полей §14.3. Порог Exact Match этим отчётом не закрывается."""

    cipher: KeyFieldValue
    stage: KeyFieldValue
    revision: KeyFieldValue
    sheet: KeyFieldValue
    room_element: KeyFieldValue


@dataclass(frozen=True, slots=True)
class DocumentPassport:
    file_id: str
    file_hash: str
    doc_stage: DocStage | None
    pages: int
    layer_kind: str
    document_code: str | None = None
    revision: str | None = None
    #: «change» для «изм», «correction» для «кор» и «ред». Пусто без номера на титуле.
    revision_kind: str = ""
    sheet: str | None = None
    discipline: str | None = None
    approval_status: ApprovalStatus = ApprovalStatus.UNKNOWN
    approval_basis: ApprovalBasis = ApprovalBasis.UNPROVEN
    approval_date: date | None = None
    object_id: str | None = None
    rotate: int = 0
    media_box: tuple[float, ...] | None = None
    crop_box: tuple[float, ...] | None = None
    has_embedded_text: bool = False
    text_render_agreement: bool | None = None
    extraction_confidence: float | None = None
    identity_code: str | None = None
    code_basis: str | None = None
    needs_clarification: bool = False
    clarification_reason: str | None = None
    injection_clean: bool | None = None

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
        if self.injection_clean is not None:
            quality["injection_clean"] = self.injection_clean
        payload: dict[str, object] = {
            "file_id": self.file_id,
            "file_hash": self.file_hash,
            "object_id": self.object_id,
            "doc_stage": stage,
            "discipline": self.discipline,
            "document_code": self.document_code,
            "identity_code": self.identity_code,
            "code_basis": self.code_basis,
            "revision": self.revision,
            "approval_status": self.approval_status.value,
            "approval_basis": self.approval_basis.value,
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


def title_block_origin(media_box: Sequence[float] | None) -> tuple[float, float]:
    """Левый верх зоны штампа в [0;1], Y вниз.

    Размер листа неизвестен или меньше надписи — прежняя нижняя полоса.
    На А1 и крупнее зона сжимается до правого нижнего угла, иначе шифр
    читается из таблицы на поле чертежа.
    """

    if media_box is None or len(media_box) != 4:
        return 0.0, _STAMP_Y0
    left, bottom, right, top = (float(item) for item in media_box)
    width_mm = (right - left) * _PT_TO_MM
    height_mm = (top - bottom) * _PT_TO_MM
    if width_mm <= _TITLE_BLOCK_WIDTH_MM or height_mm <= _TITLE_BLOCK_HEIGHT_MM:
        return 0.0, _STAMP_Y0
    return (
        1.0 - _TITLE_BLOCK_WIDTH_MM / width_mm,
        max(_STAMP_Y0, 1.0 - _TITLE_BLOCK_HEIGHT_MM / height_mm),
    )


def stamp_region_polygon(*, y0: float = _STAMP_Y0) -> tuple[tuple[float, float], ...]:
    """Прямоугольник зоны штампа в норм. координатах [0;1]. Без VLM / детектора."""

    top = min(max(y0, 0.0), 0.95)
    return ((0.0, top), (1.0, top), (1.0, 1.0), (0.0, 1.0))


def stamp_crop_box(
    tokens: Sequence[PageToken] | None = None,
    *,
    page: int | None = None,
    y0: float = _STAMP_Y0,
    media_box: Sequence[float] | None = None,
) -> tuple[float, float, float, float]:
    """Нормализованный bbox кропа штампа для OCR dual-read.

    Если в полосе есть токены — охватывающий прямоугольник с небольшим
    запасом; иначе дефолтная нижняя полоса. На крупном листе полоса — это
    основная надпись в миллиметрах, не нижние 30% страницы. Всегда в [0;1].
    """

    x_min, y_min = title_block_origin(media_box)
    y_min = max(y_min, min(max(y0, 0.0), 0.95))
    default = (x_min, y_min, 1.0, 1.0)
    if not tokens:
        return default
    pool = list(tokens)
    if page is not None:
        pool = [item for item in pool if item.page == page]
    if not pool:
        pool = list(tokens)
    first_page = min(item.page for item in pool)
    band = [
        item
        for item in pool
        if item.page == first_page and _in_title_block(item, x_min, y_min)
    ]
    if not band:
        return default
    x0, y_lo, x1, y_hi = bbox_from_polygon(band[0].polygon_norm)
    for item in band[1:]:
        left, top, right, bottom = bbox_from_polygon(item.polygon_norm)
        x0 = min(x0, left)
        y_lo = min(y_lo, top)
        x1 = max(x1, right)
        y_hi = max(y_hi, bottom)
    pad = 0.02
    return (
        max(0.0, x0 - pad),
        max(0.0, min(y_lo, y0) - pad),
        min(1.0, x1 + pad),
        min(1.0, y_hi + pad),
    )


def stamp_crop_polygon(
    tokens: Sequence[PageToken] | None = None,
    *,
    page: int | None = None,
    y0: float = _STAMP_Y0,
    media_box: Sequence[float] | None = None,
) -> tuple[tuple[float, float], ...]:
    """Четырёхугольник кропа штампа — вход для ocr_region_* / dual-read."""

    x0, y_lo, x1, y_hi = stamp_crop_box(tokens, page=page, y0=y0, media_box=media_box)
    return ((x0, y_lo), (x1, y_lo), (x1, y_hi), (x0, y_hi))


def _in_title_block(token: PageToken, x_min: float, y_min: float) -> bool:
    left, top, _right, _bottom = bbox_from_polygon(token.polygon_norm)
    return left >= x_min - 1e-6 and top >= y_min - 1e-6


def _stamp_tokens(
    tokens: Sequence[PageToken],
    *,
    media_box: Sequence[float] | None = None,
) -> tuple[PageToken, ...]:
    """Токены основной надписи. На крупном листе это правый нижний угол."""

    first_page = [item for item in tokens if item.page == 1]
    pool: Sequence[PageToken] = first_page or tokens
    x_min, y_min = title_block_origin(media_box)
    bottom = [item for item in pool if _in_title_block(item, x_min, y_min)]
    return tuple(bottom) if bottom else tuple(pool)


def _parse_approval_date(text: str) -> date | None:
    match = _DATE.search(text)
    if match is None:
        return None
    try:
        return datetime(
            int(match.group(3)),
            int(match.group(2)),
            int(match.group(1)),
        ).date()
    except ValueError:
        return None


def _title_block_approval(
    tokens: Sequence[PageToken],
) -> tuple[ApprovalStatus, date | None]:
    """Искать явное заполнение графы утверждения в штампе любого листа.

    Для APPROVED обязательны метка «Утвердил»/«утв.» и ФИО ответственного
    в той же строке. Дата без ФИО, пустая графа, «Согласовано», «ГИП» или
    «подп.» не являются достаточным признаком. Неоднозначность остаётся
    UNKNOWN и далее приводит к CLARIFICATION_REQUIRED.
    """

    by_page: dict[int, list[PageToken]] = {}
    for item in tokens:
        if bbox_from_polygon(item.polygon_norm)[1] < _STAMP_Y0:
            continue
        by_page.setdefault(item.page, []).append(item)

    for page_tokens in by_page.values():
        joined = _join(page_tokens)
        if _NOT_APPROVED.search(joined):
            return ApprovalStatus.NOT_APPROVED, _parse_approval_date(joined)
        for label in page_tokens:
            match = _APPROVAL_LABEL_PREFIX.search(label.text.strip())
            if match is None:
                continue
            left, bottom, _right, _top = bbox_from_polygon(label.polygon_norm)
            values = [match.group(1).strip()] if match.group(1).strip() else []
            for other in page_tokens:
                if other is label:
                    continue
                ox0, oy0, _ox1, _oy1 = bbox_from_polygon(other.polygon_norm)
                if ox0 <= left + 0.01:
                    continue
                if abs(oy0 - bottom) > _APPROVAL_ROW_DY:
                    continue
                if ox0 - left > _APPROVAL_MAX_DX:
                    continue
                values.append(other.text.strip())
            evidence = " ".join(value for value in values if value)
            if _NOT_APPROVED.search(evidence):
                return ApprovalStatus.NOT_APPROVED, _parse_approval_date(evidence)
            if _PERSON_NAME.search(evidence) is not None:
                return ApprovalStatus.APPROVED, _parse_approval_date(evidence)
    return ApprovalStatus.UNKNOWN, None


def _revision_mark(text: str) -> tuple[str | None, str]:
    """Номер редакции и шкала. «Изм» и «корректировка» не одна шкала."""

    match = _REV.search(text)
    if match is None:
        return None, ""
    number = normalize_key_field(match.group(2))
    if not number:
        return None, ""
    word = match.group(1).casefold()
    if word.startswith("изм"):
        return number, "change"
    return number, "correction"


def _designation_is_standard(code: str) -> bool:
    """ГОСТ, СП, сертификат и номер экспертизы — не шифр комплекта."""

    folded = fold_label(code).replace(" ", "")
    if not folded:
        return False
    return _STANDARD_CODE.search(folded) is not None


def _first(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    if match is None:
        return None
    return normalize_key_field(match.group(1))


def _first_project_code(pattern: re.Pattern[str], text: str) -> str | None:
    for match in pattern.finditer(text):
        code = normalize_key_field(match.group(1))
        if code and not _designation_is_standard(code):
            return code
    return None


def _designation(text: str) -> tuple[str | None, bool]:
    """Одно обозначение или большинство. Ничья — шифр не выбран."""

    found: list[str] = []
    for item in _CODE_DESIGNATION.findall(text):
        code = normalize_key_field(item)
        if code and not _designation_is_standard(code):
            found.append(code)
    if not found:
        return None, False
    counts: dict[str, int] = {}
    for item in found:
        counts[item] = counts.get(item, 0) + 1
    best = max(counts.values())
    winners = [key for key, count in counts.items() if count == best]
    if len(winners) == 1:
        return winners[0], False
    return None, True


_SECTION_MARKS: frozenset[str] = frozenset(
    {
        "ПЗ",
        "АР",
        "КР",
        "ОВ",
        "КЖ",
        "ОД",
        "ПЗУ",
        "ИОС",
        "ПОС",
        "ПОД",
        "ЗУ",
        "ППМ",
        "ОДИ",
        "ООС",
        "СПЗУ",
    }
)
_LATIN_SECTION: dict[str, str] = {
    "PZ": "ПЗ",
    "AR": "АР",
    "KR": "КР",
    "OV": "ОВ",
    "KJ": "КЖ",
    "OD": "ОД",
    "PZU": "ПЗУ",
    "IOS": "ИОС",
    "POS": "ПОС",
    "POD": "ПОД",
    "ZU": "ЗУ",
    "PPM": "ППМ",
    "ODI": "ОДИ",
    "OOS": "ООС",
    "SPZU": "СПЗУ",
}
# Словесные марки комплекта, которых нет в шифре матрицы. КМ к КР не сводится.
_SPOKEN_SECTION: dict[str, str] = {
    "ВК": "ИОС2",
    "VK": "ИОС2",
    "ЭОМ": "ИОС1",
    "EOM": "ИОС1",
    "СС": "ИОС5",
    "SS": "ИОС5",
}
_SECTION_TOKEN = re.compile(r"[A-ZА-ЯЁ]{2,8}")


def _filename_stem(filename: str | None) -> str:
    if filename is None:
        return ""
    return filename.replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0].strip()


def section_mark_from_filename(filename: str | None) -> str | None:
    """Одна марка раздела в имени. Две разные марки — не выбираем."""

    stem = _filename_stem(filename)
    if not stem:
        return None
    found: list[str] = []
    for raw in _SECTION_TOKEN.findall(stem.upper().replace("_", " ")):
        mark = (
            raw
            if raw in _SECTION_MARKS
            else _LATIN_SECTION.get(raw) or _SPOKEN_SECTION.get(raw)
        )
        if mark is not None and mark not in found:
            found.append(mark)
    if len(found) != 1:
        return None
    return found[0]


_PATH_PHRASES: tuple[tuple[str, str], ...] = (
    ("пояснительная записка", "ПЗ"),
    ("архитектурные решения", "АР"),
    ("конструктивные и объемно-планировочные", "КР"),
    ("отопление", "ОВ"),
    ("вентиляц", "ОВ"),
    ("овик", "ОВ"),
    ("схема планировочной организации", "ПЗУ"),
    ("проект организации строительства", "ПОС"),
    ("водоснабжен", "ИОС2"),
    ("канализац", "ИОС3"),
    ("водоотведен", "ИОС3"),
    ("электроснабжен", "ИОС1"),
    ("электрооборудован", "ИОС1"),
    ("слаботочн", "ИОС5"),
    ("пожарная сигнализация", "ИОС5"),
    ("генплан", "ПЗУ"),
)


def _mark_from_section_field(section: str | None) -> str | None:
    if not section:
        return None
    raw = section.strip().upper().replace(" ", "")
    if raw in _SECTION_MARKS:
        return raw
    return _LATIN_SECTION.get(raw) or _SPOKEN_SECTION.get(raw)


def _marks_from_index_path(relative_path: str | None) -> frozenset[str]:
    if not relative_path:
        return frozenset()
    folded = relative_path.casefold().replace("ё", "е")
    return frozenset(mark for phrase, mark in _PATH_PHRASES if phrase in folded)


def manifest_section_mark(
    section: str | None, relative_path: str | None
) -> tuple[str | None, bool]:
    """Одна марка из индекса. OTHER и чужие коды — не марка. Спор сигналов — не выбор."""

    from_field = _mark_from_section_field(section)
    from_path = _marks_from_index_path(relative_path)
    if len(from_path) > 1:
        return None, True
    path_mark = next(iter(from_path), None)
    if from_field is not None and path_mark is not None and from_field != path_mark:
        return None, True
    return from_field or path_mark, False


def cipher_from_filename(filename: str | None) -> str | None:
    """Одно обозначение в имени файла. Несколько разных — не выбираем."""

    if filename is None or not filename.strip():
        return None
    stem = _filename_stem(filename)
    text = stem.replace("_", " ")
    found = [
        item
        for item in (
            *(normalize_key_field(raw) for raw in _CODE_DESIGNATION.findall(text)),
            *(normalize_key_field(raw) for raw in _CODE_BARE.findall(text)),
        )
        if item
    ]
    unique = list(dict.fromkeys(found))
    if len(unique) != 1:
        return None
    return unique[0]


def cipher_from_text(text: str) -> str | None:
    """Шифр из уже прочитанного текста. Имя файла сюда не подставляется."""

    labeled = _first_project_code(_CODE, text) or _first_project_code(_CODE_BARE, text)
    if labeled:
        return labeled
    code, _tie = _designation(text)
    return code


def cipher_is_ambiguous(text: str) -> bool:
    """Несколько обозначений без большинства. Подписанный шифр это не спор."""

    if _first_project_code(_CODE, text) or _first_project_code(_CODE_BARE, text):
        return False
    return _designation(text)[1]


def _one_or_conflict(values: list[str]) -> KeyFieldValue:
    unique = list(dict.fromkeys(item.strip() for item in values if item.strip()))
    if not unique:
        return KeyFieldValue(KeyFieldState.ABSENT)
    if len(unique) > 1:
        return KeyFieldValue(KeyFieldState.UNREADABLE)
    return KeyFieldValue(KeyFieldState.FOUND, unique[0])


def _unreadable_fields() -> StampKeyFields:
    blank = KeyFieldValue(KeyFieldState.UNREADABLE)
    return StampKeyFields(
        cipher=blank,
        stage=blank,
        revision=blank,
        sheet=blank,
        room_element=blank,
    )


def _sheet_count_boxes(
    tokens: Sequence[PageToken],
) -> tuple[tuple[float, float, float], ...]:
    boxes: list[tuple[float, float, float]] = []
    for token in tokens:
        if not _SHEET_COUNT.fullmatch(token.text.strip()):
            continue
        left, top, right, _bottom = bbox_from_polygon(token.polygon_norm)
        boxes.append((top, left, right))
    return tuple(boxes)


def _number_beside_label(
    tokens: Sequence[PageToken], top: float, left: float, right: float
) -> str | None:
    """Число справа в строке подписи или сразу под ней. Графа «Листов» не берётся."""

    counts = _sheet_count_boxes(tokens)
    best: tuple[float, str] | None = None
    for token in tokens:
        text = token.text.strip()
        if not _SHEET_NUMBER.fullmatch(text):
            continue
        token_left, token_top, token_right, _token_bottom = bbox_from_polygon(token.polygon_norm)
        same_row = abs(token_top - top) <= 0.03 and token_left >= right - 0.01
        below = 0.0 < (token_top - top) <= 0.06 and token_left <= right and token_right >= left
        if not same_row and not below:
            continue
        distance = abs(token_left - right) + abs(token_top - top)
        nearer_count = any(
            abs(token_left - count_right) + abs(token_top - count_top) < distance
            for count_top, _count_left, count_right in counts
        )
        if nearer_count:
            continue
        if best is None or distance < best[0]:
            best = (distance, text)
    if best is None:
        return None
    return best[1]


def _lower_right(hits: list[tuple[float, float, str]]) -> tuple[str | None, bool]:
    """Нижняя правая подпись. Два разных значения в одной клетке — спор."""

    if not hits:
        return None, False
    hits.sort(key=lambda item: (item[0], item[1]), reverse=True)
    best_y, best_x, best = hits[0]
    for top, left, value in hits[1:]:
        if value == best:
            continue
        if abs(top - best_y) <= 0.03 and abs(left - best_x) <= 0.15:
            return None, True
    return best, False


def _stage_of(raw: str) -> DocStage | None:
    key = fold_label(raw).replace(" ", "").rstrip(".")
    return _STAGE_MAP.get(key)


def _stage_beside_label(
    tokens: Sequence[PageToken], top: float, left: float, right: float
) -> str | None:
    best: tuple[float, str] | None = None
    for token in tokens:
        text = token.text.strip()
        if not _STAGE_WORD.fullmatch(text):
            continue
        token_left, token_top, token_right, _token_bottom = bbox_from_polygon(token.polygon_norm)
        same_row = abs(token_top - top) <= 0.03 and token_left >= right - 0.01
        below = 0.0 < (token_top - top) <= 0.06 and token_left <= right and token_right >= left
        if not same_row and not below:
            continue
        distance = abs(token_left - right) + abs(token_top - top)
        if best is None or distance < best[0]:
            best = (distance, text)
    if best is None:
        return None
    return best[1]


def stage_from_stamp(tokens: Sequence[PageToken]) -> tuple[DocStage | None, bool]:
    """Буква графы «Стадия»: П, Р, И и слова ПД, РД, ИД.

    Буква внутри шифра сюда не входит. Нижняя правая подпись важнее вложенной.
    """

    hits: list[tuple[float, float, str]] = []
    for token in tokens:
        text = token.text.strip()
        left, top, right, _bottom = bbox_from_polygon(token.polygon_norm)
        embedded = list(_STAGE_LABELED.finditer(text))
        if embedded:
            hits.extend((top, left, match.group(1)) for match in embedded)
            continue
        if _STAGE_LABEL.fullmatch(text):
            word = _stage_beside_label(tokens, top, left, right)
            if word is not None:
                hits.append((top, left, word))
    raw, clash = _lower_right(hits)
    if clash or raw is None:
        return None, clash
    stage = _stage_of(raw)
    if stage is None:
        return None, False
    return stage, False


def sheet_from_stamp(tokens: Sequence[PageToken]) -> tuple[str | None, bool]:
    """Номер у подписи «Лист». «Листов 17» не номер. Нижняя правая подпись важнее вложенной.

    Два разных номера в одной клетке — спор, значения нет.
    """

    hits: list[tuple[float, float, str]] = []
    for token in tokens:
        text = token.text.strip()
        if _SHEET_COUNT.fullmatch(text):
            continue
        left, top, right, _bottom = bbox_from_polygon(token.polygon_norm)
        embedded = list(_SHEET.finditer(text))
        if embedded:
            hits.extend((top, left, match.group(1)) for match in embedded)
            continue
        if _SHEET_LABEL.fullmatch(text):
            number = _number_beside_label(tokens, top, left, right)
            if number is not None:
                hits.append((top, left, number))
    return _lower_right(hits)


def _sheet_field(search: str, tokens: Sequence[PageToken]) -> KeyFieldValue:
    if tokens:
        number, clash = sheet_from_stamp(tokens)
        if clash:
            return KeyFieldValue(KeyFieldState.UNREADABLE)
        if number:
            return KeyFieldValue(KeyFieldState.FOUND, number)
        return KeyFieldValue(KeyFieldState.ABSENT)
    return _one_or_conflict(list(_SHEET.findall(search)))


def _fields_from_text(
    search: str, tokens: Sequence[PageToken] = ()
) -> StampKeyFields:
    """Поля одного чтения. Имя файла и второй движок сюда не входят."""

    code = cipher_from_text(search)
    if cipher_is_ambiguous(search):
        cipher = KeyFieldValue(KeyFieldState.UNREADABLE)
    elif code:
        cipher = KeyFieldValue(KeyFieldState.FOUND, code)
    else:
        cipher = KeyFieldValue(KeyFieldState.ABSENT)
    if tokens:
        stamped, stage_clash = stage_from_stamp(tokens)
        if stage_clash:
            stage = KeyFieldValue(KeyFieldState.UNREADABLE)
        elif stamped is not None:
            stage = KeyFieldValue(KeyFieldState.FOUND, stamped.value)
        else:
            stage = KeyFieldValue(KeyFieldState.ABSENT)
    else:
        stamped = _stage_from_text(search, labeled_only=True) or _stage_from_text(
            search, labeled_only=False
        )
        stage = (
            KeyFieldValue(KeyFieldState.FOUND, stamped.value)
            if stamped is not None
            else KeyFieldValue(KeyFieldState.ABSENT)
        )
    rooms = _ROOM_NO.findall(search)
    elements = _ELEMENT_NO.findall(search)
    return StampKeyFields(
        cipher=cipher,
        stage=stage,
        revision=_one_or_conflict([item[1] for item in _REV.findall(search)]),
        sheet=_sheet_field(search, tokens),
        room_element=_one_or_conflict([*rooms, *elements]),
    )


def _agree(left: KeyFieldValue, right: KeyFieldValue) -> KeyFieldValue:
    """Два чтения. Пустое со пустым — нет поля. Разные значения — нечитаемо."""

    if left.state is KeyFieldState.UNREADABLE or right.state is KeyFieldState.UNREADABLE:
        return KeyFieldValue(KeyFieldState.UNREADABLE)
    if left.state is KeyFieldState.ABSENT and right.state is KeyFieldState.ABSENT:
        return left
    if (
        left.state is KeyFieldState.FOUND
        and right.state is KeyFieldState.FOUND
        and left.value == right.value
    ):
        return left
    return KeyFieldValue(KeyFieldState.UNREADABLE)


def _with_filename_stage(fields: StampKeyFields, filename: str | None) -> StampKeyFields:
    named = stage_from_filename(filename) if filename else None
    if named is None:
        return fields
    if fields.stage.state is KeyFieldState.FOUND and fields.stage.value != named.value:
        return replace(fields, stage=KeyFieldValue(KeyFieldState.UNREADABLE))
    if fields.stage.state is KeyFieldState.ABSENT:
        return replace(fields, stage=KeyFieldValue(KeyFieldState.FOUND, named.value))
    return fields


def stamp_key_fields(
    tokens: Sequence[PageToken],
    *,
    filename: str | None = None,
    alternate_ciphers: Sequence[str] = (),
    text_render_agreement: bool | None = None,
    second_text: str | None = None,
    media_box: Sequence[float] | None = None,
) -> StampKeyFields:
    """Шифр, стадия, редакция, лист и номер помещения или элемента.

    Нет подписи — absent. Два разных чтения — unreadable. Пустой второй
    текст (пустой кроп OCR) спор не открывает. Найденное поле не становится
    нарушением и не закрывает порог 0,90.
    """

    if text_render_agreement is False:
        return _unreadable_fields()
    region = _stamp_tokens(tokens, media_box=media_box) if tokens else ()
    pool = region or tuple(tokens)
    search = _join(pool)
    fields = _fields_from_text(search, pool)
    if second_text is not None and second_text.strip():
        other = _fields_from_text(second_text)
        fields = StampKeyFields(
            cipher=_agree(fields.cipher, other.cipher),
            stage=_agree(fields.stage, other.stage),
            revision=_agree(fields.revision, other.revision),
            sheet=_agree(fields.sheet, other.sheet),
            room_element=_agree(fields.room_element, other.room_element),
        )
    if cipher_reads_agree((fields.cipher.value, *alternate_ciphers)) is False:
        fields = replace(fields, cipher=KeyFieldValue(KeyFieldState.UNREADABLE))
    return _with_filename_stage(fields, filename)


def cipher_reads_agree(codes: Sequence[str | None]) -> bool | None:
    """None — меньше двух чтений. False — два разных шифра, код не выбираем."""

    present = [item for item in codes if item]
    if len(present) < 2:
        return None
    return all(item == present[0] for item in present)


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
    """Обработать только явный запрет; положительный статус требует evidence."""

    if _NOT_APPROVED.search(text):
        return ApprovalStatus.NOT_APPROVED, _parse_approval_date(text)
    return ApprovalStatus.UNKNOWN, None


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
    text_render_agreement: bool | None = None,
    injection_clean: bool | None = None,
    alternate_ciphers: Sequence[str] = (),
) -> DocumentPassport:
    """Прочитать паспорт. Не заполняет шифр из имени файла."""

    if _HASH.fullmatch(file_hash) is None:
        raise ValueError("file_hash паспорта обязан быть SHA-256")
    has_text = any(item.text.strip() for item in tokens)
    if layer_kind == "vector" and not has_text:
        layer_kind = "raster"
    region = _stamp_tokens(tokens, media_box=media_box) if tokens else ()
    blob = _join(region)
    full = _join(tokens)
    search = blob or full

    code = cipher_from_text(search)
    ambiguous = code is None and cipher_is_ambiguous(search)
    revision, revision_kind = _revision_mark(search)
    pool = region or tuple(tokens)
    sheet, sheet_clash = sheet_from_stamp(pool) if tokens else (None, False)
    column_stage, stage_clash = stage_from_stamp(pool) if tokens else (None, False)
    stage = column_stage or _stage_from_text(search, labeled_only=True) or _stage_from_text(
        search, labeled_only=False
    )
    name_stage = stage_from_filename(filename) if filename else None
    needs = False
    reason: str | None = None
    if sheet_clash:
        sheet = None
        needs = True
        reason = "в основной надписи два разных номера листа"
    if stage_clash:
        stage = None
        needs = True
        reason = reason or "в основной надписи две разные стадии"
    if cipher_reads_agree((code, *alternate_ciphers)) is False:
        needs = True
        reason = "шифр vector, eslav и Tesseract не совпали"
        code = None
    if text_render_agreement is False:
        needs = True
        reason = "текстовый слой расходится с растром: скрытый или перекрытый текст"
        code = None
        revision = None
        revision_kind = ""
        sheet = None
        stage = None
    if stage is not None and name_stage is not None and stage is not name_stage:
        needs = True
        reason = (
            f"стадия в штампе {stage.value}, в имени файла {name_stage.value}: "
            "эталон не выбирается"
        )
        stage = None
    elif stage is None and name_stage is not None and not stage_clash:
        stage = name_stage
    if has_text and code is None and text_render_agreement is not False:
        needs = True
        reason = reason or (
            "несколько обозначений без большинства, шифр не выбран"
            if ambiguous
            else "шифр в основной надписи не найден"
        )
    basis = ApprovalBasis.UNPROVEN
    approval, approval_date = _approval(search)
    if approval is not ApprovalStatus.UNKNOWN:
        basis = ApprovalBasis.TITLE_BLOCK
    if approval is ApprovalStatus.UNKNOWN:
        later, later_date = _title_block_approval(tokens)
        if later is not ApprovalStatus.UNKNOWN:
            approval, approval_date = later, later_date or approval_date
            basis = ApprovalBasis.TITLE_BLOCK
    if text_render_agreement is False:
        approval, approval_date = ApprovalStatus.UNKNOWN, None
        basis = ApprovalBasis.UNPROVEN
    name_code = cipher_from_filename(filename)
    filename_discipline = section_mark_from_filename(filename)
    if code is not None and name_code is not None and code != name_code:
        needs = True
        reason = reason or (
            f"шифр в штампе {code}, в имени файла {name_code}: имя не подменяет штамп"
        )
        identity_code: str | None = code
        code_basis: str | None = "STAMP"
    elif code is not None:
        identity_code = code
        code_basis = "STAMP"
    elif name_code is not None:
        identity_code = name_code
        code_basis = "FILENAME"
    elif filename_discipline is not None:
        identity_code = _filename_stem(filename) or None
        code_basis = "FILENAME" if identity_code else None
    else:
        identity_code = None
        code_basis = None
        filename_discipline = None
    filled = sum(1 for item in (code, revision, sheet) if item)
    confidence = None
    if has_text:
        confidence = filled / len(KEY_FIELDS)
    if crop_box is None:
        crop_box = stamp_crop_box(tokens if tokens else None, media_box=media_box)
    return DocumentPassport(
        file_id=file_id,
        file_hash=file_hash,
        doc_stage=stage,
        discipline=filename_discipline if code is None else None,
        pages=pages,
        layer_kind=layer_kind,
        document_code=code,
        identity_code=identity_code,
        code_basis=code_basis,
        revision=revision,
        revision_kind=revision_kind,
        sheet=sheet,
        approval_status=approval,
        approval_basis=basis,
        approval_date=approval_date,
        object_id=object_id,
        rotate=rotate,
        media_box=media_box,
        crop_box=crop_box,
        has_embedded_text=has_text,
        text_render_agreement=text_render_agreement,
        injection_clean=injection_clean,
        extraction_confidence=confidence,
        needs_clarification=needs,
        clarification_reason=reason,
    )


def _note_manifest(passport: DocumentPassport, note: str) -> DocumentPassport:
    reason = passport.clarification_reason
    if reason is None:
        reason = note
    elif note not in reason:
        reason = f"{reason}; {note}"
    return replace(passport, needs_clarification=True, clarification_reason=reason)


def _manifest_identity(
    filename: str | None, relative_path: str | None, file_id: str
) -> str:
    """Ключ тома. Голый stem и марка раздела склеивают разные папки."""

    stem = _filename_stem(filename) or file_id
    if relative_path:
        normalized = relative_path.replace("\\", "/").strip("/")
        leaf = _filename_stem(normalized.rsplit("/", 1)[-1]) or stem
        parent = normalized.rsplit("/", 1)[0] if "/" in normalized else ""
        body = f"{parent}/{leaf}" if parent else leaf
    else:
        body = stem
    return f"{body}#{file_id}"


def apply_manifest_section(
    passport: DocumentPassport,
    *,
    section: str | None,
    relative_path: str | None,
    filename: str | None,
) -> DocumentPassport:
    """Раздел индекса в discipline. Марка не становится общим identity."""

    mark, conflict = manifest_section_mark(section, relative_path)
    if conflict:
        return _note_manifest(
            passport, "раздел индекса неоднозначен и не подменяет шифр"
        )
    if mark is None or passport.discipline == mark:
        return passport
    if passport.discipline is not None:
        return _note_manifest(
            passport, f"раздел индекса {mark} не подменяет {passport.discipline}"
        )
    identity = passport.identity_code
    basis = passport.code_basis
    if identity is None:
        identity = _manifest_identity(filename, relative_path, passport.file_id)
        basis = "MANIFEST_PATH"
    return replace(
        passport,
        discipline=mark,
        identity_code=identity,
        code_basis=basis,
    )
