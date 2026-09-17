"""
Merges two AgML dataset catalogs, keyed by name — confirmed necessary by
checking a specific dataset (ACHENY_variety_classification) against both:
it isn't in any of the real `agml` package's three bundled JSON files at all
(confirmed by reading agml/utils/data.py::load_public_sources(), which only
ever loads those three files, no runtime fetch). The richer metadata
(imaging equipment, collection period, precise location, file size) only
exists in the AgML *website*'s hf_datasets.json — live-fetched here, not
vendored, same "no persistence" approach as everything else in this repo.

This mirrors the merge the website's own build does internally
(generate-embeddings.mjs::mergeForEmbedding) — not a new pattern.
"""

from __future__ import annotations

import logging
from functools import lru_cache

import agml

from agml_agent.common.http import get

log = logging.getLogger(__name__)

WEBSITE_CATALOG_URL = "https://project-agml.github.io/data/hf_datasets.json"
WEBSITE_PERFORMANCE_URL = "https://project-agml.github.io/data/performance/{name}.json"


def _metadata_to_dict(meta) -> dict:
    """Flattens a real agml.data.DatasetMetadata into a plain dict — only
    the fields that exist on every entry; extra_metadata is merged in too
    since some package entries carry extra fields there."""
    d = {
        "name": meta.name,
        "ml_task": meta.tasks.ml if meta.tasks else None,
        "ag_task": meta.tasks.ag if meta.tasks else None,
        "num_images": meta.num_images,
        "classes": _normalize_classes(list(meta.classes) if meta.classes else []),
        "license": meta.license,
        "citation": meta.citation,
        "annotation_format": meta.annotation_format,
        "sensor_modality": meta.sensor_modality,
        "location": {
            "continent": getattr(meta.location, "continent", None),
            "country": getattr(meta.location, "country", None),
        } if meta.location else None,
        "parent_dataset": meta.parent_dataset,
        "source": "agml_package",
    }
    try:
        extra = dict(meta.extra_metadata or {})
        for k, v in extra.items():
            d.setdefault(k, v)
    except Exception:
        pass
    return d


@lru_cache(maxsize=1)
def _package_catalog() -> dict[str, dict]:
    """Every dataset the installed agml package knows about — ~6,000
    entries (69 "core" + iNatAg-mini + iNatAg species splits), thinner
    metadata than the website's, but covers datasets the website doesn't."""
    catalog = {}
    for meta in agml.data.public_data_sources():
        try:
            d = _metadata_to_dict(meta)
            catalog[d["name"]] = d
        except Exception as e:
            log.debug("skipping package entry %s: %s", getattr(meta, "name", "?"), e)
    return catalog


@lru_cache(maxsize=1)
def _website_catalog() -> dict[str, dict]:
    """The website's curated ~300-entry catalog, live-fetched — richer
    metadata (imaging equipment, collection period, precise location,
    file size), and more current than what's bundled in the released
    package. Empty dict (not an exception) if the fetch fails — a network
    hiccup here shouldn't break search_agml(), just narrow its coverage."""
    resp = get(WEBSITE_CATALOG_URL)
    if resp is None or resp.status_code != 200:
        log.warning("could not fetch website catalog — falling back to package catalog only")
        return {}
    catalog = {}
    for entry in resp.json():
        name = entry.get("name")
        if not name:
            continue
        d = dict(entry)
        d["ml_task"] = entry.get("machine_learning_task")
        d["ag_task"] = entry.get("agricultural_task")
        d["classes"] = _normalize_classes(entry.get("classes"))
        d["source"] = "agml_website"
        catalog[name] = d
    return catalog


def _normalize_classes(classes) -> list:
    """The website's own hf_datasets.json is inconsistent in this field's
    type in two different ways, both confirmed live:
      1. Sometimes the whole field is one comma-joined string instead of a
         list (e.g. plant_village_classification) — iterating that as-is
         silently produces one "class" per CHARACTER ("A", "p", "p", ...).
      2. Sometimes it's a real list, but with exactly one element that is
         itself a comma-joined string (e.g.
         arabica_coffee_leaf_disease_classification's website entry —
         ["Cerscospora, Healthy, Leaf_rust, Miner, Phoma"] — while the same
         dataset's PACKAGE entry has it correctly as 5 separate elements).
    Normalized once here so nothing downstream has to defend against it."""
    if classes is None:
        return []
    if isinstance(classes, str):
        classes = [classes]
    if not isinstance(classes, list):
        return []
    if len(classes) == 1 and isinstance(classes[0], str) and "," in classes[0]:
        return [c.strip() for c in classes[0].split(",") if c.strip()]
    return classes


@lru_cache(maxsize=1)
def merged_catalog() -> dict[str, dict]:
    """Package entries first, then website entries merged on top — for a
    name present in both, the website's richer fields win, but package-only
    fields (e.g. from iNatAg splits the website doesn't carry) are kept."""
    merged = dict(_package_catalog())
    for name, website_entry in _website_catalog().items():
        if name in merged:
            merged[name] = {**merged[name], **website_entry}
        else:
            merged[name] = website_entry
    return merged


def get_benchmarks(name: str) -> list[dict] | None:
    """Live-fetches this dataset's real benchmark results from the AgML
    website (zero-shot VLM results — model, f1/precision/recall, the exact
    prompt used). None if the dataset has no benchmark file (most don't —
    only ~198 of ~6,000 are covered), not an error."""
    resp = get(WEBSITE_PERFORMANCE_URL.format(name=name), sleep=0.1)
    if resp is None or resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        return None
