"""OCR bake-off: выбор production primary и независимого verifier (гейт I, 24.09).

Результат бейк-оффа — константа GATE_I_DECISION. Живых вызовов внешних API
здесь нет: файл документирует принятое решение и экспортирует
конфигурацию для остального кода.

Ранжирование (синтетика + корпус TRAIN_PUBLIC):
  Вектор pdfium        CA ≥ 0.999  — цифровые PDF без артефактов растеризации.
  Tesseract-5 регион   CA ≥ 0.970  — отсканированные страницы, регион-кроп ≥3×.
  Tesseract-5 полная   CA ≈ 0.940  — многоколоночные таблицы ТЭП, ниже порога.
  VLM (GOT-OCR2_0)     не измерен  — нет frozen-validation; нарушает ADR-0001.

Выбор: primary=VECTOR_PDFIUM, verifier=RASTER_REGION_CROP.
Stop-condition (24.09): CA verifier < 0.95 → усиливать region crops
и классический OCR, не дообучать большую VLM.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

# ── Константы ────────────────────────────────────────────────────────────────────

#: Порог бейк-оффа: ниже — система неприемлема (ТЗ § 14.3).
CA_GATE_I_THRESHOLD: float = 0.97

#: Ожидаемая CA основного пути (вектор pdfium) на цифровых PDF.
CA_PRIMARY_EXPECTED: float = 0.999

#: Нижняя граница CA верификатора на отсканированных регион-кропах.
CA_VERIFIER_FLOOR: float = 0.970


# ── OCR-пути ────────────────────────────────────────────────────────────────────

class OcrPath(Enum):
    """Доступные пути OCR по убыванию предпочтения."""

    VECTOR_PDFIUM = auto()
    """pdfium pypdfium2: вектор текстового слоя. CA≈1.00, latency<5 мс/стр."""

    RASTER_REGION_CROP = auto()
    """Tesseract-5 на регион-кропе ×3. CA≥0.97 на чистом скане, latency~80 мс/кроп."""


# ── Решение бейк-оффа ────────────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class BakeoffDecision:
    """Зафиксированное решение по выбору OCR-стека (гейт I)."""

    primary: OcrPath
    verifier: OcrPath
    ca_threshold: float
    ca_primary_expected: float
    ca_verifier_floor: float
    rationale: str


GATE_I_DECISION: BakeoffDecision = BakeoffDecision(
    primary=OcrPath.VECTOR_PDFIUM,
    verifier=OcrPath.RASTER_REGION_CROP,
    ca_threshold=CA_GATE_I_THRESHOLD,
    ca_primary_expected=CA_PRIMARY_EXPECTED,
    ca_verifier_floor=CA_VERIFIER_FLOOR,
    rationale=(
        "pdfium-vector: CA≥0.999 на цифровых PDF — безусловный основной путь. "
        "Tesseract-5 region-crop ×3: CA≥0.970 на отсканированных страницах — "
        "верификатор для dual_read_required=True. "
        "Tesseract full: CA≈0.940 — отвергнут (<порога). "
        "VLM отложен: нет frozen-validation; нарушает ADR-0001 (grounded-token)."
    ),
)


# ── Выбор стратегии ────────────────────────────────────────────────────────────────


def needs_raster_verifier(layer_kind: str) -> bool:
    """Определить, нужен ли верификатор на растровой основе.

    Вектор: верификатор не нужен для clean-page extract,
    но включается при dual_read_required=True в правиле.
    Растр: верификатор включается всегда.
    """
    return layer_kind == "raster"


def primary_path_for(layer_kind: str) -> OcrPath:  # noqa: ARG001
    """Основной путь по типу слоя документа.

    Для вектора и гибрида — pdfium-vector (уже прочитан; рестрейн не нужен).
    Для чистого растра — тоже pdfium, но has_embedded_text=False,
    токены пусты, и верификатор становится единственным источником.
    """
    return OcrPath.VECTOR_PDFIUM
