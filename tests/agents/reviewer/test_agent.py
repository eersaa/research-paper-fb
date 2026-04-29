import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from paperfb.agents.reviewer_legacy import run_reviewer
from paperfb.contracts import ReviewerProfile


def _tool_call(name, args):
    tc = MagicMock()
    tc.id = "call_1"
    tc.type = "function"
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _res(content=None, tool_calls=None, finish_reason="stop"):
    r = MagicMock()
    r.content = content
    r.tool_calls = tool_calls
    r.finish_reason = finish_reason
    return r


def _full_review(rid="r1"):
    return {
        "reviewer_id": rid,
        "reviewer_name": "Aino",
        "specialty": "ML",
        "stance": "critical",
        "primary_focus": "methods",
        "secondary_focus": "results",
        "profile_summary": "critical methods reviewer",
        "strong_aspects": "Reproducible setup, hyperparameters reported.",
        "weak_aspects": "N=5 too few seeds.",
        "recommended_changes": "Run with >=20 seeds and add 95% CI.",
    }


def test_reviewer_calls_write_review_and_returns_path(tmp_path):
    profile = ReviewerProfile(id="r1", specialty={"path": "ML"}, stance="critical",
                              primary_focus="methods", secondary_focus="results",
                              persona_prompt="You are ...")
    llm = MagicMock()
    llm.chat.side_effect = [
        _res(tool_calls=[_tool_call("write_review", _full_review("r1"))], finish_reason="tool_calls"),
        _res(content="done"),
    ]

    path = run_reviewer(profile, manuscript="abc", llm=llm, model="stub", reviews_dir=tmp_path)
    assert path == tmp_path / "r1.json"
    assert path.exists()


def test_reviewer_invalid_review_retries_then_skips(tmp_path):
    profile = ReviewerProfile(id="r1", specialty={"path": "ML"}, stance="critical",
                              primary_focus="methods", secondary_focus=None,
                              persona_prompt="...")
    bad = {"reviewer_id": "r1"}  # missing fields
    llm = MagicMock()
    llm.chat.side_effect = [
        _res(tool_calls=[_tool_call("write_review", bad)], finish_reason="tool_calls"),
        _res(tool_calls=[_tool_call("write_review", bad)], finish_reason="tool_calls"),
    ]
    with pytest.raises(RuntimeError, match="failed to produce valid review"):
        run_reviewer(profile, "abc", llm, "stub", tmp_path)
