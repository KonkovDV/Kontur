"""Шрифт из vendor/fonts: на месте, с лицензией OFL и совпадающим SHA-256."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from kontur.infrastructure.synthetic_pdf import contest_slice_font, vendored_font

FONTS = Path(__file__).resolve().parents[2] / "vendor" / "fonts"


def test_vendored_font_has_license_and_matching_hashes() -> None:
    assert "SIL Open Font License, Version 1.1" in (FONTS / "OFL.txt").read_text(encoding="utf-8")
    for line in (FONTS / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        digest, name = line.split(maxsplit=1)
        assert hashlib.sha256((FONTS / name).read_bytes()).hexdigest() == digest, name


def test_vendored_font_is_used_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KONTUR_TEST_FONT", raising=False)
    assert vendored_font() == FONTS / "NotoSans-Regular.ttf"
    assert contest_slice_font() == FONTS / "NotoSans-Regular.ttf"
