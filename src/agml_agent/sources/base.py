"""Every src/sources/<name>.py module exposes one function with this shape:

    def fetch(query: ClassQuery) -> list[RetrievedChunk]

returning zero or more chunks for that one query (zero if nothing relevant
was found — never raise for an ordinary "no match," only for something a
human should actually see, like a missing API key). retrieve.py just imports
the module and calls .fetch(query) per active source — no registration, no
plugin machinery, the config/sources.yaml entry's `module` path is the only
wiring.

ClassQuery is built fresh per retrieve() call from its arguments — there is
no pre-enumerated list of classes anywhere in this repo; retrieve() is
demand-driven.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClassQuery:
    class_name: str
    crop: str = ""
    task: str = ""  # disease | pest | species | quality
    scientific_name: str | None = None
    aliases: list[str] | None = None

    def search_terms(self) -> list[str]:
        """class_name first, then scientific_name, then aliases — de-duped,
        order matters (first hit wins in most fetchers)."""
        terms = [self.class_name]
        if self.scientific_name and self.scientific_name not in terms:
            terms.append(self.scientific_name)
        for a in (self.aliases or []):
            if a not in terms:
                terms.append(a)
        return terms
