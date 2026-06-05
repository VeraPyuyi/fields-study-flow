from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from fields_study_flow.language import ResourceLanguagePreference, normalize_resource_language_preference


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

    def __post_init__(self) -> None:
        self.resource_language_preference = normalize_resource_language_preference(self.resource_language_preference)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["resource_language_preference"] = str(self.resource_language_preference)
        return data


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
    trust_score: float = 0.5
    why_recommended: str = ""
    license_or_access_note: str = "Link-level recommendation. Respect platform terms."
    translation_note: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
