from typing import Literal

from pydantic import BaseModel, Field


class ExternalResourceSearchRequest(BaseModel):
    topic: str = Field(..., min_length=1, max_length=200)
    knowledge_point_id: int | None = Field(default=None, gt=0)
    max_results: int = Field(default=4, ge=3, le=6)
    force_refresh: bool = False


class ResourceInteractionRequest(BaseModel):
    interaction_type: Literal[
        "opened",
        "saved",
        "unsaved",
        "completed",
        "uncompleted",
        "helpful",
        "not_helpful",
    ]
    value: dict = Field(default_factory=dict)
