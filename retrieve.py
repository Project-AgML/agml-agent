"""
agml.retrieve() — live, demand-driven grounding lookup.

    from retrieve import retrieve
    result = retrieve("Coffee leaf rust", crop="coffee", scientific_name="Hemileia vastatrix")

No corpus is built or stored anywhere. Every call hits each active source's
fetcher module (src/sources/<name>.py) live, over the network, right now.
Results are kept in a per-process in-memory cache only — nothing is written
to disk, nothing is published anywhere — so repeated lookups for the same
class within one run/process don't re-hit the network, but nothing persists
across runs.

`sources`:
  - unset (None)        -> every active external source in config/sources.yaml
                            (i.e. everything except paused/parked ones).
                            AgML's own image datasets are a SEPARATE lane —
                            see the "agml:" prefix note below — not yet wired in.
  - a list of source names -> only those (must be `status: active`)
  - an "agml:..." prefixed name -> NOT YET IMPLEMENTED (raises NotImplementedError).
    This is deliberately a distinct namespace from external source names so the
    interface shape already matches where AgML image-dataset linking will slot
    in later, without changing this function's signature.

CLI, for manually testing one class against every active source:
    python retrieve.py "Coffee leaf rust" --crop coffee --sci "Hemileia vastatrix" --aliases roya
    python retrieve.py "Coffea arabica" --crop coffee --task species
    python retrieve.py "Coffee leaf rust" --sources gbif eppo
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
from pathlib import Path

import yaml
from dotenv import load_dotenv

from src.sources.base import ClassQuery

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger(__name__)

# ddgs's internal HTTP client (primp) logs every search-backend request it
# tries while resolving one site-restricted query (Wikipedia, Brave, Yahoo,
# etc.) at INFO — noisy, and easy to mistake for "we're pulling content from
# these sites," which we never do (only site-restricted result URLs on the
# domains a fetcher actually lists get fetched for content). Quieted here;
# raise back to INFO/DEBUG if you need to debug the search step itself.
for _noisy in ("primp", "httpx", "httpcore", "urllib3", "h2"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)

ROOT = Path(__file__).parent

# process-lifetime cache: {(source_name, class_name_lower): [chunk_dict, ...]}
# Never persisted, never shared across processes — see module docstring.
_CACHE: dict[tuple[str, str], list[dict]] = {}


def _load_sources() -> dict[str, dict]:
    cfg = yaml.safe_load((ROOT / "config" / "sources.yaml").read_text())
    return {s["name"]: s for s in cfg["sources"]}


def _active_source_names() -> list[str]:
    return [name for name, cfg in _load_sources().items() if cfg.get("status") == "active"]


def retrieve(
    class_name: str,
    crop: str = "",
    task: str = "",
    scientific_name: str | None = None,
    aliases: list[str] | None = None,
    sources: list[str] | None = None,
) -> dict[str, list[dict]]:
    """Returns {source_name: [chunk_dict, ...]} — only sources that returned
    at least one chunk are present as keys. A source erroring (bad key,
    network failure, page layout changed) is logged and simply omitted, so
    one broken source never breaks the whole call."""
    registry = _load_sources()

    if sources is None:
        requested = _active_source_names()
    else:
        agml_sources = [s for s in sources if s.startswith("agml:")]
        if agml_sources:
            raise NotImplementedError(
                f"AgML image-dataset sources ({agml_sources}) aren't wired into retrieve() "
                "yet — external sources only for now. See README 'How this will link to AgML'."
            )
        requested = sources

    query = ClassQuery(
        class_name=class_name, crop=crop, task=task,
        scientific_name=scientific_name, aliases=aliases or [],
    )

    results: dict[str, list[dict]] = {}
    for name in requested:
        cfg = registry.get(name)
        if cfg is None:
            log.warning("unknown source %r — skipping (not in config/sources.yaml)", name)
            continue
        if cfg.get("status") != "active":
            log.warning("source %r is %s, not active — skipping", name, cfg.get("status"))
            continue
        if query.task and cfg["task"] and query.task not in cfg["task"]:
            continue  # this source doesn't cover this task, not an error

        cache_key = (name, class_name.strip().lower())
        if cache_key in _CACHE:
            if _CACHE[cache_key]:
                results[name] = _CACHE[cache_key]
            continue

        try:
            module = importlib.import_module(cfg["module"])
            chunks = module.fetch(query)
        except Exception as e:
            log.error("%s: %s", name, e)
            continue

        chunk_dicts = [c.to_dict() for c in chunks]
        _CACHE[cache_key] = chunk_dicts
        if chunk_dicts:
            results[name] = chunk_dicts

    return results


def main(args: argparse.Namespace) -> None:
    result = retrieve(
        class_name=args.class_name,
        crop=args.crop or "",
        task=args.task or "",
        scientific_name=args.sci,
        aliases=args.aliases,
        sources=args.sources,
    )

    if not result:
        print(f"No results for {args.class_name!r} from any active source.")
        return

    for source, chunks in result.items():
        print(f"\n=== {source} — {len(chunks)} chunk(s) ===")
        for c in chunks:
            print(f"  tags: {', '.join(c['tags'])}")
            print(f"  url:  {c['source_url']}")
            print(f"  {c['excerpt_text'][:300]}{'...' if len(c['excerpt_text']) > 300 else ''}")

    if args.json:
        print("\n" + json.dumps(result, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test agml.retrieve() against one class, live, over every active source "
                     "(see config/sources.yaml) — or a subset via --sources.",
        epilog='Example: retrieve.py "Coffee leaf rust" --crop coffee --sci "Hemileia vastatrix" '
               '--aliases roya --task disease',
    )
    parser.add_argument(
        "class_name",
        help='the class/concept to look up, exactly as you want it searched for, e.g. '
             '"Coffee leaf rust" or "Coffea arabica". This is the only required argument — '
             'everything else narrows or helps the search.',
    )
    parser.add_argument(
        "--crop", default=None,
        help='the crop/host this class belongs to, e.g. "coffee". Used both as extra search '
             'context (e.g. USDA AMS Grade Standards uses it to find the right commodity page) '
             'and carried through into each result chunk\'s `crop` field.',
    )
    parser.add_argument(
        "--task", default=None, choices=["disease", "pest", "species", "quality"],
        help="restricts which sources are even tried, since each source in config/sources.yaml "
             "only covers certain tasks (e.g. GBIF/USDA PLANTS/USDA NALT are species-only, USDA "
             "AMS is quality-only). Omit to try every active source regardless of task.",
    )
    parser.add_argument(
        "--sci", default=None,
        help='scientific name, e.g. "Hemileia vastatrix". Tried as a search term if the plain '
             "class_name doesn't get a match — most useful for species-ID sources like GBIF/"
             "USDA PLANTS, which key off scientific names more reliably than common names.",
    )
    parser.add_argument(
        "--aliases", nargs="*", default=None,
        help='extra alternate names to also try, space-separated, e.g. --aliases roya "coffee rust". '
             "Tried in order after class_name and --sci, so put the most likely match first.",
    )
    parser.add_argument(
        "--sources", nargs="*", default=None,
        help="restrict the call to specific source names instead of every active source, "
             "space-separated, e.g. --sources gbif eppo. Names must match config/sources.yaml "
             "and be status: active, or they're skipped with a warning.",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="also print the full result as indented JSON after the human-readable summary "
             "(every field per chunk — tags, raw_response, license, etc., not just the excerpt).",
    )
    main(parser.parse_args())
