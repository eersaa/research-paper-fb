# Classification agent — tool protocol & ACM CCS data representation

Status: **deferred**. Problem statement only. Re-open in a fresh brainstorm session.

Surfaced by: live acceptance test added in I2 (`tests/test_acceptance_live.py`), on `feature/i2-acceptance-readme`.

## Symptom

The live slow test runs `paperfb.orchestrator.run_pipeline` on `tests/fixtures/tiny_manuscript.md` against the real proxy. Two failure modes observed across two runs with `anthropic/claude-3.5-haiku`:

| Run | Error | Where |
|-----|-------|-------|
| 1 | `JSONDecodeError: Expecting value: line 1 column 1 (char 0)` | `paperfb/agents/classification/agent.py:48` |
| 2 | `RuntimeError: Classification exceeded tool-loop budget` | `paperfb/agents/classification/agent.py:53` |

Run 1: model returned `"Based on the manuscript's focus..., I'll classify it as follows:\n\n{\"classes\": [...]}"`. Prose preamble + JSON. `json.loads(res.content)` rejects.

Run 2: model called `lookup_acm` for 6 turns without committing. Loop hit the cap.

Same input, two distinct failures. Non-determinism on top of brittle agent code.

Unit tests at `tests/agents/classification/test_agent.py` mock the LLM to return clean JSON; happy path only. They pass while the live agent does not.

## Root cause as currently understood

Single architectural issue: **classification commits its final answer through free-text content, not a tool call**.

Consequences:
- No structure enforcement. Models add prose despite "no text outside the JSON object" instructions, especially Claude family.
- No closure signal. Without a "submit" tool the loop only ends when the model voluntarily stops calling tools — driven by prompt interpretation, not protocol.

Contributing factors (not the root issue, worth fixing alongside):
- Plan drift from spec §4.1: spec mandates a two-phase loop (explicit keyword extraction → `lookup_acm` queries with a `keywords` audit block in output). Current `agent.py` collapses both phases into one open loop and drops the keyword block.
- Loop budget of 6 is small (`agent.py:26`).
- `lookup_acm` is invoked twice per iteration (`agent.py:30-32` and `agent.py:39-41`); first result discarded.

## Wider question: data representation

`data/acm_ccs.json` is a flat list of `{path, leaf, description}` dicts (2113 entries). Built offline by `scripts/build_acm_ccs.py` from CCS 2012, descriptions LLM-generated and cached.

`lookup_acm` does substring search over `path + description`. The hierarchy lives implicitly in the `→`-separated `path` string. Cross-links (the SKOS `relatedConcept` axis CCS uses) are absent.

Open question: is "flat list of dicts, substring-searched" the right representation for an LLM-driven classification loop? Possible alternative shapes (sketch, not picks):

- **Tree-shaped JSON.** Nested `{path, children, description}`. Natural for browse/expand protocols. Trades disk size + parse cost for hierarchy clarity.
- **Graph.** Nodes + parent-of + related-to edges. Surfaces CCS cross-links the current dump throws away.
- **Prompt-embedded slice.** Top-level CCS in the system prompt; tool only fetches subtree details. Trades context length for fewer tool calls.
- **Embedding index.** Vector search over node descriptions; tool returns top-k by semantic similarity instead of substring. Adds an offline embedding step + a runtime vector store.
- **Hybrid.** Substring search for keyword discovery + path-based fetch for verification & description retrieval.

Each interacts differently with the agent–tool protocol decision. They are not independent.

## Constraints that hold

- Offline prep stays offline; runtime never rebuilds the data.
- Proxy is the only allowed network egress at runtime.
- Deterministic data file (committed); `data/acm_ccs.json` exists today and other agents depend on its presence in `data/_ccs_descriptions_cache.json`.
- Reviewer agent's tool-call pattern (`write_review`) is the existing in-repo precedent for structured commit channels.

## Open questions

- What is the agent–tool protocol? Discovery / verify / browse-tree / hybrid?
- Should final classification commit via a tool call (e.g. `submit_classification`)?
- Does the data file's shape need to change, or only the access surface?
- Restore spec §4.1's keyword-extraction phase + `keywords` audit block, or drop the spec requirement?
- Is the `description` text generated offline still the right grounding, or should it be regenerated under the new representation?
- Loop budget — function of protocol choice; revisit after.
- Test strategy — current unit tests mocked the LLM; how to test agent behaviour without the live proxy on every run?

## Out of scope here

- Picking an option.
- Implementation.
- Other Wave-1 agents (Profile Creation, Reviewer) — currently passing; revisit only if data representation change cascades.
