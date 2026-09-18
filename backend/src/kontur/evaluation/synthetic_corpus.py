"""Синтетический корпус для CI-безопасной регрессии по recall (GAP-IOS4-VAL).

Содержит 20 образцов для IOS4-078 (площадь A×B) и IOS4-079 (идентификация объекта).
Корпус детерминирован: нет random, нет сети, работает в CI без GPU.

Синтетика != реальные документы: покрывает детерминизм логики правила,
не производительность OCR/модели.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SyntheticSample:
    rule_code: str
    gold_value: str         # эталонное значение (есть нарушение)
    predicted_value: str | None  # автоматически извлеченное
    expected_match: bool    # ожидаем ли совпадение?


# ──────────────────────────────────────── IOS4-078: площадь A×B ──────────────────────────────────────────
#
# Записи IOS4-078: есть = площадь A×B в документации не соответствует параметрам.
# gold_value = значение из золотого стандарта (квадратные метры, запись в едином формате)
# predicted_value = что автомат извлёк из документа

_IOS4_078_CORPUS: tuple[SyntheticSample, ...] = (
    # Правильные извлечения (16/20 = 80 % recall = точно на пороге)
    SyntheticSample("IOS4-078", "150.00",  "150.00",  True),
    SyntheticSample("IOS4-078", "200.00",  "200.00",  True),
    SyntheticSample("IOS4-078", "350.50",  "350.50",  True),
    SyntheticSample("IOS4-078", "420.00",  "420.00",  True),
    SyntheticSample("IOS4-078", "99.99",   "99.99",   True),
    SyntheticSample("IOS4-078", "1000.00", "1000.00", True),
    SyntheticSample("IOS4-078", "78.40",   "78.40",   True),
    SyntheticSample("IOS4-078", "234.56",  "234.56",  True),
    SyntheticSample("IOS4-078", "500.00",  "500.00",  True),
    SyntheticSample("IOS4-078", "12.50",   "12.50",   True),
    SyntheticSample("IOS4-078", "800.00",  "800.00",  True),
    SyntheticSample("IOS4-078", "60.00",   "60.00",   True),
    SyntheticSample("IOS4-078", "310.00",  "310.00",  True),
    SyntheticSample("IOS4-078", "44.44",   "44.44",   True),
    SyntheticSample("IOS4-078", "175.75",  "175.75",  True),
    SyntheticSample("IOS4-078", "900.00",  "900.00",  True),
    # Пропущенные автоматом (ложнонегатив для recall)
    SyntheticSample("IOS4-078", "250.00",  None,      False),
    SyntheticSample("IOS4-078", "330.00",  None,      False),
    SyntheticSample("IOS4-078", "115.00",  None,      False),
    SyntheticSample("IOS4-078", "620.00",  None,      False),
)

# ──────────────────────────────────────── IOS4-079: идентификация ─────────────────────────────────────────

_IOS4_079_CORPUS: tuple[SyntheticSample, ...] = (
    SyntheticSample("IOS4-079", "RU-2023-00001", "RU-2023-00001", True),
    SyntheticSample("IOS4-079", "RU-2023-00002", "RU-2023-00002", True),
    SyntheticSample("IOS4-079", "RU-2023-00003", "RU-2023-00003", True),
    SyntheticSample("IOS4-079", "RU-2023-00004", "RU-2023-00004", True),
    SyntheticSample("IOS4-079", "RU-2023-00005", "RU-2023-00005", True),
    SyntheticSample("IOS4-079", "RU-2023-00006", "RU-2023-00006", True),
    SyntheticSample("IOS4-079", "RU-2023-00007", "RU-2023-00007", True),
    SyntheticSample("IOS4-079", "RU-2023-00008", "RU-2023-00008", True),
    SyntheticSample("IOS4-079", "RU-2023-00009", "RU-2023-00009", True),
    SyntheticSample("IOS4-079", "RU-2023-00010", "RU-2023-00010", True),
    SyntheticSample("IOS4-079", "RU-2023-00011", "RU-2023-00011", True),
    SyntheticSample("IOS4-079", "RU-2023-00012", "RU-2023-00012", True),
    SyntheticSample("IOS4-079", "RU-2023-00013", "RU-2023-00013", True),
    SyntheticSample("IOS4-079", "RU-2023-00014", "RU-2023-00014", True),
    SyntheticSample("IOS4-079", "RU-2023-00015", "RU-2023-00015", True),
    SyntheticSample("IOS4-079", "RU-2023-00016", "RU-2023-00016", True),
    SyntheticSample("IOS4-079", "RU-2023-00017", None,            False),
    SyntheticSample("IOS4-079", "RU-2023-00018", None,            False),
    SyntheticSample("IOS4-079", "RU-2023-00019", None,            False),
    SyntheticSample("IOS4-079", "RU-2023-00020", None,            False),
)

# Публичный API
ALL_IOS4_CORPUS: tuple[SyntheticSample, ...] = _IOS4_078_CORPUS + _IOS4_079_CORPUS


def corpus_for_rule(rule_code: str) -> tuple[SyntheticSample, ...]:
    """Подкорпус по коду правила."""
    return tuple(s for s in ALL_IOS4_CORPUS if s.rule_code == rule_code)


def pairs_for_rule(rule_code: str) -> list[tuple[str, str | None]]:
    """Пары (gold, predicted) для rule_recall_report."""
    return [(s.gold_value, s.predicted_value) for s in corpus_for_rule(rule_code)]
