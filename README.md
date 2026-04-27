# Research Paper Feedback System

Agentic Python system: takes a markdown research manuscript, produces a markdown report of feedback from a small board of LLM reviewer personas with diverse stances and focus areas.

## Quick start

```bash
# Prereqs: mise (https://mise.jdx.dev/) — installs everything else.
mise install          # Python 3.11 + uv from .mise.toml
uv sync --extra dev   # creates .venv and installs deps + dev extras

# BASE_URL for the course proxy is already in .env

# Run it
uv run python -m paperfb path/to/manuscript.md --output report.md
```

Add `-n 5` to use 5 reviewers, `--config path/to/your.yaml` to override the config.

## Architecture

Three agents + a deterministic renderer. Separate evaluation harness.

```
manuscript.md
    ↓
Classification Agent  ──(tool: lookup_acm)──► data/acm_ccs.json
    ↓   ACM classes
Profile Creation Agent (sampler + LLM) ──► N personas
    ↓
Reviewer Agents (N in parallel) ──(tool: write_review)──► reviews/r*.json
    ↓
Renderer (pure Python)
    ↓
final_report.md
```

See [docs/superpowers/specs/2026-04-24-research-paper-feedback-system-design.md](docs/superpowers/specs/2026-04-24-research-paper-feedback-system-design.md) for the full design.

## Non-leakage property

The manuscript is transmitted only to the configured LLM proxy (`BASE_URL`). No telemetry, no third-party calls. Outputs land in `reviews/`, `final_report.md`, `logs/`, `evaluations/` — all local.

## Evaluation

```bash
uv run python scripts/judge.py --manuscript samples/paper.md --reviews-dir reviews --output evaluations/run.json
```

Scores each reviewer's feedback on a 5-dimension Likert rubric: specificity, actionability, persona-fidelity, coverage, non-redundancy. Uses a different model from reviewers by default to reduce self-preference bias.

## Tests

```bash
uv run pytest                  # fast tests only (default)
uv run pytest -m slow          # live-proxy acceptance test (costs cents per run)
```
