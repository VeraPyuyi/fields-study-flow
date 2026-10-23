from __future__ import annotations

from pathlib import Path
import re
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

# Bounded legacy-English compatibility, not a general semantic policy parser.
# Match each action/object in either voice, then resolve only local prohibition
# and coordination. Structured metadata.access_policy remains authoritative.
_ACCESS_DETERMINER = r'(?:(?:the|a|an|this|that|these|those|any|all|some|your|their)\s+)*'
_ACCESS_PREDICATE = r'(?:must|should|may|can|cannot|will|shall|is|are|needs?|has|have)'
_ACCESS_NEW_INSTRUCTION = re.compile(r'\b(?:' + _ACCESS_PREDICATE + r'|do|please)\b')
_ACCESS_OBJECTS = (
    (r'download(?:s|ed|ing)?', r'videos?(?:\s+content)?', 'downloaded'),
    (r'bypass(?:es|ed|ing)?', r'login', 'bypassed'),
    (r'(?:copy|copies|copied|copying)', r'(?:full\s+text|long\s+copyrighted(?:\s+(?:content|passages|excerpts))?)', 'copied'),
    (r'scrap(?:e|es|ed|ing)', r'restricted(?:\s+(?:pages|content))?', 'scraped'),
)
_ACCESS_ACTION = re.compile(
    r'\b(?:(?P<active>' + '|'.join(
        verb + r'\s+' + _ACCESS_DETERMINER + obj for verb, obj, _ in _ACCESS_OBJECTS
    ) + r')|(?P<tool>yt-dlp|youtube-dl)|(?P<passive>' + '|'.join(
        obj + r'\s+(?:(?:' + _ACCESS_PREDICATE + r'|be|been|being|not|never|to|required)\s+)+' + participle
        for _, obj, participle in _ACCESS_OBJECTS
    ) + r'))\b'
)
_ACCESS_NEGATION = re.compile(
    r"\b(?:not|never|cannot|no|don't|doesn't|mustn't|shouldn't|can't|won't)\s+"
    r'(?:(?:ever|use|run|to|be|allowed|permitted|attempt|try)\s+)*$'
)
_ACCESS_PREVENTION = re.compile(r'\b(?:avoid\s+|(?:forbidden|prohibited|banned)\s+(?:to|from)\s+)$')
_ACCESS_PROHIBITION = re.compile(
    r'\s+(?:is|are)\s+(?:strictly\s+)?(?:prohibited|forbidden|banned|(?:not|never)\s+(?:allowed|permitted))\b'
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
        metadata={"access_policy": {"action": "metadata", "bypass_login": False}, "retrieval_mode": "degraded" if fetchMetadata else "offline", "degraded": degraded, "next_action": "Check the URL or retry later; supply title, abstract and concept tags manually, or use an arXiv metadata URL. DOI and ordinary PDF parsing are not supported."},
    ).to_dict()


def explainPaper(
    url: str | None = None,
    metadata: dict[str, Any] | None = None,
    userText: list[str] | None = None,
    level: str = 'beginner',
    language: str = 'zh',
) -> dict[str, Any]:
    """Organize candidate evidence for a host-agent explanation; no model calls.

    Supplied metadata/body stays offline. URL-only requests fetch public arXiv
    metadata, never full text. Local files are supported by the CLI only.
    """
    from urllib.parse import urlsplit
    from fields_study_flow.paper_explainer import explain_paper
    if url:
        parsed = urlsplit(url)
        if (parsed.scheme != 'https' or parsed.hostname != 'arxiv.org'
                or parsed.username or parsed.password or parsed.port not in {None, 443}
                or not re.fullmatch(r'/(?:abs|pdf)/(?:\d{4}\.\d{4,5}|[a-z-]+/\d{7})(?:v\d+)?(?:\.pdf)?', parsed.path)
                or parsed.query or parsed.fragment):
            raise ValueError('Only public HTTPS arXiv abs/pdf URLs are supported; supply metadata or userText for other papers')
    if metadata is None and not userText:
        if not url:
            raise ValueError('Supply a paper URL, metadata or userText')
        from fields_study_flow.sources_adapters import SearchService
        resource = SearchService().ingest(url)
        metadata = {**resource['metadata'], 'title': resource['title']}
    return explain_paper(metadata, userText, level, language)


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


def _affirmative_access_actions(note: str) -> list[str]:
    actions = []
    # A fresh subject, modal, or imperative ends inherited negation, even when
    # its subject is omitted ("do not copy ... and must download ...").
    clauses = re.split(
        r'[.;:!?\n]|\b(?:but|however|then|instead)\b|\b(?:and|or)\s+'
        r'(?=(?:you|we|they|he|she|it|one|the|users?|agents?|must|should|may|can|will|shall|do|please)\b)',
        note.lower().replace('’', "'"),
    )
    for clause in clauses:
        matches = list(_ACCESS_ACTION.finditer(clause))
        # Commas share scope only in an action list with an explicit final
        # conjunction. A bare comma still starts an independent instruction.
        list_links = set()
        for index in range(1, len(matches)):
            gap = clause[matches[index - 1].end():matches[index].start()]
            if not re.fullmatch(r'\s*,?\s*\b(?:and|or)\s+', gap):
                continue
            list_links.add(index)
            for earlier in range(index - 1, 0, -1):
                gap = clause[matches[earlier - 1].end():matches[earlier].start()]
                if not re.fullmatch(r'\s*,\s*', gap):
                    break
                list_links.add(earlier)
        negated, previous_end = False, 0
        prohibited = set()
        for index, match in enumerate(matches):
            if not _ACCESS_PROHIBITION.match(clause[match.end():]):
                continue
            prohibited.add(index)
            # A trailing predicate can govern a list of gerunds or tool names.
            # Do not extend it over an imperative or a separate finite clause.
            for earlier in range(index - 1, -1, -1):
                left, right = matches[earlier:earlier + 2]
                same_form = (left.lastgroup == right.lastgroup == 'tool' or
                             (left.group().split()[0].endswith('ing') and
                              right.group().split()[0].endswith('ing')))
                if not same_form or earlier + 1 not in list_links:
                    break
                prohibited.add(earlier)
        for index, match in enumerate(matches):
            before = clause[previous_end:match.start()]
            direct = _ACCESS_NEGATION.search(before)
            prevention = _ACCESS_PREVENTION.search(before)
            if prevention and not _ACCESS_NEGATION.search(before[:prevention.start()]):
                direct = True
            # A passive clause or gerund with its own predicate has its own
            # subject; it cannot inherit the previous action's prohibition.
            own_subject = (match.lastgroup == 'passive' or
                           re.match(r'\s+' + _ACCESS_PREDICATE + r'\b', clause[match.end():]))
            # A finite predicate or imperative marker anywhere in the gap
            # starts a new instruction, even with intervening ordinary actions
            # ("and students must watch and download videos"). Do not infer
            # arbitrary English subjects or verbs; only these explicit markers.
            new_instruction = _ACCESS_NEW_INSTRUCTION.search(before)
            coordinated = (not own_subject and not new_instruction and
                           (index in list_links or (',' not in before and
                            re.search(r'\b(?:and|or)\s+(?:(?:use|run)\s+)?$', before))))
            # An infinitive purpose stays inside the negated action:
            # "do not use yt-dlp / bypass login to download videos".
            purpose = (index > 0 and not own_subject and
                       re.fullmatch(r'\s+to\s+', before))
            passive_negative = (match.lastgroup == 'passive' and
                                re.search(r'\b(?:not|never|cannot)\b', match.group()))
            negated = bool(direct or passive_negative or (negated and (coordinated or purpose)))
            if not negated and index not in prohibited:
                actions.append(match.group())
            previous_end = match.end()
    return actions


def validateSources(plan: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    for phase in plan.get("phases", []):
        for resource in phase.get("resources", []):
            url = resource.get("url", "")
            access_note = resource.get("license_or_access_note", "")
            from urllib.parse import urlsplit

            parsed = urlsplit(url)
            host = (parsed.hostname or '').lower().rstrip('.')
            if parsed.scheme.lower() not in {'http', 'https'} or not host or parsed.username or parsed.password:
                issues.append(f"Resource has unsafe URL: {resource.get('title')}")
            if set(host.split('.')) & set(DISALLOWED_URL_TERMS):
                issues.append(f"Disallowed source detected: {url}")
            policy = resource.get('metadata', {}).get('access_policy')
            if policy is not None:
                if (policy.get('action', 'metadata') not in {'metadata', 'link', 'summarize'}
                        or policy.get('bypass_login') or policy.get('mirror') or policy.get('authorized') is False):
                    issues.append(f"Disallowed access policy: {resource.get('title')}")
            else:
                for term in _affirmative_access_actions(access_note):
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
