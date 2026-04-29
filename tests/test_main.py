from pathlib import Path
from unittest.mock import MagicMock

from paperfb.schemas import (
    BoardReport, CCSClass, ClassificationResult, Keywords,
    ProfileBoard, Review, ReviewerProfile, RunOutput,
)


def _run_output() -> RunOutput:
    return RunOutput(
        classification=ClassificationResult(
            keywords=Keywords(extracted_from_paper=[], synthesised=[]),
            classes=[CCSClass(path="A", weight="High", rationale="r")],
        ),
        profiles=ProfileBoard(reviewers=[ReviewerProfile(
            id="r1", name="Aino", specialty="A", stance="critical",
            primary_focus="methods", secondary_focus=None,
            persona_prompt="...", profile_summary="...",
        )]),
        board=BoardReport(
            reviews=[Review(reviewer_id="r1", strong_aspects="s",
                            weak_aspects="w", recommended_changes="c")],
            skipped=[],
        ),
    )


def test_main_calls_pipeline_run_and_returns_zero(tmp_path, monkeypatch):
    manuscript = tmp_path / "m.md"
    manuscript.write_text("hello")

    from paperfb import main as main_mod

    fake_run = MagicMock(return_value=_run_output())
    monkeypatch.setattr(main_mod, "pipeline_run", fake_run)

    rc = main_mod.main([str(manuscript), "--output", str(tmp_path / "report.md")])
    assert rc == 0
    assert fake_run.called
    kwargs = fake_run.call_args.kwargs
    assert kwargs["manuscript"] == "hello"
    assert kwargs["cfg"].paths.output == str(tmp_path / "report.md")


def test_main_returns_nonzero_when_manuscript_missing(tmp_path):
    from paperfb import main as main_mod
    rc = main_mod.main([str(tmp_path / "missing.md")])
    assert rc != 0
