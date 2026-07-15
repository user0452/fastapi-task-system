"""Shared API response helpers for v1 routers."""

from typing import Any, Generic, TypeVar

from fastapi import APIRouter
from fastapi.datastructures import DefaultPlaceholder
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    code: int = 200
    message: str = "success"
    data: T | None = None


def success(data: Any = None, message: str = "success", code: int = 200) -> dict:
    return {"code": code, "message": message, "data": data}


class V1APIRouter(APIRouter):
    """APIRouter that documents the shared v1 envelope by default.

    FastAPI represents an omitted ``response_model`` with a DefaultPlaceholder.
    An explicit ``response_model=None`` is preserved for streaming/file routes.
    """

    def add_api_route(
        self,
        path: str,
        endpoint,
        *,
        response_model: Any = None,
        **kwargs: Any,
    ) -> None:
        if isinstance(response_model, DefaultPlaceholder):
            response_model = ApiResponse[Any]
        super().add_api_route(
            path,
            endpoint,
            response_model=response_model,
            **kwargs,
        )


__all__ = ["ApiResponse", "V1APIRouter", "success"]
