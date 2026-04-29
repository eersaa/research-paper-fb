import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

from paperfb.config import Config
from paperfb.contracts import SkippedReviewer
from paperfb.agents.classification_legacy import classify_manuscript
from paperfb.agents.profile_creation_legacy import create_profiles, sample_reviewer_tuples
from paperfb.agents.reviewer_legacy import run_reviewer
from paperfb.renderer import render_report


@dataclass
class PipelineResult:
    classes: list[dict]
    reviews: list[dict]
    skipped: list[SkippedReviewer]
    report_path: Path


async def _run_reviewer_async(profile, manuscript, llm, model, reviews_dir, reviewer_fn):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, reviewer_fn, profile, manuscript, llm, model, reviews_dir
    )


async def run_pipeline(
    manuscript: str,
    cfg: Config,
    llm,
    classify_fn=classify_manuscript,
    sample_fn=sample_reviewer_tuples,
    profile_fn=create_profiles,
    reviewer_fn=run_reviewer,
) -> PipelineResult:
    # 1. Classify
    classification = classify_fn(
        manuscript=manuscript,
        llm=llm,
        model=cfg.models.classification,
        ccs_path=Path(cfg.paths.acm_ccs),
        max_classes=cfg.classification.max_classes,
    )
    classes = classification.classes

    # 2. Sample reviewer tuples deterministically
    # Sampler operates on names; descriptions are consumed by Profile Creation only.
    tuples = sample_fn(
        n=cfg.reviewers.count,
        acm_classes=classes,
        stances=[s.name for s in cfg.axes.stances],
        focuses=[f.name for f in cfg.axes.focuses],
        core_focuses=cfg.reviewers.core_focuses,
        seed=cfg.reviewers.seed,
        enable_secondary=cfg.reviewers.secondary_focus_per_reviewer,
        names_path=Path(cfg.paths.finnish_names),
    )

    # 3. Generate personas — passes the full AxesConfig so the persona prompt can
    # splice in stance/focus descriptions verbatim (per 2026-04-27 review-template merge §3).
    profiles = profile_fn(tuples, axes=cfg.axes, llm=llm, model=cfg.models.profile_creation)

    # 4. Fan out reviewers
    reviews_dir = Path(cfg.paths.reviews_dir)
    reviews_dir.mkdir(parents=True, exist_ok=True)
    tasks = [
        _run_reviewer_async(p, manuscript, llm, cfg.models.reviewer, reviews_dir, reviewer_fn)
        for p in profiles
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    reviews: list[dict] = []
    skipped: list[SkippedReviewer] = []
    for p, r in zip(profiles, results):
        if isinstance(r, Exception):
            skipped.append(SkippedReviewer(id=p.id, reason=f"{type(r).__name__}: {r}"))
            continue
        reviews.append(json.loads(Path(r).read_text()))

    # 5. Render
    md = render_report(classes=classes, reviews=reviews, skipped_reviewers=skipped)
    out = Path(cfg.paths.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)

    return PipelineResult(classes=classes, reviews=reviews, skipped=skipped, report_path=out)
