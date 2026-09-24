"""Загрузить учебный комплект на уже поднятый стенд. Эталон не назначает."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    base = os.environ.get("KONTUR_DEMO_URL", "http://127.0.0.1:3000").rstrip("/")
    token = os.environ.get(
        "KONTUR_DEMO_TOKEN",
        "inspector-1@OBJ-DEMO-COLD-START/INSPECTOR",
    )
    request = urllib.request.Request(
        f"{base}/api/v1/demo/kit",
        method="POST",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        print(detail, file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
