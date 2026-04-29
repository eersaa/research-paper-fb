# Research Paper Feedback System

Agentic Python system: takes a markdown research manuscript, produces a markdown report of feedback from a small board of LLM reviewer personas with diverse stances and focus areas.

## Quick start

```bash
# Prereqs: mise (https://mise.jdx.dev/) — installs everything else.
mise install          # Python 3.11 + uv from .mise.toml
uv sync --extra dev   # creates .venv and installs deps + dev extras

# BASE_URL for the course proxy is already in .env

# Run it
uv run python -m paperfb path/to/manuscript.md --output final_report.md
```

Add `-n 5` to use 5 reviewers, `--config path/to/your.yaml` to override the config.

## Architecture

AG2 group-chat pipeline (`ag2==0.12.1`) with Pydantic-typed structured outputs.

```
manuscript.md
    ↓
Classification Agent  ──(tool: lookup_acm)──► data/acm_ccs.json → ClassificationResult
    ↓
Profile Creation Agent ──(tool: sample_board)──► N personas → ProfileBoard
    ↓
Reviewer Agents (inline fan-out, N parallel) → BoardReport
    ↓
Renderer (pure Python, reads RunOutput)
    ↓
final_report.md   +   evaluations/run-<ts>/run.json
```

Pipeline: `UserProxyAgent → Classification → ProfileCreation → inline reviewer fan-out → BoardReport`. Renderer is pure code; joins reviews to profiles by `reviewer_id`.

See [docs/superpowers/specs/2026-04-29-ag2-refactor-design.md](docs/superpowers/specs/2026-04-29-ag2-refactor-design.md) for full architecture.

## Non-leakage property

The manuscript is transmitted only to the configured LLM proxy (`BASE_URL`). No telemetry, no third-party calls. Outputs land in `final_report.md`, `logs/`, `evaluations/` — all local.

## Evaluation

```bash
# After running the pipeline, judge each reviewer's review:
uv run python scripts/judge.py --manuscript path/to/manuscript.md
# → evaluations/run-<UTC-timestamp>.json
```

Each reviewer is scored on five 1–5 Likert dimensions: `specificity`, `actionability`, `persona_fidelity`, `coverage`, `non_redundancy`. Each dimension has its own justification. The output JSON also includes a `mean` per reviewer and a `board_mean` across all reviewers. The judge defaults to `cfg.models.judge` (different from the reviewer model) to reduce self-preference bias.

## Tests

```bash
uv run pytest                  # fast tests only (default)
uv run pytest -m slow          # live-proxy acceptance test (costs cents per run)
```
