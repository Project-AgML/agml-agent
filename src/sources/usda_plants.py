"""USDA PLANTS Database — public domain, no key. Verified live:
    GET https://plantsservices.sc.egov.usda.gov/api/PlantSearch?searchText=<term>
    GET https://plantsservices.sc.egov.usda.gov/api/PlantProfile?symbol=<symbol>
"""

from __future__ import annotations

import re
from datetime import date

from src.common.http import get
from src.common.schema import RetrievedChunk
from src.common.tagging import normalize_tags
from src.sources.base import ClassQuery

BASE = "https://plantsservices.sc.egov.usda.gov/api"
LICENSE = "Public domain (US government)"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_tags(s: str | None) -> str:
    return _TAG_RE.sub("", s or "").strip()


def _is_relevant(term: str, plant: dict) -> bool:
    """PlantSearch also matches against its internal 4-letter Symbol code, not
    just real text fields — a short/generic term like an alias ("roya") can
    coincidentally equal some unrelated plant's symbol (e.g. ROYA = Rosa
    yainacensis) with zero real relationship to the term's actual meaning.
    Require the term to appear as a whole word in the scientific or common
    name — plain substring containment isn't enough either, since "roya" is
    also a substring of the unrelated genus "Fitzroya"."""
    term_lower = term.strip().lower()
    if not term_lower:
        return False
    sci = _strip_tags(plant.get("ScientificName")).lower()
    common = (plant.get("CommonName") or "").lower()
    pattern = r"\b" + re.escape(term_lower) + r"\b"
    return bool(re.search(pattern, sci) or re.search(pattern, common))


def fetch(query: ClassQuery) -> list[RetrievedChunk]:
    match = None
    for term in query.search_terms():
        resp = get(f"{BASE}/PlantSearch", params={"searchText": term})
        if resp is None or resp.status_code != 200:
            continue
        hits = resp.json()
        relevant = [h["Plant"] for h in hits if _is_relevant(term, h["Plant"])]
        if relevant:
            match = relevant[0]
            break
    if not match:
        return []

    symbol = match["Symbol"]
    profile_resp = get(f"{BASE}/PlantProfile", params={"symbol": symbol})
    profile = profile_resp.json() if profile_resp and profile_resp.status_code == 200 else match

    sci_name = _strip_tags(profile.get("ScientificName"))
    common = profile.get("CommonName") or ""
    natives = profile.get("NativeStatuses") or []
    durations = profile.get("Durations") or []
    habits = profile.get("GrowthHabits") or []

    excerpt_parts = [f"Scientific name: {sci_name}"]
    if common:
        excerpt_parts.append(f"Common name: {common}")
    if durations:
        excerpt_parts.append(f"Duration: {', '.join(durations)}")
    if habits:
        excerpt_parts.append(f"Growth habit: {', '.join(habits)}")
    if natives:
        regions = ", ".join(f"{n['Region']} ({n['Type']})" for n in natives[:10])
        excerpt_parts.append(f"US distribution/status: {regions}")

    tags = normalize_tags(
        ["taxonomy"] + (["distribution"] if natives else []) + (["synonym"] if profile.get("HasSynonyms") else [])
    )

    return [RetrievedChunk(
        class_name=query.class_name,
        tags=tags,
        excerpt_text="\n".join(excerpt_parts),
        raw_response=RetrievedChunk.raw_json(profile),
        source_url=f"https://plants.usda.gov/plant-profile/{symbol}",
        license=LICENSE,
        accessed_date=str(date.today()),
        crop=query.crop,
        query_task=query.task,
        extra={"symbol": symbol},
    )]
