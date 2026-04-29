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

A single top-level GroupChat using AG2's **Default Pattern** with handoff edges encodes the linear pipeline. The user enters via a **UserProxyAgent** whose initiating message is the manuscript text. The Chair Agent owns the reviewer board: it consumes `ProfileBoard`, instantiates the reviewer agents, dispatches them via a **nested Redundant Pattern**, and assembles the `BoardReport`. A paired **Tool Executor Agent** runs Chair's deterministic tools.

```text
UserProxyAgent (human_input_mode="NEVER")
        │
        │ initiate_chat(message=manuscript_text)
        ▼
┌─────────────────────────┐  tool: lookup_acm
│ Classification Agent    │  output: ClassificationResult (Pydantic)
└─────────────────────────┘
        │ AfterWork → FunctionTarget(classify_to_profile):
        │   writes context_variables["acm_classes"]
        │   forwards a curated message (no keywords) to ProfileCreation
        ▼
┌─────────────────────────┐  tool: sample_board (deterministic)
│ ProfileCreation Agent   │  output: ProfileBoard (Pydantic)
└─────────────────────────┘
        │ AfterWork → AgentTarget(Chair)
        │   ProfileBoard travels in chat; manuscript still in context
        ▼
┌──────────────────────────────────────────────────────────────┐
│ Chair Agent (LLM, decider)                                   │
│   tools (executed by Tool Executor Agent):                   │
│     1. convene_review_board(profiles, manuscript)            │
│        Python: builds N reviewer ConversableAgents,          │
│        runs nested RedundantPattern, returns list[Review]    │
│     2. assemble_board_report(reviews, classification)        │
│        Python: bundles into BoardReport                      │
└──────────────────────────────────────────────────────────────┘
                         │
                         ▼ (inside convene_review_board)
            ┌────────────────────────────────────────┐
            │ RedundantPattern (nested GroupChat)    │
            │   each sibling = isolated nested chat, │
            │   sees only the task message           │
            │   (manuscript + classification ctx)    │
            │  ┌────┐  ┌────┐         ┌────┐         │
            │  │ R1 │  │ R2 │   ...   │ RN │         │  each: max_turns=1,
            │  └────┘  └────┘         └────┘         │         no tools,
            │     │      │              │            │         response_format=Review
            │     └──────┴──────────────┘            │
            │                ▼                       │
            │     [list[Review] returned to Chair]   │
            └────────────────────────────────────────┘
                         │
                         ▼ (Chair's final structured response)
                    BoardReport
                         │
                         ▼
                  Renderer (pure code)
                         │
                         ▼
                   final_report.md
```

### 2.1 AG2 features in use

- `UserProxyAgent` — entry point; injects the manuscript as the initiating message.
- `GroupChat` + **Default Pattern** — declarative handoff edges between agents.
- `AfterWork(target=...)` — unconditional sequential handoff after an agent's turn completes.
- `FunctionTarget` + `FunctionTargetResult` — handoff transformer that extracts sub-fields from a structured response and writes `context_variables` for downstream agents.
- `ContextVariables` — hidden cross-agent state. Not visible to LLMs by default; agents read via tool parameters or templated system messages.
- **Redundant Pattern** — nested group chat for reviewer fan-out. Each sibling runs in its own nested chat, isolated from siblings and from the broader orchestration. Sequential execution under the hood.
- **Tool Executor Agent** — paired `UserProxyAgent` with `human_input_mode="NEVER"` and no `llm_config`; registered to *execute* Chair's tools while Chair *selects* them via LLM. Splits `register_for_llm` (Chair) from `register_for_execution` (Executor).
- `response_format=PydanticModel` — every cross-agent message is a Pydantic-validated object.
- Tool registration via `@register_for_llm(...)` / `@register_for_execution(...)` decorators.
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
- **Handoff:** `AfterWork(target=AgentTarget(chair))`. The serialised `ProfileBoard` enters Chair's chat history; the manuscript is also still in context. Chair picks them up from there.

### 4.3 Reviewer Agent (factory; instantiated by Chair's tool)

- **Factory:** `build_reviewer_agent(profile: ReviewerProfile, llm_config) -> ConversableAgent`.
- **Constructed by:** `convene_review_board` tool (§4.4) at runtime, one per `ReviewerProfile`.
- **System prompt:** `profile.persona_prompt` verbatim. No additional layering — stance/focus rubric language is already baked in by ProfileCreation.
- **Input received per nested chat:** the manuscript text as the redundant-task message; `context_variables["acm_classes"]` available via tool params or templated system message if a reviewer needs ACM context.
- **No tools.** Pydantic structured output replaces the previous `write_review` tool.
- **Structured output:** `response_format=Review`.
- **Turn limit:** `max_consecutive_auto_reply=1`. Reviewers respond once and are done.
- **Isolation:** RedundantPattern places each reviewer in its own nested chat. Siblings cannot see each other; the broader orchestration transcript is hidden. Only the task message reaches them, mediated by `extract_task_message`.

### 4.4 Chair Agent + Tool Executor Agent

Chair owns reviewer-board lifecycle: it consumes `ProfileBoard`, dispatches reviewers, and assembles the final `BoardReport`. Its work is pure orchestration of two deterministic tools, executed by a paired Tool Executor Agent.

- **Module:** `paperfb/agents/chair.py`
- **Chair (LLM decider):** `ConversableAgent` with a short system message instructing it to (a) call `convene_review_board` once with the `ProfileBoard` from chat history and the manuscript from `context_variables`, then (b) call `assemble_board_report` with the resulting reviews and the classification, then (c) emit the resulting `BoardReport` as its structured response. Two LLM calls total (one per tool selection); no reasoning beyond tool dispatch.
- **Tool Executor (no LLM):** `UserProxyAgent(name="executor", human_input_mode="NEVER", code_execution_config=False)` — executes Chair's tools deterministically. No `llm_config`. Both tools are registered with `@register_for_llm(caller=chair)` and `@register_for_execution(executor=executor)`.
- **Tool 1 — `convene_review_board(profiles: list[ReviewerProfile], manuscript: str) -> list[Review]`:**
  - Builds N reviewer `ConversableAgent`s via `build_reviewer_agent` (§4.3).
  - Constructs a `RedundantPattern` over them with the manuscript + `acm_classes` from `context_variables` as the task.
  - Runs the pattern (sequential under the hood); collects each sibling's `Review`.
  - Returns `list[Review]`. Reviewer failures are caught here and surfaced as `SkippedReviewer` entries in `context_variables["skipped"]`.
- **Tool 2 — `assemble_board_report(reviews: list[Review], classification: ClassificationResult) -> BoardReport`:**
  - Pure bundling. Reads `context_variables["skipped"]`, combines with `reviews` and `classification` into a `BoardReport`. No reasoning.
- **Chair structured output:** `response_format=BoardReport`. After tool 2 returns, Chair emits the bundled object.
- **Why both an LLM Chair and a non-LLM Executor.** Pure tool-executor patterns (executor only, no Chair) require a fixed sequence; with a thin LLM Chair, the framework's tool-selection idiom is on display and we get per-tool retry behaviour for free. Cost is two cheap LLM calls. If profiling shows this matters, Chair can be replaced with a deterministic sequential dispatcher in implementation.

## 5. Configuration

`config/default.yaml` keeps its existing shape (already documented in the v1 design). Two additions:

```yaml
ag2:
  cache_seed: null              # AG2 caches LLM responses by seed; null disables
  retry_on_validation_error: 1  # retries on Pydantic validation failure
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

Per-agent overrides swap the `model` field only (Classification, ProfileCreation, Reviewer, Chair, Judge each pin their configured course-recommended model).

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
| Classification | `AfterWork(target=FunctionTarget(classify_to_profile))` | ProfileCreation | Function extracts `result.classes`, writes `context_variables["acm_classes"]` and `context_variables["manuscript"]`, forwards a curated message. Keywords stay in transcript. |
| ProfileCreation | `AfterWork(target=AgentTarget(chair))` | Chair | `ProfileBoard` enters Chair's chat history. |
| Chair | (no handoff — terminal node) | — | Chair's structured `BoardReport` response ends the GroupChat. |

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
│   └── chair.py                 # build_chair(...) + build_tool_executor(...);
│                                # convene_review_board, assemble_board_report
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
3. Build Classification agent (module + builder + handoff stub) + integration test against mocked AG2 LLM.
4. Build ProfileCreation agent + integration test.
5. Build reviewer factory + Chair (LLM decider) + Tool Executor agent + `convene_review_board` and `assemble_board_report` tools (the latter wraps RedundantPattern construction) + integration test.
6. Wire the full pipeline in `paperfb/pipeline.py` with `UserProxyAgent` entry; replace `paperfb/orchestrator.py` and `paperfb/llm_client.py`.
7. Update renderer to `BoardReport`; delete `reviews/*.json` runtime path.
8. Update CLI in `paperfb/main.py`.
9. Update Judge to consume `BoardReport` JSON file.
10. Delete obsolete files; update README and PLAN.md.
11. Run live acceptance test; verify final report.

## 11. Open questions

- **AG2 `response_format` semantics across providers.** Expected to work per AG2 docs for the OpenAI-compatible path through the course proxy, including Claude Haiku, GPT-4.1-mini, Gemini Flash. Verify smoke-test in Step 3 of the migration plan; if a model fails, fall back to AG2's function-calling-based JSON schema adapter for that model only. No design impact.

Resolved during this design pass:

- **Carryover shape between handoffs.** AG2 supports sub-field extraction via `FunctionTarget` + `FunctionTargetResult`. The handoff function receives the previous agent's output as a string, can parse it into a Pydantic model, write to shared `ContextVariables` (hidden from LLMs), and emit a curated `message` for the next agent. Used between Classification and ProfileCreation to extract `result.classes` and stash `acm_classes` in context. See §6.2.
- **RedundantPattern aggregator shape.** Per AG2 docs, the aggregator in the documented pattern is a `ConversableAgent` paired with a function for evaluation. We adopt the same shape: Chair (LLM decider) + Tool Executor (no LLM) + two deterministic Python tools that own the actual work. See §4.4.
- **Reviewer isolation.** RedundantPattern places each sibling in its own nested chat seeing only the task message, mediated by `extract_task_message`. No additional wrapping needed. See §4.3, §4.4.
- **Handoff timing.** `AfterWork` and `OnCondition` both fire after the source agent's full turn (including tool calls and final structured response) completes. We use `AfterWork` for unconditional sequential handoffs since none of our edges depend on response content. See §6.2.
