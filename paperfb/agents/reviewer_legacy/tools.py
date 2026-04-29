import json
from pathlib import Path

from paperfb.contracts import REVIEW_REQUIRED_FIELDS


class ReviewValidationError(ValueError):
    pass


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_review",
        "description": (
            "Write your structured review to disk. Call exactly once when your review is "
            "complete. Output three free-text aspects (strong_aspects, weak_aspects, "
            "recommended_changes); do not emit numeric ratings."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reviewer_id":         {"type": "string"},
                "reviewer_name":       {"type": "string"},
                "specialty":           {"type": "string"},
                "stance":              {"type": "string"},
                "primary_focus":       {"type": "string"},
                "secondary_focus":     {"type": ["string", "null"]},
                "profile_summary":     {"type": "string"},
                "strong_aspects":      {"type": "string"},
                "weak_aspects":        {"type": "string"},
                "recommended_changes": {"type": "string"},
            },
            "required": list(REVIEW_REQUIRED_FIELDS),
        },
    },
}


def _validate(review: dict) -> None:
    missing = [f for f in REVIEW_REQUIRED_FIELDS if f not in review]
    if missing:
        raise ReviewValidationError(f"review missing fields: {missing}")


def write_review(review: dict, reviews_dir: Path) -> Path:
    _validate(review)
    reviews_dir = Path(reviews_dir)
    reviews_dir.mkdir(parents=True, exist_ok=True)
    out = reviews_dir / f"{review['reviewer_id']}.json"
    out.write_text(json.dumps(review, indent=2, ensure_ascii=False))
    return out
