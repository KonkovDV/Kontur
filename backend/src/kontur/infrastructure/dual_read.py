"""Двойное чтение: primary + verifier для правил с dual_read_required=True.

Только числовые значения: текстовые и enum-поля двойного
чтения не требуют.

N.B. Верификатор-токены в продакшне поставляет Tesseract-5 region-crop;
здесь у нас только интерфейс обработки двух наборов токенов.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from kontur.application.extractors.number import PageToken


# ── Результат ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class DualReadResult:
    """Итог двойного чтения.

    agrees:
      True  — оба источника вернули одинаковое нормализованное значение.
      False — значения расходятся (или один источник пуст); используется ABSTAIN.

    final_value:
      primary_value если agrees=True;
      None если agrees=False (результат становится ABSTAIN).
    """

    primary_value: float | None
    verifier_value: float | None
    agrees: bool
    final_value: float | None
    rationale: str


# ── Нормализация числа ─────────────────────────────────────────────────────────────────


def _parse_number(raw: str) -> float | None:
    """Попытка разобрать float из токена с русской нотацией (запятая = точка)."""
    text = (
        unicodedata.normalize("NFC", raw)
        .strip()
        .replace(",", ".")
        .replace("\u00a0", "")
        .replace("\u202f", "")
    )
    try:
        return float(text)
    except ValueError:
        return None


def _find_value_after_anchor(
    tokens: tuple[PageToken, ...],
    anchor_words: tuple[str, ...],
) -> float | None:
    """Найти первое число, стоящее после токенов якоря.

    Сравниваем токены якоря с lowercased-вариантом, но NFC обязательно.
    """
    if not tokens or not anchor_words:
        return None
    anchor = tuple(
        unicodedata.normalize("NFC", w).lower().strip() for w in anchor_words
    )
    n = len(anchor)
    texts = [
        unicodedata.normalize("NFC", t.text).lower().strip() for t in tokens
    ]
    total = len(tokens)
    for start in range(total - n + 1):
        if tuple(texts[start : start + n]) == anchor:
            for i in range(start + n, total):
                val = _parse_number(tokens[i].text)
                if val is not None:
                    return val
    return None


# ── Двойное чтение ────────────────────────────────────────────────────────────────


def dual_read_number(
    primary_tokens: tuple[PageToken, ...],
    verifier_tokens: tuple[PageToken, ...],
    anchor_words: tuple[str, ...],
    *,
    dual_read_required: bool = True,
    tolerance: float = 0.0,
) -> DualReadResult:
    """Выполнить двойное чтение числового значения.

    Args:
        primary_tokens: токены основного пути (pdfium-vector).
        verifier_tokens: токены верификатора (tesseract region-crop).
        anchor_words: слова якоря для поиска значения.
        dual_read_required: если False — верификатор пропускается,
            agrees=True при наличии primary_value.
        tolerance: абсолютная погрешность сравнения (0.0 = строгое равенство).
    """
    p_val = _find_value_after_anchor(primary_tokens, anchor_words)

    if not dual_read_required:
        return DualReadResult(
            primary_value=p_val,
            verifier_value=None,
            agrees=p_val is not None,
            final_value=p_val,
            rationale="dual_read not required; primary only",
        )

    v_val = _find_value_after_anchor(verifier_tokens, anchor_words)

    if p_val is None and v_val is None:
        return DualReadResult(
            primary_value=None,
            verifier_value=None,
            agrees=False,
            final_value=None,
            rationale="both reads returned None",
        )

    if p_val is None or v_val is None:
        return DualReadResult(
            primary_value=p_val,
            verifier_value=v_val,
            agrees=False,
            final_value=None,
            rationale="one read returned None",
        )

    diff = abs(p_val - v_val)
    if diff <= tolerance:
        return DualReadResult(
            primary_value=p_val,
            verifier_value=v_val,
            agrees=True,
            final_value=p_val,
            rationale=f"reads agree: |{p_val} - {v_val}| = {diff:.6g} <= {tolerance}",
        )

    return DualReadResult(
        primary_value=p_val,
        verifier_value=v_val,
        agrees=False,
        final_value=None,
        rationale=f"reads disagree: |{p_val} - {v_val}| = {diff:.6g} > {tolerance}",
    )
