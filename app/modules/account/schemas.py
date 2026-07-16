from pydantic import ConfigDict, field_validator

from app.core.request_models import TrimmedRequestModel
from app.core.time_utils import validate_timezone_name


class AccountSettingsUpdate(TrimmedRequestModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return validate_timezone_name(value)


__all__ = ["AccountSettingsUpdate"]
