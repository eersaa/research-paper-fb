"""Smoke probe for AG2 0.12.1 surfaces used by the refactor.

Re-run after any AG2 version bump: `uv run python scripts/probe_ag2_api.py`.
Prints OK + the exact import paths each surface lives at, or a clear ImportError
naming the missing symbol. Used to ground the refactor plan in real APIs.

AG2 0.12.1 FINDINGS (vs. plan draft):
- AfterWork: NOT in autogen.agentchat.group. It exists only in the legacy
  autogen.agentchat.contrib.swarm_agent module. The new group API uses
  agent.handoffs.set_after_work(target=<TransitionTarget>) instead.
  Plan Tasks 6/11 must be updated to use Handoffs.set_after_work directly.
- RedundantPattern: DOES NOT EXIST in AG2 0.12.1 anywhere. Available patterns:
  DefaultPattern, AutoPattern, RoundRobinPattern, ManualPattern, RandomPattern.
  Plan Tasks 10/11 that construct RedundantPattern(...) need redesign.
  RoundRobinPattern is the closest structural equivalent.
- All other surfaces (FunctionTarget, FunctionTargetResult, NestedChatTarget,
  ContextVariables, DefaultPattern) are confirmed present at the paths below.
"""
from __future__ import annotations


def main() -> int:
    # Core agents
    from autogen import ConversableAgent, UserProxyAgent  # noqa: F401

    # Handoff machinery — all confirmed in autogen.agentchat.group
    from autogen.agentchat.group import (  # type: ignore[attr-defined]
        ContextVariables,
        FunctionTarget,
        FunctionTargetResult,
        Handoffs,
        NestedChatTarget,
        OnCondition,
    )

    # Patterns — confirmed in autogen.agentchat.group.patterns
    from autogen.agentchat.group.patterns import (  # type: ignore[attr-defined]
        AutoPattern,
        DefaultPattern,
        RoundRobinPattern,
    )

    # ABSENT FROM AG2 0.12.1 — documented here so downstream tasks know:
    # AfterWork: was in plan draft from autogen.agentchat.group — does NOT exist there.
    #   Use agent.handoffs.set_after_work(target=FunctionTarget(...)) instead.
    # RedundantPattern: was in plan draft from autogen.agentchat.group.patterns — DOES NOT EXIST.
    #   Use RoundRobinPattern or a nested DefaultPattern as structural substitute.

    surfaces = {
        "ConversableAgent": ConversableAgent,
        "UserProxyAgent": UserProxyAgent,
        "ContextVariables": ContextVariables,
        "FunctionTarget": FunctionTarget,
        "FunctionTargetResult": FunctionTargetResult,
        "Handoffs": Handoffs,
        "NestedChatTarget": NestedChatTarget,
        "OnCondition": OnCondition,
        "DefaultPattern": DefaultPattern,
        "AutoPattern": AutoPattern,
        "RoundRobinPattern": RoundRobinPattern,
    }
    for name, obj in surfaces.items():
        print(f"OK: {name} -> {obj.__module__}.{obj.__qualname__}")

    print()
    print("ABSENT (plan draft referenced these; they do not exist in AG2 0.12.1):")
    print("  AfterWork — use agent.handoffs.set_after_work(target=FunctionTarget(...))")
    print("  RedundantPattern — no equivalent; use RoundRobinPattern or nested DefaultPattern")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
