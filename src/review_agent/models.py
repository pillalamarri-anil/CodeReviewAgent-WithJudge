"""Strict, Pydantic-validated data model for the review (PRD s6, s7).

The LLM returns exactly ``LLMReview``; the risk score is never supplied by the model
-- it is computed in code (see ``review.scoring``).
"""

from __future__ import annotations

import enum
from typing import List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Severity(str, enum.Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class Category(str, enum.Enum):
    BUG = "BUG"
    SECURITY = "SECURITY"
    PERFORMANCE = "PERFORMANCE"
    ERROR_HANDLING = "ERROR_HANDLING"
    CONCURRENCY = "CONCURRENCY"
    MAINTAINABILITY = "MAINTAINABILITY"
    TESTING = "TESTING"


class Finding(BaseModel):
    """One issue on one changed line. Matches the PRD s6 JSON contract."""

    model_config = ConfigDict(extra="forbid")

    severity: Severity
    category: Category
    file: str
    line: int = Field(ge=0)
    title: str
    description: str
    impact: str
    recommendation: str
    suggested_fix: Optional[str] = None
    evidence: str = Field(description="verbatim snippet copied from the input")
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator("title", "description", "evidence")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be blank")
        return v


class LLMReview(BaseModel):
    """The complete, schema-valid object returned by one LLM call."""

    model_config = ConfigDict(extra="ignore")

    summary: str
    findings: List[Finding] = Field(default_factory=list)


class FileReviewResult(BaseModel):
    """Per-file outcome. ``status='failed'`` means the LLM call or parse failed and
    this file's review is NOT to be reported as successful (PRD s4)."""

    file: str
    status: Literal["ok", "failed", "skipped"]
    summary: str = ""
    findings: List[Finding] = Field(default_factory=list)
    error: Optional[str] = None
    repaired: bool = False


class DroppedFinding(BaseModel):
    finding: Finding
    reason: str


class JudgeReview(BaseModel):
    """The complete, schema-valid object returned by the judge's consolidation call.

    ``findings`` is the final, cross-file-correlated and deduplicated list; ``dropped``
    is every candidate finding the judge rejected as unproven or a duplicate."""

    model_config = ConfigDict(extra="ignore")

    summary: str
    findings: List[Finding] = Field(default_factory=list)
    dropped: List[DroppedFinding] = Field(default_factory=list)


class JudgeOutcome(BaseModel):
    """Outcome of the judge stage. ``status='failed'`` means the judge call or parse
    failed after the repair retry -- the judge is a refinement layer, not a hard
    dependency, so the pipeline falls back to the pre-judge findings rather than
    failing the whole review."""

    status: Literal["ok", "failed"]
    review: Optional[JudgeReview] = None
    error: Optional[str] = None
    repaired: bool = False


class TokenUsage(BaseModel):
    """Tokens consumed by the LLM across the whole PR review (every changed-file call,
    including repair retries -- PRD s6). For the ``openai`` provider these are the exact
    counts reported by the API; for ``mock`` they are the same offline ~4-chars/token
    estimate the context budget uses."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    calls: int = 0


class GateResult(BaseModel):
    status: Literal["PASS", "CHANGES REQUESTED"]
    exit_code: int
    score: int
    counts: dict
    reasons: List[str] = Field(default_factory=list)


class ReviewReport(BaseModel):
    """The always-written ``review-report.json`` artifact (PRD s4 step 9)."""

    model_config = ConfigDict(extra="ignore")

    repo: Optional[str] = None
    pr: Optional[int] = None
    base: Optional[str] = None
    head: Optional[str] = None
    commit: Optional[str] = None

    provider: str = "mock"
    review_ok: bool = True
    summary: str = ""

    files_reviewed: List[FileReviewResult] = Field(default_factory=list)
    findings: List[Finding] = Field(default_factory=list)
    dropped: List[DroppedFinding] = Field(default_factory=list)

    gate: Optional[GateResult] = None
    duration_seconds: float = 0.0
    context_budget: dict = Field(default_factory=dict)
    context_summary: dict = Field(default_factory=dict)

    token_usage: TokenUsage = Field(
        default_factory=TokenUsage,
        description="grand total across the per-file review calls AND the judge call")
    review_token_usage: TokenUsage = Field(default_factory=TokenUsage)
    judge_token_usage: TokenUsage = Field(default_factory=TokenUsage)
