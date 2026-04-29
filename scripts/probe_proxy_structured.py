"""Exploratory: does the course proxy support Pydantic structured outputs?

Tests two paths against each course-recommended model:
  1. client.beta.chat.completions.parse(response_format=PydanticModel)
     — the OpenAI SDK helper AG2 uses internally for OpenAI-typed clients.
  2. raw response_format={"type": "json_schema", "json_schema": {...}}
     — fallback if parse() fails.

If neither works for a model, AG2 will need its function-calling-based
JSON-schema adapter for that one model.
"""

from __future__ import annotations

import os
from typing import Literal

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel, ConfigDict

load_dotenv()


class CCSClass(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    weight: Literal["High", "Medium", "Low"]
    rationale: str


class TestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    classes: list[CCSClass]


PROMPT = (
    "Suggest 2 ACM CCS classes for a paper about distributed consensus "
    "in fault-tolerant systems. Use exactly 'High', 'Medium', or 'Low' for weight."
)

MODELS = [
    "anthropic/claude-3.5-haiku",
    "openai/gpt-4.1-mini",
    "google/gemini-2.5-flash-lite",
]


def try_parse(client: OpenAI, model: str) -> tuple[bool, str]:
    try:
        resp = client.beta.chat.completions.parse(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            response_format=TestResult,
        )
        parsed = resp.choices[0].message.parsed
        return True, f"parse() OK: classes={len(parsed.classes)} weights={[c.weight for c in parsed.classes]}"
    except Exception as e:
        return False, f"parse() FAILED: {type(e).__name__}: {e!s}"


def try_json_schema(client: OpenAI, model: str) -> tuple[bool, str]:
    try:
        schema = TestResult.model_json_schema()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "TestResult", "strict": True, "schema": schema},
            },
        )
        content = resp.choices[0].message.content or ""
        parsed = TestResult.model_validate_json(content)
        return True, f"json_schema OK: classes={len(parsed.classes)} weights={[c.weight for c in parsed.classes]}"
    except Exception as e:
        return False, f"json_schema FAILED: {type(e).__name__}: {e!s}"


def try_json_object(client: OpenAI, model: str) -> tuple[bool, str]:
    """Last-resort: response_format={'type': 'json_object'} (no schema enforcement,
    rely on Pydantic to validate the returned JSON afterward)."""
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Respond only with JSON matching this schema: "
                        f"{TestResult.model_json_schema()}"
                    ),
                },
                {"role": "user", "content": PROMPT},
            ],
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content or ""
        parsed = TestResult.model_validate_json(content)
        return True, f"json_object OK: classes={len(parsed.classes)} weights={[c.weight for c in parsed.classes]}"
    except Exception as e:
        return False, f"json_object FAILED: {type(e).__name__}: {e!s}"


def try_tool_calling(client: OpenAI, model: str) -> tuple[bool, str]:
    """Function-calling-as-structured-output: define one tool matching the Pydantic
    schema and force the model to call it. This is AG2's fallback adapter shape."""
    try:
        schema = TestResult.model_json_schema()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "submit_result",
                        "description": "Submit the structured TestResult.",
                        "parameters": schema,
                    },
                }
            ],
            tool_choice={"type": "function", "function": {"name": "submit_result"}},
        )
        choice = resp.choices[0]
        tcs = choice.message.tool_calls or []
        if not tcs:
            return False, f"tool_calling FAILED: no tool_calls in response (finish_reason={choice.finish_reason})"
        args = tcs[0].function.arguments
        parsed = TestResult.model_validate_json(args)
        return True, f"tool_calling OK: classes={len(parsed.classes)} weights={[c.weight for c in parsed.classes]}"
    except Exception as e:
        return False, f"tool_calling FAILED: {type(e).__name__}: {e!s}"


def main() -> None:
    base_url = os.environ["BASE_URL"]
    client = OpenAI(base_url=base_url, api_key="unused")
    print(f"Proxy: {base_url}\n")

    for model in MODELS:
        print(f"=== {model} ===")
        # Run ALL approaches to build a full compatibility matrix.
        for label, fn in [
            ("parse",        try_parse),
            ("json_schema",  try_json_schema),
            ("json_object",  try_json_object),
            ("tool_calling", try_tool_calling),
        ]:
            ok, msg = fn(client, model)
            mark = "PASS" if ok else "FAIL"
            print(f"  [{mark}] {msg}")
        print()


if __name__ == "__main__":
    main()
