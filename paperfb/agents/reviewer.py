"""Reviewer agent factory (spec §4.3). One ConversableAgent per ReviewerProfile."""
from __future__ import annotations

from autogen import ConversableAgent

from paperfb.schemas import Review, ReviewerProfile


_REVIEWER_ID_LINE = (
    "\n\nYour reviewer_id is: {rid}. Use this exact value as Review.reviewer_id."
)


def build_reviewer_agent(profile: ReviewerProfile, llm_config: dict) -> ConversableAgent:
    system = profile.persona_prompt + _REVIEWER_ID_LINE.format(rid=profile.id)
    return ConversableAgent(
        name=f"reviewer_{profile.id}",
        system_message=system,
        llm_config={**llm_config, "response_format": Review},
        max_consecutive_auto_reply=1,
        human_input_mode="NEVER",
    )
