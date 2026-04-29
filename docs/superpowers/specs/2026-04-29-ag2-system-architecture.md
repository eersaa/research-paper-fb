# AG2 pipeline — system architecture (as built)

Status: implemented (2026-04-29). Supersedes [2026-04-29-ag2-refactor-design.md](2026-04-29-ag2-refactor-design.md), which was the brainstorming draft. This document describes the system as it actually ships in `main`. Where the implementation diverged from the draft, the draft is wrong and this document is right.

The headline divergence: the draft assumed AG2 idioms (`AfterWork`, `RedundantPattern`, an LLM aggregator named "Chair") that do not exist in `ag2==0.12.1`. The implementation drops Chair entirely and runs reviewers through an inline Python fan-out inside a `FunctionTarget`. See §10 for the full surface-drift catalogue.

## 1. What this system does

Given a research-paper manuscript in markdown, produce a structured peer-review feedback report. The pipeline:

1. Classifies the manuscript against the ACM Computing Classification System (CCS).
2. Composes a board of N reviewer personas — distinct Finnish names, distinct (stance, primary_focus) pairs, ACM-grounded specialties.
3. Runs each reviewer once on the manuscript, collecting structured `Review` objects.
4. Renders a markdown report and persists a canonical `RunOutput` JSON for downstream evaluation (the Judge tool).

Domain invariants preserved from the v1 design:

- Reviewer diversity: each reviewer has a unique `(stance, primary_focus)` pair; `core_focuses` covered when `N ≥ len(core_focuses)`.
- Finnish-name uniqueness within a board.
- ACM CCS classification is the only input to persona generation that flows from upstream agents (keywords are logged but never propagate).
- Non-leakage: the manuscript body never lands in cleartext on disk; the only network egress is the configured proxy.

## 2. Architecture

A single AG2 `DefaultPattern` group chat encodes the linear leg (Classification → ProfileCreation). Reviewer fan-out happens inside the second handoff function — plain Python, sequential, isolated. There is no nested chat, no `RedundantPattern`, no LLM aggregator.

```text
UserProxyAgent (human_input_mode="NEVER";
                also tool executor for lookup_acm and sample_board)
        │
        │ initiate_group_chat(pattern, messages=manuscript, max_rounds=...)
        ▼
┌─────────────────────────┐  tool: lookup_acm  (executed by UserProxy)
│ Classification Agent    │  response_format=ClassificationResult
└─────────────────────────┘
        │ set_after_work → FunctionTarget(classify_to_profile):
        │   parses ClassificationResult
        │   writes context_variables["classification"]
        │   forwards "ACM classes: [<paths>]" to ProfileCreation
        │   target=AgentTarget(profile_creation)
        ▼
┌─────────────────────────┐  tool: sample_board  (executed by UserProxy)
│ ProfileCreation Agent   │  response_format=ProfileBoard
└─────────────────────────┘
        │ set_after_work → FunctionTarget(setup_review_board):
        │   parses ProfileBoard
        │   for profile in profiles:
        │       reviewer = build_reviewer_agent(profile)
        │       raw = reviewer.generate_reply([{role: user, content: manuscript}])
        │       reviews.append(_coerce_to_review(raw, profile.id))
        │       (on exception: SkippedReviewer(id, reason))
        │   writes context_variables["profiles"], ["board"]
        │   target=TerminateTarget()
        ▼
        (outer chat ends; pipeline.run() resumes)
        │
        ▼
   pipeline.run() reads context_variables, builds RunOutput,
   writes final_report.md and evaluations/run-<ts>/run.json
        │
        ▼
   Renderer (pure code; joins reviews ↔ profiles by reviewer_id)
        │
        ▼
   final_report.md
```

### 2.1 AG2 features in use

| Feature | Where it shows up | Notes |
| --- | --- | --- |
| `ConversableAgent` | All three LLM agents (`classification`, `profile_creation`, per-reviewer) | `llm_config` carries `response_format=PydanticModel` for structured output |
| `UserProxyAgent` | Single `user` agent — chat entry + tool executor | `human_input_mode="NEVER"`, no `llm_config` |
| `DefaultPattern` | The linear two-agent leg | `agents=[classification, profile_creation]`, `initial_agent=classification`, `user_agent=user_proxy` |
| `agent.handoffs.set_after_work(target)` | Post-turn handoff registration | Positional arg; no `target=` keyword |
| `FunctionTarget(callable)` | Wraps `classify_to_profile` and `setup_review_board` | Callable signature: `(last_message: str, context_variables: ContextVariables) -> FunctionTargetResult` |
| `FunctionTargetResult(messages=, target=)` | Return value from each handoff body | `target` is **required** (non-optional); `messages` is plural |
| `AgentTarget(agent)` | Linear advance in `classify_to_profile`'s wrapper | Constructor derives `agent_name` from `agent.name` — do not pass it explicitly |
| `TerminateTarget()` | Outer-chat termination after `setup_review_board` | Reaches `pipeline.run()` with populated `context_variables` |
| `ContextVariables` | Cross-handoff shared state (manuscript, run_id, classification, profiles, board) | Dict-like; not visible to LLMs by default |
| `initiate_group_chat(pattern, messages, max_rounds)` | Chat entrypoint | Imported from `autogen.agentchat.group.multi_agent_chat`; returns `(ChatResult, ContextVariables, last_agent)` |
| `register_for_llm` / `register_for_execution` | Tool wiring (declared on agent, executed on UserProxy) | Same UserProxy hosts execution for both tools |
| `register_hook("safeguard_llm_outputs", fn)` | Per-agent JSONL logging on classification + profile_creation | Hook receives the LLM response, returns it unmodified; we log a redacted copy as a side effect |

### 2.2 What the implementation does NOT use (despite plan-draft references)

| Plan-draft reference | Reality in 0.12.1 | Resolution |
| --- | --- | --- |
| `AfterWork(target=...)` class | Does not exist | Use `agent.handoffs.set_after_work(target)` |
| `RedundantPattern` | Does not exist | Inline Python fan-out inside `setup_review_board`; no nested chat |
| `NestedChatTarget` | Exists but unused | Not needed — fan-out is inline |
| Chair LLM aggregator | Module never created | `BoardReport` built deterministically in Python |
| `user_proxy.initiate_chat(pattern=...)` | `initiate_chat` only accepts a recipient agent | Use `initiate_group_chat(pattern, ...)` |
| `autogen.runtime_logging` (built-in) | Available but writes SQLite/JSON we couldn't redact | Custom `JsonlLogger` + `safeguard_llm_outputs` hook |

## 3. Cross-agent schemas (`paperfb/schemas.py`)

All cross-agent communication uses Pydantic models — there are no dict-based wire formats. Every model sets `model_config = ConfigDict(title="<ClassName>", extra="forbid")` for OpenAPI compliance and to work around Gemini's `additionalProperties` quirk ([AG2 issue #2348](https://github.com/ag2ai/ag2/issues/2348)).

| Model | Role | Where it appears |
| --- | --- | --- |
| `CCSMatch` | One ACM CCS lookup hit | `lookup_acm` tool return |
| `Keywords` | Extracted-from-paper + synthesised keyword lists | nested in `ClassificationResult` |
| `CCSClass` | One assigned class with weight + rationale | nested in `ClassificationResult` |
| `ClassificationResult` | Classification agent's structured output | `response_format` on classification agent |
| `ReviewerTuple` | Deterministic sampler output (id, name, specialty, axes) | `sample_board` tool return |
| `ReviewerProfile` | Reviewer persona — superset of `ReviewerTuple` plus `persona_prompt`, `profile_summary` | `response_format` on profile_creation agent (inside `ProfileBoard`) |
| `ProfileBoard` | The full N-reviewer board | profile_creation's structured output |
| `Review` | Slim review content — `reviewer_id` + three free-text aspects (strong / weak / recommended). No identity metadata | `response_format` on each reviewer agent |
| `SkippedReviewer` | Reviewer that failed (`id`, `reason`) | populated by `setup_review_board` exception handler |
| `BoardReport` | `{reviews, skipped}` | built deterministically inside `setup_review_board` |
| `RunOutput` | `{classification, profiles, board}` | assembled by `pipeline.run`; persisted to `evaluations/run-<ts>/run.json` |
| `DimensionScore`, `JudgeScore` | Wave-2 judge per-dimension Likert score (1–5) + per-dimension justification | judge LLM's expected output, validated post-call |

`ReviewerProfile` is **not** a subclass of `ReviewerTuple` (the draft showed inheritance). They are two flat models — pydantic inheritance plus `extra="forbid"` interacts awkwardly, so the field duplication is intentional.

The `Review` slim shape eliminates metadata-echo waste and hallucination risk: the reviewer agent never repeats its own name/stance/focus — those live on `ReviewerProfile` and the renderer joins them back via `reviewer_id`.

## 4. Components

### 4.1 Classification agent — `paperfb/agents/classification.py`

`build_classification_agent(llm_config, ccs_path, max_classes) -> (ConversableAgent, lookup_acm_callable)`.

- **Tool:** `lookup_acm(query, k=10) -> list[CCSMatch]` — closure-bound to `ccs_path` so the LLM never supplies it.
- **Structured output:** `response_format=ClassificationResult`.
- **System prompt outline:** two-phase loop (extract or synthesise keywords first; then drive `lookup_acm` queries; multi-token AND, word-boundary). Pick 1–`max_classes` classes; weights `High|Medium|Low`. Every emitted path must come from a `lookup_acm` result.
- **Module convention:** does *not* set `from __future__ import annotations`. AG2's `register_for_llm` introspects tool annotations through `pydantic.TypeAdapter`; stringified `ForwardRef('list[CCSMatch]')` cannot be resolved from the closure namespace. This convention also applies to `paperfb/agents/profile_creation.py`.

### 4.2 ProfileCreation agent — `paperfb/agents/profile_creation.py`

`build_profile_creation_agent(llm_config, axes, names_path, count, core_focuses, enable_secondary, seed) -> (ConversableAgent, sample_board_callable)`.

- **Tool:** `sample_board(n, classes, seed_override=None) -> list[ReviewerTuple]`. Closure-bound parameters (`stances`, `focuses`, `core_focuses`, `enable_secondary`, `names_path`) are not visible to the LLM. The LLM sees only `n`, `classes`, optional `seed_override`.
- **Structured output:** `response_format=ProfileBoard`.
- **System prompt:** axis vocabulary (stances, focuses) is spliced in verbatim from `config/axes.yaml`. Instructs the LLM to call `sample_board` exactly once and emit one full `ReviewerProfile` per returned tuple — including the `persona_prompt` (full reviewer system message) and a one-line `profile_summary` for the renderer header.
- **Persona generation strategy:** all N personas in a single LLM step via structured output. No per-tuple sub-loops.

### 4.3 Reviewer agent factory — `paperfb/agents/reviewer.py`

`build_reviewer_agent(profile: ReviewerProfile, llm_config) -> ConversableAgent`.

- Constructed inside `setup_review_board` at runtime, one per profile.
- **System message:** `profile.persona_prompt` verbatim, followed by a single appended line `"\n\nYour reviewer_id is: <id>. Use this exact value as Review.reviewer_id."` so the agent emits the correct join key without re-echoing other metadata.
- **Structured output:** `response_format=Review` (slim form). Identity metadata (name, stance, focus, specialty) lives on `ReviewerProfile` and is joined back in by the renderer.
- **No tools.** Reviewers reason only about the manuscript. ACM context is not passed — it's already baked into the persona prompt.
- **Turn limit:** `max_consecutive_auto_reply=1`.
- **Isolation:** the reviewer agent is invoked through `reviewer.generate_reply(messages=[{"role": "user", "content": manuscript}])` — a single-turn exchange entirely outside the outer chat. Each reviewer's call is its own isolated LLM context. Siblings do not see each other.

### 4.4 Handoff bodies — `paperfb/handoffs.py`

Two pure-Python functions, unit-testable without spinning up AG2. They return a small `HandoffResult` dataclass; `pipeline._wrap_handoff` adapts it into AG2's `FunctionTargetResult`.

**`classify_to_profile(agent_output, context_variables)`** — parses the full `ClassificationResult` from the agent's structured output, stashes it in `context_variables["classification"]` for the renderer + run log, and returns a curated downstream message of the form `"ACM classes: [<paths>]"`. Keywords land in `context_variables` but never enter ProfileCreation's prompt.

**`build_setup_review_board(reviewer_llm_config, build_reviewer)`** — factory that closes over the reviewer LLM config and an injectable reviewer-builder, returning the actual `setup_review_board(agent_output, context_variables)` closure. Injecting `build_reviewer` makes the closure unit-testable with a `MagicMock` reviewer factory.

The closure parses `ProfileBoard`, then for each profile:

1. Builds a fresh reviewer `ConversableAgent` via `build_reviewer(profile, llm_config)`.
2. Calls `reviewer.generate_reply(messages=[{"role": "user", "content": manuscript}])`.
3. Coerces the result through `_coerce_to_review` (a defensive helper handling JSON-string / dict / parsed-`Review` / `.content`-wrapper return shapes — AG2 0.12.1 hasn't pinned down which one `response_format` produces).
4. On any exception: appends a `SkippedReviewer(id, reason=f"{type(e).__name__}: {e}")` and continues.

After the loop it constructs `BoardReport(reviews, skipped)` deterministically (no LLM aggregation), writes `profiles`, `board`, `expected_reviewer_ids` into `context_variables`, and returns `HandoffResult(message="Review board complete.")`.

A blanket `except Exception` is intentional: a single reviewer failure must not abort the board — it becomes a `SkippedReviewer` entry, the rest of the run continues, the renderer notes the skip.

### 4.5 Pipeline runner — `paperfb/pipeline.py`

The keystone. `run(*, manuscript, cfg) -> RunOutput`:

1. Generates a UTC run-id (`run-YYYYMMDDTHHMMSSZ`) shared by the JSONL log and the `evaluations/run-<ts>/run.json` artefact for correlation.
2. Calls `_run_chat(manuscript, cfg, ts)` which builds the full AG2 setup and returns a lightweight result object exposing `.context_variables`.
3. Reads `context_variables["classification"|"profiles"|"board"]`, validates each through Pydantic, and assembles `RunOutput`.
4. Writes `final_report.md` (via the renderer) and `evaluations/run-<ts>/run.json`.

`_run_chat` itself:

1. Constructs three `llm_config` dicts (classification, profile_creation, reviewer) — all the same except for the `model` field; one `config_list` entry pointing at the proxy.
2. Builds `UserProxyAgent`, `classification_agent`, `profile_agent`.
3. Registers logging hooks (`safeguard_llm_outputs`) on classification and profile agents.
4. Wires the two tools: `lookup_acm` for classification, `sample_board` for profile_creation. Each tool is declared on the calling agent (`register_for_llm`) and executed on the user proxy (`register_for_execution`).
5. Constructs `setup_review_board` closure with `build_reviewer_agent` injected.
6. Registers the two post-turn handoffs:
   - `classification_agent.handoffs.set_after_work(FunctionTarget(_wrap_handoff(classify_to_profile, next_target=AgentTarget(profile_agent))))`
   - `profile_agent.handoffs.set_after_work(FunctionTarget(_wrap_handoff(setup_review_board, next_target=TerminateTarget())))`
7. Constructs `DefaultPattern(agents=[classification_agent, profile_agent], initial_agent=classification_agent, user_agent=user_proxy, context_variables=...)` — `context_variables` carrying `{manuscript, run_id}` is seeded here.
8. Calls `initiate_group_chat(pattern=..., messages=manuscript, max_rounds=cfg.ag2.max_rounds)`. Returns `(_ChatResult, ContextVariables, _last_agent)`; we wrap the `ContextVariables` in a small `_Result` shim so `pipeline.run()` and the unit tests' monkey-patched fakes see the same `.context_variables` interface.

`_wrap_handoff(fn, *, next_target)` is the bridge between the pure-Python `HandoffResult` returned by handoff bodies and AG2's `FunctionTargetResult`. The wrapper assigns the call-site-supplied `next_target` to every result.

`next_target` is required because `DefaultPattern` does not auto-advance after a `FunctionTarget` returns — the result must name the next speaker explicitly. (This is the gotcha that surfaced during the live test on 2026-04-29: without an explicit target the chat dies with "No next speaker selected.")

Context mutation by the handoff function (e.g. `context_variables["classification"] = ...`) happens inside the function itself; we deliberately do NOT echo it back via `FunctionTargetResult.context_variables=...` to avoid double-application.

### 4.6 Renderer — `paperfb/renderer.py`

Pure function: `render_report(run: RunOutput) -> str`. In-memory only. Joins each `Review` with its corresponding `ReviewerProfile` (via `reviewer_id` → `profile.id`) to render header + per-reviewer sections. Markdown shape:

- `# Manuscript feedback report`
- `## ACM classification` listing each `CCSClass` with its weight + rationale
- One `## Review by {profile.name} — {profile.specialty}` block per successful review, with three `### Strong aspects` / `### Weak aspects` / `### Recommended changes` subsections drawn from `Review.strong_aspects` / `Review.weak_aspects` / `Review.recommended_changes`
- `## Skipped reviewers` if `BoardReport.skipped` is non-empty

The renderer is the only place where slim `Review` content is paired with `ReviewerProfile` identity metadata. This keeps the wire schema for `Review` minimal and prevents reviewer-side metadata echo / hallucination.

### 4.7 CLI — `paperfb/main.py`

Argparse + `pipeline.run()`. Flags: positional `manuscript`, `--config`, `--axes`, `--output`, `-n/--count`. Loads `.env` via `dotenv.load_dotenv()`, reads the manuscript file, applies CLI overrides to `cfg`, invokes `pipeline.run()`, prints a one-line summary. Returns 0 on success, 2 on missing manuscript.

## 5. Configuration

`config/default.yaml` is the single source of truth. Notable keys (see the file for the full set):

- `ag2.cache_seed` — AG2 response cache key; `null` disables caching.
- `ag2.retry_on_validation_error` — Pydantic-validation retry budget (default 1; AG2 contract).
- `ag2.max_rounds` — safety bound on the outer chat turn count (default 60). Typical run is ~12 actual rounds (classification's `lookup_acm` loop + structured response + handoff + profile_creation's loop + structured response + handoff); 60 is a runaway-loop guard, not a target.
- `models.{default, classification, profile_creation, reviewer}` — pinned to OpenAI by default for `response_format` compatibility (see §5.1).
- `models.judge` — pinned to Google for cross-family bias mitigation.
- `reviewers.{count, core_focuses, secondary_focus_per_reviewer, diversity, seed}` — board composition. Defaults: N=3, core focuses `[methods, results, novelty]`, secondary focus on, strict diversity, no seed.
- `classification.max_classes` — upper bound on classes (default 5).
- `paths.{acm_ccs, finnish_names, output, logs_dir}` — file locations.

Two YAMLs in total: `config/default.yaml` (pipeline config) and `config/axes.yaml` (stance + focus vocabulary, with descriptions spliced into ProfileCreation's system prompt).

### 5.1 Model selection constraint

The course proxy forwards OpenAI-shaped requests to OpenRouter. With `api_type: "openai"`, AG2 sends a plain OpenAI `response_format` payload regardless of underlying model. A compatibility probe (`scripts/probe_proxy_structured.py`, 2026-04-29) showed:

| Model | `response_format` (Pydantic / json_schema) |
| --- | --- |
| `openai/gpt-4.1-mini` | works |
| `google/gemini-2.5-flash-lite` | works |
| `anthropic/claude-3.5-haiku` | does NOT honour — returns prose |

**Constraint:** every agent that uses `response_format=PydanticModel` (Classification, ProfileCreation, Reviewer) runs on OpenAI or Google. Judge stays on Google for cross-family bias mitigation (different family from reviewers). If a future requirement reintroduces Claude as a structured-output agent, swap that agent's transport to forced tool-calling — the probe shows tool-calling works on all three families.

AG2's native Anthropic structured-output path requires `api_type: "anthropic"` + a direct Anthropic API key + the `structured-outputs-2025-11-13` beta header. Not available through the proxy and would also bypass the non-leakage property.

## 6. Cross-cutting concerns

### 6.1 Logging — `paperfb/logging_hook.py`

JSONL log at `logs/run-<ts>.jsonl`, one event per line, UTC ISO-8601 timestamp.

`JsonlLogger.log_event(event)` automatically applies a `redact()` policy to the `content` field: any string ≥ 1024 bytes (`REDACT_THRESHOLD_BYTES`, inclusive) is replaced with `{"sha256": <hex>, "bytes": <int>}` before write. Non-string payloads pass through unchanged. The threshold is set so the manuscript trivially clears it while routine inter-agent messages (a couple of hundred bytes) do not. This is the load-bearing non-leakage guarantee.

Log surfaces in use:

- `pipeline` events at chat start (with `manuscript_bytes` byte-count, never the body) and chat end.
- `safeguard_llm_outputs` hook on `classification` and `profile_creation` agents — fires per LLM response with the full content, redacted at log-event time.

The dynamically constructed reviewer agents inside `setup_review_board` do not currently carry the hook. Reviewer responses are not logged. This is a deliberate scope choice: the manuscript-leak invariant (the load-bearing one) only requires that the manuscript itself not appear in cleartext, and reviewer output reasons about the manuscript without quoting it verbatim. If full reviewer logging becomes desirable, register the hook on `reviewer` inside the for-loop in `setup_review_board` before calling `generate_reply`.

### 6.2 Manuscript transport (non-leakage)

The manuscript travels via:

1. The initiating message of `initiate_group_chat(messages=manuscript, ...)` — into AG2's chat history (in-memory).
2. `context_variables["manuscript"]` — read inside `setup_review_board` to feed each reviewer.
3. Each `reviewer.generate_reply(messages=[{"role": "user", "content": manuscript}])` call — over the proxy.

All three are in-memory or proxy-bound. The manuscript is never:

- Written to disk by the runtime (the only on-disk artefacts are `final_report.md`, `evaluations/run-<ts>/run.json`, `logs/run-<ts>.jsonl` — the first two contain reviewer feedback only; the third applies the >1024-byte redaction).
- Logged in cleartext (redaction at `log_event` enforces this).
- Sent to any non-proxy network endpoint (the only AG2 base_url is `os.environ["BASE_URL"]`).

The acceptance test at `tests/test_acceptance_live.py` greps the log directory after a live run for a sentinel phrase from the manuscript and fails the test if it is found.

### 6.3 Error handling

| Failure mode | Behaviour |
| --- | --- |
| Classification fails (no classes, repeated tool errors, AG2 retry exhaustion) | Exception propagates; run aborts; no report written |
| ProfileCreation fails (`ProfileBoard` validation or sampler exception) | Exception propagates; run aborts |
| One reviewer fails (validation error on `Review`, exception in `generate_reply`, anything else) | Caught inside `setup_review_board`; appended to `BoardReport.skipped` with `f"{type(e).__name__}: {e}"`; loop continues |
| All reviewers fail | `BoardReport.reviews=[]`, `skipped` carries N entries; renderer shows skipped section only |
| Tool errors at runtime | `lookup_acm` raises `ValueError` on bad input; AG2 surfaces back to the calling agent which may retry within the loop budget. `sample_board` raises if `len(names) < n` (preserves Finnish-name pool invariant) |
| Pydantic validation on a structured response | AG2 retries with validator feedback once (`ag2.retry_on_validation_error: 1`); second failure raises and the agent's branch fails per the rules above |

### 6.4 Reviewer parallelism

Sequential. Each reviewer's `generate_reply` is awaited synchronously inside the for-loop in `setup_review_board`. For N=3 with proxied LLM calls of ~10–20 s each, total reviewer time is ~30–60 s. We do not wrap this in `asyncio.gather` — the sequential isolation is simpler and matches AG2's overall turn-based model.

## 7. File layout

```text
paperfb/
├── __main__.py                  # python -m paperfb
├── main.py                      # CLI; calls pipeline.run()
├── config.py                    # Config + dataclass parsers (Ag2Config, AxesConfig, …)
├── schemas.py                   # all Pydantic cross-agent + Judge models
├── pipeline.py                  # AG2 wiring + RunOutput assembly + on-disk writes
├── handoffs.py                  # classify_to_profile, build_setup_review_board, _coerce_to_review
├── renderer.py                  # render_report(run: RunOutput) -> str
├── logging_hook.py              # JsonlLogger + redact() (>1024 bytes → sha256+bytes)
├── agents/
│   ├── classification.py        # build_classification_agent
│   ├── profile_creation.py      # build_profile_creation_agent
│   └── reviewer.py              # build_reviewer_agent factory
└── tools/
    ├── acm_lookup.py            # lookup_acm (deterministic)
    └── sampler.py               # sample_board (deterministic)
scripts/
├── judge.py                     # Wave 2: consumes run.json, writes judge.json
├── build_acm_ccs.py             # offline data prep, unchanged
├── build_finnish_names.py       # offline data prep, unchanged
├── probe_ag2_api.py             # smoke probe; re-run after AG2 bumps
└── probe_proxy_structured.py    # response_format compatibility probe per model
data/
├── acm_ccs.json
└── finnish_names.json
config/
├── default.yaml
└── axes.yaml
tests/
├── test_schemas.py              # Pydantic validation, round-trip, RunOutput, JudgeScore
├── test_handoffs.py             # classify_to_profile + setup_review_board behaviour
├── test_pipeline.py             # RunOutput assembly with _run_chat patched
├── test_renderer.py             # RunOutput → markdown, profile join by reviewer_id
├── test_logging_hook.py         # redaction + JSONL writes
├── test_judge.py                # JudgeScore parsing, run.json → judge.json
├── test_main.py                 # CLI flag plumbing
├── test_config.py               # YAML → dataclass, Ag2Config presence, model-family pin
├── test_build_acm_ccs.py
├── test_build_finnish_names.py
├── test_acceptance_live.py      # @pytest.mark.slow — real proxy
└── tools/
    ├── test_acm_lookup.py
    └── test_sampler.py
```

## 8. Wave 2 — Judge

`scripts/judge.py` consumes `evaluations/run-<ts>/run.json` and writes `evaluations/run-<ts>/judge.json` alongside it.

- Reads `RunOutput`. Joins each `Review` with its matching `ReviewerProfile` via `reviewer_id` so the judge prompt sees persona context (stance, primary_focus, secondary_focus) — this is what `persona_fidelity` scores against.
- One LLM call per review using the model from `cfg.models.judge` (default Gemini Flash Lite — different family from reviewers for bias mitigation).
- `response_format` is **not** used here; the judge prompt instructs strict JSON output, which we then validate against `JudgeScore`. The model occasionally wraps the JSON in ```json fences — `scripts/judge.py` strips fences before parsing (commit `f6b7ace`).
- Bypasses AG2 entirely: `OpenAI` SDK directly against the proxy. Judge is a Wave-2 standalone tool and doesn't need chat orchestration.
- Output shape preserves the v1 contract: `{manuscript, judge_model, per_reviewer: [...], board_mean}`.

CLI:

```bash
paperfb-judge --manuscript path/to/manuscript.md --run-dir evaluations/run-<ts>
```

(`paperfb-judge` is `python -m scripts.judge` or directly `scripts/judge.py`.)

## 9. Testing strategy

**Unit tests** (~57 fast tests, all green by default):

- Pydantic schemas — round-trip, validation errors, slim `Review` shape, `RunOutput` and `JudgeScore`
- Handoffs — `classify_to_profile` (curated message excludes keywords), `setup_review_board` (happy path collects N reviews, partial-failure path appends `SkippedReviewer`, all-fail path, reply-coercion across str/dict/Review/`.content` shapes)
- Pipeline — `_run_chat` is monkey-patched to return a stub `_Result` carrying populated `context_variables`; the test asserts `RunOutput` assembly, on-disk artefacts, and skipped-reviewer propagation through `BoardReport`
- Renderer — `RunOutput` in, markdown out, profile-join by `reviewer_id`, skipped-reviewer section
- Logging hook — `redact()` boundary at 1024 bytes inclusive; `JsonlLogger` writes one line per event, applies redaction, includes UTC `ts`
- Judge — `JudgeScore` validation, persona context in user message, range checks, run.json → judge.json end-to-end
- Tools — `sample_board` deterministic invariants (diversity, name uniqueness, raise on small names pool); `lookup_acm` multi-token AND, k cap

**Live acceptance** (`@pytest.mark.slow`, deselected by default): `tests/test_acceptance_live.py` runs the full pipeline against the real proxy on `tests/fixtures/tiny_manuscript.md`. Asserts:

- `final_report.md` exists with N `## Review by ` sections
- `evaluations/run-<ts>/run.json` exists and round-trips through `RunOutput`
- ACM classes present in markdown + ≥1 class in the `RunOutput`
- For each successful review, the joined profile has a unique `(stance, primary_focus)` pair and unique Finnish name
- A sentinel phrase from the manuscript does not appear in any file under `cfg.paths.logs_dir`

Run with `BASE_URL` set: `pytest -m slow tests/test_acceptance_live.py`. Last green run: 45.23 s wall-clock against the course proxy.

## 10. AG2 0.12.1 surface notes

Surface drift the implementation had to absorb. Documented here so future readers don't go looking for the planning-stage idioms.

| Drift point | Plan-draft expected | 0.12.1 reality | Where it lives |
| --- | --- | --- | --- |
| Post-turn handoff registration | `agent.register_handoff(AfterWork(target=...))` | `agent.handoffs.set_after_work(target)` (positional) | `paperfb/pipeline.py::_run_chat` |
| Reviewer fan-out pattern | `RedundantPattern(agents, aggregator, task)` | Class does not exist | Inline Python loop in `paperfb/handoffs.py::setup_review_board` |
| Reviewer aggregation | LLM `ConversableAgent` (Chair) | No nested-pattern aggregator surface; deterministic Python build of `BoardReport` | `setup_review_board` |
| `FunctionTargetResult` shape | `message=, target=None` allowed | `messages=` (plural), `target` is required | `paperfb/pipeline.py::_wrap_handoff` |
| Linear next-speaker after FunctionTarget | DefaultPattern auto-advances to next agent | It does NOT — handoff must name `next_target` (e.g. `AgentTarget(agent)` or `TerminateTarget()`) | `paperfb/pipeline.py::_run_chat` handoff registration calls |
| Chat entrypoint | `user_proxy.initiate_chat(pattern=..., message=..., context_variables=...)` | `initiate_group_chat(pattern, messages, max_rounds)` from `autogen.agentchat.group.multi_agent_chat`; returns `(ChatResult, ContextVariables, last_agent)` | `paperfb/pipeline.py::_run_chat` |
| `AgentTarget` constructor | `AgentTarget(agent, agent_name=...)` (sig suggests both required) | `AgentTarget(agent)` only — derives `agent_name` from `agent.name` internally; passing it explicitly raises duplicate-kwarg | `paperfb/pipeline.py::_run_chat` |
| Tool annotations on closure-bound callables | `from __future__ import annotations` is fine | Stringified `ForwardRef('list[CCSClass]')` cannot be resolved by AG2's `pydantic.TypeAdapter` introspection | Convention applied in `paperfb/agents/{classification,profile_creation}.py` |
| AG2 logging | `autogen.runtime_logging.start(...)` writes a JSONL we control | Built-in logger writes SQLite/fixed JSON we couldn't redact at write time | Custom `JsonlLogger` + `safeguard_llm_outputs` per-agent hook |

`scripts/probe_ag2_api.py` documents the verified import paths for the surfaces we use; re-run after any AG2 dep bump.

## 11. Run-time invariants

A successful run produces exactly these files (relative to repo root):

- `final_report.md` (or `cfg.paths.output`) — markdown report
- `evaluations/run-<ts>/run.json` — canonical `RunOutput` artefact, consumed by Judge
- `logs/run-<ts>.jsonl` — JSONL run log, manuscript-redacted

Where `<ts>` is the same UTC timestamp `run-YYYYMMDDTHHMMSSZ` shared between the log and the evaluations directory for correlation.

Non-leakage acceptance: grepping the manuscript body verbatim against any file under `logs_dir` returns no matches.
