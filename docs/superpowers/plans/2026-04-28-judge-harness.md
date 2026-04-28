# Judge Harness (Wave 2, Task 14) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the LLM-as-judge evaluation harness that scores each reviewer's review on a five-dimension Likert rubric, writes per-reviewer + board-level means to `evaluations/<run-id>.json`, and is built test-first against fixture good/bad reviews.

**Architecture:** Standalone script under `scripts/judge.py`, no runtime coupling to the orchestrator — reads `reviews/*.json` + manuscript file, writes one JSON per run. One LLM call per reviewer, sequential loop (small N). Strict-JSON `response.content` (no tool call) parsed and range-validated. Uses `cfg.models.judge` (different from reviewer model) for bias mitigation per spec §9.

**Tech Stack:** Python 3.11, `openai` SDK via existing `paperfb.llm_client`, `pyyaml` via existing `paperfb.config`, `python-dotenv`, `pytest` with `MagicMock` (same pattern as `tests/test_orchestrator.py`).

**Spec:** [docs/superpowers/specs/2026-04-24-research-paper-feedback-system-design.md](../specs/2026-04-24-research-paper-feedback-system-design.md) §9. This plan refines the existing Task 14 in [2026-04-24-research-paper-feedback-system.md](2026-04-24-research-paper-feedback-system.md) with four deltas resolved during planning:

1. **Per-dimension justifications** (was: one overall string).
2. **Arithmetic mean** computed per-reviewer and board-level.
3. **Baseline single-shot comparison** is human-only (paste manuscript into Claude chat, eyeball) — explicitly out of scope for Judge.
4. **No "good vs bad review" fixture-bound score-bound tests.** The spec line "fixtures of known-good and known-bad reviews with expected score bounds" was a general framing. In practice (a) defining a canonical "good" review is subjective and (b) every other agent in this codebase is tested by mocking the LLM and asserting on wiring/validation — Judge follows that same pattern. Tests cover structure, range validation, mean math, and CLI integration. Quality of LLM judgment is observed via the live smoke run.

Plus: Judge reads `cfg.models.judge` rather than hard-coding a model literal in the CLI defaults.

---

## File structure

| File | Responsibility |
|---|---|
| `scripts/judge.py` | All judge logic in one module: `DimensionScore`, `RubricScores` dataclasses, pure `judge_review()` function, CLI `main()`. ~150 LOC. |
| `tests/test_judge.py` | Mock-LLM tests covering structure, validation, mean math, and CLI integration with `tmp_path` — same pattern as `tests/test_orchestrator.py`. |

**Reuses without modification:** `tests/fixtures/tiny_manuscript.md` (already exists, created in Task 15 of the master plan) for the live smoke run in Task 3. No new fixture files.

**Not modified:** `paperfb/contracts.py` (no runtime consumer of `RubricScores`, keep the type local), `paperfb/llm_client.py` (already supports `model=` override), `paperfb/config.py` (`models.judge` field already present at line 13), `config/default.yaml` (`judge: openai/gpt-4.1-mini` already wired).

**README:** small addition under "Evaluation" — Task 4 below.

---

## Task 1: `judge_review` core (types, prompt, validation, mean)

**Files:**
- Create: `tests/test_judge.py`
- Create: `scripts/judge.py`

This task drives the pure function `judge_review(manuscript, review, llm, model) -> RubricScores` plus its supporting types (`DimensionScore`, `RubricScores`). Tests follow the same mock-LLM pattern as `tests/test_orchestrator.py`: stub `llm.chat` to return a chosen JSON string, then assert on structure, validation behaviour, and wiring. **No assertions on whether the LLM "should have" scored a given review high or low — that's a quality concern observed in the live smoke run, not a unit-test concern.** CLI is Task 2.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_judge.py`:

```python
import json
from unittest.mock import MagicMock
import pytest

from scripts.judge import judge_review, RubricScores, DimensionScore, DIMENSIONS


# Inline minimal review and manuscript — tests don't depend on file fixtures.
MANUSCRIPT = "Tiny manuscript body for prompt-wiring assertions."

REVIEW = {
    "reviewer_id": "r1",
    "reviewer_name": "Aino",
    "specialty": "ML",
    "stance": "critical",
    "primary_focus": "methods",
    "secondary_focus": "results",
    "profile_summary": "",
    "strong_aspects": "x",
    "weak_aspects": "y",
    "recommended_changes": "z",
}


def _llm_returning(payload_dict: dict) -> MagicMock:
    """Stub LLMClient whose .chat(...) returns content=json.dumps(payload_dict)."""
    client = MagicMock()
    res = MagicMock()
    res.content = json.dumps(payload_dict)
    res.tool_calls = None
    res.finish_reason = "stop"
    client.chat.return_value = res
    return client


def _payload(specificity=4, actionability=4, persona_fidelity=4,
             coverage=4, non_redundancy=4) -> dict:
    return {
        "specificity":      {"score": specificity,      "justification": "spec j"},
        "actionability":    {"score": actionability,    "justification": "act j"},
        "persona_fidelity": {"score": persona_fidelity, "justification": "pf j"},
        "coverage":         {"score": coverage,         "justification": "cov j"},
        "non_redundancy":   {"score": non_redundancy,   "justification": "nr j"},
    }


def test_returns_rubric_scores_with_all_five_dimensions():
    llm = _llm_returning(_payload())
    scores = judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")
    assert isinstance(scores, RubricScores)
    for dim in DIMENSIONS:
        d = getattr(scores, dim)
        assert isinstance(d, DimensionScore)
        assert 1 <= d.score <= 5
        assert d.justification != ""


def test_mean_is_arithmetic_average_of_five_dimensions():
    llm = _llm_returning(_payload(specificity=5, actionability=4, persona_fidelity=3,
                                  coverage=2, non_redundancy=1))
    scores = judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")
    assert scores.mean == pytest.approx((5 + 4 + 3 + 2 + 1) / 5)


def test_out_of_range_score_raises():
    llm = _llm_returning(_payload(specificity=7))
    with pytest.raises(ValueError, match="specificity out of range"):
        judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")


def test_zero_score_raises():
    llm = _llm_returning(_payload(coverage=0))
    with pytest.raises(ValueError, match="coverage out of range"):
        judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")


def test_missing_dimension_raises():
    payload = _payload()
    del payload["coverage"]
    llm = _llm_returning(payload)
    with pytest.raises(ValueError, match="missing dimension coverage"):
        judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")


def test_non_int_score_raises():
    payload = _payload()
    payload["specificity"]["score"] = "five"
    llm = _llm_returning(payload)
    with pytest.raises(ValueError, match="specificity out of range"):
        judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")


def test_passes_model_through_to_llm_chat():
    llm = _llm_returning(_payload())
    judge_review(MANUSCRIPT, REVIEW, llm=llm, model="openai/gpt-4.1-mini")
    _, kwargs = llm.chat.call_args
    assert kwargs.get("model") == "openai/gpt-4.1-mini"


def test_user_message_contains_manuscript_and_review_fields():
    llm = _llm_returning(_payload())
    judge_review(MANUSCRIPT, REVIEW, llm=llm, model="stub")
    _, kwargs = llm.chat.call_args
    user_msg = next(m["content"] for m in kwargs["messages"] if m["role"] == "user")
    assert MANUSCRIPT in user_msg
    assert REVIEW["stance"] in user_msg
    assert REVIEW["primary_focus"] in user_msg
    assert REVIEW["strong_aspects"] in user_msg
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/test_judge.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'scripts.judge'` (or `ImportError`).

- [ ] **Step 3: Implement `scripts/judge.py` core**

Create `scripts/judge.py`:

```python
"""LLM-as-judge evaluation harness for reviewer feedback.

Scores each reviewer's review on a 5-dim Likert (1-5) rubric and writes a
per-run JSON to evaluations/<run-id>.json. Standalone — no runtime coupling
to the orchestrator. Uses cfg.models.judge (different model from reviewers)
for bias mitigation per spec §9.

Usage (CLI):
    uv run python scripts/judge.py --manuscript samples/01/manuscript.md
    # → evaluations/run-<UTC-timestamp>.json

    uv run python scripts/judge.py --manuscript X --reviews-dir reviews \\
        --output evaluations/myrun.json --model openai/gpt-4.1-mini
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/test_judge.py -v`

Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add scripts/judge.py tests/test_judge.py
git commit -m "Implement judge_review with per-dimension Likert scoring"
```

---

## Task 2: CLI `main()` — board-level mean, run-id, evaluations file

**Files:**
- Modify: `tests/test_judge.py` (append tests)
- Modify: `scripts/judge.py` (append `main` and `_run_id` and required imports)

The CLI loads config (for `models.judge`), iterates `reviews/*.json`, writes per-reviewer + board-level mean to `evaluations/<run-id>.json`.

- [ ] **Step 1: Append failing CLI tests**

Append to `tests/test_judge.py`:

```python
from dataclasses import replace as _replace
from paperfb.config import load_config


def _stub_llm_factory(payload_dict: dict):
    """Returns a callable matching from_env(default_model=...) that yields a stub LLM."""
    def _factory(default_model: str):
        return _llm_returning(payload_dict)
    return _factory


def _write_review(path: Path, reviewer_id: str) -> None:
    path.write_text(json.dumps({
        "reviewer_id": reviewer_id,
        "reviewer_name": "Aino",
        "specialty": "ML",
        "stance": "critical",
        "primary_focus": "methods",
        "secondary_focus": None,
        "profile_summary": "",
        "strong_aspects": "x",
        "weak_aspects": "y",
        "recommended_changes": "z",
    }))


def _write_manuscript(tmp_path: Path) -> Path:
    p = tmp_path / "manuscript.md"
    p.write_text("Tiny manuscript body.")
    return p


def test_main_writes_per_reviewer_and_board_mean(tmp_path, monkeypatch):
    from scripts import judge as judge_mod

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    _write_review(reviews_dir / "r1.json", "r1")
    _write_review(reviews_dir / "r2.json", "r2")
    manuscript = _write_manuscript(tmp_path)

    monkeypatch.setattr(judge_mod, "from_env", _stub_llm_factory(_payload(
        specificity=5, actionability=5, persona_fidelity=5, coverage=5, non_redundancy=5)))

    out_path = tmp_path / "eval.json"
    rc = judge_mod.main([
        "--manuscript", str(manuscript),
        "--reviews-dir", str(reviews_dir),
        "--output", str(out_path),
    ])
    assert rc == 0

    data = json.loads(out_path.read_text())
    assert len(data["per_reviewer"]) == 2
    for entry in data["per_reviewer"]:
        assert entry["mean"] == pytest.approx(5.0)
        for dim in DIMENSIONS:
            assert entry[dim]["score"] == 5
            assert entry[dim]["justification"] != ""
    assert data["board_mean"] == pytest.approx(5.0)
    assert data["judge_model"]  # non-empty


def test_main_auto_generates_run_id_when_output_omitted(tmp_path, monkeypatch):
    from scripts import judge as judge_mod

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    _write_review(reviews_dir / "r1.json", "r1")
    manuscript = _write_manuscript(tmp_path)

    # Resolve config paths against the repo root before we chdir, so main()
    # can still find them after the cwd flip.
    cfg_default = Path("config/default.yaml").resolve()
    cfg_axes = Path("config/axes.yaml").resolve()

    eval_dir = tmp_path / "evaluations"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(judge_mod, "from_env", _stub_llm_factory(_payload()))

    rc = judge_mod.main([
        "--manuscript", str(manuscript),
        "--reviews-dir", str(reviews_dir),
        "--config", str(cfg_default),
        "--axes", str(cfg_axes),
    ])
    assert rc == 0

    written = list(eval_dir.glob("run-*.json"))
    assert len(written) == 1
    assert written[0].name.startswith("run-") and written[0].name.endswith(".json")


def test_main_uses_cfg_models_judge_when_model_flag_omitted(tmp_path, monkeypatch):
    from scripts import judge as judge_mod

    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    expected_model = cfg.models.judge

    reviews_dir = tmp_path / "reviews"
    reviews_dir.mkdir()
    _write_review(reviews_dir / "r1.json", "r1")
    manuscript = _write_manuscript(tmp_path)

    seen_models: list[str] = []

    class _RecordingLLM:
        def chat(self, messages, model=None, **kw):
            seen_models.append(model)
            res = MagicMock()
            res.content = json.dumps(_payload())
            res.tool_calls = None
            res.finish_reason = "stop"
            return res

    monkeypatch.setattr(judge_mod, "from_env", lambda default_model: _RecordingLLM())

    rc = judge_mod.main([
        "--manuscript", str(manuscript),
        "--reviews-dir", str(reviews_dir),
        "--output", str(tmp_path / "eval.json"),
    ])
    assert rc == 0
    assert seen_models == [expected_model]
```

- [ ] **Step 2: Run the new tests to verify they fail**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/test_judge.py::test_main_writes_per_reviewer_and_board_mean tests/test_judge.py::test_main_auto_generates_run_id_when_output_omitted tests/test_judge.py::test_main_uses_cfg_models_judge_when_model_flag_omitted -v`

Expected: FAIL with `AttributeError: module 'scripts.judge' has no attribute 'main'` (or `from_env`).

- [ ] **Step 3: Append CLI implementation to `scripts/judge.py`**

Add these imports at the top of `scripts/judge.py` (after the existing imports):

```python
from dotenv import load_dotenv

from paperfb.config import load_config
from paperfb.llm_client import from_env
```

Append at the end of `scripts/judge.py`:

```python
def _run_id() -> str:
    return "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _scores_to_dict(scores: RubricScores) -> dict:
    out: dict = {}
    for dim in DIMENSIONS:
        out[dim] = asdict(getattr(scores, dim))
    out["mean"] = scores.mean
    return out


def main(argv: Optional[list[str]] = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="LLM-as-judge for reviewer feedback")
    p.add_argument("--manuscript", required=True,
                   help="Path to the manuscript markdown file judged against.")
    p.add_argument("--reviews-dir", default="reviews",
                   help="Directory containing per-reviewer JSON files (default: reviews/).")
    p.add_argument("--output", default=None,
                   help="Output JSON path. Defaults to evaluations/<run-id>.json.")
    p.add_argument("--config", default="config/default.yaml",
                   help="Path to config/default.yaml (default: config/default.yaml).")
    p.add_argument("--axes", default="config/axes.yaml",
                   help="Path to config/axes.yaml (default: config/axes.yaml).")
    p.add_argument("--model", default=None,
                   help="Override cfg.models.judge.")
    args = p.parse_args(argv)

    cfg = load_config(Path(args.config), Path(args.axes))
    model = args.model or cfg.models.judge

    manuscript = Path(args.manuscript).read_text()
    reviews_dir = Path(args.reviews_dir)
    review_paths = sorted(reviews_dir.glob("*.json"))
    if not review_paths:
        print(f"No reviews found in {reviews_dir}/")
        return 1

    out_path = Path(args.output) if args.output else Path("evaluations") / f"{_run_id()}.json"

    llm = from_env(default_model=model)
    per_reviewer: list[dict] = []
    for rp in review_paths:
        review = json.loads(rp.read_text())
        scores = judge_review(manuscript, review, llm=llm, model=model)
        per_reviewer.append({"reviewer_id": review.get("reviewer_id"), **_scores_to_dict(scores)})

    board_mean = sum(e["mean"] for e in per_reviewer) / len(per_reviewer)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({
        "manuscript":  args.manuscript,
        "judge_model": model,
        "per_reviewer": per_reviewer,
        "board_mean":  board_mean,
    }, indent=2, ensure_ascii=False))
    print(f"Wrote {out_path}  (board_mean={board_mean:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the full judge test file to verify all pass**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/test_judge.py -v`

Expected: 11 passed (8 from Task 1 + 3 new CLI tests).

- [ ] **Step 5: Run the full test suite to verify no regressions**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest`

Expected: all previously-passing tests still pass; the 10 new judge tests pass; slow tests excluded.

- [ ] **Step 6: Commit**

```bash
git add scripts/judge.py tests/test_judge.py
git commit -m "Add Judge CLI with per-reviewer + board-level mean and auto run-id"
```

---

## Task 3: README and live smoke test

**Files:**
- Modify: `README.md`

The Task 16 README draft already includes a Judge example, but it predates the per-dimension / board-mean output shape. Update it. Then run the harness against an actual sample to verify end-to-end.

- [ ] **Step 1: Replace the Evaluation section in `README.md`**

Open `README.md` and find the section starting `## Evaluation` (typically near the bottom). Replace its contents with:

```markdown
## Evaluation

```bash
# After running the pipeline, judge each reviewer's review:
uv run python scripts/judge.py --manuscript samples/01/manuscript.md
# → evaluations/run-<UTC-timestamp>.json

# Override defaults:
uv run python scripts/judge.py \
    --manuscript samples/01/manuscript.md \
    --reviews-dir reviews \
    --output evaluations/myrun.json \
    --model openai/gpt-4.1-mini
```

Each reviewer is scored on five 1–5 Likert dimensions: `specificity`, `actionability`, `persona_fidelity`, `coverage`, `non_redundancy`. Each dimension has its own justification. The output JSON also includes a `mean` per reviewer and a `board_mean` across all reviewers. The judge defaults to `cfg.models.judge` (different from the reviewer model) to reduce self-preference bias.
```

- [ ] **Step 2: Live smoke run (requires `.env` with `BASE_URL`)**

Use the existing `tests/fixtures/tiny_manuscript.md` (already used by the live acceptance test). Run the pipeline first to produce `reviews/r{1..N}.json`, then the judge:

```bash
host-spawn -cwd "$PWD" -- mise exec -- uv run python -m paperfb tests/fixtures/tiny_manuscript.md
host-spawn -cwd "$PWD" -- mise exec -- uv run python scripts/judge.py \
    --manuscript tests/fixtures/tiny_manuscript.md \
    --reviews-dir reviews
```

Expected: prints `Wrote evaluations/run-<ts>.json  (board_mean=X.XX)`. Costs a few cents.

Inspect the output:

```bash
host-spawn -cwd "$PWD" -- ls -la evaluations/
host-spawn -cwd "$PWD" -- cat evaluations/run-*.json | head -80
```

Expected: 3 entries in `per_reviewer`, each with `specificity`/`actionability`/`persona_fidelity`/`coverage`/`non_redundancy` (each a `{score: 1-5, justification: "..."}` dict) plus `mean`. Top-level `board_mean` between 1.0 and 5.0.

- [ ] **Step 3: Commit the README change**

```bash
git add README.md
git commit -m "Document Judge CLI output shape and per-reviewer / board mean"
```

---

## Final verification

- [ ] **Step 1: Full test suite**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest -v`

Expected: every test passes; no regressions in `test_orchestrator`, `test_renderer`, agent test packages.

- [ ] **Step 2: Confirm `evaluations/` is gitignored**

Run: `host-spawn -cwd "$PWD" -- git status`

Expected: any `evaluations/run-*.json` from the smoke run is **not** listed (already in `.gitignore` line 7).

- [ ] **Step 3: Confirm scope adherence**

Verify nothing was added that isn't in this plan:
- No new file under `paperfb/` (Judge stays under `scripts/`).
- No new field in `paperfb/contracts.py` (`RubricScores` stays local to `scripts/judge.py`).
- No tool-call schema for the Judge (strict-JSON `content` parsing only).
- No baseline single-shot script (human-only per spec clarification).
- No cost/token aggregation (Task 14b, separate Wave 2 task).

---

## Out of scope (do not build here)

- **Baseline single-shot comparison.** Done by hand: paste manuscript into Claude chat, save its review, eyeball it against this system's report. No code.
- **Cost / token-usage aggregation** — Task 14b in [2026-04-24-research-paper-feedback-system.md](2026-04-24-research-paper-feedback-system.md), separate Wave 2 task.
- **Per-agent cost breakdown** — explicitly v1-deferred (spec §10).
- **Promoting `RubricScores` to `paperfb/contracts.py`** — no runtime consumer exists.
- **Tool-call API for Judge output** — strict-JSON content parse is sufficient for one structured response per call; tool-call plumbing only earns its keep when the agent loops or chooses among tools.
