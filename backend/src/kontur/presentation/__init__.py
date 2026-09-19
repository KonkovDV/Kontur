"""Presentation: FastAPI application and its authoritative upload boundary."""

from __future__ import annotations

import fastapi
from starlette.types import ASGIApp

from kontur.presentation.upload_limits import ActualUploadLimitMiddleware, install_bounded_upload_read

_BaseFastAPI = fastapi.FastAPI


class _UploadBoundedFastAPI(_BaseFastAPI):
    """FastAPI with an outer raw-request upload limiter."""

    def build_middleware_stack(self) -> ASGIApp:
        return ActualUploadLimitMiddleware(super().build_middleware_stack())


install_bounded_upload_read()
fastapi.FastAPI = _UploadBoundedFastAPI  # type: ignore[misc]
