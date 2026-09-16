"""Лимиты приёма ТЗ п. 9.1: 50 МБ на файл, 200 МБ на пакет, формат, сигнатура, имя."""

from __future__ import annotations

import pytest
from kontur.application.intake import (
    EXTRA_REJECTION_CODES,
    MAX_BATCH_BYTES,
    MAX_FILE_BYTES,
    TZ_REJECTION_CODES,
    IntakeDecision,
    RejectionReason,
    UploadCandidate,
    evaluate_batch,
    filename_is_safe,
)
from kontur.application.pipeline import INTAKE_REJECTION_CODES


def _pdf(name: str = "01_ПЗ.pdf", size: int = 1024) -> UploadCandidate:
    return UploadCandidate(filename=name, size_bytes=size, header=b"%PDF-1.7\n")


def _only(decision: IntakeDecision) -> RejectionReason:
    assert len(decision.rejected) == 1
    return decision.rejected[0].reason


def test_rejection_codes_do_not_drift_from_the_contract() -> None:
    assert INTAKE_REJECTION_CODES == TZ_REJECTION_CODES
    codes = {member.value for member in RejectionReason}
    assert codes == TZ_REJECTION_CODES | EXTRA_REJECTION_CODES
    assert len(TZ_REJECTION_CODES) == 7


def test_file_limit_is_exactly_fifty_megabytes() -> None:
    assert evaluate_batch([_pdf(size=MAX_FILE_BYTES)]).ok
    decision = evaluate_batch([_pdf(size=MAX_FILE_BYTES + 1)])
    assert _only(decision) is RejectionReason.FILE_TOO_LARGE
    assert decision.rejected[0].http_status == 413
    assert decision.accepted == ()


def test_batch_limit_counts_everything_that_was_sent() -> None:
    half = MAX_FILE_BYTES
    files = [_pdf(name=f"{index}.pdf", size=half) for index in range(5)]
    assert sum(item.size_bytes for item in files) > MAX_BATCH_BYTES
    decision = evaluate_batch(files)
    assert _only(decision) is RejectionReason.BATCH_LIMIT_EXCEEDED
    assert decision.rejected[0].http_status == 413
    assert decision.accepted == ()
    assert evaluate_batch(files[:4]).ok


def test_unsupported_and_double_extensions_are_refused() -> None:
    """DWG до ответа на вопрос 6 не принимается, `.pdf.exe` отсекается по суффиксу."""

    assert _only(evaluate_batch([_pdf(name="plan.dwg")])) is RejectionReason.UNSUPPORTED_FORMAT
    assert _only(evaluate_batch([_pdf(name="pd.pdf.exe")])) is RejectionReason.UNSUPPORTED_FORMAT
    assert _only(evaluate_batch([_pdf(name="noext")])) is RejectionReason.UNSUPPORTED_FORMAT
    assert evaluate_batch([UploadCandidate("pack.zip", 2048, header=b"PK\x03\x04")]).ok
    assert evaluate_batch([UploadCandidate("smeta.docx", 2048, header=b"PK\x03\x04")]).ok
    assert evaluate_batch([UploadCandidate("ttl.xml", 512, header=b"<?xml version")]).ok


def test_worst_http_status_uses_unsupported_format_code() -> None:
    decision = evaluate_batch([_pdf(name="plan.dwg")])
    assert decision.rejected[0].http_status == 415


def test_zip_slip_and_control_characters_never_reach_storage() -> None:
    for name in ("../../etc/passwd.pdf", "sub/dir.pdf", "..\\pd.pdf", "pd\x00.pdf", " pd.pdf "):
        assert not filename_is_safe(name)
        assert _only(evaluate_batch([_pdf(name=name)])) is RejectionReason.UNSAFE_FILENAME
    assert not filename_is_safe("а" * 200 + ".pdf")
    assert filename_is_safe("01_ПЗ_том1.pdf")


def test_empty_and_mislabelled_files_are_corrupted_not_violations() -> None:
    assert _only(evaluate_batch([_pdf(size=0)])) is RejectionReason.CORRUPTED_FILE
    fake = UploadCandidate("pd.pdf", 1024, header=b"PK\x03\x04")
    decision = evaluate_batch([fake])
    assert _only(decision) is RejectionReason.CORRUPTED_FILE
    assert decision.rejected[0].http_status == 422
    unknown_header = UploadCandidate("pd.pdf", 1024, header=None)
    assert evaluate_batch([unknown_header]).ok


def test_duplicates_are_deduplicated_not_rejected() -> None:
    first = UploadCandidate("pd.pdf", 1024, header=b"%PDF-", content_hash="h1")
    again = UploadCandidate("pd_copy.pdf", 1024, header=b"%PDF-", content_hash="h1")
    other = UploadCandidate("rd.pdf", 1024, header=b"%PDF-", content_hash="h2")
    decision = evaluate_batch([first, again, other])
    assert decision.ok
    assert [item.filename for item in decision.accepted] == ["pd.pdf", "rd.pdf"]
    assert [item.filename for item in decision.duplicates] == ["pd_copy.pdf"]


def test_worst_http_status_wins_and_empty_batch_is_not_an_accept() -> None:
    decision = evaluate_batch([_pdf(name="a.dwg"), _pdf(size=MAX_FILE_BYTES + 1)])
    assert decision.http_status == max(item.http_status for item in decision.rejected)
    assert evaluate_batch([]).http_status == 202
    assert evaluate_batch([]).accepted == ()


def test_negative_size_is_a_programming_error() -> None:
    with pytest.raises(ValueError):
        UploadCandidate("pd.pdf", -1)
