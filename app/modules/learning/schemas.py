from datetime import date
from typing import Literal

from pydantic import Field

from app.core.request_models import TrimmedRequestModel


class DiagnosticGenerateRequest(TrimmedRequestModel):
    question_count: int = Field(default=6, ge=5, le=8)


class LearningAnswer(TrimmedRequestModel):
    question_id: int = Field(..., gt=0)
    user_answer: str = Field(..., min_length=1, max_length=3000)


class DiagnosticSubmitRequest(TrimmedRequestModel):
    answers: list[LearningAnswer] = Field(..., min_length=1)


class SessionSubmitRequest(TrimmedRequestModel):
    answers: list[LearningAnswer] = Field(default_factory=list)
    actual_minutes: int | None = Field(default=None, ge=1, le=1440)


class PracticeGenerateRequest(TrimmedRequestModel):
    knowledge_point_id: int | None = Field(default=None, gt=0)
    question_count: int = Field(default=3, ge=1, le=5)
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class PracticeSubmitRequest(TrimmedRequestModel):
    answers: list[LearningAnswer] = Field(..., min_length=1)


class SessionRescheduleRequest(TrimmedRequestModel):
    scheduled_date: date
    estimated_minutes: int | None = Field(default=None, ge=10, le=480)


class QuestionEvaluationReview(TrimmedRequestModel):
    question_id: int
    score: int = Field(..., ge=0, le=100)
    feedback: str = Field(..., min_length=1)
    weak_point: str | None = None


class LearningEvaluationResult(TrimmedRequestModel):
    question_reviews: list[QuestionEvaluationReview] = Field(..., min_length=1)
