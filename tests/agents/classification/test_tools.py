import json
from pathlib import Path
import pytest
from paperfb.agents.classification.tools import lookup_acm, load_ccs


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


def test_lookup_schema_has_required_fields():
    schema = next(
        s for s in TOOL_SCHEMAS if s["function"]["name"] == "lookup_acm"
    )
    assert schema["type"] == "function"
    assert "query" in schema["function"]["parameters"]["properties"]


def test_load_ccs_from_file(ccs_path):
    entries = load_ccs(ccs_path)
    assert len(entries) == 5
    assert entries[0]["path"] == "A → B"


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


def test_submit_rejects_non_dict_class_item(ccs_entries):
    args = _valid_args()
    args["classes"] = ["just a string"]
    with pytest.raises(ClassificationValidationError, match="object"):
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
