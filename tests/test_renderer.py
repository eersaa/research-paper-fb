from paperfb.renderer import render_report
from paperfb.schemas import (
    BoardReport, CCSClass, ClassificationResult, Keywords,
    ProfileBoard, Review, ReviewerProfile, RunOutput, SkippedReviewer,
)


def _profile(rid="r1", name="Aino", specialty="Computing methodologies → ML → NN"):
    return ReviewerProfile(
        id=rid, name=name, specialty=specialty,
        stance="critical", primary_focus="methods", secondary_focus="results",
        persona_prompt="...",
        profile_summary="critical methods specialist",
    )


def _review(rid="r1") -> Review:
    return Review(
        reviewer_id=rid,
        strong_aspects="Clear framing of the problem and reproducible setup.",
        weak_aspects="Sample size of N=5 cannot distinguish gains from noise.",
        recommended_changes="Run with >=20 seeds, report 95% CIs, add a paired statistical test.",
    )


_SENTINEL = object()


def _run(*, classes=None, reviews=_SENTINEL, profiles=None, skipped=None) -> RunOutput:
    return RunOutput(
        classification=ClassificationResult(
            keywords=Keywords(extracted_from_paper=[], synthesised=[]),
            classes=classes or [CCSClass(path="Computing methodologies → ML → NN",
                                          weight="High", rationale="r1")],
        ),
        profiles=ProfileBoard(reviewers=profiles or [_profile()]),
        board=BoardReport(
            reviews=[_review()] if reviews is _SENTINEL else reviews,
            skipped=skipped or [],
        ),
    )


def test_renders_full_report():
    md = render_report(_run())
    assert "# Manuscript feedback report" in md
    assert "## ACM classification" in md
    assert "Computing methodologies → ML → NN" in md
    assert "High" in md
    assert "## Review by Aino — Computing methodologies → ML → NN" in md
    assert "critical" in md
    assert "methods" in md
    assert "### Strong aspects" in md
    assert "Clear framing" in md
    assert "### Weak aspects" in md
    assert "Sample size of N=5" in md
    assert "### Recommended changes" in md
    assert ">=20 seeds" in md


def test_no_ratings_table_in_report():
    md = render_report(_run())
    assert "| Score" not in md
    assert "/5" not in md


def test_notes_skipped_reviewers():
    md = render_report(_run(reviews=[],
                            skipped=[SkippedReviewer(id="r2", reason="tool failure")]))
    assert "Skipped" in md
    assert "r2" in md
    assert "tool failure" in md


def test_no_reviews_graceful():
    md = render_report(_run(classes=[CCSClass(path="A", weight="Low", rationale="r")],
                            reviews=[], profiles=[_profile()]))
    assert "# Manuscript feedback report" in md
    assert "No reviews produced" in md


def test_review_joined_to_profile_by_reviewer_id():
    profiles = [_profile(rid="r1", name="Aino"), _profile(rid="r2", name="Eero")]
    reviews = [_review(rid="r2"), _review(rid="r1")]  # out of order on purpose
    md = render_report(_run(profiles=profiles, reviews=reviews))
    # Both names appear, joined by reviewer_id, regardless of review order
    assert "Aino" in md and "Eero" in md
