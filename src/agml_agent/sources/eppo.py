"""EPPO Data Portal REST API — free account + API key, EPPO Open Data
Licence. Per EPPO's own published REST docs:
    GET https://data.eppo.int/api/rest/1.0/tools/search?kw=<term>&authtoken=<key>
    GET https://data.eppo.int/api/rest/1.0/taxon/<eppocode>?authtoken=<key>
    GET https://data.eppo.int/api/rest/1.0/taxon/<eppocode>/categorization?authtoken=<key>
    GET https://data.eppo.int/api/rest/1.0/taxon/<eppocode>/hosts?authtoken=<key>
    GET https://data.eppo.int/api/rest/1.0/taxon/<eppocode>/distribution?authtoken=<key>

data.eppo.int timed out from the dev sandbox this was built in (DNS resolved,
TCP connect hung) — could not be hit live while writing this file. Confirm
with a real EPPO_API_KEY on a network that isn't blocking it. Only this
source needs a key — see README "API keys".
"""

from __future__ import annotations

import os
from datetime import date

from agml_agent.common.http import get
from agml_agent.common.schema import RetrievedChunk
from agml_agent.common.tagging import normalize_tags
from agml_agent.sources.base import ClassQuery

BASE = "https://data.eppo.int/api/rest/1.0"
LICENSE = "EPPO Open Data Licence"


def fetch(query: ClassQuery) -> list[RetrievedChunk]:
    api_key = os.environ.get("EPPO_API_KEY")
    if not api_key:
        raise RuntimeError(
            "EPPO_API_KEY not set. Register free at https://data.eppo.int/ui/#/user/register, "
            "log in, and your account page has your API token — put it in .env. See README 'API keys'."
        )

    eppocode = None
    for term in query.search_terms():
        resp = get(f"{BASE}/tools/search", params={"kw": term, "authtoken": api_key})
        if resp is None or resp.status_code != 200:
            continue
        hits = resp.json()
        if hits:
            eppocode = hits[0].get("eppocode")
            break
    if not eppocode:
        return []

    def _get(path: str):
        r = get(f"{BASE}/taxon/{eppocode}{path}", params={"authtoken": api_key})
        return r.json() if r is not None and r.status_code == 200 else None

    taxon = _get("")
    categorization = _get("/categorization") or []
    hosts = _get("/hosts") or []
    distribution = _get("/distribution") or []

    raw = {"taxon": taxon, "categorization": categorization, "hosts": hosts, "distribution": distribution}

    excerpt_parts = []
    if taxon:
        excerpt_parts.append(f"Preferred name: {taxon.get('prefname', query.class_name)}")
        if taxon.get("taxonomy"):
            excerpt_parts.append(f"Taxonomy: {taxon['taxonomy']}")
    if categorization:
        cats = ", ".join(c.get("name", "") for c in categorization if c.get("name"))
        if cats:
            excerpt_parts.append(f"Regulatory categorization: {cats}")
    if hosts:
        host_names = ", ".join(h.get("name", "") for h in hosts[:15] if h.get("name"))
        if host_names:
            excerpt_parts.append(f"Hosts: {host_names}")
    if distribution:
        regions = ", ".join(d.get("country", d.get("name", "")) for d in distribution[:15])
        if regions:
            excerpt_parts.append(f"Distribution: {regions}")

    tags = normalize_tags(
        ["taxonomy"]
        + (["category", "distribution"] if categorization else [])
        + (["host"] if hosts else [])
        + (["distribution"] if distribution else [])
    )

    return [RetrievedChunk(
        class_name=query.class_name,
        tags=tags,
        excerpt_text="\n".join(excerpt_parts) or query.class_name,
        raw_response=RetrievedChunk.raw_json(raw),
        source_url=f"https://gd.eppo.int/taxon/{eppocode}",
        license=LICENSE,
        accessed_date=str(date.today()),
        crop=query.crop,
        query_task=query.task,
        extra={"eppocode": eppocode},
    )]
