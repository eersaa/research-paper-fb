import os
import time
from dataclasses import dataclass
from typing import Any, Optional
from openai import OpenAI, APIStatusError, APIConnectionError, APITimeoutError


class RetryableError(RuntimeError):
    pass


@dataclass
class LLMResult:
    content: Optional[str]
    tool_calls: Optional[list]
    finish_reason: str
    raw: Any


class LLMClient:
    def __init__(self, base_url: str, default_model: str, max_retries: int = 3,
                 backoff_base: float = 0.5):
        self._sdk = OpenAI(base_url=base_url, api_key="unused")
        self._default_model = default_model
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._total_tokens = 0
        self._total_cost = 0.0

    def usage_summary(self) -> dict:
        return {"total_tokens": self._total_tokens, "total_cost_usd": self._total_cost}

    def chat(self, messages: list[dict], tools: Optional[list] = None,
             model: Optional[str] = None, **kwargs) -> LLMResult:
        model = model or self._default_model
        last_err = None
        for attempt in range(self._max_retries):
            try:
                resp = self._sdk.chat.completions.create(
                    model=model,
                    messages=messages,
                    tools=tools,
                    **kwargs,
                )
                choice = resp.choices[0]
                usage = getattr(resp, "usage", None)
                if usage is not None:
                    self._total_tokens += getattr(usage, "total_tokens", 0) or 0
                    dumped = resp.model_dump() if hasattr(resp, "model_dump") else {}
                    cost = (dumped.get("usage") or {}).get("cost") or 0.0
                    self._total_cost += float(cost)
                return LLMResult(
                    content=choice.message.content,
                    tool_calls=choice.message.tool_calls,
                    finish_reason=choice.finish_reason,
                    raw=resp,
                )
            except (APIStatusError, APIConnectionError, APITimeoutError) as e:
                last_err = e
                status = getattr(getattr(e, "response", None), "status_code", None)
                if status is not None and status < 500 and status != 429:
                    raise
                if attempt < self._max_retries - 1:
                    time.sleep(self._backoff_base * (2 ** attempt))
        raise RetryableError(f"exhausted retries: {last_err}")


def from_env(default_model: str) -> LLMClient:
    base_url = os.environ["BASE_URL"]
    return LLMClient(base_url=base_url, default_model=default_model)
