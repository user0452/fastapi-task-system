from pydantic import BaseModel, Field


class AuthCredentials(BaseModel):
    username: str = Field(..., min_length=3, max_length=80, pattern=r"^[\w.@+-]+$")
    password: str = Field(..., min_length=8, max_length=128)


class AuthUser(BaseModel):
    id: int
    username: str


__all__ = ["AuthCredentials", "AuthUser"]
