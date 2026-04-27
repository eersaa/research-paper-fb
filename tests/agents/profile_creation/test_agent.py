import json
from unittest.mock import MagicMock
from paperfb.agents.profile_creation import create_profiles, ReviewerProfile
from paperfb.agents.profile_creation.sampler import ReviewerTuple
from paperfb.config import AxesConfig, AxisItem


def _axes() -> AxesConfig:
    return AxesConfig(
        stances=[
            AxisItem("critical",   "Probing; surfaces problems the authors may have downplayed."),
            AxisItem("supportive", "Constructive; emphasises what works."),
        ],
        focuses=[
            AxisItem("methods", "Technical content and rigour: completeness of analysis, soundness of models."),
            AxisItem("results", "Whether reported results actually support the claims."),
            AxisItem("impact",  "Relevance and timeliness within the paper's research area."),
        ],
    )


def _final(content):
    r = MagicMock()
    r.content = content
    r.tool_calls = None
    r.finish_reason = "stop"
    return r


def test_creates_profile_per_tuple():
    tuples = [
        ReviewerTuple(id="r1", specialty={"path": "ML", "weight": "High"},
                      stance="critical", primary_focus="methods", secondary_focus="results",
                      name="Aino"),
        ReviewerTuple(id="r2", specialty={"path": "DB", "weight": "Medium"},
                      stance="supportive", primary_focus="results", secondary_focus="impact",
                      name="Mikko"),
    ]
    llm = MagicMock()
    llm.chat.side_effect = [
        _final("You are a critical ML expert focused on methods..."),
        _final("You are a supportive DB expert focused on results..."),
    ]

    profiles = create_profiles(tuples, axes=_axes(), llm=llm, model="stub")
    assert len(profiles) == 2
    assert all(isinstance(p, ReviewerProfile) for p in profiles)
    assert profiles[0].id == "r1"
    assert profiles[0].name == "Aino"
    assert profiles[0].stance == "critical"
    assert profiles[0].primary_focus == "methods"
    assert profiles[0].specialty == {"path": "ML", "weight": "High"}
    assert profiles[0].persona_prompt.strip() != ""


def test_persona_prompt_user_message_includes_axis_descriptions():
    """Stance/focus descriptions must be in the user message so the LLM grounds the persona."""
    tuples = [ReviewerTuple(id="r1", specialty={"path": "ML"},
                            stance="critical", primary_focus="methods",
                            secondary_focus="results", name="Aino")]
    llm = MagicMock()
    llm.chat.side_effect = [_final("You are ...")]
    create_profiles(tuples, axes=_axes(), llm=llm, model="stub")
    user_content = llm.chat.call_args.kwargs["messages"][1]["content"]
    assert "Probing; surfaces problems" in user_content        # stance description
    assert "completeness of analysis" in user_content          # primary_focus description
    assert "Whether reported results actually support" in user_content  # secondary_focus description


def test_persona_prompt_includes_reviewer_name():
    """The user message must reference the reviewer's Finnish name."""
    tuples = [ReviewerTuple(id="r1", specialty={"path": "ML"},
                            stance="critical", primary_focus="methods",
                            secondary_focus="results", name="Siiri")]
    llm = MagicMock()
    llm.chat.side_effect = [_final("You are Siiri...")]
    create_profiles(tuples, axes=_axes(), llm=llm, model="stub")
    user_content = llm.chat.call_args.kwargs["messages"][1]["content"]
    assert "Siiri" in user_content
