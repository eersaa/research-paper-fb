import argparse
import asyncio
import sys
from dataclasses import replace
from pathlib import Path
from dotenv import load_dotenv

from paperfb.config import load_config
from paperfb.llm_client import from_env
from paperfb.orchestrator import run_pipeline


def _parse(argv):
    p = argparse.ArgumentParser(description="Give a manuscript constructive feedback from a board of reviewers.")
    p.add_argument("manuscript", help="Path to manuscript markdown file.")
    p.add_argument("--config", default="config/default.yaml")
    p.add_argument("--axes", default="config/axes.yaml")
    p.add_argument("--output", default=None, help="Override paths.output.")
    p.add_argument("--reviews-dir", default=None, help="Override paths.reviews_dir.")
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
    if args.output or args.reviews_dir:
        cfg = replace(cfg, paths=replace(
            cfg.paths,
            output=args.output or cfg.paths.output,
            reviews_dir=args.reviews_dir or cfg.paths.reviews_dir,
        ))
    if args.count:
        cfg = replace(cfg, reviewers=replace(cfg.reviewers, count=args.count))

    llm = from_env(default_model=cfg.models.default)
    result = asyncio.run(run_pipeline(manuscript=manuscript, cfg=cfg, llm=llm))

    print(f"Report: {result.report_path}")
    print(f"Reviews: {len(result.reviews)} produced, {len(result.skipped)} skipped")
    if result.skipped:
        for s in result.skipped:
            print(f"  - skipped {s['id']}: {s['reason']}")
    usage = llm.usage_summary()
    print(f"Usage: {usage['total_tokens']} tokens, ~${usage['total_cost_usd']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
