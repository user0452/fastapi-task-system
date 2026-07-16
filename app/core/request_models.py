"""Shared validation defaults for public request payloads."""

from pydantic import BaseModel, ConfigDict


class TrimmedRequestModel(BaseModel):
    """Normalize surrounding whitespace before applying field constraints."""

    model_config = ConfigDict(str_strip_whitespace=True)


__all__ = ["TrimmedRequestModel"]
