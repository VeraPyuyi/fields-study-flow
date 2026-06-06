from __future__ import annotations

import math
import re
from urllib.parse import urlparse

from fields_study_flow.language import language_weight
from fields_study_flow.models import LearnerProfile, Resource


DIFFICULTY_ORDER = {
    "beginner": 0,
    "introductory": 0,
    "intermediate": 1,
    "advanced": 2,
    "expert": 3,
}


def rank_resources(resources: list[Resource], profile: LearnerProfile) -> list[Resource]:
    scored: list[Resource] = []
    for resource in resources:
        language_multiplier = language_weight(resource.language, profile.resource_language_preference)
        if language_multiplier == 0:
            continue
        _complete_learning_fields(resource)
        resource.score = round(_base_score(resource, profile) * language_multiplier, 4)
        resource.why_recommended = resource.why_recommended or _recommendation_reason(resource, profile)
        resource.translation_note = resource.translation_note or _translation_note(resource, profile.output_language)
        scored.append(resource)
    return _dedupe_by_url(sorted(scored, key=lambda item: item.score, reverse=True))


def _base_score(resource: Resource, profile: LearnerProfile) -> float:
    concept_score = _concept_match_score(resource, profile)
    trust_score = max(0.0, min(1.0, resource.trust_score))
    structure_score = _structure_score(resource)
    difficulty_score = _difficulty_fit(resource, profile)
    time_score = _time_fit(resource, profile)
    style_score = _learning_style_fit(resource, profile)
    freshness_score = 0.08 if resource.metadata.get("recently_updated") else 0.0
    target_paper_score = 0.35 if resource.metadata.get("target_paper") else 0.0
    local_shortcut_score = 0.16 if resource.metadata.get("local_availability") and resource.metadata.get("candidate_decision") == "critical-path-candidate" else 0.0

    return (
        0.36 * concept_score
        + 0.22 * trust_score
        + 0.16 * structure_score
        + 0.14 * difficulty_score
        + 0.10 * time_score
        + 0.08 * style_score
        + freshness_score
        + target_paper_score
        + local_shortcut_score
    )


def _concept_match_score(resource: Resource, profile: LearnerProfile) -> float:
    goal_terms = _tokenize(profile.goal)
    concept_terms = set()
    for concept in resource.concepts:
        concept_terms.update(_tokenize(concept))
    title_terms = _tokenize(resource.title)
    all_terms = concept_terms | title_terms
    if not goal_terms:
        return 0.4
    overlap = len(goal_terms & all_terms) / max(1, len(goal_terms))
    return min(1.0, 0.25 + overlap)


def _structure_score(resource: Resource) -> float:
    score = 0.2
    metadata = resource.metadata
    if metadata.get("has_curriculum"):
        score += 0.35
    if metadata.get("has_notebooks"):
        score += 0.2
    if metadata.get("has_exercises"):
        score += 0.15
    if metadata.get("has_official_docs"):
        score += 0.15
    if resource.learning_key_points:
        score += 0.12
    if resource.focus_areas:
        score += 0.08
    if metadata.get("stars"):
        score += min(0.12, math.log10(max(1, float(metadata["stars"]))) / 50)
    return min(score, 1.0)


def _difficulty_fit(resource: Resource, profile: LearnerProfile) -> float:
    level_values = set(profile.levels.values())
    if "beginner" in level_values or "初学" in level_values:
        target = 0
    elif "familiar" in level_values or "熟悉" in level_values:
        target = 1
    elif "advanced" in level_values or "老手" in level_values:
        target = 2
    else:
        target = 1
    resource_level = DIFFICULTY_ORDER.get(resource.difficulty, 1)
    distance = abs(target - resource_level)
    return max(0.2, 1.0 - 0.35 * distance)


def _time_fit(resource: Resource, profile: LearnerProfile) -> float:
    minutes = _estimated_minutes(resource)
    if not minutes:
        return 0.45
    if resource.metadata.get("target_paper"):
        return 0.95
    weekly_minutes = (profile.weekly_hours or 6) * 60
    if minutes <= 60:
        return 1.0
    if minutes <= weekly_minutes / 3:
        return 0.85
    if minutes <= weekly_minutes / 2:
        return 0.68
    if minutes <= weekly_minutes:
        return 0.5
    return 0.28


def _learning_style_fit(resource: Resource, profile: LearnerProfile) -> float:
    style = profile.learning_style
    if style == "auto":
        style = "practical"
    if style == "practical":
        if resource.critical_path_role == "practice-validation" or resource.type in {"repository", "code", "notebook", "practice"}:
            return 1.0
        if resource.metadata.get("target_paper") or resource.type == "paper":
            return 0.85
        return 0.55
    if style == "theory":
        if resource.metadata.get("target_paper") or resource.type in {"paper", "book"}:
            return 1.0
        if resource.critical_path_role == "practice-validation":
            return 0.55
        return 0.75
    if style == "video":
        if resource.type == "video":
            return 1.0
        if resource.type in {"course", "article"}:
            return 0.8
        return 0.55
    return 0.65


def _recommendation_reason(resource: Resource, profile: LearnerProfile) -> str:
    reason = "matches your goal"
    if resource.source == "local-library":
        return "matches your goal and can reuse material already available locally."
    if resource.source == "github" and (resource.metadata.get("has_curriculum") or resource.metadata.get("has_notebooks")):
        reason += " and includes structured code or notebooks"
    elif resource.type == "paper":
        reason += " and anchors the roadmap in primary literature"
    elif resource.type == "video":
        reason += " and gives a lower-friction intuition pass"
    return reason + "."


def _translation_note(resource: Resource, output_language: str) -> str:
    if output_language == "zh-CN" and resource.language.startswith("en"):
        return "Route notes are in Chinese; keep the original English title and use the resource for primary terminology."
    if output_language == "en" and resource.language.startswith("zh"):
        return "Roadmap notes are in English; use this Chinese resource as a regional explanation supplement."
    if output_language == "bilingual":
        return "Keep original title and add bilingual study notes."
    return "No translation needed."


def _tokenize(value: str) -> set[str]:
    normalized = value.lower().replace("/", " ").replace("-", " ")
    tokens = {token.strip(".,:;()[]{}") for token in normalized.split() if token.strip()}
    for keyword in (
        "transformer",
        "diffusion",
        "yolo",
        "ppo",
        "trpo",
        "cnn",
        "python",
        "pddl",
        "planning",
        "symbolic planning",
        "chain of thought",
        "chain-of-thought",
        "planbench",
        "instruction tuning",
    ):
        if keyword in normalized:
            tokens.add(keyword)
    return tokens


def _complete_learning_fields(resource: Resource) -> None:
    minutes = _estimated_minutes(resource)
    if minutes and resource.estimated_minutes is None:
        resource.estimated_minutes = minutes
    if minutes and resource.estimated_time == "unknown":
        resource.estimated_time = _format_minutes(minutes)
    if not resource.learning_key_points:
        resource.learning_key_points = _default_key_points(resource)
    if not resource.focus_areas:
        resource.focus_areas = _default_focus_areas(resource)
    if resource.critical_path_role == "support":
        resource.critical_path_role = _default_role(resource)


def _estimated_minutes(resource: Resource) -> int | None:
    if resource.estimated_minutes:
        return resource.estimated_minutes
    value = resource.estimated_time.lower().strip()
    if not value or value == "unknown":
        return None
    match = re.match(r"^(\d+(?:\.\d+)?)\s*(h|hr|hrs|hour|hours)$", value)
    if match:
        return int(float(match.group(1)) * 60)
    match = re.match(r"^(\d+(?:\.\d+)?)\s*(m|min|mins|minute|minutes)$", value)
    if match:
        return int(float(match.group(1)))
    match = re.match(r"^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*h", value)
    if match:
        return int(float(match.group(2)) * 60)
    return None


def _format_minutes(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}min"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes / 60:.1f}h"


def _default_key_points(resource: Resource) -> list[str]:
    if resource.type == "paper":
        return ["problem setting", "core method", "evidence and limitations"]
    if resource.type in {"repository", "code", "notebook"} or resource.source == "github":
        return ["minimal runnable path", "core implementation", "reproduction checkpoint"]
    if resource.type == "video":
        return ["intuition pass", "main examples", "terms to map back to the paper"]
    return ["definitions", "worked examples", "target-specific notes"]


def _default_focus_areas(resource: Resource) -> list[str]:
    focus = resource.concepts[:4]
    if resource.prerequisites:
        focus.extend(resource.prerequisites[:2])
    if not focus:
        focus = [resource.type, resource.source]
    return list(dict.fromkeys(focus))[:5]


def _default_role(resource: Resource) -> str:
    if resource.metadata.get("target_paper") or resource.type == "paper":
        return "core-paper"
    if resource.type in {"repository", "code", "notebook"} or resource.source in {"github", "local-library"}:
        return "practice-validation" if resource.type in {"repository", "code", "notebook"} else "focused-support"
    if resource.difficulty in {"beginner", "introductory"}:
        return "prerequisite"
    return "focused-support"


def _dedupe_by_url(resources: list[Resource]) -> list[Resource]:
    seen: set[str] = set()
    output: list[Resource] = []
    for resource in resources:
        key = _canonical_url_key(resource.url)
        if key in seen:
            continue
        seen.add(key)
        output.append(resource)
    return output


def _canonical_url_key(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme == "file":
        return f"file:{parsed.path.lower()}"
    if parsed.scheme == "local":
        return f"local:{parsed.netloc.lower()}{parsed.path.lower()}"
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")

    if host == "arxiv.org":
        parts = [part for part in path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"abs", "pdf"}:
            paper_id = parts[1].removesuffix(".pdf")
            paper_id = re.sub(r"v\d+$", "", paper_id)
            return f"arxiv:{paper_id.lower()}"

    if host == "github.com":
        normalized_path = path.removesuffix(".git").lower()
        return f"github:{normalized_path}"

    return f"{host}{path.lower()}"
