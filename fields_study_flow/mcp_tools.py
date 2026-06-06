from __future__ import annotations

from pathlib import Path
from typing import Any

from fields_study_flow.language import (
    build_language_queries,
    normalize_output_language,
    normalize_resource_language_preference,
)
from fields_study_flow.artifact_templates import write_artifact_template
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.live_search import search_live_resources
from fields_study_flow.local_resources import analyze_local_resources
from fields_study_flow.offline_catalog import offline_resources_for_goal
from fields_study_flow.paper_metadata import paper_metadata_to_resource, resolve_paper_metadata
from fields_study_flow.ranking import rank_resources
from fields_study_flow.roadmap import build_roadmap, render_html, render_markdown, render_svg, sanitize_roadmap_for_export
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
        "sources": [source.to_dict() for source in sources],
    }


def searchResources(
    query: str,
    sources: list[str] | None = None,
    filters: dict[str, Any] | None = None,
    languagePreference: str = "balanced",
    localResourcePaths: list[str] | None = None,
    liveSearch: bool = True,
) -> dict[str, Any]:
    allowed_sources = set(sources or [])
    resources = offline_resources_for_goal(query)
    live_diagnostics: dict[str, Any] = {"enabled": False, "status": "not_requested"}
    if liveSearch:
        try:
            live_resources, live_diagnostics = search_live_resources(query, sources=sources, language_preference=languagePreference)
            resources.extend(live_resources)
        except Exception as exc:
            live_diagnostics = {"enabled": True, "status": "fallback", "errors": [str(exc)], "manual_link_only_sources": [], "queried_sources": []}
    if allowed_sources:
        resources = [resource for resource in resources if resource.source in allowed_sources or resource.source.replace("-", "_") in allowed_sources]
    if localResourcePaths:
        resources.extend(analyze_local_resources(localResourcePaths, query))
    profile = LearnerProfile(
        goal=query,
        resource_language_preference=normalize_resource_language_preference(languagePreference),
    )
    resources = rank_resources(resources, profile)
    return {
        "queries": build_language_queries(query, languagePreference),
        "filters": filters or {},
        "live_search": live_diagnostics,
        "resources": [resource.to_dict() for resource in resources],
    }


def analyzeLocalResources(
    paths: list[str],
    goal: str,
    learnerProfile: dict[str, Any] | None = None,
    languagePreference: str = "balanced",
    maxFiles: int = 30,
) -> dict[str, Any]:
    profile = _profile_from_dict({**(learnerProfile or {}), "goal": goal})
    profile.resource_language_preference = normalize_resource_language_preference(languagePreference)
    resources = rank_resources(analyze_local_resources(paths, goal, max_files=maxFiles), profile)
    return {
        "goal": goal,
        "paths": [_public_local_path_summary(resource) for resource in resources],
        "shortest_path_policy": "Include local material only when it shortens prerequisite review, core paper understanding, or validation work.",
        "resources": [resource.to_dict() for resource in resources],
    }


def ingestUrl(url: str, sourceHint: str | None = None) -> dict[str, Any]:
    source = sourceHint or _guess_source(url)
    if _looks_like_paper_url(url, source):
        return paper_metadata_to_resource(resolve_paper_metadata(url)).to_dict()
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
    ranked = rank_resources([Resource(**resource) for resource in resources], profile)
    return {"target_outcome": targetOutcome, "resources": [resource.to_dict() for resource in ranked]}


def buildRoadmap(
    goal: str,
    profile: dict[str, Any],
    rankedResources: list[dict[str, Any]],
    outputLanguage: str = "zh-CN",
    routeDepth: str = "balanced",
    learningStyle: str = "practical",
    targetKind: str = "auto",
    liveSearch: dict[str, Any] | None = None,
) -> dict[str, Any]:
    learner = _profile_from_dict(
        {
            **profile,
            "goal": goal,
            "output_language": outputLanguage,
            "route_depth": routeDepth,
            "learning_style": learningStyle,
            "target_kind": targetKind,
        }
    )
    resources = [Resource(**resource) for resource in rankedResources]
    return build_roadmap(learner, resources, live_search=liveSearch)


def validateSources(plan: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    for phase in plan.get("phases", []):
        for resource in phase.get("resources", []):
            url = resource.get("url", "")
            access_note = resource.get("license_or_access_note", "")
            source = resource.get("source", "")
            normalized_url = url.lower()
            normalized_note = access_note.lower()
            if not (url.startswith("http") or (source == "local-library" and (url.startswith("local://") or url.startswith("file:")))):
                issues.append(f"Resource has non-http URL: {resource.get('title')}")
            if any(term in normalized_url for term in DISALLOWED_URL_TERMS):
                issues.append(f"Disallowed source detected: {url}")
            for term in DISALLOWED_ACCESS_NOTE_TERMS:
                if term in normalized_note:
                    issues.append(f"Disallowed access instruction ({term}): {resource.get('title')}")
            if not access_note:
                issues.append(f"Missing access note: {resource.get('title')}")
    return {"valid": not issues, "issues": issues}


def exportPlan(plan: dict[str, Any], outputDir: str) -> dict[str, str]:
    output = Path(outputDir)
    output.mkdir(parents=True, exist_ok=True)
    import json

    public_plan = sanitize_roadmap_for_export(plan)
    json_target = output / "roadmap.json"
    md_target = output / "roadmap.md"
    svg_target = output / "roadmap.svg"
    html_target = output / "roadmap.html"
    json_target.write_text(json.dumps(public_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    md_target.write_text(render_markdown(public_plan), encoding="utf-8")
    svg_target.write_text(render_svg(public_plan), encoding="utf-8")
    html_target.write_text(render_html(public_plan), encoding="utf-8")
    write_artifact_template(output, public_plan)
    result = {"roadmap_json": str(json_target), "roadmap_md": str(md_target), "roadmap_svg": str(svg_target), "roadmap_html": str(html_target)}
    if public_plan.get("generated_artifacts"):
        result["artifact_template"] = str(output / "artifact_template")
    return result


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
        target_kind=data.get("target_kind") or data.get("targetKind") or "auto",
        route_depth=data.get("route_depth") or data.get("routeDepth") or "balanced",
        learning_style=data.get("learning_style") or data.get("learningStyle") or "practical",
    )


def _public_local_path_summary(resource: Resource) -> dict[str, Any]:
    return {
        "local_resource_id": resource.metadata.get("local_resource_id"),
        "path_name": resource.metadata.get("path_name") or resource.title,
        "local_path": None,
    }


def _guess_source(url: str) -> str:
    lowered = url.lower()
    for key in ("github", "youtube", "bilibili", "zhihu", "arxiv", "huggingface", "kaggle"):
        if key in lowered:
            return key
    if "doi.org/" in lowered:
        return "doi"
    return "user-url"


def _looks_like_paper_url(url: str, source: str) -> bool:
    lowered = url.lower()
    return (
        source in {"arxiv", "doi", "semantic-scholar", "openalex", "paper"}
        or "doi.org/" in lowered
        or "arxiv.org/abs/" in lowered
        or "arxiv.org/pdf/" in lowered
        or lowered.endswith(".pdf")
    )
