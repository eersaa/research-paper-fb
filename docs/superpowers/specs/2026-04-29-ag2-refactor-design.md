# AG2 framework refactor — design

Status: drafted (brainstorming). Date: 2026-04-29. Supersedes the orchestration sections of [2026-04-24-research-paper-feedback-system-design.md](2026-04-24-research-paper-feedback-system-design.md). Reviewer schema continues from [2026-04-27-merged-review-template-design.md](2026-04-27-merged-review-template-design.md).

## 1. Purpose and scope

A course requirement mandates the use of the [AG2 agent framework](https://docs.ag2.ai/). This document specifies a holistic refactor of the existing Research Paper Feedback System onto AG2, maximising native framework features and pushing program logic out of bespoke Python orchestration into AG2 patterns.

**Goals:**

- Replace the hand-rolled tool-call loops, custom `LLMClient`, and custom `orchestrator.py` with AG2-native equivalents.
- Use AG2's GroupChat Default Pattern + Redundant Pattern + UserProxyAgent + Pydantic-typed structured outputs as the orchestration substrate.
- Preserve the system's domain invariants: deterministic reviewer diversity, Finnish-name uniqueness, ACM CCS classification, non-leakage.
- Preserve the renderer (pure code) and offline data-prep scripts.

**Non-goals:**

- No change to the overall pipeline shape (Classification → Profile Creation → Reviewer board → Renderer).
- No change to the review schema (three free-text aspects: strong / weak / recommended).
- No change to the offline data-prep tools (ACM CCS, Finnish names).
- No change to the non-leakage property (proxy remains the sole network egress).
- No change to the runtime input boundary (markdown only; PDF→markdown handled outside this project).

## 2. Architecture

A single top-level GroupChat using AG2's **Default Pattern** with handoff edges encodes the linear pipeline. The user enters via a **UserProxyAgent** that doubles as the tool executor for the linear-leg agents. The reviewer board is a **nested Redundant Pattern** whose agents are constructed at runtime by a `FunctionTarget` on ProfileCreation's handoff — exactly the AG2-idiomatic point at which to materialise downstream agents from upstream structured output. Chair is the aggregator *inside* RedundantPattern (mirroring the taskmaster/evaluator role in the AG2 redundant-pattern example).

```text
UserProxyAgent (human_input_mode="NEVER";
                also serves as tool executor for lookup_acm and sample_board)
        │
        │ initiate_chat(message=manuscript_text)
        ▼
┌─────────────────────────┐  tool: lookup_acm  (executed by UserProxy)
│ Classification Agent    │  output: ClassificationResult (Pydantic)
└─────────────────────────┘
        │ AfterWork → FunctionTarget(classify_to_profile):
        │   parses ClassificationResult
        │   writes context_variables["acm_classes"]
        │   forwards a curated, classes-only message to ProfileCreation
        ▼
┌─────────────────────────┐  tool: sample_board  (executed by UserProxy)
│ ProfileCreation Agent   │  output: ProfileBoard (Pydantic)
└─────────────────────────┘
        │ AfterWork → FunctionTarget(setup_review_board):
        │   parses ProfileBoard
        │   builds N reviewer ConversableAgents from profiles
        │   constructs RedundantPattern(reviewers + Chair as aggregator)
        │   returns NestedChatTarget(redundant_pattern)
        ▼
┌────────────────────────────────────────────────────────────┐
│ RedundantPattern (nested GroupChat)                        │
│   each sibling = isolated nested chat, sees only the task  │
│   (the manuscript), mediated by extract_task_message       │
│                                                            │
│   ┌────┐  ┌────┐         ┌────┐                            │ each reviewer:
│   │ R1 │  │ R2 │   ...   │ RN │                            │   max_turns=1,
│   └────┘  └────┘         └────┘                            │   no tools,
│      │     │               │                               │   response_format=Review
│      └─────┴───────────────┘                               │
│                  ▼                                         │
│           ┌────────────┐                                   │ Chair:
│           │   Chair    │  pure aggregator; bundles N       │   response_format=BoardReport,
│           │ (aggregator)│ Reviews + classification + skipped│  no LLM reasoning beyond
│           └────────────┘                                   │   collation
└────────────────────────────────────────────────────────────┘
                  │
                  ▼
              BoardReport
                  │
                  ▼
           Renderer (pure code)
                  │
                  ▼
            final_report.md
```

### 2.1 AG2 features in use

- `UserProxyAgent` — entry point; injects the manuscript as the initiating message. Also doubles as the tool executor for `lookup_acm` and `sample_board` (`human_input_mode="NEVER"`, no `llm_config`).
- `GroupChat` + **Default Pattern** — declarative handoff edges between agents.
- `AfterWork(target=...)` — unconditional sequential handoff after an agent's turn completes.
- `FunctionTarget` + `FunctionTargetResult` — handoff transformer that parses a structured response, writes `context_variables`, and forwards a curated message *or* transitions to a different target (including a nested chat). Used twice: (a) classification → profile creation (sub-field extraction), (b) profile creation → reviewer board (runtime agent construction + handoff to nested redundant pattern).
- `NestedChatTarget` — handoff target that runs a nested GroupChat. Used to dispatch the runtime-constructed RedundantPattern.
- `ContextVariables` — hidden cross-agent state. Not visible to LLMs by default; agents read via tool parameters or templated system messages.
- **Redundant Pattern** — nested group chat for reviewer fan-out. Each sibling runs in its own nested chat, isolated from siblings and from the broader orchestration. Sequential execution under the hood. Chair is the aggregator inside this pattern.
- `response_format=PydanticModel` — every cross-agent message is a Pydantic-validated object.
- Tool registration via `@register_for_llm(...)` (on the calling agent) / `@register_for_execution(...)` (on the executor) decorators.
- AG2 logging hooks — JSONL run log replaces the custom `LLMClient` logging.

### 2.2 What disappears

- `paperfb/llm_client.py` — replaced by AG2's `llm_config` and built-in retries.
- `paperfb/orchestrator.py` — shrinks to a thin `pipeline.py` that builds agents, registers handoffs, runs the chat, and hands the resulting `BoardReport` to the renderer.
- `paperfb/agents/*/agent.py` — hand-rolled tool-call loops; AG2 owns this now.
- `paperfb/agents/reviewer/tools.py` (`write_review`) — replaced by reviewer's structured Pydantic output. Per-reviewer JSON files no longer written by the runtime pipeline.
- Manual JSON validation in `paperfb/contracts.py` — Pydantic does it.
- `asyncio.gather` reviewer fan-out — replaced by RedundantPattern (sequential within the framework's GroupChat turn-taking; see §6.4).

### 2.3 What stays

- `data/acm_ccs.json`, `data/finnish_names.json`, `config/*.yaml`, `samples/`.
- `scripts/build_acm_ccs.py`, `scripts/build_finnish_names.py`.
- The renderer (now consumes `BoardReport` directly instead of reading per-reviewer JSON files).
- The deterministic sampler logic — relocated under `paperfb/tools/sampler.py` and exposed as the `sample_board` tool.
- `lookup_acm` lookup logic — relocated under `paperfb/tools/acm_lookup.py`.
- The non-leakage property: AG2 routes through the same OpenAI-compatible proxy via `llm_config.base_url`. No additional egress.

## 3. Pydantic schemas (`paperfb/schemas.py`)

All cross-agent messages and structured tool outputs use Pydantic. This module replaces `paperfb/contracts.py`.

```python
from typing import Literal
from pydantic import BaseModel

# Classification ────────────────────────────────────────────────────

class CCSMatch(BaseModel):
    path: str
    description: str

class Keywords(BaseModel):
    extracted_from_paper: list[str]
    synthesised: list[str]

class CCSClass(BaseModel):
    path: str
    weight: Literal["High", "Medium", "Low"]
    rationale: str

class ClassificationResult(BaseModel):
    keywords: Keywords
    classes: list[CCSClass]

# Profile Creation ──────────────────────────────────────────────────

class ReviewerTuple(BaseModel):
    id: str            # "r1"…"rN"
    name: str          # Finnish given name, unique within board
    specialty: str     # ACM class path
    stance: str
    primary_focus: str
    secondary_focus: str | None

class ReviewerProfile(ReviewerTuple):
    persona_prompt: str   # full system_message for that reviewer
    profile_summary: str  # one-line blurb for renderer header

class ProfileBoard(BaseModel):
    reviewers: list[ReviewerProfile]

# Reviewer ──────────────────────────────────────────────────────────

class Review(BaseModel):
    reviewer_id: str
    reviewer_name: str
    specialty: str
    stance: str
    primary_focus: str
    secondary_focus: str | None
    profile_summary: str
    strong_aspects: str
    weak_aspects: str
    recommended_changes: str

# Aggregation ───────────────────────────────────────────────────────

class SkippedReviewer(BaseModel):
    id: str
    reason: str

class BoardReport(BaseModel):
    classification: ClassificationResult
    reviews: list[Review]
    skipped: list[SkippedReviewer]
```

## 4. Per-agent specifications

### 4.1 Classification Agent

- **Module:** `paperfb/agents/classification.py`
- **Builder:** `build_classification_agent(llm_config, ccs_path) -> ConversableAgent`
- **System prompt outline:** ACM CCS rules (prefer leaf nodes, 2–5 classes with High/Medium/Low weights), two-phase loop (extract paper-stated or synthesised keywords first, then drive `lookup_acm` queries), keywords are logged but do not propagate downstream.
- **Tool:** `lookup_acm(query: str, k: int = 10) -> list[CCSMatch]`. Multiple calls allowed within the loop.
- **Structured output:** `response_format=ClassificationResult`.
- **Handoff:** `AfterWork(target=FunctionTarget(classify_to_profile))`. The function extracts `result.classes`, writes them to `context_variables["acm_classes"]`, and forwards a curated message (e.g. `"ACM classes: [<paths>]"`) to ProfileCreation. `result.keywords` stays in the chat transcript and the run log but does not enter ProfileCreation's prompt.

### 4.2 ProfileCreation Agent

- **Module:** `paperfb/agents/profile_creation.py`
- **Builder:** `build_profile_creation_agent(llm_config, axes, names_path, count, core_focuses, seed) -> ConversableAgent`
- **System prompt outline:** explains the persona formula (`name + specialty + stance + primary_focus + secondary_focus`), splices in the axis-vocabulary descriptions verbatim from `config/axes.yaml`, instructs the agent to call `sample_board` exactly once and then emit `ProfileBoard` with one `ReviewerProfile` per sampled tuple.
- **Tool:** `sample_board(n, classes, stances, focuses, core_focuses, seed) -> list[ReviewerTuple]` — deterministic Python, returns Pydantic models. Wraps the existing sampler under `paperfb/tools/sampler.py`.
- **Persona generation strategy:** single LLM step producing all N personas at once via structured output. Each `ReviewerProfile.persona_prompt` is a full system message — embeds the assigned Finnish given name, specialty grounding, stance description, primary/secondary focus rubric language. (Per-tuple sub-loops are YAGNI.)
- **Structured output:** `response_format=ProfileBoard`.
- **Handoff:** `AfterWork(target=FunctionTarget(setup_review_board))`. The function parses `ProfileBoard`, builds N reviewer `ConversableAgent`s via `build_reviewer_agent` (§4.3), constructs a `RedundantPattern(agents=reviewers, aggregator=chair, task=context_variables["manuscript"])`, and returns `FunctionTargetResult(target=NestedChatTarget(redundant_pattern))`. Runtime agent construction happens here, in plain Python, at the canonical AG2 boundary for "build downstream agents from upstream structured output." See §4.4 for the function body.

### 4.3 Reviewer Agent (factory; instantiated by `setup_review_board`)

- **Factory:** `build_reviewer_agent(profile: ReviewerProfile, llm_config) -> ConversableAgent`.
- **Constructed by:** `setup_review_board` FunctionTarget (§4.4) at runtime, one per `ReviewerProfile`.
- **System prompt:** `profile.persona_prompt` verbatim. ProfileCreation has already embedded the assigned name, ACM specialty, stance description, primary/secondary focus rubric language. Nothing else is layered on.
- **Input received per nested chat:** the manuscript text as the redundant-task message. That is all. ACM classification context does **not** flow to reviewers — the specialty (an ACM class path) is already part of the persona prompt.
- **No tools.** Pydantic structured output replaces the previous `write_review` tool.
- **Structured output:** `response_format=Review`.
- **Turn limit:** `max_consecutive_auto_reply=1`. Reviewers respond once and are done.
- **Isolation:** RedundantPattern places each reviewer in its own nested chat. Siblings cannot see each other; the broader orchestration transcript is hidden. Only the manuscript reaches them, mediated by `extract_task_message`.

### 4.4 `setup_review_board` FunctionTarget + Chair (aggregator)

Runtime reviewer construction lives in a `FunctionTarget` on ProfileCreation's handoff. This is the AG2-idiomatic location for "materialise downstream agents from upstream structured output" — analogous to how the [redundant-pattern example](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/pattern-cookbook/redundant/) builds its agent queue at config time, only here the inputs come from a prior agent's response. No tool dispatch, no extra LLM call.

```python
def setup_review_board(
    agent_output: str,
    context_variables: ContextVariables,
) -> FunctionTargetResult:
    board = ProfileBoard.model_validate_json(agent_output)
    reviewers = [
        build_reviewer_agent(p, reviewer_llm_config)
        for p in board.reviewers
    ]
    chair = build_chair(chair_llm_config)  # aggregator
    pattern = RedundantPattern(
        agents=reviewers,
        aggregator=chair,
        task=context_variables["manuscript"],
        # extract_task_message: each reviewer sees only the manuscript
    )
    context_variables["profiles"] = board.model_dump()  # for renderer header
    return FunctionTargetResult(
        target=NestedChatTarget(pattern.as_nested_chat()),
        context_variables=context_variables,
    )
```

(Final API names — `RedundantPattern` constructor signature, `as_nested_chat()` form — to be confirmed against the AG2 version pinned at implementation time. The shape is fixed; the surface may shift.)

**Chair Agent (aggregator inside RedundantPattern):**

- **Module:** `paperfb/agents/chair.py`
- **Builder:** `build_chair(llm_config) -> ConversableAgent`
- **Role:** receives the `Review` objects emitted by the redundant siblings, plus the upstream `ClassificationResult` (read from `context_variables["acm_classes"]`) and any `SkippedReviewer` entries (read from `context_variables["skipped"]`). Emits `BoardReport` as its structured response. No reasoning, no synthesis — collation only.
- **System prompt:** one paragraph instructing Chair to assemble the per-reviewer reviews verbatim into a `BoardReport`, preserving every field; no editing, no merging, no commentary.
- **Structured output:** `response_format=BoardReport`.
- **Why an LLM agent and not a deterministic callable.** AG2's documented RedundantPattern uses an LLM `ConversableAgent` aggregator (e.g. `evaluator_agent` calling `evaluate_and_select`). Following that idiom keeps us inside the framework's documented surface. Cost is one cheap LLM call. If a future AG2 version exposes a deterministic-callable aggregator hook on `RedundantPattern`, Chair can be swapped for it without changing any other agent.

## 5. Configuration

`config/default.yaml` is updated. Default model changes from Claude Haiku to GPT-4.1-mini for all structured-output agents — see §5.1 for the empirical reason. Two new keys (`ag2.*`):

```yaml
ag2:
  cache_seed: null              # AG2 caches LLM responses by seed; null disables
  retry_on_validation_error: 1  # retries on Pydantic validation failure

models:
  default: openai/gpt-4.1-mini
  classification: openai/gpt-4.1-mini
  profile_creation: openai/gpt-4.1-mini
  reviewer: openai/gpt-4.1-mini
  judge: google/gemini-2.5-flash-lite     # different family from reviewer for bias mitigation
```

`llm_config` is built once in `paperfb/pipeline.py` from `Config`:

```python
def build_llm_config(cfg: Config) -> dict:
    return {
        "config_list": [{
            "model": cfg.models.default,
            "base_url": os.environ["BASE_URL"],
            "api_key": "unused",
            "api_type": "openai",
        }],
        "temperature": 0.0,
        "cache_seed": cfg.ag2.cache_seed,
    }
```

Per-agent overrides swap the `model` field only (Classification, ProfileCreation, Reviewer, Chair, Judge each pin their configured model).

### 5.1 Model selection constraint (empirical)

The course proxy forwards `OpenAI /chat/completions` calls to OpenRouter. With `api_type: "openai"` AG2 sends a plain OpenAI-shaped `response_format` payload regardless of the underlying model. A compatibility probe ([_test_proxy_structured.py](../../../scripts/probe_proxy_structured.py), 2026-04-29) shows:

| Model | `response_format` (Pydantic / json_schema) | tool-calling | json_object |
| --- | --- | --- | --- |
| `openai/gpt-4.1-mini` | works | works | works |
| `google/gemini-2.5-flash-lite` | works | flaky (one 504 in test) | works |
| `anthropic/claude-3.5-haiku` | **does not honour — returns prose** | works | works |

AG2's native Anthropic structured-output support requires `api_type: "anthropic"` with a direct Anthropic API key + the `structured-outputs-2025-11-13` beta header — not available through this proxy and would also bypass the non-leakage property (§6.7).

**Constraint adopted:** every agent that uses `response_format=PydanticModel` (Classification, ProfileCreation, Reviewer, Chair) must run on a model whose proxy path honours `response_format`. Per the matrix above, that is OpenAI or Google. Judge stays on Google (Gemini Flash Lite) — different family from reviewer for bias mitigation, with structured output supported through the proxy.

If a future requirement re-introduces Claude as a structured-output agent, two escape hatches exist:

- **Tool-calling** as the structured-output transport for that agent only (forced function call as the response shape; works for all three models per the probe). Per-agent transport split.
- **AG2 beta `Agent` with `response_schema`** ([AG2 beta structured outputs](https://docs.ag2.ai/latest/docs/beta/structured_output/)). Includes a `PromptedSchema` fallback that injects the schema into the system prompt for providers without native support, then validates. Beta agents bridge into our GroupChat patterns via `as_conversable()` ([AG2 Beta blog](https://docs.ag2.ai/latest/docs/blog/2026/03/16/AG2-Beta/)). **Not adopted for v1** because (a) the beta API is positioned as "especially strong for single-agent applications" while we have a 5-agent multi-pattern setup; (b) `PromptedSchema` is mechanically equivalent to our `json_object`-with-prompt-injected-schema probe path; (c) stacking beta + `as_conversable()` + Default Pattern + RedundantPattern + FunctionTarget is unverified. Re-evaluate when AG2 beta becomes stable / 1.0.

## 6. Cross-cutting concerns

### 6.1 User entry

```python
user_proxy = UserProxyAgent(
    name="user",
    human_input_mode="NEVER",
    code_execution_config=False,
)
result = user_proxy.initiate_chat(group_chat_manager, message=manuscript_text)
board_report: BoardReport = result.summary  # or extracted from chat history
```

The manuscript is the initiating message. It travels only through the proxied conversation; non-leakage preserved.

### 6.2 Handoff topology

Default Pattern handoffs encoded on each agent at construction time:

| From | Handoff | To | Notes |
| --- | --- | --- | --- |
| (UserProxy entry) | `initiate_chat(message=manuscript_text)` | Classification | UserProxy also stashes the manuscript in `context_variables["manuscript"]` for downstream `FunctionTarget`s to read. |
| Classification | `AfterWork(target=FunctionTarget(classify_to_profile))` | ProfileCreation | Function extracts `result.classes`, writes `context_variables["acm_classes"]`, forwards a curated message. Keywords stay in transcript only. |
| ProfileCreation | `AfterWork(target=FunctionTarget(setup_review_board))` | NestedChat (RedundantPattern) | Function builds N reviewer agents from `ProfileBoard`, constructs RedundantPattern with Chair as aggregator, returns `NestedChatTarget`. See §4.4. |
| Reviewer Ri | implicit (RedundantPattern siblings → aggregator) | Chair | Pattern-internal; not a Default-Pattern handoff. |
| Chair | (no handoff — terminal node) | — | Chair's structured `BoardReport` response terminates the chat. |

`AfterWork` is unconditional: fires after the source agent's full turn (including any tool calls and the final structured response) completes. We do not use `OnCondition` since none of these handoffs are conditional on response content — Pydantic validation already gates "did the agent succeed."

### 6.3 Error handling

- **Classification fails** (no classes returned, repeated tool errors, exhausted retries): abort run, non-zero exit, no report written.
- **ProfileCreation fails** (validation failure on `ProfileBoard`, sampler exception): abort run.
- **Reviewer fails** (validation failure on `Review`, exception inside the sibling chat): caught at the sibling level, recorded as `SkippedReviewer(id=..., reason=...)`, run continues. Renderer notes the skip.
- **Pydantic validation error on a structured response:** AG2 retry-with-validator-feedback (1 retry, configured via `ag2.retry_on_validation_error`); on second failure the agent's branch fails per the rules above.
- **Tool errors:** `lookup_acm` raises `ValueError` on bad input; AG2 surfaces it back to the calling agent which may retry. `sample_board` raises if `len(names) < n` (preserves existing invariant from `data/finnish_names.json`).

### 6.4 Reviewer parallelism

RedundantPattern is implemented on top of GroupChat, which is turn-based. Reviewers therefore execute **sequentially** within the pattern, but each sibling sees an isolated context (no cross-talk; the value of RedundantPattern). For N=3 default, sequential reviewer execution is acceptable: ~10–20 s per reviewer × 3 ≈ ~30–60 s total, in line with current run times. We do **not** wrap RedundantPattern with `asyncio.gather`; staying inside the framework's pattern is a course-story priority.

### 6.5 Logging

Register an AG2 logging hook that writes JSONL to `logs/run-<ts>.jsonl`. Each line records: timestamp, agent name, role, content (or content-hash for manuscript-bearing messages), tool calls, and `usage` (tokens, cost). Replaces `LLMClient` logging. Used by Wave 2 cost reporting.

### 6.6 Renderer

`paperfb/renderer.py` becomes:

```python
def render_report(board: BoardReport) -> str: ...
```

Reads the in-memory `BoardReport` directly. Produces markdown with the same shape as today: header (assigned ACM classes), per-reviewer sections (`## Review by {name} — {specialty}`), three labelled subsections (Strong / Weak / Recommended), skipped-reviewer note if any.

The runtime no longer writes per-reviewer JSON files. The renderer additionally writes a serialised `BoardReport` to `evaluations/run-<ts>/board.json` for the Judge to consume in Wave 2.

### 6.7 Manuscript transport

Passed as the `initiate_chat(message=...)` argument from `UserProxyAgent`. Travels with the conversation through the proxy. Never written to disk by the runtime, never logged in cleartext: the JSONL logger records a SHA-256 content-hash and byte length in place of the body for any message whose payload exceeds 1024 bytes (the manuscript trivially clears this threshold; routine inter-agent messages do not). Non-leakage assertion in the acceptance test verifies this.

## 7. File layout (post-refactor)

```text
paperfb/
├── __main__.py                  # `python -m paperfb`
├── main.py                      # CLI; calls pipeline.run()
├── config.py                    # unchanged
├── schemas.py                   # NEW; replaces contracts.py — all Pydantic models
├── pipeline.py                  # NEW; ~80 lines: builds agents + handoffs, runs chat
├── renderer.py                  # signature change: render_report(board: BoardReport)
├── agents/
│   ├── classification.py        # build_classification_agent(...)
│   ├── profile_creation.py      # build_profile_creation_agent(...)
│   ├── reviewer.py              # build_reviewer_agent(profile, ...) factory
│   └── chair.py                 # build_chair(...) — aggregator inside RedundantPattern
├── handoffs.py                  # NEW; classify_to_profile, setup_review_board
│                                # FunctionTarget bodies
└── tools/
    ├── acm_lookup.py            # lookup_acm tool fn
    └── sampler.py               # sample_board tool fn (deterministic)
scripts/
├── judge.py                     # rewritten: consumes BoardReport JSON file
├── build_acm_ccs.py             # unchanged
└── build_finnish_names.py       # unchanged
```

`paperfb/agents/{classification,profile_creation,reviewer}/` directories are flattened to single modules — each agent's hand-rolled loop disappears, prompts are inline strings within the builder, tools live under `paperfb/tools/` (shared module rather than per-agent). The agent-private import-isolation rule from the v1 design is retired: agents now communicate exclusively through Pydantic models in `schemas.py`, so per-agent subpackages add no isolation value.

## 8. Wave 2 — Judge (independent tool, deferred design pass)

Judge becomes an AG2 setup:

- `JudgeAgent` (`response_format=JudgeScore`) iterates per `Review` in a `BoardReport` JSON file.
- `scripts/judge.py` reads `evaluations/run-<ts>/board.json` produced by the renderer, runs the `JudgeAgent` once per review, writes `evaluations/run-<ts>/judge.json` with per-dimension scores + per-reviewer mean + board mean (current shape preserved).
- Same Pydantic discipline: `JudgeScore` defined in `paperfb/schemas.py`.
- Judge model defaults to a different family than reviewers (current bias-mitigation rule preserved).

Detailed `JudgeScore` schema and prompt deferred to its own design pass.

## 9. Testing strategy

- **Unit:**
  - `sample_board` tool: diversity invariants — `(stance, primary_focus)` unique across reviewers; core focuses covered when `N >= len(core_focuses)`; Finnish names unique.
  - `lookup_acm` tool: deterministic ranking, multi-token AND with parent-path bonus (preserves existing behaviour).
  - Renderer: pure function, golden-output test on fixture `BoardReport`.
  - Pydantic schemas: validation error cases (bad weight value, missing fields).
- **Integration with stubbed LLM:**
  - Pipeline end-to-end with AG2's mocked-LLM facilities (or monkeypatched OpenAI client).
  - Asserts the handoff sequence (Classification → ProfileCreation → Redundant → Chair).
  - Asserts RedundantPattern emits exactly N reviews when all succeed.
  - Asserts skipped-reviewer path: stub one reviewer to raise; assert `BoardReport.skipped` length 1, `BoardReport.reviews` length N-1.
- **Acceptance (`@pytest.mark.slow`):**
  - Live proxy end-to-end on a tiny manuscript fixture.
  - Asserts: `final_report.md` exists, per-reviewer sections match N, ACM classes present, distinct stances/focuses per diversity rule, distinct Finnish names, no manuscript leakage to stdout or logs.

Existing test files to be migrated:

- `tests/test_orchestrator.py` → `tests/test_pipeline.py` (rewritten against AG2 mocked LLM).
- `tests/test_llm_client.py` → deleted (no `LLMClient` to test).
- `tests/test_contracts.py` → `tests/test_schemas.py` (Pydantic validation cases).
- `tests/agents/{classification,profile_creation,reviewer}/test_agent.py` → deleted; replaced by integration tests on the new pipeline. Tool-level tests under `tests/tools/test_acm_lookup.py` and `tests/tools/test_sampler.py` remain.
- `tests/test_renderer.py` → updated to `BoardReport` input shape.
- `tests/test_judge.py` → updated to consume `evaluations/run-<ts>/board.json` instead of per-reviewer files.
- `tests/test_acceptance_live.py` → updated assertions (no per-reviewer JSON files).

## 10. Migration plan (high-level; a detailed plan is the next deliverable via `writing-plans`)

The refactor is large enough that an in-place rewrite without a working pipeline at intermediate steps is acceptable: we have no production users, no compatibility consumers, and the existing v1 pipeline is checked in at HEAD as the reference. The implementation plan (separate document) will sequence the refactor as:

1. Add AG2 dependency, scaffold `paperfb/schemas.py` with all Pydantic models and tests for them.
2. Move `sample_board` and `lookup_acm` into `paperfb/tools/` with Pydantic-typed I/O.
3. Build Classification agent (module + builder + handoff stub) + integration test against mocked AG2 LLM. (No need to re-verify `response_format` per model — already verified in §5.1.)
4. Build ProfileCreation agent + integration test.
5. Build reviewer factory + Chair aggregator + `setup_review_board` FunctionTarget that constructs the RedundantPattern from `ProfileBoard` and returns a `NestedChatTarget` + integration test.
6. Wire the full pipeline in `paperfb/pipeline.py` with `UserProxyAgent` entry; replace `paperfb/orchestrator.py` and `paperfb/llm_client.py`.
7. Update renderer to `BoardReport`; delete `reviews/*.json` runtime path.
8. Update CLI in `paperfb/main.py`.
9. Update Judge to consume `BoardReport` JSON file.
10. Delete obsolete files; update README and PLAN.md.
11. Run live acceptance test; verify final report.

## 11. Open questions

(none blocking design; all items below are resolved or downgraded to smoke-tests)

Resolved during this design pass:

- **`response_format` across course models.** Empirically verified ([_test_proxy_structured.py](../../../scripts/probe_proxy_structured.py), 2026-04-29) against the course proxy: OpenAI (`gpt-4.1-mini`) and Google (`gemini-2.5-flash-lite`) honour `response_format=PydanticModel`; Anthropic Claude 3.5 Haiku does NOT (returns prose). AG2's native Anthropic structured-output path requires direct Anthropic API access (incompatible with this proxy and with the non-leakage property). Therefore Classification, ProfileCreation, Reviewer, and Chair are pinned to OpenAI/Google models. See §5.1 for the matrix and the constraint. Schema portability rules we adopt: every Pydantic root model defines a `title`, every model sets `model_config = {"extra": "forbid"}` (works around [Gemini's `additionalProperties` issue](https://github.com/ag2ai/ag2/issues/2348)), schemas stay OpenAPI-compliant.
- **Carryover shape between handoffs.** AG2 supports sub-field extraction via `FunctionTarget` + `FunctionTargetResult`. The handoff function receives the previous agent's output as a string, can parse it into a Pydantic model, write to shared `ContextVariables` (hidden from LLMs), and emit a curated `message` for the next agent — or transition to a `NestedChatTarget`. Used twice: classify→profile (sub-field extraction) and profile→reviewer-board (runtime agent construction). See §4.4 and §6.2.
- **RedundantPattern aggregator shape.** Per AG2 docs, the aggregator in the documented pattern is a `ConversableAgent`. Chair adopts that role: a thin LLM agent with `response_format=BoardReport` that collates verbatim. See §4.4.
- **Runtime reviewer instantiation.** Lives in a `FunctionTarget` (`setup_review_board`) on ProfileCreation's handoff, which builds N reviewer `ConversableAgent`s from the parsed `ProfileBoard` and returns a `NestedChatTarget` for the constructed RedundantPattern. No tool dispatch and no extra LLM call needed for setup. See §4.4.
- **Reviewer isolation.** RedundantPattern places each sibling in its own nested chat seeing only the task message (the manuscript), mediated by `extract_task_message`. ACM context does not flow to reviewers — specialty is already in the persona prompt. See §4.3.
- **Handoff timing.** `AfterWork` and `OnCondition` both fire after the source agent's full turn (including tool calls and final structured response) completes. We use `AfterWork` for unconditional sequential handoffs since none of our edges depend on response content. See §6.2.
