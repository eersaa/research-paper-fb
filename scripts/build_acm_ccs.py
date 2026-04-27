"""Build data/acm_ccs.json from the ACM CCS 2012 SKOS/XML dump.

Run once as a preparation step, not part of the agentic pipeline:
    uv run python scripts/build_acm_ccs.py \\
        --source data/ccs_source.xml \\
        --output data/acm_ccs.json \\
        --cache  data/_ccs_descriptions_cache.json

Outputs a flat list of {path, leaf, description} entries. Descriptions are
generated via the LLM on first run and cached; reruns hit the cache.
"""
from __future__ import annotations
import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable
from dotenv import load_dotenv

from paperfb.llm_client import from_env

NS = {
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}

PATH_SEP = " → "

DESC_SYSTEM = """You write concise 1–2 sentence descriptions of ACM Computing Classification System (CCS) concepts.
Be factual, domain-grounded, and avoid marketing language. Reply with the description only, no preamble."""


def parse_ccs_tree(source_xml: Path) -> list[dict]:
    """Parse SKOS/RDF XML into a flat list of {path, leaf} entries.

    Adapt the element and attribute lookups if the actual file uses a
    different namespace or shape.
    """
    tree = ET.parse(source_xml)
    root = tree.getroot()

    label: dict[str, str] = {}
    parent: dict[str, str] = {}
    for concept in root.findall("skos:Concept", NS):
        cid = concept.get(f"{{{NS['rdf']}}}about")
        if cid is None:
            continue
        pref = concept.find("skos:prefLabel", NS)
        if pref is not None and pref.text:
            label[cid] = pref.text.strip()
        broader = concept.find("skos:broader", NS)
        if broader is not None:
            parent[cid] = broader.get(f"{{{NS['rdf']}}}resource")

    def path_of(cid: str) -> str:
        parts: list[str] = []
        seen: set[str] = set()
        cur: str | None = cid
        while cur is not None and cur in label and cur not in seen:
            seen.add(cur)
            parts.append(label[cur])
            cur = parent.get(cur)
        return PATH_SEP.join(reversed(parts))

    has_child: set[str] = set(parent.values())
    entries = [
        {"path": path_of(cid), "leaf": cid not in has_child}
        for cid in label
    ]
    entries.sort(key=lambda e: e["path"])
    return entries


def _load_cache(cache_path: Path) -> dict[str, str]:
    if cache_path.exists():
        return json.loads(cache_path.read_text())
    return {}


def _save_cache(cache_path: Path, cache: dict[str, str]) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2, ensure_ascii=False))


def generate_descriptions(entries: Iterable[dict], llm, model: str,
                          cache_path: Path) -> list[dict]:
    cache = _load_cache(cache_path)
    out: list[dict] = []
    dirty = False
    for entry in entries:
        path = entry["path"]
        if path in cache:
            out.append({**entry, "description": cache[path]})
            continue
        res = llm.chat(
            messages=[
                {"role": "system", "content": DESC_SYSTEM},
                {"role": "user", "content": f"CCS concept path:\n{path}"},
            ],
            model=model,
        )
        desc = (res.content or "").strip()
        cache[path] = desc
        dirty = True
        out.append({**entry, "description": desc})
        if len(cache) % 25 == 0:
            _save_cache(cache_path, cache)
    if dirty:
        _save_cache(cache_path, cache)
    return out


def build(source_xml: Path, out_path: Path, cache_path: Path,
          llm, model: str) -> None:
    entries = parse_ccs_tree(source_xml)
    enriched = generate_descriptions(entries, llm=llm, model=model,
                                      cache_path=cache_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(enriched, indent=2, ensure_ascii=False))


def main(argv=None) -> int:
    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--source", default="data/ccs_source.xml")
    p.add_argument("--output", default="data/acm_ccs.json")
    p.add_argument("--cache", default="data/_ccs_descriptions_cache.json")
    p.add_argument("--model", default="anthropic/claude-3.5-haiku")
    args = p.parse_args(argv)

    source = Path(args.source)
    if not source.is_file():
        print(f"Source XML not found: {source}", file=sys.stderr)
        print("Download ACM CCS 2012 SKOS XML and save it to that path.", file=sys.stderr)
        return 2

    llm = from_env(default_model=args.model)
    build(source_xml=source, out_path=Path(args.output),
          cache_path=Path(args.cache), llm=llm, model=args.model)
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
