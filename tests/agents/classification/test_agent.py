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
