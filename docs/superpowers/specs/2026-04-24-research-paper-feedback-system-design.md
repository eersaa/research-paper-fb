# Agentic research paper feedback system — design

Status: approved (brainstorming). Date: 2026-04-24.

## 1. Purpose

Give a researcher constructive feedback on a manuscript by running it through a small board of LLM-based reviewer agents with diverse stances and focus areas. Output is a markdown report. System is stateless across runs and does not transmit the manuscript anywhere except the configured LLM proxy.

Target user: researcher. Non-goals: does not rewrite the paper; does not use private papers as knowledge.

## 2. Requirements mapping

- **≥3 agents** — Classification Agent, Profile Creation Agent, Reviewer Agent (×N, default N=3). An additional Judge Agent lives in a separate evaluation harness.
- **Multi-agent orchestration pattern** — sequential pipeline + parallel fan-out. Justification: Classification and Profile Creation have data dependencies, so they run in series; reviewers are independent and run in parallel via `asyncio.gather`. Profile Creation plays an orchestrator-like role in that it decides the board composition.
- **≥1 tool call** — two tools: `lookup_acm` (Classification Agent) and `write_review` (Reviewer Agent).

## 3. Architecture

```
[markdown manuscript]
       │
       ▼
┌───────────────────┐   tool: lookup_acm(query) → matching CCS paths
│ 1. Classification │◄─────── data/acm_ccs.json (prepared offline)
│     Agent         │
└───────────────────┘
       │ {acm_classes: [...]}
       ▼
┌───────────────────┐   deterministic sampler: pick N distinct
│ 2. Profile        │   (stance, focus) pairs  → N persona prompts
│    Creation Agent │
└───────────────────┘
       │ {reviewers: [persona_1, ..., persona_N]}
       ▼
   ┌───┼───┐  (parallel fan-out, asyncio.gather)
   ▼   ▼   ▼
 R1   R2   R3  …  R_N     tool: write_review(json) → reviews/<id>.json
   │   │   │
   └───┼───┘
       ▼
┌───────────────────┐
│ Renderer          │   pure code, no LLM — JSONs → report.md
│  (not an agent)   │
└───────────────────┘
       ▼
  final_report.md
```

## 4. Unit descriptions

### 4.1 Classification Agent (Unit 1)

- **Input:** manuscript markdown.
- **Job:** identify 2–5 most relevant ACM CCS concept paths with High/Medium/Low weights per ACM convention.
- **Tool:** `lookup_acm(query: str, k: int = 10)` — keyword/substring search over `data/acm_ccs.json`, returns matching concept paths with their descriptions. Agent may call multiple times with different candidate terms.
- **Output:**
  ```json
  {
    "classes": [
      {"path": "Computing methodologies → Machine learning → ...",
       "weight": "High",
       "rationale": "..."}
    ]
  }
  ```
- **Prompt focus:** ACM CCS guidance rules (prefer leaf nodes, use weights), reason about candidate terms before calling the tool.

### 4.2 Profile Creation Agent (Unit 2)

Two-phase hybrid:

1. **Deterministic sampler (Python).** Picks N pairs from (stance × focus) under constraint "no two reviewers share both axes; ideally differ on both." Reproducible via config-settable seed.
2. **LLM step.** For each sampled pair + ACM classes, produce a concrete reviewer persona: specialist background, voice, 1-paragraph self-description, review rubric.

- **Input:** ACM classes from Unit 1, config (N, axis vocabularies, seed).
- **Output:**
  ```json
  {
    "reviewers": [
      {"id": "r1", "stance": "...", "focus": "...",
       "persona_prompt": "<full system prompt for reviewer r1>"}
    ]
  }
  ```

### 4.3 Reviewer Agent (Unit 3, instantiated N times in parallel)

- **Input:** manuscript markdown + own persona prompt. (ACM classes are NOT passed separately — they are already baked into the persona prompt.)
- **Tool:** `write_review(reviewer_id, review_json)` — writes to `reviews/<reviewer_id>.json`. One file per reviewer; concurrency-safe.
- **Review JSON schema:**
  ```json
  {
    "reviewer_id": "...",
    "stance": "...",
    "focus": "...",
    "profile_summary": "...",
    "strengths": ["..."],
    "weaknesses": ["..."],
    "suggestions": ["..."],
    "section_comments": [{"section": "...", "comment": "..."}],
    "overall_assessment": "..."
  }
  ```
- **Prompt focus:** stay in persona; ground comments in actual manuscript text; never rewrite the paper (non-goal).

### 4.4 Renderer (not an agent)

Pure code. Reads all `reviews/*.json` + classification output + profile metadata. Emits `final_report.md`:

- Header: assigned ACM classes.
- Per-reviewer section: profile blurb → strengths / weaknesses / suggestions / section notes / overall.
- No cross-reviewer synthesis in v1.

### 4.5 Data prep script (`scripts/build_acm_ccs.py`, offline, one-time)

- Produces `data/acm_ccs.json` — list of `{path, leaf, description}`.
- Descriptions auto-generated via a one-off LLM call per node when not directly available from ACM. Cached to disk so this runs once.

## 5. Axis vocabularies (default, configurable via `config/axes.yaml`)

**Stances:** `neutral, supportive, critical, skeptical, rigorous, pragmatic, devil's-advocate, visionary`.

**Focuses:** `methods, results, impact, novelty, clarity, related-work, reproducibility, ethics`.

Extensible without code changes. Sampler operates on whatever values are in the config.

## 6. Configuration (`config/default.yaml`)

```yaml
transport: openai_chat_completions    # proxy speaks OpenAI /chat/completions
base_url_env: BASE_URL                # read from .env
models:
  default: anthropic/claude-3.5-haiku
  classification: anthropic/claude-3.5-haiku
  profile_creation: anthropic/claude-3.5-haiku
  reviewer: anthropic/claude-3.5-haiku
  judge: openai/gpt-4.1-mini          # different from reviewers to reduce self-preference bias
reviewers:
  count: 3                             # minimum 3, configurable up
  diversity: strict                    # differ on both axes when feasible
  seed: null                           # optional, for reproducibility
classification:
  max_classes: 5
paths:
  acm_ccs: data/acm_ccs.json
  reviews_dir: reviews/
  output: final_report.md
  logs_dir: logs/
```

Course-recommended text models (`openai/gpt-4.1-mini`, `anthropic/claude-3.5-haiku`, `google/gemini-3.1-flash-lite-preview`) are all valid swap-ins because the OpenAI `/chat/completions` transport routes to any of them through the OpenRouter proxy.

## 7. Error handling

- Per-LLM-call retry with exponential backoff (3 attempts) on transient errors (5xx, timeout).
- Classification failure → abort run.
- Profile Creation failure → abort run.
- Reviewer failure → skip that reviewer, log, continue. Report notes the skip.
- Tool schema violation (malformed JSON) → one retry with validator feedback, then skip.
- All LLM calls + tool calls logged to `logs/run-<timestamp>.jsonl` for debugging and cost auditing.

## 8. Non-leakage property

V1 guarantees, documented in README:

- System writes only to local paths: `reviews/`, `final_report.md`, `logs/`, `evaluations/`.
- Sole network egress is the configured proxy (`BASE_URL`).
- No telemetry, no third-party calls.

## 9. Evaluation harness (separate from main pipeline)

**Rubric (Likert 1–5 per dimension):**

- `specificity` — grounded in manuscript vs generic
- `actionability` — suggestions are concrete
- `persona-fidelity` — matches assigned stance + focus
- `coverage` — hits the focus area meaningfully
- `non-redundancy` — across reviewers, no duplicate points

**Judge agent (`scripts/judge.py`):** takes `final_report.md` + manuscript + per-reviewer JSONs; outputs `evaluations/<run-id>.json` with per-dimension scores and justifications. Uses a different model than the reviewers (bias mitigation; default `openai/gpt-4.1-mini` when reviewers use Claude).

**Baseline comparison experiment:** run each sample paper through (a) this system and (b) a single-shot Claude prompt; judge both; write up qualitative findings.

Judge feature is built **test-first**: fixtures of known-good and known-bad reviews with expected score bounds; implement `judge.py` to satisfy them.

## 10. Cost reporting

Report per-run token totals and USD cost (proxy returns `usage.cost`) at end of run. Logged, not gating.

## 11. Project structure

```
research-paper-fb-2/
├── src/
│   ├── agents/
│   │   ├── classification.py
│   │   ├── profile_creation.py
│   │   └── reviewer.py
│   ├── tools/
│   │   ├── lookup_acm.py
│   │   └── write_review.py
│   ├── orchestrator.py             # sequential + asyncio.gather fan-out
│   ├── renderer.py
│   ├── llm_client.py               # openai SDK wrapper, base_url = proxy
│   └── config.py
├── scripts/
│   ├── build_acm_ccs.py
│   └── judge.py
├── config/
│   ├── default.yaml
│   └── axes.yaml
├── data/
│   └── acm_ccs.json
├── tests/
│   ├── test_sampler.py
│   ├── test_renderer.py
│   ├── test_lookup_acm.py
│   ├── test_orchestrator.py
│   ├── test_judge.py
│   └── test_acceptance_live.py     # @pytest.mark.slow
├── samples/                        # arXiv papers for eval
├── reviews/                        # gitignored
├── evaluations/                    # gitignored
├── logs/                           # gitignored
├── PLAN.md
├── README.md
└── pyproject.toml
```

## 12. Testing strategy

- **Unit:** sampler (diversity guarantee), `lookup_acm` (deterministic), renderer (pure function), config loader.
- **Integration with mocked LLM:** orchestrator end-to-end with stubbed `llm_client`; verifies wiring, concurrency, error paths (skipped reviewer), tool-call round-trips.
- **TDD for judge:** fixtures of good/bad reviews; score bounds per dimension; implementation satisfies them.
- **Acceptance test (live proxy, `@pytest.mark.slow`):** tiny manuscript fixture, end-to-end run. Asserts: `final_report.md` exists; per-reviewer sections match N; ACM classes present; reviewer stances distinct per diversity rule; no manuscript text leaks to stdout or logs. Excluded from default `pytest`, included via `pytest -m slow`. Runs in CI on demand only (cost).

## 13. Out of scope / future work

- RAG over external corpora (arXiv, OpenResearch).
- Cross-run memory / adaptability.
- PDF and vision input.
- Human-in-the-loop.
- Reviewer tools beyond `write_review` (e.g. related-paper retrieval).
- Synthesis agent that merges reviews into a chair report.
- Embeddings-based ACM classification (current taxonomy is small enough for deterministic lookup).

## 14. Unresolved questions

- Source of ACM CCS tree — scrape from `dl.acm.org/ccs` or locate an existing structured dump?
- Sample paper set for eval — which arXiv papers, how many?
- CLI UX — invocation form and flags?
- Python version pin (3.11, 3.12)?
- Judge rubric — equal weighting of dimensions, or weighted aggregate?
