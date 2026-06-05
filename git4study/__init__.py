"""Backward-compatible import aliases for fields-study-flow."""

from __future__ import annotations

import importlib
import sys

from fields_study_flow import *  # noqa: F401,F403

_ALIASED_MODULES = [
    "language",
    "mcp_tools",
    "models",
    "offline_catalog",
    "ranking",
    "roadmap",
    "sources",
]

for _module_name in _ALIASED_MODULES:
    _module = importlib.import_module(f"fields_study_flow.{_module_name}")
    sys.modules[f"{__name__}.{_module_name}"] = _module
    setattr(sys.modules[__name__], _module_name, _module)
