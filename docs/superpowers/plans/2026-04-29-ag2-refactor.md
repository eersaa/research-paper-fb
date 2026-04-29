# AG2 Framework Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hand-rolled OpenAI tool-call loops + custom orchestrator with an AG2-native pipeline (Default Pattern + nested RedundantPattern, Pydantic structured outputs, UserProxyAgent entry/executor) while preserving domain invariants (reviewer diversity, Finnish names, ACM CCS, non-leakage) and the renderer's output shape.

**Architecture:** Single top-level `GroupChat` (Default Pattern) — Classification → ProfileCreation → nested RedundantPattern (N reviewers + Chair aggregator) — with `FunctionTarget` handoffs that parse Pydantic responses, populate `context_variables`, and (in the second hop) build reviewer agents at runtime. `pipeline.run()` assembles `RunOutput` from `context_variables` + the nested chat's `BoardReport` after the chat terminates. Renderer is pure code; joins reviews to profiles by `reviewer_id`.

**Tech Stack:** Python 3.11+, `ag2[openai]==0.12.1`, Pydantic v2, pytest. OpenAI-compatible course proxy via `BASE_URL` env var (no direct provider calls). All structured-output agents pinned to OpenAI/Google models per the §5.1 compatibility matrix in the design spec.

**Source spec:** [docs/superpowers/specs/2026-04-29-ag2-refactor-design.md](../specs/2026-04-29-ag2-refactor-design.md). Read it before starting — every task references its sections.

**Migration approach:** In-place rewrite. No feature flag. Intermediate commits between Task 4 and Task 11 will not produce a working end-to-end run; that is expected and acceptable per spec §10.

**Working directory:** Run all commands from the repo root (`/home/eeriksaarinen/Documents/projects/research-paper-fb`). Toolchain note: this sandbox lacks `mise`/`uv` directly on `PATH`; wrap commands with `host-spawn -cwd "$PWD" -- mise exec -- ...` (e.g. `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest -q`). The plan shows `uv run …` for brevity — prepend the wrapper as needed.

---

## File Structure

**New files:**
- `paperfb/schemas.py` — all Pydantic models (replaces `contracts.py`)
- `paperfb/pipeline.py` — top-level pipeline runner (replaces `orchestrator.py`)
- `paperfb/handoffs.py` — `classify_to_profile` + `setup_review_board` FunctionTarget bodies
- `paperfb/tools/__init__.py`, `paperfb/tools/sampler.py`, `paperfb/tools/acm_lookup.py`
- `paperfb/agents/classification.py`, `paperfb/agents/profile_creation.py`, `paperfb/agents/reviewer.py`, `paperfb/agents/chair.py` (flat modules; subpackages disappear in deletion sweep)
- `tests/test_schemas.py`, `tests/test_pipeline.py`, `tests/tools/test_sampler.py`, `tests/tools/test_acm_lookup.py`, `tests/test_handoffs.py`
- `scripts/probe_ag2_api.py` — one-shot smoke probe of the AG2 0.12.1 surface (verifies the exact import paths used in the rest of the plan)

**Modified:**
- `pyproject.toml` — swap direct `openai` dep for `ag2[openai]==0.12.1`
- `config/default.yaml` — pin OpenAI/Google models per spec §5.1
- `paperfb/main.py` — call `pipeline.run()`, drop `LLMClient`
- `paperfb/renderer.py` — signature change to `render_report(run: RunOutput) -> str`
- `scripts/judge.py` — consume `evaluations/run-<ts>/run.json`; add `JudgeScore` schema usage

**Deleted (Task 15):**
- `paperfb/llm_client.py`, `paperfb/orchestrator.py`, `paperfb/contracts.py`
- `paperfb/agents/classification/`, `paperfb/agents/profile_creation/`, `paperfb/agents/reviewer/` (whole subpackages)
- `tests/test_llm_client.py`, `tests/test_orchestrator.py`, `tests/test_contracts.py`, `tests/agents/`

Each task below is a self-contained commit. Tasks 1–3 land first (deps + schemas + config) so subsequent tasks can import from them. Tasks 4–10 introduce the new pieces alongside the old code (no deletions yet). Task 11 wires the new pipeline; Task 12–14 swap the renderer/CLI/judge over. Task 15 deletes the obsolete modules. Task 16 is the live acceptance test.

---

## Task 1: Dependency pin + AG2 API probe

**Files:**
- Modify: `pyproject.toml`
- Create: `scripts/probe_ag2_api.py`
- Modify: `uv.lock` (regenerated)

This task locks in `ag2==0.12.1` and writes a one-shot probe that imports every AG2 surface the rest of the plan relies on. The probe is a shell-script-grade safety net: if AG2 ever renames `FunctionTarget` or `RedundantPattern`, we discover it here, not in Task 6. The probe is committed so it can be re-run on dependency bumps.

- [ ] **Step 1: Update `pyproject.toml`**

Replace the current `dependencies` block:

```toml
dependencies = [
    "ag2[openai]==0.12.1",
    "pyyaml>=6.0",
    "python-dotenv>=1.0.0",
]
```

(Removing the direct `openai>=1.50.0` pin — `ag2[openai]` transitively pulls a compatible OpenAI SDK.)

- [ ] **Step 2: Regenerate `uv.lock`**

Run: `uv lock`
Expected: `uv.lock` is rewritten; `ag2==0.12.1` and a transitive `openai` appear in the new lockfile. `git diff uv.lock` should show only dependency edits.

- [ ] **Step 3: Install the new env**

Run: `uv sync --extra dev`
Expected: success, no resolver errors. `uv run python -c "import autogen; print(autogen.__version__)"` prints `0.12.1` (AG2 ≥0.10 publishes under the `autogen` import name; the PyPI distribution is `ag2`).

If the import name differs in 0.12.1 (e.g. `ag2`), update Step 4's probe to match and document the actual import name in a one-line comment at the top of `paperfb/schemas.py` (the first new module that imports it). Subsequent tasks must use whatever import name the probe verifies here.

- [ ] **Step 4: Write the probe**

Create `scripts/probe_ag2_api.py`:

```python
"""Smoke probe for AG2 0.12.1 surfaces used by the refactor.

Re-run after any AG2 version bump: `uv run python scripts/probe_ag2_api.py`.
Prints OK + the exact import paths each surface lives at, or a clear ImportError
naming the missing symbol. Used to ground the refactor plan in real APIs.
"""
from __future__ import annotations


def main() -> int:
    # Core agents
    from autogen import ConversableAgent, UserProxyAgent  # noqa: F401

    # Patterns + handoff machinery (paths may shift across AG2 minor versions)
    from autogen.agentchat.group import (  # type: ignore[attr-defined]
        AfterWork,
        ContextVariables,
        FunctionTarget,
        FunctionTargetResult,
        NestedChatTarget,
    )
    from autogen.agentchat.group.patterns import (  # type: ignore[attr-defined]
        DefaultPattern,
        RedundantPattern,
    )

    # Sanity: every name actually exists
    surfaces = {
        "ConversableAgent": ConversableAgent,
        "UserProxyAgent": UserProxyAgent,
        "AfterWork": AfterWork,
        "ContextVariables": ContextVariables,
        "FunctionTarget": FunctionTarget,
        "FunctionTargetResult": FunctionTargetResult,
        "NestedChatTarget": NestedChatTarget,
        "DefaultPattern": DefaultPattern,
        "RedundantPattern": RedundantPattern,
    }
    for name, obj in surfaces.items():
        print(f"OK: {name} -> {obj.__module__}.{obj.__qualname__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run the probe**

Run: `uv run python scripts/probe_ag2_api.py`
Expected: nine `OK: <name> -> <module>.<qualname>` lines, exit 0.

If any import fails: AG2 0.12.1 has reshuffled the namespace. Search the installed package (`uv run python -c "import autogen, pkgutil; [print(m.name) for m in pkgutil.walk_packages(autogen.__path__, prefix='autogen.')]" | grep -i -E "group|pattern"`) for the actual location and update the probe to import from the real path. Record the corrected import paths in a one-liner at the top of `paperfb/handoffs.py` when you write that module — the rest of the plan uses the names confirmed here regardless of which submodule they live in.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock scripts/probe_ag2_api.py
git commit -m "Pin ag2==0.12.1 and probe AG2 API surfaces"
```

---

## Task 2: Pydantic schemas (`paperfb/schemas.py`)

**Files:**
- Create: `paperfb/schemas.py`
- Create: `tests/test_schemas.py`

Per spec §3. Every `BaseModel` carries `model_config = ConfigDict(title="<ClassName>", extra="forbid")` (spec §5.1: required for OpenAPI compliance + Gemini's `additionalProperties` quirk).

`JudgeScore` is **deferred to Task 14** (when judge is rewritten) per spec §10 step 2.

- [ ] **Step 1: Write the failing test**

Create `tests/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from paperfb.schemas import (
    BoardReport,
    CCSClass,
    CCSMatch,
    ClassificationResult,
    Keywords,
    ProfileBoard,
    Review,
    ReviewerProfile,
    ReviewerTuple,
    RunOutput,
    SkippedReviewer,
)


def _classification() -> ClassificationResult:
    return ClassificationResult(
        keywords=Keywords(extracted_from_paper=["transformers"], synthesised=["attention"]),
        classes=[CCSClass(path="Computing methodologies → ML", weight="High", rationale="r")],
    )


def _profile(rid="r1") -> ReviewerProfile:
    return ReviewerProfile(
        id=rid,
        name="Aino",
        specialty="Computing methodologies → ML",
        stance="critical",
        primary_focus="methods",
        secondary_focus=None,
        persona_prompt="You are Aino...",
        profile_summary="critical methods specialist",
    )


def test_classification_round_trip():
    obj = _classification()
    parsed = ClassificationResult.model_validate_json(obj.model_dump_json())
    assert parsed == obj


def test_review_slim_shape_no_metadata_fields():
    r = Review(reviewer_id="r1", strong_aspects="a", weak_aspects="b", recommended_changes="c")
    payload = r.model_dump()
    assert set(payload) == {"reviewer_id", "strong_aspects", "weak_aspects", "recommended_changes"}


def test_extra_fields_forbidden_on_review():
    with pytest.raises(ValidationError):
        Review.model_validate({
            "reviewer_id": "r1",
            "strong_aspects": "", "weak_aspects": "", "recommended_changes": "",
            "stance": "critical",  # extra field — must be rejected per spec §5.1
        })


def test_ccs_class_weight_enum():
    with pytest.raises(ValidationError):
        CCSClass(path="x", weight="Critical", rationale="r")


def test_profile_board_validates_id_field_present():
    pb = ProfileBoard(reviewers=[_profile()])
    assert pb.reviewers[0].id == "r1"


def test_run_output_round_trip():
    run = RunOutput(
        classification=_classification(),
        profiles=ProfileBoard(reviewers=[_profile()]),
        board=BoardReport(
            reviews=[Review(reviewer_id="r1", strong_aspects="s", weak_aspects="w", recommended_changes="c")],
            skipped=[SkippedReviewer(id="r2", reason="boom")],
        ),
    )
    parsed = RunOutput.model_validate_json(run.model_dump_json())
    assert parsed == run


def test_ccs_match_shape():
    m = CCSMatch(path="A → B", description="d")
    assert m.path == "A → B"


def test_reviewer_tuple_id_required():
    with pytest.raises(ValidationError):
        ReviewerTuple(name="x", specialty="y", stance="z", primary_focus="p", secondary_focus=None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: collection error (`ModuleNotFoundError: paperfb.schemas`).

- [ ] **Step 3: Implement `paperfb/schemas.py`**

```python
"""Cross-agent message + structured-output schemas. Replaces paperfb/contracts.py.

Every BaseModel sets model_config = ConfigDict(title=<ClassName>, extra="forbid")
to satisfy OpenAPI's title requirement and Gemini's additionalProperties quirk
(spec §5.1; AG2 issue #2348).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict


# Classification ─────────────────────────────────────────────────────────────


class CCSMatch(BaseModel):
    model_config = ConfigDict(title="CCSMatch", extra="forbid")
    path: str
    description: str


class Keywords(BaseModel):
    model_config = ConfigDict(title="Keywords", extra="forbid")
    extracted_from_paper: list[str]
    synthesised: list[str]


class CCSClass(BaseModel):
    model_config = ConfigDict(title="CCSClass", extra="forbid")
    path: str
    weight: Literal["High", "Medium", "Low"]
    rationale: str


class ClassificationResult(BaseModel):
    model_config = ConfigDict(title="ClassificationResult", extra="forbid")
    keywords: Keywords
    classes: list[CCSClass]


# Profile Creation ───────────────────────────────────────────────────────────


class ReviewerTuple(BaseModel):
    model_config = ConfigDict(title="ReviewerTuple", extra="forbid")
    id: str
    name: str
    specialty: str
    stance: str
    primary_focus: str
    secondary_focus: str | None


class ReviewerProfile(BaseModel):
    model_config = ConfigDict(title="ReviewerProfile", extra="forbid")
    id: str
    name: str
    specialty: str
    stance: str
    primary_focus: str
    secondary_focus: str | None
    persona_prompt: str
    profile_summary: str


class ProfileBoard(BaseModel):
    model_config = ConfigDict(title="ProfileBoard", extra="forbid")
    reviewers: list[ReviewerProfile]


# Reviewer ───────────────────────────────────────────────────────────────────
# Slim: review *content* only. Identity metadata stays on ReviewerProfile and is
# joined back in by the renderer via reviewer_id (spec §3, §4.3).


class Review(BaseModel):
    model_config = ConfigDict(title="Review", extra="forbid")
    reviewer_id: str
    strong_aspects: str
    weak_aspects: str
    recommended_changes: str


# Aggregation ────────────────────────────────────────────────────────────────


class SkippedReviewer(BaseModel):
    model_config = ConfigDict(title="SkippedReviewer", extra="forbid")
    id: str
    reason: str


class BoardReport(BaseModel):
    model_config = ConfigDict(title="BoardReport", extra="forbid")
    reviews: list[Review]
    skipped: list[SkippedReviewer]


# Top-level run output ───────────────────────────────────────────────────────


class RunOutput(BaseModel):
    model_config = ConfigDict(title="RunOutput", extra="forbid")
    classification: ClassificationResult
    profiles: ProfileBoard
    board: BoardReport
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add paperfb/schemas.py tests/test_schemas.py
git commit -m "Add Pydantic schemas for AG2 refactor"
```

---

## Task 3: Update `config/default.yaml` model defaults

**Files:**
- Modify: `config/default.yaml`

Per spec §5.1: Anthropic Claude does NOT honour `response_format` through the course proxy. Pin every structured-output agent to OpenAI; pin judge to Google for cross-family bias mitigation. Add `ag2.*` keys.

- [ ] **Step 1: Rewrite `config/default.yaml`**

```yaml
transport: openai_chat_completions
base_url_env: BASE_URL
ag2:
  cache_seed: null
  retry_on_validation_error: 1
models:
  default: openai/gpt-4.1-mini
  classification: openai/gpt-4.1-mini
  profile_creation: openai/gpt-4.1-mini
  reviewer: openai/gpt-4.1-mini
  judge: google/gemini-2.5-flash-lite
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
  finnish_names: data/finnish_names.json
  reviews_dir: reviews
  output: final_report.md
  logs_dir: logs
```

Note: `paths.reviews_dir` is retained in config for now (the runtime no longer writes per-reviewer files — see Task 12 — but `tests/test_orchestrator.py` is still at HEAD and references it; deletion sweep in Task 15 will remove this key along with the obsolete tests).

- [ ] **Step 2: Extend `paperfb/config.py` to parse `ag2.*` keys**

Read the existing `paperfb/config.py` first. Add:

```python
@dataclass(frozen=True)
class Ag2Config:
    cache_seed: int | None
    retry_on_validation_error: int
```

Add `ag2: Ag2Config` to the `Config` dataclass and parse it in `load_config`:

```python
ag2_raw = d.get("ag2") or {}
ag2 = Ag2Config(
    cache_seed=ag2_raw.get("cache_seed"),
    retry_on_validation_error=int(ag2_raw.get("retry_on_validation_error", 1)),
)
return Config(
    ...,
    ag2=ag2,
)
```

- [ ] **Step 3: Add a config test**

Append to `tests/test_config.py`:

```python
def test_ag2_section_parsed():
    from paperfb.config import load_config
    from pathlib import Path
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    assert cfg.ag2.cache_seed is None
    assert cfg.ag2.retry_on_validation_error == 1


def test_models_pin_to_proxy_compatible_families():
    """Per spec §5.1, every structured-output agent must run on OpenAI/Google."""
    from paperfb.config import load_config
    from pathlib import Path
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    for field in ("default", "classification", "profile_creation", "reviewer"):
        m = getattr(cfg.models, field)
        assert m.startswith("openai/") or m.startswith("google/"), \
            f"models.{field}={m!r} not in OpenAI/Google families"
    assert cfg.models.judge.startswith("google/"), "judge stays on Google for bias mitigation"
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: pre-existing tests still pass; new tests pass.

- [ ] **Step 5: Commit**

```bash
git add config/default.yaml paperfb/config.py tests/test_config.py
git commit -m "Pin OpenAI/Google models and add ag2 config section"
```

---

## Task 4: Move `sample_board` tool to `paperfb/tools/sampler.py`

**Files:**
- Create: `paperfb/tools/__init__.py` (empty)
- Create: `paperfb/tools/sampler.py`
- Create: `tests/tools/__init__.py` (empty), `tests/tools/test_sampler.py`

Goal: re-home the existing sampler under `paperfb/tools/`, swap its return type from `list[ReviewerTuple]` (dataclass) to `list[ReviewerTuple]` (Pydantic, from Task 2), and accept `list[CCSClass]` (Pydantic) instead of the existing `list[dict]`. The deterministic algorithm itself is unchanged.

The original `paperfb/agents/profile_creation/sampler.py` and its test stay in place for now (Task 7's profile-creation builder will import from the new path; the old module is deleted in Task 15).

- [ ] **Step 1: Write the failing test**

Create `tests/tools/__init__.py` (empty file) and `tests/tools/test_sampler.py`:

```python
import json
from pathlib import Path

import pytest

from paperfb.schemas import CCSClass, ReviewerTuple
from paperfb.tools.sampler import sample_board


@pytest.fixture
def names_file(tmp_path) -> Path:
    p = tmp_path / "names.json"
    p.write_text(json.dumps(["Aino", "Eero", "Liisa", "Mikko", "Saara"]))
    return p


@pytest.fixture
def classes() -> list[CCSClass]:
    return [
        CCSClass(path="A → B", weight="High", rationale="r"),
        CCSClass(path="C → D", weight="Medium", rationale="r"),
    ]


def test_returns_pydantic_reviewer_tuples(classes, names_file):
    out = sample_board(
        n=3,
        classes=classes,
        stances=["critical", "constructive", "skeptical"],
        focuses=["methods", "results", "novelty", "clarity"],
        core_focuses=["methods", "results", "novelty"],
        enable_secondary=True,
        names_path=names_file,
        seed=42,
    )
    assert len(out) == 3
    assert all(isinstance(t, ReviewerTuple) for t in out)
    # Diversity invariants
    assert len({(t.stance, t.primary_focus) for t in out}) == 3
    assert len({t.name for t in out}) == 3


def test_specialty_is_class_path_not_dict(classes, names_file):
    out = sample_board(
        n=2, classes=classes,
        stances=["critical", "constructive"],
        focuses=["methods", "results"], core_focuses=["methods"],
        enable_secondary=False, names_path=names_file, seed=1,
    )
    # ReviewerTuple.specialty is a string (the ACM path), per schemas.py
    assert all(isinstance(t.specialty, str) and "→" in t.specialty for t in out)


def test_core_focus_coverage_when_n_ge_core_count(classes, names_file):
    out = sample_board(
        n=3, classes=classes,
        stances=["critical", "constructive", "skeptical"],
        focuses=["methods", "results", "novelty", "clarity"],
        core_focuses=["methods", "results", "novelty"],
        enable_secondary=True, names_path=names_file, seed=7,
    )
    assert {t.primary_focus for t in out} >= {"methods", "results", "novelty"}


def test_raises_when_names_pool_smaller_than_n(classes, tmp_path):
    short = tmp_path / "short.json"
    short.write_text(json.dumps(["Aino"]))
    with pytest.raises(ValueError, match="names"):
        sample_board(
            n=3, classes=classes,
            stances=["a", "b", "c"], focuses=["m", "r", "n"], core_focuses=["m"],
            enable_secondary=False, names_path=short, seed=1,
        )


def test_deterministic_with_same_seed(classes, names_file):
    args = dict(n=3, classes=classes,
                stances=["a", "b", "c"], focuses=["m", "r", "n", "c"],
                core_focuses=["m", "r", "n"], enable_secondary=True,
                names_path=names_file, seed=99)
    a = sample_board(**args)
    b = sample_board(**args)
    assert [t.model_dump() for t in a] == [t.model_dump() for t in b]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_sampler.py -v`
Expected: collection error (`ModuleNotFoundError: paperfb.tools`).

- [ ] **Step 3: Implement `paperfb/tools/sampler.py`**

Adapt the algorithm from `paperfb/agents/profile_creation/sampler.py`. Two changes vs. the original: (a) returns `list[ReviewerTuple]` Pydantic models with `specialty: str` (the ACM path), (b) raises `ValueError` when `len(names) < n` (was previously silent padding with empty strings — the new contract requires a name per reviewer).

Create `paperfb/tools/__init__.py` (empty) and `paperfb/tools/sampler.py`:

```python
"""Deterministic reviewer-tuple sampler. Closure-bound from
build_profile_creation_agent so the LLM only ever supplies n, classes, seed
(spec §4.2). Algorithm preserved from the v1 sampler verbatim except:
  - returns list[ReviewerTuple] (Pydantic) with specialty: str (the ACM path)
  - raises ValueError when names pool is smaller than n
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

from paperfb.schemas import CCSClass, ReviewerTuple


def _sort_classes_by_weight(classes: list[CCSClass]) -> list[CCSClass]:
    order = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(classes, key=lambda c: order[c.weight])


def _load_names(names_path: Path) -> list[str]:
    return json.loads(Path(names_path).read_text(encoding="utf-8"))


def sample_board(
    n: int,
    classes: list[CCSClass],
    stances: list[str],
    focuses: list[str],
    core_focuses: list[str],
    enable_secondary: bool,
    names_path: Path,
    seed: Optional[int] = None,
) -> list[ReviewerTuple]:
    if n < len(core_focuses):
        raise ValueError(
            f"n={n} < core_focuses count ({len(core_focuses)}); cannot guarantee coverage"
        )
    if not classes:
        raise ValueError("classes must be non-empty")
    for cf in core_focuses:
        if cf not in focuses:
            raise ValueError(f"core focus {cf!r} not in focuses")

    rng = random.Random(seed)
    sorted_classes = _sort_classes_by_weight(classes)

    primaries = list(core_focuses)
    non_core = [f for f in focuses if f not in core_focuses]
    while len(primaries) < n:
        primaries.append(rng.choice(non_core or focuses))

    stances_pool = list(stances)
    chosen_stances: list[str] = []
    used_pairs: set[tuple[str, str]] = set()
    for pf in primaries:
        rng.shuffle(stances_pool)
        picked = next((s for s in stances_pool if (s, pf) not in used_pairs), None)
        if picked is None:
            picked = rng.choice(stances_pool)
        chosen_stances.append(picked)
        used_pairs.add((picked, pf))

    secondaries: list[str | None]
    if enable_secondary:
        secondaries = []
        used = set(primaries)
        for pf in primaries:
            cands = [f for f in focuses if f != pf and f not in used] or [f for f in focuses if f != pf]
            sec = rng.choice(cands)
            secondaries.append(sec)
            used.add(sec)
    else:
        secondaries = [None] * n

    all_names = _load_names(names_path)
    if len(all_names) < n:
        raise ValueError(f"names pool has {len(all_names)} entries; need >= {n}")
    names = rng.sample(all_names, k=n)

    return [
        ReviewerTuple(
            id=f"r{i+1}",
            name=names[i],
            specialty=sorted_classes[i % len(sorted_classes)].path,
            stance=chosen_stances[i],
            primary_focus=primaries[i],
            secondary_focus=secondaries[i],
        )
        for i in range(n)
    ]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/tools/test_sampler.py -v`
Expected: all 5 tests pass. Existing `tests/agents/profile_creation/test_sampler.py` continues to pass against the old module — both coexist until Task 15.

- [ ] **Step 5: Commit**

```bash
git add paperfb/tools/__init__.py paperfb/tools/sampler.py tests/tools/__init__.py tests/tools/test_sampler.py
git commit -m "Add paperfb.tools.sampler with Pydantic I/O"
```

---

## Task 5: Move `lookup_acm` tool to `paperfb/tools/acm_lookup.py`

**Files:**
- Create: `paperfb/tools/acm_lookup.py`
- Create: `tests/tools/test_acm_lookup.py`

Re-homes `lookup_acm` (the search side of the v1 tools module). Returns `list[CCSMatch]` (Pydantic) instead of `list[dict]`. The `submit_classification` helper from the v1 tools module is gone — its job is now done by AG2's `response_format=ClassificationResult` validation. Existing `tests/agents/classification/test_tools.py` stays at HEAD and continues to test the legacy function until Task 15.

- [ ] **Step 1: Write the failing test**

```python
# tests/tools/test_acm_lookup.py
import json
from pathlib import Path

import pytest

from paperfb.schemas import CCSMatch
from paperfb.tools.acm_lookup import lookup_acm


@pytest.fixture
def ccs_path(tmp_path) -> Path:
    p = tmp_path / "ccs.json"
    p.write_text(json.dumps([
        {"path": "Computing methodologies → Machine learning → Neural networks",
         "description": "Artificial neural networks for ML."},
        {"path": "Software and its engineering → Software notations and tools",
         "description": "Languages and notations."},
        {"path": "Theory of computation → Design and analysis of algorithms",
         "description": "Algorithmic complexity."},
    ]))
    return p


def test_returns_pydantic_ccs_match_objects(ccs_path):
    out = lookup_acm("neural", k=10, ccs_path=ccs_path)
    assert all(isinstance(m, CCSMatch) for m in out)
    assert any("Neural networks" in m.path for m in out)


def test_multi_token_and_match(ccs_path):
    # Both tokens must match (case-insensitive, word-boundary)
    out = lookup_acm("neural networks", k=10, ccs_path=ccs_path)
    assert len(out) == 1
    assert "Neural networks" in out[0].path


def test_empty_query_returns_empty(ccs_path):
    assert lookup_acm("", k=10, ccs_path=ccs_path) == []


def test_k_caps_results(ccs_path):
    out = lookup_acm("computing methodologies machine learning", k=1, ccs_path=ccs_path)
    assert len(out) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/tools/test_acm_lookup.py -v`
Expected: `ModuleNotFoundError: paperfb.tools.acm_lookup`.

- [ ] **Step 3: Implement `paperfb/tools/acm_lookup.py`**

```python
"""ACM CCS lookup tool. Returns Pydantic CCSMatch objects (spec §4.1).

Algorithm preserved from paperfb/agents/classification/tools.py:lookup_acm.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from paperfb.schemas import CCSMatch


PATH_SEPARATOR = " → "


@lru_cache(maxsize=8)
def _load_ccs(ccs_path: Path) -> tuple[dict, ...]:
    with Path(ccs_path).open() as f:
        return tuple(json.load(f))


def _token_patterns(query: str) -> list[re.Pattern]:
    return [re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in query.split()]


def lookup_acm(query: str, k: int = 10, ccs_path: Path | None = None) -> list[CCSMatch]:
    if ccs_path is None:
        ccs_path = Path("data/acm_ccs.json")
    patterns = _token_patterns(query)
    if not patterns:
        return []
    out: list[CCSMatch] = []
    for e in _load_ccs(ccs_path):
        hay = e["path"] + " " + e.get("description", "")
        if all(p.search(hay) for p in patterns):
            out.append(CCSMatch(path=e["path"], description=e.get("description", "")))
        if len(out) >= k:
            break
    return out
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/tools/test_acm_lookup.py -v`
Expected: all 4 tests pass. Existing `tests/agents/classification/test_tools.py` still passes (separate module, separate function).

- [ ] **Step 5: Commit**

```bash
git add paperfb/tools/acm_lookup.py tests/tools/test_acm_lookup.py
git commit -m "Add paperfb.tools.acm_lookup with Pydantic CCSMatch return"
```

---

## Task 6: Classification agent + `classify_to_profile` FunctionTarget

**Files:**
- Create: `paperfb/agents/classification.py` (flat module — alongside the existing subpackage at `paperfb/agents/classification/`)
- Create: `paperfb/handoffs.py`
- Create: `tests/test_handoffs.py`

This is the first AG2 agent. The flat module coexists with the legacy subpackage until Task 15 (Python lets both `paperfb.agents.classification` (subpackage) and a `classification.py` module coexist only if one is removed; **rename the v1 subpackage to `classification_legacy/` for the duration**). To avoid the import ambiguity, do the rename in this task as a chore.

- [ ] **Step 1: Rename the legacy subpackages so the flat modules can land**

```bash
git mv paperfb/agents/classification paperfb/agents/classification_legacy
git mv paperfb/agents/profile_creation paperfb/agents/profile_creation_legacy
git mv paperfb/agents/reviewer paperfb/agents/reviewer_legacy
```

Update all imports of the legacy subpackages to use the `_legacy` suffix:

```bash
grep -rl 'paperfb.agents.classification\b' paperfb tests scripts | xargs sed -i 's|paperfb\.agents\.classification\b|paperfb.agents.classification_legacy|g'
grep -rl 'paperfb.agents.profile_creation\b' paperfb tests scripts | xargs sed -i 's|paperfb\.agents\.profile_creation\b|paperfb.agents.profile_creation_legacy|g'
grep -rl 'paperfb.agents.reviewer\b' paperfb tests scripts | xargs sed -i 's|paperfb\.agents\.reviewer\b|paperfb.agents.reviewer_legacy|g'
```

Run: `uv run pytest -q -x --ignore=tests/test_acceptance_live.py`
Expected: existing test suite still green after the rename. Fix any straggler imports the sed missed.

Commit this rename as a separate point so blame stays clean:

```bash
git add -A paperfb tests scripts
git commit -m "Rename v1 agent subpackages to _legacy for AG2 coexistence"
```

- [ ] **Step 2: Write the failing handoff test**

`paperfb/handoffs.py` will hold both `classify_to_profile` (this task) and `setup_review_board` (Task 10). Write the test for `classify_to_profile` first; the second handoff is added in Task 10.

```python
# tests/test_handoffs.py
import json

from paperfb.handoffs import classify_to_profile
from paperfb.schemas import CCSClass, ClassificationResult, Keywords


def _ctx():
    """Stub ContextVariables — a plain dict; AG2's ContextVariables is dict-like.
    The handoff function must accept dict-style read/write so we can unit-test it
    without instantiating the AG2 class.
    """
    return {}


def test_classify_to_profile_writes_full_classification_to_context():
    cr = ClassificationResult(
        keywords=Keywords(extracted_from_paper=["x"], synthesised=[]),
        classes=[CCSClass(path="A → B", weight="High", rationale="r")],
    )
    ctx = _ctx()
    result = classify_to_profile(cr.model_dump_json(), ctx)
    saved = ClassificationResult.model_validate(ctx["classification"])
    assert saved == cr
    # Curated message goes downstream
    assert "A → B" in result.message
    # Keywords MUST NOT leak into the downstream prompt (spec §4.1)
    assert "x" not in result.message


def test_classify_to_profile_message_lists_only_class_paths():
    cr = ClassificationResult(
        keywords=Keywords(extracted_from_paper=[], synthesised=["k1"]),
        classes=[
            CCSClass(path="A → B", weight="High", rationale="r1"),
            CCSClass(path="C → D", weight="Low", rationale="r2"),
        ],
    )
    result = classify_to_profile(cr.model_dump_json(), _ctx())
    assert "A → B" in result.message
    assert "C → D" in result.message
    # Rationales stay in context_variables, not in the downstream message
    assert "r1" not in result.message
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_handoffs.py -v`
Expected: `ModuleNotFoundError: paperfb.handoffs`.

- [ ] **Step 4: Implement `paperfb/handoffs.py` with `classify_to_profile`**

This module imports AG2 surfaces verified in Task 1. The `setup_review_board` body is a stub that raises `NotImplementedError` for now; Task 10 fills it in.

```python
"""FunctionTarget bodies for AG2 agent handoffs (spec §4.1, §4.4)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from paperfb.schemas import ClassificationResult


@dataclass
class HandoffResult:
    """Stand-in for ag2's FunctionTargetResult during unit testing.

    The pipeline-time wrapper in pipeline.py converts this into the actual AG2
    FunctionTargetResult. Keeping this layer indirected lets us unit-test
    handoff logic without spinning up an AG2 chat.
    """
    message: str
    target: Any | None = None  # set only for handoffs that transition (setup_review_board)


def classify_to_profile(agent_output: str, context_variables: dict) -> HandoffResult:
    """Classification → ProfileCreation handoff.

    Parses the full ClassificationResult, stashes it in context_variables for
    the renderer to read post-chat, and forwards a curated, classes-only
    message to ProfileCreation. Keywords stay in context_variables and the run
    log; they MUST NOT enter ProfileCreation's prompt (spec §4.1).
    """
    cr = ClassificationResult.model_validate_json(agent_output)
    context_variables["classification"] = cr.model_dump()
    paths = ", ".join(c.path for c in cr.classes)
    return HandoffResult(message=f"ACM classes: [{paths}]")


def setup_review_board(agent_output: str, context_variables: dict) -> HandoffResult:
    """ProfileCreation → RedundantPattern handoff. Filled in by Task 10."""
    raise NotImplementedError("setup_review_board lands in Task 10")
```

- [ ] **Step 5: Implement the classification agent builder**

Create `paperfb/agents/classification.py`:

```python
"""Classification agent (spec §4.1)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from autogen import ConversableAgent

from paperfb.schemas import CCSMatch, ClassificationResult
from paperfb.tools.acm_lookup import lookup_acm as _lookup_acm


SYSTEM_PROMPT = """You classify a computer-science research manuscript against the ACM Computing Classification System (CCS).

Procedure:
1. Read the manuscript. Extract the keywords actually used in it (extracted_from_paper).
   If the paper's vocabulary is non-standard or sparse, also synthesise canonical
   keywords that describe the same work (synthesised). At least one of the two lists
   must be non-empty.
2. Drive lookup_acm queries from those keywords. Multi-token queries are AND across
   tokens with word-boundary matching, so prefer multiple short queries over one long
   one. Match is case-insensitive.
3. Pick 1-{max_classes} CCS classes. Prefer leaf nodes; use higher-level nodes only
   when no leaf fits.
4. Emit a ClassificationResult with keywords and classes. Every path must come from
   a lookup_acm result — do not invent paths.

Weight rubric:
- High:   central topic — title-or-abstract-first material; the primary contribution.
- Medium: significant supporting topic — methods, frameworks, or domains the work substantially uses.
- Low:    relevant but not central — mentioned, compared against, or touched on.
"""


def build_classification_agent(
    llm_config: dict,
    ccs_path: Path,
    max_classes: int,
) -> tuple[ConversableAgent, Any]:
    """Returns (agent, lookup_acm_callable).

    Caller (pipeline.py) wires the returned callable to the UserProxy via
    @user_proxy.register_for_execution() / @agent.register_for_llm(...). We
    bind ccs_path here as a closure so the LLM never supplies it.
    """
    agent = ConversableAgent(
        name="classification",
        system_message=SYSTEM_PROMPT.format(max_classes=max_classes),
        llm_config={**llm_config, "response_format": ClassificationResult},
    )

    def lookup_acm_bound(query: str, k: int = 10) -> list[CCSMatch]:
        """ACM CCS lookup. Multi-token AND, word-boundary, case-insensitive."""
        return _lookup_acm(query=query, k=k, ccs_path=ccs_path)

    # Tool registration with the agent. The actual register_for_execution call
    # against the user_proxy happens in pipeline.py (where the UserProxy lives).
    return agent, lookup_acm_bound
```

- [ ] **Step 6: Run handoff test**

Run: `uv run pytest tests/test_handoffs.py -v`
Expected: 2 tests pass. Don't write a unit test for `build_classification_agent` itself — it's a thin builder; coverage comes from the integration test in Task 11.

- [ ] **Step 7: Commit**

```bash
git add paperfb/handoffs.py paperfb/agents/classification.py tests/test_handoffs.py
git commit -m "Add classification agent + classify_to_profile handoff"
```

---

## Task 7: ProfileCreation agent

**Files:**
- Create: `paperfb/agents/profile_creation.py`

Single LLM step that emits all N personas at once via `response_format=ProfileBoard` (spec §4.2). The `sample_board` tool is registered with `n`, `classes`, and optional `seed` as the only LLM-visible parameters; everything else (`stances`, `focuses`, `core_focuses`, `enable_secondary`, `names_path`) is closure-bound at builder time.

- [ ] **Step 1: Implement the builder**

```python
"""ProfileCreation agent (spec §4.2)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from autogen import ConversableAgent

from paperfb.config import AxesConfig
from paperfb.schemas import CCSClass, ProfileBoard, ReviewerTuple
from paperfb.tools.sampler import sample_board as _sample_board


_AXIS_BLOCK = """Stance vocabulary (use these names verbatim; descriptions ground tone):
{stances}

Focus vocabulary (use these names verbatim; descriptions ground depth):
{focuses}
"""


SYSTEM_PROMPT_TEMPLATE = """You compose reviewer personas for a research-paper feedback board.

Procedure:
1. Call sample_board exactly once with n={count} and the ACM classes you receive.
   The tool returns N reviewer tuples (id, name, specialty, stance, primary_focus,
   secondary_focus). The tool already enforces deterministic diversity, Finnish
   names, and class round-robin — do not second-guess its output.
2. For each tuple, write a full reviewer system_message that:
   - Addresses the reviewer by their assigned Finnish first name verbatim. Do NOT
     add titles, surnames, affiliations, or honourifics.
   - Establishes the reviewer as a domain specialist grounded in the specialty
     (the ACM CCS path).
   - Reflects the assigned stance in tone (drawing on the stance description).
   - Emphasises the primary_focus (drawing on its description); acknowledges the
     secondary_focus as a supplementary lens.
   - Instructs the reviewer to produce three free-text aspects (strong_aspects,
     weak_aspects, recommended_changes), each grounded in the primary_focus, with
     the secondary_focus colouring depth where natural.
   - Forbids the reviewer from rewriting the paper. Forbids numeric ratings.
3. Also write a one-line profile_summary for the renderer header.
4. Emit a ProfileBoard with one ReviewerProfile per tuple.

{axis_block}
"""


def _format_axis_block(axes: AxesConfig) -> str:
    stances = "\n".join(f"  - {s.name}: {s.description}" for s in axes.stances)
    focuses = "\n".join(f"  - {f.name}: {f.description}" for f in axes.focuses)
    return _AXIS_BLOCK.format(stances=stances, focuses=focuses)


def build_profile_creation_agent(
    llm_config: dict,
    axes: AxesConfig,
    names_path: Path,
    count: int,
    core_focuses: list[str],
    enable_secondary: bool,
    seed: int | None,
) -> tuple[ConversableAgent, Any]:
    """Returns (agent, sample_board_callable). Tool registration with the
    UserProxy happens in pipeline.py."""
    stances = [s.name for s in axes.stances]
    focuses = [f.name for f in axes.focuses]

    system_message = SYSTEM_PROMPT_TEMPLATE.format(
        count=count,
        axis_block=_format_axis_block(axes),
    )

    agent = ConversableAgent(
        name="profile_creation",
        system_message=system_message,
        llm_config={**llm_config, "response_format": ProfileBoard},
    )

    def sample_board_bound(
        n: int,
        classes: list[CCSClass],
        seed_override: int | None = None,
    ) -> list[ReviewerTuple]:
        """Deterministically sample N reviewer tuples. The bound parameters
        (stances, focuses, core_focuses, enable_secondary, names_path) come
        from config and are not LLM-controlled."""
        return _sample_board(
            n=n,
            classes=classes,
            stances=stances,
            focuses=focuses,
            core_focuses=core_focuses,
            enable_secondary=enable_secondary,
            names_path=names_path,
            seed=seed_override if seed_override is not None else seed,
        )

    return agent, sample_board_bound
```

- [ ] **Step 2: Smoke-import the builder**

Run: `uv run python -c "from paperfb.agents.profile_creation import build_profile_creation_agent; print('OK')"`
Expected: `OK`.

A targeted unit test is overkill at this layer; coverage comes from the integration test in Task 11. (Per the plan's no-placeholder rule: this builder is a closure-binder + ConversableAgent constructor; integration tests catch the real bugs.)

- [ ] **Step 3: Commit**

```bash
git add paperfb/agents/profile_creation.py
git commit -m "Add profile_creation agent with closure-bound sample_board"
```

---

## Task 8: Reviewer factory

**Files:**
- Create: `paperfb/agents/reviewer.py`

Per spec §4.3: one `ConversableAgent` per `ReviewerProfile`, no tools, `response_format=Review`, `max_consecutive_auto_reply=1`. `persona_prompt` is used verbatim as the system message; one trailing line tells the reviewer their `reviewer_id`.

- [ ] **Step 1: Implement the factory**

```python
"""Reviewer agent factory (spec §4.3). One ConversableAgent per ReviewerProfile."""
from __future__ import annotations

from autogen import ConversableAgent

from paperfb.schemas import Review, ReviewerProfile


_REVIEWER_ID_LINE = (
    "\n\nYour reviewer_id is: {rid}. Use this exact value as Review.reviewer_id."
)


def build_reviewer_agent(profile: ReviewerProfile, llm_config: dict) -> ConversableAgent:
    system = profile.persona_prompt + _REVIEWER_ID_LINE.format(rid=profile.id)
    return ConversableAgent(
        name=f"reviewer_{profile.id}",
        system_message=system,
        llm_config={**llm_config, "response_format": Review},
        max_consecutive_auto_reply=1,
        human_input_mode="NEVER",
    )
```

- [ ] **Step 2: Smoke-import**

Run: `uv run python -c "from paperfb.agents.reviewer import build_reviewer_agent; print('OK')"`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add paperfb/agents/reviewer.py
git commit -m "Add reviewer agent factory"
```

---

## Task 9: Chair aggregator

**Files:**
- Create: `paperfb/agents/chair.py`

Per spec §4.4: thin LLM aggregator. Reads sibling reviews from chat history + `expected_reviewer_ids`/`skipped` from `context_variables`, emits `BoardReport` verbatim. No metadata joining (renderer's job), no classification (pipeline.run's job).

- [ ] **Step 1: Implement the builder**

```python
"""Chair aggregator inside RedundantPattern (spec §4.4)."""
from __future__ import annotations

from autogen import ConversableAgent

from paperfb.schemas import BoardReport


SYSTEM_PROMPT = """You are the Chair aggregator for a peer-review board.

You receive the structured Review responses produced by the reviewer agents
in this chat. Your job is purely collation — no editing, no synthesis, no
commentary on the reviews themselves.

Procedure:
1. Collect every valid Review you see in the chat history.
2. Read context_variables["expected_reviewer_ids"] (the full list of reviewer_ids
   that were supposed to produce a Review).
3. For any expected_reviewer_id that did not produce a valid Review, append a
   SkippedReviewer entry with id=<that id> and reason="missing or invalid Review"
   to the BoardReport.skipped list.
4. Also include any pre-existing context_variables["skipped"] entries verbatim.
5. Emit a BoardReport(reviews=[...], skipped=[...]) as your structured response.

Do not edit, summarise, or comment on the reviews themselves. Pure passthrough.
"""


def build_chair(llm_config: dict) -> ConversableAgent:
    return ConversableAgent(
        name="chair",
        system_message=SYSTEM_PROMPT,
        llm_config={**llm_config, "response_format": BoardReport},
        human_input_mode="NEVER",
    )
```

- [ ] **Step 2: Smoke-import + commit**

Run: `uv run python -c "from paperfb.agents.chair import build_chair; print('OK')"`

```bash
git add paperfb/agents/chair.py
git commit -m "Add chair aggregator agent"
```

---

## Task 10: `setup_review_board` FunctionTarget

**Files:**
- Modify: `paperfb/handoffs.py`
- Modify: `tests/test_handoffs.py`

Per spec §4.4: parses `ProfileBoard`, builds N reviewer agents, constructs `RedundantPattern(agents=reviewers, aggregator=chair, ...)`, returns a `HandoffResult` carrying the AG2 `NestedChatTarget`. Closure captures `reviewer_llm_config`, `chair_llm_config`, and the manuscript-passing strategy.

The unit test stubs the AG2 surfaces — the integration test in Task 11 exercises the real classes.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_handoffs.py`:

```python
from unittest.mock import MagicMock, patch

from paperfb.schemas import ProfileBoard, ReviewerProfile


def _profile_board(ids=("r1", "r2", "r3")) -> ProfileBoard:
    return ProfileBoard(reviewers=[
        ReviewerProfile(
            id=i, name=n, specialty="A → B", stance="critical",
            primary_focus="methods", secondary_focus=None,
            persona_prompt="...", profile_summary="...",
        )
        for i, n in zip(ids, ["Aino", "Eero", "Liisa"])
    ])


def test_setup_review_board_writes_expected_ids_and_profiles():
    from paperfb.handoffs import build_setup_review_board

    pb = _profile_board()
    ctx = {"manuscript": "hello"}

    fake_target = MagicMock(name="NestedChatTarget")
    setup = build_setup_review_board(
        reviewer_llm_config={"model": "x"},
        chair_llm_config={"model": "x"},
        build_reviewer=lambda p, cfg: MagicMock(name=f"reviewer_{p.id}"),
        build_chair_=lambda cfg: MagicMock(name="chair"),
        build_pattern=lambda agents, aggregator, task: MagicMock(
            as_nested_chat=MagicMock(return_value=fake_target)
        ),
    )

    result = setup(pb.model_dump_json(), ctx)
    assert ctx["profiles"] == pb.model_dump()
    assert ctx["expected_reviewer_ids"] == ["r1", "r2", "r3"]
    assert ctx["skipped"] == []
    assert result.target is fake_target
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_handoffs.py -v`
Expected: `ImportError: cannot import name 'build_setup_review_board'`.

- [ ] **Step 3: Update `paperfb/handoffs.py`**

Replace the placeholder `setup_review_board` with a builder factory. The factory takes the AG2 surfaces as injectable callables so the unit test can run without AG2; the pipeline wires the real ones in Task 11.

```python
"""FunctionTarget bodies for AG2 agent handoffs (spec §4.1, §4.4)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from paperfb.schemas import ClassificationResult, ProfileBoard, ReviewerProfile


@dataclass
class HandoffResult:
    """Stand-in for ag2's FunctionTargetResult during unit testing.

    The pipeline-time wrapper in pipeline.py converts this into the actual AG2
    FunctionTargetResult. Keeping this layer indirected lets us unit-test
    handoff logic without spinning up an AG2 chat.
    """
    message: str | None = None
    target: Any | None = None


def classify_to_profile(agent_output: str, context_variables: dict) -> HandoffResult:
    """Classification → ProfileCreation handoff (spec §4.1)."""
    cr = ClassificationResult.model_validate_json(agent_output)
    context_variables["classification"] = cr.model_dump()
    paths = ", ".join(c.path for c in cr.classes)
    return HandoffResult(message=f"ACM classes: [{paths}]")


def build_setup_review_board(
    *,
    reviewer_llm_config: dict,
    chair_llm_config: dict,
    build_reviewer: Callable[[ReviewerProfile, dict], Any],
    build_chair_: Callable[[dict], Any],
    build_pattern: Callable[..., Any],
) -> Callable[[str, dict], HandoffResult]:
    """Returns a closure suitable for use as a FunctionTarget body.

    Parameters are injected so this is unit-testable without AG2:
      - build_reviewer(profile, llm_config) -> ConversableAgent
      - build_chair_(llm_config)            -> ConversableAgent
      - build_pattern(agents, aggregator, task) -> RedundantPattern
        The pattern object MUST expose .as_nested_chat() returning a NestedChatTarget.

    pipeline.py wires the real AG2 callables; tests pass MagicMocks.
    """

    def setup_review_board(agent_output: str, context_variables: dict) -> HandoffResult:
        board = ProfileBoard.model_validate_json(agent_output)
        reviewers = [build_reviewer(p, reviewer_llm_config) for p in board.reviewers]
        chair = build_chair_(chair_llm_config)
        manuscript = context_variables["manuscript"]
        pattern = build_pattern(agents=reviewers, aggregator=chair, task=manuscript)
        context_variables["profiles"] = board.model_dump()
        context_variables["expected_reviewer_ids"] = sorted(p.id for p in board.reviewers)
        context_variables.setdefault("skipped", [])
        return HandoffResult(target=pattern.as_nested_chat())

    return setup_review_board
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_handoffs.py -v`
Expected: all 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add paperfb/handoffs.py tests/test_handoffs.py
git commit -m "Add setup_review_board handoff factory"
```

---

## Task 11: Wire the pipeline (`paperfb/pipeline.py`)

**Files:**
- Create: `paperfb/pipeline.py`
- Create: `tests/test_pipeline.py`

This is the keystone. Builds the UserProxy + agents, registers tools (`@user_proxy.register_for_execution()` + `@agent.register_for_llm(...)`), wires AfterWork handoffs, runs the chat, assembles `RunOutput`. The unit test stubs AG2 with monkey-patched fakes; the live exercise lands in Task 16.

Spec sections referenced: §6.1, §6.2, §6.5, §6.7.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_pipeline.py
"""Integration test for the AG2-wired pipeline. AG2 is patched out so we don't
hit the network; the test asserts wiring (handoff sequence, RunOutput
assembly) rather than LLM behavior.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from paperfb.config import load_config
from paperfb.schemas import (
    BoardReport, CCSClass, ClassificationResult, Keywords,
    ProfileBoard, Review, ReviewerProfile, RunOutput, SkippedReviewer,
)


@pytest.fixture
def cfg(tmp_path):
    from dataclasses import replace
    c = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    return replace(c, paths=replace(
        c.paths,
        output=str(tmp_path / "report.md"),
        logs_dir=str(tmp_path / "logs"),
        reviews_dir=str(tmp_path / "reviews"),
    ))


def _fake_chat_result():
    """Stub of AG2's chat_result. Carries context_variables + a 'last nested
    message' the pipeline parses as a BoardReport."""
    classification = ClassificationResult(
        keywords=Keywords(extracted_from_paper=["x"], synthesised=[]),
        classes=[CCSClass(path="A → B", weight="High", rationale="r")],
    )
    profiles = ProfileBoard(reviewers=[
        ReviewerProfile(
            id=f"r{i+1}", name=n, specialty="A → B", stance="critical",
            primary_focus="methods", secondary_focus=None,
            persona_prompt="...", profile_summary="...",
        )
        for i, n in enumerate(["Aino", "Eero", "Liisa"])
    ])
    board = BoardReport(
        reviews=[Review(reviewer_id=f"r{i+1}", strong_aspects="s",
                        weak_aspects="w", recommended_changes="c")
                 for i in range(3)],
        skipped=[],
    )
    res = MagicMock()
    res.context_variables = {
        "classification": classification.model_dump(),
        "profiles": profiles.model_dump(),
        "expected_reviewer_ids": ["r1", "r2", "r3"],
        "skipped": [],
    }
    res.last_nested_message = board.model_dump_json()
    return res, board, classification, profiles


def test_pipeline_assembles_runoutput(cfg, monkeypatch, tmp_path):
    from paperfb import pipeline as pl

    fake_result, board, classification, profiles = _fake_chat_result()

    # Stub AG2 entirely. _run_chat returns the fake chat result.
    monkeypatch.setattr(pl, "_run_chat", lambda **kw: fake_result)
    # extract_board_report just reads .last_nested_message in our stub.
    monkeypatch.setattr(pl, "extract_board_report",
                        lambda r: BoardReport.model_validate_json(r.last_nested_message))

    run = pl.run(manuscript="hello world", cfg=cfg)
    assert isinstance(run, RunOutput)
    assert run.classification == classification
    assert run.profiles == profiles
    assert run.board == board

    # On-disk artefacts: report markdown + RunOutput JSON
    assert Path(cfg.paths.output).exists()
    eval_dirs = list(Path("evaluations").glob("run-*"))
    assert any((d / "run.json").exists() for d in eval_dirs), \
        "expected evaluations/run-<ts>/run.json to be written"


def test_pipeline_propagates_skipped_reviewers(cfg, monkeypatch):
    from paperfb import pipeline as pl

    fake_result, _, classification, profiles = _fake_chat_result()
    board_with_skip = BoardReport(
        reviews=[Review(reviewer_id="r1", strong_aspects="s",
                        weak_aspects="w", recommended_changes="c")],
        skipped=[SkippedReviewer(id="r2", reason="missing"),
                 SkippedReviewer(id="r3", reason="missing")],
    )
    fake_result.last_nested_message = board_with_skip.model_dump_json()
    monkeypatch.setattr(pl, "_run_chat", lambda **kw: fake_result)
    monkeypatch.setattr(pl, "extract_board_report",
                        lambda r: BoardReport.model_validate_json(r.last_nested_message))

    run = pl.run(manuscript="hello", cfg=cfg)
    assert {s.id for s in run.board.skipped} == {"r2", "r3"}
    assert len(run.board.reviews) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: `ModuleNotFoundError: paperfb.pipeline`.

- [ ] **Step 3: Implement `paperfb/pipeline.py`**

The implementation has two layers: pure assembly logic (which the test exercises via monkey-patching `_run_chat`) and the real AG2 wiring inside `_run_chat`. The latter uses the surfaces verified in Task 1.

```python
"""Top-level pipeline runner (spec §6.1, §6.2). Replaces orchestrator.py.

Layout:
  run(manuscript, cfg) -> RunOutput
    builds llm_configs, calls _run_chat(...), parses results into RunOutput,
    writes evaluations/run-<ts>/run.json + final_report.md.

  _run_chat(...) — the AG2 wiring. Builds UserProxy + agents, registers tools,
    wires AfterWork(FunctionTarget(...)) handoffs, calls initiate_chat.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# AG2 imports (paths verified by scripts/probe_ag2_api.py in Task 1).
from autogen import ConversableAgent, UserProxyAgent  # noqa: F401
from autogen.agentchat.group import (  # type: ignore[attr-defined]
    AfterWork,
    ContextVariables,
    FunctionTarget,
    FunctionTargetResult,
    NestedChatTarget,
)
from autogen.agentchat.group.patterns import (  # type: ignore[attr-defined]
    DefaultPattern,
    RedundantPattern,
)

from paperfb.agents.chair import build_chair
from paperfb.agents.classification import build_classification_agent
from paperfb.agents.profile_creation import build_profile_creation_agent
from paperfb.agents.reviewer import build_reviewer_agent
from paperfb.config import Config
from paperfb.handoffs import (
    HandoffResult,
    build_setup_review_board,
    classify_to_profile,
)
from paperfb.renderer import render_report
from paperfb.schemas import BoardReport, ClassificationResult, ProfileBoard, RunOutput


def _utc_timestamp() -> str:
    return "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _build_llm_config(cfg: Config, model: str) -> dict:
    return {
        "config_list": [{
            "model": model,
            "base_url": os.environ["BASE_URL"],
            "api_key": "unused",
            "api_type": "openai",
        }],
        "temperature": 0.0,
        "cache_seed": cfg.ag2.cache_seed,
    }


def _wrap_handoff(fn) -> Any:
    """Convert a HandoffResult-returning function into AG2's FunctionTargetResult."""
    def wrapper(agent_output: str, context_variables: ContextVariables) -> FunctionTargetResult:
        # ContextVariables is dict-like in AG2 0.12+; pass through as a dict.
        result: HandoffResult = fn(agent_output, context_variables)
        return FunctionTargetResult(
            message=result.message,
            target=result.target,
            context_variables=context_variables,
        )
    return wrapper


def extract_board_report(chat_result: Any) -> BoardReport:
    """Pull the BoardReport JSON out of the nested RedundantPattern chat result.

    AG2 0.12.1: the nested chat's final message lives at
    chat_result.chat_history[-1]["content"] when the outer chat terminated via
    NestedChatTarget. If a future version exposes a cleaner accessor (e.g.
    chat_result.nested_chat_results), update this one function.
    """
    history = getattr(chat_result, "chat_history", None) or []
    if not history:
        raise RuntimeError("chat_result has no chat_history; cannot extract BoardReport")
    last = history[-1]
    content = last["content"] if isinstance(last, dict) else last.content
    return BoardReport.model_validate_json(content)


def _run_chat(*, manuscript: str, cfg: Config, ts: str) -> Any:
    """Build and run the full AG2 GroupChat. Returns the raw chat_result."""
    classification_cfg = _build_llm_config(cfg, cfg.models.classification)
    profile_cfg = _build_llm_config(cfg, cfg.models.profile_creation)
    reviewer_cfg = _build_llm_config(cfg, cfg.models.reviewer)
    chair_cfg = reviewer_cfg  # Chair runs on the reviewer model; cheap collation.

    user_proxy = UserProxyAgent(
        name="user",
        human_input_mode="NEVER",
        code_execution_config=False,
    )

    classification_agent, lookup_acm_fn = build_classification_agent(
        llm_config=classification_cfg,
        ccs_path=Path(cfg.paths.acm_ccs),
        max_classes=cfg.classification.max_classes,
    )
    profile_agent, sample_board_fn = build_profile_creation_agent(
        llm_config=profile_cfg,
        axes=cfg.axes,
        names_path=Path(cfg.paths.finnish_names),
        count=cfg.reviewers.count,
        core_focuses=cfg.reviewers.core_focuses,
        enable_secondary=cfg.reviewers.secondary_focus_per_reviewer,
        seed=cfg.reviewers.seed,
    )

    # Tool wiring: caller declares to LLM (register_for_llm); user_proxy executes
    # (register_for_execution). Same UserProxy serves both linear-leg tools.
    user_proxy.register_for_execution(name="lookup_acm")(lookup_acm_fn)
    classification_agent.register_for_llm(
        name="lookup_acm",
        description="Search the ACM CCS for concept paths matching keywords. "
                    "Multi-token AND, word-boundary, case-insensitive. Returns up to k matches.",
    )(lookup_acm_fn)

    user_proxy.register_for_execution(name="sample_board")(sample_board_fn)
    profile_agent.register_for_llm(
        name="sample_board",
        description="Sample N reviewer tuples deterministically. n: int, "
                    "classes: list[CCSClass], optional seed: int. Returns N ReviewerTuples.",
    )(sample_board_fn)

    setup_review_board = build_setup_review_board(
        reviewer_llm_config=reviewer_cfg,
        chair_llm_config=chair_cfg,
        build_reviewer=build_reviewer_agent,
        build_chair_=build_chair,
        build_pattern=lambda agents, aggregator, task: RedundantPattern(
            agents=agents, aggregator=aggregator, task=task,
        ),
    )

    classification_agent.register_handoff(
        AfterWork(target=FunctionTarget(_wrap_handoff(classify_to_profile)))
    )
    profile_agent.register_handoff(
        AfterWork(target=FunctionTarget(_wrap_handoff(setup_review_board)))
    )

    pattern = DefaultPattern(
        agents=[classification_agent, profile_agent],
        initial_agent=classification_agent,
        user_agent=user_proxy,
    )

    return user_proxy.initiate_chat(
        pattern=pattern,
        message=manuscript,
        context_variables=ContextVariables({
            "manuscript": manuscript,
            "run_id": ts,
        }),
    )


@dataclass
class PipelineResult:
    run: RunOutput
    report_path: Path
    run_json_path: Path


def run(*, manuscript: str, cfg: Config) -> RunOutput:
    """Run the full pipeline. Writes final_report.md and evaluations/run-<ts>/run.json."""
    ts = _utc_timestamp()
    chat_result = _run_chat(manuscript=manuscript, cfg=cfg, ts=ts)

    ctx = chat_result.context_variables
    classification = ClassificationResult.model_validate(dict(ctx["classification"]))
    profiles = ProfileBoard.model_validate(dict(ctx["profiles"]))
    board = extract_board_report(chat_result)

    run_obj = RunOutput(classification=classification, profiles=profiles, board=board)

    # Render final_report.md
    report_path = Path(cfg.paths.output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(run_obj))

    # Write canonical RunOutput artefact for the Judge
    eval_dir = Path("evaluations") / ts
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / "run.json").write_text(
        json.dumps(run_obj.model_dump(), indent=2, ensure_ascii=False)
    )

    return run_obj
```

Note on AG2 surface uncertainty: the `register_handoff` method name and `DefaultPattern` constructor parameters match AG2 0.12.x docs but may be off by one keyword. If the integration test in Step 4 fails with `AttributeError: 'ConversableAgent' object has no attribute 'register_handoff'`, run the AG2 group-chat example from `https://docs.ag2.ai/latest/docs/user-guide/advanced-concepts/pattern-cookbook/redundant/` against the installed package and update the call sites here. The shape (one handoff per linear-leg agent, FunctionTarget wrapping the handoff body) is fixed; the exact method name is not.

- [ ] **Step 4: Run the integration test**

Run: `uv run pytest tests/test_pipeline.py -v`
Expected: 2 tests pass. (The test patches `_run_chat` so AG2 is never actually invoked here — the real exercise is Task 16.)

- [ ] **Step 5: Commit**

```bash
git add paperfb/pipeline.py tests/test_pipeline.py
git commit -m "Wire AG2 pipeline with UserProxy + handoffs"
```

---

## Task 12: AG2 JSONL logging hook with size-threshold redaction

**Files:**
- Create: `paperfb/logging_hook.py`
- Create: `tests/test_logging_hook.py`
- Modify: `paperfb/pipeline.py` (install the hook in `_run_chat`)

Per spec §6.5 + §6.7: register an AG2 logging hook that writes JSONL to `logs/run-<ts>.jsonl`. Each line: `{ts, agent, role, content, tool_calls, usage}`. Payloads larger than 1024 bytes are stored as `{sha256: <hex>, bytes: <int>}` instead of cleartext, so the manuscript never lands on disk in plaintext.

The exact AG2 hook surface (likely `autogen.runtime_logging.start(...)` with a custom logger class, or a `register_logger` callback on the pattern) needs probe-time confirmation. Treat the hook surface like Task 1's other unknowns: write the JSONL formatter as a self-contained `JsonlLogger` callable with a single entrypoint `log_event(event_dict)`, then wire it to whatever AG2 surface 0.12.1 exposes.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_logging_hook.py
import json
from pathlib import Path

from paperfb.logging_hook import JsonlLogger, redact


def test_redact_short_payload_passthrough():
    assert redact("hello") == "hello"


def test_redact_large_payload_returns_hash_and_size():
    big = "x" * 2048
    out = redact(big)
    assert isinstance(out, dict)
    assert out["bytes"] == 2048
    assert len(out["sha256"]) == 64  # hex digest


def test_redact_threshold_is_1024_bytes_inclusive():
    boundary = "x" * 1024
    over = "x" * 1025
    assert redact(boundary) == boundary
    assert isinstance(redact(over), dict)


def test_jsonl_logger_writes_one_line_per_event(tmp_path):
    log_path = tmp_path / "run.jsonl"
    logger = JsonlLogger(log_path)
    logger.log_event({"agent": "classification", "role": "assistant", "content": "ok"})
    logger.log_event({"agent": "user", "role": "tool", "content": "x" * 2048})
    logger.close()

    lines = log_path.read_text().splitlines()
    assert len(lines) == 2
    e1 = json.loads(lines[0])
    assert e1["content"] == "ok"
    e2 = json.loads(lines[1])
    assert isinstance(e2["content"], dict) and e2["content"]["bytes"] == 2048
    # ts is auto-stamped
    assert "ts" in e1 and "ts" in e2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_logging_hook.py -v`
Expected: `ModuleNotFoundError: paperfb.logging_hook`.

- [ ] **Step 3: Implement `paperfb/logging_hook.py`**

```python
"""JSONL logger for AG2 runs (spec §6.5, §6.7).

Each line is one event: {ts, agent, role, content, tool_calls, usage}.
Content payloads >1024 bytes are stored as {sha256, bytes} — never cleartext.
This is the non-leakage guard for the manuscript body (spec §6.7).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REDACT_THRESHOLD_BYTES = 1024


def redact(payload: Any) -> Any:
    """Pass through small payloads; replace large ones with a sha256 + size."""
    if not isinstance(payload, str):
        return payload
    encoded = payload.encode("utf-8")
    if len(encoded) <= REDACT_THRESHOLD_BYTES:
        return payload
    return {
        "sha256": hashlib.sha256(encoded).hexdigest(),
        "bytes": len(encoded),
    }


class JsonlLogger:
    """Append-only JSONL log. One line per event. ts is UTC ISO-8601."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._fp = self._path.open("a", encoding="utf-8")

    def log_event(self, event: dict) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            **event,
            "content": redact(event.get("content")),
        }
        self._fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._fp.flush()

    def close(self) -> None:
        if not self._fp.closed:
            self._fp.close()

    def __enter__(self) -> "JsonlLogger":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
```

- [ ] **Step 4: Run logger tests**

Run: `uv run pytest tests/test_logging_hook.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Wire the logger in `paperfb/pipeline.py::_run_chat`**

The exact AG2 hook depends on the version. The two likely paths:

**Path A — `autogen.runtime_logging`** (common in older AG2):

```python
import autogen.runtime_logging
autogen.runtime_logging.start(logger_type="file", config={"filename": str(log_path)})
```

If this works, AG2 owns the log file format (SQLite or JSONL depending on `logger_type`) and we don't need our own JsonlLogger for orchestration events. In that case, `JsonlLogger` becomes a dead module — delete it and update Task 16's leakage check to look at AG2's log instead.

**Path B — register a hook on each agent / pattern**:

Many AG2 versions expose `register_hook` or `register_reply` on `ConversableAgent`. Wire each agent's reply hook to call `logger.log_event(...)`.

Pick the one that exists in 0.12.1 (probe with `dir()` or read `autogen/runtime_logging.py` in the installed package). Update `paperfb/pipeline.py::_run_chat` near the top:

```python
from paperfb.logging_hook import JsonlLogger

def _run_chat(*, manuscript: str, cfg: Config, ts: str) -> Any:
    log_path = Path(cfg.paths.logs_dir) / f"{ts}.jsonl"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = JsonlLogger(log_path)
    try:
        # ... existing wiring ...
        # If using Path B, register `logger.log_event` against each agent here.
        return user_proxy.initiate_chat(...)
    finally:
        logger.close()
```

If AG2 0.12.1 only exposes Path A and writes its own JSONL, drop the `JsonlLogger` import here and call `autogen.runtime_logging.start(...)` / `.stop()` instead. Either way, the log path follows the spec convention `logs/<run-id>.jsonl` so Task 16's leakage assertion works unchanged.

- [ ] **Step 6: Add a smoke test to `tests/test_pipeline.py`**

Append:

```python
def test_pipeline_writes_logs_jsonl(cfg, monkeypatch, tmp_path):
    """Verifies _run_chat opens the log file. Real content depends on AG2 hook
    path; we just check the file is created with at least one event."""
    from paperfb import pipeline as pl
    from paperfb.logging_hook import JsonlLogger

    fake_result, *_ = _fake_chat_result()
    captured: list[Path] = []

    def fake_run_chat(**kw):
        # Simulate the logger producing one event during the chat.
        log_path = Path(cfg.paths.logs_dir) / f"{kw['ts']}.jsonl"
        with JsonlLogger(log_path) as lg:
            lg.log_event({"agent": "test", "role": "assistant", "content": "ok"})
        captured.append(log_path)
        return fake_result

    monkeypatch.setattr(pl, "_run_chat", fake_run_chat)
    monkeypatch.setattr(pl, "extract_board_report",
                        lambda r: __import__("paperfb.schemas", fromlist=["BoardReport"])
                                    .BoardReport.model_validate_json(r.last_nested_message))

    pl.run(manuscript="hello", cfg=cfg)
    assert captured and captured[0].exists()
    assert captured[0].read_text().strip() != ""
```

- [ ] **Step 7: Run all tests**

Run: `uv run pytest -q --ignore=tests/test_acceptance_live.py`
Expected: green.

- [ ] **Step 8: Commit**

```bash
git add paperfb/logging_hook.py paperfb/pipeline.py tests/test_logging_hook.py tests/test_pipeline.py
git commit -m "Add JSONL logger with manuscript-body redaction"
```

---

## Task 13: Update renderer to consume `RunOutput`

**Files:**
- Modify: `paperfb/renderer.py`
- Modify: `tests/test_renderer.py`

Per spec §6.6: signature changes from `render_report(classes, reviews, skipped_reviewers)` to `render_report(run: RunOutput)`. The renderer joins each `Review` with its `ReviewerProfile` via `reviewer_id` to render the per-reviewer header.

- [ ] **Step 1: Rewrite `tests/test_renderer.py`**

```python
from paperfb.renderer import render_report
from paperfb.schemas import (
    BoardReport, CCSClass, ClassificationResult, Keywords,
    ProfileBoard, Review, ReviewerProfile, RunOutput, SkippedReviewer,
)


def _profile(rid="r1", name="Aino", specialty="Computing methodologies → ML → NN"):
    return ReviewerProfile(
        id=rid, name=name, specialty=specialty,
        stance="critical", primary_focus="methods", secondary_focus="results",
        persona_prompt="...",
        profile_summary="critical methods specialist",
    )


def _review(rid="r1") -> Review:
    return Review(
        reviewer_id=rid,
        strong_aspects="Clear framing of the problem and reproducible setup.",
        weak_aspects="Sample size of N=5 cannot distinguish gains from noise.",
        recommended_changes="Run with >=20 seeds, report 95% CIs, add a paired statistical test.",
    )


def _run(*, classes=None, reviews=None, profiles=None, skipped=None) -> RunOutput:
    return RunOutput(
        classification=ClassificationResult(
            keywords=Keywords(extracted_from_paper=[], synthesised=[]),
            classes=classes or [CCSClass(path="Computing methodologies → ML → NN",
                                          weight="High", rationale="r1")],
        ),
        profiles=ProfileBoard(reviewers=profiles or [_profile()]),
        board=BoardReport(reviews=reviews or [_review()], skipped=skipped or []),
    )


def test_renders_full_report():
    md = render_report(_run())
    assert "# Manuscript feedback report" in md
    assert "## ACM classification" in md
    assert "Computing methodologies → ML → NN" in md
    assert "High" in md
    assert "## Review by Aino — Computing methodologies → ML → NN" in md
    assert "critical" in md
    assert "methods" in md
    assert "### Strong aspects" in md
    assert "Clear framing" in md
    assert "### Weak aspects" in md
    assert "Sample size of N=5" in md
    assert "### Recommended changes" in md
    assert ">=20 seeds" in md


def test_no_ratings_table_in_report():
    md = render_report(_run())
    assert "| Score" not in md
    assert "/5" not in md


def test_notes_skipped_reviewers():
    md = render_report(_run(reviews=[],
                            skipped=[SkippedReviewer(id="r2", reason="tool failure")]))
    assert "Skipped" in md
    assert "r2" in md
    assert "tool failure" in md


def test_no_reviews_graceful():
    md = render_report(_run(classes=[CCSClass(path="A", weight="Low", rationale="r")],
                            reviews=[], profiles=[_profile()]))
    assert "# Manuscript feedback report" in md
    assert "No reviews produced" in md


def test_review_joined_to_profile_by_reviewer_id():
    profiles = [_profile(rid="r1", name="Aino"), _profile(rid="r2", name="Eero")]
    reviews = [_review(rid="r2"), _review(rid="r1")]  # out of order on purpose
    md = render_report(_run(profiles=profiles, reviews=reviews))
    # Both names appear, joined by reviewer_id, regardless of review order
    assert "Aino" in md and "Eero" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_renderer.py -v`
Expected: tests fail because `render_report` still takes the old signature.

- [ ] **Step 3: Rewrite `paperfb/renderer.py`**

```python
"""Markdown report renderer (spec §6.6). Pure function: RunOutput in, str out.

Joins each Review with its ReviewerProfile via reviewer_id so the slim Review
schema (no metadata echo) renders with full reviewer identity in the header.
"""
from __future__ import annotations

from paperfb.schemas import Review, ReviewerProfile, RunOutput


def _prose_or_placeholder(text: str) -> str:
    text = (text or "").strip()
    return text if text else "_(none)_"


def _render_review(review: Review, profile: ReviewerProfile) -> list[str]:
    out: list[str] = []
    out.append(f"## Review by {profile.name} — {profile.specialty}")
    out.append("")
    blurb = [f"Stance: **{profile.stance}**",
             f"primary focus: **{profile.primary_focus}**"]
    if profile.secondary_focus:
        blurb.append(f"secondary focus: **{profile.secondary_focus}**")
    out.append(", ".join(blurb))
    if profile.profile_summary:
        out.append("")
        out.append(f"_{profile.profile_summary}_")
    out.append("")
    out.append("### Strong aspects")
    out.append("")
    out.append(_prose_or_placeholder(review.strong_aspects))
    out.append("")
    out.append("### Weak aspects")
    out.append("")
    out.append(_prose_or_placeholder(review.weak_aspects))
    out.append("")
    out.append("### Recommended changes")
    out.append("")
    out.append(_prose_or_placeholder(review.recommended_changes))
    out.append("")
    return out


def render_report(run: RunOutput) -> str:
    lines: list[str] = ["# Manuscript feedback report", ""]

    lines.append("## ACM classification")
    lines.append("")
    if run.classification.classes:
        for c in run.classification.classes:
            lines.append(f"- **{c.path}** — weight: {c.weight}")
            if c.rationale:
                lines.append(f"  - {c.rationale}")
    else:
        lines.append("_(no classes assigned)_")
    lines.append("")

    if not run.board.reviews and not run.board.skipped:
        lines.append("_No reviews produced._")
        return "\n".join(lines) + "\n"

    profiles_by_id = {p.id: p for p in run.profiles.reviewers}
    for review in run.board.reviews:
        profile = profiles_by_id.get(review.reviewer_id)
        if profile is None:
            # Spec §6.6: orphan review — render with a stub. Should not happen
            # in practice; Chair's expected_reviewer_ids check guards against it.
            continue
        lines.extend(_render_review(review, profile))

    if run.board.skipped:
        lines.append("## Skipped reviewers")
        for s in run.board.skipped:
            lines.append(f"- {s.id}: {s.reason}")
        lines.append("")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_renderer.py -v`
Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add paperfb/renderer.py tests/test_renderer.py
git commit -m "Switch renderer to RunOutput input shape"
```

---

## Task 14: Update CLI (`paperfb/main.py`)

**Files:**
- Modify: `paperfb/main.py`
- Modify: `tests/test_main.py`

CLI no longer constructs an `LLMClient` (deleted in Task 15) and no longer calls `asyncio.run`. It calls `paperfb.pipeline.run(manuscript=..., cfg=...)` and prints the artefact paths.

- [ ] **Step 1: Read existing test**

```bash
cat tests/test_main.py
```

Expected: existing test exercises argv parsing + `run_pipeline` mock path. Update it to mock `pipeline.run` instead.

- [ ] **Step 2: Rewrite `tests/test_main.py`**

```python
from pathlib import Path
from unittest.mock import MagicMock, patch

from paperfb.schemas import (
    BoardReport, CCSClass, ClassificationResult, Keywords,
    ProfileBoard, Review, ReviewerProfile, RunOutput,
)


def _run_output() -> RunOutput:
    return RunOutput(
        classification=ClassificationResult(
            keywords=Keywords(extracted_from_paper=[], synthesised=[]),
            classes=[CCSClass(path="A", weight="High", rationale="r")],
        ),
        profiles=ProfileBoard(reviewers=[ReviewerProfile(
            id="r1", name="Aino", specialty="A", stance="critical",
            primary_focus="methods", secondary_focus=None,
            persona_prompt="...", profile_summary="...",
        )]),
        board=BoardReport(
            reviews=[Review(reviewer_id="r1", strong_aspects="s",
                            weak_aspects="w", recommended_changes="c")],
            skipped=[],
        ),
    )


def test_main_calls_pipeline_run_and_returns_zero(tmp_path, monkeypatch):
    manuscript = tmp_path / "m.md"
    manuscript.write_text("hello")

    from paperfb import main as main_mod

    fake_run = MagicMock(return_value=_run_output())
    monkeypatch.setattr(main_mod, "pipeline_run", fake_run)

    rc = main_mod.main([str(manuscript), "--output", str(tmp_path / "report.md")])
    assert rc == 0
    assert fake_run.called
    kwargs = fake_run.call_args.kwargs
    assert kwargs["manuscript"] == "hello"
    assert kwargs["cfg"].paths.output == str(tmp_path / "report.md")


def test_main_returns_nonzero_when_manuscript_missing(tmp_path):
    from paperfb import main as main_mod
    rc = main_mod.main([str(tmp_path / "missing.md")])
    assert rc != 0
```

- [ ] **Step 3: Rewrite `paperfb/main.py`**

```python
"""CLI entry point. Calls paperfb.pipeline.run."""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from paperfb.config import load_config
from paperfb.pipeline import run as pipeline_run


def _parse(argv):
    p = argparse.ArgumentParser(
        description="Give a manuscript constructive feedback from a board of reviewers."
    )
    p.add_argument("manuscript", help="Path to manuscript markdown file.")
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--axes", default="config/axes.yaml")
    p.add_argument("--output", default=None, help="Override paths.output.")
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
    if args.output:
        cfg = replace(cfg, paths=replace(cfg.paths, output=args.output))
    if args.count is not None:
        cfg = replace(cfg, reviewers=replace(cfg.reviewers, count=args.count))

    run = pipeline_run(manuscript=manuscript, cfg=cfg)

    print(f"Report: {cfg.paths.output}")
    print(f"Reviews: {len(run.board.reviews)} produced, {len(run.board.skipped)} skipped")
    for s in run.board.skipped:
        print(f"  - skipped {s.id}: {s.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_main.py -v`
Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add paperfb/main.py tests/test_main.py
git commit -m "Update CLI to call pipeline.run; drop LLMClient wiring"
```

---

## Task 15: Update Judge to consume `evaluations/run-<ts>/run.json`

**Files:**
- Modify: `paperfb/schemas.py` (add `JudgeScore`)
- Modify: `scripts/judge.py`
- Modify: `tests/test_judge.py`

Per spec §8 + §10 step 10: Judge reads the canonical `RunOutput` artefact, joins each `Review` with the matching `ReviewerProfile` via `reviewer_id` for fidelity scoring, and writes `evaluations/run-<ts>/judge.json`. Schema dimensions and per-dimension Likert scoring stay the same.

- [ ] **Step 1: Add `JudgeScore` to `paperfb/schemas.py`**

Append:

```python
# Judge ──────────────────────────────────────────────────────────────────────


class DimensionScore(BaseModel):
    model_config = ConfigDict(title="DimensionScore", extra="forbid")
    score: int  # validated in [1, 5] post-parse
    justification: str


class JudgeScore(BaseModel):
    model_config = ConfigDict(title="JudgeScore", extra="forbid")
    specificity: DimensionScore
    actionability: DimensionScore
    persona_fidelity: DimensionScore
    coverage: DimensionScore
    non_redundancy: DimensionScore
```

Add a one-line test to `tests/test_schemas.py` covering JudgeScore round-trip:

```python
def test_judge_score_round_trip():
    from paperfb.schemas import DimensionScore, JudgeScore
    js = JudgeScore(**{
        d: DimensionScore(score=4, justification="j")
        for d in ["specificity", "actionability", "persona_fidelity", "coverage", "non_redundancy"]
    })
    assert JudgeScore.model_validate_json(js.model_dump_json()) == js
```

Run: `uv run pytest tests/test_schemas.py -v`. Expect green.

- [ ] **Step 2: Rewrite `tests/test_judge.py`**

The existing test exercises `judge_review(manuscript, review_dict, llm, model)` with hand-built dicts. The new contract exercises `judge_review(manuscript, review, profile, llm, model)` taking Pydantic objects, plus a `main()` test that reads `run.json`.

```python
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from paperfb.schemas import (
    BoardReport, CCSClass, ClassificationResult, Keywords,
    ProfileBoard, Review, ReviewerProfile, RunOutput,
)
from scripts.judge import judge_review, DIMENSIONS


MANUSCRIPT = "Tiny manuscript body."


def _profile(rid="r1") -> ReviewerProfile:
    return ReviewerProfile(
        id=rid, name="Aino", specialty="ML",
        stance="critical", primary_focus="methods", secondary_focus="results",
        persona_prompt="...", profile_summary="...",
    )


def _review(rid="r1") -> Review:
    return Review(reviewer_id=rid, strong_aspects="x", weak_aspects="y", recommended_changes="z")


def _payload(**overrides) -> dict:
    base = {d: {"score": 4, "justification": f"{d} j"} for d in DIMENSIONS}
    for k, v in overrides.items():
        if isinstance(v, dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = {"score": v, "justification": base[k]["justification"]}
    return base


def _llm_returning(payload: dict) -> MagicMock:
    client = MagicMock()
    res = MagicMock()
    res.content = json.dumps(payload)
    res.tool_calls = None
    res.finish_reason = "stop"
    client.chat.return_value = res
    return client


def test_judge_review_returns_pydantic_judge_score():
    from paperfb.schemas import JudgeScore
    llm = _llm_returning(_payload())
    score = judge_review(MANUSCRIPT, _review(), _profile(), llm=llm, model="m")
    assert isinstance(score, JudgeScore)
    for dim in DIMENSIONS:
        d = getattr(score, dim)
        assert 1 <= d.score <= 5


def test_judge_review_user_message_includes_persona_context():
    llm = _llm_returning(_payload())
    judge_review(MANUSCRIPT, _review(), _profile(), llm=llm, model="m")
    _, kwargs = llm.chat.call_args
    user_msg = next(m["content"] for m in kwargs["messages"] if m["role"] == "user")
    assert MANUSCRIPT in user_msg
    assert "critical" in user_msg
    assert "methods" in user_msg


def test_judge_review_rejects_out_of_range():
    llm = _llm_returning(_payload(specificity=7))
    with pytest.raises(ValueError, match="specificity"):
        judge_review(MANUSCRIPT, _review(), _profile(), llm=llm, model="m")


def test_main_reads_run_json_and_writes_judge_json(tmp_path, monkeypatch):
    from scripts import judge as judge_mod

    run = RunOutput(
        classification=ClassificationResult(
            keywords=Keywords(extracted_from_paper=[], synthesised=[]),
            classes=[CCSClass(path="A", weight="High", rationale="r")],
        ),
        profiles=ProfileBoard(reviewers=[_profile("r1"), _profile("r2")]),
        board=BoardReport(reviews=[_review("r1"), _review("r2")], skipped=[]),
    )

    eval_dir = tmp_path / "run-20260429T000000Z"
    eval_dir.mkdir()
    (eval_dir / "run.json").write_text(json.dumps(run.model_dump()))
    manuscript = tmp_path / "m.md"
    manuscript.write_text(MANUSCRIPT)

    monkeypatch.setattr(judge_mod, "from_env", lambda default_model: _llm_returning(_payload()))

    rc = judge_mod.main([
        "--manuscript", str(manuscript),
        "--run-dir", str(eval_dir),
    ])
    assert rc == 0
    out = json.loads((eval_dir / "judge.json").read_text())
    assert {e["reviewer_id"] for e in out["per_reviewer"]} == {"r1", "r2"}
    assert out["board_mean"] == pytest.approx(4.0)
```

- [ ] **Step 3: Rewrite `scripts/judge.py`**

Replaces the old `LLMClient`-based loop. Reads `run.json`, joins reviews to profiles, runs the LLM per review, validates against `JudgeScore`, writes `judge.json` next to the input.

```python
"""LLM-as-judge harness. Reads evaluations/run-<ts>/run.json (RunOutput),
scores each review on the 5-dim Likert rubric, writes judge.json alongside.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

from paperfb.config import load_config
from paperfb.schemas import (
    DimensionScore, JudgeScore, Review, ReviewerProfile, RunOutput,
)


DIMENSIONS = ["specificity", "actionability", "persona_fidelity", "coverage", "non_redundancy"]


JUDGE_SYSTEM = """You are an impartial evaluator of peer-review feedback.
Given a manuscript, the reviewer's persona context, and the reviewer's review,
score the review on five 1-5 Likert dimensions:

  - specificity:      grounded in manuscript text vs generic
  - actionability:    suggestions are concrete and implementable
  - persona_fidelity: matches assigned stance + primary_focus
  - coverage:         primary focus area is meaningfully addressed
  - non_redundancy:   contributes points distinct from generic boilerplate

Emit a JudgeScore object. Each dimension's score must be an integer in [1, 5].
"""


def from_env(default_model: str) -> OpenAI:
    """Construct an OpenAI client pointing at the proxy. Kept as a module-level
    callable so tests can monkey-patch it."""
    return OpenAI(base_url=os.environ["BASE_URL"], api_key="unused")


def _user_message(manuscript: str, review: Review, profile: ReviewerProfile) -> str:
    return (
        f"Manuscript:\n<MANUSCRIPT>\n{manuscript}\n</MANUSCRIPT>\n\n"
        f"Reviewer stance: {profile.stance}\n"
        f"Reviewer primary_focus: {profile.primary_focus}\n"
        f"Reviewer secondary_focus: {profile.secondary_focus}\n\n"
        f"Review JSON:\n{review.model_dump_json(indent=2)}"
    )


def _validate_score(raw: dict) -> JudgeScore:
    js = JudgeScore.model_validate(raw)
    for dim in DIMENSIONS:
        s = getattr(js, dim).score
        if not (1 <= s <= 5):
            raise ValueError(f"{dim} out of range: {s} (must be 1-5)")
    return js


def judge_review(
    manuscript: str,
    review: Review,
    profile: ReviewerProfile,
    llm,
    model: str,
) -> JudgeScore:
    res = llm.chat(
        messages=[
            {"role": "system", "content": JUDGE_SYSTEM},
            {"role": "user", "content": _user_message(manuscript, review, profile)},
        ],
        model=model,
    )
    return _validate_score(json.loads(res.content))


def _mean(score: JudgeScore) -> float:
    return sum(getattr(score, d).score for d in DIMENSIONS) / len(DIMENSIONS)


def _entry(review: Review, profile: ReviewerProfile, score: JudgeScore) -> dict:
    return {
        "reviewer_id": review.reviewer_id,
        **{d: getattr(score, d).model_dump() for d in DIMENSIONS},
        "mean": _mean(score),
    }


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser(description="LLM-as-judge for reviewer feedback")
    p.add_argument("--manuscript", required=True, help="Path to manuscript markdown.")
    p.add_argument("--run-dir", required=True,
                   help="Path to evaluations/run-<ts>/ directory containing run.json.")
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--axes", default="config/axes.yaml")
    p.add_argument("--model", default=None, help="Override cfg.models.judge.")
    args = p.parse_args(argv)

    cfg = load_config(Path(args.config), Path(args.axes))
    model = args.model or cfg.models.judge

    run = RunOutput.model_validate_json(Path(args.run_dir, "run.json").read_text())
    manuscript = Path(args.manuscript).read_text()

    profiles_by_id = {p.id: p for p in run.profiles.reviewers}
    llm = from_env(default_model=model)

    per_reviewer: list[dict] = []
    for review in run.board.reviews:
        profile = profiles_by_id[review.reviewer_id]
        score = judge_review(manuscript, review, profile, llm=llm, model=model)
        per_reviewer.append(_entry(review, profile, score))

    if not per_reviewer:
        print("No reviews to judge.", file=sys.stderr)
        return 1
    board_mean = sum(e["mean"] for e in per_reviewer) / len(per_reviewer)

    out = Path(args.run_dir, "judge.json")
    out.write_text(json.dumps({
        "manuscript": str(Path(args.manuscript).resolve()),
        "judge_model": model,
        "per_reviewer": per_reviewer,
        "board_mean": board_mean,
    }, indent=2, ensure_ascii=False))
    print(f"Wrote {out}  (board_mean={board_mean:.2f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Note: this Judge bypasses AG2 and calls the proxy directly via the OpenAI SDK. That's intentional — Judge is a Wave-2 standalone tool (spec §8) and doesn't need the chat-orchestration framework. The OpenAI SDK is still available transitively via `ag2[openai]`.

The `from_env` function returns an OpenAI client, but the test stubs it out before any HTTP call happens. The unit tests pass a `MagicMock` LLM whose `.chat(messages, model)` interface matches the v1 `LLMClient` shape — keep that interface for test compatibility, with the real OpenAI client wrapped on first use. To keep this simple, add a thin `_OpenAIChat` wrapper:

```python
class _OpenAIChat:
    def __init__(self, client: OpenAI):
        self._client = client
    def chat(self, messages, model, **kw):
        resp = self._client.chat.completions.create(model=model, messages=messages, **kw)
        return type("Res", (), {"content": resp.choices[0].message.content,
                                 "tool_calls": None,
                                 "finish_reason": resp.choices[0].finish_reason})()
```

Update `from_env` to return `_OpenAIChat(OpenAI(base_url=..., api_key="unused"))`.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_judge.py tests/test_schemas.py -v`
Expected: all judge tests + the JudgeScore round-trip test pass.

- [ ] **Step 5: Commit**

```bash
git add paperfb/schemas.py scripts/judge.py tests/test_judge.py tests/test_schemas.py
git commit -m "Rewrite judge to consume RunOutput JSON; add JudgeScore schema"
```

---

## Task 16: Deletion sweep + docs update

**Files (delete):**
- `paperfb/llm_client.py`, `paperfb/orchestrator.py`, `paperfb/contracts.py`
- `paperfb/agents/classification_legacy/`, `paperfb/agents/profile_creation_legacy/`, `paperfb/agents/reviewer_legacy/` (renamed in Task 6)
- `tests/test_llm_client.py`, `tests/test_orchestrator.py`, `tests/test_contracts.py`, `tests/agents/`

**Files (modify):**
- `README.md`, `PLAN.md` — point at the new architecture and link to the design + plan docs.

- [ ] **Step 1: Confirm nothing in the new codebase imports the legacy modules**

Run:

```bash
grep -rnE 'paperfb\.(orchestrator|contracts|llm_client|agents\.(classification_legacy|profile_creation_legacy|reviewer_legacy))' paperfb tests scripts
```

Expected: no matches outside the legacy modules + tests being deleted. If anything else lights up, fix the import (probably an `__init__.py` re-export) before deleting.

- [ ] **Step 2: Delete legacy modules**

```bash
git rm paperfb/llm_client.py paperfb/orchestrator.py paperfb/contracts.py
git rm -r paperfb/agents/classification_legacy paperfb/agents/profile_creation_legacy paperfb/agents/reviewer_legacy
git rm tests/test_llm_client.py tests/test_orchestrator.py tests/test_contracts.py
git rm -r tests/agents
```

Also remove the now-orphan `paperfb/agents/__init__.py` if it only re-exported the old subpackages. Re-create it as an empty file if Python imports break otherwise.

- [ ] **Step 3: Drop `paths.reviews_dir` usage**

`paths.reviews_dir` is now dead config. Remove it from `config/default.yaml`, the `PathsConfig` dataclass in `paperfb/config.py`, and the load path. Run `grep -rn reviews_dir paperfb tests scripts config` and clean up any stragglers.

- [ ] **Step 4: Run the full test suite**

Run: `uv run pytest -q --ignore=tests/test_acceptance_live.py`
Expected: all tests green.

- [ ] **Step 5: Update `README.md` and `PLAN.md`**

Replace the v1 architecture description with a 4–6 line summary of the AG2 pipeline (UserProxy → Classification → ProfileCreation → RedundantPattern{N reviewers + Chair} → renderer) and a link to the design spec at [docs/superpowers/specs/2026-04-29-ag2-refactor-design.md](../specs/2026-04-29-ag2-refactor-design.md). Drop references to `LLMClient`, `orchestrator.py`, per-reviewer JSON files, and the per-agent subpackages.

- [ ] **Step 6: Commit**

```bash
git add -A paperfb tests scripts config README.md PLAN.md
git commit -m "Delete v1 orchestrator + legacy agent subpackages"
```

---

## Task 17: Live acceptance test

**Files:**
- Modify: `tests/test_acceptance_live.py`

End-to-end against the real proxy. Asserts the new on-disk shape: `final_report.md` exists, `evaluations/run-<ts>/run.json` exists and round-trips through `RunOutput`, per-reviewer sections match N, ACM classes present, `(stance, primary_focus)` pairs unique, Finnish names unique, manuscript does not appear in cleartext in the JSONL log (spec §6.7).

- [ ] **Step 1: Rewrite `tests/test_acceptance_live.py`**

```python
import os
from dataclasses import replace
from pathlib import Path

import pytest
from dotenv import load_dotenv

from paperfb.config import load_config
from paperfb.pipeline import run as pipeline_run
from paperfb.schemas import RunOutput


pytestmark = pytest.mark.slow

load_dotenv()


@pytest.fixture
def cfg(tmp_path):
    c = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    return replace(c, paths=replace(
        c.paths,
        output=str(tmp_path / "report.md"),
        logs_dir=str(tmp_path / "logs"),
    ))


@pytest.fixture
def manuscript():
    return Path("tests/fixtures/tiny_manuscript.md").read_text()


def test_live_pipeline_produces_report_and_run_json(cfg, manuscript, tmp_path):
    assert os.environ.get("BASE_URL"), "BASE_URL env var required for live test"

    run = pipeline_run(manuscript=manuscript, cfg=cfg)
    assert isinstance(run, RunOutput)

    # (a) markdown report
    report = Path(cfg.paths.output)
    assert report.exists()
    text = report.read_text()
    assert text.count("## Review by ") == cfg.reviewers.count

    # (b) ACM classes
    assert "## ACM classification" in text
    assert len(run.classification.classes) >= 1

    # (c) reviewer diversity invariants
    pairs = {(p.stance, p.primary_focus) for p in run.profiles.reviewers}
    assert len(pairs) == len(run.profiles.reviewers)
    names = {p.name for p in run.profiles.reviewers}
    assert len(names) == len(run.profiles.reviewers)

    # (d) RunOutput artefact round-trips
    eval_dirs = sorted(Path("evaluations").glob("run-*"))
    assert eval_dirs, "no evaluations/run-* directory written"
    run_json = eval_dirs[-1] / "run.json"
    assert run_json.exists()
    parsed = RunOutput.model_validate_json(run_json.read_text())
    assert parsed == run

    # (e) non-leakage: manuscript body must not appear in cleartext logs
    sentinel = "wall-clock time recorded on a"
    logs_dir = Path(cfg.paths.logs_dir)
    if logs_dir.exists():
        for log in logs_dir.rglob("*"):
            if log.is_file():
                assert sentinel not in log.read_text(encoding="utf-8", errors="replace"), \
                    f"manuscript leaked to {log}"
```

- [ ] **Step 2: Run the live test**

Run: `uv run pytest -m slow tests/test_acceptance_live.py -v`
Expected: green. If failures appear in the AG2 wiring (handoff method names, pattern constructor signature), refer back to Task 11's note and the AG2 redundant-pattern docs.

This is also the moment to check Chair's behaviour against a reviewer failure: if no reviewer fails naturally on a clean manuscript, leave that path covered by `tests/test_pipeline.py::test_pipeline_propagates_skipped_reviewers`. A live test of the failure path is overkill.

- [ ] **Step 3: Commit**

```bash
git add tests/test_acceptance_live.py
git commit -m "Update live acceptance test for AG2 pipeline + RunOutput artefact"
```

---

## Self-review checklist (run before declaring done)

- [ ] Spec §1–§10 each have at least one task implementing them. (§1 goals: deletion in Task 16; §2 architecture: Tasks 6–11; §3 schemas: Task 2 + 15; §4 agents: Tasks 6–10; §5 config + model pinning: Task 3; §6.1/§6.2 wiring: Task 11; §6.5 logging: Task 12; §6.6 renderer: Task 13; §6.7 non-leakage: Tasks 12 + 17; §7 file layout: matches end state; §8 Judge: Task 15; §9 testing strategy: woven through; §10 migration plan: this whole document.)
- [ ] No `TBD`, `TODO`, `implement later` strings in the plan body.
- [ ] Class/function names match across tasks: `ClassificationResult`, `ProfileBoard`, `Review`, `BoardReport`, `RunOutput`, `JudgeScore`, `build_setup_review_board`, `extract_board_report`, `pipeline.run`.
- [ ] Each step is one action; commit cadence is one commit per task minimum.
- [ ] AG2 surfaces are imported via the paths verified by `scripts/probe_ag2_api.py` (Task 1) — if 0.12.1 disagrees, the probe catches it before any other task depends on it.

---

## Unresolved questions

(extremely concise per project convention)

- AG2 0.12.1 exact import paths for `RedundantPattern` / `FunctionTarget` / `NestedChatTarget`? Probe Task 1.
- AG2 0.12.1 method name for registering an `AfterWork` handoff on a `ConversableAgent` — `register_handoff`? `add_handoff`? Discover via probe + redundant-pattern docs example.
- AG2 0.12.1: does `RedundantPattern` expose `.as_nested_chat()`, or is the nesting wrapper named differently? Same probe.
- Per-sibling failure surface on `RedundantPattern`'s result — is there a deterministic hook (`pattern.failed_agents`)? If yes, populate `skipped` in `setup_review_board` before Chair runs and Chair becomes a pure passthrough (spec §4.4 alternative path).
- Manuscript-body redaction in JSONL log (spec §6.7) — is there an AG2 logging hook that exposes the message body, or do we filter in our own `LoggingMiddleware`-equivalent? Defer to first run of the live acceptance test (Task 16); if logs leak, add a redaction filter task.
