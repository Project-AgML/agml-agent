"""GBIF — free public API, no key. Verified live:
    GET https://api.gbif.org/v1/species/search?q=<term>
    GET https://api.gbif.org/v1/species/<key>/vernacularNames
    GET https://api.gbif.org/v1/species/<key>/synonyms
    GET https://api.gbif.org/v1/species/match?name=<name>
    GET https://api.gbif.org/v1/occurrence/search?taxonKey=<backbone key>&mediaType=StillImage

Species ID task: taxonomy is the primary payload, vernacular names cover
the `synonym` tag.

Images: GBIF occurrence records (many sourced from iNaturalist) often carry
real, individually-licensed photos — confirmed live and genuinely usable, but
with two real failure modes found by visually inspecting sample images:

1. `/species/search`'s own `key` is often a source-checklist-specific ID, NOT
   the GBIF Backbone Taxonomy key `/occurrence/search`'s `taxonKey` needs —
   `/species/match` resolves the real one first. Beyond that, a *fuzzy*
   match (`matchType` != EXACT — e.g. a species name with no real backbone
   entry falling back to matching its genus) pulls occurrence records for
   the whole genus, which can be nearly unrelated to the actual query
   (confirmed: "Candidatus Liberibacter asiaticus" fuzzy-matched to the
   genus Liberibacter and returned a photo of an unrelated twig). Only an
   EXACT match is trusted for images.
2. A single mislabeled/misidentified citizen-science observation can supply
   several photos at once — confirmed: 5 "images" for Phytophthora infestans
   were all the same wrong flowering-plant observation, because occurrence
   results were consumed in order without capping how many images come from
   one occurrence. Capped per-occurrence below so one bad observation can't
   fill the whole result.

Residual risk neither fix removes: GBIF's harmonized schema doesn't expose
iNaturalist's own "research grade"/verification flag, so even an exact
species match can still return a real but wrong photo from a bad citizen-
science ID. Treat these as candidate, unverified imagery — a downstream
consumer (predict(), a human reviewer) should sanity-check before treating
one as ground truth, not assume every returned image is correct.
"""

from __future__ import annotations

import re
from datetime import date

from agml_agent.common.http import get
from agml_agent.common.schema import RetrievedChunk
from agml_agent.common.tagging import normalize_tags
from agml_agent.sources.base import ClassQuery

BASE = "https://api.gbif.org/v1"
LICENSE = "CC0 / CC-BY (per-record — see raw_response.license)"
MULTIMEDIA_EXT = "http://rs.gbif.org/terms/1.0/Multimedia"
MAX_IMAGES = 5


def _taxonomy_search_terms(query: ClassQuery) -> list[str]:
    """Scientific name first, not class_name first — GBIF is a taxonomy
    database, and `ClassQuery.search_terms()`'s default order (class_name
    first) is actively harmful here: querying `/species/search` with a
    disease-name string like "Tomato late blight" doesn't fail, it fuzzy-
    matches to whatever scores best — confirmed live: it matched "Catalpa
    ovata" (an unrelated flowering tree), and because a match was found on
    the first term tried, the real scientific name was never even attempted.
    Falls back to class_name/aliases only when no scientific_name is given."""
    terms = []
    if query.scientific_name:
        terms.append(query.scientific_name)
    for t in query.search_terms():
        if t not in terms:
            terms.append(t)
    return terms


def _is_relevant(term: str, candidate: dict) -> bool:
    """Defense in depth, same pattern as usda_plants.py's gate: even
    scientific_name-first ordering doesn't help if scientific_name is empty
    and class_name alone fuzzy-matches garbage. Require the term to appear
    as a whole word in the candidate's scientific or canonical name."""
    term_lower = term.strip().lower()
    if not term_lower:
        return False
    sci = (candidate.get("scientificName") or "").lower()
    canonical = (candidate.get("canonicalName") or "").lower()
    pattern = r"\b" + re.escape(term_lower) + r"\b"
    return bool(re.search(pattern, sci) or re.search(pattern, canonical))


def _best_match(term: str) -> dict | None:
    resp = get(f"{BASE}/species/search", params={"q": term, "limit": 5})
    if resp is None or resp.status_code != 200:
        return None
    results = [r for r in resp.json().get("results", []) if _is_relevant(term, r)]
    for r in results:
        if r.get("taxonomicStatus") == "ACCEPTED":
            return r
    return results[0] if results else None


def _backbone_taxon_key(scientific_name: str) -> int | None:
    """Only an EXACT match is trusted — anything fuzzier (e.g. falling back
    to a genus) pulls occurrence records for organisms that may have nothing
    real to do with the queried species. See module docstring."""
    resp = get(f"{BASE}/species/match", params={"name": scientific_name})
    if resp is None or resp.status_code != 200:
        return None
    data = resp.json()
    return data.get("usageKey") if data.get("matchType") == "EXACT" else None


def _fetch_images(taxon_key: int, limit: int = MAX_IMAGES, max_per_occurrence: int = 2) -> list[dict]:
    """max_per_occurrence caps how many photos one single occurrence record
    can contribute — without this, one mislabeled observation with several
    photos can fill the entire result (confirmed: happened for Phytophthora
    infestans). Requests more occurrences than `limit` so capping still
    leaves room to reach `limit` images from genuinely different sightings.

    basisOfRecord=HUMAN_OBSERVATION excludes PRESERVED_SPECIMEN (herbarium/
    museum specimens) — confirmed root cause of a worse failure than either
    fix above: EVERY Phytophthora infestans image with basisOfRecord=
    PRESERVED_SPECIMEN traced back to one herbarium dataset (Institute of
    Botany, Uzbekistan Academy of Sciences) whose media links are broken —
    all 20+ checked pointed at the same unrelated flowering shrub, not the
    fungus or any host plant. Even when correct, a preserved/pressed
    specimen photo isn't useful for visual-symptom grounding anyway.
    HUMAN_OBSERVATION records (iNaturalist, fungal recording databases, etc.)
    are live field photos and were the only source of genuinely correct
    images found during testing."""
    resp = get(f"{BASE}/occurrence/search",
               params={"taxonKey": taxon_key, "mediaType": "StillImage",
                       "basisOfRecord": "HUMAN_OBSERVATION", "limit": limit * 4})
    if resp is None or resp.status_code != 200:
        return []
    images = []
    for occ in resp.json().get("results", []):
        taken_from_this_occurrence = 0
        for m in occ.get("extensions", {}).get(MULTIMEDIA_EXT, []):
            if taken_from_this_occurrence >= max_per_occurrence:
                break
            url = m.get("http://purl.org/dc/terms/identifier")
            if not url:
                continue
            images.append({
                "url": url,
                "license": m.get("http://purl.org/dc/terms/license", "unknown — verify before use"),
                "creator": m.get("http://purl.org/dc/terms/creator"),
                "publisher": m.get("http://purl.org/dc/terms/publisher"),
                "references": m.get("http://purl.org/dc/terms/references"),
            })
            taken_from_this_occurrence += 1
            if len(images) >= limit:
                return images
    return images


def fetch(query: ClassQuery) -> list[RetrievedChunk]:
    for term in _taxonomy_search_terms(query):
        match = _best_match(term)
        if match:
            break
    else:
        return []

    key = match["key"]
    vernacular_resp = get(f"{BASE}/species/{key}/vernacularNames")
    vernacular = vernacular_resp.json().get("results", []) if vernacular_resp and vernacular_resp.status_code == 200 else []

    synonyms_resp = get(f"{BASE}/species/{key}/synonyms")
    synonyms = synonyms_resp.json().get("results", []) if synonyms_resp and synonyms_resp.status_code == 200 else []

    raw = {"taxon": match, "vernacularNames": vernacular, "synonyms": synonyms}

    common_names = sorted({v["vernacularName"] for v in vernacular if v.get("vernacularName")})
    taxon_path = " > ".join(
        str(match.get(rank, "")) for rank in ("kingdom", "phylum", "class", "order", "family", "genus", "species")
        if match.get(rank)
    )
    excerpt_parts = [f"Scientific name: {match.get('scientificName', term)}"]
    if taxon_path:
        excerpt_parts.append(f"Taxonomy: {taxon_path}")
    if common_names:
        excerpt_parts.append(f"Common names: {', '.join(common_names[:10])}")
    if match.get("kingdom"):
        excerpt_parts.append(f"Kingdom: {match['kingdom']}")

    taxon_key = _backbone_taxon_key(match.get("scientificName", term))
    images = _fetch_images(taxon_key) if taxon_key else []
    if images:
        excerpt_parts.append(f"Images available: {len(images)} (see extra.images — each individually licensed)")

    tags = normalize_tags(["taxonomy"] + (["synonym"] if common_names or synonyms else []))

    return [RetrievedChunk(
        class_name=query.class_name,
        tags=tags,
        excerpt_text="\n".join(excerpt_parts),
        raw_response=RetrievedChunk.raw_json(raw),
        source_url=f"https://www.gbif.org/species/{key}",
        license=LICENSE,
        accessed_date=str(date.today()),
        crop=query.crop,
        query_task=query.task,
        extra={"gbif_key": key, "rank": match.get("rank"), "images": images},
    )]
