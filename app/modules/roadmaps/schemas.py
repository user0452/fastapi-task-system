from pydantic import Field

from app.core.request_models import TrimmedRequestModel


class RoadmapRetryRequest(TrimmedRequestModel):
    reason: str = Field(default="用户手动重试", min_length=1, max_length=300)
