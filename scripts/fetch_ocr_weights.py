"""Скачать веса OCR на сборке образа и сверить SHA-256.

Рантайм этот скрипт не вызывает. Без флага --fetch отсутствующий файл — ошибка.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path


def _load(path: Path) -> list[dict[str, str]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    files = payload.get("files")
    if not isinstance(files, list) or not files:
        raise SystemExit("lock has no files")
    out: list[dict[str, str]] = []
    for item in files:
        if not isinstance(item, dict):
            raise SystemExit("lock entry is not an object")
        name = item.get("name")
        digest = item.get("sha256")
        url = item.get("url")
        if not isinstance(name, str) or not isinstance(digest, str) or not isinstance(url, str):
            raise SystemExit("lock entry missing name, sha256 or url")
        out.append({"name": name, "sha256": digest, "url": url})
    return out


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    parser.add_argument("--fetch", action="store_true")
    args = parser.parse_args()
    args.dest.mkdir(parents=True, exist_ok=True)
    for item in _load(args.lock):
        target = args.dest / item["name"]
        if not target.is_file():
            if not args.fetch:
                raise SystemExit(f"missing {target.name}; pass --fetch only at image build")
            urllib.request.urlretrieve(item["url"], target)  # noqa: S310
        actual = _sha256(target)
        if actual != item["sha256"]:
            raise SystemExit(f"{target.name}: sha256 {actual} != {item['sha256']}")
        print(f"{actual}  {target.name}")


if __name__ == "__main__":
    main()
