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
    out = lookup_acm("neural networks", k=10, ccs_path=ccs_path)
    assert len(out) == 1
    assert "Neural networks" in out[0].path


def test_empty_query_returns_empty(ccs_path):
    assert lookup_acm("", k=10, ccs_path=ccs_path) == []


def test_k_caps_results(ccs_path):
    out = lookup_acm("computing methodologies machine learning", k=1, ccs_path=ccs_path)
    assert len(out) == 1
