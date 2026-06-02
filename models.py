from pydantic import BaseModel,Field
from typing import Optional,Literal



class Task(BaseModel):
    id: int
    title: str
    description: str
    status: str
    priority: str


class TaskCreate(BaseModel):
    title: str = Field(...,min_length=1,max_length=100)
    description: Optional[str] = Field(default="",max_length=500)
    status: Optional[Literal["todo","doing","done"]] = "todo"
    priority: Optional[Literal["low", "medium", "high"]] = "medium"


class TaskUpdate(BaseModel):
    title: Optional[str] = Field(default=None,min_length=1,max_length=100)
    description: Optional[str] = Field(default=None,max_length=500)
    status: Optional[Literal["todo","doing","done"]] = None
    priority: Optional[Literal["low", "medium", "high"]] = None


class UserRegister(BaseModel):
    username: str = Field(...,min_length=3,max_length=30)
    password: str = Field(...,min_length=6,max_length=30)


class UserLogin(BaseModel):
    username: str = Field(...,min_length=3,max_length=30)
    password: str = Field(...,min_length=6,max_length=30)

class AICommandRequest(BaseModel):
    text: str = Field(...,min_length=1,max_length=500)

class ExamScheduleParseRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=3000)

class ExamInfo(BaseModel):
    course: str = Field(...,min_length=1,max_length=100)
    exam_date: str = Field(...,min_length=1,max_length=10)
    exam_time:Optional[str] = None

class ReviewPlanPreviewRequest(BaseModel):
    exams:list[ExamInfo]

class ReviewTaskPreview(BaseModel):
    title: str = Field(...,min_length=1,max_length=100)
    description: Optional[str] = Field(default="",max_length=500)
    status:Literal["todo","doing","done"] = "todo"
    priority:Literal["low", "medium", "high"] = "medium"

class ConfirmReviewPlanRequest(BaseModel):
    tasks_preview: list[ReviewTaskPreview]

class StudentProfile(BaseModel):
    grade:Optional[ str] = None
    major:Optional[ str] = None
    goals: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    available_time:Optional[ str] = None
    learning_preference:Optional[ str] = None