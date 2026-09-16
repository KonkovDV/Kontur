"""Детерминированные компараторы. Никакая модель сюда не входит (ADR-0001)."""

from __future__ import annotations

from dataclasses import dataclass

from kontur.application.normalize import quantize
from kontur.domain.statuses import FindingStatus


@dataclass(frozen=True, slots=True)
class Comparison:
    status: FindingStatus
    expected: float
    actual: float
    delta: float
    rationale: str

    def __post_init__(self) -> None:
        if self.status in {FindingStatus.CONFIRMED_VIOLATION, FindingStatus.NEGATIVE_VERIFIED}:
            raise ValueError("компаратор не имеет права вынести человеческий вердикт")


def _tolerance(rule: dict[str, object]) -> tuple[float | None, float | None, str]:
    comparator = rule.get("comparator")
    if not isinstance(comparator, dict):
        raise TypeError("у правила нет comparator")
    abs_tol = comparator.get("tolerance_abs")
    rel_tol = comparator.get("tolerance_rel")
    rounding = str(comparator.get("rounding") or "half_up")
    abs_value = float(abs_tol) if isinstance(abs_tol, int | float) else None
    rel_value = float(rel_tol) if isinstance(rel_tol, int | float) else None
    return abs_value, rel_value, rounding


def compare_delta(expected: float, actual: float, rule: dict[str, object]) -> Comparison:
    """Расхождение относительно допуска. Ноль допуска — любое отличие = кандидат."""

    abs_tol, rel_tol, rounding = _tolerance(rule)
    left = quantize(expected, rounding)
    right = quantize(actual, rounding)
    delta = float(right - left)
    distance = abs(delta)
    within = False
    if abs_tol is not None and distance <= abs_tol:
        within = True
    if rel_tol is not None:
        scale = max(abs(float(left)), abs(float(right)), 1e-12)
        if distance / scale <= rel_tol:
            within = True
    if abs_tol is None and rel_tol is None:
        within = left == right
    unit = str(rule.get("unit") or "")
    if within:
        return Comparison(
            status=FindingStatus.AUTO_NO_DIFFERENCE,
            expected=float(left),
            actual=float(right),
            delta=delta,
            rationale=f"значения совпадают с учётом допуска ({expected} {unit} и {actual} {unit})",
        )
    return Comparison(
        status=FindingStatus.CANDIDATE,
        expected=float(left),
        actual=float(right),
        delta=delta,
        rationale=(
            f"расхождение {delta} {unit}: ожидалось {float(left)}, получено {float(right)}"
        ),
    )


def compare_values(expected: float, actual: float, rule: dict[str, object]) -> Comparison:
    comparator = rule.get("comparator")
    if not isinstance(comparator, dict):
        raise TypeError("у правила нет comparator")
    operator = comparator.get("operator")
    if operator != "delta":
        raise ValueError(
            f"{rule.get('code')}: слайс исполняет operator=delta, получено {operator!r}"
        )
    return compare_delta(expected, actual, rule)
