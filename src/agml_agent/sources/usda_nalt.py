"""USDA National Agricultural Library Thesaurus (NALT) — public linked-data
SKOS vocabulary hosted on NAL's LOD platform. Confirmed the *site* is live
(agclass.nal.usda.gov redirects there, 200), but could not confirm the exact
SPARQL query shape/results format live from the dev sandbox this was built
in (the browse UI is JS-driven). NAL's LOD deployments conventionally expose
a standard SPARQL endpoint at `/sparql` returning
`application/sparql-results+json` — that's what's implemented below. Fails
soft (returns []) rather than raising, specifically because of that
uncertainty — confirm on a network that isn't blocking it.
"""

from __future__ import annotations

import logging
from datetime import date

from agml_agent.common.http import get
from agml_agent.common.schema import RetrievedChunk
from agml_agent.common.tagging import normalize_tags
from agml_agent.sources.base import ClassQuery

log = logging.getLogger(__name__)

SPARQL_ENDPOINT = "https://lod.nal.usda.gov/sparql"
LICENSE = "Public domain (US government)"

_QUERY_TMPL = """
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?concept ?prefLabel WHERE {{
  ?concept a skos:Concept ;
           skos:prefLabel ?prefLabel .
  FILTER(CONTAINS(LCASE(STR(?prefLabel)), LCASE("{term}")))
}} LIMIT 1
"""

_DETAIL_TMPL = """
PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
SELECT ?p ?o WHERE {{
  <{uri}> ?p ?o .
}}
"""


def _sparql(query: str) -> dict | None:
    resp = get(SPARQL_ENDPOINT, params={"query": query, "format": "json"})
    if resp is None or resp.status_code != 200:
        return None
    try:
        return resp.json()
    except ValueError:
        log.warning("NALT SPARQL response wasn't JSON — endpoint shape may differ from what's assumed here")
        return None


def fetch(query: ClassQuery) -> list[RetrievedChunk]:
    concept_uri = None
    matched_label = None
    for term in query.search_terms():
        result = _sparql(_QUERY_TMPL.format(term=term))
        bindings = (result or {}).get("results", {}).get("bindings", [])
        if bindings:
            concept_uri = bindings[0]["concept"]["value"]
            matched_label = bindings[0]["prefLabel"]["value"]
            break
    if not concept_uri:
        return []

    detail = _sparql(_DETAIL_TMPL.format(uri=concept_uri))
    triples = (detail or {}).get("results", {}).get("bindings", [])

    alt_labels, broader, narrower = [], [], []
    for t in triples:
        pred = t.get("p", {}).get("value", "")
        obj = t.get("o", {}).get("value", "")
        if pred.endswith("altLabel"):
            alt_labels.append(obj)
        elif pred.endswith("broader"):
            broader.append(obj)
        elif pred.endswith("narrower"):
            narrower.append(obj)

    excerpt_parts = [f"Preferred label: {matched_label}"]
    if alt_labels:
        excerpt_parts.append(f"Synonyms (altLabel): {', '.join(alt_labels[:10])}")
    if broader:
        excerpt_parts.append(f"Broader concepts: {len(broader)} linked")
    if narrower:
        excerpt_parts.append(f"Narrower concepts: {len(narrower)} linked")

    tags = normalize_tags(
        ["taxonomy"] + (["synonym"] if alt_labels else []) + (["taxonomy"] if broader or narrower else [])
    )

    return [RetrievedChunk(
        class_name=query.class_name,
        tags=tags,
        excerpt_text="\n".join(excerpt_parts),
        raw_response=RetrievedChunk.raw_json({"concept_uri": concept_uri, "triples": triples}),
        source_url=concept_uri,
        license=LICENSE,
        accessed_date=str(date.today()),
        crop=query.crop,
        query_task=query.task,
    )]
