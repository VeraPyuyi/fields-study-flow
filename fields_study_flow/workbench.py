"""Generation-time research context and pure report projections."""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from fields_study_flow.models import Resource


def prepare_workbench(
    roadmap: dict[str, Any], resources: list[Resource], *,
    provider_mode: str = "auto", offline: bool = False,
    previous_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from fields_study_flow.explanations import prepare_explanations
    from fields_study_flow.learning_path import build_learning_path
    from fields_study_flow.research_context import build_research_context, validate_research_context

    updated = copy.deepcopy(roadmap)
    if previous_context is not None:
        previous_validation = validate_research_context(previous_context)
        if not previous_validation["valid"]:
            raise ValueError("researchContext has an invalid schema or references")
    context = build_research_context(updated, resources, previous_context=previous_context)
    context.setdefault("coverage", {})["input_analysis"] = [copy.deepcopy(r.metadata["analysis_coverage"]) for r in resources if isinstance(r.metadata.get("analysis_coverage"), dict)]
    context["learning_steps"] = build_learning_path(context, updated.get("profile", {}), updated.get("study_tasks", []))
    context["validation"] = validate_research_context(context)
    language = str(updated.get("paper_map", {}).get("output_language") or updated.get("profile", {}).get("output_language") or "zh-CN")
    context["explanations"] = prepare_explanations(context, language=language, provider_mode=provider_mode, offline=offline,
        cache_dir=Path.home() / ".cache" / "fields-study-flow" / "explanations")
    context["explanations"].setdefault("language", language)
    updated["research_context"] = context
    _project_claim_explanations(updated)
    _bind_segment_anchors(updated)
    _project_segment_explanations(updated)
    return bind_workbench_links(updated)


def _project_claim_explanations(roadmap: dict[str, Any]) -> None:
    context = roadmap["research_context"]
    prepared = context.get("explanations", {})
    language = roadmap.get("paper_map", {}).get("output_language", "zh-CN")
    compatible_language = prepared.get("language") in {None, language, "bilingual"}
    items = {item.get("claim_id"): item for item in prepared.get("items", [])}
    nodes = roadmap.get("paper_map", {}).get("nodes", [])
    for node in nodes:
        if node.get("role") != "core":
            continue
        primary = _target_source_ids(roadmap)
        anchor_sources = {a["id"]: a["source_id"] for a in context.get("anchors", [])}
        claims = [c for c in context.get("claims", []) if c.get("kind") == node.get("kind") and any(anchor_sources.get(a) in primary for a in c.get("anchor_ids", []))]
        if not claims:
            node["anchor_ids"] = []
            continue
        claims.sort(key=lambda c: c.get("evidence_status") != "located")
        node["claim_id"] = claims[0]["id"]
        node["claim_ids"] = [c["id"] for c in claims]
        node["anchor_ids"] = list(dict.fromkeys(a for c in claims for a in c.get("anchor_ids", [])))
        statuses = {c.get("evidence_status", "missing") for c in claims}
        node["evidence_status"] = "stale" if "stale" in statuses else "located" if statuses == {"located"} else "partial" if "located" in statuses or "partial" in statuses else "missing"
        node["review_status"] = "unreviewed"
        item = items.get(claims[0]["id"], {})
        if language == "en" and prepared.get("language") == "bilingual":
            item = item.get("translations", {}).get("en", {})
        # A model explanation is an interpretation, never a verification badge.
        if prepared.get("mode") == "llm" and compatible_language:
            for key in ("plain_meaning", "why_it_matters", "method_note"):
                if item.get(key):
                    node["plain_explanation" if key == "plain_meaning" else key] = item[key]
            example = item.get("example")
            if isinstance(example, dict):
                node["example"] = example.get("text", "")


def _bind_segment_anchors(roadmap: dict[str, Any]) -> None:
    context = roadmap["research_context"]
    anchors = context.get("anchors", [])
    lens = roadmap.get("paper_lens", {})
    primary = _target_source_ids(roadmap)
    for segment in lens.get("segments", []):
        text = str(segment.get("original_text") or "")
        matches = [a for a in anchors if a.get("source_id") in primary and a.get("locator_status") == "valid" and _matches_snippet(text, str(a.get("snippet") or ""))]
        segment["anchor_ids"] = [a["id"] for a in matches[:3]]
        segment["evidence_status"] = "located" if matches else "missing"
    segments = {s["id"]: s for s in lens.get("segments", [])}
    for explanation in lens.get("inline_explanations", []):
        segment = segments.get(explanation.get("segment_id"), {})
        explanation["anchor_ids"] = segment.get("anchor_ids", [])
        explanation["review_status"] = "unreviewed"


def _matches_snippet(text: str, snippet: str) -> bool:
    normalized = " ".join(text.lower().split())
    candidate = " ".join(snippet.lower().split())
    if not candidate:
        return False
    return candidate in normalized


def _target_source_ids(roadmap: dict[str, Any]) -> set[str]:
    target = roadmap.get("paper_map", {}).get("target") or roadmap.get("paper_lens", {}).get("target") or {}
    sources = [s for s in roadmap.get("research_context", {}).get("sources", []) if s.get("kind") == "paper"]
    matches = [s for s in sources if target.get("url") and s.get("url") == target["url"]]
    if not matches:
        matches = [s for s in sources if s.get("title") == target.get("title") and (not target.get("url") or not s.get("url"))]
    return {s["id"] for s in matches} if len(matches) == 1 else set()


def project_prepared_views(roadmap: dict[str, Any]) -> dict[str, Any]:
    updated = copy.deepcopy(roadmap)
    if isinstance(updated.get("research_context"), dict) and isinstance(updated["research_context"].get("explanations"), dict):
        _project_claim_explanations(updated)
        _bind_segment_anchors(updated)
        _project_segment_explanations(updated)
    return updated


def _project_segment_explanations(roadmap: dict[str, Any]) -> None:
    from fields_study_flow.explanations import explain_segment

    context = roadmap["research_context"]
    prepared = context.get("explanations", {})
    if prepared.get("mode") not in {"llm", "mixed"}:
        return
    lens = roadmap.get("paper_lens", {})
    language = str(lens.get("output_language") or lens.get("explanation_summary", {}).get("language") or "zh-CN")
    if prepared.get("language") not in {None, language, "bilingual"}:
        return
    anchors = {a["id"]: a for a in context.get("anchors", [])}
    segments = {s["id"]: s for s in lens.get("segments", [])}
    for explanation in lens.get("inline_explanations", []):
        segment = segments.get(explanation.get("segment_id"), {})
        for aid in segment.get("anchor_ids", []):
            anchor = anchors[aid]
            snippet = anchor.get("snippet", "")
            if not snippet or snippet not in str(segment.get("original_text", "")):
                continue
            projected = explain_segment({"id": segment["id"], "original_text": snippet, "anchor_ids": [aid], "source_id": anchor["source_id"], "locator": anchor["locator"]}, context, language, items=prepared)
            if not projected.get("claim_id"):
                continue
            for key in ("plain_meaning", "why_it_matters", "method_note", "evidence_refs", "translations"):
                if key in projected:
                    explanation[key] = projected[key]
            full = snippet.strip() == str(segment.get("original_text", "")).strip()
            explanation["interpretation_scope"] = "paragraph" if full else "excerpt"
            if not full:
                explanation["plain_meaning"] += "\n" + ("解释仅覆盖本段的已定位摘录，其余内容仍需读原文。" if language != "en" else "This interpretation covers only the located excerpt, not the rest of the paragraph.")
            explanation["provider_payload"] = {"mode": "llm", "llm_extension_ready": True}
            explanation["review_status"] = "unreviewed"
            break


def bind_workbench_links(roadmap: dict[str, Any]) -> dict[str, Any]:
    """Rebind downloaded files without parsing, regenerating, or calling a model."""
    updated = copy.deepcopy(roadmap)
    bundle = updated.get("study_bundle", {})
    from urllib.parse import unquote, urlsplit
    from fields_study_flow.privacy import PRIVATE_PATH_RE

    def portable(entry: dict[str, Any]) -> bool:
        href = str(entry.get("local_href") or "")
        decoded = unquote(href).replace("\\", "/")
        try:
            scheme = urlsplit(decoded).scheme
        except ValueError:
            return False
        if decoded.startswith("../"):
            file = str(entry.get("file") or "").replace("\\", "/")
            if not file or file.startswith("/") or ".." in file.split("/") or PRIVATE_PATH_RE.search(file) or not decoded.endswith("/" + file):
                return False
        return bool(href and entry.get("status") in {"copied", "downloaded", "snapshotted", "generated"}
                    and not scheme and not decoded.startswith("/")
                    and not PRIVATE_PATH_RE.search(decoded))

    entries = [e for e in bundle.get("resources", []) if isinstance(e, dict) and portable(e)]
    exact = {(str(e.get("title", "")), str(e.get("url", ""))): e for e in entries}
    titles: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        titles.setdefault(str(entry.get("title", "")), []).append(entry)

    def rebind(value: Any) -> None:
        if isinstance(value, dict):
            title = str(value.get("title") or value.get("resource_title") or "")
            match = exact.get((title, str(value.get("url", ""))))
            if match is None and len(titles.get(title, [])) == 1:
                candidate = titles[title][0]
                if not value.get("url") or not candidate.get("url"):
                    match = candidate
            if match:
                value["local_href"] = match["local_href"]
            for child in value.values():
                rebind(child)
        elif isinstance(value, list):
            for child in value:
                rebind(child)

    rebind(updated)
    if updated.get("research_context") and "study_bundle" in updated:
        from fields_study_flow.research_context import bind_context_links

        updated["research_context"] = bind_context_links(updated["research_context"], bundle)
    return updated
