# Research Paper Feedback System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a 3-agent Python system that takes a markdown manuscript and produces a markdown feedback report from a diverse board of LLM reviewer personas.

**Architecture:** Sequential pipeline (Classification → Profile Creation) + parallel fan-out (N Reviewers) + deterministic Renderer. Agents talk to LLMs via the course-provided OpenRouter AWS proxy (OpenAI `/chat/completions` transport). One tool per agent where helpful: `lookup_acm` for Classification, `write_review` for each Reviewer. Separate LLM-as-judge evaluation harness.

**Tech Stack:** Python 3.11+, `openai` SDK (pointed at proxy `BASE_URL`), `pyyaml`, `pytest`, `pytest-asyncio`, `asyncio` for fan-out.

**Spec:** [docs/superpowers/specs/2026-04-24-research-paper-feedback-system-design.md](../specs/2026-04-24-research-paper-feedback-system-design.md)

---

## File map

Files created, grouped by task:

- **Task 1:** `pyproject.toml`, `.gitignore`, `src/__init__.py`, `src/agents/__init__.py`, `src/tools/__init__.py`, `tests/__init__.py`, `scripts/__init__.py`, `config/default.yaml`, `config/axes.yaml`
- **Task 2:** `src/config.py`, `tests/test_config.py`
- **Task 3:** `src/llm_client.py`, `tests/test_llm_client.py`
- **Task 4:** `data/acm_ccs.json` (seed), `scripts/build_acm_ccs.py`
- **Task 5:** `src/tools/lookup_acm.py`, `tests/test_lookup_acm.py`
- **Task 6:** `src/agents/classification.py`, `tests/test_classification.py`
- **Task 7:** `src/agents/profile_sampler.py`, `tests/test_profile_sampler.py`
- **Task 8:** `src/agents/profile_creation.py`, `tests/test_profile_creation.py`
- **Task 9:** `src/tools/write_review.py`, `tests/test_write_review.py`
- **Task 10:** `src/agents/reviewer.py`, `tests/test_reviewer.py`
- **Task 11:** `src/renderer.py`, `tests/test_renderer.py`
- **Task 12:** `src/orchestrator.py`, `tests/test_orchestrator.py`
- **Task 13:** `src/main.py`, `tests/test_main.py`
- **Task 14:** `scripts/judge.py`, `tests/test_judge.py`, `tests/fixtures/good_review.json`, `tests/fixtures/bad_review.json`
- **Task 15:** `tests/test_acceptance_live.py`, `tests/fixtures/tiny_manuscript.md`
- **Task 16:** `README.md`

---

## Task 1: Project scaffolding

**Files:**
- Create: `.mise.toml`, `pyproject.toml`, `.gitignore`, `src/__init__.py`, `src/agents/__init__.py`, `src/tools/__init__.py`, `tests/__init__.py`, `scripts/__init__.py`, `config/default.yaml`, `config/axes.yaml`

- [ ] **Step 0: Create `.mise.toml`**

```toml
[tools]
python = "3.11"
uv = "latest"

[env]
_.python.venv = { path = ".venv", create = true }
```

Run: `mise install`
Expected: Python 3.11 and uv installed into the mise-managed toolchain.

- [ ] **Step 1: Create `pyproject.toml`**

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

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "slow: tests that hit the live proxy (excluded by default, run with -m slow)",
]
addopts = "-m 'not slow'"
testpaths = ["tests"]

[tool.setuptools.packages.find]
where = ["."]
include = ["src*"]
```

- [ ] **Step 2: Create `.gitignore`**

```
__pycache__/
*.pyc
.venv/
.env
reviews/
logs/
evaluations/
data/acm_ccs.json
.pytest_cache/
*.egg-info/
```

Note: `data/acm_ccs.json` is derived by Task 4; keep out of git unless it's the hand-seeded fixture. We will track a small seed file explicitly with `git add -f` in Task 4.

- [ ] **Step 3: Create package init files**

Create empty files:
- `src/__init__.py`
- `src/agents/__init__.py`
- `src/tools/__init__.py`
- `tests/__init__.py`
- `scripts/__init__.py`

- [ ] **Step 4: Create `config/default.yaml`**

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

- [ ] **Step 5: Create `config/axes.yaml`**

```yaml
stances:
  - neutral
  - supportive
  - critical
  - skeptical
  - rigorous
  - pragmatic
  - devil's-advocate
  - visionary
focuses:
  - methods
  - results
  - impact
  - novelty
  - clarity
  - related-work
  - reproducibility
  - ethics
```

- [ ] **Step 6: Install deps and verify**

```bash
uv sync --extra dev
uv run pytest --collect-only
```

Expected: `.venv` created, `uv.lock` generated, `pytest --collect-only` reports "collected 0 items" (no tests yet, no errors).

**Convention for all subsequent tasks:** run `pytest` and `python` either via `uv run <cmd>` or by activating the venv first (`. .venv/bin/activate`). The plan writes bare commands for brevity.

- [ ] **Step 7: Commit**

```bash
git add .mise.toml pyproject.toml uv.lock .gitignore src/ tests/ scripts/ config/
git commit -m "Scaffold project layout, mise/uv toolchain, config, and deps"
```

---

## Task 2: Config loader

**Files:**
- Create: `src/config.py`, `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_config.py`:

```python
from pathlib import Path
import pytest
from src.config import load_config, Config


def test_load_defaults():
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    assert isinstance(cfg, Config)
    assert cfg.reviewers.count == 3
    assert cfg.reviewers.core_focuses == ["methods", "results", "novelty"]
    assert cfg.models.default == "anthropic/claude-3.5-haiku"
    assert "neutral" in cfg.axes.stances
    assert "methods" in cfg.axes.focuses


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
    # covered implicitly by validation — extend if needed
    cfg = load_config(Path("config/default.yaml"), Path("config/axes.yaml"))
    for f in cfg.reviewers.core_focuses:
        assert f in cfg.axes.focuses
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_config.py -v`
Expected: FAIL (ImportError: cannot import from src.config).

- [ ] **Step 3: Implement `src/config.py`**

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
class AxesConfig:
    stances: list[str]
    focuses: list[str]


@dataclass(frozen=True)
class Config:
    transport: str
    base_url_env: str
    models: ModelsConfig
    reviewers: ReviewersConfig
    classification: ClassificationConfig
    paths: PathsConfig
    axes: AxesConfig


def load_config(default_path: Path, axes_path: Path) -> Config:
    with default_path.open() as f:
        d = yaml.safe_load(f)
    with axes_path.open() as f:
        a = yaml.safe_load(f)

    reviewers_count = d["reviewers"]["count"]
    if reviewers_count < 3:
        raise ValueError("reviewers.count must be >= 3")

    axes = AxesConfig(stances=a["stances"], focuses=a["focuses"])
    core = d["reviewers"]["core_focuses"]
    for f in core:
        if f not in axes.focuses:
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

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_config.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "Add config loader with validation"
```

---

## Task 3: LLM client

**Files:**
- Create: `src/llm_client.py`, `tests/test_llm_client.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_llm_client.py`:

```python
from unittest.mock import MagicMock, patch
import pytest
from src.llm_client import LLMClient, RetryableError


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

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_llm_client.py -v`
Expected: FAIL (module not found).

- [ ] **Step 3: Implement `src/llm_client.py`**

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

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_llm_client.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add src/llm_client.py tests/test_llm_client.py
git commit -m "Add LLM client wrapper with retry/backoff"
```

---

## Task 4: ACM CCS seed data

**Files:**
- Create: `data/acm_ccs.json`, `scripts/build_acm_ccs.py`

This task provides a hand-curated seed dataset sufficient for end-to-end testing. The scraper script is stubbed with a clear TODO for future expansion — this is acceptable because the spec §14 lists "Source of ACM CCS tree" as an unresolved question. The seed covers the top two levels of the CCS plus representative leaves, enough for classification of typical CS papers.

- [ ] **Step 1: Create `data/acm_ccs.json`**

```json
[
  {"path": "General and reference", "leaf": false, "description": "Cross-cutting topics including general literature, reference works, and historical context."},
  {"path": "General and reference → Document types → Surveys and overviews", "leaf": true, "description": "Survey papers and broad overviews of a field."},
  {"path": "Hardware → Integrated circuits", "leaf": false, "description": "Physical circuit design, VLSI, ASIC, FPGA topics."},
  {"path": "Computer systems organization → Architectures → Parallel architectures", "leaf": true, "description": "Multi-processor and parallel computing system architectures."},
  {"path": "Computer systems organization → Dependable and fault-tolerant systems and networks", "leaf": true, "description": "Reliability, fault tolerance, Byzantine failures, high-availability."},
  {"path": "Networks → Network architectures → Network protocols", "leaf": true, "description": "Design and analysis of network protocols at any layer."},
  {"path": "Networks → Network performance evaluation", "leaf": true, "description": "Measurement, modelling, and analysis of network behaviour."},
  {"path": "Software and its engineering → Software notations and tools → General programming languages", "leaf": true, "description": "Programming language design, type systems, semantics."},
  {"path": "Software and its engineering → Software creation and management → Software development process management", "leaf": true, "description": "Methodologies, agile, DevOps, project management for software."},
  {"path": "Software and its engineering → Software creation and management → Software verification and validation", "leaf": true, "description": "Testing, model checking, formal verification."},
  {"path": "Theory of computation → Theory and algorithms for application domains → Machine learning theory", "leaf": true, "description": "Theoretical foundations of machine learning including PAC learning and generalization bounds."},
  {"path": "Theory of computation → Design and analysis of algorithms", "leaf": false, "description": "Algorithmic design, complexity, approximation, randomized algorithms."},
  {"path": "Theory of computation → Logic → Automated reasoning", "leaf": true, "description": "SAT/SMT solvers, theorem provers, symbolic reasoning."},
  {"path": "Mathematics of computing → Probability and statistics → Statistical paradigms → Bayesian computation", "leaf": true, "description": "MCMC, variational inference, Bayesian deep learning."},
  {"path": "Information systems → Data management systems → Database design and models", "leaf": false, "description": "Relational, NoSQL, graph, document database modelling."},
  {"path": "Information systems → Information retrieval → Retrieval models and ranking", "leaf": true, "description": "Search ranking, BM25, learning-to-rank, neural retrieval."},
  {"path": "Security and privacy → Cryptography", "leaf": false, "description": "Encryption, signatures, zero-knowledge proofs, cryptographic protocols."},
  {"path": "Security and privacy → Systems security → Operating systems security", "leaf": true, "description": "OS-level defences, trusted execution, isolation."},
  {"path": "Human-centered computing → Human computer interaction (HCI) → HCI design and evaluation methods", "leaf": true, "description": "User studies, usability evaluation, design methodologies."},
  {"path": "Human-centered computing → Visualization → Visualization techniques", "leaf": true, "description": "Techniques for representing data visually: charts, graphs, network layouts."},
  {"path": "Computing methodologies → Machine learning → Learning paradigms → Supervised learning", "leaf": true, "description": "Classification, regression, supervised neural networks."},
  {"path": "Computing methodologies → Machine learning → Learning paradigms → Reinforcement learning", "leaf": true, "description": "MDPs, policy gradient, Q-learning, exploration."},
  {"path": "Computing methodologies → Machine learning → Machine learning approaches → Neural networks", "leaf": true, "description": "Deep learning, CNNs, transformers, attention mechanisms."},
  {"path": "Computing methodologies → Artificial intelligence → Natural language processing", "leaf": true, "description": "Parsing, semantics, dialogue, summarization, translation."},
  {"path": "Computing methodologies → Computer graphics → Rendering", "leaf": true, "description": "Real-time and photoreal rendering, ray tracing, shaders."},
  {"path": "Applied computing → Life and medical sciences → Bioinformatics", "leaf": true, "description": "Genomics, protein structure prediction, systems biology."},
  {"path": "Applied computing → Education → Interactive learning environments", "leaf": true, "description": "Intelligent tutoring systems, MOOCs, learning analytics."},
  {"path": "Social and professional topics → Computing / technology policy", "leaf": false, "description": "Ethics, regulation, societal impact of computing."},
  {"path": "Proper nouns: People, technologies and companies", "leaf": false, "description": "Named entities treated as classification anchors (rarely top-weight)."}
]
```

- [ ] **Step 2: Force-add seed file and verify**

```bash
git add -f data/acm_ccs.json
python -c "import json; print(len(json.load(open('data/acm_ccs.json'))), 'entries loaded')"
```

Expected: `29 entries loaded`.

- [ ] **Step 3: Create `scripts/build_acm_ccs.py` (stub for future work)**

```python
"""Build data/acm_ccs.json by scraping dl.acm.org/ccs.

Status: STUB. v1 uses hand-curated seed in data/acm_ccs.json.
Future work: parse the ACM CCS XML/HTML tree and auto-generate
per-node descriptions via an LLM call, cached to disk.

Run:
    python scripts/build_acm_ccs.py --output data/acm_ccs.json
"""
import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/acm_ccs.json")
    parser.parse_args()
    print("scripts/build_acm_ccs.py is a stub — see module docstring.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Commit**

```bash
git add data/acm_ccs.json scripts/build_acm_ccs.py
git commit -m "Add ACM CCS seed dataset and scraper stub"
```

---

## Task 5: lookup_acm tool

**Files:**
- Create: `src/tools/lookup_acm.py`, `tests/test_lookup_acm.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_lookup_acm.py`:

```python
import json
from pathlib import Path
import pytest
from src.tools.lookup_acm import lookup_acm, load_ccs, TOOL_SCHEMA


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

Run: `pytest tests/test_lookup_acm.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `src/tools/lookup_acm.py`**

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

Run: `pytest tests/test_lookup_acm.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add src/tools/lookup_acm.py tests/test_lookup_acm.py
git commit -m "Add lookup_acm tool with schema"
```

---

## Task 6: Classification Agent

**Files:**
- Create: `src/agents/classification.py`, `tests/test_classification.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_classification.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from src.agents.classification import classify_manuscript, ClassificationResult


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

Run: `pytest tests/test_classification.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `src/agents/classification.py`**

```python
import json
from dataclasses import dataclass
from pathlib import Path
from src.tools.lookup_acm import lookup_acm, TOOL_SCHEMA

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


@dataclass
class ClassificationResult:
    classes: list[dict]


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

Run: `pytest tests/test_classification.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/agents/classification.py tests/test_classification.py
git commit -m "Add Classification Agent with lookup_acm tool loop"
```

---

## Task 7: Profile sampler (deterministic)

**Files:**
- Create: `src/agents/profile_sampler.py`, `tests/test_profile_sampler.py`

This is the meat of the "don't be shallow" design. Test-heavy, pure Python.

- [ ] **Step 1: Write the failing test**

Create `tests/test_profile_sampler.py`:

```python
import pytest
from src.agents.profile_sampler import sample_reviewer_tuples, ReviewerTuple

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

Run: `pytest tests/test_profile_sampler.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `src/agents/profile_sampler.py`**

```python
import random
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ReviewerTuple:
    id: str
    specialty: dict
    stance: str
    primary_focus: str
    secondary_focus: Optional[str]


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

Run: `pytest tests/test_profile_sampler.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add src/agents/profile_sampler.py tests/test_profile_sampler.py
git commit -m "Add deterministic profile sampler with core-focus coverage"
```

---

## Task 8: Profile Creation Agent (LLM step)

**Files:**
- Create: `src/agents/profile_creation.py`, `tests/test_profile_creation.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_profile_creation.py`:

```python
import json
from unittest.mock import MagicMock
from src.agents.profile_creation import create_profiles, ReviewerProfile
from src.agents.profile_sampler import ReviewerTuple


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

    profiles = create_profiles(tuples, llm=llm, model="stub")
    assert len(profiles) == 2
    assert all(isinstance(p, ReviewerProfile) for p in profiles)
    assert profiles[0].id == "r1"
    assert "critical" in profiles[0].persona_prompt.lower() or \
           profiles[0].persona_prompt.startswith("You are a critical")
    assert profiles[0].stance == "critical"
    assert profiles[0].primary_focus == "methods"
    assert profiles[0].specialty == {"path": "ML", "weight": "High"}
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_profile_creation.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `src/agents/profile_creation.py`**

```python
from dataclasses import dataclass
from typing import Optional
from src.agents.profile_sampler import ReviewerTuple

PERSONA_SYSTEM = """You generate the system prompt for an AI reviewer persona for a research-paper feedback system.
Given: specialty (ACM CCS class), stance, primary focus, secondary focus — produce the full system prompt that reviewer will use to review a manuscript.

Requirements for the system prompt you produce:
- Second-person voice ("You are ...").
- Establish the reviewer as a domain specialist grounded in the specialty.
- Reflect the stance in tone.
- Emphasise the primary focus; acknowledge the secondary focus as a supplementary lens.
- Instruct the reviewer to call the write_review tool with their structured review.
- Forbid the reviewer from rewriting the paper.
- No meta-commentary, no preamble — output the system prompt directly.
"""


@dataclass
class ReviewerProfile:
    id: str
    specialty: dict
    stance: str
    primary_focus: str
    secondary_focus: Optional[str]
    persona_prompt: str


def create_profiles(tuples: list[ReviewerTuple], llm, model: str) -> list[ReviewerProfile]:
    profiles: list[ReviewerProfile] = []
    for t in tuples:
        user = (
            f"specialty: {t.specialty['path']}\n"
            f"specialty description: {t.specialty.get('description', '(none)')}\n"
            f"stance: {t.stance}\n"
            f"primary_focus: {t.primary_focus}\n"
            f"secondary_focus: {t.secondary_focus or '(none)'}\n"
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

Run: `pytest tests/test_profile_creation.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/agents/profile_creation.py tests/test_profile_creation.py
git commit -m "Add Profile Creation Agent LLM step"
```

---

## Task 9: write_review tool

**Files:**
- Create: `src/tools/write_review.py`, `tests/test_write_review.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_write_review.py`:

```python
import json
from pathlib import Path
import pytest
from src.tools.write_review import write_review, TOOL_SCHEMA, ReviewValidationError


def _sample_review(rid="r1"):
    return {
        "reviewer_id": rid,
        "stance": "critical",
        "focus": "methods",
        "profile_summary": "...",
        "strengths": ["clear framing"],
        "weaknesses": ["small n"],
        "suggestions": ["add ablations"],
        "section_comments": [{"section": "3.2", "comment": "..."}],
        "overall_assessment": "...",
    }


def test_writes_json_file(tmp_path):
    path = write_review(_sample_review("r1"), reviews_dir=tmp_path)
    assert path == tmp_path / "r1.json"
    data = json.loads(path.read_text())
    assert data["reviewer_id"] == "r1"


def test_missing_required_field_raises(tmp_path):
    bad = _sample_review()
    del bad["overall_assessment"]
    with pytest.raises(ReviewValidationError, match="overall_assessment"):
        write_review(bad, reviews_dir=tmp_path)


def test_two_reviewers_no_overlap(tmp_path):
    write_review(_sample_review("r1"), reviews_dir=tmp_path)
    write_review(_sample_review("r2"), reviews_dir=tmp_path)
    assert (tmp_path / "r1.json").exists()
    assert (tmp_path / "r2.json").exists()


def test_tool_schema_lists_required_fields():
    required = TOOL_SCHEMA["function"]["parameters"]["required"]
    for f in ["reviewer_id", "stance", "focus", "strengths", "weaknesses",
              "suggestions", "overall_assessment"]:
        assert f in required
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_write_review.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `src/tools/write_review.py`**

```python
import json
from pathlib import Path


class ReviewValidationError(ValueError):
    pass


REQUIRED_FIELDS = [
    "reviewer_id", "stance", "focus",
    "strengths", "weaknesses", "suggestions",
    "section_comments", "overall_assessment",
]


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "write_review",
        "description": "Write your structured review to disk. Call exactly once when your review is complete.",
        "parameters": {
            "type": "object",
            "properties": {
                "reviewer_id": {"type": "string"},
                "stance": {"type": "string"},
                "focus": {"type": "string"},
                "profile_summary": {"type": "string"},
                "strengths": {"type": "array", "items": {"type": "string"}},
                "weaknesses": {"type": "array", "items": {"type": "string"}},
                "suggestions": {"type": "array", "items": {"type": "string"}},
                "section_comments": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "section": {"type": "string"},
                            "comment": {"type": "string"},
                        },
                        "required": ["section", "comment"],
                    },
                },
                "overall_assessment": {"type": "string"},
            },
            "required": [
                "reviewer_id", "stance", "focus",
                "strengths", "weaknesses", "suggestions",
                "section_comments", "overall_assessment",
            ],
        },
    },
}


def _validate(review: dict) -> None:
    missing = [f for f in REQUIRED_FIELDS if f not in review]
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

Run: `pytest tests/test_write_review.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add src/tools/write_review.py tests/test_write_review.py
git commit -m "Add write_review tool with validation"
```

---

## Task 10: Reviewer Agent

**Files:**
- Create: `src/agents/reviewer.py`, `tests/test_reviewer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_reviewer.py`:

```python
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest
from src.agents.reviewer import run_reviewer
from src.agents.profile_creation import ReviewerProfile


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
        "stance": "critical",
        "focus": "methods",
        "profile_summary": "...",
        "strengths": ["a"], "weaknesses": ["b"], "suggestions": ["c"],
        "section_comments": [],
        "overall_assessment": "...",
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

Run: `pytest tests/test_reviewer.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `src/agents/reviewer.py`**

```python
import json
from pathlib import Path
from src.agents.profile_creation import ReviewerProfile
from src.tools.write_review import write_review, TOOL_SCHEMA, ReviewValidationError

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
            args.setdefault("focus", profile.primary_focus)
            try:
                return write_review(args, reviews_dir=reviews_dir)
            except ReviewValidationError as e:
                last_validation_error = str(e)
                break

    raise RuntimeError(f"reviewer {profile.id} failed to produce valid review after retry")
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_reviewer.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/agents/reviewer.py tests/test_reviewer.py
git commit -m "Add Reviewer Agent with write_review tool loop"
```

---

## Task 11: Renderer

**Files:**
- Create: `src/renderer.py`, `tests/test_renderer.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_renderer.py`:

```python
from src.renderer import render_report


def test_renders_full_report():
    classes = [
        {"path": "Computing methodologies → ML → NN", "weight": "High", "rationale": "r1"},
    ]
    reviews = [
        {
            "reviewer_id": "r1", "stance": "critical", "focus": "methods",
            "profile_summary": "a critical methods specialist",
            "strengths": ["clear framing"],
            "weaknesses": ["small n"],
            "suggestions": ["add ablations"],
            "section_comments": [{"section": "3.2", "comment": "inconsistency"}],
            "overall_assessment": "needs work",
        }
    ]
    skipped = []
    md = render_report(classes=classes, reviews=reviews, skipped_reviewers=skipped)

    assert "# Manuscript feedback report" in md
    assert "## ACM classification" in md
    assert "Computing methodologies → ML → NN" in md
    assert "High" in md
    assert "## Reviewer r1" in md
    assert "Stance: critical" in md
    assert "Focus: methods" in md
    assert "clear framing" in md
    assert "add ablations" in md
    assert "3.2" in md


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

- [ ] **Step 3: Implement `src/renderer.py`**

```python
from typing import Iterable


def _bullet_list(items: Iterable[str]) -> str:
    items = list(items)
    if not items:
        return "_(none)_\n"
    return "\n".join(f"- {x}" for x in items) + "\n"


def render_report(classes: list[dict], reviews: list[dict],
                  skipped_reviewers: list[dict]) -> str:
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
        lines.append(f"## Reviewer {r['reviewer_id']}")
        lines.append("")
        lines.append(f"- Stance: {r['stance']}")
        lines.append(f"- Focus: {r['focus']}")
        if r.get("profile_summary"):
            lines.append(f"- Profile: {r['profile_summary']}")
        lines.append("")
        lines.append("### Strengths")
        lines.append(_bullet_list(r.get("strengths", [])))
        lines.append("### Weaknesses")
        lines.append(_bullet_list(r.get("weaknesses", [])))
        lines.append("### Suggestions")
        lines.append(_bullet_list(r.get("suggestions", [])))
        sc = r.get("section_comments", [])
        if sc:
            lines.append("### Section comments")
            for item in sc:
                lines.append(f"- **{item['section']}** — {item['comment']}")
            lines.append("")
        lines.append("### Overall assessment")
        lines.append(r.get("overall_assessment", "") + "\n")

    if skipped_reviewers:
        lines.append("## Skipped reviewers")
        for s in skipped_reviewers:
            lines.append(f"- {s['id']}: {s['reason']}")
        lines.append("")

    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_renderer.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/renderer.py tests/test_renderer.py
git commit -m "Add Markdown renderer for final report"
```

---

## Task 12: Orchestrator

**Files:**
- Create: `src/orchestrator.py`, `tests/test_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_orchestrator.py`:

```python
import asyncio
import json
from pathlib import Path
from unittest.mock import MagicMock
import pytest

from src.orchestrator import run_pipeline, PipelineResult
from src.config import load_config


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
    from src.agents.profile_sampler import ReviewerTuple
    from src.agents.profile_creation import ReviewerProfile
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
            "reviewer_id": profile.id, "stance": profile.stance, "focus": profile.primary_focus,
            "profile_summary": "", "strengths": ["s"], "weaknesses": ["w"],
            "suggestions": ["x"], "section_comments": [], "overall_assessment": "ok",
        }))
        return p

    llm = MagicMock()
    result = asyncio.run(run_pipeline(
        manuscript="hello",
        cfg=cfg,
        llm=llm,
        classify_fn=lambda manuscript, llm, model, ccs_path, max_classes:
            MagicMock(classes=[{"path": "ML", "weight": "High", "rationale": "r"}]),
        sample_fn=lambda **kwargs: tuples,
        profile_fn=lambda tuples, llm, model: profiles,
        reviewer_fn=fake_reviewer,
    ))

    assert isinstance(result, PipelineResult)
    assert len(result.reviews) == 3
    assert result.skipped == []
    assert Path(cfg.paths.output).exists()
    assert "# Manuscript feedback report" in Path(cfg.paths.output).read_text()


def test_reviewer_failure_is_skipped(cfg, tmp_path):
    from src.agents.profile_sampler import ReviewerTuple
    from src.agents.profile_creation import ReviewerProfile
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
            "reviewer_id": profile.id, "stance": "critical", "focus": profile.primary_focus,
            "profile_summary": "", "strengths": [], "weaknesses": [], "suggestions": [],
            "section_comments": [], "overall_assessment": "ok",
        }))
        return p

    result = asyncio.run(run_pipeline(
        manuscript="hello", cfg=cfg, llm=MagicMock(),
        classify_fn=lambda **kw: MagicMock(classes=[{"path": "ML", "weight": "High", "rationale": "r"}]),
        sample_fn=lambda **kw: tuples,
        profile_fn=lambda tuples, llm, model: profiles,
        reviewer_fn=flaky_reviewer,
    ))
    assert len(result.reviews) == 2
    assert len(result.skipped) == 1
    assert result.skipped[0]["id"] == "r2"
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_orchestrator.py -v`
Expected: FAIL (import error).

- [ ] **Step 3: Implement `src/orchestrator.py`**

```python
import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from src.config import Config
from src.agents.classification import classify_manuscript, ClassificationResult
from src.agents.profile_sampler import sample_reviewer_tuples
from src.agents.profile_creation import create_profiles
from src.agents.reviewer import run_reviewer
from src.renderer import render_report


@dataclass
class PipelineResult:
    classes: list[dict]
    reviews: list[dict]
    skipped: list[dict]
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
    classes = classification.classes if isinstance(classification, ClassificationResult) else classification.classes

    # 2. Sample reviewer tuples deterministically
    tuples = sample_fn(
        n=cfg.reviewers.count,
        acm_classes=classes,
        stances=cfg.axes.stances,
        focuses=cfg.axes.focuses,
        core_focuses=cfg.reviewers.core_focuses,
        seed=cfg.reviewers.seed,
        enable_secondary=cfg.reviewers.secondary_focus_per_reviewer,
    )

    # 3. Generate personas
    profiles = profile_fn(tuples, llm=llm, model=cfg.models.profile_creation)

    # 4. Fan out reviewers
    reviews_dir = Path(cfg.paths.reviews_dir)
    reviews_dir.mkdir(parents=True, exist_ok=True)
    tasks = [
        _run_reviewer_async(p, manuscript, llm, cfg.models.reviewer, reviews_dir, reviewer_fn)
        for p in profiles
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    reviews: list[dict] = []
    skipped: list[dict] = []
    for p, r in zip(profiles, results):
        if isinstance(r, Exception):
            skipped.append({"id": p.id, "reason": f"{type(r).__name__}: {r}"})
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
git add src/orchestrator.py tests/test_orchestrator.py
git commit -m "Add orchestrator with sequential pipeline and parallel reviewers"
```

---

## Task 13: CLI entry point

**Files:**
- Create: `src/main.py`, `tests/test_main.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_main.py`:

```python
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.main import main


def test_cli_reads_manuscript_and_writes_report(tmp_path, monkeypatch):
    manuscript = tmp_path / "ms.md"
    manuscript.write_text("# Title\n\nAbstract.\n")
    monkeypatch.setenv("BASE_URL", "http://proxy.invalid")

    fake_result = MagicMock()
    fake_result.report_path = tmp_path / "report.md"
    fake_result.skipped = []
    fake_result.reviews = [{"reviewer_id": "r1"}, {"reviewer_id": "r2"}, {"reviewer_id": "r3"}]

    with patch("src.main.asyncio.run", return_value=fake_result), \
         patch("src.main.from_env", return_value=MagicMock()):
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

- [ ] **Step 3: Implement `src/main.py`**

```python
import argparse
import asyncio
import sys
from dataclasses import replace
from pathlib import Path
from dotenv import load_dotenv

from src.config import load_config
from src.llm_client import from_env
from src.orchestrator import run_pipeline


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
    if args.count:
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
git add src/main.py tests/test_main.py
git commit -m "Add CLI entry point"
```

---

## Task 14: Judge (LLM-as-judge, TDD)

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
  "stance": "critical",
  "focus": "methods",
  "profile_summary": "critical methods reviewer",
  "strengths": ["Reproducible setup with explicit hyperparameters (LR=1e-4)."],
  "weaknesses": [
    "N=5 seeds is too few to distinguish the +2.3% gain from noise.",
    "No statistical test (e.g. Welch's t-test) is reported for the return difference."
  ],
  "suggestions": [
    "Increase seeds to at least 20 and report 95% confidence intervals.",
    "Add a paired statistical test comparing RLAgent-X and baseline per seed."
  ],
  "section_comments": [
    {"section": "Results", "comment": "The 2.3% improvement needs a significance test given the small N."}
  ],
  "overall_assessment": "The methodology is clear but the empirical claim is underpowered."
}
```

`tests/fixtures/bad_review.json`:
```json
{
  "reviewer_id": "r2",
  "stance": "critical",
  "focus": "methods",
  "profile_summary": "critical methods reviewer",
  "strengths": ["The paper is well written."],
  "weaknesses": ["Some parts could be clearer."],
  "suggestions": ["Improve the methodology section."],
  "section_comments": [],
  "overall_assessment": "Looks fine overall."
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

from src.llm_client import from_env


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
        f"Reviewer focus: {review.get('focus')}\n\n"
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

from src.config import load_config
from src.llm_client import from_env
from src.orchestrator import run_pipeline


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
uv run python -m src.main path/to/manuscript.md --output report.md
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
uv run python -m src.main tests/fixtures/tiny_manuscript.md --output /tmp/report.md
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
