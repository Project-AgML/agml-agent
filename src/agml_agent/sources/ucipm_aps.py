"""UC IPM (ipm.ucanr.edu) + APSnet common-names pages (apsnet.org) — public
pages, no login, no documented search API. Reached via site-restricted search
+ text extraction (src/common/scrape.py). Verified live.

`tags` is derived per page from which section the matched excerpt falls
under (Identification / Life Cycle / Damage / Management) by simple keyword
presence — cheap, derived at call time since nothing is cached across calls.
"""

from __future__ import annotations

from datetime import date

from agml_agent.common.schema import RetrievedChunk
from agml_agent.common.scrape import excerpt_around_match, search_and_extract
from agml_agent.common.tagging import normalize_tags
from agml_agent.sources.base import ClassQuery

SITES = ["ipm.ucanr.edu", "apsnet.org"]
LICENSE = "UC IPM / APSnet — public pages, attribute source_url"

_SECTION_KEYWORDS = {
    "identification": ["identification", "diagnos"],
    "life_cycle": ["life cycle", "life history", "overwinter"],
    "symptom": ["symptom"],
    "damage": ["damage", "injury"],
    "management": ["management", "control", "treatment", "cultural practices"],
}


def _section_tags(text: str) -> list[str]:
    lower = text.lower()
    return [tag for tag, kws in _SECTION_KEYWORDS.items() if any(kw in lower for kw in kws)]


def fetch(query: ClassQuery) -> list[RetrievedChunk]:
    terms = query.search_terms()
    q = f"{query.class_name} {query.crop} disease pest identification management"
    hits = search_and_extract(q, SITES, terms, max_results=6, keep=2)

    chunks = []
    for hit in hits:
        tags = normalize_tags(_section_tags(hit["text"]) or ["identification"])
        chunks.append(RetrievedChunk(
            class_name=query.class_name,
            tags=tags,
            excerpt_text=excerpt_around_match(hit["text"], hit["matched_term"], 2000),
            raw_response=RetrievedChunk.raw_json({"title": hit["title"], "url": hit["url"], "matched_term": hit["matched_term"]}),
            source_url=hit["url"],
            license=LICENSE,
            accessed_date=str(date.today()),
            crop=query.crop,
            query_task=query.task,
        ))
    return chunks
