"""Top-level pipeline runner (spec §6.1, §6.2).

AG2 0.12.1 errata (verified via spike scripts, 2026-04-29):

1. AfterWork is gone — use agent.handoffs.set_after_work(target) where target
   is a TransitionTarget (e.g. FunctionTarget). Note: set_after_work takes
   positional arg, NOT keyword `target=`.

2. RedundantPattern is gone — reviewer fan-out is inline inside
   setup_review_board (Task 10).

3. Chair (LLM aggregator) was dropped — BoardReport built deterministically.

4. FunctionTargetResult has fields: messages, context_variables, target (required).
   `target` must be a TransitionTarget. Use TerminateTarget() to end the outer
   chat after setup_review_board completes.
   Deviates from plan draft: plan had message=, target=None — actual API
   requires target field (non-optional) and uses `messages` (not `message`).

5. Chat entrypoint: initiate_group_chat(pattern, messages, max_rounds) from
   autogen.agentchat.group.multi_agent_chat. Returns (ChatResult, ContextVariables, Agent).
   Deviates from plan draft which suggested user_proxy.initiate_chat(pattern=...).
   user_proxy.initiate_chat takes a ConversableAgent as recipient, not a pattern.

6. FunctionTarget callable signature: (last_message: str, context_variables: ContextVariables)
   -> FunctionTargetResult. Context is passed as ContextVariables (dict-like), not plain dict.

Layout:
  run(manuscript, cfg) -> RunOutput
    builds llm_configs, calls _run_chat(...), parses results into RunOutput,
    writes evaluations/run-<ts>/run.json.

  _run_chat(...) — the AG2 wiring. Builds UserProxy + agents, registers tools,
    wires post-turn handoffs, runs the chat.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from autogen import ConversableAgent, UserProxyAgent
from autogen.agentchat.group import (
    AgentTarget,
    ContextVariables,
    FunctionTarget,
    FunctionTargetResult,
    TerminateTarget,
)
from autogen.agentchat.group.multi_agent_chat import initiate_group_chat
from autogen.agentchat.group.patterns import DefaultPattern

from paperfb.agents.classification import build_classification_agent
from paperfb.agents.profile_creation import build_profile_creation_agent
from paperfb.agents.reviewer import build_reviewer_agent
from paperfb.config import Config
from paperfb.handoffs import (
    HandoffResult,
    build_setup_review_board,
    classify_to_profile,
)
from paperfb.logging_hook import JsonlLogger
from paperfb.renderer import render_report
from paperfb.schemas import BoardReport, ClassificationResult, ProfileBoard, RunOutput


def _utc_run_id() -> str:
    return "run-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _build_llm_config(cfg: Config, model: str) -> dict:
    return {
        "config_list": [{
            "model": model,
            "base_url": os.environ["BASE_URL"],
            "api_key": "unused",
            "api_type": "openai",
        }],
        "temperature": 0.0,
        "cache_seed": cfg.ag2.cache_seed,
    }


def _wrap_handoff(fn: Any, *, next_target: Any) -> Any:
    """Adapt a HandoffResult-returning function into AG2 FunctionTargetResult.

    next_target: the TransitionTarget that AG2 should advance to after fn runs
    (e.g. AgentTarget(profile_agent) for classify_to_profile, TerminateTarget()
    for setup_review_board). Required because FunctionTargetResult.target is
    non-optional in AG2 0.12.1, and DefaultPattern does NOT auto-advance after
    a FunctionTarget returns — the handoff itself must name the next speaker.

    Spike finding: FunctionTargetResult uses `messages` (str | list | None),
    not `message`. Context mutation by fn (e.g. ctx["classification"] = ...)
    happens inside fn itself; we don't echo it back via context_variables= to
    avoid double-application.
    """
    def wrapper(agent_output: str, context_variables: Any) -> FunctionTargetResult:
        result: HandoffResult = fn(agent_output, context_variables)
        return FunctionTargetResult(
            messages=result.message,
            target=next_target,
        )
    wrapper.__name__ = fn.__name__
    return wrapper


def _make_llm_output_hook(logger: JsonlLogger, agent_name: str):
    """Return a safeguard_llm_outputs hook that logs each LLM response.

    AG2 0.12.1: safeguard_llm_outputs hooks receive (response: str | dict)
    and must return the (optionally modified) response. We observe-and-pass-through.
    Content >1024 bytes is stored as {sha256, bytes} per spec §6.7.
    """
    def hook(response: Any) -> Any:
        content = response if isinstance(response, str) else json.dumps(response, ensure_ascii=False)
        logger.log_event({
            "agent": agent_name,
            "role": "assistant",
            "content": content,
        })
        return response
    return hook


def _run_chat(*, manuscript: str, cfg: Config, ts: str) -> Any:
    """Build and run the AG2 GroupChat. Returns context_variables dict-like.

    Per AG2 0.12.1 errata:
    - No Chair LLM agent; reviewers fan out inline inside setup_review_board.
    - Handoffs registered via agent.handoffs.set_after_work(FunctionTarget(fn)).
    - The outer chat terminates after setup_review_board returns TerminateTarget().
    - initiate_group_chat returns (ChatResult, ContextVariables, Agent); we
      return a lightweight object exposing .context_variables for pipeline.run().

    Logging (spec §6.5, §6.7):
    - JsonlLogger writes logs/run-<ts>.jsonl; closed in finally.
    - chat_start event references manuscript by byte-count only (non-leakage).
    - Per-message events via safeguard_llm_outputs hooks on classification and
      profile agents; content >1024 bytes auto-redacted by log_event.
    """
    log_path = Path(cfg.paths.logs_dir) / f"{ts}.jsonl"
    logger = JsonlLogger(log_path)
    logger.log_event({
        "agent": "pipeline",
        "role": "system",
        "content": "chat_start",
        "manuscript_bytes": len(manuscript.encode("utf-8")),
    })

    try:
        classification_cfg = _build_llm_config(cfg, cfg.models.classification)
        profile_cfg = _build_llm_config(cfg, cfg.models.profile_creation)
        reviewer_cfg = _build_llm_config(cfg, cfg.models.reviewer)

        user_proxy = UserProxyAgent(
            name="user",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        classification_agent, lookup_acm_fn = build_classification_agent(
            llm_config=classification_cfg,
            ccs_path=Path(cfg.paths.acm_ccs),
            max_classes=cfg.classification.max_classes,
        )
        profile_agent, sample_board_fn = build_profile_creation_agent(
            llm_config=profile_cfg,
            axes=cfg.axes,
            names_path=Path(cfg.paths.finnish_names),
            count=cfg.reviewers.count,
            core_focuses=cfg.reviewers.core_focuses,
            enable_secondary=cfg.reviewers.secondary_focus_per_reviewer,
            seed=cfg.reviewers.seed,
        )

        # Per-message logging via safeguard_llm_outputs (Path B).
        # Hook observes and returns the response unchanged; redaction applied inside log_event.
        classification_agent.register_hook(
            "safeguard_llm_outputs",
            _make_llm_output_hook(logger, classification_agent.name),
        )
        profile_agent.register_hook(
            "safeguard_llm_outputs",
            _make_llm_output_hook(logger, profile_agent.name),
        )

        # Tool wiring
        user_proxy.register_for_execution(name="lookup_acm")(lookup_acm_fn)
        classification_agent.register_for_llm(
            name="lookup_acm",
            description=(
                "Search the ACM CCS for concept paths matching keywords. "
                "Multi-token AND, word-boundary, case-insensitive."
            ),
        )(lookup_acm_fn)

        user_proxy.register_for_execution(name="sample_board")(sample_board_fn)
        profile_agent.register_for_llm(
            name="sample_board",
            description=(
                "Sample N reviewer tuples deterministically. n: int, "
                "classes: list[CCSClass], optional seed: int."
            ),
        )(sample_board_fn)

        setup_review_board = build_setup_review_board(
            reviewer_llm_config=reviewer_cfg,
            build_reviewer=build_reviewer_agent,
        )

        # Post-turn handoffs.
        # Spike confirmed: set_after_work takes a positional TransitionTarget, not keyword.
        # FunctionTarget validates that fn accepts (output, ctx) — wrapper satisfies this.
        # Each handoff must name its own next-speaker target — DefaultPattern does NOT
        # auto-advance after a FunctionTarget completes (live test, 2026-04-29).
        classification_agent.handoffs.set_after_work(
            FunctionTarget(_wrap_handoff(
                classify_to_profile,
                next_target=AgentTarget(profile_agent),
            ))
        )
        profile_agent.handoffs.set_after_work(
            FunctionTarget(_wrap_handoff(
                setup_review_board,
                next_target=TerminateTarget(),
            ))
        )

        context_variables = ContextVariables(data={
            "manuscript": manuscript,
            "run_id": ts,
        })

        pattern = DefaultPattern(
            agents=[classification_agent, profile_agent],
            initial_agent=classification_agent,
            user_agent=user_proxy,
            context_variables=context_variables,
        )

        # Spike confirmed: initiate_group_chat(pattern, messages, max_rounds)
        # returns (ChatResult, ContextVariables, last_agent).
        # user_proxy.initiate_chat is NOT for patterns — it takes a ConversableAgent.
        _chat_result, final_ctx, _last_agent = initiate_group_chat(
            pattern=pattern,
            messages=manuscript,
            max_rounds=cfg.ag2.max_rounds,
        )

        logger.log_event({"agent": "pipeline", "role": "system", "content": "chat_end"})

        # Return a lightweight object exposing .context_variables so pipeline.run()
        # can access it uniformly (the monkeypatch in tests sets .context_variables
        # directly on a MagicMock, so this shape matches).
        class _Result:
            def __init__(self, ctx: ContextVariables) -> None:
                self.context_variables = ctx

        return _Result(final_ctx)
    finally:
        logger.close()


def run(*, manuscript: str, cfg: Config) -> RunOutput:
    """Run the full pipeline. Writes evaluations/run-<ts>/run.json."""
    ts = _utc_run_id()
    chat_result = _run_chat(manuscript=manuscript, cfg=cfg, ts=ts)

    ctx = chat_result.context_variables
    classification = ClassificationResult.model_validate(dict(ctx["classification"]))
    profiles = ProfileBoard.model_validate(dict(ctx["profiles"]))
    board = BoardReport.model_validate(dict(ctx["board"]))

    run_obj = RunOutput(classification=classification, profiles=profiles, board=board)

    report_path = Path(cfg.paths.output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(run_obj))

    eval_dir = Path("evaluations") / ts
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / "run.json").write_text(
        json.dumps(run_obj.model_dump(), indent=2, ensure_ascii=False)
    )

    return run_obj
