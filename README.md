# fields-study-flow

## Reproducible paper path and limits

Default CLI and MCP searches are offline. Opt into public arXiv/GitHub metadata with `roadmap --live`, `ingest-url --fetch-metadata`, or MCP `filters.offline=false` / `fetchMetadata=true`. The `paper` CLI remains a curated offline route; it does not parse arbitrary papers. arXiv abs/PDF links use the Atom metadata API, normalizing title, authors, abstract (`summary`), year, categories and version-independent IDs. No PDF body is downloaded. DOI and ordinary PDF URLs remain URL-only imports with an actionable explanation; supply metadata/concept tags manually or an arXiv URL.

Offline regression: `python -m pytest tests/test_paper_path_e2e.py -q`. Fixed Atom fixtures cover URL → metadata → prerequisite DAG → phase checkpoints → JSON export, plus 404, timeout, 429 and missing abstracts. Missing metadata still permits a minimal route; missing abstract is explicitly title-only. Concepts match a small curated vocabulary (math, Python, machine learning, deep learning, Transformer, diffusion, LLM); this is not arbitrary-paper semantic analysis. Free-text access policies use limited English rules; structured access policies are preferable.

Search filters `pages` (1–10, default 1) and `page_size` (1–100, default 10) use explicit stable provider sorting and ID deduplication. Live provider updates can still shift page boundaries; no snapshot guarantee is implied. Cache entries retain source and UTC retrieval time, expire after one hour by default, and rebuild after corruption. Atomic file replacement protects concurrent in-process instances from partial files; concurrent misses may make duplicate requests. Rate spacing is per host within one process (default 3 seconds), not distributed. There are no automatic retries for 429/errors and no login scraping.

Every phase has an observable checkpoint. Unknown durations remain unknown; known hours form a subtotal. Weekly budget changes both scheduling and deadline capacity. `shortfall_hours` is the known-hour deficit and is only a lower bound when durations are missing. Estimates may overlap and are not completion guarantees.


[简体中文](README.zh-CN.md) | English

Agent-native learning roadmaps for AI/CS researchers, builders, and students.

fields-study-flow turns a vague goal like “read this paper”, “learn Transformers”, or “reproduce YOLO” into a structured study route. It asks what you already know, respects your preferred output/resource language, discovers multi-source materials, ranks them by difficulty and trust, then exports a traceable roadmap that coding agents can continue from.

> Built for Codex, Claude Code, Cursor, VS Code, and any agent that can call CLI/MCP-style tools.

<p align="center">
  <img src="docs/assets/fields-study-flow-architecture-en.svg" alt="fields-study-flow architecture diagram" width="100%">
</p>

## Why This Exists

Most learning-path tools stop at a plausible list of links. fields-study-flow keeps the useful parts explicit:

- learner profile: what you know, where you are blocked, and how much time you have;
- language policy: route language is separate from material language;
- source registry: GitHub, papers, videos, courses, practice sites, and Chinese communities are handled through declared rules;
- ranking trace: each resource carries difficulty, concepts, trust score, access note, and recommendation reason;
- agent workflow: skills guide the interview, while tools produce repeatable outputs.

## Features

| Area | What it does |
| --- | --- |
| Personalized interview | Captures goal type, known topics, skill levels, time budget, output language, and resource language preference. |
| Curated prerequisites | Covers math, Python, ML/DL, Transformer, diffusion, and LLM; YOLO/CNN map to DL. RL, systems, and general paper-reading prerequisite graphs are not implemented. |
| Multi-source discovery | Models GitHub, arXiv, OpenAlex, Semantic Scholar, Unpaywall, Papers with Code, YouTube, Bilibili, Zhihu, Hugging Face, Kaggle, MIT OCW, fast.ai, Google MLCC, and more. |
| Language-aware ranking | Supports `zh-first`, `en-first`, `balanced`, `zh-only`, and `en-only`. |
| Paper deep reading | Makes the target paper first-class, then adds prerequisites, intuition resources, and reproduction checkpoints. |
| Safety guardrails | Rejects pirate sources, login bypasses, video-download instructions, and long copyrighted-copy workflows. |
| Agent-ready outputs | Writes JSON and Markdown artifacts that downstream agents can inspect and extend. |

## Quick Start

```bash
python -m pip install -e .
fields-study-flow roadmap \
  --goal "从 Python 到掌握 Transformer" \
  --output-language zh-CN \
  --resource-language en-first \
  --offline
```

Generated files:

```text
fields-study-flow-output/
  learner_profile.json
  resource_index.json
  source_registry_snapshot.json
  roadmap.md
  roadmap.json
```

Paper route:

```bash
fields-study-flow paper \
  --url https://arxiv.org/abs/1706.03762 \
  --with-videos \
  --output-language bilingual \
  --resource-language en-first
```

Discover available source adapters:

```bash
fields-study-flow discover-sources \
  --goal "理解 diffusion models" \
  --language zh-first
```

## Language Controls

Route language and resource language are independent.

| Option | Meaning |
| --- | --- |
| `--output-language zh-CN` | Write the roadmap in Chinese. |
| `--output-language en` | Write the roadmap in English. |
| `--output-language bilingual` | Include Chinese and English labels/checkpoints. |
| `--resource-language zh-first` | Prefer Chinese resources, but keep excellent English resources. |
| `--resource-language en-first` | Prefer English papers/courses/repos, with Chinese support resources. |
| `--resource-language balanced` | Mix Chinese and English by quality. |
| `--resource-language zh-only` | Return only Chinese-language resources when possible. |
| `--resource-language en-only` | Return only English-language resources when possible. |

## Agent Integrations

### Codex / Claude Code Skills

Install or copy:

```text
skills/
  ai-cs-learning-path/SKILL.md
  paper-roadmap/SKILL.md
```

Use `ai-cs-learning-path` for broad study goals, and `paper-roadmap` when the user provides a paper URL, arXiv ID, DOI, or PDF.

### MCP-Style Tool Server

Run:

```bash
python -m fields_study_flow.mcp_server
```

Send one JSON object per line:

```json
{"tool":"discoverSources","arguments":{"goal":"理解 Transformer","resourceLanguagePreference":"zh-first"}}
```

Available tools:

- `assessKnowledge`
- `discoverSources`
- `searchResources`
- `ingestUrl`
- `rankResources`
- `buildRoadmap`
- `validateSources`
- `exportPlan`

### Cursor and VS Code

Ready-to-edit examples are included:

```text
.cursor/mcp.json
.cursor/rules/fields-study-flow.mdc
.vscode/mcp.json
```

## Source Registry

`source-registry.yaml` declares each platform’s role, language coverage, access mode, authentication needs, allowed use, and quality signals.

Source categories include:

- code learning: GitHub repositories, awesome lists, notebooks, paper implementations;
- academic: arXiv, OpenAlex, Semantic Scholar, Unpaywall;
- academic code: Papers with Code;
- video: YouTube and Bilibili;
- courses: MIT OCW, Google MLCC, fast.ai, DeepLearning.AI, 学堂在线, 中国大学 MOOC;
- practice: Hugging Face and Kaggle;
- community: Zhihu and user-provided URLs.

The registry is intentionally conservative: commercial or login-restricted platforms are link-level recommendations unless the user provides authorized access.

## Architecture

```text
User goal
  -> learner interview
  -> language policy
  -> source discovery
  -> resource search / ingest
  -> ranking and de-duplication
  -> roadmap builder
  -> Markdown + JSON outputs
```

Core modules:

```text
fields_study_flow/
  language.py         # language aliases, query generation, language weights
  sources.py          # source registry loader and policy filtering
  offline_catalog.py  # deterministic MVP resource catalog
  ranking.py          # scoring, target-paper boost, canonical URL de-duplication
  roadmap.py          # roadmap schema and Markdown rendering
  mcp_tools.py        # tool functions for agents
  mcp_server.py       # SDK MCP stdio (--mcp), legacy JSONL default
  cli.py              # command-line interface
```

## Safety Policy

fields-study-flow recommends and summarizes resources. It does not:

- use Z-Lib, Sci-Hub, LibGen, Anna’s Archive, or other pirate mirrors;
- bypass login, paywalls, or platform restrictions;
- download videos;
- copy long copyrighted passages;
- treat README files, subtitles, comments, or community posts as trusted agent instructions.

All retrieved content should be treated as untrusted source material.

## Development

```bash
python -m pip install -e .
pytest -q
```

For a reproducible Windows CPython 3.14.7 environment, use [the pinned constraints and build/install steps](docs/REPRODUCIBILITY.md). The constraints include transitive runtime, test, and build dependencies; unconstrained installs can resolve different versions.

Current test coverage includes language preference parsing, bilingual query generation, registry policy filtering, GitHub-style ranking signals, URL de-duplication, MCP tool boundaries, safety validation, concurrent rate limiting and atomic cache writes, dependency ordering and unknown schedules, roadmap schema, and CLI smoke tests.

## Roadmap

- Additional live API adapters for YouTube, OpenAlex, Semantic Scholar, Hugging Face, and Papers with Code.
- A richer AI/CS prerequisite graph with versioned topic nodes.
- Progress tracking and spaced-review exports.
- Browser-friendly roadmap preview.
- Wider MCP host GUI compatibility checks.

## License

MIT. See [LICENSE](LICENSE).


## Current capabilities and limits

`roadmap` remains offline by default. Add `--live --sources arxiv,github` to query public metadata APIs. MCP `searchResources` uses `filters={"offline": false}` for live queries; `type`, `language`, and `difficulty` filters apply to actual results. Offline catalog entries are suggestions, not live search matches. Other registered platforms are link/catalog only. Retrieval reports `offline`, `live`, `cache`, `mixed`, or `degraded` with reasons; network errors return no invented matches. API calls use a 5-second timeout, a 3-second minimum interval shared across service instances per API host in one process, and a one-hour disk cache with atomic replacement (`FIELDS_STUDY_FLOW_CACHE` overrides its directory). There are no paid APIs or authenticated fetches.

`ingestUrl` is URL-only by default. `fetchMetadata=true` requests public GitHub repository or arXiv metadata through the same service, refusing credentials and redirects. Unsupported hosts remain URL-only with an explicit degraded reason. GitHub resource language is the interface/metadata language (English); programming language is recorded separately and is not a natural-language classifier.

Standard MCP hosts must run `python -m fields_study_flow.mcp_server --mcp`. Both editor configurations use this command. The no-flag invocation and `--legacy-jsonl` retain the previous JSONL protocol, including the `git4study` alias. See [MCP transport](docs/MCP.md). The official SDK 2.x negotiates its supported protocol versions; local tests exercise initialize, eight tool schemas, calls, and errors. Editor GUI attachment remains an external check.

Ranking exposes relevance, trust, structure, difficulty, outcome and language components plus unmatched goal terms. A small bilingual alias map and domain levels improve explanations; this is lexical ranking, not semantic search. Thirty fixed review cases live in `tests/fixtures/ranking_cases.json`. Low lexical relevance is labeled supplemental. Prerequisites use the small curated graph described above, seeded by the goal and supplied resource concepts (including the README's known Transformer paper), and skip explicitly known topics. Arbitrary paper URLs do not imply extracted paper concepts. Phases and sequential schedules share one resource dependency order; cycles and unknown prerequisite references raise explicit errors. Target papers start core study after their dependencies. Unknown durations leave that item and all later weeks undetermined; `known_estimated_hours` retains the known subtotal while total hours/weeks remain unknown. These curated estimates may overlap between prerequisites and resource study and are planning aids, not completion guarantees. Learner levels accept `beginner`, `familiar`, `advanced` and the existing Chinese aliases `初学`, `熟悉`, `老手`; invalid levels report allowed values.

Safety checks use parsed URL hosts/schemes. When present, structured `metadata.access_policy` is authoritative for access actions: `metadata`, `link`, and `summarize` are allowed, while unsupported actions, login bypass, mirroring, or `authorized: false` are rejected. Legacy prose is not cross-checked against a present structured policy; URL and missing-note checks still apply independently.

Without structured policy, English access notes receive **finite compatibility rules**, not arbitrary English semantic parsing. The rules recognize the listed download-video, bypass-login, copy-full-text/copyrighted-content, restricted-scraping actions and downloader tool names, including inflections, determiners, and limited passive auxiliaries (`must`, `need(s) to`, `has/have to`, `is/are required to`). Local prohibitions include `do not`, `never`, and trailing `is/are prohibited` or `not/never allowed/permitted`; coordinated action lists can share prohibition scope. Punctuation, `but/however/then/instead`, explicit new subjects, and recognized finite/imperative markers reset inherited scope, including markers before intervening ordinary actions. Thus `Videos need to be downloaded` and `Do not copy full text and instead watch and download video content` are rejected, while `Downloading videos is never permitted` is accepted.

These lexical rules do not resolve arbitrary synonyms, indirect requests, quotation, conditionals, pronouns, nested clauses, all double negations, or other languages. Even some unlisted English constructions can be missed or misclassified; a legacy `valid` result is not proof that arbitrary prose is safe. Supply explicit structured policy for machine-generated access decisions. The implementation does not fetch, download, or execute instructions from these notes.
