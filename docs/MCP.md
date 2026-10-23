# MCP transport

Paper workflow: `ingestUrl` → `assessKnowledge` → `rankResources` → `buildRoadmap` → `exportPlan`. Only `fetchMetadata=true` fetches public arXiv/GitHub metadata. arXiv abs/PDF URLs resolve metadata, not PDF contents; DOI/ordinary PDF links degrade to URL-only with `next_action`. HTTP errors/timeouts preserve actionable reasons; missing abstracts remain title-only metadata. Provide concept tags manually when the small math/Python/ML/deep-learning/Transformer/diffusion/LLM prerequisite graph cannot match the title/abstract. Free-text access-policy parsing is limited English rules, not general language understanding.

`searchResources` defaults offline. With `filters.offline=false`, `pages` (1–10) and `page_size` (1–100) control bounded pagination; sorting is explicit and IDs are deduplicated across pages. Mutable upstream results are not a snapshot. Cache source/timestamps survive hits, malformed caches rebuild, and atomic replacement prevents partial reads by concurrent instances. Default TTL is one hour and per-host spacing is three seconds within one process; misses may duplicate requests and errors have no automatic retries. No authenticated scraping is supported.

Roadmap phases include observable `checkpoints`. The schedule retains unknown durations and reports `available_hours`, `shortfall_hours`, and `shortfall_is_lower_bound`; changing profile weekly hours updates both weekly allocation and deadline feasibility. Export preserves these fields in JSON. Offline fixture regression is `python -m pytest tests/test_paper_path_e2e.py -q`.


Install the package, then configure your host to run `python -m fields_study_flow.mcp_server --mcp`. The Cursor and VS Code examples select this mode explicitly. Use the Python interpreter from the environment where the package and its MCP SDK dependency are installed.

The server uses the official MCP Python SDK 2.x `MCPServer` stdio transport. Protocol versions and capabilities are negotiated by that SDK; this project does not implement additional protocol versions. Eight tools expose schemas derived from their existing typed signatures: assessKnowledge, discoverSources, searchResources, ingestUrl, rankResources, buildRoadmap, validateSources, exportPlan. Unknown tools and invalid arguments return SDK tool errors. Logs use stderr; stdout is reserved for protocol messages.

For compatibility, `python -m fields_study_flow.mcp_server --legacy-jsonl` accepts one `{"tool":"assessKnowledge","arguments":{"goal":"python"}}` per line and returns `{"ok":true,"result":...}`. Running without a flag retains this legacy behavior, including `python -m git4study.mcp_server`. JSONL is not MCP. Use `--mcp` for standard hosts.

Run `python -m pytest tests/test_mcp_protocol.py -q` for an actual SDK stdio initialization, tools/list, buildRoadmap call, error cases, legacy subprocess checks and configuration checks. Editor GUI attachment is a separate external check.
