"""Калибровка уверенности для HITL (SILVER, не GOLD).

Reliability-бакеты, ECE и выбор ``t_high`` по верхней границе Уильсона доли
ошибок в зоне auto-approve. Записи со split ``hidden`` отвергаются: порог не
подбирается на скрытом сете. Если размеченной выборки нет или ни один порог не
проходит по верхней границе — ``t_high = None`` и статус ``uncalibrated``.
Отчёт никогда не закрывает Gate I/K (``closes_gate = False``).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from kontur.evaluation.metrics import wilson

FORBIDDEN_SPLITS = frozenset({"hidden", "test_hidden", "gold_hidden"})


@dataclass(frozen=True)
class Sample:
    confidence: float
    correct: bool


def load_samples(rows: Iterable[Mapping[str, object]]) -> list[Sample]:
    samples: list[Sample] = []
    for row in rows:
        split = str(row.get("split", "silver")).lower()
        if split in FORBIDDEN_SPLITS:
            raise ValueError(f"split {split!r} запрещён для калибровки")
        conf = float(row["confidence"])  # type: ignore[arg-type]
        if not 0.0 <= conf <= 1.0:
            raise ValueError(f"confidence вне [0;1]: {conf}")
        samples.append(Sample(conf, bool(row["correct"])))
    return samples


def reliability_bins(samples: Sequence[Sample], n_bins: int = 10) -> list[dict[str, float | int]]:
    if n_bins < 1:
        raise ValueError("n_bins >= 1")
    bins: list[list[Sample]] = [[] for _ in range(n_bins)]
    for s in samples:
        bins[min(n_bins - 1, int(s.confidence * n_bins))].append(s)
    out: list[dict[str, float | int]] = []
    for i, items in enumerate(bins):
        n = len(items)
        out.append(
            {
                "lo": i / n_bins,
                "hi": (i + 1) / n_bins,
                "n": n,
                "conf": sum(s.confidence for s in items) / n if n else 0.0,
                "acc": sum(s.correct for s in items) / n if n else 0.0,
            }
        )
    return out


def ece(samples: Sequence[Sample], n_bins: int = 10) -> float:
    n = len(samples)
    if n == 0:
        return float("nan")
    return sum(
        int(b["n"]) / n * abs(float(b["acc"]) - float(b["conf"]))
        for b in reliability_bins(samples, n_bins)
        if b["n"]
    )


def choose_t_high(
    samples: Sequence[Sample], max_error_rate: float = 0.10, min_n: int = 30
) -> dict[str, object] | None:
    """Наименьший порог, при котором верхняя граница Уильсона доли ошибок ≤ риска."""

    for t in sorted({round(s.confidence, 2) for s in samples}):
        zone = [s for s in samples if s.confidence >= t]
        if len(zone) < min_n:
            break
        errors = sum(not s.correct for s in zone)
        ci = wilson(errors, len(zone))
        if ci.high <= max_error_rate:
            return {
                "t_high": t,
                "n_zone": len(zone),
                "errors": errors,
                "error_rate": ci.point,
                "error_rate_ci95": [ci.low, ci.high],
            }
    return None


def calibration_report(
    samples: Sequence[Sample],
    *,
    n_bins: int = 10,
    max_error_rate: float = 0.10,
    min_n: int = 30,
    source: str = "SILVER",
    git_sha: str = "",
    date: str = "",
) -> dict[str, object]:
    pick = choose_t_high(samples, max_error_rate, min_n) if samples else None
    return {
        "schema_version": "kontur.hitl_calibration.v1",
        "source": source,
        "is_gold": False,
        "closes_gate": False,
        "tuned_on_hidden": False,
        "n": len(samples),
        "n_bins": n_bins,
        "bins": reliability_bins(samples, n_bins),
        "ece": None if not samples else ece(samples, n_bins),
        "max_error_rate": max_error_rate,
        "min_n": min_n,
        "t_high": pick["t_high"] if pick else None,
        "t_high_detail": pick,
        "status": "calibrated_silver" if pick else "uncalibrated",
        "git_sha": git_sha,
        "date": date,
    }


def reliability_svg(report: Mapping[str, object], size: int = 320) -> str:
    pad = 30
    w = size - 2 * pad
    bins = report["bins"]
    n_bins = report["n_bins"]
    assert isinstance(bins, list) and isinstance(n_bins, int)
    bar = w / n_bins - 2
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}">',
        f'<rect x="{pad}" y="{pad}" width="{w}" height="{w}" fill="none" stroke="#555"/>',
        f'<line x1="{pad}" y1="{pad + w}" x2="{pad + w}" y2="{pad}" '
        'stroke="#999" stroke-dasharray="4"/>',
    ]
    for b in bins:
        if not b["n"]:
            continue
        x = pad + float(b["lo"]) * w
        h = float(b["acc"]) * w
        parts.append(
            f'<rect x="{x:.1f}" y="{pad + w - h:.1f}" width="{bar:.1f}" '
            f'height="{h:.1f}" fill="#0072B2"/>'
        )
    caption = f"{report['source']} n={report['n']} ECE={report['ece']} status={report['status']}"
    parts.append(f'<text x="{pad}" y="18" font-size="11">{caption}</text>')
    parts.append("</svg>")
    return "\n".join(parts)
