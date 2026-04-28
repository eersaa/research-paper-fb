"""LLM-as-judge evaluation harness for reviewer feedback.

Scores one reviewer's review on a 5-dim Likert (1-5) rubric using a
strict-JSON prompt and validates the response. Standalone — no runtime
coupling to the orchestrator. Different model from the reviewers
(bias mitigation per spec §9) is enforced by the caller.
"""
from __future__ import annotations

import json
from dataclasses import dataclass


DIMENSIONS = ["specificity", "actionability", "persona_fidelity", "coverage", "non_redundancy"]


JUDGE_SYSTEM = """You are an impartial evaluator of peer-review feedback.
Given a manuscript and one reviewer's review, score the review on five 1-5 Likert dimensions.

  - specificity: grounded in manuscript text vs generic
                 (5 = quotes / section refs; 1 = vague generalities)
  - actionability: suggestions are concrete and implementable
                   (5 = stepwise + measurable; 1 = "improve X")
  - persona_fidelity: matches assigned stance + primary_focus
                      (5 = clearly on-persona; 1 = off-brief)
  - coverage: primary focus area is meaningfully addressed
              (5 = deep; 1 = superficial)
  - non_redundancy: contributes points distinct from generic boilerplate
                    (5 = distinct; 1 = generic)

Respond with STRICT JSON only — no prose, no markdown fences:
{"specificity":      {"score": 1-5, "justification": "..."},
 "actionability":    {"score": 1-5, "justification": "..."},
 "persona_fidelity": {"score": 1-5, "justification": "..."},
 "coverage":         {"score": 1-5, "justification": "..."},
 "non_redundancy":   {"score": 1-5, "justification": "..."}}
"""


@dataclass
class DimensionScore:
    score: int
    justification: str


@dataclass
class RubricScores:
    specificity: DimensionScore
    actionability: DimensionScore
    persona_fidelity: DimensionScore
    coverage: DimensionScore
    non_redundancy: DimensionScore

    @property
    def mean(self) -> float:
        return sum(getattr(self, d).score for d in DIMENSIONS) / len(DIMENSIONS)


def _build_user_message(manuscript: str, review: dict) -> str:
    return (
        f"Manuscript:\n<MANUSCRIPT>\n{manuscript}\n</MANUSCRIPT>\n\n"
        f"Reviewer stance: {review.get('stance')}\n"
        f"Reviewer primary_focus: {review.get('primary_focus')}\n"
        f"Reviewer secondary_focus: {review.get('secondary_focus')}\n\n"
        f"Review JSON:\n{json.dumps(review, indent=2, ensure_ascii=False)}"
    )


def _parse_dimension(raw: dict, dim: str) -> DimensionScore:
    if dim not in raw:
        raise ValueError(f"missing dimension {dim}")
    entry = raw[dim]
    if not isinstance(entry, dict) or "score" not in entry:
        raise ValueError(f"{dim} must be a dict with 'score' and 'justification'")
    score = entry["score"]
    if not isinstance(score, int) or not (1 <= score <= 5):
        raise ValueError(f"{dim} out of range: {score}")
    return DimensionScore(score=score, justification=entry.get("justification", ""))


def judge_review(manuscript: str, review: dict, llm, model: str) -> RubricScores:
    res = llm.chat(
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": _build_user_message(manuscript, review)},
        ],
        model=model,
    )
    raw = json.loads(res.content)
    return RubricScores(**{dim: _parse_dimension(raw, dim) for dim in DIMENSIONS})
