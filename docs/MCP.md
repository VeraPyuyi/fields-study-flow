# MCP transport

Install the package, then configure your host to run `python -m fields_study_flow.mcp_server --mcp`. The Cursor and VS Code examples select this mode explicitly. Use the Python interpreter from the environment where the package and its MCP SDK dependency are installed.

The server uses the official MCP Python SDK 2.x `MCPServer` stdio transport. Protocol versions and capabilities are negotiated by that SDK; this project does not implement additional protocol versions. Eight tools expose schemas derived from their existing typed signatures: assessKnowledge, discoverSources, searchResources, ingestUrl, rankResources, buildRoadmap, validateSources, exportPlan. Unknown tools and invalid arguments return SDK tool errors. Logs use stderr; stdout is reserved for protocol messages.

For compatibility, `python -m fields_study_flow.mcp_server --legacy-jsonl` accepts one `{"tool":"assessKnowledge","arguments":{"goal":"python"}}` per line and returns `{"ok":true,"result":...}`. Running without a flag retains this legacy behavior, including `python -m git4study.mcp_server`. JSONL is not MCP. Use `--mcp` for standard hosts.

Run `python -m pytest tests/test_mcp_protocol.py -q` for an actual SDK stdio initialization, tools/list, buildRoadmap call, error cases, legacy subprocess checks and configuration checks. Editor GUI attachment is a separate external check.
