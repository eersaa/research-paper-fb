"""FunctionTarget bodies for AG2 agent handoffs (spec §4.1, §4.4).

These functions are *bodies* — Task 11 wraps them into AG2 FunctionTargetResult
at registration time. Keeping the layer indirected lets us unit-test handoff
logic without spinning up an AG2 chat.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperfb.schemas import ClassificationResult


@dataclass
class HandoffResult:
    """Stand-in for ag2's FunctionTargetResult during unit testing."""
    message: str | None = None
    target: Any | None = None


def classify_to_profile(agent_output: str, context_variables: dict) -> HandoffResult:
    """Classification → ProfileCreation handoff.

    Parses the full ClassificationResult, stashes it in context_variables for
    the renderer to read post-chat, and forwards a curated, classes-only
    message to ProfileCreation. Keywords stay in context_variables and the run
    log; they MUST NOT enter ProfileCreation's prompt (spec §4.1).
    """
    cr = ClassificationResult.model_validate_json(agent_output)
    context_variables["classification"] = cr.model_dump()
    paths = ", ".join(c.path for c in cr.classes)
    return HandoffResult(message=f"ACM classes: [{paths}]")


def setup_review_board(agent_output: str, context_variables: dict) -> HandoffResult:
    """ProfileCreation → reviewer-board handoff. Filled in by Task 10.

    Per AG2 0.12.1 errata: this function will do inline fan-out (run each reviewer,
    collect Reviews, build BoardReport deterministically) — no nested RedundantPattern,
    no Chair LLM. Stub here; real logic in Task 10.
    """
    raise NotImplementedError("setup_review_board lands in Task 10")
