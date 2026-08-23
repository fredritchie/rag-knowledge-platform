from __future__ import annotations

from typing import Any


class ApplicationError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 400,
        details: dict[str, Any] | None = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class NotFoundError(ApplicationError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            "NOT_FOUND", f"{resource} not found", status_code=404, details={"id": resource_id}
        )


class ForbiddenError(ApplicationError):
    def __init__(self, message: str = "Insufficient permission"):
        super().__init__("FORBIDDEN", message, status_code=403)


class ConflictError(ApplicationError):
    def __init__(self, code: str, message: str, **details: Any):
        super().__init__(code, message, status_code=409, details=details)
