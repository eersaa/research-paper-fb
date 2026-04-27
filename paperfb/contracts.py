"""Shared cross-agent types.

This module is the sole integration surface between agents. Agent subpackages
import their inter-agent types from here and never from each other.

Review dict shape (produced by Reviewer Agent's write_review tool, consumed by
Renderer and Judge) is documented via REVIEW_REQUIRED_FIELDS below. Kept as a
dict rather than a dataclass because it arrives directly from an LLM tool call.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ReviewerTuple:
    """Deterministic sampler output; input to Profile Creation LLM step."""
    id: str
    specialty: dict
    stance: str
    primary_focus: str
    secondary_focus: Optional[str]


@dataclass
class ReviewerProfile:
    """Profile Creation output; input to Reviewer Agent."""
    id: str
    specialty: dict
    stance: str
    primary_focus: str
    secondary_focus: Optional[str]
    persona_prompt: str


@dataclass
class ClassificationResult:
    """Classification Agent output. `classes` is a list of
    {path: str, weight: 'High'|'Medium'|'Low', rationale: str} dicts."""
    classes: list[dict]


REVIEW_REQUIRED_FIELDS = [
    "reviewer_id",
    "reviewer_name",
    "stance",
    "primary_focus",
    "strong_aspects",
    "weak_aspects",
    "recommended_changes",
]
