# MCP Integration

`git4study.mcp_tools` contains pure Python functions that can be wrapped by an MCP host.

For local experiments, `python -m git4study.mcp_server` runs a JSON-lines tool process. Each line should be:

```json
{"tool":"searchResources","arguments":{"query":"Transformer derivation","languagePreference":"en-first"}}
```

The process returns:

```json
{"ok":true,"result":{}}
```

The JSON-lines server is intentionally small and deterministic. Production MCP packaging can map the same functions onto a full MCP SDK server without changing the tool behavior.
