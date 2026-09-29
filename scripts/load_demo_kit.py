"""Загрузить учебный комплект на уже поднятый стенд. Эталон не назначает."""

from __future__ import annotations

import json
import os
import sys

import httpx


def main() -> int:
    base = os.environ.get("KONTUR_DEMO_URL", "http://127.0.0.1:3000").rstrip("/")
    token = os.environ.get(
        "KONTUR_DEMO_TOKEN",
        "inspector-1@OBJ-DEMO-COLD-START/INSPECTOR",
    )
    try:
        response = httpx.post(
            f"{base}/api/v1/demo/kit",
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        print(exc, file=sys.stderr)
        if isinstance(exc, httpx.HTTPStatusError):
            print(exc.response.text, file=sys.stderr)
        return 1
    print(json.dumps(response.json(), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
