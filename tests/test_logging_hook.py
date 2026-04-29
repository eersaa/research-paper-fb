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
    assert "ts" in e1 and "ts" in e2
