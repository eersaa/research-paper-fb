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
