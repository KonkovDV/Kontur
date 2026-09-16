"""Собрать data/matrix из каталога организатора.

Источник — `parameter_catalog_132.jsonl` (открытый train). Правила — данные:
скелет на каждый код, ручные экстракторы живут в `data/matrix/overrides/`.
Покрытие остаётся `extractor_missing`, пока нет рабочего извлечения.
"""

from __future__ import annotations

import csv
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "data" / "matrix"
CATALOG = MATRIX / "source" / "parameter_catalog_132.jsonl"
OVERRIDES = MATRIX / "overrides"
RULES = MATRIX / "rules"
PARAMS_CSV = MATRIX / "params.template.csv"

CATALOG_CANDIDATES = (
    ROOT
    / "files"
    / "РАЗМЕЧЕННЫЙ_TRAIN_PUBLIC_203"
    / "РАЗМЕЧЕННЫЙ_TRAIN_PUBLIC_203"
    / "data"
    / "parameter_catalog_132.jsonl",
    ROOT
    / "files"
    / "01_ПАКЕТ_УЧАСТНИКАМ_3_ОБЪЕКТА"
    / "ХАКАТОН_УЧАСТНИКАМ_ГОТОВО_К_ПЕРЕДАЧЕ"
    / "02_ФОРМАТ_ДАННЫХ_И_ПРИМЕРЫ"
    / "data"
    / "parameter_catalog_132.jsonl",
)

PREFIX_TO_SECTION = {
    "PZ": "ПЗ",
    "SPZU": "СПЗУ",
    "AR": "АР",
    "KR": "КР",
    "IOS1": "ИОС1",
    "IOS2": "ИОС2",
    "IOS3": "ИОС3",
    "IOS4": "ИОС4",
    "IOS5": "ИОС5",
    "POS": "ПОС",
    "POD": "ПОД",
    "OOS": "ООС",
    "PPM": "ППМ",
    "ODI": "ОДИ",
    "ZU": "ЗУ",
    "SM": "СМ",
}

NON_NUMERIC_UNITS = frozenset({"—", "-", "Статус", "Буква", "Коорд.", "RAL / Артикул"})
REL_DELTA = re.compile(r">\s*(\d+(?:[.,]\d+)?)\s*%")
ABS_ZERO = re.compile(r">\s*0(?:\.0+)?")
LOWER_BOUND = re.compile(
    r"(?:<|менее)\s*(\d+(?:[.,]\d+)?)\s*(мм|м\b)",
    re.IGNORECASE,
)
DOWNGRADE = re.compile(r"понижен|снижен|занижен", re.IGNORECASE)
ABSENCE = re.compile(r"отсутств", re.IGNORECASE)

FAILURE_MAPPING = {
    "source_absent": "MISSING_EVIDENCE",
    "not_comparable": "NOT_COMPARABLE",
    "revision_conflict": "CLARIFICATION_REQUIRED",
    "low_quality": "LOW_QUALITY",
    "reads_disagree": "ABSTAIN",
}

DEFAULT_TESTS = [
    {"name": "equal_or_compliant_gives_no_difference", "expected_status": "AUTO_NO_DIFFERENCE"},
    {"name": "triggering_difference_gives_candidate", "expected_status": "CANDIDATE"},
    {"name": "required_stage_absent_gives_missing_evidence", "expected_status": "MISSING_EVIDENCE"},
    {"name": "parameter_not_applicable_on_object", "expected_status": "NOT_APPLICABLE"},
]


def _load_catalog(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def ensure_catalog() -> Path:
    """Каталог в git; `files/` используется только если локальной копии ещё нет."""

    if CATALOG.is_file():
        return CATALOG
    CATALOG.parent.mkdir(parents=True, exist_ok=True)
    for candidate in CATALOG_CANDIDATES:
        if candidate.is_file():
            shutil.copyfile(candidate, CATALOG)
            return CATALOG
    raise FileNotFoundError(
        "нет parameter_catalog_132.jsonl: положите копию в "
        "data/matrix/source/ или распакуйте открытый train в files/"
    )


def _section(code: str) -> str:
    prefix = code.rsplit("-", 1)[0]
    try:
        return PREFIX_TO_SECTION[prefix]
    except KeyError as exc:
        raise ValueError(f"{code}: неизвестный префикс {prefix}") from exc


def _priority(criticality: str) -> str:
    return "HIGH" if "критическ" in criticality.casefold() else "MEDIUM"


def _is_numeric_unit(unit: str) -> bool:
    return unit.strip() not in NON_NUMERIC_UNITS


def _comparator(row: dict[str, object]) -> tuple[dict[str, object], str]:
    trigger = str(row["trigger"])
    unit = str(row["unit"])
    rel = REL_DELTA.search(trigger)
    if rel:
        value = float(rel.group(1).replace(",", ".")) / 100.0
        return (
            {
                "operator": "delta",
                "tolerance_abs": None,
                "tolerance_rel": value,
                "rounding": "half_up",
                "unit_target": unit,
            },
            "number",
        )
    lowered = trigger.casefold()
    if ABS_ZERO.search(trigger) and ("расхожд" in lowered or "дельта" in lowered):
        return (
            {
                "operator": "delta",
                "tolerance_abs": 0.0,
                "tolerance_rel": None,
                "rounding": "half_up",
                "unit_target": unit,
            },
            "number",
        )
    bound = LOWER_BOUND.search(trigger)
    if bound:
        raw = float(bound.group(1).replace(",", "."))
        if bound.group(2).casefold() == "мм":
            raw /= 1000.0
        return (
            {
                "operator": "ge",
                "value": raw,
                "min_value": raw,
                "tolerance_abs": 0.0,
                "rounding": "none",
                "unit_target": "м",
            },
            "number",
        )
    if DOWNGRADE.search(trigger):
        return (
            {
                "operator": "class_not_lower",
                "rounding": "none",
                "unit_target": unit if unit != "—" else None,
            },
            "enum",
        )
    if ABSENCE.search(trigger):
        return (
            {"operator": "present", "rounding": "none", "unit_target": None},
            "presence",
        )
    if _is_numeric_unit(unit):
        return (
            {
                "operator": "delta",
                "tolerance_abs": 0.0,
                "tolerance_rel": None,
                "rounding": "half_up",
                "unit_target": unit,
            },
            "number",
        )
    return (
        {"operator": "eq", "rounding": "none", "unit_target": unit if unit != "—" else None},
        "exact_field",
    )


def skeleton(row: dict[str, object]) -> dict[str, object]:
    code = str(row["parameter_code"])
    unit = str(row["unit"])
    comparator, extractor_type = _comparator(row)
    critical = "критическ" in str(row["criticality"]).casefold()
    return {
        "code": code,
        "section": _section(code),
        "name": row["parameter_name"],
        "unit": unit,
        "matrix_version": "draft-0",
        "source_trigger_logic": row["trigger"],
        "coverage": "extractor_missing",
        "applicability": {
            "stages_required": ["PD", "RD"],
            "object_types": [],
            "condition": None,
        },
        "sources": {
            "pd": {"description": row["source_pd"]},
            "rd": {"description": row["source_rd"]},
            "id": {"description": row["source_id"]},
        },
        "extractor": {
            "type": extractor_type,
            "regex": None,
            "anchors": [str(row["parameter_name"])],
            "normalization": ["nfc", "collapse_spaces"],
            "dual_read_required": critical and extractor_type in {"number", "enum"},
        },
        "comparator": comparator,
        "required_evidence": ["expected", "actual"],
        "normative_refs": [],
        "failure_mapping": dict(FAILURE_MAPPING),
        "review_priority": _priority(str(row["criticality"])),
        "tests": list(DEFAULT_TESTS),
    }


def _stamp_catalog_fields(rule: dict[str, object], row: dict[str, object]) -> dict[str, object]:
    """Поля каталога первичны: override не может переименовать параметр."""

    stamped = dict(rule)
    stamped["code"] = row["parameter_code"]
    stamped["section"] = _section(str(row["parameter_code"]))
    stamped["name"] = row["parameter_name"]
    stamped["unit"] = row["unit"]
    stamped["source_trigger_logic"] = row["trigger"]
    stamped["matrix_version"] = "draft-0"
    coverage = str(rule.get("coverage") or "extractor_missing")
    if coverage not in {
        "executable",
        "extractor_missing",
        "source_missing",
        "advisory",
        "not_applicable",
    }:
        raise ValueError(f"{row['parameter_code']}: неизвестный coverage {coverage}")
    # coverage — наш статус, не поле каталога: executable ставит override
    # только когда экстрактор реально работает.
    stamped["coverage"] = coverage
    stamped["review_priority"] = _priority(str(row["criticality"]))
    return stamped


def load_overrides() -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    if not OVERRIDES.is_dir():
        return found
    for path in sorted(OVERRIDES.glob("*.json")):
        rule = json.loads(path.read_text(encoding="utf-8"))
        code = str(rule["code"])
        if code in found:
            raise ValueError(f"дубликат override: {code}")
        found[code] = rule
    return found


def write_params_csv(rows: list[dict[str, object]]) -> None:
    fieldnames = [
        "id",
        "code",
        "section",
        "parameter_name",
        "unit",
        "source_pd",
        "source_rd",
        "source_id",
        "trigger_logic",
        "review_priority",
        "legal_criticality",
        "data_type",
        "is_active",
    ]
    PARAMS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with PARAMS_CSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            comparator, extractor_type = _comparator(row)
            _ = comparator
            writer.writerow(
                {
                    "id": row["parameter_id"],
                    "code": row["parameter_code"],
                    "section": _section(str(row["parameter_code"])),
                    "parameter_name": row["parameter_name"],
                    "unit": row["unit"],
                    "source_pd": row["source_pd"],
                    "source_rd": row["source_rd"],
                    "source_id": row["source_id"],
                    "trigger_logic": row["trigger"],
                    "review_priority": _priority(str(row["criticality"])),
                    "legal_criticality": row["criticality"],
                    "data_type": extractor_type,
                    "is_active": "TRUE",
                }
            )


def compile_rules() -> tuple[int, int]:
    catalog = _load_catalog(ensure_catalog())
    if len(catalog) != 132:
        raise ValueError(f"в каталоге {len(catalog)} строк, ожидалось 132")
    overrides = load_overrides()
    unknown = set(overrides) - {str(row["parameter_code"]) for row in catalog}
    if unknown:
        raise ValueError(f"override вне матрицы: {sorted(unknown)}")

    RULES.mkdir(parents=True, exist_ok=True)
    written: set[str] = set()
    for row in catalog:
        code = str(row["parameter_code"])
        rule = _stamp_catalog_fields(overrides[code], row) if code in overrides else skeleton(row)
        path = RULES / f"{code}.json"
        path.write_text(
            json.dumps(rule, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written.add(code)

    for stale in RULES.glob("*.json"):
        if stale.stem not in written:
            stale.unlink()

    write_params_csv(catalog)
    return len(written), len(overrides)


def main() -> int:
    declared, overridden = compile_rules()
    print(f"matrix: {declared} правил, из них {overridden} с ручным экстрактором")
    return 0


if __name__ == "__main__":
    sys.exit(main())
