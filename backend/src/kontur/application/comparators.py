"""Детерминированные компараторы. Никакая модель сюда не входит (ADR-0001).

Гейт H: поддерживаются все операторы matrix/rule.schema.json:
  numeric : delta, eq, ne, lt, le, gt, ge, range
  set     : in_set, not_in_set
  string  : class_not_lower
  special : present
"""

from __future__ import annotations

from dataclasses import dataclass

from kontur.application.normalize import quantize
from kontur.domain.statuses import FindingStatus


@dataclass(frozen=True, slots=True)
class Comparison:
    status: FindingStatus
    expected: str | float | bool
    actual: str | float | bool
    delta: str | float
    rationale: str

    def __post_init__(self) -> None:
        if self.status in {FindingStatus.CONFIRMED_VIOLATION, FindingStatus.NEGATIVE_VERIFIED}:
            raise ValueError("компаратор не имеет права вынести человеческий вердикт")


# ── internal helpers ──────────────────────────────────────────────────────────

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


def _comparator_dict(rule: dict[str, object]) -> dict[str, object]:
    comparator = rule.get("comparator")
    if not isinstance(comparator, dict):
        raise TypeError("у правила нет comparator")
    return comparator


# ── numeric operators ─────────────────────────────────────────────────────────

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


def compare_ordering(expected: float, actual: float, rule: dict[str, object]) -> Comparison:
    """Операторы eq, ne, lt, le, gt, ge.

    Если comparator.value задан — actual сравнивается с ним (фиксированный порог);
    иначе сравнивается с expected (PD↔RD).
    """
    c = _comparator_dict(rule)
    operator = str(c.get("operator", ""))
    raw_value = c.get("value")
    ref: float = float(raw_value) if isinstance(raw_value, int | float) else expected
    unit = str(rule.get("unit") or "")

    results: dict[str, bool] = {
        "eq": actual == ref,
        "ne": actual != ref,
        "lt": actual < ref,
        "le": actual <= ref,
        "gt": actual > ref,
        "ge": actual >= ref,
    }
    ok = results.get(operator)
    if ok is None:
        raise ValueError(f"compare_ordering: неизвестный operator {operator!r}")
    delta = float(actual - ref)
    verdict = "выполнено" if ok else "нарушение"
    return Comparison(
        status=FindingStatus.AUTO_NO_DIFFERENCE if ok else FindingStatus.CANDIDATE,
        expected=ref,
        actual=actual,
        delta=delta,
        rationale=f"{actual} {unit} {operator} {ref} {unit}: {verdict}",
    )


def compare_range(expected: float, actual: float, rule: dict[str, object]) -> Comparison:
    """Оператор range: actual в [min_value, max_value].

    Оба предела опциональны — отсутствие предела снимает ограничение с той стороны.
    """
    c = _comparator_dict(rule)
    min_v = c.get("min_value")
    max_v = c.get("max_value")
    min_f: float | None = float(min_v) if isinstance(min_v, int | float) else None
    max_f: float | None = float(max_v) if isinstance(max_v, int | float) else None
    unit = str(rule.get("unit") or "")

    in_range = True
    reason_parts: list[str] = []
    if min_f is not None and actual < min_f:
        in_range = False
        reason_parts.append(f"{actual} {unit} < нижняя граница {min_f} {unit}")
    if max_f is not None and actual > max_f:
        in_range = False
        reason_parts.append(f"{actual} {unit} > верхняя граница {max_f} {unit}")
    if in_range:
        reason_parts.append(f"{actual} {unit} в диапазоне [{min_f}, {max_f}] {unit}")

    delta = float(actual - expected)
    return Comparison(
        status=FindingStatus.AUTO_NO_DIFFERENCE if in_range else FindingStatus.CANDIDATE,
        expected=expected,
        actual=actual,
        delta=delta,
        rationale="; ".join(reason_parts),
    )


# ── set operators ─────────────────────────────────────────────────────────────

def compare_set_membership(actual_raw: object, rule: dict[str, object]) -> Comparison:
    """Операторы in_set и not_in_set.

    comparator.value — список допустимых строк.
    Membership проверяется по строковому представлению actual после strip/upper.
    """
    c = _comparator_dict(rule)
    operator = str(c.get("operator", ""))
    raw_set = c.get("value")
    allowed: set[str] = {
        str(v).strip().upper()
        for v in (raw_set if isinstance(raw_set, list) else [])
    }
    actual_str = str(actual_raw).strip().upper()
    in_set = actual_str in allowed
    ok = in_set if operator == "in_set" else not in_set
    verdict = "выполнено" if ok else "нарушение"
    membership = "присутствует" if in_set else "отсутствует"
    return Comparison(
        status=FindingStatus.AUTO_NO_DIFFERENCE if ok else FindingStatus.CANDIDATE,
        expected=1.0 if operator == "in_set" else 0.0,
        actual=1.0 if in_set else 0.0,
        delta=0.0 if ok else -1.0,
        rationale=f"{actual_raw!r} {membership} в допустимом множестве: {verdict}",
    )


# ── ordered-class operator ────────────────────────────────────────────────────

def _class_rank(value: str, ordered: list[str]) -> int:
    """Позиция значения в упорядоченном списке. Нечувствительно к пробелам."""
    normalized = value.strip().upper()
    for idx, item in enumerate(ordered):
        if str(item).strip().upper() == normalized:
            return idx
    raise ValueError(
        f"значение {value!r} не найдено в упорядоченном списке {ordered!r}"
    )


def compare_class_not_lower(
    expected: str,
    actual: str,
    rule: dict[str, object],
) -> Comparison:
    """Оператор class_not_lower: понижение класса = CANDIDATE; равенство/повышение = AUTO.

    comparator.value — упорядоченный список от худшего к лучшему.
    Понижение: act_rank < exp_rank.
    Повышение класса не является нарушением (NO_VIOLATION в gold KR-055).
    """
    c = _comparator_dict(rule)
    raw_ordered = c.get("value")
    ordered: list[str] = [
        str(v) for v in (raw_ordered if isinstance(raw_ordered, list) else [])
    ]
    if not ordered:
        raise ValueError(
            f"{rule.get('code')}: class_not_lower требует непустого comparator.value"
        )

    exp_rank = _class_rank(str(expected), ordered)
    act_rank = _class_rank(str(actual), ordered)
    delta = float(act_rank - exp_rank)
    lowered = act_rank < exp_rank  # фактический класс ниже проектного

    if lowered:
        return Comparison(
            status=FindingStatus.CANDIDATE,
            expected=float(exp_rank),
            actual=float(act_rank),
            delta=delta,
            rationale=(
                f"понижение класса: {expected} (позиция {exp_rank}) → "
                f"{actual} (позиция {act_rank})"
            ),
        )
    return Comparison(
        status=FindingStatus.AUTO_NO_DIFFERENCE,
        expected=float(exp_rank),
        actual=float(act_rank),
        delta=delta,
        rationale=f"класс не понижен: {expected} → {actual}",
    )


# ── exact text field operator ─────────────────────────────────────────────────

def compare_exact_field(expected: str, actual: str, rule: dict[str, object]) -> Comparison:
    """Сравнение строкового поля без приведения к числу."""

    operator = str(_comparator_dict(rule).get("operator", "eq"))
    if operator not in {"eq", "ne"}:
        raise ValueError(f"exact_field: неизвестный operator {operator!r}")
    equal = expected == actual
    ok = equal if operator == "eq" else not equal
    return Comparison(
        status=FindingStatus.AUTO_NO_DIFFERENCE if ok else FindingStatus.CANDIDATE,
        expected=expected,
        actual=actual,
        delta=0.0 if ok else 1.0,
        rationale=(
            f"текстовое поле {operator}: {expected!r} и {actual!r}: "
            f"{"совпадает" if ok else "расходится"}"
        ),
    )


# ── presence operator ─────────────────────────────────────────────────────────

def compare_presence(actual: object, rule: dict[str, object]) -> Comparison:
    """Оператор present: элемент обязан присутствовать.

    actual — любое значение; отсутствие/пустота/None = нарушение.
    """
    present = bool(actual) if actual is not None else False
    return Comparison(
        status=FindingStatus.AUTO_NO_DIFFERENCE if present else FindingStatus.MISSING_EVIDENCE,
        expected=1.0,
        actual=1.0 if present else 0.0,
        delta=0.0 if present else -1.0,
        rationale="элемент присутствует" if present else "элемент отсутствует: доказательство не сформировано",
    )


# ── router ────────────────────────────────────────────────────────────────────

#: Множества операторов для быстрой проверки совместимости с extractor-типом.
NUMERIC_OPERATORS: frozenset[str] = frozenset(
    {"delta", "eq", "ne", "lt", "le", "gt", "ge", "range"}
)
SET_OPERATORS: frozenset[str] = frozenset({"in_set", "not_in_set"})
STRING_OPERATORS: frozenset[str] = frozenset({"class_not_lower"})
PRESENCE_OPERATORS: frozenset[str] = frozenset({"present"})
ALL_OPERATORS: frozenset[str] = (
    NUMERIC_OPERATORS | SET_OPERATORS | STRING_OPERATORS | PRESENCE_OPERATORS
)


def compare_values(expected: object, actual: object, rule: dict[str, object]) -> Comparison:
    """Единая точка входа матричного движка.

    Маршрутизирует по comparator.operator. Не содержит модели — только
    детерминированная логика (ADR-0001). Неизвестный operator → ValueError.
    """
    c = _comparator_dict(rule)
    operator = str(c.get("operator") or "")

    if operator == "delta":
        return compare_delta(
            float(expected),  # type: ignore[arg-type]
            float(actual),  # type: ignore[arg-type]
            rule,
        )
    if operator in {"eq", "ne"} and isinstance(expected, str) and isinstance(actual, str):
        return compare_exact_field(expected, actual, rule)
    if operator in {"eq", "ne", "lt", "le", "gt", "ge"}:
        return compare_ordering(
            float(expected),  # type: ignore[arg-type]
            float(actual),  # type: ignore[arg-type]
            rule,
        )
    if operator == "range":
        return compare_range(
            float(expected),  # type: ignore[arg-type]
            float(actual),  # type: ignore[arg-type]
            rule,
        )
    if operator in SET_OPERATORS:
        return compare_set_membership(actual, rule)
    if operator == "class_not_lower":
        return compare_class_not_lower(str(expected), str(actual), rule)
    if operator == "present":
        return compare_presence(actual, rule)
    raise ValueError(
        f"{rule.get('code')}: operator {operator!r} не реализован; "
        f"поддерживаются: {sorted(ALL_OPERATORS)}"
    )
