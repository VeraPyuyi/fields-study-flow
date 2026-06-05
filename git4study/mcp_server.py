"""Compatibility MCP server wrapper for the renamed fields-study-flow package."""

from __future__ import annotations

from fields_study_flow.mcp_server import main


if __name__ == "__main__":
    raise SystemExit(main())
