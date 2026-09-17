"""Гейт публикации модели (ТЗ п. 9.4).

Модель допускается в контур только при прохождении всех обязательных порогов
раздела 14, без просадки Recall по любой обязательной категории более чем на
2 п..п. и без роста FPR более чем на 2 п..п.

Изменения RT-2609-17:
- evaluate() требует PublicationSignature: без подписи ответственного — blocking.
- evaluate() требует полный набор REQUIRED_CATEGORIES — без любой
  категории скоринг ограничен до 59/100 (ТЗ п. 9.4, Приложение 1).
- PublicationSignature хранит responsible_id, model_version и rollback_plan.
"""

from __future__ import annotations

from dataclasses import dataclass

from kontur.evaluation.metrics import TZ_THRESHOLDS, Interval, meets_threshold

MAX_RECALL_DROP_PP = 2.0
MAX_FPR_RISE_PP = 2.0

#: Обязательные категории матрицы (ТЗ п. 9.4, Приложение 1).
#: Публикация без покрытия любой категории ограничивает скоринг до 59/100.
REQUIRED_CATEGORIES: frozenset[str] = frozenset(
    {
        "PZ",   # Пояснительная записка
        "KR",   # Конструктивные решения
        "AR",   # Архитектурные решения
        "IOS",  # Инженерные системы
        "SM",   # Смежные разделы
        "OOS",  # Охрана окружающей среды
    }
)


@dataclass(frozen=True, slots=True)
class GateResult:
    passed: bool
    blocking: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PublicationSignature:
    """Подпись ответственного за публикацию модели (RT-2609-17).

    responsible_id: идентификатор ответственного лица (не может быть пустым).
    model_version: версия модели, которая публикуется.
    rollback_plan: URI или описание процедуры отката (не может быть пустым).
    """

    responsible_id: str
    model_version: str
    rollback_plan: str

    def __post_init__(self) -> None:
        if not self.responsible_id.strip():
            raise ValueError("responsible_id не может быть пустым")
        if not self.model_version.strip():
            raise ValueError("model_version не может быть пустым")
        if not self.rollback_plan.strip():
            raise ValueError("rollback_plan не может быть пустым")


def evaluate(
    *,
    intervals: dict[str, Interval],
    recall_by_category: dict[str, float],
    baseline_recall_by_category: dict[str, float],
    fpr_by_group: dict[str, float],
    baseline_fpr_by_group: dict[str, float],
    signature: PublicationSignature | None = None,
) -> GateResult:
    """Gate публикации. False, если хоть одно условие не выполнено."""
    blocking: list[str] = []

    # RT-2609-17: подпись обязательна
    if signature is None:
        blocking.append(
            "публикация без PublicationSignature запрещена:"
            " укажите ответственного и rollback-план"
        )

    # RT-2609-17: полный набор обязательных категорий
    covered = frozenset(cat for cat in REQUIRED_CATEGORIES if cat in recall_by_category)
    missing = REQUIRED_CATEGORIES - covered
    if missing:
        blocking.append(
            f"отсутствуют обязательные категории: {', '.join(sorted(missing))}"
        )

    # Пороги ТЗ (раздел 14)
    for name in TZ_THRESHOLDS:
        interval = intervals.get(name)
        if interval is None:
            blocking.append(f"{name}: не измерено")
            continue
        if not meets_threshold(name, interval):
            blocking.append(f"{name}: порог не подтверждён интервалом")

    for category, value in recall_by_category.items():
        baseline = baseline_recall_by_category.get(category)
        if baseline is not None and (baseline - value) * 100 > MAX_RECALL_DROP_PP:
            blocking.append(f"recall[{category}]: просадка больше {MAX_RECALL_DROP_PP} п..п.")

    for group, value in fpr_by_group.items():
        baseline = baseline_fpr_by_group.get(group)
        if baseline is not None and (value - baseline) * 100 > MAX_FPR_RISE_PP:
            blocking.append(f"fpr[{group}]: рост больше {MAX_FPR_RISE_PP} п..п.")

    return GateResult(passed=not blocking, blocking=tuple(blocking))
