# agml-agent

Agentic toolkit for agricultural ML grounding and dataset discovery, exposed via MCP.

- **`retrieve`** — live grounding text/images for a disease, pest, species, or quality class, from external sources (EPPO, GBIF, UC IPM/APS, Bugwood, USDA).
- **`search_agml`** — search or look up datasets in the AgML catalog, including class labels, licenses, and model benchmark results.

## Install

```bash
uvx --from git+https://github.com/Project-AgML/agml-agent agml-agent-mcp
```

## Usage

### MCP clients (Claude Code, Claude Desktop, Cursor, etc.)

Claude Code (`-s user` makes it available in every project, not just the current one):

```bash
claude mcp add agml-agent -s user -- uvx --from git+https://github.com/Project-AgML/agml-agent agml-agent-mcp
```

Claude Desktop / any other MCP-compatible client:

```json
{
  "mcpServers": {
    "agml-agent": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/Project-AgML/agml-agent", "agml-agent-mcp"]
    }
  }
}
```

### Ollama

Ollama has no MCP client support, so `agml-agent-chat` runs as a standalone bridge process instead of a client config: it connects to your Ollama server, translates the MCP tool schemas into Ollama's tool-calling format, and forwards tool calls back through MCP.

```bash
uvx --from git+https://github.com/Project-AgML/agml-agent agml-agent-chat --host http://localhost:11434
```

### CLI

```bash
uvx --from git+https://github.com/Project-AgML/agml-agent agml-agent-retrieve "Coffee leaf rust" --crop coffee --sci "Hemileia vastatrix"
uvx --from git+https://github.com/Project-AgML/agml-agent agml-agent-search "citrus disease" --ml-task image_classification
```

### Python

```python
from agml_agent.retrieve import retrieve
from agml_agent.search_agml import search_agml

retrieve("Coffee leaf rust", crop="coffee", scientific_name="Hemileia vastatrix")
search_agml("citrus disease", ml_task="image_classification")
```

## Tools

### `retrieve(class_name, crop="", task="", scientific_name=None, aliases=None, sources=None)`

Returns `{source_name: [chunk, ...]}`. Each chunk:

| field | type |
|---|---|
| `class_name` | str |
| `tags` | list[str] |
| `excerpt_text` | str |
| `raw_response` | str (JSON) |
| `source_url` | str |
| `license` | str |
| `accessed_date` | str |
| `extra` | dict |

`task`: `disease` \| `pest` \| `species` \| `quality`.
`sources`: restrict to specific source names (default: all active sources).

**Sources**: EPPO, UC IPM/APS, Bugwood, GBIF, USDA NALT, USDA PLANTS, USDA AMS Grade Standards. Configured in `src/agml_agent/config/sources.yaml`.

### `search_agml(query="", exact_name=None, ml_task=None, ag_task=None, limit=10)`

Returns `{"results": [...], "total_matched": N}`. Keyword search returns trimmed summaries; `exact_name` returns full metadata plus benchmark results.

`ml_task`: `image_classification` \| `object_detection` \| `semantic_segmentation`.
`ag_task`: e.g. `disease_classification`, `weed_detection`, `quality_classification`.

## Updating / removing

`uvx --from git+...` resolves the latest commit on the default branch on every launch — each new session picks up the newest version automatically, no reinstall needed. To pin a stable version instead, append `@<tag>` to the URL, e.g. `git+https://github.com/Project-AgML/agml-agent@v0.1.0`.

To remove:

```bash
claude mcp remove agml-agent
```

For other MCP clients, delete the `agml-agent` entry from the client's MCP config.

## Configuration

```bash
cp .env.example .env
```

| variable | required for | notes |
|---|---|---|
| `EPPO_API_KEY` | `retrieve` (EPPO source only) | free — [register](https://data.eppo.int/ui/#/user/register) |
| `OLLAMA_HOST` | `agml-agent-chat` | defaults to `http://localhost:11434` |

## Development

```bash
git clone https://github.com/Project-AgML/agml-agent
cd agml-agent
uv sync
uv run agml-agent-mcp
```

## License

Apache 2.0
