import json
from pathlib import Path
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
    with pytest.raises(ValueError, match="specificity: score must be an integer"):
        judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")


def test_bool_score_raises():
    payload = _payload()
    payload["specificity"]["score"] = True  # bool is a subclass of int — must still be rejected
    llm = _llm_returning(payload)
    with pytest.raises(ValueError, match="specificity: score must be an integer"):
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


from dataclasses import replace as _replace
from paperfb.config import load_config


def _stub_llm_factory(payload_dict: dict):
    """Returns a callable matching from_env(default_model=...) that yields a stub LLM."""
    def _factory(default_model: str):
        return _llm_returning(payload_dict)
    return _factory


def _write_review(path: Path, reviewer_id: str) -> None:
    path.write_text(json.dumps({
        "reviewer_id": reviewer_id,
        "reviewer_name": "Aino",
        "specialty": "ML",
        "stance": "critical",
        "primary_focus": "methods",
        "secondary_focus": None,
        "profile_summary": "",
        "strong_aspects": "x",
        "weak_aspects": "y",
        "recommended_changes": "z",
    }))


def _write_manuscript(tmp_path: Path) -> Path:
    p = tmp_path / "manuscript.md"
    p.write_text("Tiny manuscript body.")
    return p


def test_main_writes_per_reviewer_and_board_mean(tmp_path, monkeypatch):
    from scripts import judge as judge_mod

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    _write_review(reviews_dir / "r1.json", "r1")
    _write_review(reviews_dir / "r2.json", "r2")
    manuscript = _write_manuscript(tmp_path)

    monkeypatch.setattr(judge_mod, "from_env", _stub_llm_factory(_payload(
        specificity=5, actionability=5, persona_fidelity=5, coverage=5, non_redundancy=5)))

    out_path = tmp_path / "eval.json"
    rc = judge_mod.main([
        "--manuscript", str(manuscript),
        "--reviews-dir", str(reviews_dir),
        "--output", str(out_path),
    ])
    assert rc == 0

    data = json.loads(out_path.read_text())
    assert len(data["per_reviewer"]) == 2
    for entry in data["per_reviewer"]:
        assert entry["mean"] == pytest.approx(5.0)
        for dim in DIMENSIONS:
            assert entry[dim]["score"] == 5
            assert entry[dim]["justification"] != ""
    assert data["board_mean"] == pytest.approx(5.0)
    assert data["judge_model"]  # non-empty


def test_main_auto_generates_run_id_when_output_omitted(tmp_path, monkeypatch):
    from scripts import judge as judge_mod

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    _write_review(reviews_dir / "r1.json", "r1")
    manuscript = _write_manuscript(tmp_path)

    # Resolve config paths against the repo root before we chdir, so main()
    # can still find them after the cwd flip.
    cfg_default = Path("config/default.yaml").resolve()
    cfg_axes = Path("config/axes.yaml").resolve()

    eval_dir = tmp_path / "evaluations"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(judge_mod, "from_env", _stub_llm_factory(_payload()))

    rc = judge_mod.main([
        "--manuscript", str(manuscript),
        "--reviews-dir", str(reviews_dir),
        "--config", str(cfg_default),
        "--axes", str(cfg_axes),
    ])
    assert rc == 0

    written = list(eval_dir.glob("run-*.json"))
    assert len(written) == 1
    assert written[0].name.startswith("run-") and written[0].name.endswith(".json")


def test_main_uses_cfg_models_judge_when_model_flag_omitted(tmp_path, monkeypatch):
    from scripts import judge as judge_mod

    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    expected_model = cfg.models.judge

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    _write_review(reviews_dir / "r1.json", "r1")
    manuscript = _write_manuscript(tmp_path)

    seen_models: list[str] = []

    class _RecordingLLM:
        def chat(self, messages, model=None, **kw):
            seen_models.append(model)
            res = MagicMock()
            res.content = json.dumps(_payload())
            res.tool_calls = None
            res.finish_reason = "stop"
            return res

    monkeypatch.setattr(judge_mod, "from_env", lambda default_model: _RecordingLLM())

    rc = judge_mod.main([
        "--manuscript", str(manuscript),
        "--reviews-dir", str(reviews_dir),
        "--output", str(tmp_path / "eval.json"),
    ])
    assert rc == 0
    assert seen_models == [expected_model]
