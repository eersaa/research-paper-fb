import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from paperfb.main import main


def test_cli_reads_manuscript_and_writes_report(tmp_path, monkeypatch):
    manuscript = tmp_path / "ms.md"
    manuscript.write_text("# Title\n\nAbstract.\n")
    monkeypatch.setenv("BASE_URL", "http://proxy.invalid")

    fake_result = MagicMock()
    fake_result.report_path = tmp_path / "report.md"
    fake_result.skipped = []
    fake_result.reviews = [{"reviewer_id": "r1"}, {"reviewer_id": "r2"}, {"reviewer_id": "r3"}]

    fake_llm = MagicMock()
    fake_llm.usage_summary.return_value = {"total_tokens": 0, "total_cost_usd": 0.0}
    with patch("paperfb.main.asyncio.run", return_value=fake_result), \
         patch("paperfb.main.from_env", return_value=fake_llm):
        rc = main([
            str(manuscript),
            "--output", str(tmp_path / "report.md"),
            "--reviews-dir", str(tmp_path / "reviews"),
        ])
    assert rc == 0


def test_cli_missing_manuscript_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_URL", "http://proxy.invalid")
    rc = main([str(tmp_path / "nope.md")])
    assert rc != 0
