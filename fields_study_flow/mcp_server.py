from __future__ import annotations

import json
import sys
from typing import Any, Callable

from fields_study_flow import mcp_tools


TOOLS: dict[str, Callable[..., Any]] = {
    "assessKnowledge": mcp_tools.assessKnowledge,
    "discoverSources": mcp_tools.discoverSources,
    "searchResources": mcp_tools.searchResources,
    "ingestUrl": mcp_tools.ingestUrl,
    "rankResources": mcp_tools.rankResources,
    "buildRoadmap": mcp_tools.buildRoadmap,
    "validateSources": mcp_tools.validateSources,
    "exportPlan": mcp_tools.exportPlan,
}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="MCP stdio or legacy JSONL tools")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--mcp", action="store_true", help="Standard MCP SDK stdio transport")
    mode.add_argument("--legacy-jsonl", action="store_true", help="Legacy JSONL (also the compatibility default)")
    args = parser.parse_args()
    if args.mcp:
        from mcp.server.mcpserver import MCPServer

        server = MCPServer("fields-study-flow", version="0.1.0", subscriptions=False)
        for name, tool in TOOLS.items():
            server.add_tool(tool, name=name)
        server.run(transport="stdio")
        return 0
    return legacy_main()


def legacy_main() -> int:
    """Small JSON-lines tool server for local agent integration examples.

    Full MCP hosts can wrap these same tool functions. This process accepts one
    JSON object per line: {"tool": "discoverSources", "arguments": {...}}.
    """

    for line in sys.stdin:
        try:
            request = json.loads(line)
            tool_name = request["tool"]
            arguments = request.get("arguments", {})
            if tool_name not in TOOLS:
                raise KeyError(f"Unknown tool: {tool_name}")
            result = TOOLS[tool_name](**arguments)
            print(json.dumps({"ok": True, "result": result}, ensure_ascii=False), flush=True)
        except Exception as exc:  # pragma: no cover - defensive stdio boundary
            print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
