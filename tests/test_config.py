from pathlib import Path
import pytest
from paperfb.config import load_config, Config


def test_load_defaults():
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    assert isinstance(cfg, Config)
    assert cfg.reviewers.count == 3
    assert cfg.reviewers.core_focuses == ["methods", "results", "novelty"]
    assert cfg.models.default == "anthropic/claude-3.5-haiku"
    assert "neutral" in cfg.axes.stances
    assert "methods" in cfg.axes.focuses


def test_reviewer_count_minimum(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("""
transport: openai_chat_completions
base_url_env: BASE_URL
models: {default: x, classification: x, profile_creation: x, reviewer: x, judge: x}
reviewers: {count: 2, core_focuses: [m], secondary_focus_per_reviewer: true, diversity: strict, seed: null}
classification: {max_classes: 5}
paths: {acm_ccs: a, reviews_dir: r, output: o, logs_dir: l}
""")
    with pytest.raises(ValueError, match="count must be >= 3"):
        load_config(bad, Path("config/axes.yaml"))


def test_core_focuses_must_be_subset_of_focuses():
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    for f in cfg.reviewers.core_focuses:
        assert f in cfg.axes.focuses
