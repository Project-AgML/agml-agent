"""CABI Compendium — parked. Subscription/institutional access only, no API,
no bulk export except a manual data-request form. config/sources.yaml marks
this source `status: parked`, so retrieve.py skips it before ever calling
fetch(). This function exists only so importing the module (were something
to do it directly) fails loudly instead of silently returning nothing.
"""

from __future__ import annotations

from agml_agent.sources.base import ClassQuery
from agml_agent.common.schema import RetrievedChunk


def fetch(query: ClassQuery) -> list[RetrievedChunk]:
    raise NotImplementedError(
        "CABI Compendium has no API and no self-serve bulk export — request "
        "a data export directly from CABI (https://www.cabi.org/cabidigitallibrary/"
        "contact-us/) and, once granted, add a real fetcher here. This source "
        "is marked `status: parked` in config/sources.yaml and should stay "
        "excluded from retrieve.py until then."
    )
