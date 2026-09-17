"""Shared HTTP conventions: one User-Agent, one retry/backoff policy, one
place to slow down against sources that don't like being hammered."""

from __future__ import annotations

import logging
import time

import requests

log = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": (
        "AgML-Agent/1.0 "
        "(+https://github.com/Project-AgML; research/non-commercial; "
        "contact via github.com/Project-AgML)"
    )
}

TIMEOUT = 20
RETRY_DELAYS = [3, 8, 20]  # seconds, on 429/5xx


def get(url: str, *, params: dict | None = None, headers: dict | None = None,
        sleep: float = 0.5) -> requests.Response | None:
    """GET with retry on 429/5xx, a polite sleep after every call (success or
    not), and None (never a raised exception) on total failure."""
    merged_headers = {**HEADERS, **(headers or {})}
    resp = None
    for attempt, delay in enumerate([0] + RETRY_DELAYS):
        if delay:
            log.debug("retry in %ds (attempt %d) — %s", delay, attempt + 1, url)
            time.sleep(delay)
        try:
            resp = requests.get(url, params=params, headers=merged_headers, timeout=TIMEOUT)
        except requests.RequestException as e:
            log.warning("request failed: %s — %s", url, e)
            time.sleep(sleep)
            continue
        if resp.status_code not in (429, 500, 502, 503, 504):
            time.sleep(sleep)
            return resp
    time.sleep(sleep)
    if resp is not None:
        log.warning("giving up after retries: %s — status %d", url, resp.status_code)
    return resp
