# Git-4-Study Flow

[简体中文](README.zh-CN.md) | English

Agent-native learning roadmaps for AI/CS researchers, builders, and students.

Git-4-Study Flow turns a vague goal like “read this paper”, “learn Transformers”, or “reproduce YOLO” into a structured study route. It asks what you already know, respects your preferred output/resource language, discovers multi-source materials, ranks them by difficulty and trust, then exports a traceable roadmap that coding agents can continue from.

> Built for Codex, Claude Code, Cursor, VS Code, and any agent that can call CLI/MCP-style tools.

## Why This Exists

Most learning-path tools stop at a plausible list of links. Git-4-Study Flow keeps the useful parts explicit:

- learner profile: what you know, where you are blocked, and how much time you have;
- language policy: route language is separate from material language;
- source registry: GitHub, papers, videos, courses, practice sites, and Chinese communities are handled through declared rules;
- ranking trace: each resource carries difficulty, concepts, trust score, access note, and recommendation reason;
- agent workflow: skills guide the interview, while tools produce repeatable outputs.

## Features

| Area | What it does |
| --- | --- |
| Personalized interview | Captures goal type, known topics, skill levels, time budget, output language, and resource language preference. |
| AI/CS taxonomy | Seeds routes with math, programming, ML/DL, LLM, RL, systems, and paper-reading prerequisites. |
| Multi-source discovery | Models GitHub, arXiv, OpenAlex, Semantic Scholar, Unpaywall, Papers with Code, YouTube, Bilibili, Zhihu, Hugging Face, Kaggle, MIT OCW, fast.ai, Google MLCC, and more. |
| Language-aware ranking | Supports `zh-first`, `en-first`, `balanced`, `zh-only`, and `en-only`. |
| Paper deep reading | Makes the target paper first-class, then adds prerequisites, intuition resources, and reproduction checkpoints. |
| Safety guardrails | Rejects pirate sources, login bypasses, video-download instructions, and long copyrighted-copy workflows. |
| Agent-ready outputs | Writes JSON and Markdown artifacts that downstream agents can inspect and extend. |

## Quick Start

```bash
python -m pip install -e .
python -m git4study.cli roadmap \
  --goal "从 Python 到掌握 Transformer" \
  --output-language zh-CN \
  --resource-language en-first \
  --offline
```

Generated files:

```text
git4study-output/
  learner_profile.json
  resource_index.json
  source_registry_snapshot.json
  roadmap.md
  roadmap.json
```

Paper route:

```bash
python -m git4study.cli paper \
  --url https://arxiv.org/abs/1706.03762 \
  --with-videos \
  --output-language bilingual \
  --resource-language en-first
```

Discover available source adapters:

```bash
python -m git4study.cli discover-sources \
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
python -m git4study.mcp_server
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
.cursor/rules/git4study.mdc
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
git4study/
  language.py         # language aliases, query generation, language weights
  sources.py          # source registry loader and policy filtering
  offline_catalog.py  # deterministic MVP resource catalog
  ranking.py          # scoring, target-paper boost, canonical URL de-duplication
  roadmap.py          # roadmap schema and Markdown rendering
  mcp_tools.py        # tool functions for agents
  mcp_server.py       # simple JSON-lines tool server
  cli.py              # command-line interface
```

## Safety Policy

Git-4-Study Flow recommends and summarizes resources. It does not:

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

Current test coverage includes language preference parsing, bilingual query generation, registry policy filtering, GitHub-style ranking signals, URL de-duplication, MCP tool boundaries, safety validation, roadmap schema, and CLI smoke tests.

## Roadmap

- Live official API adapters for GitHub, YouTube, OpenAlex, Semantic Scholar, Hugging Face, and Papers with Code.
- A richer AI/CS prerequisite graph with versioned topic nodes.
- Progress tracking and spaced-review exports.
- Browser-friendly roadmap preview.
- Full MCP SDK packaging.

## License

MIT. See [LICENSE](LICENSE).
