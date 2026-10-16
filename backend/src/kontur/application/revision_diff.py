"""Parameter diff between two revisions of a document (SOTA-K3).

Compares the values extracted from an older and a newer revision of the same document, per
matrix parameter (``rule_code``). The pair must be an explicit revision chain
(``new.predecessor_file_id == old.file_id``); revision order is never guessed from the
revision label. Values are compared as extracted (no unit conversion). A value that is not
grounded in the source tokens is reported but marked as not usable for an automatic finding.
This is an aid for the inspector, not a finding and not a ``finding_status``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from kontur.domain.models import DocumentRef, EvidenceFragment, EvidenceGroup

__all__ = [
    "ChangeKind",
    "ParameterChange",
    "RevisionChainError",
    "change_to_schema",
    "diff_revisions",
    "documents_in",
    "revision_changes",
    "revision_diff_payload",
]


class ChangeKind(StrEnum):
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    CHANGED = "CHANGED"
    UNCHANGED = "UNCHANGED"
    AMBIGUOUS = "AMBIGUOUS"


class RevisionChainError(ValueError):
    """The two documents are not an explicit predecessor/successor pair."""


@dataclass(frozen=True, slots=True)
class ValueAt:
    value: str | float | bool | None
    unit: str | None
    page: int
    grounded: bool


@dataclass(frozen=True, slots=True)
class ParameterChange:
    rule_code: str
    kind: ChangeKind
    old: ValueAt | None
    new: ValueAt | None

    @property
    def usable_for_automatic_finding(self) -> bool:
        return all(v is None or v.grounded for v in (self.old, self.new))


def _values(
    groups: Iterable[EvidenceGroup], file_id: str
) -> dict[str, set[tuple[str | float | bool | None, str | None, int, bool]]]:
    found: dict[str, set[tuple[str | float | bool | None, str | None, int, bool]]] = defaultdict(
        set
    )
    for group in groups:
        fragment: EvidenceFragment
        for fragment in (*group.fragments, *group.prior_revision_fragments):
            if fragment.document.file_id != file_id:
                continue
            ex = fragment.extracted
            found[group.rule_code].add(
                (ex.normalized_value, ex.unit, fragment.page, ex.usable_for_automatic_finding)
            )
    return found


def _single(
    items: set[tuple[str | float | bool | None, str | None, int, bool]],
) -> ValueAt | None:
    distinct = {(value, unit) for value, unit, _, _ in items}
    if len(distinct) != 1:
        return None
    value, unit, page, grounded = min(items, key=lambda item: item[2])
    return ValueAt(value=value, unit=unit, page=page, grounded=grounded)


def diff_revisions(
    groups: Iterable[EvidenceGroup], old: DocumentRef, new: DocumentRef
) -> list[ParameterChange]:
    """Per-parameter changes from ``old`` to ``new``, sorted by rule_code."""
    if new.predecessor_file_id != old.file_id:
        raise RevisionChainError(
            f"{new.file_id} is not a recorded successor of {old.file_id}; order is not guessed"
        )
    items = list(groups)
    before, after = _values(items, old.file_id), _values(items, new.file_id)
    changes: list[ParameterChange] = []
    for code in sorted(set(before) | set(after)):
        old_items, new_items = before.get(code, set()), after.get(code, set())
        old_value = _single(old_items) if old_items else None
        new_value = _single(new_items) if new_items else None
        if (old_items and old_value is None) or (new_items and new_value is None):
            kind = ChangeKind.AMBIGUOUS
        elif old_value is None:
            kind = ChangeKind.ADDED
        elif new_value is None:
            kind = ChangeKind.REMOVED
        elif (old_value.value, old_value.unit) == (new_value.value, new_value.unit):
            kind = ChangeKind.UNCHANGED
        else:
            kind = ChangeKind.CHANGED
        changes.append(ParameterChange(code, kind, old_value, new_value))
    return changes


def _value_to_schema(value: ValueAt | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "value": value.value,
        "unit": value.unit,
        "page": value.page,
        "grounded": value.grounded,
    }


def change_to_schema(change: ParameterChange) -> dict[str, object]:
    return {
        "rule_code": change.rule_code,
        "kind": change.kind.value,
        "old": _value_to_schema(change.old),
        "new": _value_to_schema(change.new),
        "usable_for_automatic_finding": change.usable_for_automatic_finding,
    }


def documents_in(groups: Iterable[EvidenceGroup]) -> dict[str, DocumentRef]:
    """Documents referenced by evidence fragments and resolved revisions, by file_id."""
    found: dict[str, DocumentRef] = {}
    for group in groups:
        for ref in group.resolved_revisions:
            found.setdefault(ref.file_id, ref)
        for fragment in (*group.fragments, *group.prior_revision_fragments):
            found.setdefault(fragment.document.file_id, fragment.document)
    return found


def revision_diff_payload(
    groups: Iterable[EvidenceGroup], old: DocumentRef, new: DocumentRef
) -> dict[str, object]:
    """JSON body of one revision pair: contracts/schemas/revision_diff.schema.json."""
    changes = diff_revisions(groups, old, new)
    return {
        "old_file_id": old.file_id,
        "new_file_id": new.file_id,
        "document_code": new.document_code,
        "old_revision": old.revision,
        "new_revision": new.revision,
        "changes": [change_to_schema(change) for change in changes],
    }


def revision_changes(groups: Iterable[EvidenceGroup]) -> list[dict[str, object]]:
    """Every explicit revision pair with at least one non-UNCHANGED parameter.

    Only pairs recorded as predecessor/successor are diffed; documents without a recorded
    predecessor in the package are skipped, never paired by label.
    """
    items = list(groups)
    documents = documents_in(items)
    pairs: list[dict[str, object]] = []
    for file_id in sorted(documents):
        new = documents[file_id]
        predecessor = new.predecessor_file_id
        if predecessor is None or predecessor not in documents:
            continue
        payload = revision_diff_payload(items, documents[predecessor], new)
        changes = payload["changes"]
        assert isinstance(changes, list)
        payload["changes"] = [
            change for change in changes if change["kind"] != ChangeKind.UNCHANGED.value
        ]
        if payload["changes"]:
            pairs.append(payload)
    return pairs
