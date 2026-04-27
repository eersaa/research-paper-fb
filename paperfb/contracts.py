"""Shared cross-agent types.

This module is the sole integration surface between agents. Agent subpackages
import their inter-agent types from here and never from each other.

Review dict shape (produced by Reviewer Agent's write_review tool, consumed by
Renderer and Judge) is documented via REVIEW_REQUIRED_FIELDS below. Kept as a
dict rather than a dataclass because it arrives directly from an LLM tool call.
"""
from dataclasses import dataclass
from typing import Optional, TypedDict


@dataclass(frozen=True)
class ReviewerTuple:
    """Deterministic sampler output; input to Profile Creation LLM step.

    `specialty` carries the full ACM class dict ({path, weight, rationale,
    description, ...}) in-memory so Profile Creation can ground the persona
    prompt without re-reading data/acm_ccs.json. Flattened to `path` (str) at
    the reviewer JSON wire boundary.
    """
    id: str
    specialty: dict
    stance: str
    primary_focus: str
    secondary_focus: Optional[str]
    name: str = ""   # Finnish given name assigned by the sampler


@dataclass
class ReviewerProfile:
    """Profile Creation output; input to Reviewer Agent.

    `specialty` shape matches ReviewerTuple.specialty (in-memory dict;
    flattened to path string in the on-disk reviewer JSON).
    """
    id: str
    specialty: dict
    stance: str
    primary_focus: str
    secondary_focus: Optional[str]
    persona_prompt: str
    name: str = ""   # Finnish given name assigned by the sampler


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


class SkippedReviewer(TypedDict):
    """Orchestrator-built dict for a reviewer whose run raised. Consumed by the
    renderer's "Skipped reviewers" section."""
    id: str
    reason: str
