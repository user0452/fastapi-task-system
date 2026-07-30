from urllib.parse import urlsplit

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.core.request_models import TrimmedRequestModel
from app.core.time_utils import validate_timezone_name


def _validate_llm_base_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("API 地址必须是有效的 http 或 https URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("API 地址不能包含账号、密码、查询参数或片段")
    return value.rstrip("/")


def _validate_llm_model(value: str) -> str:
    if any(character in value for character in ("\r", "\n", "\x00")):
        raise ValueError("模型名称包含无效字符")
    return value


class AccountSettingsUpdate(TrimmedRequestModel):
    model_config = ConfigDict(extra="forbid")

    timezone: str

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        return validate_timezone_name(value)


class UserMemorySettingsUpdate(TrimmedRequestModel):
    model_config = ConfigDict(extra="forbid")

    course_auto_memory_enabled: bool | None = None
    cross_course_profile_enabled: bool | None = None

    @model_validator(mode="after")
    def validate_consistent_settings(self):
        if self.cross_course_profile_enabled and self.course_auto_memory_enabled is False:
            raise ValueError("启用跨课程画像时不能同时关闭自动课程记忆")
        return self


class UserLlmConfigUpdate(TrimmedRequestModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=160)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return _validate_llm_base_url(value)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        return _validate_llm_model(value)


class UserLlmConfigTest(TrimmedRequestModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str = Field(min_length=8, max_length=500)
    model: str = Field(min_length=1, max_length=160)
    api_key: str | None = Field(default=None, min_length=1, max_length=4096)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        return _validate_llm_base_url(value)

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        return _validate_llm_model(value)


__all__ = [
    "AccountSettingsUpdate",
    "UserLlmConfigTest",
    "UserLlmConfigUpdate",
    "UserMemorySettingsUpdate",
]
