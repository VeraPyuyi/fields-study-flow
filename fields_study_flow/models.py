from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from fields_study_flow.language import ResourceLanguagePreference, normalize_resource_language_preference

VALID_TARGET_KINDS = {"auto", "paper", "field", "course"}
VALID_ROUTE_DEPTHS = {"fastest", "balanced", "complete"}
VALID_LEARNING_STYLES = {"auto", "practical", "theory", "video"}
PRIVATE_PATH_RE = re.compile(r"(?:file://[^\s)\]}\"'<]+|(?<![A-Za-z0-9])[A-Za-z]:[\\/][^)\]}\"'<\r\n]+|/(?:Users|home)/[^)\]}\"'<\r\n]+)")


@dataclass(slots=True)
class LearnerProfile:
    goal: str
    output_language: str = "zh-CN"
    resource_language_preference: ResourceLanguagePreference = ResourceLanguagePreference.BALANCED
    known_topics: list[str] = field(default_factory=list)
    levels: dict[str, str] = field(default_factory=dict)
    weekly_hours: int | None = None
    target_date: str | None = None
    goal_type: str = "skill"
    target_kind: str = "auto"
    route_depth: str = "balanced"
    learning_style: str = "practical"

    def __post_init__(self) -> None:
        self.resource_language_preference = normalize_resource_language_preference(self.resource_language_preference)
        self.target_kind = _normalize_choice(self.target_kind, VALID_TARGET_KINDS, "auto")
        self.route_depth = _normalize_choice(self.route_depth, VALID_ROUTE_DEPTHS, "balanced")
        self.learning_style = _normalize_choice(self.learning_style, VALID_LEARNING_STYLES, "practical")

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["resource_language_preference"] = str(self.resource_language_preference)
        return _sanitize_public_value(data)


@dataclass(slots=True)
class Resource:
    title: str
    url: str
    source: str
    type: str
    language: str = "en"
    difficulty: str = "intermediate"
    prerequisites: list[str] = field(default_factory=list)
    concepts: list[str] = field(default_factory=list)
    estimated_time: str = "unknown"
    estimated_minutes: int | None = None
    learning_key_points: list[str] = field(default_factory=list)
    focus_areas: list[str] = field(default_factory=list)
    critical_path_role: str = "support"
    local_path: str | None = None
    trust_score: float = 0.5
    why_recommended: str = ""
    license_or_access_note: str = "Link-level recommendation. Respect platform terms."
    translation_note: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0

    def to_dict(self, include_private: bool = False) -> dict[str, Any]:
        data = asdict(self)
        if not include_private:
            data = _sanitize_public_value(data)
        if (self.source == "local-library" or self.local_path) and not include_private:
            data["local_path"] = None
            if _contains_private_path(str(data.get("url", ""))):
                data["url"] = _safe_local_url(data)
        return data


def _normalize_choice(value: str | None, allowed: set[str], default: str) -> str:
    normalized = (value or default).strip().lower().replace("_", "-")
    aliases = {
        "field-study": "field",
        "topic": "field",
        "skill": "field",
        "paper-roadmap": "paper",
        "coursework": "course",
        "shortest": "fastest",
        "fast": "fastest",
        "full": "complete",
        "comprehensive": "complete",
        "practice": "practical",
        "implementation": "practical",
        "hands-on": "practical",
        "theoretical": "theory",
        "videos": "video",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in allowed else default


def _sanitize_public_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for child_key, child_value in value.items():
            if child_key == "local_path":
                sanitized[child_key] = None
            elif child_key == "url" and isinstance(child_value, str) and _contains_private_path(child_value):
                sanitized[child_key] = _safe_local_url(value)
            else:
                sanitized[child_key] = _sanitize_public_value(child_value)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_public_value(item) for item in value]
    if isinstance(value, str):
        return _redact_private_paths(value)
    return value


def _contains_private_path(value: str) -> bool:
    return bool(PRIVATE_PATH_RE.search(value))


def _redact_private_paths(value: str) -> str:
    if not _contains_private_path(value):
        return value
    return PRIVATE_PATH_RE.sub("[private local path]", value)


def _safe_local_url(resource: dict[str, Any]) -> str:
    metadata = resource.get("metadata")
    local_id = metadata.get("local_resource_id") if isinstance(metadata, dict) else None
    slug_source = local_id or resource.get("title") or "private-resource"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", str(slug_source)).strip("-").lower()
    return f"local://{slug or 'private-resource'}"


@dataclass(slots=True)
class Source:
    id: str
    name: str
    category: str
    languages: list[str]
    access_mode: str
    auth_required: bool
    allowed_use: str
    quality_signals: list[str] = field(default_factory=list)
    restricted: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
