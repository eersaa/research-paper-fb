from paperfb.renderer import render_report


def _review(rid="r1", name="Aino"):
    return {
        "reviewer_id": rid,
        "reviewer_name": name,
        "specialty": "Computing methodologies → ML → NN",
        "stance": "critical",
        "primary_focus": "methods",
        "secondary_focus": "results",
        "profile_summary": "critical methods specialist",
        "strong_aspects": "Clear framing of the problem and reproducible setup.",
        "weak_aspects": "Sample size of N=5 cannot distinguish gains from noise.",
        "recommended_changes": "Run with >=20 seeds, report 95% CIs, add a paired statistical test.",
    }


def test_renders_full_report():
    classes = [
        {"path": "Computing methodologies → ML → NN", "weight": "High", "rationale": "r1"},
    ]
    reviews = [_review()]
    md = render_report(classes=classes, reviews=reviews, skipped_reviewers=[])

    assert "# Manuscript feedback report" in md
    assert "## ACM classification" in md
    assert "Computing methodologies → ML → NN" in md
    assert "High" in md
    # Per-reviewer header includes Finnish name and specialty
    assert "## Review by Aino" in md
    assert "Computing methodologies → ML → NN" in md
    # Profile blurb
    assert "critical" in md
    assert "methods" in md
    # Three labeled prose sections
    assert "### Strong aspects" in md
    assert "Clear framing" in md
    assert "### Weak aspects" in md
    assert "Sample size of N=5" in md
    assert "### Recommended changes" in md
    assert ">=20 seeds" in md


def test_no_ratings_table_in_report():
    """Per 2026-04-27 review-template merge, ratings are not part of the schema or output."""
    md = render_report(classes=[], reviews=[_review()], skipped_reviewers=[])
    # No table header, no /5 score formatting
    assert "| Score" not in md
    assert "/5" not in md


def test_notes_skipped_reviewers():
    md = render_report(classes=[], reviews=[],
                        skipped_reviewers=[{"id": "r2", "reason": "tool failure"}])
    assert "Skipped" in md
    assert "r2" in md
    assert "tool failure" in md


def test_no_reviews_graceful():
    md = render_report(classes=[], reviews=[], skipped_reviewers=[])
    assert "# Manuscript feedback report" in md
    assert "No reviews produced" in md
