import json
from unittest.mock import MagicMock

import pytest

from paperfb.handoffs import HandoffResult, build_setup_review_board, classify_to_profile
from paperfb.schemas import (
    BoardReport,
    CCSClass,
    ClassificationResult,
    Keywords,
    Review,
    ProfileBoard,
    ReviewerProfile,
    SkippedReviewer,
)


def _ctx():
    """Stub ContextVariables — a plain dict; AG2's ContextVariables is dict-like.
    The handoff function must accept dict-style read/write so we can unit-test it
    without instantiating the AG2 class.
    """
    return {}


def test_classify_to_profile_writes_full_classification_to_context():
    cr = ClassificationResult(
        keywords=Keywords(extracted_from_paper=["x"], synthesised=[]),
        classes=[CCSClass(path="A → B", weight="High", rationale="r")],
    )
    ctx = _ctx()
    result = classify_to_profile(cr.model_dump_json(), ctx)
    saved = ClassificationResult.model_validate(ctx["classification"])
    assert saved == cr
    # Curated message goes downstream
    assert "A → B" in result.message
    # Keywords MUST NOT leak into the downstream prompt (spec §4.1)
    assert "x" not in result.message


def test_classify_to_profile_message_lists_only_class_paths():
    cr = ClassificationResult(
        keywords=Keywords(extracted_from_paper=[], synthesised=["k1"]),
        classes=[
            CCSClass(path="A → B", weight="High", rationale="r1"),
            CCSClass(path="C → D", weight="Low", rationale="r2"),
        ],
    )
    result = classify_to_profile(cr.model_dump_json(), _ctx())
    assert "A → B" in result.message
    assert "C → D" in result.message
    # Rationales stay in context_variables, not in the downstream message
    assert "r1" not in result.message


# ---------------------------------------------------------------------------
# setup_review_board tests (Task 10)
# ---------------------------------------------------------------------------


def _profile_board(ids=("r1", "r2", "r3")) -> ProfileBoard:
    return ProfileBoard(reviewers=[
        ReviewerProfile(
            id=i, name=n, specialty="A → B", stance="critical",
            primary_focus="methods", secondary_focus=None,
            persona_prompt="...", profile_summary="...",
        )
        for i, n in zip(ids, ["Aino", "Eero", "Liisa"])
    ])


def _review_json(rid: str) -> str:
    return json.dumps({
        "reviewer_id": rid,
        "strong_aspects": "good framing",
        "weak_aspects": "small N",
        "recommended_changes": "more seeds",
    })


def _stub_reviewer(reply_value):
    """Build a MagicMock standing in for a ConversableAgent.

    reply_value: what generate_reply(...) returns. May be a JSON string, a dict,
    a Review, or a callable raising an exception (use side_effect for that).
    """
    agent = MagicMock(name="reviewer")
    if callable(reply_value) and not isinstance(reply_value, (dict, str)):
        agent.generate_reply.side_effect = reply_value
    else:
        agent.generate_reply.return_value = reply_value
    return agent


def test_setup_review_board_happy_path_collects_all_reviews():
    pb = _profile_board()
    ctx = {"manuscript": "manuscript text"}

    def build_reviewer(profile, cfg):
        return _stub_reviewer(_review_json(profile.id))

    setup = build_setup_review_board(
        reviewer_llm_config={"model": "x"},
        build_reviewer=build_reviewer,
    )
    result = setup(pb.model_dump_json(), ctx)

    assert isinstance(result, HandoffResult)
    # context_variables populated
    assert ctx["profiles"] == pb.model_dump()
    assert ctx["expected_reviewer_ids"] == ["r1", "r2", "r3"]
    board = BoardReport.model_validate(ctx["board"])
    assert len(board.reviews) == 3
    assert {r.reviewer_id for r in board.reviews} == {"r1", "r2", "r3"}
    assert board.skipped == []


def test_setup_review_board_partial_failure_marks_skipped():
    pb = _profile_board()
    ctx = {"manuscript": "manuscript text"}

    def build_reviewer(profile, cfg):
        if profile.id == "r2":
            agent = MagicMock(name="reviewer_r2_failing")
            agent.generate_reply.side_effect = RuntimeError("simulated failure")
            return agent
        return _stub_reviewer(_review_json(profile.id))

    setup = build_setup_review_board(
        reviewer_llm_config={"model": "x"},
        build_reviewer=build_reviewer,
    )
    setup(pb.model_dump_json(), ctx)

    board = BoardReport.model_validate(ctx["board"])
    assert {r.reviewer_id for r in board.reviews} == {"r1", "r3"}
    assert len(board.skipped) == 1
    assert board.skipped[0].id == "r2"
    assert "RuntimeError" in board.skipped[0].reason
    assert "simulated failure" in board.skipped[0].reason


def test_setup_review_board_all_failures():
    pb = _profile_board()
    ctx = {"manuscript": "m"}

    def build_reviewer(profile, cfg):
        agent = MagicMock(name=f"reviewer_{profile.id}")
        agent.generate_reply.side_effect = ValueError("boom")
        return agent

    setup = build_setup_review_board(
        reviewer_llm_config={"model": "x"},
        build_reviewer=build_reviewer,
    )
    setup(pb.model_dump_json(), ctx)

    board = BoardReport.model_validate(ctx["board"])
    assert board.reviews == []
    assert {s.id for s in board.skipped} == {"r1", "r2", "r3"}


def test_setup_review_board_accepts_dict_or_pydantic_reply():
    """generate_reply may return JSON str, dict, or already-parsed Review.
    All three should coerce successfully."""
    pb = _profile_board(ids=("r1", "r2", "r3"))
    ctx = {"manuscript": "m"}

    def build_reviewer(profile, cfg):
        if profile.id == "r1":
            reply = _review_json("r1")  # JSON str
        elif profile.id == "r2":
            reply = json.loads(_review_json("r2"))  # dict
        else:
            reply = Review(reviewer_id="r3", strong_aspects="s", weak_aspects="w", recommended_changes="c")
        return _stub_reviewer(reply)

    setup = build_setup_review_board(
        reviewer_llm_config={"model": "x"},
        build_reviewer=build_reviewer,
    )
    setup(pb.model_dump_json(), ctx)

    board = BoardReport.model_validate(ctx["board"])
    assert len(board.reviews) == 3
    assert {r.reviewer_id for r in board.reviews} == {"r1", "r2", "r3"}
