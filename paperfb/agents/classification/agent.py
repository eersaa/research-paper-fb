import json
from pathlib import Path
from paperfb.contracts import ClassificationResult
from paperfb.agents.classification.tools import lookup_acm, TOOL_SCHEMAS

SYSTEM_PROMPT = """You classify a computer-science research manuscript against the ACM Computing Classification System (CCS).
Rules:
- Use the lookup_acm tool one or more times with candidate keywords before deciding.
- Prefer leaf nodes; use higher-level nodes only when no leaf fits.
- Pick 1–{max_classes} classes total.
- Assign each a weight: High, Medium, or Low.
- Return STRICT JSON of the form:
  {{"classes": [{{"path": "<full CCS path>", "weight": "High|Medium|Low", "rationale": "<short>"}}]}}
- Do not include any text outside the JSON object.
"""


def classify_manuscript(manuscript: str, llm, model: str, ccs_path: Path,
                        max_classes: int) -> ClassificationResult:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(max_classes=max_classes)},
        {"role": "user", "content": f"Manuscript:\n\n{manuscript}"},
    ]
    tools = TOOL_SCHEMAS

    for _ in range(6):  # bound tool loop
        res = llm.chat(messages=messages, tools=tools, model=model)
        if res.tool_calls:
            assistant_msg = {"role": "assistant", "content": res.content, "tool_calls": []}
            for tc in res.tool_calls:
                args = json.loads(tc.function.arguments)
                out = lookup_acm(args["query"], k=args.get("k", 10), ccs_path=ccs_path)
                assistant_msg["tool_calls"].append({
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                })
            messages.append(assistant_msg)
            for tc in res.tool_calls:
                args = json.loads(tc.function.arguments)
                out = lookup_acm(args["query"], k=args.get("k", 10), ccs_path=ccs_path)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(out),
                })
            continue
        data = json.loads(res.content)
        classes = data.get("classes", [])
        if not classes:
            raise ValueError("Classification produced no classes")
        return ClassificationResult(classes=classes[:max_classes])
    raise RuntimeError("Classification exceeded tool-loop budget")
