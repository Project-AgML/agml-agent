"""
The one shape every source returns from retrieve() — nothing here is ever
written to disk; it's built fresh per call and handed back to the caller.
`source_organization` is deliberately not a field — it's implicit in which
source module produced the chunk (retrieve() already tags results by source
name in the dict it returns).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict


@dataclass
class RetrievedChunk:
    class_name: str            # the class/concept this chunk is evidence for
    tags: list[str]            # canonical tags first (see config/tags.yaml), then any
                                # source-specific extras — see src/common/tagging.py
    excerpt_text: str          # human/LLM-readable text — the part actually worth reading
    raw_response: str          # untouched source payload, stringified, in case a
                                # caller wants to re-derive tags/fields itself
    source_url: str
    license: str
    accessed_date: str         # ISO date this was fetched — "just now," not a build date
    crop: str = ""             # query metadata carried through for traceability
    query_task: str = ""
    extra: dict = field(default_factory=dict)  # source-specific fields that don't fit
                                                 # elsewhere (e.g. EPPO's eppocode)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @staticmethod
    def raw_json(obj) -> str:
        """Helper for building raw_response from a dict/list payload."""
        try:
            return json.dumps(obj, ensure_ascii=False)
        except TypeError:
            return json.dumps(str(obj), ensure_ascii=False)
