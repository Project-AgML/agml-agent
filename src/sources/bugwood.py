"""Bugwood / IPM Images network — factsheet text (not the images themselves)
is what's returned here; images are CC-BY or CC-BY-NC PER IMAGE, so `license`
is left as a flag to verify per item rather than asserted as one blanket
license. Verified live (site-restricted search, same as ucipm_aps).
"""

from __future__ import annotations

from datetime import date

from src.common.schema import RetrievedChunk
from src.common.scrape import excerpt_around_match, search_and_extract
from src.common.tagging import normalize_tags
from src.sources.base import ClassQuery

SITES = ["bugwood.org", "images.bugwood.org", "ipmimages.org", "forestryimages.org"]
LICENSE = "CC-BY or CC-BY-NC per item — VERIFY on source_url before commercial/deployment use"


def fetch(query: ClassQuery) -> list[RetrievedChunk]:
    terms = query.search_terms()
    q = f"{query.class_name} {query.crop}"
    # imgrecruit/listxtax pages are Bugwood's internal image-cataloging index
    # (a giant table of every taxon name in their system) — a page matching
    # on class_name there is a false-positive relevance hit, not real content.
    hits = search_and_extract(q, SITES, terms, max_results=6, keep=2,
                               avoid_url_substrings=["imgrecruit", "listxtax"])

    chunks = []
    for hit in hits:
        tags = normalize_tags(["identification", "damage"])
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
