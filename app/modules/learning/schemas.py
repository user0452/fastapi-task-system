from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class DiagnosticGenerateRequest(BaseModel):
    question_count: int = Field(default=6, ge=5, le=8)


class LearningAnswer(BaseModel):
    question_id: int = Field(..., gt=0)
    user_answer: str = Field(..., min_length=1, max_length=3000)


class DiagnosticSubmitRequest(BaseModel):
    answers: list[LearningAnswer] = Field(..., min_length=1)


class SessionSubmitRequest(BaseModel):
    answers: list[LearningAnswer] = Field(..., min_length=1)
    actual_minutes: int | None = Field(default=None, ge=1, le=1440)


class PracticeGenerateRequest(BaseModel):
    knowledge_point_id: int | None = Field(default=None, gt=0)
    question_count: int = Field(default=3, ge=1, le=5)
    difficulty: Literal["easy", "medium", "hard"] = "medium"


class PracticeSubmitRequest(BaseModel):
    answers: list[LearningAnswer] = Field(..., min_length=1)


class SessionRescheduleRequest(BaseModel):
    scheduled_date: date
    estimated_minutes: int | None = Field(default=None, ge=10, le=480)


class QuestionEvaluationReview(BaseModel):
    question_id: int
    question: str = Field(..., min_length=1)
    reference_answer: str = Field(..., min_length=1)
    user_answer: str = Field(..., min_length=1)
    score: int = Field(..., ge=0, le=100)
    feedback: str = Field(..., min_length=1)
    weak_point: str | None = None


class LearningEvaluationResult(BaseModel):
    quiz_set_id: int
    score: int = Field(..., ge=0, le=100)
    level: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=1)
    weak_points: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    question_reviews: list[QuestionEvaluationReview] = Field(default_factory=list)
