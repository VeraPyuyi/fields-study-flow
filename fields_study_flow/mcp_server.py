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
