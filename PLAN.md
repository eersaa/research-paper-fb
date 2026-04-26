# Project plan - Agentic research paper feedback system

Goal: give constructive feedback to a researcher on a manuscript, via a small board of LLM reviewer agents with diverse stances and focus areas.

Full design: [docs/superpowers/specs/2026-04-24-research-paper-feedback-system-design.md](docs/superpowers/specs/2026-04-24-research-paper-feedback-system-design.md).

## System operation

Offline prep (run once, committed):

- `scripts/build_acm_ccs.py` → `data/acm_ccs.json`
- `scripts/build_finnish_names.py` → `data/finnish_names.json`
- `scripts/pdf_to_markdown.py` → `samples/<paper-id>/manuscript.md` (3 published-with-CCS papers, used for evaluation)

Runtime:

1. User provides manuscript (markdown only; PDFs are converted offline).
2. **Classification Agent** runs a two-phase loop: extract paper-keywords (or synthesise from title/abstract/headings), then drive `lookup_acm` queries to pick 2–5 ACM CCS classes with weights. Keywords are logged but not propagated downstream.
3. **Profile Creation Agent** samples N reviewer tuples `(specialty from ACM classes, stance, primary_focus, secondary_focus)`, picks a unique Finnish given name per reviewer from `data/finnish_names.json`, and generates a persona for each. Core focuses (`methods, results, novelty`) always covered.
4. **Reviewer Agents** (N in parallel) each emit a review JSON via `write_review`. Schema mirrors `review-template.txt` (EuCNC/6G EDAS form): five 1–5 ratings with descriptor labels + three free-text aspects (Strong / Weak / Recommended Changes).
5. **Renderer** (pure code) compiles all review JSONs into `final_report.md`. Each review section opens with the reviewer's Finnish name and shows the ratings table.

Separate evaluation harness (deferred — built last): **Judge Agent** scores reports on specificity, actionability, persona-fidelity, coverage, non-redundancy.

## Requirements (met)

- ≥3 agents: Classification, Profile Creation, Reviewer (×N). Judge in eval harness.
- Orchestration pattern: sequential pipeline + parallel fan-out.
- ≥1 tool call: `lookup_acm`, `write_review`.

## Key decisions

- **Runtime input:** markdown only. PDFs are converted offline via `scripts/pdf_to_markdown.py` (default backend `pymupdf4llm`); the runtime CLI never sees PDF.
- **State:** stateless across runs. Shared-context memory future work.
- **N reviewers:** default 3, configurable. Diversity constraint: `(stance, primary_focus)` unique across reviewers; reviewer **names** also unique per Board.
- **Persona formula:** `name (Finnish given name from calendar) + specialty (from ACM classes, round-robin across reviewers) + stance + primary_focus + secondary_focus`. Core focuses always covered.
- **Axes:** configurable in `config/axes.yaml`. Defaults cover 8 stances × 8 focuses; 3 core focuses.
- **ACM tool:** deterministic JSON lookup over a prebuilt CCS dump, not embeddings.
- **Classification flow:** keyword extraction (paper-stated or synthesised) → `lookup_acm` queries → class selection. Keywords logged, not propagated downstream — Profile Creation receives `{classes: [...]}` only.
- **Reviewer schema:** mirrors `review-template.txt` (EuCNC/6G EDAS form). 5 numeric ratings each with descriptor label, plus 3 free-text aspects (single strings).
- **Reviewer naming:** sampler picks a unique Finnish given name from `data/finnish_names.json` per reviewer; surfaced in persona prompt and rendered review header.
- **Transport:** OpenAI `/chat/completions` via the provided proxy — routes to any course-recommended text model (Claude Haiku, GPT-4.1-mini, Gemini Flash).
- **Default model:** `anthropic/claude-3.5-haiku`; judge uses a different model for bias mitigation.
- **Output:** per-reviewer JSON → rendered markdown. One file per reviewer avoids concurrency issues.
- **Evaluation:** separate LLM-as-judge harness with a 5-dimension Likert rubric. Judge implemented test-first.
- **Implementation phasing:** Wave 1 = core pipeline end-to-end (Classification → Profile Creation → Reviewers → Renderer + offline prep). Wave 2 (deferred to last) = Judge harness, cost / token-usage reporting aggregation, EDAS rubric capture.
- **No-leakage:** only local file writes + proxy as network egress.

## Agent API

OpenRouter via the AWS proxy (`BASE_URL` in `.env`). OpenAI chat completions format. No API key. See `proxy-test.py`.

Framework: bare `openai` Python SDK with `base_url` pointed at the proxy, plus a thin homegrown orchestrator — keeps model choice free across all three recommended options.

## Development environment

- **Python version:** 3.11, pinned via [mise](https://mise.jdx.dev/).
- **Packages + virtualenv:** [uv](https://docs.astral.sh/uv/) (`uv sync` creates `.venv` and installs deps + dev extras; `uv.lock` committed).
- **Bootstrap:** `mise install && uv sync`. mise also installs uv, so one tool bootstraps the rest.

## Unresolved questions

- EDAS rubric labels — 13/25 cells unknown (form gated behind authenticated EDAS). Capture via TPC screenshot or saved review HTML; tracked as Wave 2 Task 14c.
- `pymupdf4llm` table fidelity on chosen samples — swap to `marker` if blocking.

Prior items resolved:

- ACM CCS source → offline data-prep tool downloads CCS 2012, parses full tree, generates per-node descriptions via LLM (cached), emits `data/acm_ccs.json`.
- CLI → `uv run python -m paperfb <manuscript.md>`; markdown only at runtime; PDFs converted offline.
- Judge rubric → equal weighting across 5 Likert dimensions; per-dimension + arithmetic mean.
- Manuscript ingestion → offline `scripts/pdf_to_markdown.py` (default `pymupdf4llm`).
- Reviewer relatability → unique Finnish given name per reviewer from committed calendar list.
- Keyword extraction → inside Classification loop; logged not propagated.
- Reviewer schema → mirrors `review-template.txt`; `section_comments` dropped in v1.
- Build order → Wave 1 (core pipeline) before Wave 2 (judge + cost reporting + rubric capture).
