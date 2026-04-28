import json
from unittest.mock import MagicMock
import pytest
from paperfb.agents.classification import classify_manuscript, ClassificationResult


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


def test_lookup_missing_query_arg_is_rejected_not_raised(ccs_file):
    """Regression: agent must NOT KeyError on a malformed lookup_acm call."""
    client = MagicMock()
    client.chat.side_effect = [
        _msg_tool_calls(_tc("lookup_acm", {}, call_id="c1")),
        _msg_tool_calls(_tc("submit_classification", _good_submit_args(), call_id="c2")),
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
