"""USDA AMS Grade Standards — public domain, no key. No documented search
API, and no flat per-commodity index either: the top-level page only lists
broad categories (fruits, vegetables, specialty-products, ...); a specific
commodity's own standards page is one level deeper. 2-level crawl: category
index -> category page -> commodity link matching the query crop, falling
back to the category page itself if no commodity-specific link is found.
"""

from __future__ import annotations

import re
from datetime import date

from agml_agent.common.http import get
from agml_agent.common.schema import RetrievedChunk
from agml_agent.common.scrape import excerpt_around_match, fetch_and_extract, find_match
from agml_agent.common.tagging import normalize_tags
from agml_agent.sources.base import ClassQuery

INDEX_URL = "https://www.ams.usda.gov/grades-standards"
LICENSE = "Public domain (US government)"

_CROP_TO_CATEGORY = {
    "apple": "fruits", "grape": "fruits", "citrus": "fruits", "peach": "fruits",
    "tomato": "vegetables", "potato": "vegetables", "onion": "vegetables",
    "coffee": "specialty-products", "cocoa": "specialty-products", "cotton": "cotton",
    "rice": "rice-pulses", "corn": "grain-standards", "wheat": "grain-standards",
}

_LINK_RE = re.compile(r'href="(/grades-standards/[^"]+)"[^>]*>([^<]+)<', re.I)
_SUFFIX_RE = re.compile(r"\s*grades?\s*(&|and)?\s*standards?\s*$", re.I)
# processed-product modifiers — a category page usually lists both the raw
# commodity ("Apple Grades & Standards") and several processed variants
# ("Apple Butter", "Canned Apple", "Apples for Processing", ...). Without
# ranking these, naive substring matching on crop name picks whichever
# variant happens to appear first in page order — e.g. "apple butter" before
# plain "apple" — which isn't what a fresh-produce/visual quality query means.
_MODIFIER_WORDS = {"butter", "juice", "sauce", "canned", "processing", "dried",
                    "frozen", "concentrate", "paste", "puree", "sliced", "diced"}


def _links(url: str) -> list[tuple[str, str]]:
    resp = get(url)
    if resp is None or resp.status_code != 200:
        return []
    return [(href, label) for href, label in _LINK_RE.findall(resp.text)]


def _rank_candidate(crop: str, label: str) -> tuple[int, int]:
    """Lower is better. Exact-commodity match ranks above any label carrying
    a processed-product modifier word; shortest label breaks remaining ties
    (the raw commodity's own label is almost always the shortest one)."""
    stripped = _SUFFIX_RE.sub("", label).strip().lower()
    has_modifier = any(w in label.lower() for w in _MODIFIER_WORDS)
    exact = stripped != crop.lower()
    return (int(has_modifier), int(exact), len(label))


def _find_commodity_url(crop: str) -> str | None:
    if not crop:
        return None
    category = _CROP_TO_CATEGORY.get(crop.lower())
    if not category:
        candidates = [(href, label) for href, label in _links(INDEX_URL) if crop.lower() in label.lower()]
        if not candidates:
            return None
        href, _ = min(candidates, key=lambda hl: _rank_candidate(crop, hl[1]))
        return "https://www.ams.usda.gov" + href

    category_url = f"{INDEX_URL}/{category}"
    candidates = [(href, label) for href, label in _links(category_url)
                  if crop.lower() in label.lower() or crop.lower() in href.lower()]
    if not candidates:
        return category_url
    href, _ = min(candidates, key=lambda hl: _rank_candidate(crop, hl[1]))
    return "https://www.ams.usda.gov" + href


def fetch(query: ClassQuery) -> list[RetrievedChunk]:
    if query.task and query.task != "quality":
        return []

    url = _find_commodity_url(query.crop)
    if not url:
        return []

    text = fetch_and_extract(url)
    if not text:
        return []

    terms = query.search_terms() + ([query.crop] if query.crop else [])
    matched = find_match(text, terms) or query.crop

    tags = normalize_tags(["grade_defect"])

    return [RetrievedChunk(
        class_name=query.class_name,
        tags=tags,
        excerpt_text=excerpt_around_match(text, matched, 2000),
        raw_response=RetrievedChunk.raw_json({"url": url, "matched_term": matched}),
        source_url=url,
        license=LICENSE,
        accessed_date=str(date.today()),
        crop=query.crop,
        query_task=query.task,
    )]
