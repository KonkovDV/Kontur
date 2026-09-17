"""Каркас Red Team наборов RT-A…RT-I (docs/RED_TEAM.md).

По одному представительному кейсу на набор. Каждый кейс фиксирует oracle:
что именно система обязана сделать с враждебным входом.

RT-2709-08 (неутверждённая редакция не эталон) и RT-D rename/хеш закрыты.
RT-A: реализован — xfail удалён.
Остальные xfail strict: RT-C×2, RT-E, RT-F, RT-G, RT-H, RT-I.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest

from kontur.application.revision_resolver import resolve_revision
from kontur.domain.models import ApprovalStatus, DocStage, DocumentRef
from kontur.infrastructure.intake import IntakeResult, RejectReason, validate_intake
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
        document_code=f"CODE-{stage.value}",
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


def test_rt_a_decompression_bomb_is_rejected_with_reason_code() -> None:
    """Архив-бомба отклоняется с конкретным reason_code, парсер не падает.

    Сценарий: ZIP-архив с 1 МБ нулей компрессируется до ~1 КБ.
    Expansion ratio ~1000x >> порог 100x.
    validate_intake() должна:
      1. Вернуть IntakeResult(ok=False)
      2. reason_code в {DECOMPRESSION_BOMB, EXPAND_LIMIT_EXCEEDED}
      3. Не выбрасывать исключения (RT-A: парсер не падает)
    """
    # Создаём zip-бомбу: 1 МБ нулей → ~1 КБ в zip (ratio ~1000x)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("bomb.bin", b"\x00" * 1_000_000)  # 1 МБ нулей
    bomb = buf.getvalue()

    # Паранойдный перехватчик: validate_intake не должна выбрасывать
    result: IntakeResult = validate_intake(bomb)

    assert not result.ok, f"Зип-бомба должна быть отклонена, result.ok=True"
    assert result.reason_code in {
        RejectReason.DECOMPRESSION_BOMB,
        RejectReason.EXPAND_LIMIT_EXCEEDED,
    }, f"Ожидали bomb reason_code, получено: {result.reason_code!r}"
    assert result.reason_code is not None
    # ADR-0001: никогда не должна выбрасываться ошибка из validate_intake()
    # (если бы выбросилась, тест уже упал бы выше)


def test_rt_b_hidden_text_layer_blocks_automatic_finding() -> None:
    """Белый текст в слое есть, на растре нет → штамп не становится паспортом."""

    import sys
    from pathlib import Path

    from kontur.application.passport import read_passport
    from kontur.infrastructure.pdfium_tokens import extract_pdf_bytes, file_sha256, flatten_tokens
    from kontur.infrastructure.pdfium_visual import assess_pdf_bytes

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from pdf_fixtures import stamp_pdf

    data = stamp_pdf(fill=(255, 255, 255, 255))
    assessment = assess_pdf_bytes(data)
    assert assessment.agreement is False
    passport = read_passport(
        flatten_tokens(extract_pdf_bytes(data)),
        file_id="hidden",
        file_hash=file_sha256(data),
        text_render_agreement=assessment.agreement,
    )
    assert passport.document_code is None
    assert passport.needs_clarification is True


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
