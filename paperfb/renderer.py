def _prose_or_placeholder(text) -> str:
    text = (text or "").strip()
    return text if text else "_(none)_"


def render_report(classes: list[dict], reviews: list[dict],
                  skipped_reviewers: list[dict]) -> str:
    lines: list[str] = ["# Manuscript feedback report", ""]

    lines.append("## ACM classification")
    lines.append("")
    if classes:
        for c in classes:
            lines.append(f"- **{c['path']}** — weight: {c['weight']}")
            if c.get("rationale"):
                lines.append(f"  - {c['rationale']}")
    else:
        lines.append("_(no classes assigned)_")
    lines.append("")

    if not reviews and not skipped_reviewers:
        lines.append("_No reviews produced._")
        return "\n".join(lines) + "\n"

    for r in reviews:
        name = r.get("reviewer_name") or r.get("reviewer_id", "")
        specialty = r.get("specialty", "")
        header = f"## Review by {name}"
        if specialty:
            header += f" — {specialty}"
        lines.append(header)
        lines.append("")
        blurb_parts = [f"Stance: **{r.get('stance', '')}**",
                       f"primary focus: **{r.get('primary_focus', '')}**"]
        sec = r.get("secondary_focus")
        if sec:
            blurb_parts.append(f"secondary focus: **{sec}**")
        lines.append(", ".join(blurb_parts))
        if r.get("profile_summary"):
            lines.append("")
            lines.append(f"_{r['profile_summary']}_")
        lines.append("")
        lines.append("### Strong aspects")
        lines.append("")
        lines.append(_prose_or_placeholder(r.get("strong_aspects")))
        lines.append("")
        lines.append("### Weak aspects")
        lines.append("")
        lines.append(_prose_or_placeholder(r.get("weak_aspects")))
        lines.append("")
        lines.append("### Recommended changes")
        lines.append("")
        lines.append(_prose_or_placeholder(r.get("recommended_changes")))
        lines.append("")

    if skipped_reviewers:
        lines.append("## Skipped reviewers")
        for s in skipped_reviewers:
            lines.append(f"- {s['id']}: {s['reason']}")
        lines.append("")

    return "\n".join(lines) + "\n"
