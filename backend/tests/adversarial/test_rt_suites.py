"""Каркас Red Team наборов RT-A…RT-I (docs/RED_TEAM.md).

По одному представительному кейсу на набор. Каждый кейс фиксирует oracle:
что именно система обязана сделать с враждебным входом.

RT-2709-08 (неутверждённая редакция не эталон) и RT-D rename/хеш закрыты.
Остальные тесты — xfail strict, пока слой не реализован.
"""

from __future__ import annotations

from datetime import date

import pytest

from kontur.application.revision_resolver import resolve_revision
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.infrastructure.pdfium_tokens import file_sha256


def _doc(
    file_id: str,
    *,
    stage: DocStage = DocStage.PD,
    approval: ApprovalStatus = ApprovalStatus.APPROVED,
    approval_date: date | None = None,
    predecessor: str | None = None,
    successor: str | None = None,
) -> DocumentRef:
    return DocumentRef(
        file_id=file_id,
        file_hash=f"sha-{file_id}",
        doc_stage=stage,
        document_code=f"CODE-{file_id}",
        revision=file_id[-1],
        approval_status=approval,
        approval_date=approval_date,
        predecessor_file_id=predecessor,
        successor_file_id=successor,
    )


def test_rt_d_newer_unapproved_revision_does_not_become_baseline() -> None:
    """Новая неутверждённая редакция не смещает эталон (ADR-0003, RT-2709-08)."""

    v1 = _doc(
        "pd-v1",
        approval=ApprovalStatus.APPROVED,
        approval_date=date(2025, 1, 1),
        successor="pd-v2",
    )
    v2 = _doc(
        "pd-v2",
        approval=ApprovalStatus.NOT_APPROVED,
        approval_date=date(2025, 9, 1),
        predecessor="pd-v1",
    )
    result = resolve_revision([v1, v2], DocStage.PD)
    assert result.resolved is not None
    assert result.resolved.document.file_id == "pd-v1"


def test_rt_d_rename_does_not_change_identity() -> None:
    """Переименование и перемещение файла не меняют identity: решает content hash."""

    payload = b"%PDF-1.4 renamed-or-moved"
    moved = b"%PDF-1.4 renamed-or-moved"
    assert file_sha256(payload) == file_sha256(moved)
    assert file_sha256(payload) != file_sha256(payload + b"\x00")


@pytest.mark.xfail(reason="RT-A: слой приёма не реализован", strict=True)
def test_rt_a_decompression_bomb_is_rejected_with_reason_code() -> None:
    """Архив-бомба отклоняется с конкретным reason_code, парсер не падает."""

    raise NotImplementedError("RT-A")


@pytest.mark.xfail(reason="RT-B: детектор скрытого текста не реализован", strict=True)
def test_rt_b_hidden_text_layer_blocks_automatic_finding() -> None:
    """Видимый слой и текстовый слой расходятся → находка блокируется как событие безопасности."""

    raise NotImplementedError("RT-B")


@pytest.mark.xfail(reason="RT-C: dual-read OCR не реализован", strict=True)
def test_rt_c_digit_misread_triggers_abstain() -> None:
    """Два независимых чтения дали 6 и 8 → ABSTAIN, а не выбор «уверенного» варианта."""

    raise NotImplementedError("RT-C")


@pytest.mark.xfail(reason="RT-C: LLM изоляция не реализована", strict=True)
def test_rt_c_instruction_inside_image_is_ignored() -> None:
    """Текст «ignore rules» внутри чертежа остаётся данными и не управляет пайплайном."""

    raise NotImplementedError("RT-C")


@pytest.mark.xfail(reason="RT-E: нормативная база не реализована", strict=True)
def test_rt_e_expired_normative_revision_gives_clarification() -> None:
    """Истёкшая редакция нормы не даёт нарушения, только CLARIFICATION_REQUIRED."""

    raise NotImplementedError("RT-E")


@pytest.mark.xfail(reason="RT-F: нормативная база не реализована", strict=True)
def test_rt_f_unsigned_normative_chunk_is_not_used() -> None:
    """Неподписанный нормативный фрагмент не попадает в исполнение правила."""

    raise NotImplementedError("RT-F")


@pytest.mark.xfail(reason="RT-G: idempotency broker не реализован", strict=True)
def test_rt_g_duplicate_queue_message_yields_one_business_effect() -> None:
    """At-least-once доставка даёт ровно одну находку и одну версию протокола."""

    raise NotImplementedError("RT-G")


@pytest.mark.xfail(reason="RT-H: многоарендность не реализована", strict=True)
def test_rt_h_cross_tenant_access_is_denied_without_side_effect() -> None:
    """Запрос к чужому объекту отклоняется и не оставляет побочного эффекта."""

    raise NotImplementedError("RT-H")


@pytest.mark.xfail(reason="RT-I: UI не реализован", strict=True)
def test_rt_i_approve_is_not_default_action() -> None:
    """Подтверждение не является предвыбранным действием в интерфейсе."""

    raise NotImplementedError("RT-I")
