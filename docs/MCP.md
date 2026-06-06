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
- `roadmap.html`
- `artifact_template/` when `generated_artifacts` is present in the plan

Before writing shareable files, `exportPlan` sanitizes private values: `local_path` is cleared, `file://` URLs become redacted `local://` references, and private absolute paths embedded in notes are replaced.

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
