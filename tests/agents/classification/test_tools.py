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
    # Token order does not matter — AND is set-like.
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
    assert r["leaf"] == "D"
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
