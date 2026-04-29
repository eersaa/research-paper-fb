"""Markdown report renderer (spec §6.6). Pure function: RunOutput in, str out.

Joins each Review with its ReviewerProfile via reviewer_id so the slim Review
schema (no metadata echo) renders with full reviewer identity in the header.
"""
from __future__ import annotations

from paperfb.schemas import Review, ReviewerProfile, RunOutput


def _prose_or_placeholder(text: str) -> str:
    text = (text or "").strip()
    return text if text else "_(none)_"


def _render_review(review: Review, profile: ReviewerProfile) -> list[str]:
    out: list[str] = []
    out.append(f"## Review by {profile.name} — {profile.specialty}")
    out.append("")
    blurb = [f"Stance: **{profile.stance}**",
             f"primary focus: **{profile.primary_focus}**"]
    if profile.secondary_focus:
        blurb.append(f"secondary focus: **{profile.secondary_focus}**")
    out.append(", ".join(blurb))
    if profile.profile_summary:
        out.append("")
        out.append(f"_{profile.profile_summary}_")
    out.append("")
    out.append("### Strong aspects")
    out.append("")
    out.append(_prose_or_placeholder(review.strong_aspects))
    out.append("")
    out.append("### Weak aspects")
    out.append("")
    out.append(_prose_or_placeholder(review.weak_aspects))
    out.append("")
    out.append("### Recommended changes")
    out.append("")
    out.append(_prose_or_placeholder(review.recommended_changes))
    out.append("")
    return out


def render_report(run: RunOutput) -> str:
    lines: list[str] = ["# Manuscript feedback report", ""]

    lines.append("## ACM classification")
    lines.append("")
    if run.classification.classes:
        for c in run.classification.classes:
            lines.append(f"- **{c.path}** — weight: {c.weight}")
            if c.rationale:
                lines.append(f"  - {c.rationale}")
    else:
        lines.append("_(no classes assigned)_")
    lines.append("")

    if not run.board.reviews and not run.board.skipped:
        lines.append("_No reviews produced._")
        return "\n".join(lines) + "\n"

    profiles_by_id = {p.id: p for p in run.profiles.reviewers}
    for review in run.board.reviews:
        profile = profiles_by_id.get(review.reviewer_id)
        if profile is None:
            continue
        lines.extend(_render_review(review, profile))

    if run.board.skipped:
        lines.append("## Skipped reviewers")
        for s in run.board.skipped:
            lines.append(f"- {s.id}: {s.reason}")
        lines.append("")

    return "\n".join(lines) + "\n"
