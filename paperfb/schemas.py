"""Cross-agent message + structured-output schemas. Replaces paperfb/contracts.py.

Every BaseModel sets model_config = ConfigDict(title=<ClassName>, extra="forbid")
to satisfy OpenAPI's title requirement and Gemini's additionalProperties quirk
(spec §5.1; AG2 issue #2348).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


# Classification ─────────────────────────────────────────────────────────────


class CCSMatch(BaseModel):
    model_config = ConfigDict(title="CCSMatch", extra="forbid")
    path: str
    description: str


class Keywords(BaseModel):
    model_config = ConfigDict(title="Keywords", extra="forbid")
    extracted_from_paper: list[str]
    synthesised: list[str]


class CCSClass(BaseModel):
    model_config = ConfigDict(title="CCSClass", extra="forbid")
    path: str
    weight: Literal["High", "Medium", "Low"]
    rationale: str


class ClassificationResult(BaseModel):
    model_config = ConfigDict(title="ClassificationResult", extra="forbid")
    keywords: Keywords
    classes: list[CCSClass]


# Profile Creation ───────────────────────────────────────────────────────────


class ReviewerTuple(BaseModel):
    model_config = ConfigDict(title="ReviewerTuple", extra="forbid")
    id: str
    name: str
    specialty: str
    stance: str
    primary_focus: str
    secondary_focus: str | None


class ReviewerProfile(BaseModel):
    model_config = ConfigDict(title="ReviewerProfile", extra="forbid")
    id: str
    name: str
    specialty: str
    stance: str
    primary_focus: str
    secondary_focus: str | None
    persona_prompt: str
    profile_summary: str


class ProfileBoard(BaseModel):
    model_config = ConfigDict(title="ProfileBoard", extra="forbid")
    reviewers: list[ReviewerProfile]


# Reviewer ───────────────────────────────────────────────────────────────────
# Slim: review *content* only. Identity metadata stays on ReviewerProfile and is
# joined back in by the renderer via reviewer_id (spec §3, §4.3).


class Review(BaseModel):
    model_config = ConfigDict(title="Review", extra="forbid")
    reviewer_id: str
    strong_aspects: str
    weak_aspects: str
    recommended_changes: str


# Aggregation ────────────────────────────────────────────────────────────────


class SkippedReviewer(BaseModel):
    model_config = ConfigDict(title="SkippedReviewer", extra="forbid")
    id: str
    reason: str


class BoardReport(BaseModel):
    model_config = ConfigDict(title="BoardReport", extra="forbid")
    reviews: list[Review]
    skipped: list[SkippedReviewer]


# Top-level run output ───────────────────────────────────────────────────────


class RunOutput(BaseModel):
    model_config = ConfigDict(title="RunOutput", extra="forbid")
    classification: ClassificationResult
    profiles: ProfileBoard
    board: BoardReport
