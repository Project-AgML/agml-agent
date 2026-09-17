"""
search_agml() — the second tool, alongside retrieve(). Everything about
AgML's own dataset catalog: keyword search across the merged package+website
catalog, or an exact-name lookup — bundling metadata and benchmark data into
one result per dataset, the same way gbif.py bundles taxonomy + images into
one call instead of splitting them into separate tools.

    from agml_agent.search_agml import search_agml
    search_agml("citrus disease classification")
    search_agml(exact_name="my_eval_set")   # explicit opt-in to a held-out set

No embeddings — keyword/word-boundary relevance matching against each
dataset's name/classes/crop_types/tasks, same gate pattern already used in
agml_agent/sources/usda_plants.py and agml_agent/sources/gbif.py. See the
design doc for why: the catalog's long tail (iNatAg splits) is never
browsed raw, and the genuinely diverse core+curated catalog is small enough
for this to work without a precomputed embedding index.

CLI, for manually testing (from a source checkout:
`uv run python -m agml_agent.search_agml ...`; installed: `agml-agent-search ...`):
    agml-agent-search "citrus disease classification"
    agml-agent-search "coffee" --ml-task image_classification
    agml-agent-search --exact-name bean_disease_uganda
"""

from __future__ import annotations

import argparse
import json
import logging
import re

from agml_agent.agml_catalog import get_benchmarks, merged_catalog

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

DEFAULT_LIMIT = 10


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    """Splits on any non-alphanumeric run — critically including `_`, which
    regex \\b does NOT treat as a word boundary (underscore is a \\w char),
    so dataset names like "citrus_fruit_leaf_disease_classification" never
    matched a \\bcitrus\\b-style check even though "citrus" is clearly one
    of its real words. This is why an earlier version of this function
    matched nothing for "citrus disease" despite real matches existing."""
    return set(_TOKEN_RE.findall(text.lower()))


def _matches(query: str, entry: dict) -> bool:
    """Every word in the query must exactly match a token somewhere in the
    entry's name/classes/crop_types/tasks — a multi-word query like "citrus
    disease" is an AND over {"citrus", "disease"}, not one literal phrase."""
    query_tokens = _tokenize(query)
    if not query_tokens:
        return True
    crop_types = entry.get("crop_types")
    haystacks = [
        str(entry.get("name") or ""),
        " ".join(str(c) for c in (entry.get("classes") or []) if c is not None),
        " ".join(str(c) for c in crop_types if c is not None) if isinstance(crop_types, list) else str(crop_types or ""),
        str(entry.get("ag_task") or ""),
        str(entry.get("ml_task") or ""),
    ]
    entry_tokens = _tokenize(" ".join(haystacks))
    return query_tokens.issubset(entry_tokens)


def _summarize(entry: dict, include_benchmarks: bool = False) -> dict:
    """A trimmed view for search results — enough to judge relevance
    without dumping every field (raw_response-equivalent) into a list of
    candidates. Full detail comes from an exact_name lookup instead."""
    summary = {
        "name": entry.get("name"),
        "ml_task": entry.get("ml_task"),
        "ag_task": entry.get("ag_task"),
        "crop_types": entry.get("crop_types"),
        "num_images": entry.get("num_images"),
        "num_classes": len(entry.get("classes") or []),
        "classes_preview": (entry.get("classes") or [])[:8],
        "license": entry.get("license"),
        "hf_link": entry.get("hf_link"),
        "source": entry.get("source"),
    }
    if include_benchmarks:
        summary["benchmarks"] = get_benchmarks(entry["name"])
    return summary


def search_agml(
    query: str = "",
    exact_name: str | None = None,
    ml_task: str | None = None,
    ag_task: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> dict:
    """Returns {"results": [...]} for a keyword search, or
    {"results": [<full detail incl. benchmarks>]} (one entry) for an exact
    lookup. exact_name is the only way to reach a dataset regardless of
    whether it matches `query` — the eval-set opt-in path."""
    catalog = merged_catalog()

    if exact_name:
        entry = catalog.get(exact_name)
        if entry is None:
            log.warning("no dataset named %r in the merged catalog", exact_name)
            return {"results": []}
        full = dict(entry)
        full["benchmarks"] = get_benchmarks(exact_name)
        return {"results": [full]}

    candidates = list(catalog.values())
    if ml_task:
        candidates = [c for c in candidates if c.get("ml_task") == ml_task]
    if ag_task:
        candidates = [c for c in candidates if c.get("ag_task") == ag_task]
    if query:
        candidates = [c for c in candidates if _matches(query, c)]

    results = [_summarize(c) for c in candidates[:limit]]
    return {"results": results, "total_matched": len(candidates)}


def _run(args: argparse.Namespace) -> None:
    result = search_agml(
        query=args.query or "",
        exact_name=args.exact_name,
        ml_task=args.ml_task,
        ag_task=args.ag_task,
        limit=args.limit,
    )

    if not result["results"]:
        print("No matching datasets.")
        return

    if args.exact_name:
        d = result["results"][0]
        print(f"=== {d['name']} ===")
        for k, v in d.items():
            if k == "benchmarks":
                continue
            print(f"  {k}: {v}")
        bm = d.get("benchmarks")
        print(f"  benchmarks: {len(bm) if bm else 0} result(s)")
        if bm:
            for b in bm[:3]:
                print(f"    - {b.get('model')}: f1={b.get('metrics', {}).get('f1')}")
    else:
        print(f"{result['total_matched']} matched, showing {len(result['results'])}:\n")
        for d in result["results"]:
            print(f"  {d['name']} — {d['ml_task']}/{d['ag_task']} — {d['num_classes']} classes, {d['num_images']} images")
            if d["classes_preview"]:
                print(f"    classes: {', '.join(str(c) for c in d['classes_preview'])}")

    if args.json:
        print("\n" + json.dumps(result, indent=2, default=str))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Search AgML's dataset catalog (package + live website data merged), or look up one dataset by exact name.",
        epilog='Example: agml-agent-search "citrus disease" --ml-task image_classification',
    )
    parser.add_argument("query", nargs="?", default=None, help="keyword(s) to match against dataset name/classes/crop/task")
    parser.add_argument("--exact-name", default=None, help="look up one dataset by its exact name (bypasses query matching) — the eval-set opt-in path")
    parser.add_argument("--ml-task", default=None, help='e.g. image_classification, object_detection, semantic_segmentation')
    parser.add_argument("--ag-task", default=None, help='e.g. disease_classification, weed_detection, quality_classification')
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--json", action="store_true")
    _run(parser.parse_args())


if __name__ == "__main__":
    main()
