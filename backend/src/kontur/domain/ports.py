"""Порты домена. Инфраструктура реализует эти Protocol, домен их только вызывает.

Fail-closed: молчание адаптера не считается успехом. Адаптер, который не умеет
выполнить операцию, обязан вернуть явный отказ, а не пустой результат.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from kontur.domain.models import (
    DocumentRef,
    EvidenceFragment,
    EvidenceGroup,
    Extraction,
    Finding,
    Polygon,
)


@runtime_checkable
class DocumentProfiler(Protocol):
    """L0. Профиль файла: формат, целостность, слои, геометрия страниц."""

    def profile(self, path: Path) -> dict[str, object]: ...


@runtime_checkable
class TextExtractor(Protocol):
    """L2. Первичен векторный слой; OCR вызывается только для растровых зон."""

    engine_name: str
    engine_version: str

    def extract_page_tokens(self, path: Path, page: int) -> list[tuple[str, Polygon]]: ...


@runtime_checkable
class RegionReader(Protocol):
    """L2. Чтение выделенной зоны (штамп, ячейка таблицы, размер на чертеже)."""

    def read_region(self, path: Path, page: int, polygon: Polygon) -> Extraction: ...


@runtime_checkable
class CoordinateMapper(Protocol):
    """L3. Единственное место, где учитываются MediaBox, CropBox, Rotate и DPI."""

    def to_normalized(self, path: Path, page: int, polygon: Polygon) -> Polygon: ...

    def to_source(self, path: Path, page: int, polygon_norm: Polygon) -> Polygon: ...


@runtime_checkable
class RevisionResolver(Protocol):
    """L4. Возвращает эталон либо сообщает о конфликте (ADR-0003)."""

    def resolve(self, candidates: list[DocumentRef]) -> DocumentRef | None: ...


@runtime_checkable
class DocumentPairing(Protocol):
    """L5. Кандидаты сопоставления ПД↔РД↔ИД: top-k, не top-1."""

    def candidates(
        self, anchor: DocumentRef, pool: list[DocumentRef], k: int
    ) -> list[DocumentRef]: ...


@runtime_checkable
class RuleRegistry(Protocol):
    """L6. Матрица как данные (ADR-0004)."""

    matrix_version: str

    def get(self, code: str) -> dict[str, object]: ...

    def all_codes(self) -> list[str]: ...

    def coverage_report(self) -> dict[str, int]: ...


@runtime_checkable
class Comparator(Protocol):
    """L6. Детерминированное сравнение. Никакой модели внутри."""

    def compare(self, rule: dict[str, object], group: EvidenceGroup) -> Finding: ...


@runtime_checkable
class EvidenceStore(Protocol):
    """L7. Неизменяемое хранилище доказательств."""

    def put(self, fragment: EvidenceFragment) -> str: ...

    def get(self, fragment_id: str) -> EvidenceFragment: ...


@runtime_checkable
class ProtocolRepository(Protocol):
    """L9. Версионированный протокол; финализированная версия не изменяется."""

    def save(self, protocol: dict[str, object]) -> int: ...

    def load(self, protocol_id: str, version: int | None = None) -> dict[str, object]: ...


@runtime_checkable
class AuditLog(Protocol):
    """Неизменяемый журнал. Удаление событий не предусмотрено интерфейсом."""

    def record(self, actor_id: str, action: str, payload: dict[str, object]) -> None: ...


@runtime_checkable
class TaskQueue(Protocol):
    """Доставка at-least-once; бизнес-эффект обязан быть ровно один."""

    def publish(self, topic: str, payload: dict[str, object], idempotency_key: str) -> None: ...


@runtime_checkable
class ExternalInspectionSync(Protocol):
    """L9. Внешняя ИС (целевая — ИАИС «РиН»). Только PROTOCOL_FINALIZED."""

    def send(self, protocol: dict[str, object], idempotency_key: str) -> str: ...


@runtime_checkable
class AdvisoryModel(Protocol):
    """LLM/VLM. Никогда не возвращает finding_status (ADR-0001).

    Вход трактуется как данные, не как инструкции. Инструментов и секретов
    реализация не получает.
    """

    def draft_explanation(self, finding: Finding) -> str: ...

    def propose_candidates(self, context: dict[str, object]) -> list[dict[str, object]]: ...
