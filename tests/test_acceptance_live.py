import os
from dataclasses import replace
from pathlib import Path

import pytest
from dotenv import load_dotenv

from paperfb.config import load_config
from paperfb.pipeline import run as pipeline_run
from paperfb.schemas import RunOutput


pytestmark = pytest.mark.slow

load_dotenv()


@pytest.fixture
def cfg(tmp_path):
    c = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    return replace(c, paths=replace(
        c.paths,
        output=str(tmp_path / "report.md"),
        logs_dir=str(tmp_path / "logs"),
    ))


@pytest.fixture
def manuscript():
    return Path("tests/fixtures/tiny_manuscript.md").read_text()


def test_live_pipeline_produces_report_and_run_json(cfg, manuscript, tmp_path):
    assert os.environ.get("BASE_URL"), "BASE_URL env var required for live test"

    run = pipeline_run(manuscript=manuscript, cfg=cfg)
    assert isinstance(run, RunOutput)

    # (a) markdown report
    report = Path(cfg.paths.output)
    assert report.exists()
    text = report.read_text()
    assert text.count("## Review by ") == cfg.reviewers.count

    # (b) ACM classes
    assert "## ACM classification" in text
    assert len(run.classification.classes) >= 1

    # (c) reviewer diversity invariants — read from profiles, not from slim Review
    successful_ids = {r.reviewer_id for r in run.board.reviews}
    successful_profiles = [p for p in run.profiles.reviewers if p.id in successful_ids]
    pairs = {(p.stance, p.primary_focus) for p in successful_profiles}
    assert len(pairs) == len(successful_profiles), "stance/focus pair duplication"
    names = {p.name for p in successful_profiles}
    assert len(names) == len(successful_profiles), "Finnish-name duplication"

    # (d) RunOutput artefact round-trips
    eval_dirs = sorted(Path("evaluations").glob("run-*"))
    assert eval_dirs, "no evaluations/run-* directory written"
    run_json = eval_dirs[-1] / "run.json"
    assert run_json.exists()
    parsed = RunOutput.model_validate_json(run_json.read_text())
    assert parsed == run

    # (e) non-leakage: manuscript body must not appear in cleartext logs
    sentinel = "wall-clock time recorded on a"
    logs_dir = Path(cfg.paths.logs_dir)
    if logs_dir.exists():
        for log in logs_dir.rglob("*"):
            if log.is_file():
                assert sentinel not in log.read_text(encoding="utf-8", errors="replace"), \
                    f"manuscript leaked to {log}"
