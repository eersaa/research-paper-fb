import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional


PATH_SEPARATOR = " → "


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "lookup_acm",
        "description": (
            "Search the ACM CCS for concept paths matching one or more keywords. "
            "Query is split on whitespace; every token must match (case-insensitive, "
            "word-boundary) the entry's path or description. Returns up to k entries."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "One or more whitespace-separated keywords.",
                },
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


def _parent_path(path: str) -> str:
    segments = path.split(PATH_SEPARATOR)
    return PATH_SEPARATOR.join(segments[:-1]) if len(segments) > 1 else ""


def _leaf(path: str) -> str:
    return path.split(PATH_SEPARATOR)[-1]


def _token_patterns(query: str) -> list[re.Pattern]:
    tokens = query.split()
    return [re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in tokens]


def lookup_acm(query: str, k: int = 10, ccs_path: Optional[Path] = None) -> list[dict]:
    if ccs_path is None:
        ccs_path = Path("data/acm_ccs.json")
    entries = load_ccs(ccs_path)
    patterns = _token_patterns(query)
    if not patterns:
        return []
    matches: list[dict] = []
    for e in entries:
        hay = e["path"] + " " + e.get("description", "")
        if all(p.search(hay) for p in patterns):
            matches.append({
                "path": e["path"],
                "leaf": _leaf(e["path"]),
                "description": e.get("description", ""),
                "parent_path": _parent_path(e["path"]),
            })
        if len(matches) >= k:
            break
    return matches
