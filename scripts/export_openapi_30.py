"""Даунконверт канонического OpenAPI 3.1.0 в 3.0.3.

ТЗ п. 1.3 требует валидацию OpenAPI 3.0. Канон репозитория — 3.1.0
(RT-2609-19): ``contentMediaType`` и типы ``["string", "null"]``.
Этот модуль пишет соседний файл, не подменяя канон.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "contracts" / "openapi.yaml"
TARGET = ROOT / "contracts" / "openapi-3.0.yaml"
HEADER = (
    "# Сгенерировано scripts/export_openapi_30.py из contracts/openapi.yaml.\n"
    "# Канонический контракт — OpenAPI 3.1.0. Этот файл — даунконверт 3.0.3\n"
    "# для валидаторов ТЗ п. 1.3. Правки вносить в contracts/openapi.yaml.\n"
)


def downconvert(spec: dict[str, object]) -> dict[str, object]:
    """Вернуть копию спецификации в конструкциях OpenAPI 3.0.3."""

    converted = copy.deepcopy(spec)
    _walk(converted)
    converted["openapi"] = "3.0.3"
    return converted


def render_openapi_30(spec: dict[str, object]) -> str:
    """Текст ``contracts/openapi-3.0.yaml`` для данной спецификации 3.1."""

    body = yaml.safe_dump(
        downconvert(spec),
        allow_unicode=True,
        sort_keys=False,
        width=1000,
        default_flow_style=False,
    )
    return HEADER + body


def _walk(node: object) -> None:
    if isinstance(node, dict):
        media = node.pop("contentMediaType", None)
        if isinstance(media, str):
            node.setdefault("format", "binary")
            node["x-content-media-type"] = media
        kind = node.get("type")
        if isinstance(kind, list):
            non_null = [item for item in kind if item != "null"]
            if "null" not in kind or len(non_null) != 1 or not isinstance(non_null[0], str):
                raise ValueError(f"тип OpenAPI 3.1 не сведён к nullable: {kind!r}")
            node["type"] = non_null[0]
            node["nullable"] = True
        for value in node.values():
            _walk(value)
        return
    if isinstance(node, list):
        for item in node:
            _walk(item)


def main() -> int:
    spec = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        print("openapi.yaml: ожидался объект")
        return 1
    text = render_openapi_30(spec)
    if "--check" in sys.argv:
        if not TARGET.is_file() or TARGET.read_text(encoding="utf-8") != text:
            print("openapi-3.0.yaml расходится с даунконвертом")
            return 1
        print("openapi-3.0.yaml совпадает с даунконвертом")
        return 0
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"записан {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
