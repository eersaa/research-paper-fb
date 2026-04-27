import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from paperfb.orchestrator import run_pipeline, PipelineResult
from paperfb.config import load_config


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    # minimal tmp-path-scoped config
    c = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    # override paths via monkey-patch of attributes (frozen dataclass workaround: replace)
    from dataclasses import replace
    paths = replace(c.paths, reviews_dir=str(tmp_path / "reviews"),
                    output=str(tmp_path / "report.md"),
                    logs_dir=str(tmp_path / "logs"),
                    acm_ccs="data/acm_ccs.json")
    return replace(c, paths=paths)


def test_full_pipeline_happy_path(cfg, tmp_path):
    classify = MagicMock(return_value=MagicMock(classes=[
        {"path": "Computing methodologies → Machine learning → Machine learning approaches → Neural networks",
         "weight": "High", "rationale": "CNNs"}
    ]))
    sampler_out = [
        MagicMock(id=f"r{i+1}", specialty={"path": "ML"}, stance="critical",
                  primary_focus="methods", secondary_focus="results")
        for i in range(3)
    ]
    # need concrete ReviewerTuple/Profile types for real code path:
    from paperfb.contracts import ReviewerTuple, ReviewerProfile
    tuples = [
        ReviewerTuple(id=f"r{i+1}", specialty={"path": "ML", "weight": "High"},
                      stance="critical", primary_focus=["methods", "results", "novelty"][i],
                      secondary_focus="clarity")
        for i in range(3)
    ]
    profiles = [ReviewerProfile(id=t.id, specialty=t.specialty, stance=t.stance,
                                 primary_focus=t.primary_focus, secondary_focus=t.secondary_focus,
                                 persona_prompt="...") for t in tuples]

    def fake_reviewer(profile, manuscript, llm, model, reviews_dir):
        p = Path(reviews_dir) / f"{profile.id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "reviewer_id": profile.id,
            "reviewer_name": "Aino",
            "specialty": profile.specialty.get("path", ""),
            "stance": profile.stance,
            "primary_focus": profile.primary_focus,
            "secondary_focus": profile.secondary_focus,
            "profile_summary": "",
            "strong_aspects": "good framing",
            "weak_aspects": "small N",
            "recommended_changes": "more seeds",
        }))
        return p

    llm = MagicMock()
    result = asyncio.run(run_pipeline(
        manuscript="hello",
        cfg=cfg,
        llm=llm,
        classify_fn=lambda manuscript, llm, model, ccs_path, max_classes:
            MagicMock(classes=[{"path": "ML", "weight": "High", "rationale": "r"}]),
        sample_fn=lambda **kwargs: tuples,
        profile_fn=lambda tuples, axes, llm, model: profiles,
        reviewer_fn=fake_reviewer,
    ))

    assert isinstance(result, PipelineResult)
    assert len(result.reviews) == 3
    assert result.skipped == []
    assert Path(cfg.paths.output).exists()
    assert "# Manuscript feedback report" in Path(cfg.paths.output).read_text()


def test_reviewer_failure_is_skipped(cfg, tmp_path):
    from paperfb.contracts import ReviewerTuple, ReviewerProfile
    tuples = [ReviewerTuple(id=f"r{i+1}", specialty={"path": "ML"}, stance="critical",
                             primary_focus=["methods", "results", "novelty"][i],
                             secondary_focus=None) for i in range(3)]
    profiles = [ReviewerProfile(id=t.id, specialty=t.specialty, stance=t.stance,
                                 primary_focus=t.primary_focus, secondary_focus=None,
                                 persona_prompt="...") for t in tuples]

    def flaky_reviewer(profile, manuscript, llm, model, reviews_dir):
        if profile.id == "r2":
            raise RuntimeError("simulated failure")
        p = Path(reviews_dir) / f"{profile.id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "reviewer_id": profile.id,
            "reviewer_name": "Eero",
            "specialty": profile.specialty.get("path", ""),
            "stance": "critical",
            "primary_focus": profile.primary_focus,
            "secondary_focus": profile.secondary_focus,
            "profile_summary": "",
            "strong_aspects": "",
            "weak_aspects": "",
            "recommended_changes": "",
        }))
        return p

    result = asyncio.run(run_pipeline(
        manuscript="hello", cfg=cfg, llm=MagicMock(),
        classify_fn=lambda **kw: MagicMock(classes=[{"path": "ML", "weight": "High", "rationale": "r"}]),
        sample_fn=lambda **kw: tuples,
        profile_fn=lambda tuples, axes, llm, model: profiles,
        reviewer_fn=flaky_reviewer,
    ))
    assert len(result.reviews) == 2
    assert len(result.skipped) == 1
    assert result.skipped[0]["id"] == "r2"
