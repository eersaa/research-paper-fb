import json
from pathlib import Path
import pytest
from paperfb.agents.reviewer.tools import write_review, TOOL_SCHEMA, ReviewValidationError


def _sample_review(rid="r1"):
    return {
        "reviewer_id": rid,
        "reviewer_name": "Aino",
        "specialty": "Computing methodologies → Machine learning",
        "stance": "critical",
        "primary_focus": "methods",
        "secondary_focus": "results",
        "profile_summary": "critical methods reviewer",
        "strong_aspects": "Clear framing of the problem and reproducible setup.",
        "weak_aspects": "N=5 seeds is too few to distinguish the gain from noise.",
        "recommended_changes": "Increase seeds to >=20 and add a paired statistical test.",
    }


def test_writes_json_file(tmp_path):
    path = write_review(_sample_review("r1"), reviews_dir=tmp_path)
    assert path == tmp_path / "r1.json"
    data = json.loads(path.read_text())
    assert data["reviewer_id"] == "r1"
    assert data["reviewer_name"] == "Aino"


def test_missing_required_field_raises(tmp_path):
    bad = _sample_review()
    del bad["recommended_changes"]
    with pytest.raises(ReviewValidationError, match="recommended_changes"):
        write_review(bad, reviews_dir=tmp_path)


def test_two_reviewers_no_overlap(tmp_path):
    write_review(_sample_review("r1"), reviews_dir=tmp_path)
    write_review(_sample_review("r2"), reviews_dir=tmp_path)
    assert (tmp_path / "r1.json").exists()
    assert (tmp_path / "r2.json").exists()


def test_tool_schema_lists_required_fields():
    required = TOOL_SCHEMA["function"]["parameters"]["required"]
    for f in ["reviewer_id", "reviewer_name", "stance", "primary_focus",
              "strong_aspects", "weak_aspects", "recommended_changes"]:
        assert f in required


def test_tool_schema_does_not_include_ratings():
    """Per 2026-04-27 review-template merge, ratings are no longer in the schema."""
    props = TOOL_SCHEMA["function"]["parameters"]["properties"]
    assert "ratings" not in props
    assert "strengths" not in props
    assert "section_comments" not in props
