"""Shared site-restricted search + extract, for the sources with no stable
search API (ucipm_aps, plantwise, bugwood): search restricted to a domain,
fetch each candidate page fresh, extract clean text, keep only pages that
actually mention the class (a search engine ranking a page well doesn't mean
it's about this specific class)."""

from __future__ import annotations

import logging
import time

import requests
import trafilatura
from ddgs import DDGS

from agml_agent.common.http import HEADERS, TIMEOUT

log = logging.getLogger(__name__)

FETCH_SLEEP = 1.0


def fetch_and_extract(url: str) -> str | None:
    """requests (with our own User-Agent) + trafilatura.extract — trafilatura
    2.x's fetch_url() no longer takes a `headers` kwarg, so the HTTP fetch is
    done ourselves and only the HTML is handed to trafilatura."""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as e:
        log.debug("fetch failed for %s: %s", url, e)
        return None
    if resp.status_code != 200:
        return None
    return trafilatura.extract(resp.text)


def find_match(text: str, terms: list[str]) -> str | None:
    text_lower = text.lower()
    for term in terms:
        if term.lower() in text_lower:
            return term
    return None


def excerpt_around_match(text: str, term: str, max_len: int = 1200) -> str:
    idx = text.lower().find(term.lower())
    if idx == -1:
        return text[:max_len]
    start = max(0, idx - max_len // 4)
    return text[start:start + max_len]


def search_and_extract(
    query: str,
    sites: list[str],
    match_terms: list[str],
    max_results: int = 6,
    keep: int = 2,
    avoid_url_substrings: list[str] | None = None,
) -> list[dict]:
    """Returns up to `keep` dicts: {title, url, text, matched_term}.

    avoid_url_substrings deprioritizes matching hits (e.g. "/pdf/" links that
    trafilatura can't extract text from) rather than dropping them outright —
    they're tried last, so a source whose only hits are PDFs still gets
    something instead of nothing."""
    site_filter = " OR ".join(f"site:{s}" for s in sites)
    full_query = f"({site_filter}) {query}"

    hits: list[dict] = []
    for attempt, delay in enumerate([0, 4, 10]):
        if delay:
            time.sleep(delay)
        try:
            hits = list(DDGS().text(full_query, max_results=max_results))
            if hits:
                break
        except Exception as e:
            log.debug("search attempt %d failed for %r: %s", attempt + 1, full_query, e)
    if not hits:
        log.warning("no search results for %r after retries — DDGS backends can be flaky/"
                     "rate-limited at scale, retry this class individually if it matters", full_query)
        return []

    avoid = avoid_url_substrings or []
    if avoid:
        hits.sort(key=lambda h: any(a in (h.get("href") or "") for a in avoid))

    found: list[dict] = []
    for hit in hits:
        if len(found) >= keep:
            break
        url = hit.get("href")
        if not url or not any(s in url for s in sites):
            continue
        try:
            text = fetch_and_extract(url)
            if not text:
                continue
            matched = find_match(text, match_terms)
            if matched is None:
                continue
            found.append({
                "title": hit.get("title") or url,
                "url": url,
                "text": text,
                "matched_term": matched,
            })
        except Exception as e:
            log.debug("fetch/extract failed for %s: %s", url, e)
        time.sleep(FETCH_SLEEP)
    return found
