"""Integration test for the AG2-wired pipeline. AG2 is patched out so we don't
hit the network; the test asserts wiring (handoff sequence, RunOutput
assembly) rather than LLM behavior.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from paperfb.config import load_config
from paperfb.schemas import (
    BoardReport, CCSClass, ClassificationResult, Keywords,
    ProfileBoard, Review, ReviewerProfile, RunOutput, SkippedReviewer,
)


@pytest.fixture
def cfg(tmp_path):
    from dataclasses import replace
    c = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    return replace(c, paths=replace(
        c.paths,
        output=str(tmp_path / "report.md"),
        logs_dir=str(tmp_path / "logs"),
    ))


def _fake_chat_result():
    """Stub of AG2's chat_result. Carries context_variables populated by the
    handoff functions."""
    classification = ClassificationResult(
        keywords=Keywords(extracted_from_paper=["x"], synthesised=[]),
        classes=[CCSClass(path="A → B", weight="High", rationale="r")],
    )
    profiles = ProfileBoard(reviewers=[
        ReviewerProfile(
            id=f"r{i+1}", name=n, specialty="A → B", stance="critical",
            primary_focus="methods", secondary_focus=None,
            persona_prompt="...", profile_summary="...",
        )
        for i, n in enumerate(["Aino", "Eero", "Liisa"])
    ])
    board = BoardReport(
        reviews=[Review(reviewer_id=f"r{i+1}", strong_aspects="s",
                        weak_aspects="w", recommended_changes="c")
                 for i in range(3)],
        skipped=[],
    )
    res = MagicMock()
    res.context_variables = {
        "classification": classification.model_dump(),
        "profiles": profiles.model_dump(),
        "board": board.model_dump(),
        "expected_reviewer_ids": ["r1", "r2", "r3"],
    }
    return res, board, classification, profiles


def test_pipeline_assembles_runoutput_from_context(cfg, monkeypatch):
    """pipeline.run() must read context_variables (populated by handoffs in
    a real run) and build a RunOutput from them."""
    from paperfb import pipeline as pl

    fake_result, board, classification, profiles = _fake_chat_result()
    monkeypatch.setattr(pl, "_run_chat", lambda **kw: fake_result)

    run = pl.run(manuscript="hello world", cfg=cfg)
    assert isinstance(run, RunOutput)
    assert run.classification == classification
    assert run.profiles == profiles
    assert run.board == board

    # On-disk artefact: RunOutput JSON written under evaluations/run-<ts>/
    eval_dirs = list(Path("evaluations").glob("run-*"))
    matching = [d for d in eval_dirs if (d / "run.json").exists()]
    assert matching, "expected evaluations/run-<ts>/run.json to be written"
    # Verify round-trip
    written = RunOutput.model_validate_json((matching[-1] / "run.json").read_text())
    assert written == run

    # Rendered markdown report
    report_path = Path(cfg.paths.output)
    assert report_path.exists()
    assert "# Manuscript feedback report" in report_path.read_text()


def test_pipeline_propagates_skipped_reviewers(cfg, monkeypatch):
    from paperfb import pipeline as pl

    fake_result, _, _, _ = _fake_chat_result()
    board_with_skip = BoardReport(
        reviews=[Review(reviewer_id="r1", strong_aspects="s", weak_aspects="w", recommended_changes="c")],
        skipped=[SkippedReviewer(id="r2", reason="missing"),
                 SkippedReviewer(id="r3", reason="missing")],
    )
    fake_result.context_variables["board"] = board_with_skip.model_dump()
    monkeypatch.setattr(pl, "_run_chat", lambda **kw: fake_result)

    run = pl.run(manuscript="hello", cfg=cfg)
    assert {s.id for s in run.board.skipped} == {"r2", "r3"}
    assert len(run.board.reviews) == 1


def test_pipeline_writes_logs_jsonl(cfg, monkeypatch, tmp_path):
    """Verifies _run_chat opens the log file. Real content depends on AG2 hook
    path; we just check the file is created with at least one event."""
    from paperfb import pipeline as pl
    from paperfb.logging_hook import JsonlLogger

    fake_result, *_ = _fake_chat_result()
    captured: list[Path] = []

    def fake_run_chat(**kw):
        log_path = Path(cfg.paths.logs_dir) / f"{kw['ts']}.jsonl"
        with JsonlLogger(log_path) as lg:
            lg.log_event({"agent": "test", "role": "assistant", "content": "ok"})
        captured.append(log_path)
        return fake_result

    monkeypatch.setattr(pl, "_run_chat", fake_run_chat)

    pl.run(manuscript="hello", cfg=cfg)
    assert captured and captured[0].exists()
    assert captured[0].read_text().strip() != ""
