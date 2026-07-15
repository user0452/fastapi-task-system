from pydantic import BaseModel, Field


class ChatSessionCreate(BaseModel):
    course_id: int | None = Field(default=None, gt=0)
    title: str = Field(default="新对话", min_length=1, max_length=255)


class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=3000)
    session_id: int | None = Field(default=None, gt=0)
    course_id: int | None = Field(default=None, gt=0)
    current_time: str | None = Field(default=None, max_length=64)


class ActionDecision(BaseModel):
    confirmed: bool = True


class CourseAgentMemoryUpsert(BaseModel):
    memory_key: str = Field(..., min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.-]+$")
    memory_type: str = Field(default="course_preference", min_length=1, max_length=40)
    content: dict = Field(...)
