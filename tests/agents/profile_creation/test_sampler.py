import json
from pathlib import Path
import pytest
from paperfb.agents.profile_creation.sampler import sample_reviewer_tuples
from paperfb.contracts import ReviewerTuple

STANCES = ["neutral", "critical", "skeptical", "supportive", "rigorous"]
FOCUSES = ["methods", "results", "impact", "novelty", "clarity", "reproducibility"]
CORE = ["methods", "results", "novelty"]

ACM_CLASSES = [
    {"path": "A", "weight": "High"},
    {"path": "B", "weight": "Medium"},
]


def test_returns_n_tuples():
    tuples = sample_reviewer_tuples(n=3, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    assert len(tuples) == 3
    assert all(isinstance(t, ReviewerTuple) for t in tuples)


def test_core_focuses_all_covered_when_n_ge_core():
    tuples = sample_reviewer_tuples(n=3, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    primaries = {t.primary_focus for t in tuples}
    assert set(CORE).issubset(primaries)


def test_specialty_round_robin_across_acm_classes():
    tuples = sample_reviewer_tuples(n=4, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    assert tuples[0].specialty["path"] == "A"
    assert tuples[1].specialty["path"] == "B"
    assert tuples[2].specialty["path"] == "A"
    assert tuples[3].specialty["path"] == "B"


def test_diversity_stance_primary_unique():
    tuples = sample_reviewer_tuples(n=3, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    pairs = {(t.stance, t.primary_focus) for t in tuples}
    assert len(pairs) == 3


def test_secondary_focus_different_from_primary():
    tuples = sample_reviewer_tuples(n=3, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    for t in tuples:
        assert t.secondary_focus is not None
        assert t.secondary_focus != t.primary_focus


def test_seed_reproducibility():
    a = sample_reviewer_tuples(3, ACM_CLASSES, STANCES, FOCUSES, CORE, seed=7)
    b = sample_reviewer_tuples(3, ACM_CLASSES, STANCES, FOCUSES, CORE, seed=7)
    assert [(t.stance, t.primary_focus, t.secondary_focus) for t in a] \
        == [(t.stance, t.primary_focus, t.secondary_focus) for t in b]


def test_different_seeds_differ():
    a = sample_reviewer_tuples(3, ACM_CLASSES, STANCES, FOCUSES, CORE, seed=1)
    b = sample_reviewer_tuples(3, ACM_CLASSES, STANCES, FOCUSES, CORE, seed=2)
    assert a != b


def test_single_acm_class_all_share_specialty():
    one = [{"path": "Z", "weight": "High"}]
    tuples = sample_reviewer_tuples(3, one, STANCES, FOCUSES, CORE, seed=1)
    assert {t.specialty["path"] for t in tuples} == {"Z"}


def test_n_less_than_core_raises():
    with pytest.raises(ValueError):
        sample_reviewer_tuples(2, ACM_CLASSES, STANCES, FOCUSES, CORE, seed=1)


def test_secondary_focus_maximises_coverage():
    tuples = sample_reviewer_tuples(n=3, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    all_focuses_used = {t.primary_focus for t in tuples} | {t.secondary_focus for t in tuples}
    assert len(all_focuses_used) >= 5


def test_names_assigned_when_names_path_provided(tmp_path):
    """When names_path is given, each ReviewerTuple gets a unique non-empty Finnish name."""
    names_file = tmp_path / "names.json"
    names_file.write_text(json.dumps(["Aino", "Liisa", "Mikko", "Pekka", "Eero"]))
    tuples = sample_reviewer_tuples(n=3, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42,
                                     names_path=names_file)
    assert all(t.name != "" for t in tuples)
    assert len({t.name for t in tuples}) == 3  # unique per board


def test_names_not_assigned_when_no_names_path():
    """Without names_path, name field stays empty string."""
    tuples = sample_reviewer_tuples(n=3, acm_classes=ACM_CLASSES, stances=STANCES,
                                     focuses=FOCUSES, core_focuses=CORE, seed=42)
    assert all(t.name == "" for t in tuples)
