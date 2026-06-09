# fields-study-flow

[简体中文](README.zh-CN.md) | English

Agent-native mastery-path generator for AI/CS papers, fields, and courses.

fields-study-flow turns goals such as "master this paper", "learn diffusion models", or "reproduce YOLO" into a traceable learning path. It combines learner profile, route depth, language preferences, live open-source discovery, and explicit local resources, then exports Markdown, JSON, SVG, and a polished static HTML report.

<p align="center">
  <img src="docs/assets/fields-study-flow-architecture-en.svg" alt="fields-study-flow architecture diagram" width="100%">
</p>

## What It Optimizes

- Unified dual mode: single-paper mastery and field/course learning share the same planner.
- Mastery standard: explain, derive, reproduce, and critique.
- Route depth: `fastest`, `balanced` default, or `complete`.
- Learning style: practical default, theory, video, or auto.
- Language choice: Markdown, HTML, and SVG reports follow `zh-CN`, `en`, or `bilingual` output language.
- Short routes: `fastest` and practical `balanced` routes compress broad prerequisite courses into a focused prerequisite sprint when that keeps the mastery path shorter.
- Local resources: only explicit user paths are analyzed; private paths are redacted from shareable outputs.
- Paper parsing: local PDFs expose sections, method/experiment/limitation hints, keywords, formula candidates, and code links when detectable.
- Paper Lens: paper routes export `paper_lens.html`, a standalone target-paper reader that maps collected literature, bundle files, evidence snippets, and tasks back onto the target paper's sections.
- Evidence-driven RAG: local resources and study bundles are chunked into a lightweight `.rag_index`; key points, resource reasons, and validation tasks can cite supporting snippets.
- Learning knowledge graph: reports include a local, evidence-driven concept -> resource -> task -> assessment graph for navigation and mastery tracing.
- Live discovery: open official APIs are searched by default; credentialed/link-only sources remain manual-link candidates.
- Route audit: every plan explains coverage, omitted resources, time saved, and why the chosen route is the shortest visible path under the selected depth.
- Actionability: reports include study tasks, next actions, quality gates, final evidence, and runnable artifact enforcement.
- Interactive learning console: `roadmap.html` is the primary report. It includes a draggable/zoomable KG network, a right-side task guide with local progress checks, local-first resource links, multi-dimensional resource filter chips, evidence expand/collapse, and collapsible phases.

## Quick Start

```bash
python -m pip install -e .
fields-study-flow roadmap \
  --goal "learn diffusion models and build a small project" \
  --preset field-project \
  --output-language en \
  --resource-language en-first \
  --local-resource ./my-notes/diffusion \
  --resource-dir ./study-assets/diffusion \
  --bundle-scope all
```

Use deterministic offline mode when you do not want live search:

```bash
fields-study-flow roadmap \
  --goal "master Transformer paper" \
  --no-live-search \
  --local-resource ./my-notes/transformer
```

Paper route:

```bash
fields-study-flow paper \
  --url https://arxiv.org/abs/1706.03762 \
  --preset paper-fastest \
  --output-language bilingual \
  --resource-language en-first \
  --resource-dir ./study-assets/transformer
```

Guided mode asks for language, storage, learning preferences, and `bundle_scope` when a study bundle is enabled:

```bash
fields-study-flow paper --interactive
fields-study-flow roadmap --interactive
```

Generated files:

```text
fields-study-flow-output/
  learner_profile.json
  resource_index.json
  local_resource_analysis.json
  source_registry_snapshot.json
  roadmap.md
  roadmap.json
  roadmap.svg
  roadmap.html            # primary interactive study report
  paper_lens.html         # target-paper reader, generated when a target paper is present
  artifact_template/        # generated only when a runnable artifact is required
    README.md
    task_checklist.md
    reproduction_log.md
    notebook_skeleton.ipynb
    src/main.py

study-assets/
  study_bundle_manifest.json # generated when --resource-dir is set
  README.md                   # bundle summary and how to start
  .rag_index/manifest.json   # generated for evidence retrieval and bundle Q&A
  links.md
  01-selected-local-or-open-resource.pdf
```

When `--resource-dir` is used, downloaded/copied resources in `roadmap.html`, `paper_lens.html`, and `roadmap.md` link to the local study bundle first. Original web links remain visible only as fallback/source links, and absolute local paths are still redacted from shareable outputs.

Ask a question against the downloaded/copied bundle only:

```bash
fields-study-flow ask \
  --roadmap fields-study-flow-output/roadmap.json \
  --resource-dir ./study-assets/diffusion \
  --question "Which evidence explains the reproduction target?"
```

## Key CLI Options

| Option | Meaning |
| --- | --- |
| `--preset fastest\|balanced\|complete\|paper-fastest\|paper-deep\|field-project\|course-complete` | Start from a common planning mode; explicit options can still override it. |
| `--target-kind paper\|field\|course\|auto` | Select or infer the planning mode. |
| `--route-depth fastest\|balanced\|complete` | Control how short or comprehensive the route should be. |
| `--learning-style practical\|theory\|video\|auto` | Bias ranking toward implementation, theory, or intuition resources. |
| `--local-resource PATH` | Analyze an explicit local file/folder as a private candidate. Repeatable. |
| `--resource-dir PATH` | Copy/download the study resource library into a private study folder and write `study_bundle_manifest.json`. |
| `--bundle-scope selected\|all` | Choose whether the bundle downloads only selected route resources or all directly obtainable candidates. Default: `all`; unavailable resources remain in `links.md`. |
| `--rag off\|light\|auto\|embedding` | Control evidence retrieval. `auto` uses lightweight local retrieval; `embedding` uses the optional `rag` extra when installed. |
| `--no-paper-lens` | Skip the standalone `paper_lens.html` reader even when a target paper is present. |
| `--interactive` | Ask for goal, language, route depth, learning style, local resources, output directory, and resource directory before executing. |
| `--no-live-search` / `--offline` | Disable default live discovery and use deterministic local catalog behavior. |
| `--output-language zh-CN\|en\|bilingual` | Control roadmap language. |
| `--resource-language zh-first\|en-first\|balanced\|zh-only\|en-only` | Control material-language preference. |

Supported local resource types include Markdown, TXT, TeX, PDF, Jupyter notebooks, Python files, YAML/JSON/CSV, and common document/slide formats at metadata level. Resource bundling copies only paths the user explicitly provided. With the default `--bundle-scope all`, it attempts every directly obtainable candidate: arXiv PDFs, raw GitHub files, public GitHub archives, and ordinary public-page snapshots when the server allows it. With `--bundle-scope selected`, it keeps the faster shortest-route bundle behavior. Videos, restricted pages, failed downloads, and credentialed sources stay as links in `links.md`, and the manifest records selected/omitted plus downloaded/link-only status.

Embedding retrieval is optional:

```bash
python -m pip install -e .[rag]
```

## MCP-Style Tools

Run the JSON-lines tool server:

```bash
python -m fields_study_flow.mcp_server
```

Example:

```json
{"tool":"searchResources","arguments":{"query":"Transformer derivation","languagePreference":"en-first"}}
```

Available functions:

- `assessKnowledge`
- `discoverSources`
- `searchResources`
- `analyzeLocalResources`
- `ingestUrl`
- `rankResources`
- `buildRoadmap`
- `retrieveEvidence`
- `answerFromBundle`
- `validateSources`
- `exportPlan`

`exportPlan` writes JSON, Markdown, SVG, HTML, `paper_lens.html` when a target paper is present, and the `artifact_template/` package when the route needs a runnable project or reproduction checkpoint.
The template package follows the selected output language and includes paper-derived formula/code/experiment targets when available.

The interactive HTML is a single offline file with no frontend framework or remote font dependency. Task progress is stored in the browser via `localStorage` when available; if the browser blocks local storage, the report still works as a readable, clickable study console and simply treats checkmarks as temporary.

On Windows PowerShell, read exported JSON as UTF-8 when piping to native JSON tools:

```powershell
Get-Content .\fields-study-flow-output\roadmap.json -Raw -Encoding UTF8 | ConvertFrom-Json
```

## Architecture

```text
goal/profile
  -> unified planner options
  -> live discovery + offline catalog + explicit local resources
  -> lightweight RAG chunks + evidence retrieval
  -> lightweight learning knowledge graph
  -> ranking, de-duplication, quality/style weighting
  -> route-depth-aware mastery path
  -> mastery graph + route audit + quality gates + final artifact + checkpoints
  -> Markdown / JSON / SVG / HTML outputs + optional artifact template
```

Core modules:

```text
fields_study_flow/
  live_search.py      # open API discovery with credential-safe fallback
  local_resources.py  # explicit local path analysis
  paper_metadata.py   # arXiv/DOI/local-PDF metadata and fallback extraction
  paper_lens.py       # target-paper reading layer with section evidence and local-first links
  artifact_templates.py # generated verification scaffold when no runnable resource fits
  rag.py              # local evidence chunks, bundle index, retrieval, and bundle Q&A
  knowledge_graph.py  # local concept/resource/task/assessment learning graph
  ranking.py          # quality, language, time, and style scoring
  roadmap.py          # mastery graph, route selection, and renderers
  mcp_tools.py        # agent-callable functions
  cli.py              # command-line interface
```

## Safety Policy

fields-study-flow recommends and summarizes resources. It does not scan local disks by default, expose private local paths in shareable reports, bypass logins or paywalls, download videos, use pirate mirrors, or copy long copyrighted passages. When `--resource-dir` is used, downloaded/copied files are kept in the private local bundle selected by the user. External content is treated as untrusted source material.

## Development

```bash
python -m pip install -e .[dev]
pytest -q
```

MIT. See [LICENSE](LICENSE).
