# Project plan - Agentic research paper feedback system

Goal: give constructive feedback to a researcher on a manuscript, via a small board of LLM reviewer agents with diverse stances and focus areas.

Full design: [docs/superpowers/specs/2026-04-29-ag2-refactor-design.md](docs/superpowers/specs/2026-04-29-ag2-refactor-design.md) (current — AG2 framework). Original v1 design: [docs/superpowers/specs/2026-04-24-research-paper-feedback-system-design.md](docs/superpowers/specs/2026-04-24-research-paper-feedback-system-design.md).

## System operation

Offline prep (run once, committed):

- `scripts/build_acm_ccs.py` → `data/acm_ccs.json`
- `scripts/build_finnish_names.py` → `data/finnish_names.json`
- Sample manuscripts: 3 published-with-CCS papers delivered as `samples/<paper-id>/manuscript.md` (PDF→markdown conversion happens outside this project)

Runtime (AG2 group chat with Pydantic-typed structured outputs):

1. User provides manuscript (markdown only; PDFs are converted offline).
2. **Classification Agent** drives a `lookup_acm` tool loop and emits a `ClassificationResult` (`response_format=ClassificationResult`). Keywords are written to `context_variables` but the post-turn handoff (`classify_to_profile`) forwards only the class paths downstream.
3. **Profile Creation Agent** calls the deterministic `sample_board` tool once and emits a `ProfileBoard` (one `ReviewerProfile` per reviewer) via `response_format=ProfileBoard`. Core focuses (`methods, results, novelty`) always covered; Finnish names unique per board.
4. **Reviewer fan-out** runs inside the `setup_review_board` post-turn handoff: each `ReviewerProfile` is materialised as a one-shot `ConversableAgent` with `response_format=Review` and called sequentially with the manuscript. Successes go into `BoardReport.reviews`; per-reviewer exceptions go into `BoardReport.skipped`. No Chair LLM aggregator — `BoardReport` is built deterministically in Python.
5. **Renderer** (pure code) consumes the in-memory `RunOutput` (= classification + profiles + board) and joins each `Review` to its `ReviewerProfile` by `reviewer_id` to compose `final_report.md`. The serialised `RunOutput` is also written to `evaluations/run-<ts>/run.json` for the Judge.

Separate evaluation harness: **Judge Agent** (`scripts/judge.py`, bypasses AG2) reads `evaluations/run-<ts>/run.json`, scores each `Review` against the matching `ReviewerProfile` on five Likert dimensions (specificity, actionability, persona-fidelity, coverage, non-redundancy), writes `evaluations/run-<ts>/judge.json`.

## Requirements (met)

- ≥3 agents: Classification, Profile Creation, Reviewer (×N). Judge in eval harness.
- Orchestration pattern: sequential AG2 group chat + inline reviewer fan-out (one-shot `generate_reply` per reviewer).
- ≥1 tool call: `lookup_acm`, `sample_board`.

## Key decisions

- **Runtime input:** markdown only. PDF→markdown conversion is performed outside this project; the runtime CLI never sees PDF.
- **State:** stateless across runs. Shared-context memory future work.
- **N reviewers:** default 3, configurable. Diversity constraint: `(stance, primary_focus)` unique across reviewers; reviewer **names** also unique per Board.
- **Persona formula:** `name (Finnish given name from calendar) + specialty (from ACM classes, round-robin across reviewers) + stance + primary_focus + secondary_focus`. Core focuses always covered.
- **Axes:** configurable in `config/axes.yaml`. Defaults cover 8 stances × 8 focuses; 3 core focuses. Each entry carries a `description` that gets spliced into the persona prompt — this is where the rubric language from both review templates lives.
- **ACM tool:** deterministic JSON lookup over a prebuilt CCS dump, not embeddings.
- **Classification flow:** keyword extraction (paper-stated or synthesised) → `lookup_acm` queries → class selection. Keywords logged, not propagated downstream — Profile Creation receives `{classes: [...]}` only.
- **Reviewer schema:** slim — only `reviewer_id` + three free-text aspects (`strong_aspects`, `weak_aspects`, `recommended_changes`). Identity metadata (name, specialty, stance, focus) lives on `ReviewerProfile` and is joined back in by the renderer via `reviewer_id`. Numeric ratings dropped. Rubric language from `review-template.txt` (EuCNC/EDAS) and `review-template2.txt` is absorbed into focus-axis descriptions on the prompt side. See [docs/superpowers/specs/2026-04-27-merged-review-template-design.md](docs/superpowers/specs/2026-04-27-merged-review-template-design.md).
- **Reviewer naming:** sampler picks a unique Finnish given name from `data/finnish_names.json` per reviewer; surfaced in persona prompt and rendered review header.
- **Transport:** OpenAI `/chat/completions` via the provided proxy. Per `2026-04-29-ag2-refactor-design.md` §5.1, every structured-output agent (Classification, Profile Creation, Reviewer) is pinned to OpenAI/Google because Anthropic Claude does not honour `response_format` through the proxy.
- **Default model:** `openai/gpt-4.1-mini` for all chat agents; Judge runs on `google/gemini-2.5-flash-lite` (different family, bias mitigation).
- **Output:** `RunOutput` (Pydantic, in-memory: `classification + profiles + board`) → rendered markdown at `final_report.md`; serialised `RunOutput` at `evaluations/run-<ts>/run.json` (Judge input). No per-reviewer JSON files written at runtime.
- **Logging:** AG2 `safeguard_llm_outputs` hooks on classification + profile_creation agents write `logs/run-<ts>.jsonl`. Any string content >1024 bytes is stored as `{sha256, bytes}` rather than cleartext, so the manuscript body never lands on disk in plaintext.
- **Evaluation:** separate LLM-as-judge harness with a 5-dimension Likert rubric. Judge implemented test-first.
- **Implementation phasing:** Wave 1 = core pipeline end-to-end (Classification → Profile Creation → Reviewers → Renderer + offline prep). Wave 2 (deferred to last) = Judge harness, cost / token-usage reporting aggregation, EDAS rubric capture.
- **No-leakage:** only local file writes + proxy as network egress.

## Agent API

OpenRouter via the AWS proxy (`BASE_URL` in `.env`). OpenAI chat completions format. No API key.

Framework: `ag2==0.12.1` (`autogen` package) — `ConversableAgent` + `UserProxyAgent` in a `DefaultPattern` group chat, with `FunctionTarget` post-turn handoffs. Structured outputs via Pydantic `response_format`. See [docs/superpowers/specs/2026-04-29-ag2-refactor-design.md](docs/superpowers/specs/2026-04-29-ag2-refactor-design.md) for full architecture.

## Development environment

- **Python version:** 3.11, pinned via [mise](https://mise.jdx.dev/).
- **Packages + virtualenv:** [uv](https://docs.astral.sh/uv/) (`uv sync` creates `.venv` and installs deps + dev extras; `uv.lock` committed).
- **Bootstrap:** `mise install && uv sync`. mise also installs uv, so one tool bootstraps the rest.

## Unresolved questions

- **Sample papers — concrete picks.** 3 published-with-CCS papers needed as evaluation fixtures. User sources titles + DOIs and delivers each as `samples/<paper-id>/{manuscript.md, expected_acm_classes.json}` (PDF→markdown conversion is performed outside this project).

Prior items resolved:

- ACM CCS source → offline data-prep tool downloads CCS 2012, parses full tree, generates per-node descriptions via LLM (cached), emits `data/acm_ccs.json`.
- CLI → `uv run python -m paperfb <manuscript.md>`; markdown only at runtime; PDF→markdown handled outside the project.
- Judge rubric → equal weighting across 5 Likert dimensions; per-dimension + arithmetic mean.
- Manuscript ingestion → out of project scope; markdown delivered by hand.
- Reviewer relatability → unique Finnish given name per reviewer from committed calendar list.
- Keyword extraction → inside Classification loop; logged not propagated.
- Reviewer schema → three free-text aspects only; numeric ratings dropped (2026-04-27 review-template merge). `section_comments` dropped earlier in v1.
- EDAS rubric labels → no longer needed; reviewer no longer emits numeric ratings, so the Wave 2 Task 14c follow-up is removed.
- Build order → Wave 1 (core pipeline) before Wave 2 (judge + cost reporting + rubric capture).
