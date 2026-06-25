# MCP Integration

`fields_study_flow.mcp_tools` exposes pure Python functions that can be wrapped by an MCP host. The tools now use the same unified planner as the CLI, so paper mastery and field/course learning share route depth, learning style, mastery graph, final artifact, and export behavior.

For local experiments:

```bash
python -m fields_study_flow.mcp_server
```

Each stdin line should be one JSON object:

```json
{"tool":"searchResources","arguments":{"query":"Transformer derivation","languagePreference":"en-first"}}
```

## Common Calls

Search resources. Live open-source discovery is enabled by default and falls back to the offline catalog when network/API calls fail:

```json
{"tool":"searchResources","arguments":{"query":"master Transformer paper","languagePreference":"en-first"}}
```

Disable live search for deterministic runs:

```json
{"tool":"searchResources","arguments":{"query":"master Transformer paper","languagePreference":"en-first","liveSearch":false}}
```

Analyze explicit local files/folders:

```json
{"tool":"analyzeLocalResources","arguments":{"goal":"master Transformer paper","paths":["./my-notes/transformer"],"languagePreference":"en-first"}}
```

Build a unified roadmap:

```json
{
  "tool": "buildRoadmap",
  "arguments": {
    "goal": "build a diffusion model project",
    "profile": {"output_language": "en"},
    "rankedResources": [],
    "outputLanguage": "en",
    "routeDepth": "balanced",
    "learningStyle": "practical",
    "targetKind": "field"
  }
}
```

Export a generated plan:

```json
{"tool":"exportPlan","arguments":{"plan":{},"outputDir":"./fields-study-flow-output"}}
```

`exportPlan` writes:

- `roadmap.json`
- `roadmap.md`
- `roadmap.svg`
- `index.html`
- `roadmap.html`
- `artifact_template/` when `generated_artifacts` is present in the plan

Before writing shareable files, `exportPlan` sanitizes private values: `local_path` is cleared, `file://` URLs become redacted `local://` references, and private absolute paths embedded in notes are replaced.

After any CLI or MCP export, run the local quality gate when checking visual regressions:

```bash
fields-study-flow audit-report --report-dir ./fields-study-flow-output
python -m pip install -e ".[visual]"
python -m playwright install chromium
fields-study-flow audit-report --report-dir ./fields-study-flow-output --capture-screenshots
fields-study-flow audit-report --report-dir ./fields-study-flow-output --probe-interactions
fields-study-flow audit-report --report-dir ./fields-study-flow-output --snapshot-baseline docs/visual-baselines/demo.manifest.json
fields-study-flow audit-report --report-dir ./fields-study-flow-output --write-fresh-user-worksheet
fields-study-flow audit-report --report-dir ./fields-study-flow-output --fresh-user-minutes 8.5
fields-study-flow audit-report --report-dir ./fields-study-flow-output --fresh-user-worksheet-input ./fields-study-flow-output/fresh_user_test.md --write-fresh-user-backlog
fields-study-flow audit-report --report-dir ./fields-study-flow-output --fresh-user-backlog-input ./fields-study-flow-output/fresh_user_backlog.md --write-fresh-user-trend-report
fields-study-flow audit-report --report-dir ./fields-study-flow-output --capture-screenshots --probe-interactions --fresh-user-backlog-input ./fields-study-flow-output/fresh_user_backlog.md --write-fresh-user-trend-report --write-release-readiness --write-release-history
```

The audit checks exported HTML for private path leaks, mobile viewport metadata, long-text wrapping safeguards, width constraints, font stacks, and key product affordances such as the start page, Paper Map density controls, Paper Lens evidence, and roadmap mastery checklist. The optional screenshot flag writes desktop/mobile captures under `visual-snapshots/` when Playwright/Chromium is installed, or reports a skipped browser check when the optional runtime is unavailable. `--probe-interactions` opens the offline HTML in the same optional browser runtime and smoke-tests Paper Map branch expansion, node detail updates, zoom/pan behavior, Paper Lens paragraph selection, and roadmap resource filtering. `--snapshot-baseline` compares current screenshot metadata with a saved golden manifest and exits nonzero when a required page, viewport, dimension, or screenshot hash changes. `--write-fresh-user-worksheet` writes `fresh_user_test.md` so reviewers can record checkpoints and blockers. `--fresh-user-minutes` records a measured first-run time-to-first-mastery-task and fails when it exceeds the default 10-minute target, unless `--fresh-user-target-minutes` is set. `--fresh-user-worksheet-input` plus `--write-fresh-user-backlog` aggregates filled worksheets into `fresh_user_backlog.md`, ranking repeated blockers first. `--fresh-user-backlog-input` plus `--write-fresh-user-trend-report` aggregates backlog files into `fresh_user_trends.md`, highlighting blockers that recur across releases or report variants. `--write-release-readiness` writes `release_readiness.md` and `release_readiness.html`, human-readable ship / needs_work / do_not_ship dashboards that combine market readiness, visual QA, screenshots, browser interactions, timing, recurring blockers, and competitor-inspired gates. `--write-release-history` appends a sanitized decision entry to `release_readiness_history.jsonl` and rewrites `release_readiness_history.md` plus `release_readiness_history.html` with trend, score-delta, and recurring-blocker-delta summaries so CI or reviewers can compare quality across runs without opening every HTML report. The report start page and release-readiness dashboard receive idempotent quality-trend entries that link to the HTML history dashboard. When release dashboards are generated, the JSON output also includes `generated_artifact_audit`, a same-run audit pass over the newly written HTML pages. Export also writes `report_audit.json` with market-readiness, experience-risk, viewport-risk, and competitor-benchmark gates, including NotebookLM-style portable study outputs such as presentation notes, concise reading exports, and mastery artifacts.

`buildRoadmap` returns route-level evidence fields in addition to phases:

- `study_tasks`: explain/derive/reproduce/critique or field synthesis tasks, each with evidence and supporting resources
- `next_actions`: the first concrete steps a learner should take
- `route_audit`: coverage, omitted resources, time saved, and the shortest-path claim
- `quality_report`: usefulness, usability, convenience, novelty, and completeness gates with evidence
- `artifact_requirements`: whether a runnable artifact is required and how it is satisfied

The template package contains a README, task checklist, reproduction log, notebook skeleton, and minimal Python entrypoint. It means no target-aligned runnable resource was found; the learner still needs to fill in the implementation and evidence.
When paper metadata includes keywords, formula candidates, code links, method hints, experiment hints, or limitation hints, the template package turns those into concrete acceptance targets. The template text follows the plan's selected output language.

## Tool List

- `assessKnowledge`
- `discoverSources`
- `searchResources`
- `analyzeLocalResources`
- `ingestUrl`
- `rankResources`
- `buildRoadmap`
- `validateSources`
- `exportPlan`

The JSON-lines server intentionally stays small. Production MCP packaging can map these functions onto a full MCP SDK server without changing the tool semantics.
