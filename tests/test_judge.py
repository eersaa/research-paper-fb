import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from paperfb.schemas import (
    BoardReport, CCSClass, ClassificationResult, Keywords,
    ProfileBoard, Review, ReviewerProfile, RunOutput,
)
from scripts.judge import judge_review, DIMENSIONS


MANUSCRIPT = "Tiny manuscript body."


def _profile(rid="r1") -> ReviewerProfile:
    return ReviewerProfile(
        id=rid, name="Aino", specialty="ML",
        stance="critical", primary_focus="methods", secondary_focus="results",
        persona_prompt="...", profile_summary="...",
    )


def _review(rid="r1") -> Review:
    return Review(reviewer_id=rid, strong_aspects="x", weak_aspects="y", recommended_changes="z")


def _payload(**overrides) -> dict:
    base = {d: {"score": 4, "justification": f"{d} j"} for d in DIMENSIONS}
    for k, v in overrides.items():
        if isinstance(v, dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = {"score": v, "justification": base[k]["justification"]}
    return base


def _llm_returning(payload: dict) -> MagicMock:
    client = MagicMock()
    res = MagicMock()
    res.content = json.dumps(payload)
    res.tool_calls = None
    res.finish_reason = "stop"
    client.chat.return_value = res
    return client


def test_judge_review_returns_pydantic_judge_score():
    from paperfb.schemas import JudgeScore
    llm = _llm_returning(_payload())
    score = judge_review(MANUSCRIPT, _review(), _profile(), llm=llm, model="m")
    assert isinstance(score, JudgeScore)
    for dim in DIMENSIONS:
        d = getattr(score, dim)
        assert 1 <= d.score <= 5


def test_judge_review_user_message_includes_persona_context():
    llm = _llm_returning(_payload())
    judge_review(MANUSCRIPT, _review(), _profile(), llm=llm, model="m")
    _, kwargs = llm.chat.call_args
    user_msg = next(m["content"] for m in kwargs["messages"] if m["role"] == "user")
    assert MANUSCRIPT in user_msg
    assert "critical" in user_msg
    assert "methods" in user_msg


def test_judge_review_rejects_out_of_range():
    llm = _llm_returning(_payload(specificity=7))
    with pytest.raises(ValueError, match="specificity"):
        judge_review(MANUSCRIPT, _review(), _profile(), llm=llm, model="m")


def test_main_reads_run_json_and_writes_judge_json(tmp_path, monkeypatch):
    from scripts import judge as judge_mod

    run = RunOutput(
        classification=ClassificationResult(
            keywords=Keywords(extracted_from_paper=[], synthesised=[]),
            classes=[CCSClass(path="A", weight="High", rationale="r")],
        ),
        profiles=ProfileBoard(reviewers=[_profile("r1"), _profile("r2")]),
        board=BoardReport(reviews=[_review("r1"), _review("r2")], skipped=[]),
    )

    eval_dir = tmp_path / "run-20260429T000000Z"
    eval_dir.mkdir()
    (eval_dir / "run.json").write_text(json.dumps(run.model_dump()))
    manuscript = tmp_path / "m.md"
    manuscript.write_text(MANUSCRIPT)

    monkeypatch.setattr(judge_mod, "from_env", lambda default_model: _llm_returning(_payload()))

    rc = judge_mod.main([
        "--manuscript", str(manuscript),
        "--run-dir", str(eval_dir),
    ])
    assert rc == 0
    out = json.loads((eval_dir / "judge.json").read_text())
    assert {e["reviewer_id"] for e in out["per_reviewer"]} == {"r1", "r2"}
    assert out["board_mean"] == pytest.approx(4.0)
