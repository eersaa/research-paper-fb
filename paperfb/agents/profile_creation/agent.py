from paperfb.contracts import ReviewerTuple, ReviewerProfile
from paperfb.config import AxesConfig

PERSONA_SYSTEM = """You generate the system prompt for an AI reviewer persona for a research-paper feedback system.
Given: reviewer name, specialty (ACM CCS class), stance (with description), primary focus (with description), secondary focus (with description) — produce the full system prompt that reviewer will use to review a manuscript.

Requirements for the system prompt you produce:
- Second-person voice ("You are ...").
- Address the reviewer by their name in the opening line.
- Establish the reviewer as a domain specialist grounded in the specialty.
- Reflect the stance in tone, drawing on the stance description.
- Emphasise the primary focus, drawing on its description; acknowledge the secondary focus as a supplementary lens.
- The reviewer's three free-text outputs (strong_aspects, weak_aspects, recommended_changes) must each be grounded in the primary focus, with the secondary focus colouring depth where natural. Do NOT instruct the reviewer to emit numeric ratings.
- Instruct the reviewer to call the write_review tool with their structured review.
- Forbid the reviewer from rewriting the paper.
- No meta-commentary, no preamble — output the system prompt directly.
"""


def _lookup(items, name):
    for it in items:
        if it.name == name:
            return it
    return None


def create_profiles(
    tuples: list[ReviewerTuple],
    axes: AxesConfig,
    llm,
    model: str,
) -> list[ReviewerProfile]:
    profiles: list[ReviewerProfile] = []
    for t in tuples:
        stance_item = _lookup(axes.stances, t.stance)
        primary_item = _lookup(axes.focuses, t.primary_focus)
        secondary_item = _lookup(axes.focuses, t.secondary_focus) if t.secondary_focus else None

        stance_desc = stance_item.description if stance_item else "(no description)"
        primary_desc = primary_item.description if primary_item else "(no description)"
        secondary_line = (
            f"secondary_focus: {t.secondary_focus} — {secondary_item.description}\n"
            if secondary_item else "secondary_focus: (none)\n"
        )

        user = (
            f"reviewer_name: {t.name}\n"
            f"specialty: {t.specialty['path']}\n"
            f"specialty description: {t.specialty.get('description', '(none)')}\n"
            f"stance: {t.stance} — {stance_desc}\n"
            f"primary_focus: {t.primary_focus} — {primary_desc}\n"
            f"{secondary_line}"
        )
        res = llm.chat(
            messages=[
                {"role": "system", "content": PERSONA_SYSTEM},
                {"role": "user", "content": user},
            ],
            model=model,
        )
        profiles.append(ReviewerProfile(
            id=t.id,
            name=t.name,
            specialty=t.specialty,
            stance=t.stance,
            primary_focus=t.primary_focus,
            secondary_focus=t.secondary_focus,
            persona_prompt=res.content.strip(),
        ))
    return profiles
