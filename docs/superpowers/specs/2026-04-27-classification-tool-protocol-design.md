# Classification agent — tool protocol redesign

Status: **design approved**, ready for implementation plan.

Supersedes the deferred problem statement at [`2026-04-27-classification-tool-and-data-representation.md`](../discussions/2026-04-27-classification-tool-and-data-representation.md).

## Context

The Classification Agent (`paperfb/agents/classification/agent.py`) commits its final answer through free-text `res.content` and parses it as JSON. Two distinct live-test failures with `anthropic/claude-3.5-haiku`:

1. `JSONDecodeError` at `agent.py:48` — model added prose preamble before the JSON block.
2. `RuntimeError: Classification exceeded tool-loop budget` at `agent.py:53` — model called `lookup_acm` six times without committing.

Mock-LLM unit tests returned clean JSON and missed both modes. The fix is a structured tool-call commit channel — the same pattern Reviewer Agent already uses with `write_review` ([`paperfb/agents/reviewer/tools.py`](../../../paperfb/agents/reviewer/tools.py)).

Scope decision (from brainstorm): **fix the agent–tool protocol; keep `data/acm_ccs.json` as a flat list**. Tree/graph/embedding representations deferred. Smallest change that closes the failure modes.

## 1. Architecture

- Add `submit_classification` tool — single commit channel. Eliminates free-text JSON parsing.
- Improve `lookup_acm` — word-boundary tokenized matching, multi-token AND, return `leaf` and `parent_path`. Drop substring-only.
- Restore spec §4.1: `keywords.{extracted_from_paper, synthesised}` is a required field on `submit_classification`. Audit block is schema-enforced.
- Keep `data/acm_ccs.json` flat. No changes to `scripts/build_acm_ccs.py` or `data/_ccs_descriptions_cache.json`.
- Loop budget = 8 (was 6). Termination = `submit_classification` validates.
- Downstream contract unchanged: `ClassificationResult.classes` is what flows to Profile Creation. The keywords block is logged for the Judge but does not propagate.

## 2. Tool schemas

### `lookup_acm` (read channel — improved)

```json
{
  "name": "lookup_acm",
  "description": "Search the ACM CCS for concept paths matching one or more keywords. Returns up to k entries with their hierarchy context.",
  "parameters": {
    "query": "string — one or more whitespace-separated keywords",
    "k":     "integer, default 10"
  }
}
```

Match rule: query is split into tokens; an entry matches if **every** token appears as a word-boundary, case-insensitive match in `path + " " + description`. Multi-token query is **AND**, not OR.

Returns: list of `{path, leaf, description, parent_path}`.

### `submit_classification` (write channel — new)

```json
{
  "name": "submit_classification",
  "description": "Commit your final classification. Call exactly once when you have decided.",
  "parameters": {
    "keywords": {
      "extracted_from_paper": ["string", "..."],
      "synthesised":          ["string", "..."]
    },
    "classes": [
      {"path": "<full CCS path>",
       "weight": "High|Medium|Low",
       "rationale": "<short>"}
    ]
  },
  "required": ["keywords", "classes"]
}
```

Validation (raises `ClassificationValidationError`, retried once like `write_review`):
- `1 ≤ len(classes) ≤ max_classes`
- Every `path` exists in the loaded CCS entries (exact match against `path` field).
- `weight ∈ {High, Medium, Low}`.
- At least one of `keywords.extracted_from_paper` / `keywords.synthesised` is non-empty.

### Weight rubric (in system prompt)

- **High**: central topic — would appear in the title or first sentence of the abstract; the paper's primary contribution lives here.
- **Medium**: significant supporting topic — methods, frameworks, or domains the work substantially uses.
- **Low**: relevant but not central — mentioned, compared against, or touched on.

## 3. Agent loop

Replaces the current `agent.py` body. Structurally mirrors Reviewer's loop.

```
messages = [system_prompt, user(manuscript)]
tools    = [lookup_acm, submit_classification]
last_validation_error = None

for attempt in range(8):
    if last_validation_error:
        messages.append(user(f"submit_classification was rejected: {err}. Retry."))
        last_validation_error = None

    res = llm.chat(messages, tools, model)

    if not res.tool_calls:
        messages.append(user("You must use lookup_acm or submit_classification. Do not reply in plain text."))
        continue

    for tc in res.tool_calls:
        if tc.function.name == "lookup_acm":
            append assistant tool_call + tool_result to messages
        elif tc.function.name == "submit_classification":
            try:
                return validate_and_build_result(tc.arguments, max_classes, ccs_entries)
            except ClassificationValidationError as e:
                last_validation_error = str(e)
                break

raise RuntimeError("Classification did not call submit_classification within budget")
```

Properties:
- Single termination point (`submit_classification` validates).
- Three named failure shapes: validation error (retried), no tool call (nudged), budget exhausted (terminal).
- One round-trip per turn — fixes the duplicate `lookup_acm` invocation at current `agent.py:30-32` vs `39-41` where the first result is discarded.
- System prompt instructs explicit two-phase behavior per spec §4.1: extract or synthesise keywords first, drive `lookup_acm` from those keywords, then submit.

## 4. Tests

Update `tests/agents/classification/test_agent.py` — mocks drive tool-call sequences (drop the prose-JSON pattern):

| Test | Mock LLM behaviour | Expected outcome |
|---|---|---|
| Happy path | turn 1: 2× `lookup_acm`; turn 2: `submit_classification` (valid) | returns `ClassificationResult` |
| Bad weight | submit with `weight: "Critical"` | one retry, then second submit succeeds |
| Unknown CCS path | submit with path not in CCS data | one retry, then second submit succeeds |
| Empty classes | submit with `classes: []` | retry, then succeed |
| No tool call | model returns free-text content | nudge; second turn calls submit |
| Budget exhausted | only calls `lookup_acm`, never submits | `RuntimeError` after 8 iterations |
| Prose preamble (regression) | emits `"Sure, here's...{json}"` as content, no tool call | nudge → recover or fail cleanly (was run 1) |

Add `tests/agents/classification/test_tools.py` cases:
- `lookup_acm("ML")` does **not** match "HTML" (word-boundary).
- Multi-token query is AND.
- `parent_path` populated correctly.

`tests/test_acceptance_live.py` unchanged — slow-marked, optional; no longer the only thing that catches commit-channel bugs.

## 5. Risks

- **Word-boundary stricter than substring** may miss hits the old substring matched. Mitigation: agent can issue multiple queries with variants. Acceptable.
- **Prompt-ignoring models** can still hit budget. That's the right failure surface — model-capability issue, not agent-code issue.
- **Validation retries amplify cost** — capped at one retry per submit attempt (same as Reviewer).

## 6. Out of scope (consciously deferred)

- Tree/graph/embedding data representation.
- Cross-link extraction from CCS SKOS source (`scripts/build_acm_ccs.py` changes).
- Any change to Profile Creation, Reviewer, or `data/_ccs_descriptions_cache.json`.
- Loop-budget tuning beyond 8 — revisit empirically after this lands.

## 7. Critical files

- `paperfb/agents/classification/agent.py` — loop rewritten (Section 3).
- `paperfb/agents/classification/tools.py` — improved `lookup_acm`, new `submit_classification` + `TOOL_SCHEMAS`, `ClassificationValidationError`.
- `paperfb/agents/classification/__init__.py` — export new error type if needed.
- `paperfb/contracts.py` — verify `ClassificationResult` shape; no change expected.
- `tests/agents/classification/test_agent.py` — rewrite per Section 4.
- `tests/agents/classification/test_tools.py` — add word-boundary cases.

## 8. Verification

1. `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/agents/classification -q` — all unit tests pass.
2. `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest -q` — full suite green.
3. `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/test_acceptance_live.py -q` (manual, slow, requires proxy) — runs end-to-end against `anthropic/claude-3.5-haiku` without `JSONDecodeError` or budget-exhaustion failures.

## 9. Unresolved questions

- None — design approved across protocol shape, data shape (flat), keyword phase (field on submit), and weight rubric (Option A).
