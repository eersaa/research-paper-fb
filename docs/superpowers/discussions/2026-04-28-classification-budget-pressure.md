# Classification — residual budget pressure after tool-protocol fix

Status: **observation, not yet actionable**. Documented for the next brainstorm.

Surfaced by: post-merge sanity runs of the classification tool-protocol redesign (branch `classification-tool-protocol`, plan `2026-04-28-classification-tool-protocol.md`).

## Symptom

After the redesign, the two original failure modes are gone (`JSONDecodeError` and the old budget-6 exhaustion). But classification still hits the new budget (8) on `tests/fixtures/tiny_manuscript.md` against `anthropic/claude-3.5-haiku` at a non-trivial rate.

| Trial type | Runs | Successes | Failures |
|---|---|---|---|
| pytest live acceptance test | 2 | 2 | 0 |
| `python -m paperfb` CLI | 6 | 3 | 3 |
| **Total** | **8** | **5** | **3** |

Empirical failure rate ≈ 37% on a single manuscript. The pytest test happens to land in the lucky tail; the CLI shows the wider distribution.

Failure shape is always the same: `RuntimeError: Classification did not call submit_classification within budget` at `agent.py:_LOOP_BUDGET=8`. No prose-preamble, no validation rejection — the model just runs out of turns calling `lookup_acm`.

## Root cause as currently understood

Word-boundary multi-token AND matching is **substantially stricter** than the old substring matcher, in a way the spec acknowledged (§5) but underweighted.

Instrumented run on the same fixture:

```
lookup_acm(query='performance benchmarking python list summation') → 0 matches
lookup_acm(query='python performance')                              → 0 matches
lookup_acm(query='performance')                                     → 10 matches
lookup_acm(query='python benchmarking numerical computing')         → 0 matches
lookup_acm(query='numerical computation')                           → 8 matches
[submit_classification — 5 turns spent on lookup, 1 on commit, 6 total]
```

The model's instinct is to send a long descriptive multi-token query first. With AND semantics every token has to be present — most fail. The model then iterates with simpler queries. When five 0-match probes happen in a row before the model adapts, the budget is gone.

System prompt says "prefer multiple short queries over one long one" but the model does not consistently obey on the first turn.

## What's NOT the cause

- Not the `submit_classification` validator — failures occur before any submit call.
- Not the no-tool-call nudge path — failures show 8 lookups, no nudges.
- Not validation retries eating budget — same.
- Not `lookup_acm` correctness — when queries are short, matches are returned correctly.
- Not the data file — flat list of dicts is fine for the queries that succeed.

## Options to consider (not picks)

- **Bump `_LOOP_BUDGET` 8 → 12.** Cheapest. Successful runs use 5–7 turns; bad luck uses all 8. Header room of 4 should absorb the empirical variance. Spec §6 explicitly defers budget tuning to "after this lands".
- **Soften matching: AND-then-OR fallback.** If word-boundary AND returns 0, fall back to OR (any token matches) before reporting empty. Restores recall the old substring matcher provided without re-introducing the "ML matches HTML" bug. Adds one branch in `lookup_acm`.
- **Strengthen the system prompt.** Forbid >2-token queries explicitly; require the model to start single-token. Free, but model-compliance dependent.
- **Tool-result diagnostics on 0 matches.** When `lookup_acm` returns `[]`, return a hint like `{"matches": [], "tip": "try fewer or shorter tokens"}`. The model sees the tip in the next turn's context. Cheap, plausibly effective.
- **Keep matching strict, lift recall via embeddings.** The deferred direction from `2026-04-27-classification-tool-and-data-representation.md`. Larger change; out of scope here.

The first three are reversible single-line / single-block edits. The fourth is small. The fifth is a separate project.

## Constraints that hold

- `submit_classification` and `ClassificationResult.classes` shape are now load-bearing across tests and orchestrator — do not change.
- Word-boundary matching's correctness wins (`ML` ∉ `HTML`) must not regress — any softening must preserve the precision floor.
- Live acceptance test `tests/test_acceptance_live.py` should remain the empirical gauge.

## Open questions

- Is the right fix on the `lookup_acm` side (recall) or the agent side (budget / prompt)?
- What failure rate is acceptable? <5% with this model? Different threshold per model?
- Is `tiny_manuscript.md` representative, or is it a worst-case (CS-but-not-CCS-vocabulary)? More fixtures would tell.
- Should the live acceptance test be promoted from a single-shot pass/fail to N runs with a rate threshold?
- If we add a 0-match hint payload, does that bias the model in undesirable ways on legitimate empties?

## Out of scope here

- Picking a fix.
- Implementation.
- Embedding-based retrieval (covered by the deferred 2026-04-27 discussion).
