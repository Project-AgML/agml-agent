# agml-agent

An agentic toolkit for grounding AgML predictions/evaluation — two tools,
one MCP server. Nothing is pre-built or published: every call fetches live,
right now, from either live external sources or AgML's own dataset catalog.
Design doc: [AgML Agent Toolkit](https://claude.ai/artifact/RwqtEov5Feag7Qg6sWuDZQ).

- **`retrieve()`** — live grounding text/images for one class, from external
  sources (EPPO, GBIF, UC IPM/APS, Bugwood, USDA...).
- **`search_agml()`** — search or exact-lookup AgML's own dataset catalog
  (real classes, licenses, HF links, and real model benchmark results).
- **`mcp_server.py`** — wraps both as MCP tools, usable from Claude Code,
  Claude Desktop, Cursor, or any other MCP-compatible agent framework, not
  just this repo's own scripts.

Deployment (how this actually ships/runs in production) is a separate
conversation — this README covers building and testing it locally.

## Setup

Uses [uv](https://docs.astral.sh/uv/) — no manual venv, no `pip install`.

```bash
uv sync
cp .env.example .env
```

### API keys

Only **one** source needs a key — everything else, including the real
`agml` package and the AgML website data, is free and keyless.

- **`EPPO_API_KEY`** — used only by `src/sources/eppo.py` (part of
  `retrieve()`, not `search_agml()`). Free key:
  1. Register at [data.eppo.int/ui/#/user/register](https://data.eppo.int/ui/#/user/register)
  2. Log in at [data.eppo.int/ui/#/user/login](https://data.eppo.int/ui/#/user/login)
  3. Your account page has your API token
  4. Paste it into `.env`

  Without it, `retrieve()` logs an error for `eppo` and continues with every
  other source — it never blocks the call.

## The MCP server

```bash
uv run mcp_server.py
```

Exposes two tools, `retrieve_grounding` and `search_agml`, over stdio — any
MCP client that can launch a command speaks to it the same way. Example
Claude Desktop config (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "agml-agent": {
      "command": "uv",
      "args": ["run", "--directory", "/absolute/path/to/agml-agent", "mcp_server.py"]
    }
  }
}
```

Verified end to end with a real MCP client (not just direct function calls)
— started the server as a subprocess, listed its tools over the actual
protocol, and called both:

```
TOOL: retrieve_grounding
 params: ['class_name', 'crop', 'task', 'scientific_name', 'aliases', 'sources']
TOOL: search_agml
 params: ['query', 'exact_name', 'ml_task', 'ag_task', 'limit']
```

One thing worth knowing if you're on `mcp>=2.0`: that release renamed
`FastMCP` to `MCPServer` (`from mcp.server.mcpserver import MCPServer`) —
`mcp_server.py` already uses the new name; if you're following older MCP
tutorials elsewhere, they'll reference the old one.

### Getting this into frameworks that don't speak MCP natively

Claude Code, Claude Desktop, Cursor, and anything else MCP-aware need
nothing beyond the config above. A framework that isn't MCP-native (Ollama
today) needs a small **bridge**: start `mcp_server.py`, call `list_tools()`
to get the real schemas, translate them into that framework's own tool
format, and forward tool calls through the MCP session instead of calling
Python functions directly. `chat.py` (below) *is* that bridge for Ollama —
built this way on purpose so there's exactly one adapter pattern to reuse
for any future non-MCP backend, rather than a second hand-maintained copy
of the tool definitions per framework.

## Interactive chat via Ollama (`chat.py`)

```bash
uv run chat.py                                    # local Ollama, pick model interactively
uv run chat.py --host http://192.168.1.50:11434    # a VM with more VRAM/compute
uv run chat.py --model qwen2.5:7b                  # skip the model picker
```

`--host` (or the `OLLAMA_HOST` env var) points at any Ollama server, local
or remote — useful for running the model on a machine with more VRAM than
this one. On startup it lists whichever models that server has pulled and
lets you pick, or `--model` skips straight to one.

Under the hood: `chat.py` starts `mcp_server.py` as a subprocess and talks
to it as a real MCP client — the tool schemas Ollama sees come from
`list_tools()`, not a separate hand-written copy. Verified structurally
(schema translation + a real tool call through the MCP session) without
needing a local model call to prove it. One real end-to-end run (model
choosing a tool from a plain-language prompt) already confirmed
`search_agml` gets picked correctly for a dataset-discovery question.

## Testing each tool directly

### `retrieve()` — external grounding

`uv run retrieve.py --help` documents every argument. Quick summary:

| arg | meaning |
|---|---|
| `class_name` (positional, required) | the class/concept to look up, e.g. `"Coffee leaf rust"` |
| `--crop` | the crop/host, e.g. `coffee` |
| `--task` | `disease` \| `pest` \| `species` \| `quality` — restricts which sources are tried |
| `--sci` | scientific name — tried if `class_name` alone doesn't match |
| `--aliases` | space-separated alternate names to also try |
| `--sources` | restrict to specific source names, e.g. `--sources gbif eppo` |
| `--json` | also print full JSON |

```bash
uv run retrieve.py "Coffee leaf rust" --crop coffee --sci "Hemileia vastatrix" --aliases roya --task disease
```

```python
from retrieve import retrieve
result = retrieve("Coffee leaf rust", crop="coffee", task="disease",
                   scientific_name="Hemileia vastatrix", aliases=["roya"])
# {"ucipm_aps": [...], "bugwood": [...]}
```

### `search_agml()` — AgML's own catalog

`uv run search_agml.py --help` documents every argument. Quick summary:

| arg | meaning |
|---|---|
| `query` (positional, optional) | keyword(s) — every word must match somewhere in a dataset's name/classes/crop/task |
| `--exact-name` | look up one dataset by its exact name, bypassing keyword matching — the eval-set opt-in path |
| `--ml-task` | e.g. `image_classification`, `object_detection`, `semantic_segmentation` |
| `--ag-task` | e.g. `disease_classification`, `weed_detection`, `quality_classification` |
| `--limit` | max results (default 10) |
| `--json` | also print full JSON |

```bash
uv run search_agml.py "citrus disease" --ml-task image_classification
uv run search_agml.py --exact-name bean_disease_uganda
```

Real output from a live run:

```
4 matched, showing 4:

  lemon_leaf_disease_classification — image_classification/disease_classification — 9 classes, 1354 images
    classes: Anthracnose, Bacterial Blight, Citrus Canker, Curl Virus, Deficiency Leaf, Dry Leaf, Healthy Leaf, Sooty Mould
  citrusuat_disease_classification — image_classification/disease_classification — 12 classes, 953 images
    classes: Citrus_leafminer, Fe, Greasy_spot, HLB, Healthy, Mg, Mn, N
  citrus_fruit_leaf_disease_classification — image_classification/disease_classification — 6 classes, 759 images
    classes: black_spot, canker, greening, healthy, melanose, scab
```

## A real combined workflow (both tools together)

This is genuinely how they're meant to compose — tested live, output real:

```python
from search_agml import search_agml
from retrieve import retrieve

# 1. Discover: "I'm building a citrus disease classifier"
candidates = search_agml("citrus disease")["results"]
# -> citrus_fruit_leaf_disease_classification, citrusuat_disease_classification, ...

# 2. Inspect one candidate + its real benchmark history before committing to it
full = search_agml(exact_name="citrus_fruit_leaf_disease_classification")["results"][0]
# classes: ['black_spot', 'canker', 'greening', 'healthy', 'melanose', 'scab']
# benchmarks: [('google/gemma-4-12b-it', f1=0.279), ('qwen/Qwen3.6-27B-FP8', f1=0.284)]
# -> zero-shot VLMs score poorly here; a fine-tuned model or few-shot prompting
#    is probably worth planning for, not assuming zero-shot is good enough

# 3. One of its classes ("greening") needs grounding text for a prompt/rubric
grounding = retrieve("Citrus greening", crop="citrus", task="disease",
                      scientific_name="Candidatus Liberibacter asiaticus",
                      aliases=["HLB", "Huanglongbing"])
# -> real symptom/pathogen text from UC IPM/APSnet and Bugwood
```

## Sources (`retrieve()`)

9 external sources registered in `config/sources.yaml`; only `active` ones
are ever called.

| source | task | access | status |
|---|---|---|---|
| EPPO Data Portal | disease, pest | keyed API | active — needs `EPPO_API_KEY`, unverified (sandbox network blocked it) |
| UC IPM / APSnet | disease, pest | scrape | active — verified live |
| Plantwise Knowledge Bank | disease, pest | scrape | **paused** — bot-blocked (403), see note below |
| Bugwood / IPM Images | disease, pest | scrape | active — verified live |
| GBIF | species | free API | active — verified live |
| USDA NALT | species | free API | active — unverified (SPARQL endpoint unconfirmed from this sandbox) |
| USDA PLANTS | species | free API | active — verified live |
| USDA AMS Grade Standards | quality | scrape | active — verified live |
| CABI Compendium | disease, pest | gated | parked — no API, no self-serve export |

**Plantwise is paused, not broken-and-forgotten.** Every fetch attempt got
`403` (bot-protection a plain HTTP client can't pass). `src/sources/plantwise.py`
is written and will work as-is once that's solved (headless browser,
scraping proxy, or a direct ask to CABI/Plantwise) — flip `status: paused`
to `active` in `config/sources.yaml` when it is.

Adding a 9th source later: write `src/sources/<name>.py` exposing
`fetch(query: ClassQuery) -> list[RetrievedChunk]`, add one entry to
`config/sources.yaml`.

## How `retrieve()` works

```python
def retrieve(
    class_name: str,
    crop: str = "",
    task: str = "",                       # disease | pest | species | quality
    scientific_name: str | None = None,
    aliases: list[str] | None = None,
    sources: list[str] | None = None,      # None = every active source
) -> dict[str, list[dict]]:                # {source_name: [chunk, ...]}
```

- No seed list, no enumeration — every call is a single, on-demand lookup.
- Per-process **in-memory cache only**, keyed by `(source, class_name)`.
  Nothing persists across runs, nothing is written to disk, nothing is
  published. A caller doing anything paper-quality should log what
  `retrieve()` actually returned alongside its results.
- A source erroring is logged and simply omitted — one broken source never
  breaks the call.

### Every `retrieve()` chunk has the same shape

| field | meaning |
|---|---|
| `class_name` | the class/concept this chunk is evidence for |
| `tags` | canonical tags first (see `config/tags.yaml`), then source-specific extras |
| `excerpt_text` | the human/LLM-readable text |
| `raw_response` | untouched source payload, JSON-stringified |
| `source_url` | where this was fetched from |
| `license` | per-row license — verify before commercial/deployment use |
| `accessed_date` | today's date — this is a live fetch, not a build date |
| `crop`, `query_task` | query metadata carried through for traceability |
| `extra` | source-specific fields (e.g. EPPO's `eppocode`, GBIF's `images`) |

Canonical tag vocabulary (`config/tags.yaml`): `taxonomy`, `synonym`, `host`,
`symptom`, `life_cycle`, `damage`, `management`, `distribution`, `category`,
`identification`, `grade_defect`.

### Images

Only `gbif.py` returns real images today, in `extra["images"]` — a list of
`{url, license, creator, publisher, references}`, each **individually
licensed**. Getting from "the API returns something" to "the image is
actually correct" took four real, visually-confirmed fixes:

1. `/species/search`'s `key` is often a source-checklist ID, not the GBIF
   Backbone Taxonomy key `/occurrence/search` needs — resolved via a second
   `/species/match` call.
2. **Term order matters more than expected.** `gbif.py` used to try
   `class_name` before `scientific_name`. For a disease query like "Tomato
   late blight," GBIF's species search doesn't fail — it fuzzy-matches to
   whatever scores best, and confirmed live, that was **"Catalpa ovata,"** an
   unrelated flowering tree. Fixed by trying `scientific_name` first.
3. A *fuzzy* match (`matchType` ≠ `EXACT`) isn't trustworthy either —
   confirmed live: "Candidatus Liberibacter asiaticus" (citrus greening)
   only matched at genus rank, pulling images for the whole genus. Only
   `EXACT` matches are used for images now.
4. Even a correct, exact species match can have **systematically wrong
   media**: every Phytophthora infestans photo from
   `basisOfRecord: PRESERVED_SPECIMEN` traced back to one broken herbarium
   dataset. Filtered to `basisOfRecord=HUMAN_OBSERVATION` only, and capped
   per-occurrence so one bad observation can't fill the whole result.

**Residual risk no filter removes**: GBIF doesn't expose iNaturalist's
"research grade" verification flag, so a correctly-matched record can still
be a wrong citizen-science ID. Treat every image as candidate, unverified
evidence.

Bugwood does **not** provide images today — its photo-browsing sites have
no discoverable public API; `bugwood.py` only reaches a separate text-wiki
subdomain.

## `search_agml()` — AgML's own catalog, two sources merged

```python
def search_agml(
    query: str = "",
    exact_name: str | None = None,
    ml_task: str | None = None,
    ag_task: str | None = None,
    limit: int = 10,
) -> dict:                                 # {"results": [...], "total_matched": N}
```

**Merges two catalogs, keyed by dataset name** (`src/agml_catalog.py`):

- `agml.data.public_data_sources()` — the real, installed `agml` package's
  own ~6,000-entry catalog (69 "core" + `iNatAg-mini` + `iNatAg` species
  splits). Thinner metadata, but covers datasets the website doesn't.
- The AgML **website**'s `hf_datasets.json` — 300 richer, more current
  entries (imaging equipment, collection period, precise location, file
  size), **live-fetched**, never vendored. Confirmed necessary: a specific
  dataset (`ACHENY_variety_classification`) isn't in the package's bundled
  files at all — confirmed by reading `agml/utils/data.py::load_public_sources()`
  directly, which only loads 3 fixed local JSON files, no runtime fetch of
  anything richer.

No embeddings — keyword/whole-token relevance matching (same pattern as
`usda_plants.py`/`gbif.py` in `retrieve()`), not a precomputed vector index.
The catalog's long tail (`iNatAg` species splits) is never meant to be
browsed raw — it's ~6,000 entries, one fine-grained species split repeated
per-taxon; the genuinely diverse core+curated catalog is small enough for
keyword filtering + an LLM iterating on terms to work without one.

**Two real bugs found and fixed during testing**, both from the website's
own data being inconsistently typed:
1. A multi-word query like `"citrus disease"` was matching the whole string
   as one literal phrase (so real matches were missed) — fixed to match
   each word independently (AND).
2. Dataset names use underscores (`citrus_fruit_leaf_disease_classification`)
   — regex `\b` does **not** treat `_` as a word boundary, so whole-word
   matching silently matched nothing against real dataset names. Fixed with
   proper tokenization on non-alphanumeric characters.
3. `classes` is inconsistently typed in the website's own JSON — sometimes a
   real list, sometimes one comma-joined string (`plant_village_classification`),
   sometimes a one-element list *containing* a comma-joined string
   (`arabica_coffee_leaf_disease_classification`'s website entry, while its
   package entry has the same 5 classes correctly separated). All three
   shapes normalized to a real list in one place (`_normalize_classes`) so
   nothing downstream has to defend against it.

### What a result contains

A keyword search (`query=...`) returns **trimmed summaries** — name, task,
crop, image/class counts, a class preview — enough to judge relevance
without dumping full records for every candidate.

An `exact_name=...` lookup returns the **full record**, plus real benchmark
data live-fetched from the AgML website
(`…/data/performance/<name>.json`) when available — actual zero-shot VLM
results (model, f1/precision/recall, the exact prompt used), not vendored,
not guessed.

**No eval/held-out flag exists in AgML** — checked the package's full
schema and codebase, there isn't one. Which dataset(s) count as a held-out
eval set for a given project is necessarily an external policy decision;
`exact_name` is the only way to reach a specific dataset regardless of
whether `query` would have surfaced it, which is what makes it the
deliberate opt-in path rather than something that happens by accident.

## Project structure

```
agml-agent/
├── retrieve.py          # external grounding — tool 1
├── search_agml.py        # AgML catalog search/lookup — tool 2
├── mcp_server.py          # wraps both as MCP tools
├── chat.py                # interactive Ollama chat, via mcp_server.py as an MCP client
├── config/
│   ├── sources.yaml       # external source registry (retrieve())
│   └── tags.yaml          # canonical tag vocabulary (retrieve())
└── src/
    ├── agml_catalog.py     # package + website catalog merge (search_agml())
    ├── common/             # http.py, scrape.py, schema.py, tagging.py (retrieve())
    └── sources/            # one fetcher per external source (retrieve())
```

## Inference backend (vLLM vs. Ollama)

`retrieve()` and `search_agml()` never call an LLM themselves — they only
return grounding text/data. `chat.py` does call one, but only to *test* that
an LLM actually picks the right tool with sensible arguments — it isn't the
eventual `predict()` pipeline's backend. That backend decision is still
open:

- **vLLM** — distributed/batch inference, matches offline `vLLM.generate()`
  eval runs. Right fit for research-scale batch prediction.
- **Ollama** ([ollama-python](https://github.com/ollama/ollama-python)) —
  local, single-request, near-zero setup. Right fit for typical/interactive
  usage.

Plan: a thin backend interface once `predict()` exists — not a decision
either tool here needs to make.

## Orchestration

The MCP server above **is** the "MCP tools + thin custom loop" orchestration
call from the design doc, actually built — not LangChain, matching the
reasoning that the batch prediction pipeline is offline `vLLM.generate()`,
not a chat-completion loop.
