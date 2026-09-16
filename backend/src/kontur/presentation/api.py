"""FastAPI-фасад. Контракт — contracts/openapi.yaml, здесь только маршруты-заглушки.

Обработка не выполняется в процессе запроса: загрузка публикует задачу в очередь
и сразу возвращает process_id. Эндпоинт статуса обязан оставаться быстрым
(целевой p95 ≤200 мс, ТЗ п. 11), поэтому читает только проекцию состояния.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from kontur.domain.state_machines import TransitionError

app = FastAPI(title="Инспектор ИИ", version="0.1.0-skeleton")

MAX_FILE_BYTES = 50 * 1024 * 1024
MAX_BATCH_BYTES = 200 * 1024 * 1024
SUPPORTED_SUFFIXES = frozenset({".pdf", ".docx", ".xml"})


@app.exception_handler(TransitionError)
async def _transition_error(_request: Request, exc: TransitionError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.get("/api/v1/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/documents/upload", status_code=202)
def upload_documents() -> dict[str, object]:
    raise NotImplementedError("L0: антивирус, хеш, лимиты, публикация задачи")


@app.get("/api/v1/processes/{process_id}/status")
def get_status(process_id: str) -> dict[str, object]:
    raise NotImplementedError("L9: чтение проекции состояния процесса")


@app.get("/api/v1/processes/{process_id}/protocol")
def get_protocol(process_id: str, version: int | None = None) -> dict[str, object]:
    raise NotImplementedError("L9: сборка протокола по Приложению 2")


@app.post("/api/v1/findings/{finding_id}/review")
def review_finding(finding_id: str) -> dict[str, object]:
    raise NotImplementedError("L8: делегирует kontur.application.review.review")


@app.post("/api/v1/processes/{process_id}/finalize")
def finalize(process_id: str) -> dict[str, object]:
    raise NotImplementedError("L8: проверка can_finalize, затем неизменяемая версия")


@app.post("/api/v1/inspection/{process_id}", status_code=202)
def sync_inspection(process_id: str) -> dict[str, object]:
    raise NotImplementedError("L9: outbox во внешнюю ИС, только PROTOCOL_FINALIZED")
