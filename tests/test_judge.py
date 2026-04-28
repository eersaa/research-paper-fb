import json
from unittest.mock import MagicMock
import pytest

from scripts.judge import judge_review, RubricScores, DimensionScore, DIMENSIONS


# Inline minimal review and manuscript — tests don't depend on file fixtures.
MANUSCRIPT = "Tiny manuscript body for prompt-wiring assertions."

REVIEW = {
    "reviewer_id": "r1",
    "reviewer_name": "Aino",
    "specialty": "ML",
    "stance": "critical",
    "primary_focus": "methods",
    "secondary_focus": "results",
    "profile_summary": "",
    "strong_aspects": "x",
    "weak_aspects": "y",
    "recommended_changes": "z",
}


def _llm_returning(payload_dict: dict) -> MagicMock:
    """Stub LLMClient whose .chat(...) returns content=json.dumps(payload_dict)."""
    client = MagicMock()
    res = MagicMock()
    res.content = json.dumps(payload_dict)
    res.tool_calls = None
    res.finish_reason = "stop"
    client.chat.return_value = res
    return client


def _payload(specificity=4, actionability=4, persona_fidelity=4,
             coverage=4, non_redundancy=4) -> dict:
    return {
        "specificity":      {"score": specificity,      "justification": "spec j"},
        "actionability":    {"score": actionability,    "justification": "act j"},
        "persona_fidelity": {"score": persona_fidelity, "justification": "pf j"},
        "coverage":         {"score": coverage,         "justification": "cov j"},
        "non_redundancy":   {"score": non_redundancy,   "justification": "nr j"},
    }


def test_returns_rubric_scores_with_all_five_dimensions():
    llm = _llm_returning(_payload())
    scores = judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")
    assert isinstance(scores, RubricScores)
    for dim in DIMENSIONS:
        d = getattr(scores, dim)
        assert isinstance(d, DimensionScore)
        assert 1 <= d.score <= 5
        assert d.justification != ""


def test_mean_is_arithmetic_average_of_five_dimensions():
    llm = _llm_returning(_payload(specificity=5, actionability=4, persona_fidelity=3,
                                  coverage=2, non_redundancy=1))
    scores = judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")
    assert scores.mean == pytest.approx((5 + 4 + 3 + 2 + 1) / 5)


def test_out_of_range_score_raises():
    llm = _llm_returning(_payload(specificity=7))
    with pytest.raises(ValueError, match="specificity out of range"):
        judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")


def test_zero_score_raises():
    llm = _llm_returning(_payload(coverage=0))
    with pytest.raises(ValueError, match="coverage out of range"):
        judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")


def test_missing_dimension_raises():
    payload = _payload()
    del payload["coverage"]
    llm = _llm_returning(payload)
    with pytest.raises(ValueError, match="missing dimension coverage"):
        judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")


def test_non_int_score_raises():
    payload = _payload()
    payload["specificity"]["score"] = "five"
    llm = _llm_returning(payload)
    with pytest.raises(ValueError, match="specificity out of range"):
        judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")


def test_passes_model_through_to_llm_chat():
    llm = _llm_returning(_payload())
    judge_review(MANUSCRIPT, REVIEW, llm=llm, model="openai/gpt-4.1-mini")
    _, kwargs = llm.chat.call_args
    assert kwargs.get("model") == "openai/gpt-4.1-mini"


def test_user_message_contains_manuscript_and_review_fields():
    llm = _llm_returning(_payload())
    judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")
    _, kwargs = llm.chat.call_args
    user_msg = next(m["content"] for m in kwargs["messages"] if m["role"] == "user")
    assert MANUSCRIPT in user_msg
    assert REVIEW["stance"] in user_msg
    assert REVIEW["primary_focus"] in user_msg
    assert REVIEW["strong_aspects"] in user_msg
    assert REVIEW["secondary_focus"] in user_msg
