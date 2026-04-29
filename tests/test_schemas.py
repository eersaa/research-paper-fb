import pytest
from pydantic import ValidationError

from paperfb.schemas import (
    BoardReport,
    CCSClass,
    CCSMatch,
    ClassificationResult,
    Keywords,
    ProfileBoard,
    Review,
    ReviewerProfile,
    ReviewerTuple,
    RunOutput,
    SkippedReviewer,
)


def _classification() -> ClassificationResult:
    return ClassificationResult(
        keywords=Keywords(extracted_from_paper=["transformers"], synthesised=["attention"]),
        classes=[CCSClass(path="Computing methodologies → ML", weight="High", rationale="r")],
    )


def _profile(rid="r1") -> ReviewerProfile:
    return ReviewerProfile(
        id=rid,
        name="Aino",
        specialty="Computing methodologies → ML",
        stance="critical",
        primary_focus="methods",
        secondary_focus=None,
        persona_prompt="You are Aino...",
        profile_summary="critical methods specialist",
    )


def test_classification_round_trip():
    obj = _classification()
    parsed = ClassificationResult.model_validate_json(obj.model_dump_json())
    assert parsed == obj


def test_review_slim_shape_no_metadata_fields():
    r = Review(reviewer_id="r1", strong_aspects="a", weak_aspects="b", recommended_changes="c")
    payload = r.model_dump()
    assert set(payload) == {"reviewer_id", "strong_aspects", "weak_aspects", "recommended_changes"}


def test_extra_fields_forbidden_on_review():
    with pytest.raises(ValidationError):
        Review.model_validate({
            "reviewer_id": "r1",
            "strong_aspects": "", "weak_aspects": "", "recommended_changes": "",
            "stance": "critical",  # extra field — must be rejected per spec §5.1
        })


def test_ccs_class_weight_enum():
    with pytest.raises(ValidationError):
        CCSClass(path="x", weight="Critical", rationale="r")


def test_profile_board_validates_id_field_present():
    pb = ProfileBoard(reviewers=[_profile()])
    assert pb.reviewers[0].id == "r1"


def test_run_output_round_trip():
    run = RunOutput(
        classification=_classification(),
        profiles=ProfileBoard(reviewers=[_profile()]),
        board=BoardReport(
            reviews=[Review(reviewer_id="r1", strong_aspects="s", weak_aspects="w", recommended_changes="c")],
            skipped=[SkippedReviewer(id="r2", reason="boom")],
        ),
    )
    parsed = RunOutput.model_validate_json(run.model_dump_json())
    assert parsed == run


def test_ccs_match_shape():
    m = CCSMatch(path="A → B", description="d")
    assert m.path == "A → B"


def test_reviewer_tuple_id_required():
    with pytest.raises(ValidationError):
        ReviewerTuple(name="x", specialty="y", stance="z", primary_focus="p", secondary_focus=None)
