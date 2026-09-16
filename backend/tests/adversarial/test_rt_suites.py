"""Каркас Red Team наборов RT-A…RT-I (docs/RED_TEAM.md).

По одному представительному кейсу на набор. Каждый кейс фиксирует oracle:
что именно система обязана сделать с враждебным входом. Все помечены xfail
strict — снятие метки требует реализации соответствующего слоя.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.xfail(reason="слои L0–L9 не реализованы", strict=True)


def test_rt_a_decompression_bomb_is_rejected_with_reason_code() -> None:
    """Архив-бомба отклоняется с конкретным reason_code, парсер не падает."""

    raise NotImplementedError("RT-A")


def test_rt_b_hidden_text_layer_blocks_automatic_finding() -> None:
    """Видимый слой и текстовый слой расходятся → находка блокируется как событие безопасности."""

    raise NotImplementedError("RT-B")


def test_rt_c_digit_misread_triggers_abstain() -> None:
    """Два независимых чтения дали 6 и 8 → ABSTAIN, а не выбор «уверенного» варианта."""

    raise NotImplementedError("RT-C")


def test_rt_c_instruction_inside_image_is_ignored() -> None:
    """Текст «ignore rules» внутри чертежа остаётся данными и не управляет пайплайном."""

    raise NotImplementedError("RT-C")


def test_rt_d_newer_unapproved_revision_does_not_become_baseline() -> None:
    """Новая неутверждённая редакция не смещает эталон (ADR-0003)."""

    raise NotImplementedError("RT-D")


def test_rt_d_rename_does_not_change_identity() -> None:
    """Переименование и перемещение файла не меняют identity: решает content hash."""

    raise NotImplementedError("RT-D")


def test_rt_e_expired_normative_revision_gives_clarification() -> None:
    """Истёкшая редакция нормы не даёт нарушения, только CLARIFICATION_REQUIRED."""

    raise NotImplementedError("RT-E")


def test_rt_f_unsigned_normative_chunk_is_not_used() -> None:
    """Неподписанный нормативный фрагмент не попадает в исполнение правила."""

    raise NotImplementedError("RT-F")


def test_rt_g_duplicate_queue_message_yields_one_business_effect() -> None:
    """At-least-once доставка даёт ровно одну находку и одну версию протокола."""

    raise NotImplementedError("RT-G")


def test_rt_h_cross_tenant_access_is_denied_without_side_effect() -> None:
    """Запрос к чужому объекту отклоняется и не оставляет побочного эффекта."""

    raise NotImplementedError("RT-H")


def test_rt_i_approve_is_not_default_action() -> None:
    """Подтверждение не является предвыбранным действием в интерфейсе."""

    raise NotImplementedError("RT-I")
