"""LLM-as-judge harness. Reads evaluations/run-<ts>/run.json (RunOutput),
scores each review on the 5-dim Likert rubric, writes judge.json alongside.

Bypasses AG2 — calls the proxy directly via the OpenAI SDK. Judge is a
Wave-2 standalone tool (spec §8) and doesn't need chat orchestration.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from paperfb.config import load_config
from paperfb.schemas import (
    DimensionScore, JudgeScore, Review, ReviewerProfile, RunOutput,
)


DIMENSIONS = ["specificity", "actionability", "persona_fidelity", "coverage", "non_redundancy"]


JUDGE_SYSTEM = """You are an impartial evaluator of peer-review feedback.
Given a manuscript, the reviewer's persona context, and the reviewer's review,
score the review on five 1-5 Likert dimensions:

  - specificity:      grounded in manuscript text vs generic
  - actionability:    suggestions are concrete and implementable
  - persona_fidelity: matches assigned stance + primary_focus
  - coverage:         primary focus area is meaningfully addressed
  - non_redundancy:   contributes points distinct from generic boilerplate

Respond with STRICT JSON only — no prose, no markdown fences. Each "score" must be an integer in [1, 5]:
{"specificity":      {"score": <integer 1-5>, "justification": "..."},
 "actionability":    {"score": <integer 1-5>, "justification": "..."},
 "persona_fidelity": {"score": <integer 1-5>, "justification": "..."},
 "coverage":         {"score": <integer 1-5>, "justification": "..."},
 "non_redundancy":   {"score": <integer 1-5>, "justification": "..."}}
"""


class _OpenAIChat:
    """Thin wrapper around OpenAI SDK matching the v1 LLMClient.chat() contract."""

    def __init__(self, client: OpenAI):
        self._client = client

    def chat(self, messages, model, **kw):
        resp = self._client.chat.completions.create(model=model, messages=messages, **kw)
        choice = resp.choices[0]
        return type("Res", (), {
            "content": choice.message.content,
            "tool_calls": None,
            "finish_reason": choice.finish_reason,
        })()


def from_env(default_model: str):
    """Construct an OpenAI client wrapper pointing at the proxy. Module-level
    callable so tests can monkey-patch it."""
    return _OpenAIChat(OpenAI(base_url=os.environ["BASE_URL"], api_key="unused"))


def _user_message(manuscript: str, review: Review, profile: ReviewerProfile) -> str:
    return (
        f"Manuscript:\n<MANUSCRIPT>\n{manuscript}\n</MANUSCRIPT>\n\n"
        f"Reviewer stance: {profile.stance}\n"
        f"Reviewer primary_focus: {profile.primary_focus}\n"
        f"Reviewer secondary_focus: {profile.secondary_focus}\n\n"
        f"Review JSON:\n{review.model_dump_json(indent=2)}"
    )


_FENCE_RE = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL)


def _strip_fence(content: str) -> str:
    m = _FENCE_RE.match(content)
    return m.group(1) if m else content


def _validate_score(raw: dict) -> JudgeScore:
    js = JudgeScore.model_validate(raw)
    for dim in DIMENSIONS:
        s = getattr(js, dim).score
        if not (1 <= s <= 5):
            raise ValueError(f"{dim} out of range: {s} (must be 1-5)")
    return js


def judge_review(
    manuscript: str,
    review: Review,
    profile: ReviewerProfile,
    llm,
    model: str,
) -> JudgeScore:
    res = llm.chat(
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": _user_message(manuscript, review, profile)},
        ],
        model=model,
    )
    return _validate_score(json.loads(_strip_fence(res.content)))


def _mean(score: JudgeScore) -> float:
    return sum(getattr(score, d).score for d in DIMENSIONS) / len(DIMENSIONS)


def _entry(review: Review, profile: ReviewerProfile, score: JudgeScore) -> dict:
    return {
        "reviewer_id": review.reviewer_id,
        **{d: getattr(score, d).model_dump() for d in DIMENSIONS},
        "mean": _mean(score),
    }


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="LLM-as-judge for reviewer feedback")
    p.add_argument("--manuscript", required=True, help="Path to manuscript markdown.")
    p.add_argument("--run-dir", required=True,
                   help="Path to evaluations/run-<ts>/ directory containing run.json.")
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--axes", default="config/axes.yaml")
    p.add_argument("--model", default=None, help="Override cfg.models.judge.")
    args = p.parse_args(argv)

    cfg = load_config(Path(args.config), Path(args.axes))
    model = args.model or cfg.models.judge

    run_obj = RunOutput.model_validate_json(Path(args.run_dir, "run.json").read_text())
    manuscript = Path(args.manuscript).read_text()

    profiles_by_id = {p.id: p for p in run_obj.profiles.reviewers}
    llm = from_env(default_model=model)

    per_reviewer: list[dict] = []
    for review in run_obj.board.reviews:
        profile = profiles_by_id[review.reviewer_id]
        score = judge_review(manuscript, review, profile, llm=llm, model=model)
        per_reviewer.append(_entry(review, profile, score))

    if not per_reviewer:
        print("No reviews to judge.", file=sys.stderr)
        return 1
    board_mean = sum(e["mean"] for e in per_reviewer) / len(per_reviewer)

    out = Path(args.run_dir, "judge.json")
    out.write_text(json.dumps({
        "manuscript": str(Path(args.manuscript).resolve()),
        "judge_model": model,
        "per_reviewer": per_reviewer,
        "board_mean": board_mean,
    }, indent=2, ensure_ascii=False))
    print(f"Wrote {out}  (board_mean={board_mean:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
