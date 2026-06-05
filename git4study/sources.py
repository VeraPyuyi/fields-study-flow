from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from git4study.language import normalize_resource_language_preference
from git4study.models import Source

VALID_SOURCE_POLICIES = {"open", "all"}


@dataclass(slots=True)
class SourceRegistry:
    sources: dict[str, Source]

    @classmethod
    def from_yaml(cls, path: Path) -> "SourceRegistry":
        raw = path.read_text(encoding="utf-8")
        data = _load_yaml(raw)
        sources = {
            item["id"]: Source(
                id=item["id"],
                name=item["name"],
                category=item["category"],
                languages=item["languages"],
                access_mode=item["access_mode"],
                auth_required=bool(item.get("auth_required", False)),
                allowed_use=item["allowed_use"],
                quality_signals=item.get("quality_signals", []),
                restricted=bool(item.get("restricted", False)),
                notes=item.get("notes", ""),
            )
            for item in data["sources"]
        }
        return cls(sources=sources)

    @classmethod
    def default(cls) -> "SourceRegistry":
        return cls.from_yaml(default_registry_path())

    def discover(self, language_preference: str = "balanced", source_policy: str = "open") -> list[Source]:
        if source_policy not in VALID_SOURCE_POLICIES:
            raise ValueError(f"Unsupported source policy: {source_policy}. Expected one of: {', '.join(sorted(VALID_SOURCE_POLICIES))}.")
        preference = normalize_resource_language_preference(language_preference)
        output: list[Source] = []
        for source in self.sources.values():
            if source_policy == "open" and source.restricted:
                continue
            if preference == "zh-only" and "zh-CN" not in source.languages:
                continue
            if preference == "en-only" and "en" not in source.languages:
                continue
            output.append(source)
        return output

    def snapshot(self) -> dict[str, Any]:
        return {"sources": [source.to_dict() for source in self.sources.values()]}


def default_registry_path() -> Path:
    return Path(__file__).resolve().parent.parent / "source-registry.yaml"


def _load_yaml(raw: str) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dependency fallback
        import json

        try:
            return json.loads(raw)
        except json.JSONDecodeError as json_exc:
            raise RuntimeError("PyYAML is required for non-JSON source registry files.") from json_exc
    data = yaml.safe_load(raw)
    if not isinstance(data, dict):
        raise ValueError("Source registry must contain a mapping at the top level.")
    return data
