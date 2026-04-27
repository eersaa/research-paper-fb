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
