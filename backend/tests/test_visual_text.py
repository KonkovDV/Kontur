"""Детектор скрытого текста: растр vs текстовый слой, без True «потому что токены есть»."""

from __future__ import annotations

import sys
from pathlib import Path

from kontur.application.passport import read_passport
from kontur.application.visual_text import (
    MIN_VISIBLE_STD,
    agree_visual_and_text,
    gray_std,
    token_is_visually_present,
)
from kontur.infrastructure.pdfium_tokens import extract_pdf_bytes, file_sha256, flatten_tokens
from kontur.infrastructure.pdfium_visual import assess_pdf_bytes

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pdf_fixtures import stamp_pdf  # noqa: E402


def test_uniform_patch_is_hidden_when_text_is_present() -> None:
    samples = (255.0,) * 32
    assert gray_std(samples) < MIN_VISIBLE_STD
    assert token_is_visually_present("12345-PZ", samples) is False


def test_contrasted_patch_is_visible() -> None:
    samples = tuple([0.0, 255.0] * 16)
    assert token_is_visually_present("12345-PZ", samples) is True


def test_too_few_pixels_are_inconclusive() -> None:
    assert token_is_visually_present("12345-PZ", (0.0, 255.0)) is None


def test_any_hidden_token_fails_agreement() -> None:
    result = agree_visual_and_text([True, False, True])
    assert result.agreement is False
    assert result.hidden_tokens == 1


def test_no_samples_keep_agreement_unknown() -> None:
    assert agree_visual_and_text([]).agreement is None
    assert agree_visual_and_text([None, None]).agreement is None


def test_visible_black_text_agrees_with_raster() -> None:
    data = stamp_pdf(fill=(0, 0, 0, 255))
    assessment = assess_pdf_bytes(data)
    assert assessment.agreement is True
    assert assessment.hidden_tokens == 0
    tokens = flatten_tokens(extract_pdf_bytes(data))
    passport = read_passport(
        tokens,
        file_id="file-pd",
        file_hash=file_sha256(data),
        text_render_agreement=assessment.agreement,
    )
    assert passport.document_code == "12345-PZ"
    assert passport.text_render_agreement is True
    assert passport.needs_clarification is False


def test_white_text_on_white_is_hidden_and_clears_stamp() -> None:
    data = stamp_pdf(fill=(255, 255, 255, 255))
    extracted = extract_pdf_bytes(data)
    tokens = flatten_tokens(extracted)
    assert any("12345-PZ" in item.text for item in tokens)
    assessment = assess_pdf_bytes(data)
    assert assessment.agreement is False
    assert assessment.hidden_tokens >= 1
    passport = read_passport(
        tokens,
        file_id="file-pd",
        file_hash=file_sha256(data),
        filename="RD_pack.pdf",
        text_render_agreement=assessment.agreement,
    )
    assert passport.document_code is None
    assert passport.revision is None
    assert passport.sheet is None
    assert passport.text_render_agreement is False
    assert passport.needs_clarification is True
    assert passport.clarification_reason is not None
    assert "скрытый" in passport.clarification_reason
