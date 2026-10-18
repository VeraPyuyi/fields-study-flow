from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any

from fields_study_flow.language import ResourceLanguagePreference, normalize_resource_language_preference


class KnowledgeLevel(str, Enum):
    BEGINNER = 'beginner'
    FAMILIAR = 'familiar'
    ADVANCED = 'advanced'


LEVEL_ALIASES = {'初学': 'beginner', '熟悉': 'familiar', '老手': 'advanced'}


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
        if not isinstance(self.levels, dict):
            raise ValueError('levels must map domains to beginner, familiar, or advanced')
        for domain, level in self.levels.items():
            try:
                if not isinstance(level, str):
                    raise ValueError('level must be text')
                KnowledgeLevel(LEVEL_ALIASES.get(level, level))
            except ValueError:
                raise ValueError(f'Invalid level {level!r} for {domain!r}; expected beginner, familiar, or advanced (aliases: 初学, 熟悉, 老手)') from None
        import math
        import re
        from datetime import date
        if self.weekly_hours is not None and (isinstance(self.weekly_hours, bool) or not isinstance(self.weekly_hours, (int, float)) or not math.isfinite(self.weekly_hours) or not 0 < self.weekly_hours <= 168):
            raise ValueError('weekly_hours must be a finite number in (0, 168]')
        if self.target_date is not None:
            if not isinstance(self.target_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', self.target_date):
                raise ValueError('target_date must be YYYY-MM-DD')
            date.fromisoformat(self.target_date)

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
    score_components: dict[str, float] = field(default_factory=dict)
    missing_concepts: list[str] = field(default_factory=list)

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
