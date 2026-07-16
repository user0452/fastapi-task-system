from datetime import datetime
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from app.core.request_models import TrimmedRequestModel

CourseStatus = Literal[
    "draft",
    "preparing",
    "diagnostic_pending",
    "active",
    "completed",
    "archived",
]


class CourseCreate(TrimmedRequestModel):
    name: str = Field(..., min_length=1, max_length=100)
    goal: str = Field(default="", max_length=500)
    exam_at: datetime | None = None
    daily_minutes: int = Field(default=30, ge=10, le=480)


class CourseUpdate(TrimmedRequestModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=100)
    goal: str | None = Field(default=None, max_length=500)
    exam_at: datetime | None = None
    daily_minutes: int | None = Field(default=None, ge=10, le=480)

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("至少提供一个需要更新的字段")
        return self


class CourseStatusTransition(TrimmedRequestModel):
    model_config = ConfigDict(extra="forbid")

    status: CourseStatus


class CourseArchiveCommand(TrimmedRequestModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: bool
