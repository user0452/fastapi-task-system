from pydantic import Field

from app.core.request_models import TrimmedRequestModel


class TextMaterialCreate(TrimmedRequestModel):
    title: str = Field(..., min_length=1, max_length=255)
    content: str = Field(..., min_length=1, max_length=2_000_000)


class MaterialSearchRequest(TrimmedRequestModel):
    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
