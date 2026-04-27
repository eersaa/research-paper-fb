from unittest.mock import MagicMock, patch
import pytest
from paperfb.llm_client import LLMClient, RetryableError


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
    client = LLMClient(base_url="http://proxy", default_model="m", max_retries=3, backoff_base=0.0)
    err = APIStatusError("boom", response=MagicMock(status_code=502), body=None)
    call = MagicMock(side_effect=[err, err, make_response("ok")])
    with patch.object(client._sdk.chat.completions, "create", call):
        result = client.chat(messages=[{"role": "user", "content": "x"}])
    assert result.content == "ok"
    assert call.call_count == 3


def test_chat_raises_after_exhausting_retries():
    from openai import APIStatusError
    client = LLMClient(base_url="http://proxy", default_model="m", max_retries=2, backoff_base=0.0)
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
    assert summary["total_tokens"] == 30
    assert summary["total_cost_usd"] == pytest.approx(0.0002)
