from __future__ import annotations

from pathlib import Path
from typing import Any

from fields_study_flow.language import (
    build_language_queries,
    normalize_output_language,
    normalize_resource_language_preference,
)
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.offline_catalog import offline_resources_for_goal
from fields_study_flow.ranking import rank_resources
from fields_study_flow.roadmap import build_roadmap
from fields_study_flow.sources import SourceRegistry

DISALLOWED_URL_TERMS = (
    "z-lib",
    "zlibrary",
    "sci-hub",
    "scihub",
    "libgen",
    "annas-archive",
    "annasarchive",
    "anna-archive",
)

DISALLOWED_ACCESS_NOTE_TERMS = (
    "download video",
    "yt-dlp",
    "youtube-dl",
    "bypass login",
    "copy full text",
    "copy long copyrighted",
    "scrape restricted",
)


def assessKnowledge(
    goal: str,
    knownTopics: list[str] | None = None,
    confidenceLevels: dict[str, str] | None = None,
    timeBudget: dict[str, Any] | None = None,
    outputLanguage: str = "zh-CN",
    resourceLanguagePreference: str = "balanced",
) -> dict[str, Any]:
    profile = LearnerProfile(
        goal=goal,
        output_language=normalize_output_language(outputLanguage),
        resource_language_preference=normalize_resource_language_preference(resourceLanguagePreference),
        known_topics=knownTopics or [],
        levels=confidenceLevels or {},
        weekly_hours=(timeBudget or {}).get("weekly_hours"),
        target_date=(timeBudget or {}).get("target_date"),
    )
    return profile.to_dict()


def discoverSources(
    goal: str,
    outputLanguage: str = "zh-CN",
    resourceLanguagePreference: str = "balanced",
    region: str = "global-cn",
    sourcePolicy: str = "open",
) -> dict[str, Any]:
    registry = SourceRegistry.default()
    sources = registry.discover(language_preference=resourceLanguagePreference, source_policy=sourcePolicy)
    return {
        "goal": goal,
        "output_language": normalize_output_language(outputLanguage),
        "resource_language_preference": str(normalize_resource_language_preference(resourceLanguagePreference)),
        "region": region,
        "sources": [{**source.to_dict(), "adapter_status": "implemented" if source.id in {"arxiv", "github"} else "link-only"} for source in sources],
    }


def searchResources(
    query: str,
    sources: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    languagePreference: str = "balanced",
) -> dict[str, Any]:
    from fields_study_flow.sources_adapters import SearchService
    options = filters or {}
    result = SearchService().search(query, sources, options, offline=options.get('offline', True))
    resources = [Resource(**resource) for resource in result['resources']]
    profile = LearnerProfile(
        goal=query,
        resource_language_preference=normalize_resource_language_preference(languagePreference),
    )
    resources = rank_resources(resources, profile)
    return {
        **result,
        "queries": build_language_queries(query, languagePreference),
        "filters": filters or {},
        "resources": [resource.to_dict() for resource in resources],
    }


def ingestUrl(url: str, sourceHint: str | None = None, fetchMetadata: bool = False) -> dict[str, Any]:
    degraded = 'Metadata fetch not requested; URL-only import'
    if fetchMetadata:
        from fields_study_flow.sources_adapters import SearchService
        try:
            return SearchService().ingest(url)
        except (OSError, ValueError, KeyError) as exc:
            degraded = f'{type(exc).__name__}: {exc}'
    source = sourceHint or _guess_source(url)
    return Resource(
        title=url.rstrip("/").split("/")[-1] or url,
        url=url,
        source=source,
        type="link",
        language="unknown",
        difficulty="intermediate",
        concepts=[],
        trust_score=0.45,
        license_or_access_note="User-provided URL. Parse metadata only; do not bypass login or copy long content.",
        metadata={"access_policy": {"action": "metadata", "bypass_login": False}, "retrieval_mode": "degraded" if fetchMetadata else "offline", "degraded": degraded},
    ).to_dict()


def rankResources(
    resources: list[dict[str, Any]],
    learnerProfile: dict[str, Any],
    targetOutcome: str = "understand",
    languagePreference: str | None = None,
) -> dict[str, Any]:
    profile = _profile_from_dict(learnerProfile)
    if languagePreference:
        profile.resource_language_preference = normalize_resource_language_preference(languagePreference)
    ranked = rank_resources([Resource(**resource) for resource in resources], profile, target_outcome=targetOutcome)
    return {"target_outcome": targetOutcome, "resources": [resource.to_dict() for resource in ranked]}


def buildRoadmap(
    goal: str,
    profile: dict[str, Any],
    rankedResources: list[dict[str, Any]],
    outputLanguage: str = "zh-CN",
) -> dict[str, Any]:
    learner = _profile_from_dict({**profile, "goal": goal, "output_language": outputLanguage})
    resources = [Resource(**resource) for resource in rankedResources]
    return build_roadmap(learner, resources)


def validateSources(plan: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    for phase in plan.get("phases", []):
        for resource in phase.get("resources", []):
            url = resource.get("url", "")
            access_note = resource.get("license_or_access_note", "")
            from urllib.parse import urlsplit
            import re

            parsed = urlsplit(url)
            host = (parsed.hostname or '').lower()
            if parsed.scheme.lower() not in {'http', 'https'} or not host or parsed.username or parsed.password:
                issues.append(f"Resource has unsafe URL: {resource.get('title')}")
            if any(term in host for term in DISALLOWED_URL_TERMS):
                issues.append(f"Disallowed source detected: {url}")
            policy = resource.get('metadata', {}).get('access_policy')
            if policy is not None:
                if (policy.get('action', 'metadata') not in {'metadata', 'link', 'summarize'}
                        or policy.get('bypass_login') or policy.get('mirror') or policy.get('authorized') is False):
                    issues.append(f"Disallowed access policy: {resource.get('title')}")
            else:
                # Legacy records encoded operations in notes. Ignore explicitly negated clauses;
                # structured records never infer operations from explanatory prose.
                for clause in re.split(r'[.;]', access_note.lower()):
                    if re.search(r'\b(do not|don.t|never|must not)\b', clause):
                        continue
                    for term in DISALLOWED_ACCESS_NOTE_TERMS:
                        if term in clause:
                            issues.append(f"Disallowed access instruction ({term}): {resource.get('title')}")
            if not access_note:
                issues.append(f"Missing access note: {resource.get('title')}")
    return {"valid": not issues, "issues": issues}


def exportPlan(plan: dict[str, Any], outputDir: str) -> dict[str, str]:
    output = Path(outputDir)
    output.mkdir(parents=True, exist_ok=True)
    target = output / "roadmap.json"
    import json

    target.write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"roadmap_json": str(target)}


def _profile_from_dict(data: dict[str, Any]) -> LearnerProfile:
    return LearnerProfile(
        goal=data.get("goal", ""),
        output_language=normalize_output_language(data.get("output_language") or data.get("outputLanguage") or "zh-CN"),
        resource_language_preference=normalize_resource_language_preference(
            data.get("resource_language_preference") or data.get("resourceLanguagePreference") or "balanced"
        ),
        known_topics=data.get("known_topics") or data.get("knownTopics") or [],
        levels=data.get("levels") or data.get("confidenceLevels") or {},
        weekly_hours=data.get("weekly_hours"),
        target_date=data.get("target_date"),
        goal_type=data.get("goal_type", "skill"),
    )


def _guess_source(url: str) -> str:
    lowered = url.lower()
    for key in ("github", "youtube", "bilibili", "zhihu", "arxiv", "huggingface", "kaggle"):
        if key in lowered:
            return key
    return "user-url"
