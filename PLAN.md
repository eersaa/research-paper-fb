# Project plan - Agentic research paper feedback system

Goal: give constructive feedback to a researcher on a manuscript, via a small board of LLM reviewer agents with diverse stances and focus areas.

Full design: [docs/superpowers/specs/2026-04-24-research-paper-feedback-system-design.md](docs/superpowers/specs/2026-04-24-research-paper-feedback-system-design.md).

## System operation

1. User provides manuscript (markdown, v1).
2. **Classification Agent** tags the manuscript with ACM CCS classes using `lookup_acm` tool over `data/acm_ccs.json`.
3. **Profile Creation Agent** samples N reviewer tuples `(specialty from ACM classes, stance, primary_focus, secondary_focus)` and generates a persona for each. Core focuses (`methods, results, novelty`) always covered.
4. **Reviewer Agents** (N in parallel) each produce a review JSON via `write_review` tool.
5. **Renderer** (pure code) compiles all review JSONs into `final_report.md`.

Separate evaluation harness: **Judge Agent** scores reports on specificity, actionability, persona-fidelity, coverage, non-redundancy.

## Requirements (met)

- ≥3 agents: Classification, Profile Creation, Reviewer (×N). Judge in eval harness.
- Orchestration pattern: sequential pipeline + parallel fan-out.
- ≥1 tool call: `lookup_acm`, `write_review`.

## Key decisions

- **Input:** markdown only (v1). PDF/vision future work.
- **State:** stateless across runs. Shared-context memory future work.
- **N reviewers:** default 3, configurable. Diversity constraint: `(stance, primary_focus)` unique across reviewers.
- **Persona formula:** `specialty (from ACM classes, round-robin across reviewers) + stance + primary_focus + secondary_focus`. Core focuses always covered.
- **Axes:** configurable in `config/axes.yaml`. Defaults cover 8 stances × 8 focuses; 3 core focuses.
- **ACM tool:** deterministic JSON lookup over a prebuilt CCS dump, not embeddings.
- **Transport:** OpenAI `/chat/completions` via the provided proxy — routes to any course-recommended text model (Claude Haiku, GPT-4.1-mini, Gemini Flash).
- **Default model:** `anthropic/claude-3.5-haiku`; judge uses a different model for bias mitigation.
- **Output:** per-reviewer JSON → rendered markdown. One file per reviewer avoids concurrency issues.
- **Evaluation:** separate LLM-as-judge harness with a 5-dimension Likert rubric. Judge implemented test-first.
- **No-leakage:** only local file writes + proxy as network egress.

## Agent API

OpenRouter via the AWS proxy (`BASE_URL` in `.env`). OpenAI chat completions format. No API key. See `proxy-test.py`.

Framework: bare `openai` Python SDK with `base_url` pointed at the proxy, plus a thin homegrown orchestrator — keeps model choice free across all three recommended options.

## Unresolved questions

- Source of ACM CCS tree (scrape `dl.acm.org/ccs` vs existing dump)?
- Sample papers for eval (which, how many)?
- CLI invocation form and flags?
- Python version pin?
- Judge rubric weighting (equal vs weighted)?
