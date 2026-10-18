from __future__ import annotations

import math
import re
from urllib.parse import urlparse

from fields_study_flow.concepts import dominant_domain, tokenize as _tokenize
from fields_study_flow.language import language_weight
from fields_study_flow.models import LearnerProfile, Resource


DIFFICULTY_ORDER = {
    "beginner": 0,
    "introductory": 0,
    "intermediate": 1,
    "advanced": 2,
    "expert": 3,
}


def rank_resources(resources: list[Resource], profile: LearnerProfile, target_outcome: str = 'understand') -> list[Resource]:
    scored: list[Resource] = []
    for resource in resources:
        language_multiplier = language_weight(resource.language, profile.resource_language_preference)
        if language_multiplier == 0:
            continue
        relevance = _concept_match_score(resource, profile)
        outcome = 0.2 if (target_outcome in {'reproduce', 'implement', '复现'} and resource.type == 'repository') or (target_outcome in {'derive', '推导'} and resource.type == 'paper') else 0.0
        resource.score_components = {'relevance': relevance, 'trust': max(0., min(1., resource.trust_score)), 'structure': _structure_score(resource), 'difficulty': _difficulty_fit(resource, profile), 'outcome': outcome, 'language': language_multiplier}
        resource.missing_concepts = sorted(_tokenize(profile.goal) - _tokenize(resource.title + ' ' + ' '.join(resource.concepts)))
        resource.score = round((_base_score(resource, profile) + outcome) * language_multiplier, 4)
        resource.why_recommended = _recommendation_reason(resource, profile)
        resource.translation_note = resource.translation_note or _translation_note(resource, profile.output_language)
        scored.append(resource)
    return _dedupe_by_url(sorted(scored, key=lambda item: item.score, reverse=True))


def _base_score(resource: Resource, profile: LearnerProfile) -> float:
    concept_score = _concept_match_score(resource, profile)
    trust_score = max(0.0, min(1.0, resource.trust_score))
    structure_score = _structure_score(resource)
    difficulty_score = _difficulty_fit(resource, profile)
    freshness_score = 0.08 if resource.metadata.get("recently_updated") else 0.0
    target_paper_score = 0.35 if resource.metadata.get("target_paper") else 0.0

    return (
        0.42 * concept_score
        + 0.24 * trust_score
        + 0.2 * structure_score
        + 0.14 * difficulty_score
        + freshness_score
        + target_paper_score
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
    return min(1.0, overlap)


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
    if metadata.get("stars"):
        score += min(0.12, math.log10(max(1, float(metadata["stars"]))) / 50)
    return min(score, 1.0)


def _difficulty_fit(resource: Resource, profile: LearnerProfile) -> float:
    domain = (dominant_domain(' '.join(resource.concepts))
              or dominant_domain(resource.title) or dominant_domain(profile.goal))
    level_values = {profile.levels.get(domain, 'familiar')}
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


def _recommendation_reason(resource: Resource, profile: LearnerProfile) -> str:
    reason = "matches your goal" if _concept_match_score(resource, profile) >= 0.1 else "No direct concept match; supplemental resource"
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

    from urllib.parse import parse_qsl, urlencode

    query = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True)
             if not k.lower().startswith('utm_') and k.lower() not in {'gclid', 'fbclid', 'msclkid'}]
    if host in {'youtube.com', 'm.youtube.com', 'youtu.be'}:
        params = dict(query)
        video = path.lstrip('/') if host == 'youtu.be' else params.get('v')
        if video:
            return f"youtube:video:{video}"
        if params.get('list'):
            return f"youtube:list:{params['list']}"
        query = [(k, v) for k, v in query if k not in {'si', 'feature'}]
    if host in {'bilibili.com', 'm.bilibili.com'}:
        query = [(k, v) for k, v in query if k not in {'spm_id_from', 'share_source', 'share_medium', 'share_session_id'}]
    suffix = urlencode(sorted(query))
    return f"{host}{path}" + (f"?{suffix}" if suffix else '')
