"""
Normalizes each source's native tag/field/section-header strings onto the
canonical vocabulary in config/tags.yaml, so an agent can filter by tag
consistently regardless of which source a chunk came from.

Nothing is dropped: a raw tag with no known alias is kept as-is, just sorted
after the canonical ones.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

_TAGS_YAML = Path(__file__).resolve().parents[2] / "config" / "tags.yaml"


@lru_cache(maxsize=1)
def _load_vocab() -> tuple[list[str], dict[str, list[str]]]:
    cfg = yaml.safe_load(_TAGS_YAML.read_text(encoding="utf-8"))
    canonical = list(cfg["tags"].keys())
    aliases = {k.lower(): v for k, v in (cfg.get("aliases") or {}).items()}
    return canonical, aliases


def canonical_tags() -> list[str]:
    return _load_vocab()[0]


def normalize_tags(raw_tags: list[str]) -> list[str]:
    canonical, aliases = _load_vocab()
    resolved: list[str] = []
    extras: list[str] = []

    for raw in raw_tags:
        if not raw:
            continue
        key = raw.strip().lower()
        if key in canonical:
            if key not in resolved:
                resolved.append(key)
        elif key in aliases:
            for mapped in aliases[key]:
                if mapped not in resolved:
                    resolved.append(mapped)
        else:
            cleaned = raw.strip().lower().replace(" ", "_")
            if cleaned not in extras:
                extras.append(cleaned)

    ordered_canonical = [t for t in canonical if t in resolved]
    return ordered_canonical + extras
