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
        │   writes context_variables["classification"] (full result)
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
│           │   Chair    │  collates slim Reviews + skipped  │   response_format=BoardReport
│           │ (aggregator)│ into BoardReport. No metadata    │   (slim: reviews+skipped),
│           └────────────┘  joining; renderer does that.     │   no LLM reasoning beyond
└────────────────────────────────────────────────────────────┘   collation
                  │
                  ▼
              BoardReport (slim: reviews + skipped)
                  │
                  ▼
       pipeline.run() assembles RunOutput
       (= classification + profiles + board)
       from context_variables + nested chat result
                  │
                  ▼
           Renderer (pure code; joins reviews ↔ profiles by reviewer_id)
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
- `paperfb/orchestrator.py` — shrinks to a thin `pipeline.py` that builds agents, registers handoffs, runs the chat, assembles `RunOutput` from `context_variables` + the nested chat's `BoardReport`, and hands `RunOutput` to the renderer.
- `paperfb/agents/*/agent.py` — hand-rolled tool-call loops; AG2 owns this now.
- `paperfb/agents/reviewer/tools.py` (`write_review`) — replaced by reviewer's structured Pydantic output. Per-reviewer JSON files no longer written by the runtime pipeline.
- Manual JSON validation in `paperfb/contracts.py` — Pydantic does it.
- `asyncio.gather` reviewer fan-out — replaced by RedundantPattern (sequential within the framework's GroupChat turn-taking; see §6.4).

### 2.3 What stays

- `data/acm_ccs.json`, `data/finnish_names.json`, `config/*.yaml`, `samples/`.
- `scripts/build_acm_ccs.py`, `scripts/build_finnish_names.py`.
- The renderer (now consumes `RunOutput` in-memory instead of reading per-reviewer JSON files).
- The deterministic sampler logic — relocated under `paperfb/tools/sampler.py` and exposed as the `sample_board` tool.
- `lookup_acm` lookup logic — relocated under `paperfb/tools/acm_lookup.py`.
- The non-leakage property: AG2 routes through the same OpenAI-compatible proxy via `llm_config.base_url`. No additional egress.

## 3. Pydantic schemas (`paperfb/schemas.py`)

All cross-agent messages and structured tool outputs use Pydantic. This module replaces `paperfb/contracts.py`.

**Portability rules (per §5.1) — applied to every model below, shown explicitly on `CCSClass` for example, omitted from the rest of the listing for brevity:**

```python
class CCSClass(BaseModel):
    model_config = ConfigDict(title="CCSClass", extra="forbid")
    ...
```

i.e. every `BaseModel` subclass sets `model_config = ConfigDict(title="<ClassName>", extra="forbid")`. This satisfies the OpenAPI `title` requirement and works around [Gemini's `additionalProperties` issue](https://github.com/ag2ai/ag2/issues/2348).

```python
from typing import Literal
from pydantic import BaseModel, ConfigDict

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
# Slim: review *content* only. Reviewer-identity metadata stays on
# ReviewerProfile and is joined back in by the renderer (§6.6) via
# reviewer_id. This eliminates metadata-echo waste and hallucination
# risk — see §4.3.

class Review(BaseModel):
    reviewer_id: str               # join key — must match a ReviewerProfile.id
    strong_aspects: str
    weak_aspects: str
    recommended_changes: str

# Aggregation ───────────────────────────────────────────────────────

class SkippedReviewer(BaseModel):
    id: str
    reason: str

class BoardReport(BaseModel):
    """Chair's structured output. No classification, no profile metadata —
    those are joined back in by pipeline.run() and the renderer."""
    reviews: list[Review]
    skipped: list[SkippedReviewer]

# Top-level run output ──────────────────────────────────────────────
# Assembled by pipeline.run() AFTER the chat completes. Renderer and
# Judge consume this. RunOutput is the on-disk shape (evaluations/run-<ts>/run.json).

class RunOutput(BaseModel):
    classification: ClassificationResult
    profiles: ProfileBoard
    board: BoardReport
```

## 4. Per-agent specifications

### 4.1 Classification Agent

- **Module:** `paperfb/agents/classification.py`
- **Builder:** `build_classification_agent(llm_config, ccs_path) -> ConversableAgent`
- **System prompt outline:** ACM CCS rules (prefer leaf nodes, 2–5 classes with High/Medium/Low weights), two-phase loop (extract paper-stated or synthesised keywords first, then drive `lookup_acm` queries), keywords are logged but do not propagate downstream.
- **Tool:** `lookup_acm(query: str, k: int = 10) -> list[CCSMatch]`. Multiple calls allowed within the loop.
- **Structured output:** `response_format=ClassificationResult`.
- **Handoff:** `AfterWork(target=FunctionTarget(classify_to_profile))`. The function parses the full `ClassificationResult`, writes it to `context_variables["classification"]` (so the renderer can read keywords + classes after the chat completes), and forwards a curated, classes-only message (e.g. `"ACM classes: [<paths>]"`) to ProfileCreation. `result.keywords` is preserved in `context_variables` and the run log but does NOT enter ProfileCreation's prompt or any downstream agent's prompt.

### 4.2 ProfileCreation Agent

- **Module:** `paperfb/agents/profile_creation.py`
- **Builder:** `build_profile_creation_agent(llm_config, axes, names_path, count, core_focuses, seed) -> ConversableAgent`
- **System prompt outline:** explains the persona formula (`name + specialty + stance + primary_focus + secondary_focus`), splices in the axis-vocabulary descriptions verbatim from `config/axes.yaml`, instructs the agent to call `sample_board` exactly once and then emit `ProfileBoard` with one `ReviewerProfile` per sampled tuple.
- **Tool:** `sample_board(n: int, classes: list[CCSClass], seed: int | None = None) -> list[ReviewerTuple]`. Deterministic Python; wraps the existing sampler under `paperfb/tools/sampler.py`. Config-derived parameters (`stances`, `focuses`, `core_focuses`, `enable_secondary`, `names_path`) are **closure-bound** at tool-registration time inside `build_profile_creation_agent` — the LLM does not see or supply them. This minimises the LLM's parameter surface (only `n`, `classes`, optional `seed`) and prevents the agent from inventing axis vocabularies.
- **Persona generation strategy:** single LLM step producing all N personas at once via structured output. Each `ReviewerProfile.persona_prompt` is a full system message — embeds the assigned Finnish given name, specialty grounding, stance description, primary/secondary focus rubric language. (Per-tuple sub-loops are YAGNI.)
- **Structured output:** `response_format=ProfileBoard`.
- **Handoff:** `AfterWork(target=FunctionTarget(setup_review_board))`. The function parses `ProfileBoard`, builds N reviewer `ConversableAgent`s via `build_reviewer_agent` (§4.3), constructs a `RedundantPattern(agents=reviewers, aggregator=chair, task=context_variables["manuscript"])`, and returns `FunctionTargetResult(target=NestedChatTarget(redundant_pattern))`. Runtime agent construction happens here, in plain Python, at the canonical AG2 boundary for "build downstream agents from upstream structured output." See §4.4 for the function body.

### 4.3 Reviewer Agent (factory; instantiated by `setup_review_board`)

- **Factory:** `build_reviewer_agent(profile: ReviewerProfile, llm_config) -> ConversableAgent`.
- **Constructed by:** `setup_review_board` FunctionTarget (§4.4) at runtime, one per `ReviewerProfile`.
- **System prompt:** `profile.persona_prompt` verbatim, plus a single appended line `"Your reviewer_id is: <profile.id>. Use this exact value as Review.reviewer_id."` so the agent knows the join key without reproducing other metadata. ProfileCreation has already embedded the assigned name, ACM specialty, stance description, primary/secondary focus rubric language inside `persona_prompt`.
- **Input received per nested chat:** the manuscript text as the redundant-task message. That is all. ACM classification context does **not** flow to reviewers — the specialty (an ACM class path) is already part of the persona prompt.
- **No tools.** Pydantic structured output replaces the previous `write_review` tool.
- **Structured output:** `response_format=Review` — the slim form (§3): `{reviewer_id, strong_aspects, weak_aspects, recommended_changes}`. Identity metadata (name, stance, focus, specialty) is owned by `ReviewerProfile` and joined back in by the renderer (§6.6) via `reviewer_id`. The reviewer agent never echoes its own metadata.
- **Turn limit:** `max_consecutive_auto_reply=1`. Reviewers respond once and are done.
- **Isolation:** RedundantPattern places each reviewer in its own nested chat. Siblings cannot see each other; the broader orchestration transcript is hidden. Only the manuscript reaches them, mediated by `extract_task_message`.

### 4.4 `setup_review_board` FunctionTarget + Chair (aggregator)

Runtime reviewer construction lives in a `FunctionTarget` on ProfileCreation's handoff. This is the AG2-idiomatic location for "materialise downstream agents from upstream structured output" — analogous to how the [redundant-pattern example](https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/pattern-cookbook/redundant/) builds its agent queue at config time, only here the inputs come from a prior agent's response. No tool dispatch, no extra LLM call.

```python
def setup_review_board(
    agent_output: str,
    context_variables: ContextVariables,
) -> FunctionTargetResult:
    """Closure: captures llm_configs and expected_ids at pipeline-build time."""
    board = ProfileBoard.model_validate_json(agent_output)
    expected_ids = {p.id for p in board.reviewers}
    reviewers = [
        build_reviewer_agent(p, reviewer_llm_config)
        for p in board.reviewers
    ]
    chair = build_chair(chair_llm_config)
    pattern = RedundantPattern(
        agents=reviewers,
        aggregator=chair,
        task=context_variables["manuscript"],
    )
    context_variables["profiles"] = board.model_dump()
    context_variables["expected_reviewer_ids"] = sorted(expected_ids)
    context_variables.setdefault("skipped", [])
    return FunctionTargetResult(
        target=NestedChatTarget(pattern.as_nested_chat()),
        context_variables=context_variables,
    )
```

(Final API names — `RedundantPattern` constructor signature, `as_nested_chat()` form — to be confirmed against AG2 0.12.1 at implementation time. The shape is fixed; the surface may shift.)

**Reviewer-failure detection:** RedundantPattern siblings can fail in two ways: (a) Pydantic validation fails on the agent's structured output after the configured retry, (b) the underlying LLM call raises after retries. AG2 reports per-sibling status on the pattern's result. The implementation pass MUST verify the exact API but the contract is: after the nested chat completes, *Chair's system prompt directs it to* read the sibling chat history, identify which `expected_reviewer_ids` did not produce a valid `Review`, and write `SkippedReviewer(id=..., reason=...)` entries to `context_variables["skipped"]`. Chair sees the sibling failures because it runs as the aggregator inside the same nested chat. If a more reliable AG2 hook surfaces (e.g. `pattern.failed_agents`), `setup_review_board` can populate `skipped` deterministically before Chair runs and Chair becomes a pure passthrough.

**Chair Agent (aggregator inside RedundantPattern):**

- **Module:** `paperfb/agents/chair.py`
- **Builder:** `build_chair(llm_config) -> ConversableAgent`
- **Role:** receives the slim `Review` objects emitted by the redundant siblings (in chat history), reads `context_variables["expected_reviewer_ids"]` and `context_variables["skipped"]`, and emits `BoardReport(reviews=[...], skipped=[...])` as its structured response. **No metadata joining** — that's the renderer's job. **No classification** — that's pipeline.run()'s job (read from `context_variables["classification"]` and bundled into `RunOutput`).
- **System prompt:** one paragraph instructing Chair to (1) collect every valid `Review` it sees from the siblings, (2) for any `expected_reviewer_id` whose Review is missing or malformed, append a `SkippedReviewer(id, reason="missing or invalid Review")` entry to `BoardReport.skipped`, (3) emit `BoardReport`. No editing, no synthesis, no commentary.
- **Structured output:** `response_format=BoardReport` (slim — see §3).
- **Why an LLM agent and not a deterministic callable.** AG2's documented RedundantPattern uses an LLM `ConversableAgent` aggregator. Following that idiom keeps us inside the framework's documented surface. Cost is one cheap LLM call. If a future AG2 version exposes a deterministic-callable aggregator hook on `RedundantPattern`, Chair can be swapped without changing any other agent.

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

If a future requirement re-introduces Claude as a structured-output agent, the implementation can adopt **tool-calling** as the structured-output transport for that agent only (forced function call as the response shape; works for all three models per the probe).

## 6. Cross-cutting concerns

### 6.1 User entry, tool-executor wiring, and post-chat assembly

```python
# Single UserProxyAgent serves dual role: chat initiator + tool executor.
user_proxy = UserProxyAgent(
    name="user",
    human_input_mode="NEVER",
    code_execution_config=False,
)

# Tool registration: the calling agent declares the tool to its LLM
# (register_for_llm); the user_proxy is the *executor* that actually runs it
# (register_for_execution). Same UserProxy instance used for both linear-leg tools.
classification_agent = build_classification_agent(...)
profile_creation_agent = build_profile_creation_agent(...)

@user_proxy.register_for_execution()
@classification_agent.register_for_llm(name="lookup_acm", description="...")
def lookup_acm(query: str, k: int = 10) -> list[CCSMatch]: ...

@user_proxy.register_for_execution()
@profile_creation_agent.register_for_llm(name="sample_board", description="...")
def sample_board(n: int, classes: list[CCSClass], seed: int | None = None) -> list[ReviewerTuple]:
    # closure-bound: stances, focuses, core_focuses, enable_secondary, names_path
    ...

# Run the chat. Manuscript is the initiating message and gets stashed for
# downstream FunctionTargets via initial context_variables.
ts = utc_timestamp()  # used by both logger (§6.5) and renderer output dir (§6.6)
chat_result = user_proxy.initiate_chat(
    group_chat_manager,
    message=manuscript_text,
    context_variables={"manuscript": manuscript_text, "run_id": ts},
)

# Post-chat assembly. Outer GroupChat terminates after the nested
# RedundantPattern returns (no further AfterWork registered after
# setup_review_board's NestedChatTarget — see §6.2). pipeline.run() now
# reads everything from context_variables + the nested chat result.
ctx = chat_result.context_variables
classification = ClassificationResult.model_validate(ctx["classification"])
profiles       = ProfileBoard.model_validate(ctx["profiles"])
board_report   = extract_board_report(chat_result)  # last message of nested chat,
                                                    # parsed via Pydantic
run = RunOutput(classification=classification, profiles=profiles, board=board_report)

# Renderer + on-disk artefact
final_md = render_report(run)
write_run_output(run, ts)  # evaluations/run-<ts>/run.json for Judge
```

The manuscript is the initiating message and is also stashed in `context_variables["manuscript"]` so the `setup_review_board` `FunctionTarget` can pass it as the redundant-pattern task. It travels only through the proxied conversation; non-leakage preserved (§6.7).

`extract_board_report` reads the nested chat's last message (Chair's structured response) and parses it as `BoardReport`. Final API path (`chat_result.nested_chat_results`, `chat_result.chat_history`, etc.) is to be confirmed against AG2 0.12.1 at implementation time.

### 6.2 Handoff topology

Default Pattern handoffs encoded on each agent at construction time:

| From | Handoff | To | Notes |
| --- | --- | --- | --- |
| (UserProxy entry) | `initiate_chat(message=manuscript_text)` | Classification | UserProxy also stashes the manuscript in `context_variables["manuscript"]` for downstream `FunctionTarget`s to read. |
| Classification | `AfterWork(target=FunctionTarget(classify_to_profile))` | ProfileCreation | Function parses the full `ClassificationResult`, writes it to `context_variables["classification"]` (so the renderer can read keywords + classes after the chat completes), forwards a curated, classes-only message to ProfileCreation. |
| ProfileCreation | `AfterWork(target=FunctionTarget(setup_review_board))` | NestedChat (RedundantPattern) | Function builds N reviewer agents from `ProfileBoard`, constructs RedundantPattern with Chair as aggregator, returns `NestedChatTarget`. See §4.4. |
| Reviewer Ri | implicit (RedundantPattern siblings → aggregator) | Chair | Pattern-internal; not a Default-Pattern handoff. |
| Chair | (no handoff — terminal node of nested chat) | — | Chair's structured `BoardReport` response terminates the *nested* RedundantPattern chat. |
| (post-nested) | (no further outer handoff registered) | — | The outer Default-Pattern chat has nothing to do after the `NestedChatTarget` returns. The outer chat terminates. `pipeline.run()` then assembles `RunOutput` from `context_variables` + the nested chat's final message — see §6.1. |

`AfterWork` is unconditional: fires after the source agent's full turn (including any tool calls and the final structured response) completes. We do not use `OnCondition` since none of these handoffs are conditional on response content — Pydantic validation already gates "did the agent succeed."

### 6.3 Error handling

- **Classification fails** (no classes returned, repeated tool errors, exhausted retries): abort run, non-zero exit, no report written.
- **ProfileCreation fails** (validation failure on `ProfileBoard`, sampler exception): abort run.
- **Reviewer fails** (validation failure on `Review`, exception inside the sibling chat): the sibling does not produce a valid `Review`. Chair (per its system prompt, §4.4) detects the missing `reviewer_id` against `context_variables["expected_reviewer_ids"]` and emits a `SkippedReviewer(id=..., reason=...)` entry in `BoardReport.skipped`. Run continues; renderer notes the skip. If AG2 surfaces a per-sibling failure hook on `RedundantPattern`, `setup_review_board` populates `skipped` deterministically before Chair runs and Chair becomes a pure passthrough.
- **Pydantic validation error on a structured response:** AG2 retry-with-validator-feedback (1 retry, configured via `ag2.retry_on_validation_error`); on second failure the agent's branch fails per the rules above.
- **Tool errors:** `lookup_acm` raises `ValueError` on bad input; AG2 surfaces it back to the calling agent which may retry. `sample_board` raises if `len(names) < n` (preserves existing invariant from `data/finnish_names.json`).

### 6.4 Reviewer parallelism

RedundantPattern is implemented on top of GroupChat, which is turn-based. Reviewers therefore execute **sequentially** within the pattern, but each sibling sees an isolated context (no cross-talk; the value of RedundantPattern). For N=3 default, sequential reviewer execution is acceptable: ~10–20 s per reviewer × 3 ≈ ~30–60 s total, in line with current run times. We do **not** wrap RedundantPattern with `asyncio.gather`; staying inside the framework's pattern is a course-story priority.

### 6.5 Logging

Register an AG2 logging hook that writes JSONL to `logs/run-<ts>.jsonl`. The `<ts>` is the same UTC timestamp generated once in `pipeline.run()` (§6.1) and reused by the renderer for its on-disk output (`evaluations/run-<ts>/run.json`, §6.6) — the two artefacts share a run-id for correlation. Each line records: timestamp, agent name, role, content (subject to the size-threshold filter described in §6.7 — payloads >1024 bytes are stored as a SHA-256 content-hash + byte length, not cleartext), tool calls, and `usage` (tokens, cost). Replaces `LLMClient` logging. Used by Wave 2 cost reporting.

### 6.6 Renderer

`paperfb/renderer.py` becomes:

```python
def render_report(run: RunOutput) -> str: ...
```

Reads the in-memory `RunOutput`. Joins each `Review` with its corresponding `ReviewerProfile` (via `reviewer_id` → `profile.id`) to render header + per-reviewer sections. Produces markdown with the same shape as today: header (assigned ACM classes from `run.classification.classes`), per-reviewer sections (`## Review by {profile.name} — {profile.specialty}`), three labelled subsections (Strong / Weak / Recommended), skipped-reviewer note from `run.board.skipped` if any.

`pipeline.run()` separately writes the serialised `RunOutput` to `evaluations/run-<ts>/run.json` (same `<ts>` as the JSONL log, §6.5) — the canonical on-disk artefact consumed by the Wave 2 Judge (§8). The runtime no longer writes per-reviewer JSON files.

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
├── renderer.py                  # signature change: render_report(run: RunOutput)
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
├── judge.py                     # rewritten: consumes RunOutput JSON file
├── build_acm_ccs.py             # unchanged
└── build_finnish_names.py       # unchanged
```

`paperfb/agents/{classification,profile_creation,reviewer}/` directories are flattened to single modules — each agent's hand-rolled loop disappears, prompts are inline strings within the builder, tools live under `paperfb/tools/` (shared module rather than per-agent). The agent-private import-isolation rule from the v1 design is retired: agents now communicate exclusively through Pydantic models in `schemas.py`, so per-agent subpackages add no isolation value.

## 8. Wave 2 — Judge (independent tool, deferred design pass)

Judge becomes an AG2 setup:

- `JudgeAgent` (`response_format=JudgeScore`) iterates per `Review` in `run.board.reviews`, joining with the matching `ReviewerProfile` from `run.profiles` via `reviewer_id` so the judge sees the persona context for fidelity scoring.
- `scripts/judge.py` reads `evaluations/run-<ts>/run.json` (the `RunOutput` artefact written by `pipeline.run()`, §6.6), runs the `JudgeAgent` once per review, writes `evaluations/run-<ts>/judge.json` with per-dimension scores + per-reviewer mean + board mean (current shape preserved).
- Same Pydantic discipline: `JudgeScore` defined in `paperfb/schemas.py`.
- Judge model defaults to a different family than reviewers (current bias-mitigation rule preserved — see §5).

Detailed `JudgeScore` schema and prompt deferred to its own design pass.

## 9. Testing strategy

- **Unit:**
  - `sample_board` tool: diversity invariants — `(stance, primary_focus)` unique across reviewers; core focuses covered when `N >= len(core_focuses)`; Finnish names unique.
  - `lookup_acm` tool: deterministic ranking, multi-token AND with parent-path bonus (preserves existing behaviour).
  - Renderer: pure function, golden-output test on fixture `RunOutput` (covers the `reviewer_id` ↔ `ReviewerProfile` join logic).
  - Pydantic schemas: validation error cases (bad weight value, missing fields, slim `Review` shape, `RunOutput` round-trip).
- **Integration with stubbed LLM:**
  - Pipeline end-to-end with AG2's mocked-LLM facilities (or monkeypatched OpenAI client).
  - Asserts the handoff sequence (Classification → ProfileCreation → Redundant → Chair).
  - Asserts RedundantPattern emits exactly N reviews when all succeed.
  - Asserts skipped-reviewer path: stub one reviewer to raise; assert `BoardReport.skipped` length 1, `BoardReport.reviews` length N-1.
  - Asserts `context_variables` propagates from outer chat into the nested RedundantPattern (Chair can read `expected_reviewer_ids` and `skipped`).
  - Asserts `pipeline.run()` builds a valid `RunOutput` from `context_variables["classification"]` + `context_variables["profiles"]` + the nested chat result.
- **Acceptance (`@pytest.mark.slow`):**
  - Live proxy end-to-end on a tiny manuscript fixture.
  - Asserts: `final_report.md` exists, `evaluations/run-<ts>/run.json` exists and round-trips through `RunOutput`, per-reviewer sections match N, ACM classes present, distinct stances/focuses per diversity rule, distinct Finnish names, no manuscript leakage to stdout or logs.

Existing test files to be migrated:

- `tests/test_orchestrator.py` → `tests/test_pipeline.py` (rewritten against AG2 mocked LLM).
- `tests/test_llm_client.py` → deleted (no `LLMClient` to test).
- `tests/test_contracts.py` → `tests/test_schemas.py` (Pydantic validation cases for the §3 schemas, including `RunOutput`).
- `tests/agents/profile_creation/test_sampler.py` → `tests/tools/test_sampler.py`.
- `tests/agents/classification/test_tools.py` → `tests/tools/test_acm_lookup.py`.
- `tests/agents/{classification,profile_creation,reviewer}/test_agent.py` → deleted; replaced by integration tests on the new pipeline.
- `tests/test_renderer.py` → updated to `RunOutput` input shape; covers profile-join via `reviewer_id`.
- `tests/test_judge.py` → updated to consume `evaluations/run-<ts>/run.json`.
- `tests/test_acceptance_live.py` → updated assertions (no per-reviewer JSON files; assert `RunOutput` artefact instead).

## 10. Migration plan (high-level; a detailed plan is the next deliverable via `writing-plans`)

**Approach: in-place rewrite.** No feature flag, no parallel pipeline, no compatibility shim. The existing v1 pipeline at HEAD is the reference; intermediate commits during the rewrite may not produce working end-to-end runs. Rationale: no production users, no external consumers, and a parallel pipeline would double the surface area being maintained for the duration of the refactor.

**Dependency pin:** `ag2==0.12.1` (latest stable on PyPI as of 2026-04-29). The `pyproject.toml` change replaces the existing `openai>=1.50.0` direct dependency with `ag2[openai]==0.12.1`, which transitively pulls in a compatible `openai` SDK.

The implementation plan (separate document) will sequence the refactor as:

1. Update `pyproject.toml` to depend on `ag2[openai]==0.12.1` (replacing the direct `openai>=1.50.0` dep). Regenerate `uv.lock` with `uv lock`.
2. Scaffold `paperfb/schemas.py` with all Pydantic models from §3 (ClassificationResult, ProfileBoard, Review, BoardReport, RunOutput, plus supporting types). All models carry `model_config = ConfigDict(title="<ClassName>", extra="forbid")`. Add unit tests for validation and round-trip. **Defer `JudgeScore`** — added in step 10.
3. Move `sample_board` and `lookup_acm` into `paperfb/tools/` with Pydantic-typed I/O. Move existing tool tests: `tests/agents/profile_creation/test_sampler.py` → `tests/tools/test_sampler.py`, `tests/agents/classification/test_tools.py` → `tests/tools/test_acm_lookup.py`. Adapt assertions to Pydantic-typed returns.
4. Build Classification agent (`paperfb/agents/classification.py` + builder) and the `classify_to_profile` FunctionTarget body in `paperfb/handoffs.py`. Integration test against mocked AG2 LLM. (No need to re-verify `response_format` per model — already verified in §5.1.)
5. Build ProfileCreation agent (`paperfb/agents/profile_creation.py` + builder, with `sample_board` registered as a closure-bound tool). Integration test.
6. Build reviewer factory (`paperfb/agents/reviewer.py`), Chair aggregator (`paperfb/agents/chair.py`), and the `setup_review_board` FunctionTarget body in `paperfb/handoffs.py`. The FunctionTarget constructs the RedundantPattern from `ProfileBoard` and returns a `NestedChatTarget`. Integration test covering: handoff sequence, RedundantPattern emits N reviews on success, skipped-reviewer path (one stubbed reviewer raises), and verification that nested chat reads outer `context_variables`.
7. Wire the full pipeline in `paperfb/pipeline.py` with `UserProxyAgent` entry (dual role: chat initiator + tool executor for `lookup_acm` and `sample_board`). Generate run-id timestamp; pass to logger and renderer. Implement `extract_board_report(chat_result) -> BoardReport`. Implement `RunOutput` assembly per §6.1.
8. Update renderer to `render_report(run: RunOutput) -> str`; implement deterministic profile-join via `reviewer_id`. Delete the per-reviewer `reviews/*.json` runtime path. Add `write_run_output(run, ts)` writing `evaluations/run-<ts>/run.json`.
9. Update CLI in `paperfb/main.py` to call `pipeline.run()` and pass results through renderer + on-disk writer.
10. Update Judge: add `JudgeScore` to `paperfb/schemas.py`; rewrite `scripts/judge.py` to consume `evaluations/run-<ts>/run.json` (joining `Review` with `ReviewerProfile` via `reviewer_id` for fidelity scoring); update `tests/test_judge.py` accordingly.
11. **Deletion sweep.** Remove obsolete files:
    - `paperfb/llm_client.py`, `paperfb/orchestrator.py`, `paperfb/contracts.py`
    - `paperfb/agents/classification/` (whole subpackage), `paperfb/agents/profile_creation/`, `paperfb/agents/reviewer/`
    - `tests/test_llm_client.py`, `tests/test_orchestrator.py`, `tests/test_contracts.py`, `tests/agents/`
    Update README and PLAN.md to reflect the new architecture; cross-link this design doc.
12. Run live acceptance test (`pytest -m slow`); verify `final_report.md` and `evaluations/run-<ts>/run.json`.

## 11. Open questions

(none blocking design; all items below are resolved or downgraded to smoke-tests)

Resolved during this design pass:

- **`response_format` across course models.** Empirically verified ([_test_proxy_structured.py](../../../scripts/probe_proxy_structured.py), 2026-04-29) against the course proxy: OpenAI (`gpt-4.1-mini`) and Google (`gemini-2.5-flash-lite`) honour `response_format=PydanticModel`; Anthropic Claude 3.5 Haiku does NOT (returns prose). AG2's native Anthropic structured-output path requires direct Anthropic API access (incompatible with this proxy and with the non-leakage property). Therefore Classification, ProfileCreation, Reviewer, and Chair are pinned to OpenAI/Google models. See §5.1 for the matrix and the constraint. Schema portability rules we adopt: every Pydantic root model defines a `title`, every model sets `model_config = {"extra": "forbid"}` (works around [Gemini's `additionalProperties` issue](https://github.com/ag2ai/ag2/issues/2348)), schemas stay OpenAPI-compliant.
- **Carryover shape between handoffs.** AG2 supports sub-field extraction via `FunctionTarget` + `FunctionTargetResult`. The handoff function receives the previous agent's output as a string, can parse it into a Pydantic model, write to shared `ContextVariables` (hidden from LLMs), and emit a curated `message` for the next agent — or transition to a `NestedChatTarget`. Used twice: classify→profile (sub-field extraction) and profile→reviewer-board (runtime agent construction). See §4.4 and §6.2.
- **RedundantPattern aggregator shape.** Per AG2 docs, the aggregator in the documented pattern is a `ConversableAgent`. Chair adopts that role: a thin LLM agent with `response_format=BoardReport` that collates verbatim. See §4.4.
- **Runtime reviewer instantiation.** Lives in a `FunctionTarget` (`setup_review_board`) on ProfileCreation's handoff, which builds N reviewer `ConversableAgent`s from the parsed `ProfileBoard` and returns a `NestedChatTarget` for the constructed RedundantPattern. No tool dispatch and no extra LLM call needed for setup. See §4.4.
- **Reviewer isolation.** RedundantPattern places each sibling in its own nested chat seeing only the task message (the manuscript), mediated by `extract_task_message`. ACM context does not flow to reviewers — specialty is already in the persona prompt. See §4.3.
- **Handoff timing.** `AfterWork` and `OnCondition` both fire after the source agent's full turn (including tool calls and final structured response) completes. We use `AfterWork` for unconditional sequential handoffs since none of our edges depend on response content. See §6.2.
