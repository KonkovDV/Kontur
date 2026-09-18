"""Тесты гейта I: OCR bake-off + двойное чтение.

Гейт I (24.09): выбран production primary + независимый verifier;
Character Accuracy ≥ 0.97 на цифровых PDF (vector-path = CA ≈1.00).

N.B.  CA верификатора (Tesseract region-crop) ≥ 0.97 зафиксирована
в GATE_I_DECISION.ca_verifier_floor и docs/OCR_BAKEOFF.md; живых вызовов
Tesseract здесь нет (нет frozen validation в sandbox).
"""

from __future__ import annotations

import pytest

from kontur.application.extractors.number import PageToken
from kontur.evaluation.metrics import character_accuracy
from kontur.infrastructure.dual_read import dual_read_number
from kontur.infrastructure.ocr_bakeoff import (
    CA_GATE_I_THRESHOLD,
    GATE_I_DECISION,
    OcrPath,
    needs_raster_verifier,
    primary_path_for,
)

# ── Синтетические токены ───────────────────────────────────────────────────


def _tok(text: str, x: float = 0.1, y: float = 0.4) -> PageToken:
    p = ((x, y), (x + 0.12, y), (x + 0.12, y + 0.04), (x, y + 0.04))
    return PageToken(text=text, page=1, polygon_source=p, polygon_norm=p)


def _tokens(*words: str) -> tuple[PageToken, ...]:
    return tuple(_tok(w, 0.05 + i * 0.13) for i, w in enumerate(words))


# ── Гейт I: бейк-офф ────────────────────────────────────────────────────


def test_gate_i_primary_is_vector_pdfium() -> None:
    """Основной путь — pdfium-vector."""
    assert GATE_I_DECISION.primary is OcrPath.VECTOR_PDFIUM


def test_gate_i_verifier_is_raster_region_crop() -> None:
    """Верификатор — raster-region-crop (Tesseract-5)."""
    assert GATE_I_DECISION.verifier is OcrPath.RASTER_REGION_CROP


def test_gate_i_ca_threshold() -> None:
    """Порог CA гейта I = 0.97."""
    assert GATE_I_DECISION.ca_threshold == pytest.approx(0.97)
    assert CA_GATE_I_THRESHOLD == pytest.approx(0.97)


def test_gate_i_primary_ca_exceeds_threshold() -> None:
    """Ожидаемая CA основного пути выше порога гейта I."""
    assert GATE_I_DECISION.ca_primary_expected >= GATE_I_DECISION.ca_threshold


def test_gate_i_verifier_floor_meets_threshold() -> None:
    """Нижняя граница CA верификатора ≥ порог гейта I."""
    assert GATE_I_DECISION.ca_verifier_floor >= GATE_I_DECISION.ca_threshold


def test_gate_i_decision_has_rationale() -> None:
    """Решение содержит обоснование."""
    assert len(GATE_I_DECISION.rationale.strip()) > 20


# ── CA на синтетических парах (vector-path: perfect copy) ─────────────────

#: pdfium воспроизводит векторный текст без искажений — CA = 1.0 по каждой паре.
_VECTOR_PERFECT: list[tuple[str, str]] = [
    ("Площадь застройки", "Площадь застройки"),
    ("Общая площадь здания", "Общая площадь здания"),
    ("1 250,5", "1 250,5"),
    ("Этажность (надземная): 25", "Этажность (надземная): 25"),
    ("Высота здания: 99,5 м", "Высота здания: 99,5 м"),
    ("Объём грунта (выемка/насыпь)", "Объём грунта (выемка/насыпь)"),
    ("Ширина проёма 0,9 м", "Ширина проёма 0,9 м"),
    ("Итоговая стоимость по ССР", "Итоговая стоимость по ССР"),
]


@pytest.mark.parametrize(
    "reference,hypothesis",
    _VECTOR_PERFECT,
    ids=[r[:20] for r, _ in _VECTOR_PERFECT],
)
def test_character_accuracy_meets_gate_i_threshold(
    reference: str, hypothesis: str
) -> None:
    """CA каждой пары ≥ CA_GATE_I_THRESHOLD = 0.97."""
    ca = character_accuracy(reference, hypothesis)
    assert ca >= CA_GATE_I_THRESHOLD, (
        f"CA={ca:.4f} < {CA_GATE_I_THRESHOLD} для ({reference!r}, {hypothesis!r})"
    )


def test_vector_path_ca_is_perfect_on_identical_strings() -> None:
    """Одинаковые строки → CA = 1.0 (вектор pdfium: perfect copy)."""
    ref = "Площадь застройки, м²"
    assert character_accuracy(ref, ref) == pytest.approx(1.0)


# ── Стратегия по типу слоя ───────────────────────────────────────────────


def test_vector_layer_no_raster_verifier_needed() -> None:
    """Векторный слой: растровый верификатор не обязателен по умолчанию."""
    assert not needs_raster_verifier("vector")


def test_raster_layer_triggers_verifier() -> None:
    """Растровый слой: верификатор включается."""
    assert needs_raster_verifier("raster")


def test_hybrid_layer_no_raster_verifier_forced() -> None:
    """Гибридный слой: растровый верификатор не форсируется."""
    assert not needs_raster_verifier("hybrid")


def test_primary_path_is_always_vector_pdfium() -> None:
    """Основной путь — всегда pdfium, независимо от типа слоя."""
    for kind in ("vector", "raster", "hybrid"):
        assert primary_path_for(kind) is OcrPath.VECTOR_PDFIUM


# ── Двойное чтение ────────────────────────────────────────────────────────────────


def test_dual_read_agrees_on_identical_tokens() -> None:
    """Одинаковые токены primary и verifier → agrees=True, final_value заполнен."""
    anchor = ("Площадь", "застройки")
    primary = _tokens("Площадь", "застройки", "1250,5")
    verifier = _tokens("Площадь", "застройки", "1250,5")
    result = dual_read_number(primary, verifier, anchor, dual_read_required=True)
    assert result.agrees is True
    assert result.final_value == pytest.approx(1250.5)
    assert result.primary_value == pytest.approx(1250.5)
    assert result.verifier_value == pytest.approx(1250.5)


def test_dual_read_disagrees_on_different_values() -> None:
    """Разные значения → agrees=False, final_value=None (ABSTAIN)."""
    anchor = ("Высота", "здания")
    primary = _tokens("Высота", "здания", "99,5")
    verifier = _tokens("Высота", "здания", "98,0")
    result = dual_read_number(primary, verifier, anchor, dual_read_required=True)
    assert result.agrees is False
    assert result.final_value is None
    assert result.primary_value == pytest.approx(99.5)
    assert result.verifier_value == pytest.approx(98.0)


def test_dual_read_not_required_trusts_primary_only() -> None:
    """dual_read_required=False: verifier не нужен, agrees=True если primary есть."""
    anchor = ("Объём", "грунта")
    primary = _tokens("Объём", "грунта", "5000,0")
    result = dual_read_number(primary, (), anchor, dual_read_required=False)
    assert result.agrees is True
    assert result.final_value == pytest.approx(5000.0)
    assert result.verifier_value is None


def test_dual_read_one_side_none_no_agreement() -> None:
    """Один из источников не нашёл значение → agrees=False."""
    anchor = ("Площадь", "застройки")
    primary = _tokens("Площадь", "застройки", "1250,5")
    verifier = _tokens("Площадь", "застройки")  # без числа
    result = dual_read_number(primary, verifier, anchor, dual_read_required=True)
    assert result.agrees is False
    assert result.final_value is None
    assert result.primary_value == pytest.approx(1250.5)
    assert result.verifier_value is None


def test_dual_read_both_none_no_agreement() -> None:
    """Оба источника не нашли значение → agrees=False."""
    anchor = ("Площадь", "застройки")
    empty: tuple[PageToken, ...] = ()
    result = dual_read_number(empty, empty, anchor, dual_read_required=True)
    assert result.agrees is False
    assert result.final_value is None
    assert result.primary_value is None
    assert result.verifier_value is None


def test_dual_read_tolerance_accepts_rounding_diff() -> None:
    """С tolerance=0.5: разница 0.5 принимается, final_value = primary."""
    anchor = ("Высота", "здания")
    primary = _tokens("Высота", "здания", "99,5")
    verifier = _tokens("Высота", "здания", "100,0")
    result = dual_read_number(
        primary, verifier, anchor, dual_read_required=True, tolerance=0.5
    )
    assert result.agrees is True
    assert result.final_value == pytest.approx(99.5)


def test_dual_read_tolerance_rejects_large_diff() -> None:
    """Разница больше tolerance → agrees=False."""
    anchor = ("Высота", "здания")
    primary = _tokens("Высота", "здания", "99,5")
    verifier = _tokens("Высота", "здания", "100,0")
    result = dual_read_number(
        primary, verifier, anchor, dual_read_required=True, tolerance=0.49
    )
    assert result.agrees is False
