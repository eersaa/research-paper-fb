import json
from pathlib import Path
from paperfb.contracts import ReviewerProfile
from paperfb.agents.reviewer.tools import write_review, TOOL_SCHEMA, ReviewValidationError

REVIEWER_USER_TEMPLATE = """Manuscript follows between the markers.

<MANUSCRIPT>
{manuscript}
</MANUSCRIPT>

Write your review by calling the write_review tool. Do not rewrite the paper. Do not output anything else."""


def run_reviewer(profile: ReviewerProfile, manuscript: str, llm, model: str,
                 reviews_dir: Path) -> Path:
    messages = [
        {"role": "system", "content": profile.persona_prompt},
        {"role": "user", "content": REVIEWER_USER_TEMPLATE.format(manuscript=manuscript)},
    ]
    tools = [TOOL_SCHEMA]
    last_validation_error: str | None = None

    for attempt in range(2):
        if last_validation_error is not None:
            messages.append({
                "role": "user",
                "content": f"Your prior write_review call was invalid: {last_validation_error}. "
                            "Retry, producing a complete review.",
            })

        res = llm.chat(messages=messages, tools=tools, model=model)
        if not res.tool_calls:
            raise RuntimeError(f"reviewer {profile.id} did not call write_review")

        for tc in res.tool_calls:
            if tc.function.name != "write_review":
                continue
            args = json.loads(tc.function.arguments)
            args.setdefault("reviewer_id", profile.id)
            args.setdefault("stance", profile.stance)
            args.setdefault("primary_focus", profile.primary_focus)
            args.setdefault("secondary_focus", profile.secondary_focus)
            try:
                return write_review(args, reviews_dir=reviews_dir)
            except ReviewValidationError as e:
                last_validation_error = str(e)
                break

    raise RuntimeError(f"reviewer {profile.id} failed to produce valid review after retry")
