import json
from pathlib import Path

from paperfb.contracts import ClassificationResult
from paperfb.agents.classification.tools import (
    lookup_acm,
    submit_classification,
    load_ccs,
    TOOL_SCHEMAS,
    ClassificationValidationError,
)


SYSTEM_PROMPT = """You classify a computer-science research manuscript against the ACM Computing Classification System (CCS).

Procedure:
1. Read the manuscript. Extract the keywords actually used in it (extracted_from_paper).
   If the paper's vocabulary is non-standard or sparse, also synthesise canonical
   keywords that describe the same work (synthesised). At least one of the two lists
   must be non-empty.
2. Drive lookup_acm queries from those keywords. Multi-token queries are AND across
   tokens with word-boundary matching, so prefer multiple short queries over one long
   one. Match is case-insensitive.
3. Pick 1–{max_classes} CCS classes. Prefer leaf nodes; use higher-level nodes only
   when no leaf fits.
4. Commit by calling submit_classification exactly once. Do not emit free-text JSON.

Weight rubric:
- High:   central topic — would appear in the title or first sentence of the abstract;
          the paper's primary contribution lives here.
- Medium: significant supporting topic — methods, frameworks, or domains the work
          substantially uses.
- Low:    relevant but not central — mentioned, compared against, or touched on.

Use the lookup_acm tool one or more times before committing. Every path you submit
must come from lookup_acm results — do not invent paths."""


_LOOP_BUDGET = 8


def _nudge_no_tool_call() -> dict:
    return {
        "role": "user",
        "content": (
            "You must call lookup_acm or submit_classification. "
            "Do not reply in plain text."
        ),
    }


def _assistant_with_tool_calls(res, tool_calls: list) -> dict:
    return {
        "role": "assistant",
        "content": res.content,
        "tool_calls": [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.function.name,
                    "arguments": tc.function.arguments,
                },
            }
            for tc in tool_calls
        ],
    }


def _tool_result(tc, payload) -> dict:
    return {
        "role": "tool",
        "tool_call_id": tc.id,
        "content": json.dumps(payload),
    }


def classify_manuscript(
    manuscript: str, llm, model: str, ccs_path: Path, max_classes: int
) -> ClassificationResult:
    ccs_entries = load_ccs(ccs_path)

    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT.format(max_classes=max_classes)},
        {"role": "user", "content": f"Manuscript:\n\n{manuscript}"},
    ]

    for _ in range(_LOOP_BUDGET):
        res = llm.chat(messages=messages, tools=TOOL_SCHEMAS, model=model)

        if not res.tool_calls:
            messages.append({"role": "assistant", "content": res.content})
            messages.append(_nudge_no_tool_call())
            continue

        messages.append(_assistant_with_tool_calls(res, res.tool_calls))

        committed: ClassificationResult | None = None
        for tc in res.tool_calls:
            name = tc.function.name
            args = json.loads(tc.function.arguments)

            if name == "lookup_acm":
                query = args.get("query")
                if not query:
                    messages.append(_tool_result(tc, {
                        "status": "rejected",
                        "error": "missing required arg: query",
                    }))
                    continue
                out = lookup_acm(query, k=args.get("k", 10), ccs_path=ccs_path)
                messages.append(_tool_result(tc, out))

            elif name == "submit_classification":
                try:
                    committed = submit_classification(
                        args, ccs_entries=ccs_entries, max_classes=max_classes
                    )
                    messages.append(_tool_result(tc, {"status": "accepted"}))
                    break
                except ClassificationValidationError as e:
                    messages.append(_tool_result(tc, {
                        "status": "rejected",
                        "error": str(e),
                    }))

            else:
                messages.append(_tool_result(tc, {
                    "status": "rejected",
                    "error": f"unknown tool: {name}",
                }))

        if committed is not None:
            return committed

    raise RuntimeError("Classification did not call submit_classification within budget")
