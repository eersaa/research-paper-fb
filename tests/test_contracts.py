from paperfb.contracts import (
    ReviewerTuple,
    ReviewerProfile,
    ClassificationResult,
    REVIEW_REQUIRED_FIELDS,
)


def test_reviewer_tuple_fields():
    t = ReviewerTuple(id="r1", specialty={"path": "X"}, stance="neutral",
                     primary_focus="methods", secondary_focus="results")
    assert t.id == "r1"
    assert t.specialty == {"path": "X"}


def test_reviewer_profile_fields():
    p = ReviewerProfile(id="r1", specialty={"path": "X"}, stance="neutral",
                       primary_focus="methods", secondary_focus=None,
                       persona_prompt="You are ...")
    assert p.persona_prompt == "You are ..."
    assert p.secondary_focus is None


def test_classification_result_holds_list():
    r = ClassificationResult(classes=[{"path": "X", "weight": "High", "rationale": "x"}])
    assert r.classes[0]["weight"] == "High"


def test_review_required_fields_declared():
    for f in ["reviewer_id", "stance", "focus", "strengths", "weaknesses",
              "suggestions", "section_comments", "overall_assessment"]:
        assert f in REVIEW_REQUIRED_FIELDS
