import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from paperfb.contracts import ClassificationResult


log = logging.getLogger(__name__)

PATH_SEPARATOR = " → "
WEIGHTS = ("High", "Medium", "Low")


class ClassificationValidationError(ValueError):
    pass


LOOKUP_ACM_SCHEMA = {
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


SUBMIT_CLASSIFICATION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "submit_classification",
        "description": (
            "Commit your final classification. Call exactly once when you have decided. "
            "First emit the keywords you extracted or synthesised; then emit the chosen "
            "ACM CCS classes with weight (High|Medium|Low) and a short rationale."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "object",
                    "properties": {
                        "extracted_from_paper": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Keywords as they appear in the manuscript.",
                        },
                        "synthesised": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Canonical keywords you supplied to describe the paper's topic.",
                        },
                    },
                    "required": ["extracted_from_paper", "synthesised"],
                },
                "classes": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Full ACM CCS path exactly as returned by lookup_acm.",
                            },
                            "weight": {
                                "type": "string",
                                "enum": list(WEIGHTS),
                                "description": "High = central topic; Medium = significant supporting topic; Low = relevant but not central.",
                            },
                            "rationale": {
                                "type": "string",
                                "description": "One short sentence explaining why this class applies.",
                            },
                        },
                        "required": ["path", "weight", "rationale"],
                    },
                },
            },
            "required": ["keywords", "classes"],
        },
    },
}


TOOL_SCHEMAS = [LOOKUP_ACM_SCHEMA, SUBMIT_CLASSIFICATION_SCHEMA]


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


def submit_classification(
    args: dict, *, ccs_entries: tuple, max_classes: int
) -> ClassificationResult:
    if "keywords" not in args:
        raise ClassificationValidationError("missing required field: keywords")
    if "classes" not in args:
        raise ClassificationValidationError("missing required field: classes")

    kw = args["keywords"]
    extracted = kw.get("extracted_from_paper", []) if isinstance(kw, dict) else []
    synthesised = kw.get("synthesised", []) if isinstance(kw, dict) else []
    if not extracted and not synthesised:
        raise ClassificationValidationError(
            "keywords.extracted_from_paper and keywords.synthesised are both empty"
        )

    classes = args["classes"]
    if not isinstance(classes, list) or len(classes) == 0:
        raise ClassificationValidationError("classes must be a non-empty list")
    if len(classes) > max_classes:
        raise ClassificationValidationError(
            f"classes has {len(classes)} entries; max_classes={max_classes}"
        )

    known_paths = {e["path"] for e in ccs_entries}
    for c in classes:
        if not isinstance(c, dict):
            raise ClassificationValidationError(
                f"each class must be an object; got {type(c).__name__!r}"
            )
        if c.get("weight") not in WEIGHTS:
            raise ClassificationValidationError(
                f"weight must be one of {WEIGHTS}; got {c.get('weight')!r}"
            )
        if c.get("path") not in known_paths:
            raise ClassificationValidationError(
                f"path not in CCS data: {c.get('path')!r}"
            )

    log.info(
        "classification keywords: extracted=%s synthesised=%s",
        extracted, synthesised,
    )
    return ClassificationResult(classes=list(classes))
