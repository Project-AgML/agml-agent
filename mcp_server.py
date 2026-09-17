"""
The MCP server — wraps retrieve() and search_agml() as two distinct tools,
reachable identically from any MCP-compatible agent (Claude Code, Claude
Desktop, Cursor, a custom agent loop), not just this project's own scripts.

Run directly:
    uv run mcp_server.py

Point an MCP client at it by running this file as the client's configured
command — see README "MCP server" for a Claude Desktop config example.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer  # mcp>=2.0 — FastMCP was renamed to MCPServer

from retrieve import retrieve as _retrieve
from search_agml import search_agml as _search_agml

mcp = MCPServer("agml-agent")


@mcp.tool()
def retrieve_grounding(
    class_name: str,
    crop: str = "",
    task: str = "",
    scientific_name: str | None = None,
    aliases: list[str] | None = None,
    sources: list[str] | None = None,
) -> dict:
    """Fetch live grounding text/images for one class from external sources
    (EPPO, UC IPM/APS, Bugwood, GBIF, USDA NALT/PLANTS/AMS Grade Standards).

    Nothing is pre-built or cached across calls beyond the current process —
    every call hits each source live, right now. If results come back empty
    or thin, retry with a different `scientific_name`, broader `aliases`, a
    narrower `task`, or without a `crop` — this is expected, not an error.

    `task` restricts which sources are even tried (disease/pest sources
    differ from species-ID or quality sources) — omit it to try every
    active source. `sources` restricts to specific source names (e.g.
    ["gbif", "eppo"]) instead of every active one.

    Returns {source_name: [chunk, ...]} — only sources that found something
    appear as keys. Each chunk has class_name, tags, excerpt_text,
    raw_response, source_url, license, accessed_date, and (for GBIF) a list
    of real licensed images in extra["images"] when available.
    """
    return _retrieve(
        class_name=class_name, crop=crop, task=task,
        scientific_name=scientific_name, aliases=aliases, sources=sources,
    )


@mcp.tool()
def search_agml(
    query: str = "",
    exact_name: str | None = None,
    ml_task: str | None = None,
    ag_task: str | None = None,
    limit: int = 10,
) -> dict:
    """Search AgML's own dataset catalog (the real `agml` package's ~6,000
    entries merged with the AgML website's richer, more current ~300-entry
    catalog), or look up one dataset by its exact name.

    `query` is keyword search (e.g. "citrus disease", "weed detection") —
    every word must match somewhere in a dataset's name/classes/crop/task,
    no embeddings. Narrow further with `ml_task` (e.g.
    "image_classification", "object_detection", "semantic_segmentation") or
    `ag_task` (e.g. "disease_classification", "weed_detection",
    "quality_classification"). Empty or irrelevant results? Retry with
    different/fewer keywords, or drop a filter — same idea as
    retrieve_grounding.

    `exact_name` looks up one specific dataset by its exact catalog name,
    bypassing keyword matching entirely — this is the ONLY way to reach a
    dataset that should be treated as a held-out/eval set for this project
    (AgML itself has no such flag; that's a policy decision on the caller's
    side, not something this tool infers).

    A keyword search returns trimmed summaries (name, task, crop, image/
    class counts, a class preview) for judging relevance without dumping
    full records. An exact_name lookup returns full detail for that one
    dataset AND its real benchmark results (zero-shot VLM scores — model,
    f1/precision/recall, the actual prompt used) when available, live-
    fetched from the AgML website, not vendored.
    """
    return _search_agml(
        query=query, exact_name=exact_name,
        ml_task=ml_task, ag_task=ag_task, limit=limit,
    )


if __name__ == "__main__":
    mcp.run()
