"""Два провода статусов: внутренний FindingStatus и внешний submission хакатона.

Домен не подгоняется под enum организатора. Этот модуль — адаптер границы
соревнования: `submission_schema.json`. Провод ТЗ/РиН по-прежнему идёт через
`status_map.on_the_wire` и не содержит AUTO_NO_DIFFERENCE.

Здесь же собирается сам JSON ответа. Правило одно: файл участника не должен
собираться «руками» в другом месте, иначе формат кода параметра, локализация и
номер страницы разъедутся с матрицей, и ответ потеряет баллы молча.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum

from kontur.domain.models import DocStage, EvidenceFragment, EvidenceGroup, EvidenceRole, Finding
from kontur.domain.rule_codes import (
    KnownCodes,
    canonicalize_rule_code,
    display_alias,
    is_canonical_rule_code,
)
from kontur.domain.statuses import WIRE_FINDING_STATUSES, FindingStatus, ReviewPriority


class ContestViolationLabel(StrEnum):
    """`violation_label` из submission_schema.json организатора."""

    VIOLATION_PRESENT = "VIOLATION_PRESENT"
    NO_VIOLATION = "NO_VIOLATION"
    MISSING_DOCUMENT = "MISSING_DOCUMENT"
    COMPARISON_IMPOSSIBLE = "COMPARISON_IMPOSSIBLE"


class ContestProtocolStatus(StrEnum):
    """`protocol_status` из submission_schema.json. Не FindingStatus и не review_priority."""

    OK = "OK"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
    ID_MISSING = "ID_MISSING"
    RD_MISSING = "RD_MISSING"
    PD_MISSING = "PD_MISSING"
    COMPARISON_IMPOSSIBLE = "COMPARISON_IMPOSSIBLE"


class ContestCodeStyle(StrEnum):
    """Формат `parameter_code` на проводе соревнования.

    Каталог параметров организатора трёхзначный (`PZ-001`), в текстах Приложения 2
    встречается короткая форма (`PZ-1`). Пока организатор не подтвердил формат
    приёмки (вопрос 16), выбор живёт в одной константе, а не в десяти местах.
    """

    CANONICAL = "CANONICAL"
    SHORT = "SHORT"


#: Единственная точка выбора формата кода в ответе участника.
CONTEST_CODE_STYLE = ContestCodeStyle.CANONICAL


# Команда на хакатоне заявляет детекцию. CANDIDATE — это её VIOLATION_PRESENT.
# AUTO_NO_DIFFERENCE на провод ТЗ не отдаётся, но в JSON участника становится
# NO_VIOLATION: иначе 5 gold-проверок с violation_label=NO_VIOLATION некуда класть.
_CONTEST_LABEL: dict[FindingStatus, ContestViolationLabel] = {
    FindingStatus.CANDIDATE: ContestViolationLabel.VIOLATION_PRESENT,
    FindingStatus.CONFIRMED_VIOLATION: ContestViolationLabel.VIOLATION_PRESENT,
    FindingStatus.NEGATIVE_VERIFIED: ContestViolationLabel.NO_VIOLATION,
    FindingStatus.AUTO_NO_DIFFERENCE: ContestViolationLabel.NO_VIOLATION,
    FindingStatus.MISSING_EVIDENCE: ContestViolationLabel.MISSING_DOCUMENT,
    FindingStatus.NOT_APPLICABLE: ContestViolationLabel.NO_VIOLATION,
    FindingStatus.NOT_COMPARABLE: ContestViolationLabel.COMPARISON_IMPOSSIBLE,
    FindingStatus.LOW_QUALITY: ContestViolationLabel.COMPARISON_IMPOSSIBLE,
    FindingStatus.ABSTAIN: ContestViolationLabel.COMPARISON_IMPOSSIBLE,
    FindingStatus.CLARIFICATION_REQUIRED: ContestViolationLabel.COMPARISON_IMPOSSIBLE,
    FindingStatus.SUSPICION: ContestViolationLabel.COMPARISON_IMPOSSIBLE,
}

_MISSING_STAGE_STATUS: dict[DocStage, ContestProtocolStatus] = {
    DocStage.PD: ContestProtocolStatus.PD_MISSING,
    DocStage.RD: ContestProtocolStatus.RD_MISSING,
    DocStage.ID: ContestProtocolStatus.ID_MISSING,
}

_STAGE_VALUE_KEY: dict[DocStage, str] = {
    DocStage.PD: "pd_value",
    DocStage.RD: "rd_value",
    DocStage.ID: "id_value",
}

#: Роли, значения которых участвуют в сравнении и потому обязаны быть grounded.
_COMPARED_ROLES: frozenset[EvidenceRole] = frozenset({EvidenceRole.EXPECTED, EvidenceRole.ACTUAL})

Value = str | float | bool | None


def contest_violation_label(status: FindingStatus) -> ContestViolationLabel:
    """Внутренний статус → метка JSON участника. Не используется для РиН."""

    try:
        return _CONTEST_LABEL[status]
    except KeyError as exc:
        raise ValueError(f"нет маппинга на submission_schema для {status}") from exc


def contest_allows_auto_no_difference() -> bool:
    """Напоминание инварианта: два провода расходятся на AUTO_NO_DIFFERENCE."""

    return FindingStatus.AUTO_NO_DIFFERENCE not in WIRE_FINDING_STATUSES


def contest_parameter_code(
    code: str,
    style: ContestCodeStyle | None = None,
    known_codes: KnownCodes = None,
) -> str:
    """Код параметра в формате приёмки. Пустой или неразбираемый код — отказ."""

    canonical = canonicalize_rule_code(code, known_codes=known_codes)
    if not is_canonical_rule_code(canonical):
        raise ValueError(f"код параметра не разбирается: {code!r}")
    if known_codes is not None and canonical not in set(known_codes):
        raise ValueError(f"код параметра не из матрицы: {code!r}")
    chosen = CONTEST_CODE_STYLE if style is None else style
    if chosen is ContestCodeStyle.SHORT:
        return display_alias(canonical)
    return canonical


def contest_protocol_status(
    status: FindingStatus,
    *,
    review_priority: ReviewPriority | None = None,
    missing_stage: DocStage | None = None,
) -> ContestProtocolStatus:
    """`protocol_status` выводится из метки, а не из внутреннего статуса напрямую.

    CRITICAL ставится только при явном HIGH: без основания нарушение не
    повышается в тяжести (ТЗ п. 9.2 — review_priority не юридическая тяжесть).
    """

    label = contest_violation_label(status)
    if label is ContestViolationLabel.MISSING_DOCUMENT:
        if missing_stage is None:
            return ContestProtocolStatus.COMPARISON_IMPOSSIBLE
        return _MISSING_STAGE_STATUS[missing_stage]
    if label is ContestViolationLabel.COMPARISON_IMPOSSIBLE:
        return ContestProtocolStatus.COMPARISON_IMPOSSIBLE
    if label is ContestViolationLabel.VIOLATION_PRESENT:
        if review_priority is ReviewPriority.HIGH:
            return ContestProtocolStatus.CRITICAL
        return ContestProtocolStatus.WARNING
    return ContestProtocolStatus.OK


@dataclass(frozen=True, slots=True)
class SubmissionEvidence:
    """Ссылка на страницу PDF. Номер страницы в схеме организатора — от 1."""

    stage: DocStage
    file_id: str
    pdf_page_number: int

    def __post_init__(self) -> None:
        if self.pdf_page_number < 1:
            raise ValueError("pdf_page_number в submission начинается с 1, а не с 0")
        if not self.file_id.strip():
            raise ValueError("evidence без file_id не проверяема")

    def to_wire(self) -> dict[str, object]:
        return {
            "stage": self.stage.value,
            "file_id": self.file_id,
            "pdf_page_number": self.pdf_page_number,
        }


@dataclass(frozen=True, slots=True)
class SubmissionCheck:
    """Одна строка `checks[]` ответа участника."""

    parameter_code: str
    location: str
    violation_label: ContestViolationLabel
    evidence: tuple[SubmissionEvidence, ...]
    pd_value: Value = None
    rd_value: Value = None
    id_value: Value = None
    protocol_status: ContestProtocolStatus | None = None
    criticality: str | None = None

    def __post_init__(self) -> None:
        if not self.parameter_code.strip():
            raise ValueError("check без parameter_code")
        if not self.location.strip():
            raise ValueError("check без location: локализация обязательна (ТЗ п. 14)")

    def to_wire(self) -> dict[str, object]:
        wire: dict[str, object] = {
            "parameter_code": self.parameter_code,
            "location": self.location,
            "violation_label": self.violation_label.value,
            "evidence": [item.to_wire() for item in self.evidence],
        }
        for key, value in (
            ("pd_value", self.pd_value),
            ("rd_value", self.rd_value),
            ("id_value", self.id_value),
        ):
            if value is not None:
                wire[key] = value
        if self.protocol_status is not None:
            wire["protocol_status"] = self.protocol_status.value
        if self.criticality is not None:
            wire["criticality"] = self.criticality
        return wire


def _fragment_value(fragment: EvidenceFragment) -> Value:
    extraction = fragment.extracted
    if extraction.normalized_value is not None:
        return extraction.normalized_value
    return extraction.raw_token


def stage_values(group: EvidenceGroup) -> dict[DocStage, Value]:
    """Значения по стадиям. Два разных значения на одной стадии — ошибка связки."""

    values: dict[DocStage, Value] = {}
    for fragment in group.fragments:
        stage = fragment.document.doc_stage
        value = _fragment_value(fragment)
        if stage in values and values[stage] != value:
            raise ValueError(
                f"{group.evidence_group_id}: на стадии {stage.value} два разных значения "
                f"({values[stage]!r} и {value!r}) — связка не однозначна"
            )
        values[stage] = value
    return values


def evidence_from_group(group: EvidenceGroup) -> tuple[SubmissionEvidence, ...]:
    """Доказательства без дублей, в порядке фрагментов группы."""

    seen: set[tuple[str, str, int]] = set()
    items: list[SubmissionEvidence] = []
    for fragment in group.fragments:
        document = fragment.document
        key = (document.doc_stage.value, document.file_id, fragment.page)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            SubmissionEvidence(
                stage=document.doc_stage,
                file_id=document.file_id,
                pdf_page_number=fragment.page,
            )
        )
    return tuple(items)


def location_from_group(group: EvidenceGroup) -> str:
    """Ключ организатора: номер помещения или конструктивный элемент, иначе «объект».

    Стадия, шифр, редакция, лист и страница лежат в evidence, не в location.
    Отдельного поля помещения во фрагменте пока нет, поэтому ключ — «объект».
    """

    if not group.fragments:
        raise ValueError(f"{group.evidence_group_id}: нет фрагментов для локализации")
    return "объект"


def dual_read_required(rule: dict[str, object] | None) -> bool:
    """`extractor.dual_read_required` из матрицы. Нет правила — нет требования."""

    if rule is None:
        return False
    extractor = rule.get("extractor")
    if not isinstance(extractor, dict):
        return False
    return extractor.get("dual_read_required") is True


def _assert_groundedness(group: EvidenceGroup, *, require_second_read: bool) -> None:
    for fragment in group.fragments:
        if fragment.role not in _COMPARED_ROLES:
            continue
        extraction = fragment.extracted
        if not extraction.usable_for_automatic_finding:
            raise ValueError(
                f"{fragment.fragment_id}: значение не подтверждено токенами источника — "
                "автоматический кандидат запрещён (ADR-0001)"
            )
        if require_second_read and extraction.second_read_agrees is not True:
            raise ValueError(
                f"{fragment.fragment_id}: правило требует двойного чтения, "
                "а второе чтение не подтвердило значение"
            )


def build_check(
    finding: Finding,
    group: EvidenceGroup | None = None,
    *,
    missing_stage: DocStage | None = None,
    criticality: str | None = None,
    location: str | None = None,
    style: ContestCodeStyle | None = None,
    require_second_read: bool | None = None,
    rule: dict[str, object] | None = None,
    known_codes: KnownCodes = None,
) -> SubmissionCheck:
    """Собрать строку ответа из находки и её доказательства.

    Проверки отказа (все — намеренно fail-closed):

    * код параметра обязан канонизироваться в код матрицы;
    * доказательство обязано принадлежать этой же находке и этому же правилу;
    * `VIOLATION_PRESENT` без локализации не выпускается: без страницы и файла
      организатор не сможет его засчитать, а FPR вырастет;
    * автоматический кандидат обязан опираться на grounded-значения;
    * `dual_read_required` из правила исполняется, даже если вызывающий
      забыл передать `require_second_read`.
    """

    need_second_read = (
        dual_read_required(rule) if require_second_read is None else require_second_read
    )
    code = contest_parameter_code(finding.rule_code, style, known_codes=known_codes)
    label = contest_violation_label(finding.finding_status)

    if group is not None:
        finding_code = canonicalize_rule_code(finding.rule_code, known_codes=known_codes)
        group_code = canonicalize_rule_code(group.rule_code, known_codes=known_codes)
        if group_code != finding_code:
            raise ValueError(
                f"{finding.finding_id}: доказательство правила {group.rule_code} "
                f"подставлено находке правила {finding.rule_code}"
            )
        if (
            finding.evidence_group_id is not None
            and finding.evidence_group_id != group.evidence_group_id
        ):
            raise ValueError(
                f"{finding.finding_id}: evidence_group_id находки и группы расходятся"
            )

    evidence: tuple[SubmissionEvidence, ...] = ()
    values: dict[DocStage, Value] = {}
    resolved_location = location
    if group is not None and group.fragments:
        if finding.finding_status is FindingStatus.CANDIDATE:
            _assert_groundedness(group, require_second_read=need_second_read)
        evidence = evidence_from_group(group)
        values = stage_values(group)
        if resolved_location is None:
            resolved_location = location_from_group(group)

    if label is ContestViolationLabel.VIOLATION_PRESENT and not evidence:
        raise ValueError(
            f"{finding.finding_id}: нарушение без доказательства в ответ не попадает "
            "(ТЗ п. 14: локализация обязательна)"
        )

    if resolved_location is None:
        if label is ContestViolationLabel.MISSING_DOCUMENT:
            stage = missing_stage.value if missing_stage is not None else "ПД/РД/ИД"
            resolved_location = f"{stage}: документ не представлен"
        else:
            raise ValueError(
                f"{finding.finding_id}: нет ни доказательства, ни явной location — "
                "строка ответа была бы нелокализуемой"
            )

    return SubmissionCheck(
        parameter_code=code,
        location=resolved_location,
        violation_label=label,
        evidence=evidence,
        pd_value=values.get(DocStage.PD),
        rd_value=values.get(DocStage.RD),
        id_value=values.get(DocStage.ID),
        protocol_status=contest_protocol_status(
            finding.finding_status,
            review_priority=finding.review_priority,
            missing_stage=missing_stage,
        ),
        criticality=criticality,
    )


def build_submission(
    object_id: str,
    checks: Iterable[SubmissionCheck],
    *,
    known_codes: Sequence[str] | frozenset[str] | None = None,
) -> dict[str, object]:
    """JSON ответа участника: детерминированный порядок, без дублей и без чужих кодов."""

    if not object_id.strip():
        raise ValueError("submission без object_id")
    allowed = None if known_codes is None else {canonicalize_rule_code(c) for c in known_codes}

    wire: list[dict[str, object]] = []
    seen: set[str] = set()
    for check in checks:
        if allowed is not None and canonicalize_rule_code(check.parameter_code) not in allowed:
            raise ValueError(
                f"{check.parameter_code}: кода нет в матрице — ответ бы ссылался на "
                "несуществующий параметр"
            )
        item = check.to_wire()
        fingerprint = repr(sorted(item.items(), key=lambda pair: pair[0]))
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        wire.append(item)

    wire.sort(key=lambda item: (str(item["parameter_code"]), str(item["location"])))
    return {"object_id": object_id, "checks": wire}


def _missing_stage_from_rationale(rationale: str) -> DocStage | None:
    for stage in DocStage:
        if f"{stage.value} не представлен" in rationale:
            return stage
    return None


def findings_to_submission(
    object_id: str,
    findings: Sequence[Finding],
    groups: Sequence[EvidenceGroup] = (),
    *,
    known_codes: Sequence[str] | frozenset[str] | None = None,
    rules: Mapping[str, dict[str, object]] | None = None,
) -> dict[str, object]:
    """Собрать JSON участника из находок. Единственная точка сборки, не руками."""

    grouped = {group.evidence_group_id: group for group in groups}
    checks: list[SubmissionCheck] = []
    for finding in findings:
        group = None
        if finding.evidence_group_id is not None:
            group = grouped.get(finding.evidence_group_id)
        rule = None
        if rules is not None:
            rule = rules.get(canonicalize_rule_code(finding.rule_code))
        location = None
        if group is None or not group.fragments:
            text = finding.rationale.strip()
            location = text or None
        checks.append(
            build_check(
                finding,
                group,
                missing_stage=_missing_stage_from_rationale(finding.rationale),
                location=location,
                rule=rule,
                known_codes=known_codes,
            )
        )
    return build_submission(object_id, checks, known_codes=known_codes)
