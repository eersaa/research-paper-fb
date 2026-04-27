import asyncio
import json
import os
from dataclasses import replace
from pathlib import Path
import pytest
from dotenv import load_dotenv

from paperfb.config import load_config
from paperfb.llm_client import from_env
from paperfb.orchestrator import run_pipeline


pytestmark = pytest.mark.slow

load_dotenv()


@pytest.fixture
def cfg_tmp(tmp_path):
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    return replace(cfg, paths=replace(
        cfg.paths,
        reviews_dir=str(tmp_path / "reviews"),
        output=str(tmp_path / "report.md"),
        logs_dir=str(tmp_path / "logs"),
    ))


@pytest.fixture
def manuscript():
    return Path("tests/fixtures/tiny_manuscript.md").read_text()


def test_live_pipeline_produces_report(cfg_tmp, manuscript, tmp_path):
    assert os.environ.get("BASE_URL"), "BASE_URL env var required for live test"
    llm = from_env(default_model=cfg_tmp.models.default)

    result = asyncio.run(run_pipeline(manuscript=manuscript, cfg=cfg_tmp, llm=llm))

    # (a) report exists
    report = Path(cfg_tmp.paths.output)
    assert report.exists(), "final_report.md missing"
    text = report.read_text()

    # (b) per-reviewer sections match N
    assert text.count("## Review by ") == cfg_tmp.reviewers.count

    # (c) ACM classes present
    assert "## ACM classification" in text
    assert len(result.classes) >= 1

    # (d) reviewer stances distinct per (stance, primary_focus)
    pairs = {(r["stance"], r["primary_focus"]) for r in result.reviews}
    assert len(pairs) == len(result.reviews), "stance/focus pair duplication"

    # (e) no manuscript text leaks to stdout/logs
    #     manuscript has a unique sentinel phrase:
    sentinel = "wall-clock time recorded on a"
    logs_dir = Path(cfg_tmp.paths.logs_dir)
    if logs_dir.exists():
        for log in logs_dir.rglob("*"):
            if log.is_file():
                assert sentinel not in log.read_text(encoding="utf-8", errors="replace"), \
                    f"manuscript leaked to {log}"
