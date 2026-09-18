"""Gate J: recall на frozen val corpus (IOS4-078, IOS4-079).

CKI-безопасно: без KONTUR_FROZEN_VAL_PATH — skip.
Цифры не публикуются до закрытия GAP-IOS4-VAL.

Порог: recall ≥ 0.80 по нижней границе Wilson (TZ п. 14.3).
"""
from __future__ import annotations

import pytest

from kontur.evaluation.metrics import TZ_THRESHOLDS, meets_threshold
from kontur.evaluation.recall import compute_recall

# Только эти правила требуют замера recall; расширять вместе с frozen val.
_IOS4_RULES = ['IOS4-078', 'IOS4-079']


@pytest.mark.parametrize('rule_code', _IOS4_RULES)
def test_frozen_val_recall(
    rule_code: str,
    frozen_val_pairs: dict[str, list[tuple[str, str | None]]],
) -> None:
    """Для каждого правила проверяем Wilson lower bound ≥ 0.80.

    frozen_val_pairs[правило] — пары (gold, predicted).
    predicted=None — автомат пропустил находку (ложнонегатив).
    """
    if rule_code not in frozen_val_pairs:
        pytest.skip(f'{rule_code} отсутствует в frozen val corpus')

    pairs = frozen_val_pairs[rule_code]
    gold = [g for g, _ in pairs]
    predicted = [p for _, p in pairs]

    interval = compute_recall(predicted, gold)
    threshold = TZ_THRESHOLDS['recall']  # 0.80, не хардкодим

    # В CI (skip) не доходим; при наличии корпуса печатаем цифры.
    print(
        f'{rule_code}: recall={interval.point:.3f} '
        f'[{interval.low:.3f}, {interval.high:.3f}] '
        f'n={interval.n}  threshold={threshold}'
    )

    assert meets_threshold('recall', interval), (
        f'{rule_code}: recall lower bound {interval.low:.3f} < {threshold} '
        f'(n={interval.n}). GAP-IOS4-VAL не закрыт.'
    )
