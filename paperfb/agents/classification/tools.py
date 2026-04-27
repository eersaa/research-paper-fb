import json
from functools import lru_cache
from pathlib import Path
from typing import Optional


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "lookup_acm",
        "description": (
            "Search the ACM Computing Classification System for concept paths "
            "matching a keyword or phrase. Returns up to k matching entries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Keyword or short phrase."},
                "k": {"type": "integer", "description": "Max results.", "default": 10},
            },
            "required": ["query"],
        },
    },
}


@lru_cache(maxsize=8)
def load_ccs(ccs_path: Path) -> tuple[dict, ...]:
    with Path(ccs_path).open() as f:
        data = json.load(f)
    return tuple(data)


def lookup_acm(query: str, k: int = 10, ccs_path: Optional[Path] = None) -> list[dict]:
    if ccs_path is None:
        ccs_path = Path("data/acm_ccs.json")
    entries = load_ccs(ccs_path)
    q = query.lower().strip()
    if not q:
        return []
    matches = []
    for e in entries:
        hay = (e["path"] + " " + e.get("description", "")).lower()
        if q in hay:
            matches.append(dict(e))
        if len(matches) >= k:
            break
    return matches
