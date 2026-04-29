"""ProfileCreation agent (spec §4.2)."""
# NOTE: no `from __future__ import annotations` here. AG2's register_for_llm
# introspects tool callables via Pydantic TypeAdapter, which can't resolve
# stringified ForwardRefs from a closure's namespace. Python 3.11 supports
# native list[X] / X | None at runtime, so this works without the future import.
from pathlib import Path
from typing import Any

from autogen import ConversableAgent

from paperfb.config import AxesConfig
from paperfb.schemas import CCSClass, ProfileBoard, ReviewerTuple
from paperfb.tools.sampler import sample_board as _sample_board


_AXIS_BLOCK = """Stance vocabulary (use these names verbatim; descriptions ground tone):
{stances}

Focus vocabulary (use these names verbatim; descriptions ground depth):
{focuses}
"""


SYSTEM_PROMPT_TEMPLATE = """You compose reviewer personas for a research-paper feedback board.

Procedure:
1. Call sample_board exactly once with n={count} and the ACM classes you receive.
   The tool returns N reviewer tuples (id, name, specialty, stance, primary_focus,
   secondary_focus). The tool already enforces deterministic diversity, Finnish
   names, and class round-robin — do not second-guess its output.
2. For each tuple, write a full reviewer system_message that:
   - Addresses the reviewer by their assigned Finnish first name verbatim. Do NOT
     add titles, surnames, affiliations, or honourifics.
   - Establishes the reviewer as a domain specialist grounded in the specialty
     (the ACM CCS path).
   - Reflects the assigned stance in tone (drawing on the stance description).
   - Emphasises the primary_focus (drawing on its description); acknowledges the
     secondary_focus as a supplementary lens.
   - Instructs the reviewer to produce three free-text aspects (strong_aspects,
     weak_aspects, recommended_changes), each grounded in the primary_focus, with
     the secondary_focus colouring depth where natural.
   - Forbids the reviewer from rewriting the paper. Forbids numeric ratings.
3. Also write a one-line profile_summary for the renderer header.
4. Emit a ProfileBoard with one ReviewerProfile per tuple.

{axis_block}
"""


def _format_axis_block(axes: AxesConfig) -> str:
    stances = "\n".join(f"  - {s.name}: {s.description}" for s in axes.stances)
    focuses = "\n".join(f"  - {f.name}: {f.description}" for f in axes.focuses)
    return _AXIS_BLOCK.format(stances=stances, focuses=focuses)


def build_profile_creation_agent(
    llm_config: dict,
    axes: AxesConfig,
    names_path: Path,
    count: int,
    core_focuses: list[str],
    enable_secondary: bool,
    seed: int | None,
) -> tuple[ConversableAgent, Any]:
    """Returns (agent, sample_board_callable). Tool registration with the
    UserProxy happens in pipeline.py."""
    stances = [s.name for s in axes.stances]
    focuses = [f.name for f in axes.focuses]

    system_message = SYSTEM_PROMPT_TEMPLATE.format(
        count=count,
        axis_block=_format_axis_block(axes),
    )

    agent = ConversableAgent(
        name="profile_creation",
        system_message=system_message,
        llm_config={**llm_config, "response_format": ProfileBoard},
    )

    def sample_board_bound(
        n: int,
        classes: list[CCSClass],
        seed_override: int | None = None,
    ) -> list[ReviewerTuple]:
        """Deterministically sample N reviewer tuples. The bound parameters
        (stances, focuses, core_focuses, enable_secondary, names_path) come
        from config and are not LLM-controlled."""
        return _sample_board(
            n=n,
            classes=classes,
            stances=stances,
            focuses=focuses,
            core_focuses=core_focuses,
            enable_secondary=enable_secondary,
            names_path=names_path,
            seed=seed_override if seed_override is not None else seed,
        )

    return agent, sample_board_bound
