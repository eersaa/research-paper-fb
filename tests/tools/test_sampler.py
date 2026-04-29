import json
from pathlib import Path

import pytest

from paperfb.schemas import CCSClass, ReviewerTuple
from paperfb.tools.sampler import sample_board


@pytest.fixture
def names_file(tmp_path) -> Path:
    p = tmp_path / "names.json"
    p.write_text(json.dumps(["Aino", "Eero", "Liisa", "Mikko", "Saara"]))
    return p


@pytest.fixture
def classes() -> list[CCSClass]:
    return [
        CCSClass(path="A → B", weight="High", rationale="r"),
        CCSClass(path="C → D", weight="Medium", rationale="r"),
    ]


def test_returns_pydantic_reviewer_tuples(classes, names_file):
    out = sample_board(
        n=3,
        classes=classes,
        stances=["critical", "constructive", "skeptical"],
        focuses=["methods", "results", "novelty", "clarity"],
        core_focuses=["methods", "results", "novelty"],
        enable_secondary=True,
        names_path=names_file,
        seed=42,
    )
    assert len(out) == 3
    assert all(isinstance(t, ReviewerTuple) for t in out)
    assert len({(t.stance, t.primary_focus) for t in out}) == 3
    assert len({t.name for t in out}) == 3


def test_specialty_is_class_path_not_dict(classes, names_file):
    out = sample_board(
        n=2, classes=classes,
        stances=["critical", "constructive"],
        focuses=["methods", "results"], core_focuses=["methods"],
        enable_secondary=False, names_path=names_file, seed=1,
    )
    assert all(isinstance(t.specialty, str) and "→" in t.specialty for t in out)


def test_core_focus_coverage_when_n_ge_core_count(classes, names_file):
    out = sample_board(
        n=3, classes=classes,
        stances=["critical", "constructive", "skeptical"],
        focuses=["methods", "results", "novelty", "clarity"],
        core_focuses=["methods", "results", "novelty"],
        enable_secondary=True, names_path=names_file, seed=7,
    )
    assert {t.primary_focus for t in out} >= {"methods", "results", "novelty"}


def test_raises_when_names_pool_smaller_than_n(classes, tmp_path):
    short = tmp_path / "short.json"
    short.write_text(json.dumps(["Aino"]))
    with pytest.raises(ValueError, match="names"):
        sample_board(
            n=3, classes=classes,
            stances=["a", "b", "c"], focuses=["m", "r", "n"], core_focuses=["m"],
            enable_secondary=False, names_path=short, seed=1,
        )


def test_deterministic_with_same_seed(classes, names_file):
    args = dict(n=3, classes=classes,
                stances=["a", "b", "c"], focuses=["m", "r", "n", "c"],
                core_focuses=["m", "r", "n"], enable_secondary=True,
                names_path=names_file, seed=99)
    a = sample_board(**args)
    b = sample_board(**args)
    assert [t.model_dump() for t in a] == [t.model_dump() for t in b]
