from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


def error_payload(message: str, code: int, details: Any = None) -> dict:
    return {
        "code": code,
        "message": message,
        "data": None,
        "details": details,
    }


class ApiJSONResponse(JSONResponse):
    """JSON response that remains mapping-compatible with legacy helpers."""

    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        super().__init__(status_code=status_code, content=payload)

    def __getitem__(self, key: str):
        return self.payload[key]

    def get(self, key: str, default: Any = None):
        return self.payload.get(key, default)


class AppError(Exception):
    def __init__(
        self,
        message: str,
        status_code: int = 400,
        error_code: str = "APP_ERROR",
        details: Any = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, AppError):
        raise exc
    payload = error_payload(exc.message, exc.status_code, exc.details)
    payload["error_code"] = exc.error_code
    return JSONResponse(status_code=exc.status_code, content=payload)
