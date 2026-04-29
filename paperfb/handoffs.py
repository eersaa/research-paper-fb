"""FunctionTarget bodies for AG2 agent handoffs (spec §4.1, §4.4).

These are *bodies* — pipeline.py wraps them into AG2 FunctionTargetResult at
registration time. Keeping the layer indirected lets us unit-test handoff
logic without spinning up an AG2 chat.

Per AG2 0.12.1 errata: the reviewer board is NOT a RedundantPattern (that class
doesn't exist in 0.12.1). Instead, build_setup_review_board returns a closure
that fans out N reviewers inline — each via reviewer.generate_reply(messages=...)
— and constructs BoardReport deterministically.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import ValidationError

from paperfb.schemas import (
    BoardReport,
    ClassificationResult,
    ProfileBoard,
    Review,
    ReviewerProfile,
    SkippedReviewer,
)


@dataclass
class HandoffResult:
    """Stand-in for ag2's FunctionTargetResult during unit testing."""
    message: str | None = None
    target: Any | None = None


def classify_to_profile(agent_output: str, context_variables: dict) -> HandoffResult:
    """Classification → ProfileCreation handoff (spec §4.1).

    Parses the full ClassificationResult, stashes it in context_variables for
    the renderer to read post-chat, and forwards a curated, classes-only
    message to ProfileCreation. Keywords stay in context_variables and the run
    log; they MUST NOT enter ProfileCreation's prompt (spec §4.1).
    """
    cr = ClassificationResult.model_validate_json(agent_output)
    context_variables["classification"] = cr.model_dump()
    paths = ", ".join(c.path for c in cr.classes)
    return HandoffResult(message=f"ACM classes: [{paths}]")


def _coerce_to_review(raw: Any, expected_id: str) -> Review:
    """AG2 0.12.1 may return generate_reply output as str, dict, or Review.
    Normalise to a Review or raise.

    Observed return types (to be confirmed in Task 17 live acceptance):
    - str: JSON string — most common when response_format is set
    - dict: some AG2 paths return parsed dict
    - Review: if the caller pre-parses or tests inject a Pydantic model
    - object with .content attribute: some AG2 reply wrappers
    """
    if isinstance(raw, Review):
        return raw
    if isinstance(raw, str):
        return Review.model_validate_json(raw)
    if isinstance(raw, dict):
        return Review.model_validate(raw)
    # Some AG2 paths wrap the content; try .content
    content = getattr(raw, "content", None)
    if isinstance(content, str):
        return Review.model_validate_json(content)
    if isinstance(content, dict):
        return Review.model_validate(content)
    raise ValueError(
        f"reviewer {expected_id}: unexpected generate_reply return type {type(raw).__name__}"
    )


def build_setup_review_board(
    *,
    reviewer_llm_config: dict,
    build_reviewer: Callable[[ReviewerProfile, dict], Any],
) -> Callable[[str, dict], HandoffResult]:
    """Returns a closure usable as a FunctionTarget body.

    The closure parses ProfileBoard, builds N reviewer agents, runs each via
    reviewer.generate_reply([{role: user, content: manuscript}]), collects the
    Pydantic Reviews (or SkippedReviewer entries on exception), and writes a
    BoardReport into context_variables["board"].

    The outer chat is signalled to terminate by returning HandoffResult with no
    target; pipeline.py wraps this into the AG2-native termination shape.
    """

    def setup_review_board(agent_output: str, context_variables: dict) -> HandoffResult:
        board_in = ProfileBoard.model_validate_json(agent_output)
        manuscript = context_variables["manuscript"]

        reviews: list[Review] = []
        skipped: list[SkippedReviewer] = []

        for profile in board_in.reviewers:
            try:
                reviewer = build_reviewer(profile, reviewer_llm_config)
                raw = reviewer.generate_reply(
                    messages=[{"role": "user", "content": manuscript}]
                )
                reviews.append(_coerce_to_review(raw, profile.id))
            except Exception as e:
                skipped.append(SkippedReviewer(
                    id=profile.id,
                    reason=f"{type(e).__name__}: {e}",
                ))

        board_report = BoardReport(reviews=reviews, skipped=skipped)

        context_variables["profiles"] = board_in.model_dump()
        context_variables["board"] = board_report.model_dump()
        context_variables["expected_reviewer_ids"] = sorted(p.id for p in board_in.reviewers)

        return HandoffResult(message="Review board complete.")

    return setup_review_board
