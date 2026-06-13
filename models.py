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

class StudentProfileGenerateRequest(BaseModel):
    text: str = Field(...,min_length=1,max_length=3000)

class LearningResource(BaseModel):
    title:str = Field(...,min_length=1,max_length=100)
    resource_type:Literal["explanation"] = "explanation"
    content:str = Field(...,min_length=1)
    key_points:list[str] = Field(default_factory=list)
    examples:list[str] = Field(default_factory=list)

class LearningResourceGenerateRequest(BaseModel):
    course_name: str = Field(...,min_length=1,max_length=100)
    topic: str = Field(...,min_length=1,max_length=100)

class QuizQuestion(BaseModel):
    question:str = Field(...,min_length=1,max_length=500)
    answer:str = Field(...,min_length=1,max_length=1000)
    question_type:Literal["choice","short_answer","coding"] = "short_answer"
    difficulty:Literal["easy", "medium", "hard"] = "easy"

class QuizSet(BaseModel):
    title:str = Field(...,min_length=1,max_length=100)
    course_name:str = Field(...,min_length=1,max_length=100)
    topic:str = Field(...,min_length=1,max_length=100)
    questions:list[QuizQuestion] = Field(default_factory=list)

class QuizGenerateRequest(BaseModel):
    course_name: str = Field(...,min_length=1,max_length=100)
    topic: str = Field(...,min_length=1,max_length=100)

class PlanPreviewRequest(BaseModel):
    course_name: str = Field(..., min_length=1, max_length=100)
    topic:str = Field(...,min_length=1,max_length=100)
    days:int = Field(default=3,ge=1,le=7)

class PlanTaskPreview(BaseModel):
    title: str = Field(...,min_length=1,max_length=100)
    description: Optional[str] = Field(default="",max_length=500)
    status:Literal["todo","doing","done"] = "todo"
    priority:Literal["low", "medium", "high"] = "medium"

class LearningPlan(BaseModel):
    plan_title: str = Field(...,min_length=1,max_length=100)
    course_name:str = Field(...,min_length=1,max_length=100)
    topic:str = Field(...,min_length=1,max_length=100)
    days:int = Field(default=3,ge=1,le=30)
    tasks_preview: list[PlanTaskPreview] = Field(default_factory=list)

class PlanConfirmRequest(BaseModel):
    tasks_preview: list[PlanTaskPreview] = Field(default_factory=list)

class AgentChatRequest(BaseModel):
    message: str = Field(...,min_length=1,max_length=3000)

class AgentToolPlan(BaseModel):
    reply: str = Field(..., min_length=1)
    status:Literal["need_more_info","ready_to_execute","chat_only"] = "need_more_info"
    intent: Literal[
        "generate_study_package",
        "generate_resource",
        "generate_quiz",
        "generate_plan",
        "update_profile",
        "qa",
        "unknown"
    ] = "unknown"
    course_name: Optional[str] = None
    topic: Optional[str] = None
    days: int = Field(default=3, ge=1, le=7)

    available_time: Optional[str] = None
    current_level: Optional[str] = None
    resource_preference: Optional[str] = None

    missing_fields: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    need_confirm_import: bool = True

