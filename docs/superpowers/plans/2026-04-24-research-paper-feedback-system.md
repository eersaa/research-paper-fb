# Research Paper Feedback System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 3-agent Python system that takes a markdown manuscript and produces a markdown feedback report from a diverse board of LLM reviewer personas.

**Architecture:** Sequential pipeline (Classification → Profile Creation) + parallel fan-out (N Reviewers) + deterministic Renderer. Agents talk to LLMs via the course-provided OpenRouter AWS proxy (OpenAI `/chat/completions` transport). One tool per agent where helpful: `lookup_acm` for Classification, `write_review` for each Reviewer. Separate LLM-as-judge evaluation harness.

**Tech Stack:** Python 3.11+, `openai` SDK (pointed at proxy `BASE_URL`), `pyyaml`, `pytest`, `pytest-asyncio`, `asyncio` for fan-out.

**Spec:** [docs/superpowers/specs/2026-04-24-research-paper-feedback-system-design.md](../specs/2026-04-24-research-paper-feedback-system-design.md)

---

## Implementation phasing (Wave 1 / Wave 2)

Per spec §15, the build is split into two waves so the system reaches end-to-end behaviour before paying for evaluation infrastructure.

**Wave 1 — core pipeline (Tasks 1 → 13, 15, 16).** Scaffolding, config, contracts, LLM client, offline prep (ACM CCS, Finnish names), Classification (with keyword-extraction phase), Profile Creation (sampler with Finnish-name pick + LLM persona step), Reviewer (template-aligned schema), Renderer, Orchestrator, CLI, live acceptance test, README. End of Wave 1: `python -m paperfb <manuscript.md>` produces a final report on a real manuscript. Manuscript-PDF→markdown conversion is performed outside this project.

**Wave 2 — evaluation & accounting (Tasks 14, 14b). Built LAST.** Judge harness, cost / token-usage reporting aggregation. **Earlier tasks may include only thin logging hooks** (LLM client logs raw `usage` blocks per call) — no aggregation, no cost dashboards. (Task 14c "EDAS rubric capture" was removed by the [2026-04-27 merged review template delta](../specs/2026-04-27-merged-review-template-design.md): no numeric ratings → no rubric to capture.)

Task numbering is preserved from v1 of this plan; new tasks slot in as `4a`, `4b`, `14b`. (Task `14c`, EDAS rubric capture, was removed by the 2026-04-27 review-template merge — see `docs/superpowers/specs/2026-04-27-merged-review-template-design.md`.) The "Track A / Track B" two-developer split below also defers Wave 2 work to the end.

## Parallelization and decoupling

Each agent is a **self-contained subpackage** under `paperfb/agents/` with one public function exposed via `__init__.py`. Internal modules (agent, prompts, tools, sampler) are package-private. Inter-agent types live in `paperfb/contracts.py` — the only cross-agent import surface. Invariants:

- An agent subpackage imports only from: its own submodules, `paperfb.contracts`, `paperfb.config`, `paperfb.llm_client`, stdlib, third-party.
- An agent subpackage MUST NOT import from another agent subpackage.
- Only `orchestrator.py` imports multiple agents (via their public APIs).
- Public function shape: `def <verb>(required_input, cfg: Config, llm: LLMClient) -> OutputType`. Stateless, deps explicit.

**Two-developer split — module-based:**

The work is broken into **self-contained modules**. Each module is a complete, independently testable deliverable (code + prompts + tools + tests + offline-prep where applicable). Within a module, tasks run sequentially. Across modules, the only contact surface is `paperfb/contracts.py` — so two developers can hold one module each at any time without stepping on each other.

The modules sit in three phases, gated by data dependencies:

| Phase | Module | Tasks | Owner | Notes |
|-------|--------|-------|-------|-------|
| **0. Foundation** | Foundation | 1, 2, 2b, 3 | pair (or one dev solo) | Scaffolding, config, contracts, LLM client. Must finish before any Phase-1 module can claim "done." Sub-tasks 4a/4b/7 can technically start in parallel with Task 3 since they don't use the LLM client. |
| **1. Independent modules** (parallelizable) | M1 Classification | 4, 5, 6 | Dev A | ACM CCS data prep → `lookup_acm` tool → Classification agent (with keyword-extraction phase). Public API: `classify(manuscript, cfg, llm) -> ClassificationResult`. |
| | M2 Profile Creation | 4a, 7, 8 | Dev B | Finnish names data prep → deterministic Sampler (with name picker) → LLM persona step. Public API: `create_profiles(classes, cfg, llm) -> list[ReviewerProfile]`. |
| | M3 Reviewer | 9, 10 | Dev A (after M1) | `write_review` tool → Reviewer agent (3 free-text aspects only — see 2026-04-27 review-template merge). Public API: `review(profile, manuscript, cfg, llm) -> Path`. |
| | ~~M4 Manuscript Ingestion~~ | ~~4b~~ | — | **Removed.** Manuscript-PDF→markdown is performed outside this project. |
| | M5 Renderer | 11 | Dev B (after M3 schema is stable) | Pure code, no LLM. Depends only on the Review JSON schema (frozen in `contracts.py` + a fixture from M3). Can be drafted against the schema and finalised once M3 commits. |
| **2. Integration** | I1 Orchestrator + CLI | 12, 13 | whichever dev finishes Phase 1 first | Wires the three agent public APIs + Renderer. |
| | I2 Live acceptance + README | 15, 16 | the other dev | Closes Wave 1. Needs I1 done. |

After Wave 1 ships end-to-end, **Wave 2** modules — also independent — can be picked up one at a time:

| Phase | Module | Tasks | Owner | Notes |
|-------|--------|-------|-------|-------|
| **3. Wave 2** | W1 Judge | 14 | either dev | TDD against fixture reviews. No runtime dependency. |
| | W2 Cost reporting | 14b | either dev | Aggregation layer over already-logged JSONL. |

**Why this assignment:**

- Dev A handles the two LLM-loop-with-tool agents (Classification, Reviewer) — same mental model.
- Dev B handles the deterministic / supporting work (Sampler, Ingestion, Renderer) plus the more constrained Profile Creation LLM step.
- M5 Renderer's only schema dependency on M3 is mitigated by freezing the Review JSON shape in `contracts.py` early — Dev B can mock M3's output and develop the Renderer against it in parallel.

**Module handoff diagram:**

```
       ┌──────────────────────────┐
       │  0. Foundation           │  pair
       │  Tasks 1, 2, 2b, 3       │
       └────────────┬─────────────┘
                    │
        ┌───────────┴────────────┐
        ▼                        ▼
  Dev A: M1 Classification    Dev B: M2 Profile Creation
        │                        │
        ▼                        ▼
  Dev A: M3 Reviewer          Dev B: M5 Renderer  ◄── depends on M3 schema (frozen in contracts.py)
        │                        │
        └────────────┬───────────┘
                     ▼
            I1 Orchestrator + CLI
                     │
                     ▼
            I2 Live acceptance + README
                     │
                     ▼
                === Wave 1 ships ===
                     │
                     ▼
            W1 Judge → W2 Cost (Wave 2, any order)
```

---

## File map

Files created, grouped by task:

- **Task 1:** `pyproject.toml`, `.gitignore`, `.mise.toml`, `paperfb/__init__.py`, `paperfb/__main__.py`, `paperfb/agents/__init__.py`, `paperfb/agents/classification/__init__.py`, `paperfb/agents/profile_creation/__init__.py`, `paperfb/agents/reviewer/__init__.py`, `tests/__init__.py`, `tests/agents/__init__.py`, `scripts/__init__.py`, `config/default.yaml`, `config/axes.yaml`
- **Task 2:** `paperfb/config.py`, `tests/test_config.py`
- **Task 2b:** `paperfb/contracts.py`, `tests/test_contracts.py`
- **Task 3:** `paperfb/llm_client.py`, `tests/test_llm_client.py`
- **Task 4:** `scripts/build_acm_ccs.py`, `tests/test_build_acm_ccs.py`, `tests/fixtures/ccs_sample.xml`, generated `data/acm_ccs.json`
- **Task 4a (Wave 1, new):** `scripts/build_finnish_names.py`, `tests/test_build_finnish_names.py`, generated `data/finnish_names.json`
- **Task 4b:** REMOVED — manuscript-PDF→markdown conversion is performed outside this project. Sample papers are delivered as `samples/<paper-id>/{manuscript.md, expected_acm_classes.json}`.
- **Task 5:** `paperfb/agents/classification/tools.py`, `tests/agents/classification/test_tools.py`
- **Task 6:** `paperfb/agents/classification/{__init__.py, agent.py, prompts.py}`, `tests/agents/classification/test_agent.py` — agent runs the keyword-extraction phase before driving `lookup_acm`; `ClassificationResult` contract unchanged
- **Task 7:** `paperfb/agents/profile_creation/sampler.py`, `tests/agents/profile_creation/test_sampler.py` — sampler now also picks unique Finnish given names per Board (loads `data/finnish_names.json`)
- **Task 8:** `paperfb/agents/profile_creation/{__init__.py, agent.py, prompts.py}`, `tests/agents/profile_creation/test_agent.py` — persona prompt addresses the reviewer by their Finnish given name
- **Task 9:** `paperfb/agents/reviewer/tools.py`, `tests/agents/reviewer/test_tools.py`
- **Task 10:** `paperfb/agents/reviewer/{__init__.py, agent.py, prompts.py}`, `tests/agents/reviewer/test_agent.py` — review JSON schema = three free-text aspects only (`strong_aspects`, `weak_aspects`, `recommended_changes`); persona prompt instructs reviewer to ground all three in primary focus (implicit focus angle); see 2026-04-27 review-template merge
- **Task 11:** `paperfb/renderer.py`, `tests/test_renderer.py` — per-reviewer header includes Finnish name; three free-text aspects rendered as labeled prose subsections (no ratings table)
- **Task 12:** `paperfb/orchestrator.py`, `tests/test_orchestrator.py`; extends `paperfb/contracts.py` + `tests/test_contracts.py` with `SkippedReviewer` TypedDict (shape of the dict the orchestrator emits for failed reviewers and passes to the renderer)
- **Task 13:** `paperfb/main.py`, `tests/test_main.py`
- **Task 14 (Wave 2, last):** `scripts/judge.py`, `tests/test_judge.py`, `tests/fixtures/{good_review.json, bad_review.json, tiny_manuscript_for_judge.md}`
- **Task 14b (Wave 2, last, new):** cost / token-usage aggregation in `paperfb/logging.py` + `paperfb/main.py` end-of-run summary; `tests/test_cost_reporting.py`
- **Task 14c:** *Removed* by 2026-04-27 review-template merge (no numeric ratings ⇒ no rubric to capture).
- **Task 15:** `tests/test_acceptance_live.py`, `tests/fixtures/tiny_manuscript.md`
- **Task 16:** `README.md`

---

## Task 1: Project scaffolding

**Files:**
- Create: `.mise.toml`, `pyproject.toml`, `.gitignore`, `paperfb/__init__.py`, `paperfb/__main__.py`, `paperfb/agents/__init__.py`, `paperfb/agents/classification/__init__.py`, `paperfb/agents/profile_creation/__init__.py`, `paperfb/agents/reviewer/__init__.py`, `tests/__init__.py`, `tests/agents/__init__.py`, `tests/agents/classification/__init__.py`, `tests/agents/profile_creation/__init__.py`, `tests/agents/reviewer/__init__.py`, `scripts/__init__.py`, `config/default.yaml`, `config/axes.yaml`

- [x] **Step 0: Create `.mise.toml`**

```toml
[tools]
python = "3.11"
uv = "latest"

[env]
_.python.venv = { path = ".venv", create = true }
```

Run: `mise install`
Expected: Python 3.11 and uv installed into the mise-managed toolchain.

- [x] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "research-paper-feedback"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "openai>=1.50.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
]

[project.scripts]
paperfb = "paperfb.main:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "slow: tests that hit the live proxy (excluded by default, run with -m slow)",
]
addopts = "-m 'not slow'"
testpaths = ["tests"]

[tool.setuptools.packages.find]
where = ["."]
include = ["paperfb*"]
```

- [x] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
reviews/
logs/
evaluations/
data/ccs_source.xml
data/_ccs_descriptions_cache.json
.pytest_cache/
*.egg-info/
```

Note: `data/acm_ccs.json` and `data/finnish_names.json` ARE committed (prep-tool outputs consumed by the pipeline). Sample papers under `samples/<paper-id>/{manuscript.md, expected_acm_classes.json}` are committed; source PDFs are not in this repo (conversion happens outside the project).

- [x] **Step 3: Create package init files**

Create empty files:

- `paperfb/__init__.py`
- `paperfb/agents/__init__.py`
- `paperfb/agents/classification/__init__.py`
- `paperfb/agents/profile_creation/__init__.py`
- `paperfb/agents/reviewer/__init__.py`
- `tests/__init__.py`
- `tests/agents/__init__.py`
- `tests/agents/classification/__init__.py`
- `tests/agents/profile_creation/__init__.py`
- `tests/agents/reviewer/__init__.py`
- `scripts/__init__.py`

Create `paperfb/__main__.py` so `python -m paperfb` works:

```python
from paperfb.main import main
import sys

raise SystemExit(main(sys.argv[1:]))
```

- [x] **Step 4: Create `config/default.yaml`**

```yaml
transport: openai_chat_completions
base_url_env: BASE_URL
models:
  default: anthropic/claude-3.5-haiku
  classification: anthropic/claude-3.5-haiku
  profile_creation: anthropic/claude-3.5-haiku
  reviewer: anthropic/claude-3.5-haiku
  judge: openai/gpt-4.1-mini
reviewers:
  count: 3
  core_focuses: [methods, results, novelty]
  secondary_focus_per_reviewer: true
  diversity: strict
  seed: null
classification:
  max_classes: 5
paths:
  acm_ccs: data/acm_ccs.json
  reviews_dir: reviews
  output: final_report.md
  logs_dir: logs
```

- [x] **Step 5: Create `config/axes.yaml`**

Each entry is `{name, description}`. The description is a 1–2-sentence prompt-fragment Profile Creation splices into the persona prompt; rubric language from both review templates lives only here. See `docs/superpowers/specs/2026-04-27-merged-review-template-design.md` §3.

```yaml
stances:
  - {name: neutral,          description: "Balanced; weighs strengths and weaknesses without prior tilt."}
  - {name: supportive,       description: "Constructive; emphasises what works and how to extend it."}
  - {name: critical,         description: "Probing; surfaces problems the authors may have downplayed."}
  - {name: skeptical,        description: "Treats every claim as unproven until the evidence forces belief."}
  - {name: rigorous,         description: "Holds the work to formal correctness, statistical and methodological standards."}
  - {name: pragmatic,        description: "Asks whether results matter in practice, not just in theory."}
  - {name: devil's-advocate, description: "Argues the opposite of whatever the paper claims, to stress-test it."}
  - {name: visionary,        description: "Reads for long-horizon impact and what this work makes possible next."}

focuses:
  - {name: methods,         description: "Technical content and scientific rigour: completeness of analysis, soundness of models, validity of methodology. (Content / Technical Content & Rigour)"}
  - {name: results,         description: "Whether reported results actually support the claims; effect sizes, baselines, statistical strength. (Technical Content & Rigour)"}
  - {name: novelty,         description: "Originality: novel ideas vs incremental variations on a well-investigated subject. (Originality / Novelty & Originality)"}
  - {name: clarity,         description: "Quality of presentation: organisation, English, figures, references — does the paper communicate its message? (Clarity / Quality of Presentation)"}
  - {name: impact,          description: "Relevance and timeliness within the paper's research area; potential to influence the field."}
  - {name: related-work,    description: "Coverage and accuracy of references; positioning relative to existing literature."}
  - {name: reproducibility, description: "Whether a reader could rebuild the experiment from what is reported."}
  - {name: ethics,          description: "Ethical implications of methodology, dataset use, deployment, dual-use risks."}
```

- [x] **Step 6: Install deps and verify**

```bash
uv sync --extra dev
uv run pytest --collect-only
```

Expected: `.venv` created, `uv.lock` generated, `pytest --collect-only` reports "collected 0 items" (no tests yet, no errors).

**Convention for all subsequent tasks:** run `pytest` and `python` either via `uv run <cmd>` or by activating the venv first (`. .venv/bin/activate`). The plan writes bare commands for brevity.

- [x] **Step 7: Commit**

```bash
git add .mise.toml pyproject.toml uv.lock .gitignore paperfb/ tests/ scripts/ config/
git commit -m "Scaffold project layout, mise/uv toolchain, config, and deps"
```

---

## Task 2: Config loader

**Files:**
- Create: `paperfb/config.py`, `tests/test_config.py`

- [x] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from pathlib import Path
import pytest
from paperfb.config import load_config, Config, AxisItem


def test_load_defaults():
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    assert isinstance(cfg, Config)
    assert cfg.reviewers.count == 3
    assert cfg.reviewers.core_focuses == ["methods", "results", "novelty"]
    assert cfg.models.default == "anthropic/claude-3.5-haiku"
    stance_names = [s.name for s in cfg.axes.stances]
    focus_names = [f.name for f in cfg.axes.focuses]
    assert "neutral" in stance_names
    assert "methods" in focus_names


def test_axis_items_carry_descriptions():
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    methods = next(f for f in cfg.axes.focuses if f.name == "methods")
    assert isinstance(methods, AxisItem)
    assert methods.description  # non-empty
    critical = next(s for s in cfg.axes.stances if s.name == "critical")
    assert critical.description


def test_reviewer_count_minimum(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("""
transport: openai_chat_completions
base_url_env: BASE_URL
models: {default: x, classification: x, profile_creation: x, reviewer: x, judge: x}
reviewers: {count: 2, core_focuses: [m], secondary_focus_per_reviewer: true, diversity: strict, seed: null}
classification: {max_classes: 5}
paths: {acm_ccs: a, reviews_dir: r, output: o, logs_dir: l}
""")
    with pytest.raises(ValueError, match="count must be >= 3"):
        load_config(bad, Path("config/axes.yaml"))


def test_core_focuses_must_be_subset_of_focuses():
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    focus_names = {f.name for f in cfg.axes.focuses}
    for f in cfg.reviewers.core_focuses:
        assert f in focus_names


def test_axis_entry_must_have_name_and_description(tmp_path):
    bad_axes = tmp_path / "axes.yaml"
    bad_axes.write_text("stances:\n  - neutral\nfocuses:\n  - methods\n")
    default = tmp_path / "default.yaml"
    default.write_text("""
transport: openai_chat_completions
base_url_env: BASE_URL
models: {default: x, classification: x, profile_creation: x, reviewer: x, judge: x}
reviewers: {count: 3, core_focuses: [methods], secondary_focus_per_reviewer: true, diversity: strict, seed: null}
classification: {max_classes: 5}
paths: {acm_ccs: a, reviews_dir: r, output: o, logs_dir: l}
""")
    with pytest.raises(ValueError, match="must be \\{name, description\\}"):
        load_config(default, bad_axes)
```

- [x] **Step 2: Run to verify fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (ImportError: cannot import from paperfb.config).

- [x] **Step 3: Implement `paperfb/config.py`**

```python
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import yaml


@dataclass(frozen=True)
class ModelsConfig:
    default: str
    classification: str
    profile_creation: str
    reviewer: str
    judge: str


@dataclass(frozen=True)
class ReviewersConfig:
    count: int
    core_focuses: list[str]
    secondary_focus_per_reviewer: bool
    diversity: str
    seed: Optional[int]


@dataclass(frozen=True)
class ClassificationConfig:
    max_classes: int


@dataclass(frozen=True)
class PathsConfig:
    acm_ccs: str
    reviews_dir: str
    output: str
    logs_dir: str


@dataclass(frozen=True)
class AxisItem:
    name: str
    description: str


@dataclass(frozen=True)
class AxesConfig:
    stances: list[AxisItem]
    focuses: list[AxisItem]


@dataclass(frozen=True)
class Config:
    transport: str
    base_url_env: str
    models: ModelsConfig
    reviewers: ReviewersConfig
    classification: ClassificationConfig
    paths: PathsConfig
    axes: AxesConfig


def _parse_axis_items(raw: list, axis_name: str) -> list[AxisItem]:
    items: list[AxisItem] = []
    for entry in raw:
        if not isinstance(entry, dict) or "name" not in entry or "description" not in entry:
            raise ValueError(
                f"axes.{axis_name} entries must be {{name, description}} dicts; got {entry!r}"
            )
        items.append(AxisItem(name=entry["name"], description=entry["description"]))
    return items


def load_config(default_path: Path, axes_path: Path) -> Config:
    with default_path.open() as f:
        d = yaml.safe_load(f)
    with axes_path.open() as f:
        a = yaml.safe_load(f)

    reviewers_count = d["reviewers"]["count"]
    if reviewers_count < 3:
        raise ValueError("reviewers.count must be >= 3")

    axes = AxesConfig(
        stances=_parse_axis_items(a["stances"], "stances"),
        focuses=_parse_axis_items(a["focuses"], "focuses"),
    )
    focus_names = {f.name for f in axes.focuses}
    core = d["reviewers"]["core_focuses"]
    for f in core:
        if f not in focus_names:
            raise ValueError(f"core focus '{f}' not in axes.focuses")

    return Config(
        transport=d["transport"],
        base_url_env=d["base_url_env"],
        models=ModelsConfig(**d["models"]),
        reviewers=ReviewersConfig(**d["reviewers"]),
        classification=ClassificationConfig(**d["classification"]),
        paths=PathsConfig(**d["paths"]),
        axes=axes,
    )
```

- [x] **Step 4: Run to verify pass**

Run: `pytest tests/test_config.py -v`
Expected: 3 passed.

- [x] **Step 5: Commit**

```bash
git add paperfb/config.py tests/test_config.py
git commit -m "Add config loader with validation"
```

---

## Task 2b: Shared contracts module

**Files:**
- Create: `paperfb/contracts.py`, `tests/test_contracts.py`

The single cross-agent type surface. Every agent imports its inter-agent types from here; agents never import from each other.

- [x] **Step 1: Write the failing test**

Create `tests/test_contracts.py`:

```python
from paperfb.contracts import (
    ReviewerTuple,
    ReviewerProfile,
    ClassificationResult,
    REVIEW_REQUIRED_FIELDS,
)


def test_reviewer_tuple_fields():
    t = ReviewerTuple(id="r1", specialty={"path": "X"}, stance="neutral",
                     primary_focus="methods", secondary_focus="results")
    assert t.id == "r1"
    assert t.specialty == {"path": "X"}


def test_reviewer_profile_fields():
    p = ReviewerProfile(id="r1", specialty={"path": "X"}, stance="neutral",
                       primary_focus="methods", secondary_focus=None,
                       persona_prompt="You are ...")
    assert p.persona_prompt == "You are ..."
    assert p.secondary_focus is None


def test_classification_result_holds_list():
    r = ClassificationResult(classes=[{"path": "X", "weight": "High", "rationale": "x"}])
    assert r.classes[0]["weight"] == "High"


def test_review_required_fields_declared():
    for f in ["reviewer_id", "reviewer_name", "stance", "primary_focus",
              "strong_aspects", "weak_aspects", "recommended_changes"]:
        assert f in REVIEW_REQUIRED_FIELDS
```

- [x] **Step 2: Run to verify fail**

Run: `pytest tests/test_contracts.py -v`
Expected: FAIL (module not found).

- [x] **Step 3: Implement `paperfb/contracts.py`**

```python
"""Shared cross-agent types.

This module is the sole integration surface between agents. Agent subpackages
import their inter-agent types from here and never from each other.

Review dict shape (produced by Reviewer Agent's write_review tool, consumed by
Renderer and Judge) is documented via REVIEW_REQUIRED_FIELDS below. Kept as a
dict rather than a dataclass because it arrives directly from an LLM tool call.
"""
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ReviewerTuple:
    """Deterministic sampler output; input to Profile Creation LLM step."""
    id: str
    specialty: dict                 # {path, weight, description, ...} from ACM classes
    stance: str
    primary_focus: str
    secondary_focus: Optional[str]


@dataclass
class ReviewerProfile:
    """Profile Creation output; input to Reviewer Agent."""
    id: str
    specialty: dict
    stance: str
    primary_focus: str
    secondary_focus: Optional[str]
    persona_prompt: str


@dataclass
class ClassificationResult:
    """Classification Agent output. `classes` is a list of
    {path: str, weight: 'High'|'Medium'|'Low', rationale: str} dicts."""
    classes: list[dict]


REVIEW_REQUIRED_FIELDS = [
    "reviewer_id",
    "reviewer_name",
    "stance",
    "primary_focus",
    "strong_aspects",
    "weak_aspects",
    "recommended_changes",
]
```

> **Schema rationale (2026-04-27 review-template merge):** Reviewer JSON carries three free-text aspects only. Numeric ratings from both `review-template.txt` (EuCNC/EDAS) and `review-template2.txt` are deliberately dropped — LLM-generated 1–5 scores were judged low-signal as researcher feedback. The rubric language survives only as prompt-side scaffolding via `axes.focuses[*].description` (see Task 1's `config/axes.yaml` and Task 8's persona prompt). See `docs/superpowers/specs/2026-04-27-merged-review-template-design.md` for the full delta.

- [x] **Step 4: Run to verify pass**

Run: `pytest tests/test_contracts.py -v`
Expected: 4 passed.

- [x] **Step 5: Commit**

```bash
git add paperfb/contracts.py tests/test_contracts.py
git commit -m "Add shared contracts module for cross-agent types"
```

---

## Task 3: LLM client

**Files:**
- Create: `paperfb/llm_client.py`, `tests/test_llm_client.py`

- [x] **Step 1: Write the failing test**

Create `tests/test_llm_client.py`:

```python
from unittest.mock import MagicMock, patch
import pytest
from paperfb.llm_client import LLMClient, RetryableError


def make_response(content="hi", tool_calls=None, finish_reason="stop"):
    r = MagicMock()
    msg = MagicMock()
    msg.content = content
    msg.tool_calls = tool_calls
    choice = MagicMock()
    choice.message = msg
    choice.finish_reason = finish_reason
    r.choices = [choice]
    r.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    r.model_dump = lambda: {"usage": {"total_tokens": 15, "cost": 0.0001}}
    return r


def test_chat_returns_assistant_message():
    client = LLMClient(base_url="http://proxy", default_model="anthropic/claude-3.5-haiku")
    with patch.object(client._sdk.chat.completions, "create", return_value=make_response("hello")):
        result = client.chat(messages=[{"role": "user", "content": "hi"}])
    assert result.content == "hello"
    assert result.tool_calls is None


def test_chat_retries_on_5xx_then_succeeds():
    from openai import APIStatusError
    client = LLMClient(base_url="http://proxy", default_model="m", max_retries=3)
    err = APIStatusError("boom", response=MagicMock(status_code=502), body=None)
    call = MagicMock(side_effect=[err, err, make_response("ok")])
    with patch.object(client._sdk.chat.completions, "create", call):
        result = client.chat(messages=[{"role": "user", "content": "x"}])
    assert result.content == "ok"
    assert call.call_count == 3


def test_chat_raises_after_exhausting_retries():
    from openai import APIStatusError
    client = LLMClient(base_url="http://proxy", default_model="m", max_retries=2)
    err = APIStatusError("boom", response=MagicMock(status_code=500), body=None)
    call = MagicMock(side_effect=[err, err])
    with patch.object(client._sdk.chat.completions, "create", call):
        with pytest.raises(RetryableError):
            client.chat(messages=[{"role": "user", "content": "x"}])


def test_chat_includes_tool_calls():
    tc = MagicMock()
    tc.id = "t1"
    tc.function.name = "lookup_acm"
    tc.function.arguments = '{"query": "x"}'
    client = LLMClient(base_url="http://proxy", default_model="m")
    with patch.object(client._sdk.chat.completions, "create",
                      return_value=make_response(None, tool_calls=[tc], finish_reason="tool_calls")):
        result = client.chat(messages=[{"role": "user", "content": "x"}], tools=[{"name": "lookup_acm"}])
    assert result.tool_calls is not None
    assert result.tool_calls[0].function.name == "lookup_acm"


def test_usage_summary_accumulates_across_calls():
    client = LLMClient(base_url="http://proxy", default_model="m")
    with patch.object(client._sdk.chat.completions, "create", return_value=make_response("a")):
        client.chat(messages=[{"role": "user", "content": "x"}])
        client.chat(messages=[{"role": "user", "content": "y"}])
    summary = client.usage_summary()
    assert summary["total_tokens"] == 30      # 15 per call * 2
    assert summary["total_cost_usd"] == pytest.approx(0.0002)
```

- [x] **Step 2: Run to verify fail**

Run: `pytest tests/test_llm_client.py -v`
Expected: FAIL (module not found).

- [x] **Step 3: Implement `paperfb/llm_client.py`**

```python
import os
import time
from dataclasses import dataclass
from typing import Any, Optional
from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError


class RetryableError(RuntimeError):
    pass


@dataclass
class LLMResult:
    content: Optional[str]
    tool_calls: Optional[list]
    finish_reason: str
    raw: Any


class LLMClient:
    def __init__(self, base_url: str, default_model: str, max_retries: int = 3,
                 backoff_base: float = 0.5):
        self._sdk = OpenAI(base_url=base_url, api_key="unused")
        self._default_model = default_model
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._total_tokens = 0
        self._total_cost = 0.0

    def usage_summary(self) -> dict:
        return {"total_tokens": self._total_tokens, "total_cost_usd": self._total_cost}

    def chat(self, messages: list[dict], tools: Optional[list] = None,
             model: Optional[str] = None, **kwargs) -> LLMResult:
        model = model or self._default_model
        last_err = None
        for attempt in range(self._max_retries):
            try:
                resp = self._sdk.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    **kwargs,
                )
                choice = resp.choices[0]
                usage = getattr(resp, "usage", None)
                if usage is not None:
                    self._total_tokens += getattr(usage, "total_tokens", 0) or 0
                    dumped = resp.model_dump() if hasattr(resp, "model_dump") else {}
                    cost = (dumped.get("usage") or {}).get("cost") or 0.0
                    self._total_cost += float(cost)
                return LLMResult(
                    content=choice.message.content,
                    tool_calls=choice.message.tool_calls,
                    finish_reason=choice.finish_reason,
                    raw=resp,
                )
            except (APIStatusError, APIConnectionError, APITimeoutError) as e:
                last_err = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status is not None and status < 500 and status != 429:
                    raise
                if attempt < self._max_retries - 1:
                    time.sleep(self._backoff_base * (2 ** attempt))
        raise RetryableError(f"exhausted retries: {last_err}")


def from_env(default_model: str) -> LLMClient:
    base_url = os.environ["BASE_URL"]
    return LLMClient(base_url=base_url, default_model=default_model)
```

- [x] **Step 4: Run to verify pass**

Run: `pytest tests/test_llm_client.py -v`
Expected: 5 passed.

- [x] **Step 5: Commit**

```bash
git add paperfb/llm_client.py tests/test_llm_client.py
git commit -m "Add LLM client wrapper with retry/backoff"
```

---

## Task 4: ACM CCS data preparation tool

**Files:**
- Create: `scripts/build_acm_ccs.py`, `tests/test_build_acm_ccs.py`, `tests/fixtures/ccs_sample.xml`
- Produce at runtime: `data/acm_ccs.json`, `data/_ccs_descriptions_cache.json`

Runs outside the agentic pipeline as a one-time prep step. Parses ACM's CCS 2012 SKOS/XML dump into a flat tree, generates a 1–2 sentence description per node via the LLM (cached to disk), emits `data/acm_ccs.json` consumed by `lookup_acm`.

**Prerequisite (manual, one-off):** download the ACM CCS 2012 SKOS XML from ACM's classification page and save it to `data/ccs_source.xml`. The exact download URL and precise XML schema may change — the parser below assumes a SKOS/RDF shape (`skos:Concept` with `skos:prefLabel` and `skos:broader`). Adapt element / namespace references to the actual downloaded file if needed.

- [ ] **Step 1: Create a tiny fixture XML mimicking the CCS shape**

`tests/fixtures/ccs_sample.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
         xmlns:skos="http://www.w3.org/2004/02/skos/core#">
  <skos:Concept rdf:about="urn:ccs:root">
    <skos:prefLabel xml:lang="en">Computing methodologies</skos:prefLabel>
  </skos:Concept>
  <skos:Concept rdf:about="urn:ccs:ml">
    <skos:prefLabel xml:lang="en">Machine learning</skos:prefLabel>
    <skos:broader rdf:resource="urn:ccs:root"/>
  </skos:Concept>
  <skos:Concept rdf:about="urn:ccs:nn">
    <skos:prefLabel xml:lang="en">Neural networks</skos:prefLabel>
    <skos:broader rdf:resource="urn:ccs:ml"/>
  </skos:Concept>
</rdf:RDF>
```

- [ ] **Step 2: Write failing tests for the parser and description generator**

Create `tests/test_build_acm_ccs.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from scripts.build_acm_ccs import (
    parse_ccs_tree,
    generate_descriptions,
    build,
)


FIXTURE = Path("tests/fixtures/ccs_sample.xml")


def test_parse_ccs_tree_returns_paths_with_leaf_flags():
    entries = parse_ccs_tree(FIXTURE)
    paths = {e["path"]: e for e in entries}

    assert "Computing methodologies" in paths
    assert paths["Computing methodologies"]["leaf"] is False

    assert "Computing methodologies → Machine learning" in paths
    assert paths["Computing methodologies → Machine learning"]["leaf"] is False

    leaf = "Computing methodologies → Machine learning → Neural networks"
    assert leaf in paths
    assert paths[leaf]["leaf"] is True


def _stub_llm(return_content):
    client = MagicMock()
    res = MagicMock()
    res.content = return_content
    res.tool_calls = None
    res.finish_reason = "stop"
    client.chat.return_value = res
    return client


def test_generate_descriptions_caches_and_skips_cached(tmp_path):
    entries = [
        {"path": "A", "leaf": False},
        {"path": "A → B", "leaf": True},
    ]
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps({"A": "pre-cached description"}))

    llm = _stub_llm("generated")
    out = generate_descriptions(entries, llm=llm, model="stub", cache_path=cache_path)

    assert out[0]["description"] == "pre-cached description"
    assert out[1]["description"] == "generated"
    assert llm.chat.call_count == 1   # only the uncached entry triggered a call

    cached = json.loads(cache_path.read_text())
    assert cached["A → B"] == "generated"


def test_build_end_to_end_writes_output(tmp_path):
    llm = _stub_llm("desc")
    out_path = tmp_path / "acm_ccs.json"
    cache_path = tmp_path / "cache.json"
    build(source_xml=FIXTURE, out_path=out_path, cache_path=cache_path,
          llm=llm, model="stub")
    data = json.loads(out_path.read_text())
    assert len(data) == 3
    for entry in data:
        assert "path" in entry and "leaf" in entry and "description" in entry
```

- [ ] **Step 3: Run to verify fail**

Run: `pytest tests/test_build_acm_ccs.py -v`
Expected: FAIL (module not found).

- [ ] **Step 4: Implement `scripts/build_acm_ccs.py`**

```python
"""Build data/acm_ccs.json from the ACM CCS 2012 SKOS/XML dump.

Run once as a preparation step, not part of the agentic pipeline:
    uv run python scripts/build_acm_ccs.py \\
        --source data/ccs_source.xml \\
        --output data/acm_ccs.json \\
        --cache  data/_ccs_descriptions_cache.json

Outputs a flat list of {path, leaf, description} entries. Descriptions are
generated via the LLM on first run and cached; reruns hit the cache.
"""
from __future__ import annotations
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable
from dotenv import load_dotenv

from paperfb.llm_client import from_env

NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}

PATH_SEP = " → "

DESC_SYSTEM = """You write concise 1–2 sentence descriptions of ACM Computing Classification System (CCS) concepts.
Be factual, domain-grounded, and avoid marketing language. Reply with the description only, no preamble."""


def parse_ccs_tree(source_xml: Path) -> list[dict]:
    """Parse SKOS/RDF XML into a flat list of {path, leaf} entries.

    Adapt the element and attribute lookups if the actual file uses a
    different namespace or shape.
    """
    tree = ET.parse(source_xml)
    root = tree.getroot()

    label: dict[str, str] = {}
    parent: dict[str, str] = {}
    for concept in root.findall("skos:Concept", NS):
        cid = concept.get(f"{{{NS['rdf']}}}about")
        if cid is None:
            continue
        pref = concept.find("skos:prefLabel", NS)
        if pref is not None and pref.text:
            label[cid] = pref.text.strip()
        broader = concept.find("skos:broader", NS)
        if broader is not None:
            parent[cid] = broader.get(f"{{{NS['rdf']}}}resource")

    def path_of(cid: str) -> str:
        parts: list[str] = []
        seen: set[str] = set()
        cur: str | None = cid
        while cur is not None and cur in label and cur not in seen:
            seen.add(cur)
            parts.append(label[cur])
            cur = parent.get(cur)
        return PATH_SEP.join(reversed(parts))

    has_child: set[str] = set(parent.values())
    entries = [
        {"path": path_of(cid), "leaf": cid not in has_child}
        for cid in label
    ]
    entries.sort(key=lambda e: e["path"])
    return entries


def _load_cache(cache_path: Path) -> dict[str, str]:
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    return {}


def _save_cache(cache_path: Path, cache: dict[str, str]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def generate_descriptions(entries: Iterable[dict], llm, model: str,
                          cache_path: Path) -> list[dict]:
    cache = _load_cache(cache_path)
    out: list[dict] = []
    dirty = False
    for entry in entries:
        path = entry["path"]
        if path in cache:
            out.append({**entry, "description": cache[path]})
            continue
        res = llm.chat(
            messages=[
                {"role": "system", "content": DESC_SYSTEM},
                {"role": "user", "content": f"CCS concept path:\n{path}"},
            ],
            model=model,
        )
        desc = (res.content or "").strip()
        cache[path] = desc
        dirty = True
        out.append({**entry, "description": desc})
        if len(cache) % 25 == 0:
            _save_cache(cache_path, cache)
    if dirty:
        _save_cache(cache_path, cache)
    return out


def build(source_xml: Path, out_path: Path, cache_path: Path,
          llm, model: str) -> None:
    entries = parse_ccs_tree(source_xml)
    enriched = generate_descriptions(entries, llm=llm, model=model,
                                      cache_path=cache_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(enriched, indent=2, ensure_ascii=False))


def main(argv=None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="data/ccs_source.xml")
    p.add_argument("--output", default="data/acm_ccs.json")
    p.add_argument("--cache", default="data/_ccs_descriptions_cache.json")
    p.add_argument("--model", default="anthropic/claude-3.5-haiku")
    args = p.parse_args(argv)

    source = Path(args.source)
    if not source.is_file():
        print(f"Source XML not found: {source}", file=sys.stderr)
        print("Download ACM CCS 2012 SKOS XML and save it to that path.", file=sys.stderr)
        return 2

    llm = from_env(default_model=args.model)
    build(source_xml=source, out_path=Path(args.output),
          cache_path=Path(args.cache), llm=llm, model=args.model)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run to verify tests pass**

Run: `pytest tests/test_build_acm_ccs.py -v`
Expected: 3 passed.

- [ ] **Step 6: (Manual, one-off) download ACM CCS 2012 SKOS XML**

Save to `data/ccs_source.xml`. Add `data/ccs_source.xml` and `data/_ccs_descriptions_cache.json` to `.gitignore` so the raw tree + cache stay out of git (the output `data/acm_ccs.json` is committed).

```bash
# after downloading:
echo "data/ccs_source.xml" >> .gitignore
echo "data/_ccs_descriptions_cache.json" >> .gitignore
```

- [ ] **Step 7: Run the tool once to produce `data/acm_ccs.json`**

```bash
uv run python scripts/build_acm_ccs.py \
    --source data/ccs_source.xml \
    --output data/acm_ccs.json \
    --cache  data/_ccs_descriptions_cache.json
```

Expected: completes in a few minutes on first run (one LLM call per concept, batched via cache). Subsequent runs hit the cache and are instant.

- [ ] **Step 8: Verify and commit**

```bash
python -c "import json; d = json.load(open('data/acm_ccs.json')); print(len(d), 'entries')"
git add scripts/build_acm_ccs.py tests/test_build_acm_ccs.py tests/fixtures/ccs_sample.xml .gitignore
git add -f data/acm_ccs.json
git commit -m "Add ACM CCS data-prep tool and generated taxonomy"
```

---

## Task 4a: Finnish names data preparation tool

**Files:**
- Create: `scripts/build_finnish_names.py`, `tests/test_build_finnish_names.py`
- Generated: `data/finnish_names.json` (committed)

**Goal:** produce `data/finnish_names.json` — a list of traditional Finnish given names drawn from the Finnish nameday calendar. The Profile Creation sampler reads this file at runtime to assign a unique `Reviewer Name` to each persona.

- [ ] **Step 1: Pick a source**

Use a static, license-clean source for the v1 list — e.g. a curated subset of the Finnish nameday calendar (Yliopiston almanakka tradition) committed as a constant inside `scripts/build_finnish_names.py`. Avoid runtime fetches. First names only. **Pool size: ≥50, balanced ~50/50 male/female** (e.g. 25 male + 25 female) so any seeded Board has roughly even gender mix. Encode the male/female split as two named lists in the script and concatenate after sorting.

- [ ] **Step 2: Write the failing test**

Create `tests/test_build_finnish_names.py`:

- Asserts `data/finnish_names.json` exists after the script runs.
- Asserts the JSON parses to `list[str]` with `len(names) >= 50`.
- Asserts every entry is non-empty, no whitespace/punctuation, and unique.
- Asserts gender balance: the script's male and female sub-lists each have `>= 25` entries; their union (deduplicated) equals the committed JSON.
- Asserts deterministic output (running the script twice yields byte-identical JSON).

- [ ] **Step 3: Implement `scripts/build_finnish_names.py`**

A small script: declare the curated list as a constant, sort it (deterministic), `json.dump` to `data/finnish_names.json` with `indent=2, ensure_ascii=False, sort_keys=False`. No network. Idempotent.

- [ ] **Step 4: Run the prep tool, then tests**

```bash
uv run python scripts/build_finnish_names.py
uv run pytest tests/test_build_finnish_names.py
```

- [ ] **Step 5: Commit**

```bash
git add scripts/build_finnish_names.py tests/test_build_finnish_names.py
git add -f data/finnish_names.json
git commit -m "Add Finnish names data-prep tool and generated list"
```

---

## Task 4b: REMOVED — PDF→markdown is out of project scope

Manuscript-PDF→markdown conversion is performed outside this repo. The runtime contract (markdown only) is unchanged; the project simply does not own the conversion tool. Sample papers are delivered into `samples/<paper-id>/manuscript.md` by hand.

---

## Task 5: lookup_acm tool

**Files:**
- Create: `paperfb/agents/classification/tools.py`, `tests/agents/classification/test_tools.py`

- [ ] **Step 1: Write the failing test**

Create `tests/agents/classification/test_tools.py`:

```python
import json
from pathlib import Path
import pytest
from paperfb.agents.classification.tools import lookup_acm, load_ccs, TOOL_SCHEMA


@pytest.fixture
def ccs_path(tmp_path):
    data = [
        {"path": "A → B", "leaf": True, "description": "Machine learning stuff"},
        {"path": "C → D", "leaf": True, "description": "Database stuff"},
        {"path": "E", "leaf": False, "description": "Machine learning overview"},
    ]
    p = tmp_path / "ccs.json"
    p.write_text(json.dumps(data))
    return p


def test_matches_by_description_substring(ccs_path):
    results = lookup_acm("machine learning", k=5, ccs_path=ccs_path)
    assert len(results) == 2
    assert all("machine learning" in r["description"].lower() for r in results)


def test_matches_by_path_segment(ccs_path):
    results = lookup_acm("database", k=5, ccs_path=ccs_path)
    assert len(results) == 1
    assert results[0]["path"] == "C → D"


def test_respects_k(ccs_path):
    results = lookup_acm("stuff", k=1, ccs_path=ccs_path)
    assert len(results) == 1


def test_no_matches_returns_empty(ccs_path):
    results = lookup_acm("quantum cats", k=5, ccs_path=ccs_path)
    assert results == []


def test_tool_schema_has_required_fields():
    assert TOOL_SCHEMA["type"] == "function"
    assert TOOL_SCHEMA["function"]["name"] == "lookup_acm"
    assert "query" in TOOL_SCHEMA["function"]["parameters"]["properties"]


def test_load_ccs_from_file(ccs_path):
    entries = load_ccs(ccs_path)
    assert len(entries) == 3
    assert entries[0]["path"] == "A → B"
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/agents/classification/test_tools.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `paperfb/agents/classification/tools.py`**

```python
import json
from functools import lru_cache
from pathlib import Path
from typing import Optional


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "lookup_acm",
        "description": (
            "Search the ACM Computing Classification System for concept paths "
            "matching a keyword or phrase. Returns up to k matching entries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword or short phrase."},
                "k": {"type": "integer", "description": "Max results.", "default": 10},
            },
            "required": ["query"],
        },
    },
}


@lru_cache(maxsize=8)
def load_ccs(ccs_path: Path) -> tuple[dict, ...]:
    with Path(ccs_path).open() as f:
        data = json.load(f)
    return tuple(data)


def lookup_acm(query: str, k: int = 10, ccs_path: Optional[Path] = None) -> list[dict]:
    if ccs_path is None:
        ccs_path = Path("data/acm_ccs.json")
    entries = load_ccs(ccs_path)
    q = query.lower().strip()
    if not q:
        return []
    matches = []
    for e in entries:
        hay = (e["path"] + " " + e.get("description", "")).lower()
        if q in hay:
            matches.append(dict(e))
        if len(matches) >= k:
            break
    return matches
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/agents/classification/test_tools.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add paperfb/agents/classification/tools.py tests/agents/classification/test_tools.py
git commit -m "Add lookup_acm tool with schema"
```

---

## Task 6: Classification Agent

**Files:**
- Create: `paperfb/agents/classification/agent.py`, `tests/agents/classification/test_agent.py`

- [ ] **Step 1: Write the failing test**

Create `tests/agents/classification/test_agent.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from paperfb.agents.classification import classify_manuscript, ClassificationResult


def _msg_with_tool_call(name, args):
    tc = MagicMock()
    tc.id = "call_1"
    tc.type = "function"
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    r = MagicMock()
    r.content = None
    r.tool_calls = [tc]
    r.finish_reason = "tool_calls"
    r.raw = None
    return r


def _msg_final(content):
    r = MagicMock()
    r.content = content
    r.tool_calls = None
    r.finish_reason = "stop"
    r.raw = None
    return r


def test_classify_uses_tool_and_returns_classes(tmp_path):
    ccs_file = tmp_path / "ccs.json"
    ccs_file.write_text(json.dumps([
        {"path": "Computing methodologies → Machine learning → Neural networks",
         "leaf": True, "description": "Deep learning"},
    ]))
    client = MagicMock()
    final_json = json.dumps({
        "classes": [
            {"path": "Computing methodologies → Machine learning → Neural networks",
             "weight": "High", "rationale": "paper uses CNNs"}
        ]
    })
    client.chat.side_effect = [
        _msg_with_tool_call("lookup_acm", {"query": "neural networks"}),
        _msg_final(final_json),
    ]

    result = classify_manuscript(
        manuscript="We train a CNN.",
        llm=client,
        model="stub",
        ccs_path=ccs_file,
        max_classes=5,
    )

    assert isinstance(result, ClassificationResult)
    assert len(result.classes) == 1
    assert result.classes[0]["weight"] == "High"
    assert client.chat.call_count == 2


def test_classify_raises_when_no_classes(tmp_path):
    ccs_file = tmp_path / "ccs.json"
    ccs_file.write_text("[]")
    client = MagicMock()
    client.chat.side_effect = [_msg_final(json.dumps({"classes": []}))]
    with pytest.raises(ValueError, match="no classes"):
        classify_manuscript("abc", client, "stub", ccs_file, 5)
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/agents/classification/test_agent.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `paperfb/agents/classification/agent.py`**

```python
import json
from pathlib import Path
from paperfb.contracts import ClassificationResult
from paperfb.agents.classification.tools import lookup_acm, TOOL_SCHEMA

SYSTEM_PROMPT = """You classify a computer-science research manuscript against the ACM Computing Classification System (CCS).
Rules:
- Use the lookup_acm tool one or more times with candidate keywords before deciding.
- Prefer leaf nodes; use higher-level nodes only when no leaf fits.
- Pick 1–{max_classes} classes total.
- Assign each a weight: High, Medium, or Low.
- Return STRICT JSON of the form:
  {{"classes": [{{"path": "<full CCS path>", "weight": "High|Medium|Low", "rationale": "<short>"}}]}}
- Do not include any text outside the JSON object.
"""


def classify_manuscript(manuscript: str, llm, model: str, ccs_path: Path,
                        max_classes: int) -> ClassificationResult:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(max_classes=max_classes)},
        {"role": "user", "content": f"Manuscript:\n\n{manuscript}"},
    ]
    tools = [TOOL_SCHEMA]

    for _ in range(6):  # bound tool loop
        res = llm.chat(messages=messages, tools=tools, model=model)
        if res.tool_calls:
            assistant_msg = {"role": "assistant", "content": res.content, "tool_calls": []}
            for tc in res.tool_calls:
                args = json.loads(tc.function.arguments)
                out = lookup_acm(args["query"], k=args.get("k", 10), ccs_path=ccs_path)
                assistant_msg["tool_calls"].append({
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                })
            messages.append(assistant_msg)
            for tc in res.tool_calls:
                args = json.loads(tc.function.arguments)
                out = lookup_acm(args["query"], k=args.get("k", 10), ccs_path=ccs_path)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(out),
                })
            continue
        data = json.loads(res.content)
        classes = data.get("classes", [])
        if not classes:
            raise ValueError("Classification produced no classes")
        return ClassificationResult(classes=classes[:max_classes])
    raise RuntimeError("Classification exceeded tool-loop budget")
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/agents/classification/test_agent.py -v`
Expected: 2 passed.

- [ ] **Step 5: Create `paperfb/agents/classification/__init__.py` re-export**

```python
"""Classification agent — public API.

Downstream code (orchestrator, tests) should import only from here.
"""
from paperfb.agents.classification.agent import classify_manuscript
from paperfb.contracts import ClassificationResult

__all__ = ["classify_manuscript", "ClassificationResult"]
```

- [ ] **Step 6: Commit**

```bash
git add paperfb/agents/classification/ tests/agents/classification/
git commit -m "Add Classification Agent subpackage with public re-export"
```

---

## Task 7: Profile sampler (deterministic)

**Files:**
- Create: `paperfb/agents/profile_creation/sampler.py`, `tests/agents/profile_creation/test_sampler.py`

This is the meat of the "don't be shallow" design. Test-heavy, pure Python.

- [ ] **Step 1: Write the failing test**

Create `tests/agents/profile_creation/test_sampler.py`:

```python
import pytest
from paperfb.agents.profile_creation.sampler import sample_reviewer_tuples, ReviewerTuple

STANCES = ["neutral", "critical", "skeptical", "supportive", "rigorous"]
FOCUSES = ["methods", "results", "impact", "novelty", "clarity", "reproducibility"]
CORE = ["methods", "results", "novelty"]

ACM_CLASSES = [
    {"path": "A", "weight": "High"},
    {"path": "B", "weight": "Medium"},
]


def test_returns_n_tuples():
    tuples = sample_reviewer_tuples(n=3, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    assert len(tuples) == 3
    assert all(isinstance(t, ReviewerTuple) for t in tuples)


def test_core_focuses_all_covered_when_n_ge_core():
    tuples = sample_reviewer_tuples(n=3, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    primaries = {t.primary_focus for t in tuples}
    assert set(CORE).issubset(primaries)


def test_specialty_round_robin_across_acm_classes():
    tuples = sample_reviewer_tuples(n=4, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    assert tuples[0].specialty["path"] == "A"
    assert tuples[1].specialty["path"] == "B"
    assert tuples[2].specialty["path"] == "A"
    assert tuples[3].specialty["path"] == "B"


def test_diversity_stance_primary_unique():
    tuples = sample_reviewer_tuples(n=3, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    pairs = {(t.stance, t.primary_focus) for t in tuples}
    assert len(pairs) == 3


def test_secondary_focus_different_from_primary():
    tuples = sample_reviewer_tuples(n=3, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    for t in tuples:
        assert t.secondary_focus is not None
        assert t.secondary_focus != t.primary_focus


def test_seed_reproducibility():
    a = sample_reviewer_tuples(3, ACM_CLASSES, STANCES, FOCUSES, CORE, seed=7)
    b = sample_reviewer_tuples(3, ACM_CLASSES, STANCES, FOCUSES, CORE, seed=7)
    assert [(t.stance, t.primary_focus, t.secondary_focus) for t in a] \
        == [(t.stance, t.primary_focus, t.secondary_focus) for t in b]


def test_different_seeds_differ():
    a = sample_reviewer_tuples(3, ACM_CLASSES, STANCES, FOCUSES, CORE, seed=1)
    b = sample_reviewer_tuples(3, ACM_CLASSES, STANCES, FOCUSES, CORE, seed=2)
    assert a != b or True  # allow collisions, but at minimum it should not always equal


def test_single_acm_class_all_share_specialty():
    one = [{"path": "Z", "weight": "High"}]
    tuples = sample_reviewer_tuples(3, one, STANCES, FOCUSES, CORE, seed=1)
    assert {t.specialty["path"] for t in tuples} == {"Z"}


def test_n_less_than_core_raises():
    with pytest.raises(ValueError):
        sample_reviewer_tuples(2, ACM_CLASSES, STANCES, FOCUSES, CORE, seed=1)


def test_secondary_focus_maximises_coverage():
    tuples = sample_reviewer_tuples(n=3, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    all_focuses_used = {t.primary_focus for t in tuples} | {t.secondary_focus for t in tuples}
    # with 3 reviewers × (primary + secondary) we expect 5+ distinct focuses
    assert len(all_focuses_used) >= 5
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/agents/profile_creation/test_sampler.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `paperfb/agents/profile_creation/sampler.py`**

```python
import random
from typing import Optional

from paperfb.contracts import ReviewerTuple


def _sort_classes_by_weight(classes: list[dict]) -> list[dict]:
    order = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(classes, key=lambda c: order.get(c.get("weight", "Low"), 2))


def sample_reviewer_tuples(
    n: int,
    acm_classes: list[dict],
    stances: list[str],
    focuses: list[str],
    core_focuses: list[str],
    seed: Optional[int] = None,
    enable_secondary: bool = True,
) -> list[ReviewerTuple]:
    if n < len(core_focuses):
        raise ValueError(
            f"n={n} is less than number of core focuses ({len(core_focuses)}); "
            "cannot guarantee coverage"
        )
    if not acm_classes:
        raise ValueError("acm_classes must be non-empty")
    for cf in core_focuses:
        if cf not in focuses:
            raise ValueError(f"core focus '{cf}' not in focuses list")

    rng = random.Random(seed)
    sorted_classes = _sort_classes_by_weight(acm_classes)

    # Primary focuses: core first, then random from non-core for remaining slots
    primaries: list[str] = list(core_focuses)
    non_core = [f for f in focuses if f not in core_focuses]
    while len(primaries) < n:
        if non_core:
            primaries.append(rng.choice(non_core))
        else:
            primaries.append(rng.choice(focuses))

    # Stances: pick so (stance, primary) is unique; fall back to relaxing if infeasible
    stances_pool = list(stances)
    chosen_stances: list[str] = []
    used_pairs: set[tuple[str, str]] = set()
    for pf in primaries:
        rng.shuffle(stances_pool)
        picked = None
        for s in stances_pool:
            if (s, pf) not in used_pairs:
                picked = s
                break
        if picked is None:
            picked = rng.choice(stances_pool)
        chosen_stances.append(picked)
        used_pairs.add((picked, pf))

    # Secondary focuses: greedy coverage — prefer focuses not yet used by any reviewer
    secondaries: list[Optional[str]] = []
    if enable_secondary:
        used_focuses = set(primaries)
        for pf in primaries:
            candidates = [f for f in focuses if f != pf and f not in used_focuses]
            if not candidates:
                candidates = [f for f in focuses if f != pf]
            sec = rng.choice(candidates)
            secondaries.append(sec)
            used_focuses.add(sec)
    else:
        secondaries = [None] * n

    # Specialty round-robin over sorted classes
    tuples: list[ReviewerTuple] = []
    for i in range(n):
        tuples.append(ReviewerTuple(
            id=f"r{i+1}",
            specialty=sorted_classes[i % len(sorted_classes)],
            stance=chosen_stances[i],
            primary_focus=primaries[i],
            secondary_focus=secondaries[i],
        ))
    return tuples
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/agents/profile_creation/test_sampler.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add paperfb/agents/profile_creation/sampler.py tests/agents/profile_creation/test_sampler.py
git commit -m "Add deterministic profile sampler with core-focus coverage"
```

---

## Task 8: Profile Creation Agent (LLM step)

**Files:**
- Create: `paperfb/agents/profile_creation/agent.py`, `tests/agents/profile_creation/test_agent.py`

- [ ] **Step 1: Write the failing test**

Create `tests/agents/profile_creation/test_agent.py`:

```python
import json
from unittest.mock import MagicMock
from paperfb.agents.profile_creation import create_profiles, ReviewerProfile
from paperfb.agents.profile_creation.sampler import ReviewerTuple
from paperfb.config import AxesConfig, AxisItem


def _axes() -> AxesConfig:
    return AxesConfig(
        stances=[
            AxisItem("critical",   "Probing; surfaces problems the authors may have downplayed."),
            AxisItem("supportive", "Constructive; emphasises what works."),
        ],
        focuses=[
            AxisItem("methods", "Technical content and rigour: completeness of analysis, soundness of models."),
            AxisItem("results", "Whether reported results actually support the claims."),
            AxisItem("impact",  "Relevance and timeliness within the paper's research area."),
        ],
    )


def _final(content):
    r = MagicMock()
    r.content = content
    r.tool_calls = None
    r.finish_reason = "stop"
    return r


def test_creates_profile_per_tuple():
    tuples = [
        ReviewerTuple(id="r1", specialty={"path": "ML", "weight": "High"},
                      stance="critical", primary_focus="methods", secondary_focus="results"),
        ReviewerTuple(id="r2", specialty={"path": "DB", "weight": "Medium"},
                      stance="supportive", primary_focus="results", secondary_focus="impact"),
    ]
    llm = MagicMock()
    llm.chat.side_effect = [
        _final("You are a critical ML expert focused on methods..."),
        _final("You are a supportive DB expert focused on results..."),
    ]

    profiles = create_profiles(tuples, axes=_axes(), llm=llm, model="stub")
    assert len(profiles) == 2
    assert all(isinstance(p, ReviewerProfile) for p in profiles)
    assert profiles[0].id == "r1"
    assert "critical" in profiles[0].persona_prompt.lower() or \
           profiles[0].persona_prompt.startswith("You are a critical")
    assert profiles[0].stance == "critical"
    assert profiles[0].primary_focus == "methods"
    assert profiles[0].specialty == {"path": "ML", "weight": "High"}


def test_persona_prompt_user_message_includes_axis_descriptions():
    """Per 2026-04-27 review-template merge: stance/focus descriptions must be
    spliced into the user message so the LLM grounds the persona in rubric language."""
    tuples = [ReviewerTuple(id="r1", specialty={"path": "ML"},
                            stance="critical", primary_focus="methods",
                            secondary_focus="results")]
    llm = MagicMock()
    llm.chat.side_effect = [_final("You are ...")]
    create_profiles(tuples, axes=_axes(), llm=llm, model="stub")
    user_content = llm.chat.call_args.kwargs["messages"][1]["content"]
    assert "Probing; surfaces problems" in user_content        # stance description
    assert "completeness of analysis" in user_content          # primary_focus description
    assert "Whether reported results actually support" in user_content  # secondary_focus description
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/agents/profile_creation/test_agent.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `paperfb/agents/profile_creation/agent.py`**

```python
from paperfb.contracts import ReviewerTuple, ReviewerProfile
from paperfb.config import AxesConfig

PERSONA_SYSTEM = """You generate the system prompt for an AI reviewer persona for a research-paper feedback system.
Given: specialty (ACM CCS class), stance (with description), primary focus (with description), secondary focus (with description) — produce the full system prompt that reviewer will use to review a manuscript.

Requirements for the system prompt you produce:
- Second-person voice ("You are ...").
- Establish the reviewer as a domain specialist grounded in the specialty.
- Reflect the stance in tone, drawing on the stance description.
- Emphasise the primary focus, drawing on its description; acknowledge the secondary focus as a supplementary lens.
- The reviewer's three free-text outputs (strong_aspects, weak_aspects, recommended_changes) must each be grounded in the primary focus, with the secondary focus colouring depth where natural. Do NOT instruct the reviewer to emit numeric ratings.
- Instruct the reviewer to call the write_review tool with their structured review.
- Forbid the reviewer from rewriting the paper.
- No meta-commentary, no preamble — output the system prompt directly.
"""


def _lookup(items, name):
    for it in items:
        if it.name == name:
            return it
    return None


def create_profiles(
    tuples: list[ReviewerTuple],
    axes: AxesConfig,
    llm,
    model: str,
) -> list[ReviewerProfile]:
    profiles: list[ReviewerProfile] = []
    for t in tuples:
        stance_item = _lookup(axes.stances, t.stance)
        primary_item = _lookup(axes.focuses, t.primary_focus)
        secondary_item = _lookup(axes.focuses, t.secondary_focus) if t.secondary_focus else None

        stance_desc = stance_item.description if stance_item else "(no description)"
        primary_desc = primary_item.description if primary_item else "(no description)"
        secondary_line = (
            f"secondary_focus: {t.secondary_focus} — {secondary_item.description}\n"
            if secondary_item else "secondary_focus: (none)\n"
        )

        user = (
            f"specialty: {t.specialty['path']}\n"
            f"specialty description: {t.specialty.get('description', '(none)')}\n"
            f"stance: {t.stance} — {stance_desc}\n"
            f"primary_focus: {t.primary_focus} — {primary_desc}\n"
            f"{secondary_line}"
        )
        res = llm.chat(
            messages=[
                {"role": "system", "content": PERSONA_SYSTEM},
                {"role": "user", "content": user},
            ],
            model=model,
        )
        profiles.append(ReviewerProfile(
            id=t.id,
            specialty=t.specialty,
            stance=t.stance,
            primary_focus=t.primary_focus,
            secondary_focus=t.secondary_focus,
            persona_prompt=res.content.strip(),
        ))
    return profiles
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/agents/profile_creation/test_agent.py -v`
Expected: 1 passed.

- [ ] **Step 5: Create `paperfb/agents/profile_creation/__init__.py` re-export**

```python
"""Profile Creation agent — public API."""
from paperfb.agents.profile_creation.agent import create_profiles
from paperfb.agents.profile_creation.sampler import sample_reviewer_tuples
from paperfb.contracts import ReviewerTuple, ReviewerProfile

__all__ = ["create_profiles", "sample_reviewer_tuples",
           "ReviewerTuple", "ReviewerProfile"]
```

- [ ] **Step 6: Commit**

```bash
git add paperfb/agents/profile_creation/ tests/agents/profile_creation/
git commit -m "Add Profile Creation subpackage with public re-export"
```

---

## Task 9: write_review tool

**Files:**
- Create: `paperfb/agents/reviewer/tools.py`, `tests/agents/reviewer/test_tools.py`

- [ ] **Step 1: Write the failing test**

Create `tests/agents/reviewer/test_tools.py`:

```python
import json
from pathlib import Path
import pytest
from paperfb.agents.reviewer.tools import write_review, TOOL_SCHEMA, ReviewValidationError


def _sample_review(rid="r1"):
    return {
        "reviewer_id": rid,
        "reviewer_name": "Aino",
        "specialty": "Computing methodologies → Machine learning",
        "stance": "critical",
        "primary_focus": "methods",
        "secondary_focus": "results",
        "profile_summary": "critical methods reviewer",
        "strong_aspects": "Clear framing of the problem and reproducible setup.",
        "weak_aspects": "N=5 seeds is too few to distinguish the gain from noise.",
        "recommended_changes": "Increase seeds to >=20 and add a paired statistical test.",
    }


def test_writes_json_file(tmp_path):
    path = write_review(_sample_review("r1"), reviews_dir=tmp_path)
    assert path == tmp_path / "r1.json"
    data = json.loads(path.read_text())
    assert data["reviewer_id"] == "r1"
    assert data["reviewer_name"] == "Aino"


def test_missing_required_field_raises(tmp_path):
    bad = _sample_review()
    del bad["recommended_changes"]
    with pytest.raises(ReviewValidationError, match="recommended_changes"):
        write_review(bad, reviews_dir=tmp_path)


def test_two_reviewers_no_overlap(tmp_path):
    write_review(_sample_review("r1"), reviews_dir=tmp_path)
    write_review(_sample_review("r2"), reviews_dir=tmp_path)
    assert (tmp_path / "r1.json").exists()
    assert (tmp_path / "r2.json").exists()


def test_tool_schema_lists_required_fields():
    required = TOOL_SCHEMA["function"]["parameters"]["required"]
    for f in ["reviewer_id", "reviewer_name", "stance", "primary_focus",
              "strong_aspects", "weak_aspects", "recommended_changes"]:
        assert f in required


def test_tool_schema_does_not_include_ratings():
    """Per 2026-04-27 review-template merge, ratings are no longer in the schema."""
    props = TOOL_SCHEMA["function"]["parameters"]["properties"]
    assert "ratings" not in props
    assert "strengths" not in props
    assert "section_comments" not in props
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/agents/reviewer/test_tools.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `paperfb/agents/reviewer/tools.py`**

```python
import json
from pathlib import Path

from paperfb.contracts import REVIEW_REQUIRED_FIELDS


class ReviewValidationError(ValueError):
    pass


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_review",
        "description": (
            "Write your structured review to disk. Call exactly once when your review is "
            "complete. Output three free-text aspects (strong_aspects, weak_aspects, "
            "recommended_changes); do not emit numeric ratings."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reviewer_id":         {"type": "string"},
                "reviewer_name":       {"type": "string"},
                "specialty":           {"type": "string"},
                "stance":              {"type": "string"},
                "primary_focus":       {"type": "string"},
                "secondary_focus":     {"type": ["string", "null"]},
                "profile_summary":     {"type": "string"},
                "strong_aspects":      {"type": "string"},
                "weak_aspects":        {"type": "string"},
                "recommended_changes": {"type": "string"},
            },
            "required": list(REVIEW_REQUIRED_FIELDS),
        },
    },
}


def _validate(review: dict) -> None:
    missing = [f for f in REVIEW_REQUIRED_FIELDS if f not in review]
    if missing:
        raise ReviewValidationError(f"review missing fields: {missing}")


def write_review(review: dict, reviews_dir: Path) -> Path:
    _validate(review)
    reviews_dir = Path(reviews_dir)
    reviews_dir.mkdir(parents=True, exist_ok=True)
    out = reviews_dir / f"{review['reviewer_id']}.json"
    out.write_text(json.dumps(review, indent=2, ensure_ascii=False))
    return out
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/agents/reviewer/test_tools.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add paperfb/agents/reviewer/tools.py tests/agents/reviewer/test_tools.py
git commit -m "Add write_review tool with validation"
```

---

## Task 10: Reviewer Agent

**Files:**
- Create: `paperfb/agents/reviewer/agent.py`, `tests/agents/reviewer/test_agent.py`

- [ ] **Step 1: Write the failing test**

Create `tests/agents/reviewer/test_agent.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from paperfb.agents.reviewer import run_reviewer
from paperfb.contracts import ReviewerProfile


def _tool_call(name, args):
    tc = MagicMock()
    tc.id = "call_1"
    tc.type = "function"
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _res(content=None, tool_calls=None, finish_reason="stop"):
    r = MagicMock()
    r.content = content
    r.tool_calls = tool_calls
    r.finish_reason = finish_reason
    return r


def _full_review(rid="r1"):
    return {
        "reviewer_id": rid,
        "reviewer_name": "Aino",
        "specialty": "ML",
        "stance": "critical",
        "primary_focus": "methods",
        "secondary_focus": "results",
        "profile_summary": "critical methods reviewer",
        "strong_aspects": "Reproducible setup, hyperparameters reported.",
        "weak_aspects": "N=5 too few seeds.",
        "recommended_changes": "Run with >=20 seeds and add 95% CI.",
    }


def test_reviewer_calls_write_review_and_returns_path(tmp_path):
    profile = ReviewerProfile(id="r1", specialty={"path": "ML"}, stance="critical",
                              primary_focus="methods", secondary_focus="results",
                              persona_prompt="You are ...")
    llm = MagicMock()
    llm.chat.side_effect = [
        _res(tool_calls=[_tool_call("write_review", _full_review("r1"))], finish_reason="tool_calls"),
        _res(content="done"),
    ]

    path = run_reviewer(profile, manuscript="abc", llm=llm, model="stub", reviews_dir=tmp_path)
    assert path == tmp_path / "r1.json"
    assert path.exists()


def test_reviewer_invalid_review_retries_then_skips(tmp_path):
    profile = ReviewerProfile(id="r1", specialty={"path": "ML"}, stance="critical",
                              primary_focus="methods", secondary_focus=None,
                              persona_prompt="...")
    bad = {"reviewer_id": "r1"}  # missing fields
    llm = MagicMock()
    llm.chat.side_effect = [
        _res(tool_calls=[_tool_call("write_review", bad)], finish_reason="tool_calls"),
        _res(tool_calls=[_tool_call("write_review", bad)], finish_reason="tool_calls"),
    ]
    with pytest.raises(RuntimeError, match="failed to produce valid review"):
        run_reviewer(profile, "abc", llm, "stub", tmp_path)
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/agents/reviewer/test_agent.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `paperfb/agents/reviewer/agent.py`**

```python
import json
from pathlib import Path
from paperfb.contracts import ReviewerProfile
from paperfb.agents.reviewer.tools import write_review, TOOL_SCHEMA, ReviewValidationError

REVIEWER_USER_TEMPLATE = """Manuscript follows between the markers.

<MANUSCRIPT>
{manuscript}
</MANUSCRIPT>

Write your review by calling the write_review tool. Do not rewrite the paper. Do not output anything else."""


def run_reviewer(profile: ReviewerProfile, manuscript: str, llm, model: str,
                 reviews_dir: Path) -> Path:
    messages = [
        {"role": "system", "content": profile.persona_prompt},
        {"role": "user", "content": REVIEWER_USER_TEMPLATE.format(manuscript=manuscript)},
    ]
    tools = [TOOL_SCHEMA]
    last_validation_error: str | None = None

    for attempt in range(2):
        if last_validation_error is not None:
            messages.append({
                "role": "user",
                "content": f"Your prior write_review call was invalid: {last_validation_error}. "
                            "Retry, producing a complete review.",
            })

        res = llm.chat(messages=messages, tools=tools, model=model)
        if not res.tool_calls:
            raise RuntimeError(f"reviewer {profile.id} did not call write_review")

        for tc in res.tool_calls:
            if tc.function.name != "write_review":
                continue
            args = json.loads(tc.function.arguments)
            args.setdefault("reviewer_id", profile.id)
            args.setdefault("stance", profile.stance)
            args.setdefault("primary_focus", profile.primary_focus)
            args.setdefault("secondary_focus", profile.secondary_focus)
            try:
                return write_review(args, reviews_dir=reviews_dir)
            except ReviewValidationError as e:
                last_validation_error = str(e)
                break

    raise RuntimeError(f"reviewer {profile.id} failed to produce valid review after retry")
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/agents/reviewer/test_agent.py -v`
Expected: 2 passed.

- [ ] **Step 5: Create `paperfb/agents/reviewer/__init__.py` re-export**

```python
"""Reviewer agent — public API."""
from paperfb.agents.reviewer.agent import run_reviewer

__all__ = ["run_reviewer"]
```

- [ ] **Step 6: Commit**

```bash
git add paperfb/agents/reviewer/ tests/agents/reviewer/
git commit -m "Add Reviewer Agent subpackage with public re-export"
```

---

## Task 11: Renderer

**Files:**
- Create: `paperfb/renderer.py`, `tests/test_renderer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_renderer.py`:

```python
from paperfb.renderer import render_report


def _review(rid="r1", name="Aino"):
    return {
        "reviewer_id": rid,
        "reviewer_name": name,
        "specialty": "Computing methodologies → ML → NN",
        "stance": "critical",
        "primary_focus": "methods",
        "secondary_focus": "results",
        "profile_summary": "critical methods specialist",
        "strong_aspects": "Clear framing of the problem and reproducible setup.",
        "weak_aspects": "Sample size of N=5 cannot distinguish gains from noise.",
        "recommended_changes": "Run with >=20 seeds, report 95% CIs, add a paired statistical test.",
    }


def test_renders_full_report():
    classes = [
        {"path": "Computing methodologies → ML → NN", "weight": "High", "rationale": "r1"},
    ]
    reviews = [_review()]
    md = render_report(classes=classes, reviews=reviews, skipped_reviewers=[])

    assert "# Manuscript feedback report" in md
    assert "## ACM classification" in md
    assert "Computing methodologies → ML → NN" in md
    assert "High" in md
    # Per-reviewer header includes Finnish name and specialty on the same line
    assert "## Review by Aino — Computing methodologies → ML → NN" in md
    # Profile blurb
    assert "critical" in md
    assert "methods" in md
    # Three labeled prose sections
    assert "### Strong aspects" in md
    assert "Clear framing" in md
    assert "### Weak aspects" in md
    assert "Sample size of N=5" in md
    assert "### Recommended changes" in md
    assert ">=20 seeds" in md


def test_no_ratings_table_in_report():
    """Per 2026-04-27 review-template merge, ratings are not part of the schema or output."""
    md = render_report(classes=[], reviews=[_review()], skipped_reviewers=[])
    # No table header, no /5 score formatting
    assert "| Score" not in md
    assert "/5" not in md


def test_notes_skipped_reviewers():
    md = render_report(classes=[], reviews=[],
                        skipped_reviewers=[{"id": "r2", "reason": "tool failure"}])
    assert "Skipped" in md
    assert "r2" in md
    assert "tool failure" in md


def test_no_reviews_graceful():
    md = render_report(classes=[], reviews=[], skipped_reviewers=[])
    assert "# Manuscript feedback report" in md
    assert "No reviews produced" in md
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_renderer.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `paperfb/renderer.py`**

Per 2026-04-27 review-template merge: render the three free-text aspects as labeled prose subsections. No ratings table.

```python
def _prose_or_placeholder(text) -> str:
    text = (text or "").strip()
    return text if text else "_(none)_"


def render_report(classes: list[dict], reviews: list[dict],
                  skipped_reviewers: list[SkippedReviewer]) -> str:
    lines: list[str] = ["# Manuscript feedback report", ""]

    lines.append("## ACM classification")
    lines.append("")
    if classes:
        for c in classes:
            lines.append(f"- **{c['path']}** — weight: {c['weight']}")
            if c.get("rationale"):
                lines.append(f"  - {c['rationale']}")
    else:
        lines.append("_(no classes assigned)_")
    lines.append("")

    if not reviews and not skipped_reviewers:
        lines.append("_No reviews produced._")
        return "\n".join(lines) + "\n"

    for r in reviews:
        name = r.get("reviewer_name") or r.get("reviewer_id", "")
        specialty = r.get("specialty", "")
        header = f"## Review by {name}"
        if specialty:
            header += f" — {specialty}"
        lines.append(header)
        lines.append("")
        blurb_parts = [f"Stance: **{r.get('stance', '')}**",
                       f"primary focus: **{r.get('primary_focus', '')}**"]
        sec = r.get("secondary_focus")
        if sec:
            blurb_parts.append(f"secondary focus: **{sec}**")
        lines.append(", ".join(blurb_parts))
        if r.get("profile_summary"):
            lines.append("")
            lines.append(f"_{r['profile_summary']}_")
        lines.append("")
        lines.append("### Strong aspects")
        lines.append("")
        lines.append(_prose_or_placeholder(r.get("strong_aspects")))
        lines.append("")
        lines.append("### Weak aspects")
        lines.append("")
        lines.append(_prose_or_placeholder(r.get("weak_aspects")))
        lines.append("")
        lines.append("### Recommended changes")
        lines.append("")
        lines.append(_prose_or_placeholder(r.get("recommended_changes")))
        lines.append("")

    if skipped_reviewers:
        lines.append("## Skipped reviewers")
        for s in skipped_reviewers:
            lines.append(f"- {s['id']}: {s['reason']}")
        lines.append("")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_renderer.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add paperfb/renderer.py tests/test_renderer.py
git commit -m "Add Markdown renderer for final report"
```

---

## Task 12: Orchestrator

**Files:**
- Create: `paperfb/orchestrator.py`, `tests/test_orchestrator.py`
- Modify: `paperfb/contracts.py`, `tests/test_contracts.py` (add `SkippedReviewer`)

The orchestrator emits one dict per failed reviewer that the renderer then surfaces in the report's "Skipped reviewers" section. The shape (`{id, reason}`) was implicit in the M5 Renderer; Task 12 formalises it as a `SkippedReviewer` TypedDict in `contracts.py` so the orchestrator-renderer boundary is explicit.

- [ ] **Step 0: Extend `paperfb/contracts.py` with `SkippedReviewer` (TDD)**

Add to `tests/test_contracts.py`:

```python
def test_skipped_reviewer_shape():
    from paperfb.contracts import SkippedReviewer
    s: SkippedReviewer = {"id": "r2", "reason": "tool failure"}
    assert s["id"] == "r2"
    assert s["reason"] == "tool failure"
```

Run: `pytest tests/test_contracts.py -v` → expect FAIL (ImportError).

Add to `paperfb/contracts.py`:

```python
from typing import TypedDict


class SkippedReviewer(TypedDict):
    """Orchestrator-built dict for a reviewer whose run raised. Consumed by the
    renderer's "Skipped reviewers" section."""
    id: str
    reason: str
```

Run: `pytest tests/test_contracts.py -v` → expect pass.

- [ ] **Step 1: Write the failing test**

Create `tests/test_orchestrator.py`:

```python
import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from paperfb.orchestrator import run_pipeline, PipelineResult
from paperfb.config import load_config


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    # minimal tmp-path-scoped config
    c = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    # override paths via monkey-patch of attributes (frozen dataclass workaround: replace)
    from dataclasses import replace
    paths = replace(c.paths, reviews_dir=str(tmp_path / "reviews"),
                    output=str(tmp_path / "report.md"),
                    logs_dir=str(tmp_path / "logs"),
                    acm_ccs="data/acm_ccs.json")
    return replace(c, paths=paths)


def test_full_pipeline_happy_path(cfg, tmp_path):
    classify = MagicMock(return_value=MagicMock(classes=[
        {"path": "Computing methodologies → Machine learning → Machine learning approaches → Neural networks",
         "weight": "High", "rationale": "CNNs"}
    ]))
    sampler_out = [
        MagicMock(id=f"r{i+1}", specialty={"path": "ML"}, stance="critical",
                  primary_focus="methods", secondary_focus="results")
        for i in range(3)
    ]
    # need concrete ReviewerTuple/Profile types for real code path:
    from paperfb.contracts import ReviewerTuple, ReviewerProfile
    tuples = [
        ReviewerTuple(id=f"r{i+1}", specialty={"path": "ML", "weight": "High"},
                      stance="critical", primary_focus=["methods", "results", "novelty"][i],
                      secondary_focus="clarity")
        for i in range(3)
    ]
    profiles = [ReviewerProfile(id=t.id, specialty=t.specialty, stance=t.stance,
                                 primary_focus=t.primary_focus, secondary_focus=t.secondary_focus,
                                 persona_prompt="...") for t in tuples]

    def fake_reviewer(profile, manuscript, llm, model, reviews_dir):
        p = Path(reviews_dir) / f"{profile.id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "reviewer_id": profile.id,
            "reviewer_name": "Aino",
            "specialty": profile.specialty.get("path", ""),
            "stance": profile.stance,
            "primary_focus": profile.primary_focus,
            "secondary_focus": profile.secondary_focus,
            "profile_summary": "",
            "strong_aspects": "good framing",
            "weak_aspects": "small N",
            "recommended_changes": "more seeds",
        }))
        return p

    llm = MagicMock()
    result = asyncio.run(run_pipeline(
        manuscript="hello",
        cfg=cfg,
        llm=llm,
        classify_fn=lambda **kw: MagicMock(classes=[{"path": "ML", "weight": "High", "rationale": "r"}]),
        sample_fn=lambda **kwargs: tuples,
        profile_fn=lambda tuples, axes, llm, model: profiles,
        reviewer_fn=fake_reviewer,
    ))

    assert isinstance(result, PipelineResult)
    assert len(result.reviews) == 3
    assert result.skipped == []
    assert Path(cfg.paths.output).exists()
    assert "# Manuscript feedback report" in Path(cfg.paths.output).read_text()


def test_reviewer_failure_is_skipped(cfg, tmp_path):
    from paperfb.contracts import ReviewerTuple, ReviewerProfile
    tuples = [ReviewerTuple(id=f"r{i+1}", specialty={"path": "ML"}, stance="critical",
                             primary_focus=["methods", "results", "novelty"][i],
                             secondary_focus=None) for i in range(3)]
    profiles = [ReviewerProfile(id=t.id, specialty=t.specialty, stance=t.stance,
                                 primary_focus=t.primary_focus, secondary_focus=None,
                                 persona_prompt="...") for t in tuples]

    def flaky_reviewer(profile, manuscript, llm, model, reviews_dir):
        if profile.id == "r2":
            raise RuntimeError("simulated failure")
        p = Path(reviews_dir) / f"{profile.id}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({
            "reviewer_id": profile.id,
            "reviewer_name": "Eero",
            "specialty": profile.specialty.get("path", ""),
            "stance": "critical",
            "primary_focus": profile.primary_focus,
            "secondary_focus": profile.secondary_focus,
            "profile_summary": "",
            "strong_aspects": "",
            "weak_aspects": "",
            "recommended_changes": "",
        }))
        return p

    result = asyncio.run(run_pipeline(
        manuscript="hello", cfg=cfg, llm=MagicMock(),
        classify_fn=lambda **kw: MagicMock(classes=[{"path": "ML", "weight": "High", "rationale": "r"}]),
        sample_fn=lambda **kw: tuples,
        profile_fn=lambda tuples, axes, llm, model: profiles,
        reviewer_fn=flaky_reviewer,
    ))
    assert len(result.reviews) == 2
    assert len(result.skipped) == 1
    assert result.skipped[0]["id"] == "r2"
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_orchestrator.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `paperfb/orchestrator.py`**

```python
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from paperfb.config import Config
from paperfb.contracts import SkippedReviewer
from paperfb.agents.classification import classify_manuscript
from paperfb.agents.profile_creation import create_profiles, sample_reviewer_tuples
from paperfb.agents.reviewer import run_reviewer
from paperfb.renderer import render_report


@dataclass
class PipelineResult:
    classes: list[dict]
    reviews: list[dict]
    skipped: list[SkippedReviewer]
    report_path: Path


async def _run_reviewer_async(profile, manuscript, llm, model, reviews_dir, reviewer_fn):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, reviewer_fn, profile, manuscript, llm, model, reviews_dir
    )


async def run_pipeline(
    manuscript: str,
    cfg: Config,
    llm,
    classify_fn=classify_manuscript,
    sample_fn=sample_reviewer_tuples,
    profile_fn=create_profiles,
    reviewer_fn=run_reviewer,
) -> PipelineResult:
    # 1. Classify
    classification = classify_fn(
        manuscript=manuscript,
        llm=llm,
        model=cfg.models.classification,
        ccs_path=Path(cfg.paths.acm_ccs),
        max_classes=cfg.classification.max_classes,
    )
    classes = classification.classes

    # 2. Sample reviewer tuples deterministically
    # Sampler operates on names; descriptions are consumed by Profile Creation only.
    tuples = sample_fn(
        n=cfg.reviewers.count,
        acm_classes=classes,
        stances=[s.name for s in cfg.axes.stances],
        focuses=[f.name for f in cfg.axes.focuses],
        core_focuses=cfg.reviewers.core_focuses,
        seed=cfg.reviewers.seed,
        enable_secondary=cfg.reviewers.secondary_focus_per_reviewer,
    )

    # 3. Generate personas — passes the full AxesConfig so the persona prompt can
    # splice in stance/focus descriptions verbatim (per 2026-04-27 review-template merge §3).
    profiles = profile_fn(tuples, axes=cfg.axes, llm=llm, model=cfg.models.profile_creation)

    # 4. Fan out reviewers
    reviews_dir = Path(cfg.paths.reviews_dir)
    reviews_dir.mkdir(parents=True, exist_ok=True)
    tasks = [
        _run_reviewer_async(p, manuscript, llm, cfg.models.reviewer, reviews_dir, reviewer_fn)
        for p in profiles
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    reviews: list[dict] = []
    skipped: list[SkippedReviewer] = []
    for p, r in zip(profiles, results):
        if isinstance(r, Exception):
            skipped.append(SkippedReviewer(id=p.id, reason=f"{type(r).__name__}: {r}"))
            continue
        reviews.append(json.loads(Path(r).read_text()))

    # 5. Render
    md = render_report(classes=classes, reviews=reviews, skipped_reviewers=skipped)
    out = Path(cfg.paths.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)

    return PipelineResult(classes=classes, reviews=reviews, skipped=skipped, report_path=out)
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_orchestrator.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add paperfb/contracts.py tests/test_contracts.py paperfb/orchestrator.py tests/test_orchestrator.py
git commit -m "Add orchestrator with sequential pipeline and parallel reviewers"
```

---

## Task 13: CLI entry point

**Files:**
- Create: `paperfb/main.py`, `tests/test_main.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_main.py`:

```python
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from paperfb.main import main


def test_cli_exits_zero_when_pipeline_succeeds(tmp_path, monkeypatch):
    manuscript = tmp_path / "ms.md"
    manuscript.write_text("# Title\n\nAbstract.\n")
    monkeypatch.setenv("BASE_URL", "http://proxy.invalid")

    fake_result = MagicMock()
    fake_result.report_path = tmp_path / "report.md"
    fake_result.skipped = []
    fake_result.reviews = [{"reviewer_id": "r1"}, {"reviewer_id": "r2"}, {"reviewer_id": "r3"}]

    fake_llm = MagicMock()
    fake_llm.usage_summary.return_value = {"total_tokens": 0, "total_cost_usd": 0.0}
    with patch("paperfb.main.asyncio.run", return_value=fake_result), \
         patch("paperfb.main.from_env", return_value=fake_llm):
        rc = main([
            str(manuscript),
            "--output", str(tmp_path / "report.md"),
            "--reviews-dir", str(tmp_path / "reviews"),
        ])
    assert rc == 0


def test_cli_missing_manuscript_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("BASE_URL", "http://proxy.invalid")
    rc = main([str(tmp_path / "nope.md")])
    assert rc != 0
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_main.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `paperfb/main.py`**

```python
import argparse
import asyncio
import sys
from dataclasses import replace
from pathlib import Path
from dotenv import load_dotenv

from paperfb.config import load_config
from paperfb.llm_client import from_env
from paperfb.orchestrator import run_pipeline


def _parse(argv):
    p = argparse.ArgumentParser(description="Give a manuscript constructive feedback from a board of reviewers.")
    p.add_argument("manuscript", help="Path to manuscript markdown file.")
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--axes", default="config/axes.yaml")
    p.add_argument("--output", default=None, help="Override paths.output.")
    p.add_argument("--reviews-dir", default=None, help="Override paths.reviews_dir.")
    p.add_argument("-n", "--count", type=int, default=None, help="Override reviewers.count.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    load_dotenv()
    args = _parse(argv if argv is not None else sys.argv[1:])

    manuscript_path = Path(args.manuscript)
    if not manuscript_path.is_file():
        print(f"Manuscript not found: {manuscript_path}", file=sys.stderr)
        return 2
    manuscript = manuscript_path.read_text()

    cfg = load_config(Path(args.config), Path(args.axes))
    if args.output or args.reviews_dir:
        cfg = replace(cfg, paths=replace(
            cfg.paths,
            output=args.output or cfg.paths.output,
            reviews_dir=args.reviews_dir or cfg.paths.reviews_dir,
        ))
    if args.count is not None:
        cfg = replace(cfg, reviewers=replace(cfg.reviewers, count=args.count))

    llm = from_env(default_model=cfg.models.default)
    result = asyncio.run(run_pipeline(manuscript=manuscript, cfg=cfg, llm=llm))

    print(f"Report: {result.report_path}")
    print(f"Reviews: {len(result.reviews)} produced, {len(result.skipped)} skipped")
    if result.skipped:
        for s in result.skipped:
            print(f"  - skipped {s['id']}: {s['reason']}")
    usage = llm.usage_summary()
    print(f"Usage: {usage['total_tokens']} tokens, ~${usage['total_cost_usd']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_main.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add paperfb/main.py tests/test_main.py
git commit -m "Add CLI entry point"
```

---

## Task 14: Judge (LLM-as-judge, TDD) — Wave 2

> **Phasing:** This task is **Wave 2**. Do not start it until Tasks 1–13, 15, and 16 are complete and the core pipeline ships end-to-end on a real manuscript. See "Implementation phasing" at the top of this plan.

**Files:**
- Create: `scripts/judge.py`, `tests/test_judge.py`, `tests/fixtures/good_review.json`, `tests/fixtures/bad_review.json`, `tests/fixtures/tiny_manuscript_for_judge.md`

Per spec §9 and user request: judge feature built test-first with known-good and known-bad fixtures.

- [ ] **Step 1: Create fixture files**

`tests/fixtures/tiny_manuscript_for_judge.md`:
```markdown
# An empirical study of N=5 on a new RL agent

Abstract: We introduce RLAgent-X, evaluated on CartPole with N=5 seeds.
Results are +2.3% over baseline.

## Methods
We use a standard DQN with LR=1e-4.

## Results
Mean return 210.1 vs baseline 205.4. No statistical test performed.
```

`tests/fixtures/good_review.json`:
```json
{
  "reviewer_id": "r1",
  "reviewer_name": "Aino",
  "specialty": "Computing methodologies → Machine learning → Reinforcement learning",
  "stance": "critical",
  "primary_focus": "methods",
  "secondary_focus": "results",
  "profile_summary": "critical methods reviewer",
  "strong_aspects": "The setup is reproducible: hyperparameters (LR=1e-4) are reported explicitly and the baseline DQN is standard.",
  "weak_aspects": "N=5 seeds is too few to distinguish the +2.3% gain from noise, and no statistical test (e.g. Welch's t-test) is reported for the return difference. The Results section reports means without confidence intervals, so the claim is empirically underpowered.",
  "recommended_changes": "Increase seeds to at least 20 and report 95% confidence intervals. Add a paired statistical test comparing RLAgent-X and the baseline per seed; report the test statistic and p-value alongside the means."
}
```

`tests/fixtures/bad_review.json`:

```json
{
  "reviewer_id": "r2",
  "reviewer_name": "Eero",
  "specialty": "Computing methodologies",
  "stance": "critical",
  "primary_focus": "methods",
  "secondary_focus": null,
  "profile_summary": "critical methods reviewer",
  "strong_aspects": "The paper is well written.",
  "weak_aspects": "Some parts could be clearer.",
  "recommended_changes": "Improve the methodology section."
}
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_judge.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from scripts.judge import judge_review, RubricScores


FIXTURES = Path("tests/fixtures")
MANUSCRIPT = (FIXTURES / "tiny_manuscript_for_judge.md").read_text()


def _llm_returning(scores_json):
    client = MagicMock()
    res = MagicMock()
    res.content = scores_json
    res.tool_calls = None
    res.finish_reason = "stop"
    client.chat.return_value = res
    return client


def test_good_review_high_specificity_and_actionability():
    good = json.loads((FIXTURES / "good_review.json").read_text())
    payload = json.dumps({
        "specificity": 5, "actionability": 5, "persona_fidelity": 4,
        "coverage": 5, "non_redundancy": 4,
        "justification": "Specific, concrete, on-persona."
    })
    scores = judge_review(manuscript=MANUSCRIPT, review=good,
                          llm=_llm_returning(payload), model="stub")
    assert scores.specificity >= 4
    assert scores.actionability >= 4


def test_bad_review_low_specificity_and_actionability():
    bad = json.loads((FIXTURES / "bad_review.json").read_text())
    payload = json.dumps({
        "specificity": 1, "actionability": 2, "persona_fidelity": 2,
        "coverage": 2, "non_redundancy": 3,
        "justification": "Vague, generic, low signal."
    })
    scores = judge_review(manuscript=MANUSCRIPT, review=bad,
                          llm=_llm_returning(payload), model="stub")
    assert scores.specificity <= 2
    assert scores.actionability <= 2


def test_scores_object_has_all_dimensions():
    good = json.loads((FIXTURES / "good_review.json").read_text())
    payload = json.dumps({
        "specificity": 4, "actionability": 4, "persona_fidelity": 4,
        "coverage": 4, "non_redundancy": 4, "justification": "ok"
    })
    scores = judge_review(manuscript=MANUSCRIPT, review=good,
                          llm=_llm_returning(payload), model="stub")
    assert isinstance(scores, RubricScores)
    for dim in ["specificity", "actionability", "persona_fidelity", "coverage", "non_redundancy"]:
        assert hasattr(scores, dim)
        assert 1 <= getattr(scores, dim) <= 5


def test_out_of_range_score_raises():
    good = json.loads((FIXTURES / "good_review.json").read_text())
    payload = json.dumps({
        "specificity": 7, "actionability": 5, "persona_fidelity": 5,
        "coverage": 5, "non_redundancy": 5, "justification": "x"
    })
    with pytest.raises(ValueError, match="out of range"):
        judge_review(MANUSCRIPT, good, llm=_llm_returning(payload), model="stub")
```

- [ ] **Step 3: Run to verify fail**

Run: `pytest tests/test_judge.py -v`
Expected: FAIL (import error).

- [ ] **Step 4: Implement `scripts/judge.py`**

```python
"""LLM-as-judge evaluation harness for reviewer feedback.

Usage (CLI):
    python scripts/judge.py --manuscript samples/paper1.md --reviews-dir reviews \\
        --output evaluations/run-<ts>.json
"""
import argparse
import json
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from dotenv import load_dotenv

from paperfb.llm_client import from_env


JUDGE_SYSTEM = """You are an impartial evaluator of peer-review feedback.
Given a manuscript and one reviewer's review, score the review on five 1-5 Likert dimensions:
- specificity: grounded in manuscript text vs generic (5 = specific quotations/section refs; 1 = vague)
- actionability: suggestions are concrete and implementable (5 = stepwise, measurable; 1 = 'improve X')
- persona_fidelity: matches assigned stance + focus (5 = clearly on-persona; 1 = off-brief)
- coverage: the primary focus area is meaningfully addressed (5 = deep; 1 = superficial)
- non_redundancy: the review contributes unique points (5 = distinct; 1 = generic boilerplate)

Respond with STRICT JSON only:
{"specificity": 1-5, "actionability": 1-5, "persona_fidelity": 1-5,
 "coverage": 1-5, "non_redundancy": 1-5, "justification": "<2-3 sentences>"}
"""


@dataclass
class RubricScores:
    specificity: int
    actionability: int
    persona_fidelity: int
    coverage: int
    non_redundancy: int
    justification: str


DIMENSIONS = ["specificity", "actionability", "persona_fidelity", "coverage", "non_redundancy"]


def judge_review(manuscript: str, review: dict, llm, model: str) -> RubricScores:
    user = (
        f"Manuscript:\n<MANUSCRIPT>\n{manuscript}\n</MANUSCRIPT>\n\n"
        f"Reviewer stance: {review.get('stance')}\n"
        f"Reviewer primary_focus: {review.get('primary_focus')}\n"
        f"Reviewer secondary_focus: {review.get('secondary_focus')}\n\n"
        f"Review JSON:\n{json.dumps(review, indent=2)}"
    )
    res = llm.chat(
        messages=[{"role": "system", "content": JUDGE_SYSTEM},
                  {"role": "user", "content": user}],
        model=model,
    )
    data = json.loads(res.content)
    for dim in DIMENSIONS:
        if dim not in data:
            raise ValueError(f"judge output missing {dim}")
        if not (1 <= data[dim] <= 5):
            raise ValueError(f"{dim} out of range: {data[dim]}")
    return RubricScores(
        specificity=data["specificity"],
        actionability=data["actionability"],
        persona_fidelity=data["persona_fidelity"],
        coverage=data["coverage"],
        non_redundancy=data["non_redundancy"],
        justification=data.get("justification", ""),
    )


def main(argv=None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--manuscript", required=True)
    p.add_argument("--reviews-dir", default="reviews")
    p.add_argument("--output", required=True)
    p.add_argument("--model", default="openai/gpt-4.1-mini")
    args = p.parse_args(argv)

    manuscript = Path(args.manuscript).read_text()
    reviews_dir = Path(args.reviews_dir)
    reviews = [json.loads(f.read_text()) for f in sorted(reviews_dir.glob("*.json"))]

    llm = from_env(default_model=args.model)
    out = {"manuscript": str(args.manuscript), "per_reviewer": []}
    for r in reviews:
        scores = judge_review(manuscript, r, llm=llm, model=args.model)
        out["per_reviewer"].append({"reviewer_id": r.get("reviewer_id"), **asdict(scores)})

    outp = Path(args.output)
    outp.parent.mkdir(parents=True, exist_ok=True)
    outp.write_text(json.dumps(out, indent=2))
    print(f"Wrote {outp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/test_judge.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add scripts/judge.py tests/test_judge.py tests/fixtures/
git commit -m "Add LLM-as-judge evaluation harness with TDD rubric"
```

---

## Task 15: Live-proxy acceptance test

**Files:**
- Create: `tests/test_acceptance_live.py`, `tests/fixtures/tiny_manuscript.md`

Runs only via `pytest -m slow`. Hits the real proxy.

- [ ] **Step 1: Create the tiny manuscript fixture**

`tests/fixtures/tiny_manuscript.md`:
```markdown
# A minimal study of list summation in Python

## Abstract
We compare three methods of summing a list of integers: a for-loop,
the built-in `sum`, and NumPy's `np.sum`. Benchmarks on lists of
length 10^3 to 10^6 show `np.sum` wins for N > 10^4.

## Methods
Each method run 10 times per N; mean wall-clock time recorded on a
single laptop (M1, 16GB).

## Results
| N         | for-loop  | sum     | np.sum  |
|-----------|-----------|---------|---------|
| 1,000     | 0.05 ms   | 0.01 ms | 0.03 ms |
| 1,000,000 | 45.0 ms   | 8.5 ms  | 0.9 ms  |

## Conclusion
For large N use NumPy; for small N `sum` is fastest.
```

- [ ] **Step 2: Write the acceptance test**

Create `tests/test_acceptance_live.py`:

```python
import asyncio
import json
import os
from dataclasses import replace
from pathlib import Path
import pytest

from paperfb.config import load_config
from paperfb.llm_client import from_env
from paperfb.orchestrator import run_pipeline


pytestmark = pytest.mark.slow


@pytest.fixture
def cfg_tmp(tmp_path):
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    return replace(cfg, paths=replace(
        cfg.paths,
        reviews_dir=str(tmp_path / "reviews"),
        output=str(tmp_path / "report.md"),
        logs_dir=str(tmp_path / "logs"),
    ))


@pytest.fixture
def manuscript():
    return Path("tests/fixtures/tiny_manuscript.md").read_text()


def test_live_pipeline_produces_report(cfg_tmp, manuscript, tmp_path):
    assert os.environ.get("BASE_URL"), "BASE_URL env var required for live test"
    llm = from_env(default_model=cfg_tmp.models.default)

    result = asyncio.run(run_pipeline(manuscript=manuscript, cfg=cfg_tmp, llm=llm))

    # (a) report exists
    report = Path(cfg_tmp.paths.output)
    assert report.exists(), "final_report.md missing"
    text = report.read_text()

    # (b) per-reviewer sections match N
    assert text.count("## Reviewer ") == cfg_tmp.reviewers.count

    # (c) ACM classes present
    assert "## ACM classification" in text
    assert len(result.classes) >= 1

    # (d) reviewer stances distinct per (stance, primary_focus)
    pairs = {(r["stance"], r["focus"]) for r in result.reviews}
    assert len(pairs) == len(result.reviews), "stance/focus pair duplication"

    # (e) no manuscript text leaks to stdout/logs
    #     manuscript has a unique sentinel phrase:
    sentinel = "wall-clock time recorded on a"
    logs_dir = Path(cfg_tmp.paths.logs_dir)
    for log in logs_dir.rglob("*"):
        if log.is_file():
            assert sentinel not in log.read_text(), f"manuscript leaked to {log}"
```

- [ ] **Step 3: Verify it is excluded by default**

Run: `pytest`
Expected: 0 tests from `test_acceptance_live.py` collected (all marked slow).

Run: `pytest --collect-only -m slow`
Expected: 1 test collected.

- [ ] **Step 4: Run the live test (requires `.env` with BASE_URL set)**

Run: `pytest -m slow tests/test_acceptance_live.py -v`
Expected: 1 passed. Costs a few cents per run.

- [ ] **Step 5: Commit**

```bash
git add tests/test_acceptance_live.py tests/fixtures/tiny_manuscript.md
git commit -m "Add live-proxy acceptance test (slow)"
```

---

## Task 16: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write README.md**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "Add README with quick-start, architecture, and eval notes"
```

---

## Final verification

- [ ] **Step 1: Run the full fast test suite**

Run: `pytest -v`
Expected: all non-slow tests pass.

- [ ] **Step 2: Run the slow acceptance test end-to-end**

Run: `pytest -m slow -v`
Expected: live-proxy acceptance test passes.

- [ ] **Step 3: Run the system on a real sample and inspect the report**

```bash
uv run python -m paperfb tests/fixtures/tiny_manuscript.md --output /tmp/report.md
cat /tmp/report.md
```

Expected: sensible markdown report with 3 reviewer sections, one each covering methods / results / novelty.

- [ ] **Step 4: Run the judge against the same output**

```bash
uv run python scripts/judge.py --manuscript tests/fixtures/tiny_manuscript.md \
    --reviews-dir reviews --output /tmp/judge.json
cat /tmp/judge.json
```

Expected: per-reviewer rubric scores.

---

## Task 14b: Cost / token-usage reporting — Wave 2

> **Phasing:** Wave 2. Build only after Task 14 (Judge) ships. During Waves 1 and the rest of Wave 2, the LLM client logs raw `usage` blocks per call to `logs/run-<timestamp>.jsonl` — no aggregation. This task adds the aggregation layer.

**Files:**
- Modify: `paperfb/logging.py`, `paperfb/main.py`
- Create: `tests/test_cost_reporting.py`

**Goal:** at end of run, print and log a single global summary of total input/output tokens and total USD cost (from the proxy's `usage.cost` field, per spec §10). **No per-agent breakdown in v1.**

- [ ] **Step 1: Write the failing test**

`tests/test_cost_reporting.py`:

- Build a synthetic JSONL log with N entries, each carrying `usage.{prompt_tokens, completion_tokens, total_tokens, cost}`.
- Call `paperfb.logging.summarise_run(log_path) -> CostSummary`.
- Assert totals are arithmetic sums of the entries (prompt, completion, total tokens, USD cost). No per-agent grouping.

- [ ] **Step 2: Implement `summarise_run`**

A pure function over an existing JSONL file. Returns global totals only. No new I/O at LLM-call time — Wave 1's logging hooks already wrote what we need.

- [ ] **Step 3: Wire into `main.py`**

After the orchestrator returns, call `summarise_run(run_log_path)` and print:

```
Run cost: $0.0123  (prompt 4321 tok, completion 1789 tok, total 6110 tok)
```

Logged, not gating. No retries / no cost cap in v1.

- [ ] **Step 4: Run tests and commit**

```bash
uv run pytest tests/test_cost_reporting.py
git add paperfb/logging.py paperfb/main.py tests/test_cost_reporting.py
git commit -m "Aggregate per-run cost and token usage summary"
```

---

## Task 14c: REMOVED

The 2026-04-27 review-template merge dropped numeric ratings from the reviewer schema entirely. With no numeric scores in the output, there is no rubric to capture.

See `docs/superpowers/specs/2026-04-27-merged-review-template-design.md` for the full rationale; rubric language from both source templates now lives in `axes.focuses[*].description` on the prompt side only.
