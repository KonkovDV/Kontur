"""Presentation boundary wiring.

The upload endpoint predates the workspace-level duplicate query and calls
``reopen_for_upload`` before it constructs ``AcceptedFile`` objects. Install a
small compatibility guard on the in-memory workspace so a hash+stage retry is
classified before any durable process mutation or parser invocation.
"""

from __future__ import annotations

from typing import Any

from kontur.application.runtime import AcceptedFile, ProcessRecord, ProcessWorkspace
from kontur.domain.models import DocStage
from kontur.domain.state_machines import TransitionError
from kontur.domain.statuses import ProcessState

_PENDING = "_kontur_upload_pending"
_ADDED = "_kontur_upload_added"


def _record_has_file(
    record: ProcessRecord, content_hash: str, stage: DocStage
) -> bool:
    """Return whether hash+stage is already attached, without exposing its blob."""

    return any(
        item.file_hash == content_hash and item.doc_stage is stage
        for item in record.files
    )


def _workspace_has_file(
    workspace: ProcessWorkspace,
    record: ProcessRecord,
    content_hash: str,
    stage: DocStage,
) -> bool:
    """Public workspace query used by upload idempotency checks."""

    del workspace
    return _record_has_file(record, content_hash, stage)


def _install_idempotent_upload_guard() -> None:
    if getattr(ProcessWorkspace, "_idempotent_upload_guard", False):
        return

    original_reopen = ProcessWorkspace.reopen_for_upload
    original_attach = ProcessWorkspace.attach_file
    original_pipeline = ProcessWorkspace.run_matrix_pipeline

    def reopen_for_upload(
        workspace: ProcessWorkspace, record: ProcessRecord
    ) -> None:
        del workspace
        # FINALIZED remains an unconditional conflict, including duplicate-only
        # retries. For every other state, defer reopen until a new file exists.
        if record.process_state is ProcessState.FINALIZED:
            raise TransitionError("протокол финализирован, дозагрузка запрещена")
        record.__dict__[_PENDING] = True
        record.__dict__[_ADDED] = False

    def attach_file(
        workspace: ProcessWorkspace, record: ProcessRecord, item: AcceptedFile
    ) -> bool:
        if _workspace_has_file(workspace, record, item.file_hash, item.doc_stage):
            return False
        if getattr(record, _PENDING, False) and not getattr(record, _ADDED, False):
            # The first genuinely new item is the mutation boundary. Mixed
            # batches therefore reopen and parse once, while duplicates vanish.
            original_reopen(workspace, record)
        attached = original_attach(workspace, record, item)
        if attached:
            record.__dict__[_ADDED] = True
        return attached

    def run_matrix_pipeline(
        workspace: ProcessWorkspace, record: ProcessRecord
    ) -> Any:
        pending = getattr(record, _PENDING, False)
        added = getattr(record, _ADDED, False)
        try:
            if pending and not added:
                return None
            return original_pipeline(workspace, record)
        finally:
            if pending:
                record.__dict__.pop(_PENDING, None)
                record.__dict__.pop(_ADDED, None)

    ProcessRecord.has_file = _record_has_file  # type: ignore[attr-defined]
    ProcessWorkspace.has_file = _workspace_has_file  # type: ignore[attr-defined]
    ProcessWorkspace.reopen_for_upload = reopen_for_upload  # type: ignore[method-assign]
    ProcessWorkspace.attach_file = attach_file  # type: ignore[method-assign]
    ProcessWorkspace.run_matrix_pipeline = run_matrix_pipeline  # type: ignore[method-assign]
    ProcessWorkspace._idempotent_upload_guard = True  # type: ignore[attr-defined]


_install_idempotent_upload_guard()

__all__ = []
