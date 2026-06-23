from __future__ import annotations

from pathlib import Path


USER_FACING_DOCS = (
    Path("README.md"),
    Path("README.zh-CN.md"),
    Path("docs/COMPETITIVE_NOTES.md"),
    Path("docs/MARKET_POSITIONING_2026.md"),
    Path("docs/MCP.md"),
)


def test_user_facing_docs_do_not_use_decorative_ellipsis_placeholders() -> None:
    for path in USER_FACING_DOCS:
        assert path.exists(), f"{path} should exist and be checked"
        text = path.read_text(encoding="utf-8")
        assert "..." not in text, f"{path} should use explicit placeholders instead of ..."
        assert "…" not in text, f"{path} should not use decorative ellipsis"
