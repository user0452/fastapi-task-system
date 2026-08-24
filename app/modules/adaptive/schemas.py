"""HTTP contracts for the Adaptive Tutor product surface."""

from typing import Literal

from pydantic import Field

from app.core.request_models import TrimmedRequestModel


class QuestionBankItem(TrimmedRequestModel):
    content: str = Field(..., min_length=8, max_length=8000)
    question_type: Literal["short_answer", "single_choice", "multiple_choice", "true_false"] = "short_answer"
    answer: str = Field(..., min_length=1, max_length=5000)
    rubric: str | None = Field(default=None, max_length=5000)
    explanation: str | None = Field(default=None, max_length=5000)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    source_type: Literal["user_upload", "textbook", "public_source", "search", "generated"] = "user_upload"
    source_material_id: int | None = Field(default=None, gt=0)
    source_url: str | None = Field(default=None, max_length=1000)
    objective_ids: list[int] = Field(default_factory=list, max_length=12)
    coverage_type: Literal["direct", "scenario", "transfer", "diagnostic", "review"] = "direct"
    confidence: float = Field(default=0.9, ge=0, le=1)
    quality_score: float = Field(default=0.8, ge=0, le=1)


class QuestionBankCreateRequest(TrimmedRequestModel):
    questions: list[QuestionBankItem] = Field(..., min_length=1, max_length=200)


class AdaptiveAnswerRequest(TrimmedRequestModel):
    response: str = Field(..., min_length=1, max_length=5000)
    misconception_code: str | None = Field(default=None, max_length=100)
    misconception_text: str | None = Field(default=None, max_length=500)
    misconception_confidence: float | None = Field(default=None, ge=0, le=1)


class DiagnosticStartRequest(TrimmedRequestModel):
    question_count: int = Field(default=6, ge=1, le=30)


class DiagnosticAnswer(TrimmedRequestModel):
    question_id: int = Field(..., gt=0)
    response: str = Field(..., min_length=1, max_length=5000)


class DiagnosticSubmitRequest(TrimmedRequestModel):
    answers: list[DiagnosticAnswer] = Field(..., min_length=1, max_length=30)


class CurriculumRebuildRequest(TrimmedRequestModel):
    material_id: int | None = Field(default=None, gt=0)


__all__ = [
    "AdaptiveAnswerRequest",
    "CurriculumRebuildRequest",
    "DiagnosticAnswer",
    "DiagnosticStartRequest",
    "DiagnosticSubmitRequest",
    "QuestionBankCreateRequest",
    "QuestionBankItem",
]
