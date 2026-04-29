"""CLI entry point. Calls paperfb.pipeline.run."""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from dotenv import load_dotenv

from paperfb.config import load_config
from paperfb.pipeline import run as pipeline_run


def _parse(argv):
    p = argparse.ArgumentParser(
        description="Give a manuscript constructive feedback from a board of reviewers."
    )
    p.add_argument("manuscript", help="Path to manuscript markdown file.")
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--axes", default="config/axes.yaml")
    p.add_argument("--output", default=None, help="Override paths.output.")
    p.add_argument("-n", "--count", type=int, default=None, help="Override reviewers.count.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    load_dotenv()
    args = _parse(argv if argv is not None else sys.argv[1:])

    manuscript_path = Path(args.manuscript)
    if not manuscript_path.is_file():
        print(f"Manuscript not found: {manuscript_path}", file=sys.stderr)
        return 2
    manuscript = manuscript_path.read_text()

    cfg = load_config(Path(args.config), Path(args.axes))
    if args.output:
        cfg = replace(cfg, paths=replace(cfg.paths, output=args.output))
    if args.count is not None:
        cfg = replace(cfg, reviewers=replace(cfg.reviewers, count=args.count))

    run_obj = pipeline_run(manuscript=manuscript, cfg=cfg)

    print(f"Report: {cfg.paths.output}")
    print(f"Reviews: {len(run_obj.board.reviews)} produced, {len(run_obj.board.skipped)} skipped")
    for s in run_obj.board.skipped:
        print(f"  - skipped {s.id}: {s.reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
