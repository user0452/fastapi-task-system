from pydantic import BaseModel, Field

from app.core.request_models import TrimmedRequestModel


class AuthCredentials(TrimmedRequestModel):
    username: str = Field(..., min_length=3, max_length=80, pattern=r"^[\w.@+-]+$")
    password: str = Field(..., min_length=8, max_length=128)


class AuthUser(BaseModel):
    id: int
    username: str
    timezone: str


__all__ = ["AuthCredentials", "AuthUser"]
