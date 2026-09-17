"""Plantwise Knowledge Bank — CABI-run but confirmed free/open factsheets
(~4,000), distinct from the paywalled CABI Compendium. PAUSED: every request
from this sandbox — even with a browser-like User-Agent — got a 403
(bot-protected). config/sources.yaml has this marked `status: paused`, so
retrieve.py skips it. Left implemented so it's ready the moment the block is
solved (headless browser, scraping proxy, or a direct ask to CABI/Plantwise).
"""

from __future__ import annotations

from datetime import date

from agml_agent.common.schema import RetrievedChunk
from agml_agent.common.scrape import excerpt_around_match, search_and_extract
from agml_agent.common.tagging import normalize_tags
from agml_agent.sources.base import ClassQuery

SITES = ["plantwiseplusknowledgebank.org"]
LICENSE = "CABI Plantwise Knowledge Bank — free/open factsheet"


def fetch(query: ClassQuery) -> list[RetrievedChunk]:
    terms = query.search_terms()
    q = f"{query.class_name} {query.crop} factsheet"
    hits = search_and_extract(q, SITES, terms, max_results=6, keep=2, avoid_url_substrings=["/doi/pdf/"])

    chunks = []
    for hit in hits:
        tags = normalize_tags(["identification", "symptom", "management"])
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
