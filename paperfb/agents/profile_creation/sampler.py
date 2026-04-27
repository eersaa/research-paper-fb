import json
import random
from pathlib import Path
from typing import Optional

from paperfb.contracts import ReviewerTuple


def _sort_classes_by_weight(classes: list[dict]) -> list[dict]:
    order = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(classes, key=lambda c: order.get(c.get("weight", "Low"), 2))


def _load_names(names_path: Path) -> list[str]:
    return json.loads(names_path.read_text(encoding="utf-8"))


def sample_reviewer_tuples(
    n: int,
    acm_classes: list[dict],
    stances: list[str],
    focuses: list[str],
    core_focuses: list[str],
    seed: Optional[int] = None,
    enable_secondary: bool = True,
    names_path: Optional[Path] = None,
) -> list[ReviewerTuple]:
    if n < len(core_focuses):
        raise ValueError(
            f"n={n} is less than number of core focuses ({len(core_focuses)}); "
            "cannot guarantee coverage"
        )
    if not acm_classes:
        raise ValueError("acm_classes must be non-empty")
    for cf in core_focuses:
        if cf not in focuses:
            raise ValueError(f"core focus '{cf}' not in focuses list")

    rng = random.Random(seed)
    sorted_classes = _sort_classes_by_weight(acm_classes)

    # Primary focuses: core first, then random from non-core for remaining slots
    primaries: list[str] = list(core_focuses)
    non_core = [f for f in focuses if f not in core_focuses]
    while len(primaries) < n:
        if non_core:
            primaries.append(rng.choice(non_core))
        else:
            primaries.append(rng.choice(focuses))

    # Stances: pick so (stance, primary) is unique; fall back if infeasible
    stances_pool = list(stances)
    chosen_stances: list[str] = []
    used_pairs: set[tuple[str, str]] = set()
    for pf in primaries:
        rng.shuffle(stances_pool)
        picked = None
        for s in stances_pool:
            if (s, pf) not in used_pairs:
                picked = s
                break
        if picked is None:
            picked = rng.choice(stances_pool)
        chosen_stances.append(picked)
        used_pairs.add((picked, pf))

    # Secondary focuses: greedy coverage
    secondaries: list[Optional[str]] = []
    if enable_secondary:
        used_focuses = set(primaries)
        for pf in primaries:
            candidates = [f for f in focuses if f != pf and f not in used_focuses]
            if not candidates:
                candidates = [f for f in focuses if f != pf]
            sec = rng.choice(candidates)
            secondaries.append(sec)
            used_focuses.add(sec)
    else:
        secondaries = [None] * n

    # Finnish name assignment — pad with "" when names pool is smaller than n
    names: list[str] = [""] * n
    if names_path is not None:
        all_names = _load_names(names_path)
        picked_names = rng.sample(all_names, k=min(n, len(all_names)))
        for i, nm in enumerate(picked_names):
            names[i] = nm

    # Specialty round-robin over sorted classes
    tuples: list[ReviewerTuple] = []
    for i in range(n):
        tuples.append(ReviewerTuple(
            id=f"r{i+1}",
            specialty=sorted_classes[i % len(sorted_classes)],
            stance=chosen_stances[i],
            primary_focus=primaries[i],
            secondary_focus=secondaries[i],
            name=names[i],
        ))
    return tuples
