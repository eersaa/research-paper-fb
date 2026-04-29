"""ACM CCS lookup tool. Returns Pydantic CCSMatch objects (spec §4.1).

Algorithm preserved from paperfb/agents/classification/tools.py:lookup_acm.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from paperfb.schemas import CCSMatch


PATH_SEPARATOR = " → "


@lru_cache(maxsize=8)
def _load_ccs(ccs_path: Path) -> tuple[dict, ...]:
    with Path(ccs_path).open() as f:
        return tuple(json.load(f))


def _token_patterns(query: str) -> list[re.Pattern]:
    return [re.compile(rf"\b{re.escape(t)}\b", re.IGNORECASE) for t in query.split()]


def lookup_acm(query: str, k: int = 10, ccs_path: Path | None = None) -> list[CCSMatch]:
    if ccs_path is None:
        ccs_path = Path("data/acm_ccs.json")
    patterns = _token_patterns(query)
    if not patterns:
        return []
    out: list[CCSMatch] = []
    for e in _load_ccs(ccs_path):
        hay = e["path"] + " " + e.get("description", "")
        if all(p.search(hay) for p in patterns):
            out.append(CCSMatch(path=e["path"], description=e.get("description", "")))
        if len(out) >= k:
            break
    return out
