from __future__ import annotations

import re
from typing import Any

from defusedxml import ElementTree as ET

from fields_study_flow.models import Resource
from fields_study_flow.sources import SourceRegistry


OPEN_API_SOURCES = {"arxiv", "github", "openalex", "semantic-scholar", "hugging-face"}
MANUAL_ONLY_ACCESS_MARKERS = ("link-only", "url-only")


def search_live_resources(
    query: str,
    sources: list[str] | None = None,
    language_preference: str = "balanced",
    limit: int = 8,
    client: Any | None = None,
    timeout: float = 6.0,
) -> tuple[list[Resource], dict[str, Any]]:
    """Search live, open metadata sources and return rankable resources.

    Credentialed, link-only, and URL-only sources are intentionally reported as
    manual-link-only. This keeps default discovery broad without scraping or
    requiring secrets.
    """

    registry = SourceRegistry.default()
    requested = _requested_sources(registry, sources, language_preference)
    resources: list[Resource] = []
    diagnostics: dict[str, Any] = {
        "enabled": True,
        "status": "ok",
        "queried_sources": [],
        "manual_link_only_sources": [],
        "unsupported_sources": [],
        "errors": [],
    }

    close_client = False
    if client is None:
        try:
            import httpx

            client = httpx.Client(timeout=timeout, follow_redirects=True)
            close_client = True
        except Exception as exc:
            diagnostics["status"] = "fallback"
            diagnostics["errors"].append(f"http_client_unavailable: {exc}")
            return [], diagnostics

    try:
        for source_id in requested:
            source = registry.sources.get(source_id)
            if source is None:
                diagnostics["unsupported_sources"].append(source_id)
                continue
            if source.auth_required or any(marker in source.access_mode for marker in MANUAL_ONLY_ACCESS_MARKERS):
                diagnostics["manual_link_only_sources"].append(source_id)
                continue
            if source_id not in OPEN_API_SOURCES:
                diagnostics["unsupported_sources"].append(source_id)
                continue
            diagnostics["queried_sources"].append(source_id)
            try:
                resources.extend(_search_source(source_id, query, client, max(1, limit // 3), timeout))
            except Exception as exc:
                diagnostics["errors"].append(f"{source_id}: {exc}")
    finally:
        if close_client:
            client.close()

    if diagnostics["errors"] and not resources:
        diagnostics["status"] = "fallback"
    elif diagnostics["errors"]:
        diagnostics["status"] = "partial"
    return resources[:limit], diagnostics


def _requested_sources(registry: SourceRegistry, sources: list[str] | None, language_preference: str) -> list[str]:
    if sources:
        return [source.strip() for source in sources if source.strip()]
    return [source.id for source in registry.discover(language_preference=language_preference, source_policy="open")]


def _search_source(source_id: str, query: str, client: Any, limit: int, timeout: float) -> list[Resource]:
    if source_id == "arxiv":
        return _search_arxiv(query, client, limit, timeout)
    if source_id == "github":
        return _search_github(query, client, limit, timeout)
    if source_id == "openalex":
        return _search_openalex(query, client, limit, timeout)
    if source_id == "semantic-scholar":
        return _search_semantic_scholar(query, client, limit, timeout)
    if source_id == "hugging-face":
        return _search_hugging_face(query, client, limit, timeout)
    return []


def _search_arxiv(query: str, client: Any, limit: int, timeout: float) -> list[Resource]:
    response = client.get(
        "https://export.arxiv.org/api/query",
        params={"search_query": f"all:{query}", "start": 0, "max_results": limit},
        timeout=timeout,
    )
    response.raise_for_status()
    root = ET.fromstring(response.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    resources: list[Resource] = []
    for entry in root.findall("atom:entry", ns):
        title = _clean_text(entry.findtext("atom:title", default="", namespaces=ns))
        url = _clean_text(entry.findtext("atom:id", default="", namespaces=ns))
        summary = _clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
        if title and url:
            resources.append(
                Resource(
                    title=title,
                    url=url,
                    source="arxiv",
                    type="paper",
                    language="en",
                    difficulty="advanced",
                    concepts=_concepts_from_text(f"{title} {summary}"),
                    estimated_time="4h",
                    estimated_minutes=240,
                    trust_score=0.9,
                    license_or_access_note="arXiv metadata and abstract/PDF links. Link and summarize; do not copy long excerpts.",
                    metadata={"live_search": True, "has_official_docs": True},
                )
            )
    return resources


def _search_github(query: str, client: Any, limit: int, timeout: float) -> list[Resource]:
    response = client.get(
        "https://api.github.com/search/repositories",
        params={"q": query, "sort": "stars", "order": "desc", "per_page": limit},
        timeout=timeout,
    )
    response.raise_for_status()
    resources: list[Resource] = []
    for item in response.json().get("items", [])[:limit]:
        title = item.get("full_name") or item.get("name")
        url = item.get("html_url")
        if not title or not url:
            continue
        description = item.get("description") or ""
        resources.append(
            Resource(
                title=title,
                url=url,
                source="github",
                type="repository",
                language="en",
                difficulty="intermediate",
                concepts=_concepts_from_text(f"{title} {description}"),
                estimated_time="6h",
                estimated_minutes=360,
                trust_score=0.72,
                license_or_access_note="Public GitHub repository metadata. Check repository license before reuse.",
                metadata={
                    "live_search": True,
                    "stars": item.get("stargazers_count") or 0,
                    "recently_updated": bool(item.get("updated_at")),
                    "has_curriculum": _looks_like_curriculum(title, description),
                },
            )
        )
    return resources


def _search_openalex(query: str, client: Any, limit: int, timeout: float) -> list[Resource]:
    response = client.get("https://api.openalex.org/works", params={"search": query, "per-page": limit}, timeout=timeout)
    response.raise_for_status()
    resources: list[Resource] = []
    for item in response.json().get("results", [])[:limit]:
        title = item.get("display_name") or ""
        url = item.get("id") or item.get("doi") or ""
        if not title or not url:
            continue
        resources.append(
            Resource(
                title=title,
                url=url,
                source="openalex",
                type="paper",
                language="en",
                difficulty="advanced",
                concepts=[concept.get("display_name", "").lower() for concept in item.get("concepts", [])[:5] if concept.get("display_name")],
                estimated_time="3h",
                estimated_minutes=180,
                trust_score=0.82,
                license_or_access_note="OpenAlex scholarly metadata. Follow open-access links only.",
                metadata={"live_search": True, "citations": item.get("cited_by_count") or 0},
            )
        )
    return resources


def _search_semantic_scholar(query: str, client: Any, limit: int, timeout: float) -> list[Resource]:
    response = client.get(
        "https://api.semanticscholar.org/graph/v1/paper/search",
        params={"query": query, "limit": limit, "fields": "title,url,abstract,citationCount,year,isOpenAccess"},
        timeout=timeout,
    )
    response.raise_for_status()
    resources: list[Resource] = []
    for item in response.json().get("data", [])[:limit]:
        title = item.get("title") or ""
        url = item.get("url") or ""
        if not title or not url:
            continue
        resources.append(
            Resource(
                title=title,
                url=url,
                source="semantic-scholar",
                type="paper",
                language="en",
                difficulty="advanced",
                concepts=_concepts_from_text(f"{title} {item.get('abstract') or ''}"),
                estimated_time="3h",
                estimated_minutes=180,
                trust_score=0.8,
                license_or_access_note="Semantic Scholar metadata and links. Use legal open-access locations only.",
                metadata={"live_search": True, "citations": item.get("citationCount") or 0, "year": item.get("year")},
            )
        )
    return resources


def _search_hugging_face(query: str, client: Any, limit: int, timeout: float) -> list[Resource]:
    response = client.get("https://huggingface.co/api/models", params={"search": query, "limit": limit}, timeout=timeout)
    response.raise_for_status()
    data = response.json()
    resources: list[Resource] = []
    for item in data[:limit] if isinstance(data, list) else []:
        model_id = item.get("modelId") or item.get("id")
        if not model_id:
            continue
        resources.append(
            Resource(
                title=f"Hugging Face: {model_id}",
                url=f"https://huggingface.co/{model_id}",
                source="hugging-face",
                type="practice",
                language="en",
                difficulty="intermediate",
                concepts=_concepts_from_text(model_id),
                estimated_time="2h",
                estimated_minutes=120,
                trust_score=0.68,
                license_or_access_note="Hugging Face model card link. Check model card and license before reuse.",
                metadata={"live_search": True, "downloads": item.get("downloads") or 0, "likes": item.get("likes") or 0},
            )
        )
    return resources


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _concepts_from_text(value: str) -> list[str]:
    normalized = value.lower()
    concepts: list[str] = []
    keywords = {
        "transformer": "transformer",
        "attention": "attention",
        "diffusion": "diffusion models",
        "score": "score matching",
        "yolo": "yolo",
        "ppo": "ppo",
        "reinforcement": "reinforcement learning",
        "language model": "language model",
        "pytorch": "pytorch",
        "python": "python",
    }
    for keyword, concept in keywords.items():
        if keyword in normalized and concept not in concepts:
            concepts.append(concept)
    return concepts[:6] or [token for token in re.split(r"[\s/_-]+", normalized) if len(token) > 4][:4]


def _looks_like_curriculum(title: str, description: str) -> bool:
    text = f"{title} {description}".lower()
    return any(term in text for term in ("course", "tutorial", "notebook", "learn", "reproduce", "from scratch"))
