# Agentic research paper feedback system — design

Status: approved (brainstorming). Date: 2026-04-24.

## 1. Purpose

Give a researcher constructive feedback on a manuscript by running it through a small board of LLM-based reviewer agents with diverse stances and focus areas. Output is a markdown report. System is stateless across runs and does not transmit the manuscript anywhere except the configured LLM proxy.

Target user: researcher. Non-goals: does not rewrite the paper; does not use private papers as knowledge.

The runtime pipeline ingests **markdown only**. PDF source manuscripts are converted to markdown ahead of time via an offline ingestion tool (§4.6); three published papers in this field whose ACM classifications are publicly known are converted and stored under `samples/` for evaluation.

## 2. Requirements mapping

- **≥3 agents** — Classification Agent, Profile Creation Agent, Reviewer Agent (×N, default N=3). An additional Judge Agent lives in a separate evaluation harness.
- **Multi-agent orchestration pattern** — sequential pipeline + parallel fan-out. Justification: Classification and Profile Creation have data dependencies, so they run in series; reviewers are independent and run in parallel via `asyncio.gather`. Profile Creation plays an orchestrator-like role in that it decides the board composition.
- **≥1 tool call** — two tools: `lookup_acm` (Classification Agent) and `write_review` (Reviewer Agent).

## 3. Architecture

Offline preparation (run once, outputs committed under `data/` and `samples/`):

```
[ACM CCS XML dump] ──► scripts/build_acm_ccs.py        ──► data/acm_ccs.json
[Finnish nameday calendar] ──► scripts/build_finnish_names.py ──► data/finnish_names.json
[paper.pdf]      ──► scripts/pdf_to_markdown.py        ──► samples/<id>/manuscript.md
```

Runtime (per Run):

```
[markdown manuscript]
       │
       ▼
┌───────────────────┐   tool: lookup_acm(query) → matching CCS paths
│ 1. Classification │◄─────── data/acm_ccs.json (prepared offline)
│     Agent         │   keyword extraction → tool queries → class selection
└───────────────────┘
       │ {keywords, classes}
       ▼
┌───────────────────┐   deterministic sampler: pick N distinct
│ 2. Profile        │   (stance, focus) tuples + Finnish names → N persona prompts
│    Creation Agent │◄─────── data/finnish_names.json
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
- **Job (single agent loop, two phases):**
  1. **Keyword extraction.** Produce a list of CCS-relevant candidate keywords. Source order:
     - explicit `Keywords:` / `Index Terms:` block in the manuscript (high precedence);
     - synthesised terms drawn from title, abstract, and section headings when the explicit block is missing or sparse — terms a domain expert would expect to land in the CCS taxonomy.
     The two sources are tracked separately on the output so reviewers (and the Judge) can see what was extracted vs. synthesised.
  2. **Class selection.** Drive `lookup_acm` queries from those keywords, then pick 2–5 most relevant CCS concept paths with `High`/`Medium`/`Low` weights per ACM convention. The original "reason about candidate terms before calling the tool" loop is retained on top — keywords seed the queries but the agent may issue additional exploratory queries from its own reasoning.
- **Tool:** `lookup_acm(query: str, k: int = 10)` — keyword/substring search over `data/acm_ccs.json`, returns matching concept paths with their descriptions. Agent calls it multiple times with different candidate terms.
- **Agent's full JSON output (logged for auditing / judge):**
  ```json
  {
    "keywords": {
      "extracted_from_paper": ["..."],
      "synthesised":          ["..."]
    },
    "classes": [
      {"path": "Computing methodologies → Machine learning → ...",
       "weight": "High",
       "rationale": "..."}
    ]
  }
  ```

- **Downstream contract (`ClassificationResult` consumed by Profile Creation):** unchanged from v0 — only `classes` is propagated. The keyword block is internal: it shapes tool queries and is logged/visible to the Judge, but does not flow to Profile Creation or to Reviewer prompts.
- **Prompt focus:** ACM CCS guidance rules (prefer leaf nodes, use weights); make keyword extraction explicit before any tool call; reason about candidate terms before each tool call.

### 4.2 Profile Creation Agent (Unit 2)

**Persona formula:**

```
persona = name(Finnish given name) + specialty(from ACM classes) + stance + primary_focus + secondary_focus
```

- **Name** is a relatability touch — a traditional Finnish given name pulled from the Finnish nameday calendar (`data/finnish_names.json`). Surfaced in the persona prompt and in the rendered review header.
- **Specialty** is the foundation — grounds the reviewer as a real domain expert (e.g. "reviewer specializing in distributed fault-tolerant systems"), derived from an ACM CCS class path produced by Unit 1. This is what the sketch in `Process-and-agent-units.png` calls "base version creates profiles based on ACM classes."
- **Stance + focuses** are the modulation — how this specialist approaches the paper. What the sketch calls "add some variation."

Two-phase hybrid:

1. **Deterministic sampler (Python).** Produces N tuples `(specialty_class, stance, primary_focus, secondary_focus)`. Reproducible via config-settable seed.
2. **LLM step.** For each sampled tuple, produce a concrete reviewer persona: specialist background grounded in the ACM class description, voice shaped by stance, review rubric emphasising primary focus with secondary focus as supplementary lens. Output is a full system prompt for that reviewer.

**Sampler algorithm:**

1. Sort ACM classes by weight (High → Medium → Low).
2. For each reviewer `r_i` (i in 0..N-1):
   - `specialty = acm_classes[i % len(acm_classes)]` — round-robin with cycling when N > number of classes, so higher-weight classes get reused first. If only one class exists, all reviewers share specialty but differ on the other axes.
   - `primary_focus` — first K=|core_focuses| reviewers get each core focus in order; remaining reviewers draw randomly from the full focus pool.
   - `secondary_focus` — drawn to maximise unused focuses across the board (greedy coverage heuristic), distinct from the reviewer's own primary.
   - `stance` — drawn from stance pool under the constraint that `(stance, primary_focus)` is unique across the board. Neutral stance allowed.
   - `name` — drawn at random (sampler seed) from `data/finnish_names.json`, no repeats across the board (sampler aborts and resamples if the names list is smaller than N — `len(names) >= N` is enforced).

**Diversity constraint:** no two reviewers share the same `(stance, primary_focus)` pair. Secondary focus is allowed to overlap — it is a depth dimension, not an identity dimension. **Name** is independently unique across the board but is not part of the identity tuple — two boards may reuse the same names across runs. With default N=3 and core focuses `[methods, results, novelty]`, the three primary focuses are guaranteed distinct and the three stances are effectively distinct too.

- **Input:** ACM classes from Unit 1, config (N, axis vocabularies, core focuses, seed).
- **Output:**

  ```json
  {
    "reviewers": [
      {"id": "r1",
       "name": "Aino",
       "specialty": "<ACM class path>",
       "stance": "...",
       "primary_focus": "...",
       "secondary_focus": "...",
       "persona_prompt": "<full system prompt for reviewer r1, addresses the reviewer by name>"}
    ]
  }
  ```

### 4.3 Reviewer Agent (Unit 3, instantiated N times in parallel)

- **Input:** manuscript markdown + own persona prompt. (ACM classes are NOT passed separately — they are already baked into the persona prompt.)
- **Tool:** `write_review(reviewer_id, review_json)` — writes to `reviews/<reviewer_id>.json`. One file per reviewer; concurrency-safe.
- **Review JSON schema** (mirrors `review-template.txt`, an IEEE-style conference reviewing form — five 1–5 ratings each with a descriptor label, plus three free-text aspects as single strings):

  ```json
  {
    "reviewer_id": "r1",
    "reviewer_name": "Aino",
    "specialty": "...",
    "stance": "...",
    "primary_focus": "...",
    "secondary_focus": "...",
    "profile_summary": "...",
    "ratings": {
      "relevance_and_timeliness":     {"score": 4, "label": "Good"},
      "technical_content_and_rigour": {"score": 3, "label": "Valid work but limited contribution"},
      "novelty_and_originality":      {"score": 4, "label": "Significant original work and novel results"},
      "quality_of_presentation":      {"score": 4, "label": "Well written"},
      "overall_recommendation":       {"score": 4, "label": "Accept"}
    },
    "strong_aspects":      "...",
    "weak_aspects":        "...",
    "recommended_changes": "..."
  }
  ```

- **Rating dimensions** map 1:1 onto the IEEE-style template fields. `score` is integer 1–5; `label` is the descriptor for that score on that dimension. The full canonical descriptor table is partially captured in `review-template.txt` and is otherwise treated as an open follow-up (see §14) — the agent emits the descriptor that best fits the score, falling back to `null` when the canonical wording is unknown.
- **Prompt focus:** stay in persona; ground comments in actual manuscript text; never rewrite the paper (non-goal); use the persona's assigned Finnish given name when self-referencing.

### 4.4 Renderer (not an agent)

Pure code. Reads all `reviews/*.json` + classification output + profile metadata. Emits `final_report.md`:

- Header: assigned ACM classes.
- Per-reviewer section: header line `## Review by {reviewer_name} — {specialty}` (Finnish given name surfaced for relatability), one-line profile blurb (stance + primary/secondary focus), a five-row ratings table (`{dimension} | {score}/5 | {label}`), then the three free-text aspects (strong / weak / recommended changes).
- No cross-reviewer synthesis in v1.

### 4.5 Offline data preparation tools

Three offline scripts produce committed inputs the runtime pipeline reads. All run outside the agentic pipeline.

#### 4.5.1 ACM CCS dump (`scripts/build_acm_ccs.py`)

- Fetches the ACM CCS 2012 tree (source: ACM's official structured dump of the CCS classification).
- Parses the full tree (not a seed subset) into a flat list.
- For each node, generates a 1–2 sentence description via an LLM call through the proxy. Descriptions are cached to disk (`data/_ccs_descriptions_cache.json`) so reruns of the prep tool are cheap and deterministic.
- Emits `data/acm_ccs.json` — list of `{path, leaf, description}` entries consumed by `lookup_acm`.

#### 4.6 Manuscript ingestion: PDF → markdown (`scripts/pdf_to_markdown.py`)

- **Purpose:** convert PDF source manuscripts to markdown ahead of time so the runtime pipeline keeps its single-input contract (markdown only). Three published papers in this field with publicly known ACM classifications are converted up front and stored under `samples/<paper-id>/manuscript.md` for evaluation.
- **Library:** `pymupdf4llm` as the v1 default — text-first, low setup cost, good enough for the body text the reviewers reason over. Tables come through best-effort; replacing the backend with `marker` is a future swap if quality blocks evaluation.
- **CLI:** `uv run python scripts/pdf_to_markdown.py <input.pdf> <output.md>`.
- **Scope:** strictly offline. The runtime CLI (`python -m paperfb`) does NOT auto-invoke this tool when handed a `.pdf` — it expects markdown.
- **Sample layout:** for each evaluation paper, `samples/<paper-id>/` contains `manuscript.md` and `expected_acm_classes.json` (ground-truth classification published with the paper) — both committed. `manuscript.pdf` lives alongside on disk but is **gitignored** (redistribution / size hygiene); contributors regenerate the markdown locally with the prep tool. The Judge harness compares the agentic system's output against the committed fixtures.

#### 4.7 Finnish names list (`scripts/build_finnish_names.py`)

- **Purpose:** produce `data/finnish_names.json` — the curated pool the Profile Creation sampler draws Reviewer names from.
- **Source:** the Finnish nameday calendar (e.g. Yliopiston almanakka tradition). First names only. Stored as a flat list of strings, committed to the repo, no fetch at runtime.
- **Pool size & balance:** ≥50 names, balanced ~50/50 male/female so the gender mix on any Board is roughly even regardless of seed. The script asserts both invariants on output.
- **Output schema:**

  ```json
  ["Aino", "Toivo", "Eero", "Kerttu", "..."]
  ```

- **Rerun behaviour:** the script is run rarely (once at setup, again only if the list needs to grow). Output is deterministic and committed; runtime never refetches.

## 5. Axis vocabularies (default, configurable via `config/axes.yaml`)

**Stances:** `neutral, supportive, critical, skeptical, rigorous, pragmatic, devil's-advocate, visionary`.

**Focuses:** `methods, results, impact, novelty, clarity, related-work, reproducibility, ethics`.

**Core focuses (must be covered on every board):** `methods, results, novelty`. Sampler guarantees each core focus is assigned as some reviewer's primary focus when N ≥ |core_focuses|.

Specialty is NOT an axis vocabulary — it is derived per run from the ACM classes produced by Unit 1.

All three lists are extensible without code changes. Sampler operates on whatever values are in the config.

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
  core_focuses: [methods, results, novelty]   # always covered when N >= len(core_focuses)
  secondary_focus_per_reviewer: true   # set false for v1-lite (single focus per reviewer)
  diversity: strict                    # (stance, primary_focus) unique across reviewers
  seed: null                           # optional, for reproducibility
classification:
  max_classes: 5
paths:
  acm_ccs: data/acm_ccs.json
  finnish_names: data/finnish_names.json
  samples_dir: samples/
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

Report **global** per-run totals only — input/output/total tokens and USD cost (proxy returns `usage.cost`) — at end of run. No per-agent breakdown in v1. Logged, not gating.

## 11. Project structure

```
research-paper-fb/
├── paperfb/
│   ├── __main__.py                 # enables `python -m paperfb <manuscript.md>`
│   ├── main.py                     # CLI entry point
│   ├── contracts.py                # shared cross-agent types (ReviewerTuple, ReviewerProfile, ClassificationResult). ONLY cross-agent import surface.
│   ├── config.py
│   ├── llm_client.py               # openai SDK wrapper, base_url = proxy
│   ├── logging.py                  # run-scoped JSONL logger used by LLM client and tools
│   ├── orchestrator.py             # sequential + asyncio.gather fan-out; imports only agent __init__ + contracts
│   ├── renderer.py                 # pure function, JSONs → markdown
│   └── agents/
│       ├── classification/
│       │   ├── __init__.py         # public API: classify(manuscript, cfg, llm) -> ClassificationResult
│       │   ├── agent.py            # LLM + tool loop (private)
│       │   ├── prompts.py          # system prompt (private)
│       │   └── tools.py            # lookup_acm — agent-private tool (private)
│       ├── profile_creation/
│       │   ├── __init__.py         # public API: create_profiles(classes, cfg, llm) -> list[ReviewerProfile]
│       │   ├── sampler.py          # deterministic tuple sampler (private)
│       │   ├── agent.py            # LLM persona generation (private)
│       │   └── prompts.py
│       └── reviewer/
│           ├── __init__.py         # public API: review(profile, manuscript, cfg, llm) -> Path
│           ├── agent.py            # LLM + tool loop (private)
│           ├── prompts.py
│           └── tools.py            # write_review — agent-private tool (private)
├── scripts/
│   ├── build_acm_ccs.py
│   ├── build_finnish_names.py
│   ├── pdf_to_markdown.py
│   └── judge.py
├── config/
│   ├── default.yaml
│   └── axes.yaml
├── data/
│   ├── acm_ccs.json
│   └── finnish_names.json
├── samples/                        # 3 published-with-CCS papers, prepared offline
│   └── <paper-id>/
│       ├── manuscript.md
│       ├── manuscript.pdf          # gitignored — not committed
│       └── expected_acm_classes.json
├── tests/
│   ├── agents/
│   │   ├── classification/
│   │   │   ├── test_agent.py
│   │   │   └── test_tools.py
│   │   ├── profile_creation/
│   │   │   ├── test_sampler.py
│   │   │   └── test_agent.py
│   │   └── reviewer/
│   │       ├── test_agent.py
│   │       └── test_tools.py
│   ├── test_contracts.py
│   ├── test_config.py
│   ├── test_llm_client.py
│   ├── test_orchestrator.py
│   ├── test_renderer.py
│   ├── test_build_acm_ccs.py
│   ├── test_build_finnish_names.py
│   ├── test_pdf_to_markdown.py
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

## 10a. Decoupling and agent boundaries

Each agent is a **self-contained subpackage** under `paperfb/agents/` with a single public function exposed via `__init__.py`. Everything else (prompts, tools, implementation) is package-private.

**Invariants the code must preserve:**

- An agent subpackage may import from: its own submodules, `paperfb.contracts`, `paperfb.config`, `paperfb.llm_client`, stdlib, and third-party.
- An agent subpackage must NOT import from another agent subpackage. All inter-agent communication is via types in `paperfb.contracts`.
- Only `orchestrator.py` imports multiple agents. It imports each via its public API (`from paperfb.agents.classification import classify`) and wires them together.
- Public function shape is `def <verb>(required_input, cfg: Config, llm: LLMClient) -> OutputType`. Dependencies are explicit function parameters; agents are stateless.
- Tools live with the agent that uses them (e.g. `lookup_acm` under `agents/classification/tools.py`). They are not shared.

**Shared contracts (`paperfb/contracts.py`):**

- `ClassificationResult` — output of Classification Agent
- `ReviewerTuple` — output of Profile Creation sampler
- `ReviewerProfile` — output of Profile Creation Agent, input to Reviewer Agent
- The Review JSON schema (reviewer output) is documented in this module as a dict shape — intentionally kept as a dict because it comes directly from an LLM tool call, but the canonical field list is defined here.

This layout lets two developers work on different agents in parallel with no file conflicts: each agent is a full deliverable (code + prompts + tools + tests).

## 11a. Development environment

- **Python version:** pinned to 3.11 via [mise](https://mise.jdx.dev/) using a `.mise.toml` at repo root.
- **Package + virtualenv manager:** [uv](https://docs.astral.sh/uv/). `uv sync` creates `.venv` and installs all runtime + dev deps from `pyproject.toml`. `uv.lock` committed for reproducible installs.
- **Bootstrap (fresh clone):** `mise install && uv sync`. mise installs both the pinned Python and uv itself, so no prior tooling beyond mise is required on the host.
- **Running commands:** `uv run pytest`, `uv run python -m paperfb ...` — or activate `.venv` manually. mise can also expose `pytest`/`python` directly when `_.python.venv` is configured.

## 12. Testing strategy

- **Unit:** sampler (diversity guarantee + Finnish-name uniqueness), `lookup_acm` (deterministic), renderer (pure function — ratings table + name header), config loader.
- **Integration with mocked LLM:** orchestrator end-to-end with stubbed `llm_client`; verifies wiring, concurrency, error paths (skipped reviewer), tool-call round-trips. Includes a Classification test that asserts the keyword-extraction phase runs and is logged but does NOT show up in the `ClassificationResult` passed downstream.
- **Offline data prep:** `pdf_to_markdown.py` smoke test on a tiny fixture PDF (asserts non-empty markdown body, headings preserved). `build_finnish_names.py` test asserts deterministic output and a minimum pool size (`>= reviewers.count`).
- **TDD for judge:** fixtures of good/bad reviews; score bounds per dimension; implementation satisfies them.
- **Acceptance test (live proxy, `@pytest.mark.slow`):** tiny manuscript fixture, end-to-end run. Asserts: `final_report.md` exists; per-reviewer sections match N; ACM classes present; reviewer stances distinct per diversity rule; reviewer names distinct and drawn from `data/finnish_names.json`; no manuscript text leaks to stdout or logs. Excluded from default `pytest`, included via `pytest -m slow`. Runs in CI on demand only (cost).

## 13. Out of scope / future work

- RAG over external corpora (arXiv, OpenResearch).
- Cross-run memory / adaptability.
- PDF as runtime input — converted offline via `scripts/pdf_to_markdown.py` (§4.6); the runtime CLI still consumes only markdown. Vision input remains out of scope.
- Human-in-the-loop.
- Reviewer tools beyond `write_review` (e.g. related-paper retrieval).
- Synthesis agent that merges reviews into a chair report.
- Embeddings-based ACM classification (current taxonomy is small enough for deterministic lookup).
- Stronger PDF backends (`marker`, `docling`) — swap once `pymupdf4llm` text fidelity becomes the bottleneck.

## 14. Unresolved questions

Open:

- **EDAS rubric capture.** Form identified as EuCNC & 6G Summit EDAS reviewer form. Verbatim 1–5 descriptor labels (13 of 25 cells) not publicly indexed — locked behind authenticated EDAS. Need a TPC-access screenshot or saved review HTML to fill the table. Tracked as a follow-up task in the implementation plan; until done, the agent emits `null` for unknown-cell labels.
- **Sample papers — concrete picks.** 3 papers in this field with publicly published ACM CCS classifications. User will source titles + DOIs and prepare them through the ingestion tool.
- **`pymupdf4llm` table fidelity on the chosen samples.** v1 uses it as default; if extracted markdown loses critical tables on any of the 3 samples, swap-in `marker` becomes a follow-up.

Prior items (resolved):

- ACM CCS source — Offline data-prep tool fetches ACM's CCS 2012 structured dump, parses full tree, generates per-node descriptions via LLM (cached). See §4.5.1.
- CLI UX — `uv run python -m paperfb <manuscript.md>`; only manuscript path required; all other flags optional. Markdown only at the runtime boundary; PDFs are converted offline (§4.6).
- Judge rubric weighting — Equal weighting across 5 Likert dimensions; report per-dimension scores + arithmetic mean.
- Manuscript ingestion — PDF→markdown handled offline via `scripts/pdf_to_markdown.py` (default backend `pymupdf4llm`). See §4.6.
- Reviewer relatability — Profile Creation sampler picks a unique Finnish given name per reviewer from `data/finnish_names.json`; name surfaces in persona prompt and rendered review header. See §4.2, §4.4, §4.7.
- Keyword extraction — embedded in the Classification agent loop; logged but not propagated downstream. `ClassificationResult` contract unchanged. See §4.1.
- Reviewer output schema — mirrors `review-template.txt` (5 numeric ratings + 3 free-text aspects as single strings); `section_comments` dropped in v1.
- Implementation phasing — Judge harness and cost / token-usage reporting are the LAST features built. Earlier tasks may include thin logging hooks but not aggregation. See §15.

## 15. Implementation phasing

The full design above is the v1 target. **Build it in two waves:**

**Wave 1 — core pipeline (must-have for a working v1):**

1. Scaffolding, config, contracts, LLM client.
2. Offline prep: ACM CCS dump, Finnish names list, PDF→markdown.
3. Classification Agent (incl. keyword extraction phase).
4. Profile Creation Agent (sampler with Finnish-name pick + LLM persona step).
5. Reviewer Agent (template-aligned JSON schema).
6. Renderer + Orchestrator + CLI.
7. Mocked-LLM integration tests + live acceptance test.

After Wave 1 the system produces a final report end-to-end on a real manuscript.

**Wave 2 — evaluation & accounting (deferred to the very end):**

1. **Judge harness** (LLM-as-judge, separate from the runtime pipeline). Built test-first against fixture reviews per §9.
2. **Cost / token-usage reporting.** During Wave 1 the LLM client logs raw `usage` blocks per call to JSONL (cheap, no aggregation). Aggregation, per-run totals, USD cost reporting, and any cost-aware behaviour (§10) all land here.
3. **Rubric capture follow-up.** Recover the verbatim EDAS reviewer-form 1–5 descriptor labels from authenticated EDAS access; backfill `data/edas_rubric.json` and update the Reviewer prompt to draw labels from it instead of generating ad-hoc.

Rationale: Waves 1 and 2 are decoupled — the judge has no upstream dependency on the runtime pipeline beyond reading its outputs, and cost reporting is a layer over already-logged data. Pushing both to the end keeps Wave 1 minimal and lets the user see end-to-end behaviour before paying for evaluation infrastructure.
