from __future__ import annotations

import tomllib
from pathlib import Path


def test_rag_extra_is_optional_and_declares_fastembed():
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))["project"]

    assert "fastembed" not in " ".join(project["dependencies"]).lower()
    rag_extra = project["optional-dependencies"]["rag"]
    assert any("fastembed" in dependency.lower() for dependency in rag_extra)
    assert any("numpy" in dependency.lower() for dependency in rag_extra)
