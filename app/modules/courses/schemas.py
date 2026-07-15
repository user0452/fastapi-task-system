from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

CourseStatus = Literal[
    "draft",
    "preparing",
    "diagnostic_pending",
    "active",
    "completed",
    "archived",
]


class CourseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    goal: str = Field(default="", max_length=500)
    exam_at: datetime | None = None
    daily_minutes: int = Field(default=30, ge=10, le=480)


class CourseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    goal: str | None = Field(default=None, max_length=500)
    exam_at: datetime | None = None
    daily_minutes: int | None = Field(default=None, ge=10, le=480)
    status: CourseStatus | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set:
            raise ValueError("至少提供一个需要更新的字段")
        return self
