"""Classification agent (spec §4.1)."""
# NOTE: no `from __future__ import annotations` — see paperfb/agents/profile_creation.py
# for the full rationale. AG2 introspects tool annotations at register_for_llm time.
from pathlib import Path
from typing import Any

from autogen import ConversableAgent

from paperfb.schemas import CCSMatch, ClassificationResult
from paperfb.tools.acm_lookup import lookup_acm as _lookup_acm


SYSTEM_PROMPT = """You classify a computer-science research manuscript against the ACM Computing Classification System (CCS).

Procedure:
1. Read the manuscript. Extract the keywords actually used in it (extracted_from_paper).
   If the paper's vocabulary is non-standard or sparse, also synthesise canonical
   keywords that describe the same work (synthesised). At least one of the two lists
   must be non-empty.
2. Drive lookup_acm queries from those keywords. Multi-token queries are AND across
   tokens with word-boundary matching, so prefer multiple short queries over one long
   one. Match is case-insensitive.
3. Pick 1-{max_classes} CCS classes. Prefer leaf nodes; use higher-level nodes only
   when no leaf fits.
4. Emit a ClassificationResult with keywords and classes. Every path must come from
   a lookup_acm result — do not invent paths.

Weight rubric:
- High:   central topic — title-or-abstract-first material; the primary contribution.
- Medium: significant supporting topic — methods, frameworks, or domains the work substantially uses.
- Low:    relevant but not central — mentioned, compared against, or touched on.
"""


def build_classification_agent(
    llm_config: dict,
    ccs_path: Path,
    max_classes: int,
) -> tuple[ConversableAgent, Any]:
    """Returns (agent, lookup_acm_callable).

    Caller (pipeline.py) wires the returned callable to the UserProxy via
    @user_proxy.register_for_execution() / @agent.register_for_llm(...). We
    bind ccs_path here as a closure so the LLM never supplies it.
    """
    agent = ConversableAgent(
        name="classification",
        system_message=SYSTEM_PROMPT.format(max_classes=max_classes),
        llm_config={**llm_config, "response_format": ClassificationResult},
    )

    def lookup_acm_bound(query: str, k: int = 10) -> list[CCSMatch]:
        """ACM CCS lookup. Multi-token AND, word-boundary, case-insensitive."""
        return _lookup_acm(query=query, k=k, ccs_path=ccs_path)

    return agent, lookup_acm_bound
