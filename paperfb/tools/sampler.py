"""Deterministic reviewer-tuple sampler. Closure-bound from
build_profile_creation_agent so the LLM only ever supplies n, classes, seed
(spec §4.2). Algorithm preserved from the v1 sampler verbatim except:
  - returns list[ReviewerTuple] (Pydantic) with specialty: str (the ACM path)
  - raises ValueError when names pool is smaller than n
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Optional

from paperfb.schemas import CCSClass, ReviewerTuple


def _sort_classes_by_weight(classes: list[CCSClass]) -> list[CCSClass]:
    order = {"High": 0, "Medium": 1, "Low": 2}
    return sorted(classes, key=lambda c: order[c.weight])


def _load_names(names_path: Path) -> list[str]:
    return json.loads(Path(names_path).read_text(encoding="utf-8"))


def sample_board(
    n: int,
    classes: list[CCSClass],
    stances: list[str],
    focuses: list[str],
    core_focuses: list[str],
    enable_secondary: bool,
    names_path: Path,
    seed: Optional[int] = None,
) -> list[ReviewerTuple]:
    if n < len(core_focuses):
        raise ValueError(
            f"n={n} < core_focuses count ({len(core_focuses)}); cannot guarantee coverage"
        )
    if not classes:
        raise ValueError("classes must be non-empty")
    for cf in core_focuses:
        if cf not in focuses:
            raise ValueError(f"core focus {cf!r} not in focuses")

    rng = random.Random(seed)
    sorted_classes = _sort_classes_by_weight(classes)

    primaries = list(core_focuses)
    non_core = [f for f in focuses if f not in core_focuses]
    while len(primaries) < n:
        primaries.append(rng.choice(non_core or focuses))

    stances_pool = list(stances)
    chosen_stances: list[str] = []
    used_pairs: set[tuple[str, str]] = set()
    for pf in primaries:
        rng.shuffle(stances_pool)
        picked = next((s for s in stances_pool if (s, pf) not in used_pairs), None)
        if picked is None:
            picked = rng.choice(stances_pool)
        chosen_stances.append(picked)
        used_pairs.add((picked, pf))

    secondaries: list[str | None]
    if enable_secondary:
        secondaries = []
        used = set(primaries)
        for pf in primaries:
            cands = [f for f in focuses if f != pf and f not in used] or [f for f in focuses if f != pf]
            sec = rng.choice(cands)
            secondaries.append(sec)
            used.add(sec)
    else:
        secondaries = [None] * n

    all_names = _load_names(names_path)
    if len(all_names) < n:
        raise ValueError(f"names pool has {len(all_names)} entries; need >= {n}")
    names = rng.sample(all_names, k=n)

    return [
        ReviewerTuple(
            id=f"r{i+1}",
            name=names[i],
            specialty=sorted_classes[i % len(sorted_classes)].path,
            stance=chosen_stances[i],
            primary_focus=primaries[i],
            secondary_focus=secondaries[i],
        )
        for i in range(n)
    ]
