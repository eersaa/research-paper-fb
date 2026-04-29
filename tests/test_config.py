from pathlib import Path
import pytest
from paperfb.config import load_config, Config, AxisItem


def test_load_defaults():
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    assert isinstance(cfg, Config)
    assert cfg.reviewers.count == 3
    assert cfg.reviewers.core_focuses == ["methods", "results", "novelty"]
    assert cfg.models.default == "openai/gpt-4.1-mini"
    stance_names = [s.name for s in cfg.axes.stances]
    focus_names = [f.name for f in cfg.axes.focuses]
    assert "neutral" in stance_names
    assert "methods" in focus_names


def test_axis_items_carry_descriptions():
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    methods = next(f for f in cfg.axes.focuses if f.name == "methods")
    assert isinstance(methods, AxisItem)
    assert methods.description  # non-empty
    critical = next(s for s in cfg.axes.stances if s.name == "critical")
    assert critical.description


def test_reviewer_count_minimum(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("""
transport: openai_chat_completions
base_url_env: BASE_URL
models: {default: x, classification: x, profile_creation: x, reviewer: x, judge: x}
reviewers: {count: 2, core_focuses: [m], secondary_focus_per_reviewer: true, diversity: strict, seed: null}
classification: {max_classes: 5}
paths: {acm_ccs: a, finnish_names: f, output: o, logs_dir: l}
""")
    with pytest.raises(ValueError, match="count must be >= 3"):
        load_config(bad, Path("config/axes.yaml"))


def test_core_focuses_must_be_subset_of_focuses():
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    focus_names = {f.name for f in cfg.axes.focuses}
    for f in cfg.reviewers.core_focuses:
        assert f in focus_names


def test_axis_entry_must_have_name_and_description(tmp_path):
    bad_axes = tmp_path / "axes.yaml"
    bad_axes.write_text("stances:\n  - neutral\nfocuses:\n  - methods\n")
    default = tmp_path / "default.yaml"
    default.write_text("""
transport: openai_chat_completions
base_url_env: BASE_URL
models: {default: x, classification: x, profile_creation: x, reviewer: x, judge: x}
reviewers: {count: 3, core_focuses: [methods], secondary_focus_per_reviewer: true, diversity: strict, seed: null}
classification: {max_classes: 5}
paths: {acm_ccs: a, finnish_names: f, output: o, logs_dir: l}
""")
    with pytest.raises(ValueError, match="must be \\{name, description\\}"):
        load_config(default, bad_axes)


def test_ag2_section_parsed():
    from paperfb.config import load_config
    from pathlib import Path
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    assert cfg.ag2.cache_seed is None
    assert cfg.ag2.retry_on_validation_error == 1


def test_models_pin_to_proxy_compatible_families():
    """Per spec §5.1, every structured-output agent must run on OpenAI/Google."""
    from paperfb.config import load_config
    from pathlib import Path
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    for field in ("default", "classification", "profile_creation", "reviewer"):
        m = getattr(cfg.models, field)
        assert m.startswith("openai/") or m.startswith("google/"), \
            f"models.{field}={m!r} not in OpenAI/Google families"
    assert cfg.models.judge.startswith("google/"), "judge stays on Google for bias mitigation"
