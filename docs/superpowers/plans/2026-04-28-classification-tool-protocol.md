# Classification Tool-Protocol Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Classification Agent's free-text JSON commit channel with a `submit_classification` tool call, and tighten `lookup_acm` to word-boundary multi-token matching — closing the two failure modes hit by `anthropic/claude-3.5-haiku` in live acceptance.

**Architecture:** Mirror Reviewer Agent's tool-call commit pattern. Two tools (`lookup_acm` read channel, `submit_classification` write channel). Loop terminates when `submit_classification` validates; one validation retry per submit (same shape as Reviewer's `write_review`). Loop budget 6 → 8. ACM CCS data stays as flat `data/acm_ccs.json` — no representation changes.

**Tech Stack:** Python 3, stdlib `re`, stdlib `logging`, `pytest`, existing `paperfb.contracts.ClassificationResult`. `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest …` is the canonical test invocation in this repo.

**Spec:** [`docs/superpowers/specs/2026-04-27-classification-tool-protocol-design.md`](../specs/2026-04-27-classification-tool-protocol-design.md).

---

## File map

- `paperfb/agents/classification/tools.py` — Task 1 improves `lookup_acm`; Task 2 adds `submit_classification`, `ClassificationValidationError`, and `TOOL_SCHEMAS`.
- `paperfb/agents/classification/agent.py` — Task 2 swaps the import to `TOOL_SCHEMAS`; Task 3 rewrites the loop.
- `tests/agents/classification/test_tools.py` — Task 1 adds word-boundary / multi-token / `parent_path` cases; Task 2 adds validator cases and updates the schema test.
- `tests/agents/classification/test_agent.py` — Task 3 fully rewrites for tool-call mocks.
- `paperfb/agents/classification/__init__.py` — unchanged (no new public exports — `ClassificationValidationError` is internal to the agent loop).
- `paperfb/contracts.py` — unchanged (`ClassificationResult.classes` shape preserved).
- `tests/test_acceptance_live.py` — unchanged (slow-marked, manual).

---

## Task 1: Improve `lookup_acm` — word-boundary, multi-token AND, `parent_path`

**Files:**
- Modify: `paperfb/agents/classification/tools.py`
- Modify: `tests/agents/classification/test_tools.py`

**Background for the implementer:**
- Path entries use ` → ` (U+2192 with surrounding spaces) as the segment separator, e.g. `"A → B → C"`. `parent_path` for that is `"A → B"`. For a top-level entry like `"A"`, `parent_path` is `""`.
- Word-boundary matching: split the query on whitespace into tokens, build a case-insensitive regex `r"\b" + re.escape(token) + r"\b"` per token, and require **every** token regex to match `path + " " + description`. This is AND across tokens.
- Use `re.escape` on each token — queries can contain regex metachars (`.`, `+`, `(`, etc.). Without escaping these are silent bugs.
- The arrow ` → ` is not a word character, so `\b` boundaries work cleanly around segment names.
- `lru_cache` on `load_ccs` stays. The fixture rewrites the cached file per-test (`tmp_path` makes paths unique), so cache collisions are not an issue.
- `TOOL_SCHEMA` (singular) stays in this task. Task 2 renames to `TOOL_SCHEMAS`.

- [ ] **Step 1: Write failing tests in `test_tools.py`**

Replace the entire contents of `tests/agents/classification/test_tools.py` with:

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
        {"path": "Web → Markup → HTML", "leaf": True,
         "description": "HyperText Markup Language documents."},
        {"path": "Computing → ML", "leaf": True,
         "description": "Machine learning subfield."},
    ]
    p = tmp_path / "ccs.json"
    p.write_text(json.dumps(data))
    return p


def test_matches_by_description_word(ccs_path):
    results = lookup_acm("machine learning", k=10, ccs_path=ccs_path)
    paths = {r["path"] for r in results}
    assert paths == {"A → B", "E", "Computing → ML"}


def test_matches_by_path_segment(ccs_path):
    results = lookup_acm("database", k=5, ccs_path=ccs_path)
    assert len(results) == 1
    assert results[0]["path"] == "C → D"


def test_word_boundary_does_not_match_substring(ccs_path):
    # "ML" must not match "HTML"
    results = lookup_acm("ML", k=10, ccs_path=ccs_path)
    paths = {r["path"] for r in results}
    assert paths == {"Computing → ML"}


def test_multi_token_query_is_AND(ccs_path):
    # "machine database" matches NO entry (no entry contains both tokens)
    results = lookup_acm("machine database", k=10, ccs_path=ccs_path)
    assert results == []


def test_multi_token_query_AND_positive(ccs_path):
    # "machine learning" already covered above (both tokens present in 3 entries)
    results = lookup_acm("learning machine", k=10, ccs_path=ccs_path)
    paths = {r["path"] for r in results}
    assert paths == {"A → B", "E", "Computing → ML"}


def test_parent_path_populated(ccs_path):
    results = lookup_acm("machine", k=10, ccs_path=ccs_path)
    by_path = {r["path"]: r for r in results}
    assert by_path["A → B"]["parent_path"] == "A"
    assert by_path["E"]["parent_path"] == ""
    assert by_path["Computing → ML"]["parent_path"] == "Computing"


def test_returned_entry_has_leaf_and_description(ccs_path):
    results = lookup_acm("database", k=5, ccs_path=ccs_path)
    r = results[0]
    assert r["leaf"] is True
    assert "Database" in r["description"]


def test_respects_k(ccs_path):
    results = lookup_acm("stuff", k=1, ccs_path=ccs_path)
    assert len(results) == 1


def test_no_matches_returns_empty(ccs_path):
    results = lookup_acm("quantum cats", k=5, ccs_path=ccs_path)
    assert results == []


def test_query_with_regex_metachars_does_not_explode(ccs_path):
    # query containing "." and "(" must not raise; just no matches
    results = lookup_acm("c++ (notation)", k=5, ccs_path=ccs_path)
    assert results == []


def test_tool_schema_has_required_fields():
    assert TOOL_SCHEMA["type"] == "function"
    assert TOOL_SCHEMA["function"]["name"] == "lookup_acm"
    assert "query" in TOOL_SCHEMA["function"]["parameters"]["properties"]


def test_load_ccs_from_file(ccs_path):
    entries = load_ccs(ccs_path)
    assert len(entries) == 5
    assert entries[0]["path"] == "A → B"
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/agents/classification/test_tools.py -q`

Expected: at minimum `test_word_boundary_does_not_match_substring`, `test_multi_token_query_is_AND`, and `test_parent_path_populated` FAIL. (The current substring matcher will return "HTML" for "ML" and will treat "machine database" as a single substring search.)

- [ ] **Step 3: Implement word-boundary, multi-token AND, and `parent_path` in `tools.py`**

Replace `paperfb/agents/classification/tools.py` with:

```python
import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional


PATH_SEPARATOR = " → "


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "lookup_acm",
        "description": (
            "Search the ACM CCS for concept paths matching one or more keywords. "
            "Query is split on whitespace; every token must match (case-insensitive, "
            "word-boundary) the entry's path or description. Returns up to k entries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "One or more whitespace-separated keywords.",
                },
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


def _parent_path(path: str) -> str:
    segments = path.split(PATH_SEPARATOR)
    return PATH_SEPARATOR.join(segments[:-1]) if len(segments) > 1 else ""


def _leaf(path: str) -> str:
    return path.split(PATH_SEPARATOR)[-1]


def _token_patterns(query: str) -> list[re.Pattern]:
    tokens = query.lower().split()
    return [re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in tokens]


def lookup_acm(query: str, k: int = 10, ccs_path: Optional[Path] = None) -> list[dict]:
    if ccs_path is None:
        ccs_path = Path("data/acm_ccs.json")
    entries = load_ccs(ccs_path)
    patterns = _token_patterns(query)
    if not patterns:
        return []
    matches: list[dict] = []
    for e in entries:
        hay = e["path"] + " " + e.get("description", "")
        if all(p.search(hay) for p in patterns):
            matches.append({
                "path": e["path"],
                "leaf": _leaf(e["path"]),
                "description": e.get("description", ""),
                "parent_path": _parent_path(e["path"]),
            })
        if len(matches) >= k:
            break
    return matches
```

Note: `leaf` in the returned dict is now the **leaf segment string**, per spec §2 (`{path, leaf, description, parent_path}`). The stored `leaf` boolean from the data file is intentionally not surfaced — the agent gets richer information from the segment string and can infer hierarchy from `parent_path`.

- [ ] **Step 4: Run tests to confirm they pass**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/agents/classification/test_tools.py -q`

Expected: all 12 tests PASS.

- [ ] **Step 5: Run the full classification suite to confirm no regression in `test_agent.py`**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/agents/classification -q`

Expected: all tests PASS. (`test_agent.py` still uses the old prose-JSON protocol; it does not exercise `lookup_acm` return shape directly.)

- [ ] **Step 6: Commit**

```bash
git add paperfb/agents/classification/tools.py tests/agents/classification/test_tools.py
git commit -m "Tighten lookup_acm to word-boundary multi-token AND with parent_path"
```

---

## Task 2: Add `submit_classification` tool, validator, and `TOOL_SCHEMAS`

**Files:**
- Modify: `paperfb/agents/classification/tools.py`
- Modify: `paperfb/agents/classification/agent.py` (import-only change in this task)
- Modify: `tests/agents/classification/test_tools.py`

**Background for the implementer:**
- The validator `submit_classification` mirrors the role of `write_review` in [`paperfb/agents/reviewer/tools.py`](../../../paperfb/agents/reviewer/tools.py): pure validation, raises `ClassificationValidationError` on bad input, returns the typed result on success.
- `ClassificationValidationError` extends `ValueError` (consistent with `ReviewValidationError` in the Reviewer module).
- The validator receives `ccs_entries` (the loaded tuple from `load_ccs`) so path-existence is checked against actual loaded data, not a hard-coded list.
- The keywords block is logged via stdlib `logging` for downstream Judge consumption and **not** placed on `ClassificationResult` — `ClassificationResult.classes` shape is preserved per spec §1.
- `TOOL_SCHEMA` (singular) is removed in favor of `TOOL_SCHEMAS` (a list of two schemas). `agent.py`'s import is updated in the same task so the package remains importable; the agent's loop body is rewritten in Task 3.

- [ ] **Step 1: Write failing tests for the validator and schema in `test_tools.py`**

Append the following to `tests/agents/classification/test_tools.py` (and update the existing `test_tool_schema_has_required_fields` per the next sub-step):

```python
# --- submit_classification validator ---

from paperfb.agents.classification.tools import (
    submit_classification,
    ClassificationValidationError,
    TOOL_SCHEMAS,
)
from paperfb.contracts import ClassificationResult


@pytest.fixture
def ccs_entries():
    return (
        {"path": "Computing methodologies → Machine learning", "leaf": False,
         "description": "ML overview."},
        {"path": "Computing methodologies → Machine learning → Neural networks",
         "leaf": True, "description": "Deep learning, CNNs, RNNs."},
    )


def _valid_args(path="Computing methodologies → Machine learning → Neural networks"):
    return {
        "keywords": {
            "extracted_from_paper": ["neural network"],
            "synthesised": [],
        },
        "classes": [
            {"path": path, "weight": "High", "rationale": "primary topic"},
        ],
    }


def test_submit_returns_classification_result(ccs_entries):
    r = submit_classification(_valid_args(), ccs_entries=ccs_entries, max_classes=5)
    assert isinstance(r, ClassificationResult)
    assert len(r.classes) == 1
    assert r.classes[0]["weight"] == "High"


def test_submit_rejects_empty_classes(ccs_entries):
    args = _valid_args()
    args["classes"] = []
    with pytest.raises(ClassificationValidationError, match="classes"):
        submit_classification(args, ccs_entries=ccs_entries, max_classes=5)


def test_submit_rejects_too_many_classes(ccs_entries):
    args = _valid_args()
    args["classes"] = [
        {"path": "Computing methodologies → Machine learning → Neural networks",
         "weight": "High", "rationale": "x"}
    ] * 3
    with pytest.raises(ClassificationValidationError, match="max_classes"):
        submit_classification(args, ccs_entries=ccs_entries, max_classes=2)


def test_submit_rejects_unknown_path(ccs_entries):
    args = _valid_args(path="Made up → Path")
    with pytest.raises(ClassificationValidationError, match="path"):
        submit_classification(args, ccs_entries=ccs_entries, max_classes=5)


def test_submit_rejects_bad_weight(ccs_entries):
    args = _valid_args()
    args["classes"][0]["weight"] = "Critical"
    with pytest.raises(ClassificationValidationError, match="weight"):
        submit_classification(args, ccs_entries=ccs_entries, max_classes=5)


def test_submit_rejects_missing_keywords_block(ccs_entries):
    args = _valid_args()
    del args["keywords"]
    with pytest.raises(ClassificationValidationError, match="keywords"):
        submit_classification(args, ccs_entries=ccs_entries, max_classes=5)


def test_submit_rejects_keywords_both_empty(ccs_entries):
    args = _valid_args()
    args["keywords"] = {"extracted_from_paper": [], "synthesised": []}
    with pytest.raises(ClassificationValidationError, match="keywords"):
        submit_classification(args, ccs_entries=ccs_entries, max_classes=5)


def test_submit_accepts_keywords_only_synthesised(ccs_entries):
    args = _valid_args()
    args["keywords"] = {"extracted_from_paper": [], "synthesised": ["deep learning"]}
    r = submit_classification(args, ccs_entries=ccs_entries, max_classes=5)
    assert len(r.classes) == 1


def test_submit_rejects_missing_classes_field(ccs_entries):
    args = _valid_args()
    del args["classes"]
    with pytest.raises(ClassificationValidationError, match="classes"):
        submit_classification(args, ccs_entries=ccs_entries, max_classes=5)


# --- TOOL_SCHEMAS ---

def test_tool_schemas_lists_both_tools():
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert names == {"lookup_acm", "submit_classification"}


def test_submit_schema_requires_keywords_and_classes():
    submit = next(
        s for s in TOOL_SCHEMAS if s["function"]["name"] == "submit_classification"
    )
    required = submit["function"]["parameters"]["required"]
    assert set(required) == {"keywords", "classes"}
```

Also **update** the existing `test_tool_schema_has_required_fields` (which referenced `TOOL_SCHEMA`, removed in this task) to reference the lookup schema inside `TOOL_SCHEMAS`. Replace this test:

```python
def test_tool_schema_has_required_fields():
    assert TOOL_SCHEMA["type"] == "function"
    assert TOOL_SCHEMA["function"]["name"] == "lookup_acm"
    assert "query" in TOOL_SCHEMA["function"]["parameters"]["properties"]
```

with:

```python
def test_lookup_schema_has_required_fields():
    schema = next(
        s for s in TOOL_SCHEMAS if s["function"]["name"] == "lookup_acm"
    )
    assert schema["type"] == "function"
    assert "query" in schema["function"]["parameters"]["properties"]
```

And remove `TOOL_SCHEMA` from the top-of-file import — leave only `lookup_acm, load_ccs`.

- [ ] **Step 2: Run tests to confirm they fail**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/agents/classification/test_tools.py -q`

Expected: all the new tests FAIL with `ImportError` (or `AttributeError`) for `submit_classification`, `ClassificationValidationError`, `TOOL_SCHEMAS`.

- [ ] **Step 3: Implement validator, error class, and schemas in `tools.py`**

Replace `paperfb/agents/classification/tools.py` with:

```python
import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from paperfb.contracts import ClassificationResult


log = logging.getLogger(__name__)

PATH_SEPARATOR = " → "
WEIGHTS = ("High", "Medium", "Low")


class ClassificationValidationError(ValueError):
    pass


LOOKUP_ACM_SCHEMA = {
    "type": "function",
    "function": {
        "name": "lookup_acm",
        "description": (
            "Search the ACM CCS for concept paths matching one or more keywords. "
            "Query is split on whitespace; every token must match (case-insensitive, "
            "word-boundary) the entry's path or description. Returns up to k entries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "One or more whitespace-separated keywords.",
                },
                "k": {"type": "integer", "description": "Max results.", "default": 10},
            },
            "required": ["query"],
        },
    },
}


SUBMIT_CLASSIFICATION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_classification",
        "description": (
            "Commit your final classification. Call exactly once when you have decided. "
            "First emit the keywords you extracted or synthesised; then emit the chosen "
            "ACM CCS classes with weight (High|Medium|Low) and a short rationale."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "object",
                    "properties": {
                        "extracted_from_paper": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "synthesised": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["extracted_from_paper", "synthesised"],
                },
                "classes": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "path":      {"type": "string"},
                            "weight":    {"type": "string", "enum": list(WEIGHTS)},
                            "rationale": {"type": "string"},
                        },
                        "required": ["path", "weight", "rationale"],
                    },
                },
            },
            "required": ["keywords", "classes"],
        },
    },
}


TOOL_SCHEMAS = [LOOKUP_ACM_SCHEMA, SUBMIT_CLASSIFICATION_SCHEMA]


@lru_cache(maxsize=8)
def load_ccs(ccs_path: Path) -> tuple[dict, ...]:
    with Path(ccs_path).open() as f:
        data = json.load(f)
    return tuple(data)


def _parent_path(path: str) -> str:
    segments = path.split(PATH_SEPARATOR)
    return PATH_SEPARATOR.join(segments[:-1]) if len(segments) > 1 else ""


def _leaf(path: str) -> str:
    return path.split(PATH_SEPARATOR)[-1]


def _token_patterns(query: str) -> list[re.Pattern]:
    tokens = query.lower().split()
    return [re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in tokens]


def lookup_acm(query: str, k: int = 10, ccs_path: Optional[Path] = None) -> list[dict]:
    if ccs_path is None:
        ccs_path = Path("data/acm_ccs.json")
    entries = load_ccs(ccs_path)
    patterns = _token_patterns(query)
    if not patterns:
        return []
    matches: list[dict] = []
    for e in entries:
        hay = e["path"] + " " + e.get("description", "")
        if all(p.search(hay) for p in patterns):
            matches.append({
                "path": e["path"],
                "leaf": _leaf(e["path"]),
                "description": e.get("description", ""),
                "parent_path": _parent_path(e["path"]),
            })
        if len(matches) >= k:
            break
    return matches


def submit_classification(
    args: dict, *, ccs_entries: tuple, max_classes: int
) -> ClassificationResult:
    if "keywords" not in args:
        raise ClassificationValidationError("missing required field: keywords")
    if "classes" not in args:
        raise ClassificationValidationError("missing required field: classes")

    kw = args["keywords"]
    extracted = kw.get("extracted_from_paper", []) if isinstance(kw, dict) else []
    synthesised = kw.get("synthesised", []) if isinstance(kw, dict) else []
    if not extracted and not synthesised:
        raise ClassificationValidationError(
            "keywords.extracted_from_paper and keywords.synthesised are both empty"
        )

    classes = args["classes"]
    if not isinstance(classes, list) or len(classes) == 0:
        raise ClassificationValidationError("classes must be a non-empty list")
    if len(classes) > max_classes:
        raise ClassificationValidationError(
            f"classes has {len(classes)} entries; max_classes={max_classes}"
        )

    known_paths = {e["path"] for e in ccs_entries}
    for c in classes:
        if c.get("weight") not in WEIGHTS:
            raise ClassificationValidationError(
                f"weight must be one of {WEIGHTS}; got {c.get('weight')!r}"
            )
        if c.get("path") not in known_paths:
            raise ClassificationValidationError(
                f"path not in CCS data: {c.get('path')!r}"
            )

    log.info(
        "classification keywords: extracted=%s synthesised=%s",
        extracted, synthesised,
    )
    return ClassificationResult(classes=list(classes))
```

- [ ] **Step 4: Update `agent.py` import so the package still imports cleanly**

In `paperfb/agents/classification/agent.py`, change line 4 from:

```python
from paperfb.agents.classification.tools import lookup_acm, TOOL_SCHEMA
```

to:

```python
from paperfb.agents.classification.tools import lookup_acm, TOOL_SCHEMAS
```

And change the loop's `tools = [TOOL_SCHEMA]` (currently line 24) to:

```python
    tools = TOOL_SCHEMAS
```

Leave the rest of `agent.py` untouched in this task — Task 3 rewrites the loop body. The existing `test_agent.py` mocks the LLM and never actually invokes `submit_classification`, so the old prose-JSON path still passes.

- [ ] **Step 5: Run the full classification suite to confirm green**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/agents/classification -q`

Expected: all tests PASS — both the new validator/schema tests and the existing prose-JSON `test_agent.py` cases.

- [ ] **Step 6: Run the full repo suite to confirm no other module imported `TOOL_SCHEMA` from this package**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest -q`

Expected: full green. (Reviewer's `TOOL_SCHEMA` lives in `paperfb.agents.reviewer.tools` — distinct module, unaffected.)

- [ ] **Step 7: Commit**

```bash
git add paperfb/agents/classification/tools.py paperfb/agents/classification/agent.py tests/agents/classification/test_tools.py
git commit -m "Add submit_classification tool, validator, and TOOL_SCHEMAS"
```

---

## Task 3: Rewrite the classification agent loop

**Files:**
- Modify: `paperfb/agents/classification/agent.py`
- Modify: `tests/agents/classification/test_agent.py`

**Background for the implementer:**
- Loop structure mirrors [`paperfb/agents/reviewer/agent.py`](../../../paperfb/agents/reviewer/agent.py) — a single termination point (the validator), nudge on no-tool-call, retry on validation error.
- Loop budget per spec §1: **8** (was 6).
- Per-turn behavior:
  - LLM produces zero or more tool calls. The current bug at `agent.py:30-32` vs `39-41` (calling `lookup_acm` twice and discarding the first result) is fixed by computing each tool call's result exactly once and appending it to `messages` immediately.
  - If `submit_classification` validates, return the result.
  - If `submit_classification` raises `ClassificationValidationError`, append a tool result conveying the error to the model and continue the loop with one retry budget. (Spec §5: "capped at one retry per submit attempt." Implemented by feeding the error back as a `tool` message; the model then has a fresh turn to either fix or abort.)
  - If the LLM returns no tool calls, append a nudge user message and continue.
- The system prompt absorbs spec §4.1's two-phase guidance (extract/synthesise keywords first, then look up) and the spec §2 weight rubric.
- The tool-call/tool-result message shape matches the existing Reviewer pattern and the OpenAI/LiteLLM tool-calling protocol already in use across this repo.

- [ ] **Step 1: Replace `tests/agents/classification/test_agent.py` with the new mock-driven cases**

Replace the entire contents of `tests/agents/classification/test_agent.py` with:

```python
import json
from unittest.mock import MagicMock
import pytest
from paperfb.agents.classification import classify_manuscript, ClassificationResult


# --- mock helpers ---

def _tc(name, args, call_id="call_1"):
    tc = MagicMock()
    tc.id = call_id
    tc.type = "function"
    tc.function.name = name
    tc.function.arguments = json.dumps(args)
    return tc


def _msg_tool_calls(*calls):
    r = MagicMock()
    r.content = None
    r.tool_calls = list(calls)
    r.finish_reason = "tool_calls"
    r.raw = None
    return r


def _msg_text(content):
    r = MagicMock()
    r.content = content
    r.tool_calls = None
    r.finish_reason = "stop"
    r.raw = None
    return r


# --- fixtures ---

@pytest.fixture
def ccs_file(tmp_path):
    data = [
        {"path": "Computing methodologies → Machine learning → Neural networks",
         "leaf": True, "description": "Deep learning."},
        {"path": "Computing methodologies → Machine learning",
         "leaf": False, "description": "Machine learning overview."},
    ]
    p = tmp_path / "ccs.json"
    p.write_text(json.dumps(data))
    return p


def _good_submit_args(path="Computing methodologies → Machine learning → Neural networks"):
    return {
        "keywords": {
            "extracted_from_paper": ["convolutional neural network"],
            "synthesised": [],
        },
        "classes": [
            {"path": path, "weight": "High", "rationale": "core topic"},
        ],
    }


# --- tests ---

def test_happy_path_lookup_then_submit(ccs_file):
    client = MagicMock()
    client.chat.side_effect = [
        _msg_tool_calls(
            _tc("lookup_acm", {"query": "neural networks"}, call_id="c1"),
            _tc("lookup_acm", {"query": "deep learning"}, call_id="c2"),
        ),
        _msg_tool_calls(_tc("submit_classification", _good_submit_args(), call_id="c3")),
    ]
    result = classify_manuscript(
        manuscript="We train a CNN.",
        llm=client,
        model="stub",
        ccs_path=ccs_file,
        max_classes=5,
    )
    assert isinstance(result, ClassificationResult)
    assert result.classes[0]["weight"] == "High"
    assert client.chat.call_count == 2


def test_bad_weight_retries_then_succeeds(ccs_file):
    bad = _good_submit_args()
    bad["classes"][0]["weight"] = "Critical"
    good = _good_submit_args()
    client = MagicMock()
    client.chat.side_effect = [
        _msg_tool_calls(_tc("submit_classification", bad, call_id="c1")),
        _msg_tool_calls(_tc("submit_classification", good, call_id="c2")),
    ]
    result = classify_manuscript("m", client, "stub", ccs_file, 5)
    assert result.classes[0]["weight"] == "High"
    assert client.chat.call_count == 2


def test_unknown_path_retries_then_succeeds(ccs_file):
    bad = _good_submit_args(path="Made up → Path")
    good = _good_submit_args()
    client = MagicMock()
    client.chat.side_effect = [
        _msg_tool_calls(_tc("submit_classification", bad, call_id="c1")),
        _msg_tool_calls(_tc("submit_classification", good, call_id="c2")),
    ]
    result = classify_manuscript("m", client, "stub", ccs_file, 5)
    assert len(result.classes) == 1


def test_empty_classes_retries_then_succeeds(ccs_file):
    bad = _good_submit_args()
    bad["classes"] = []
    good = _good_submit_args()
    client = MagicMock()
    client.chat.side_effect = [
        _msg_tool_calls(_tc("submit_classification", bad, call_id="c1")),
        _msg_tool_calls(_tc("submit_classification", good, call_id="c2")),
    ]
    result = classify_manuscript("m", client, "stub", ccs_file, 5)
    assert len(result.classes) == 1


def test_no_tool_call_nudges_then_recovers(ccs_file):
    client = MagicMock()
    client.chat.side_effect = [
        _msg_text("here is some prose"),
        _msg_tool_calls(_tc("submit_classification", _good_submit_args(), call_id="c1")),
    ]
    result = classify_manuscript("m", client, "stub", ccs_file, 5)
    assert len(result.classes) == 1
    assert client.chat.call_count == 2


def test_prose_preamble_with_json_still_treated_as_no_tool_call(ccs_file):
    """Regression: model emits 'Sure, here's...{json}' as text content with no tool call.
    The new loop nudges instead of JSON-parsing."""
    client = MagicMock()
    final_json = json.dumps({"classes": [{"path": "X", "weight": "High", "rationale": "y"}]})
    client.chat.side_effect = [
        _msg_text(f"Sure, here's the classification: {final_json}"),
        _msg_tool_calls(_tc("submit_classification", _good_submit_args(), call_id="c1")),
    ]
    result = classify_manuscript("m", client, "stub", ccs_file, 5)
    assert len(result.classes) == 1


def test_budget_exhausted_only_lookups(ccs_file):
    client = MagicMock()
    client.chat.side_effect = [
        _msg_tool_calls(_tc("lookup_acm", {"query": "x"}, call_id=f"c{i}"))
        for i in range(8)
    ]
    with pytest.raises(RuntimeError, match="budget"):
        classify_manuscript("m", client, "stub", ccs_file, 5)
    assert client.chat.call_count == 8
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/agents/classification/test_agent.py -q`

Expected: most cases FAIL — the existing loop JSON-parses `res.content`, doesn't recognise `submit_classification`, and never retries on validation error.

- [ ] **Step 3: Replace `paperfb/agents/classification/agent.py` with the new loop**

Replace the entire contents of `paperfb/agents/classification/agent.py` with:

```python
import json
from pathlib import Path

from paperfb.contracts import ClassificationResult
from paperfb.agents.classification.tools import (
    lookup_acm,
    submit_classification,
    load_ccs,
    TOOL_SCHEMAS,
    ClassificationValidationError,
)


SYSTEM_PROMPT = """You classify a computer-science research manuscript against the ACM Computing Classification System (CCS).

Procedure:
1. Read the manuscript. Extract the keywords actually used in it (extracted_from_paper).
   If the paper's vocabulary is non-standard or sparse, also synthesise canonical
   keywords that describe the same work (synthesised). At least one of the two lists
   must be non-empty.
2. Drive lookup_acm queries from those keywords. Multi-token queries are AND across
   tokens with word-boundary matching, so prefer multiple short queries over one long
   one. Match is case-insensitive.
3. Pick 1–{max_classes} CCS classes. Prefer leaf nodes; use higher-level nodes only
   when no leaf fits.
4. Commit by calling submit_classification exactly once. Do not emit free-text JSON.

Weight rubric:
- High:   central topic — would appear in the title or first sentence of the abstract;
          the paper's primary contribution lives here.
- Medium: significant supporting topic — methods, frameworks, or domains the work
          substantially uses.
- Low:    relevant but not central — mentioned, compared against, or touched on.

Use the lookup_acm tool one or more times before committing. Every path you submit
must come from lookup_acm results — do not invent paths."""


_LOOP_BUDGET = 8


def _nudge_no_tool_call() -> dict:
    return {
        "role": "user",
        "content": (
            "You must call lookup_acm or submit_classification. "
            "Do not reply in plain text."
        ),
    }


def _assistant_with_tool_calls(res, tool_calls: list) -> dict:
    return {
        "role": "assistant",
        "content": res.content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in tool_calls
        ],
    }


def _tool_result(tc, payload) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tc.id,
        "content": json.dumps(payload),
    }


def classify_manuscript(
    manuscript: str, llm, model: str, ccs_path: Path, max_classes: int
) -> ClassificationResult:
    ccs_entries = load_ccs(ccs_path)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(max_classes=max_classes)},
        {"role": "user", "content": f"Manuscript:\n\n{manuscript}"},
    ]

    for _ in range(_LOOP_BUDGET):
        res = llm.chat(messages=messages, tools=TOOL_SCHEMAS, model=model)

        if not res.tool_calls:
            messages.append(_nudge_no_tool_call())
            continue

        messages.append(_assistant_with_tool_calls(res, res.tool_calls))

        committed: ClassificationResult | None = None
        for tc in res.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments)

            if name == "lookup_acm":
                out = lookup_acm(args["query"], k=args.get("k", 10), ccs_path=ccs_path)
                messages.append(_tool_result(tc, out))

            elif name == "submit_classification":
                try:
                    committed = submit_classification(
                        args, ccs_entries=ccs_entries, max_classes=max_classes
                    )
                    messages.append(_tool_result(tc, {"status": "accepted"}))
                except ClassificationValidationError as e:
                    messages.append(_tool_result(tc, {
                        "status": "rejected",
                        "error": str(e),
                    }))

            else:
                messages.append(_tool_result(tc, {
                    "status": "rejected",
                    "error": f"unknown tool: {name}",
                }))

        if committed is not None:
            return committed

    raise RuntimeError("Classification did not call submit_classification within budget")
```

Key design notes:
- **Single round-trip per turn:** each `lookup_acm` is invoked once, immediately after the assistant message is appended. Eliminates the duplicate-invocation bug at the old `agent.py:30-32` vs `39-41`.
- **Validation retry via tool result:** when `submit_classification` rejects, we append the rejection as the tool's `tool_result` — the model sees the error in the conversation and gets the next turn to retry. No separate "retry budget" beyond the loop budget; spec §5 caps at "one retry per submit attempt" naturally because each rejection consumes one loop turn and the loop budget is 8.
- **Returning after the inner loop:** we set `committed` and return after processing all tool calls in the turn, so a turn with multiple tool calls (e.g. one `lookup_acm` plus one `submit_classification`) is handled correctly.

- [ ] **Step 4: Run classification tests to confirm green**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/agents/classification -q`

Expected: all tests PASS.

- [ ] **Step 5: Run the full repo suite**

Run: `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest -q`

Expected: full green. (Orchestrator's `classify_fn=classify_manuscript` interface is unchanged; `ClassificationResult.classes` shape is preserved.)

- [ ] **Step 6: Commit**

```bash
git add paperfb/agents/classification/agent.py tests/agents/classification/test_agent.py
git commit -m "Rewrite classification agent loop around submit_classification tool"
```

---

## Verification (after all tasks)

Per spec §8:

1. `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/agents/classification -q` — all unit tests pass.
2. `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest -q` — full suite green.
3. `host-spawn -cwd "$PWD" -- mise exec -- uv run pytest tests/test_acceptance_live.py -q` (manual, slow, requires the LiteLLM proxy and `.env`) — runs end-to-end against `anthropic/claude-3.5-haiku` without `JSONDecodeError` or budget-exhaustion failures.

The live acceptance test is **not** modified by this plan; it is the ground truth that the prior failures are gone.

---

## Unresolved questions

- None. Spec §9 explicitly closes design at protocol shape, data shape (flat), keyword-block placement (field on `submit_classification`), and weight rubric.
