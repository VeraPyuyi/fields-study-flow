"""Version-one public evidence context, independent of report integration.

Located evidence and valid locators do not assert scientific correctness.
Rule/model associations are candidates; acceptance is an explicit review act.
"""
from __future__ import annotations

import copy
import re
from dataclasses import fields, replace
from pathlib import Path
from typing import Any

from fields_study_flow.models import Resource
from fields_study_flow.rag import _resource_id
from fields_study_flow.project_evidence import (
    LOCATOR_KEYS, SOURCE_KINDS, MAX_ANCHORS, _anchor, _digest, _id, _items,
    _locator, _mapping, _portable_href, _public_text, _safe_relative, _safe_url, _source_identity,
    extract_project_evidence,
)

CLAIM_KINDS = {"background", "motivation", "problem", "methodology", "experiment", "result", "contribution", "limitation"}
RELATION_KINDS = {"motivates", "addresses", "implements", "uses_config", "evaluated_by", "supports", "bounded_by"}
_ALIASES = {"method": "methodology", "formula": "methodology", "abstract": "background", "related_work": "background", "results": "result", "limitations": "limitation"}


def _claim_kind(value: Any) -> str:
    text = str(value or "").lower().strip()
    text = _ALIASES.get(text, text)
    if text in CLAIM_KINDS:
        return text
    for pattern, kind in ((r"limitation|boundary|局限", "limitation"), (r"result|结果", "result"),
                          (r"experiment|evaluation|实验", "experiment"), (r"method|approach|方法", "methodology"),
                          (r"problem|问题", "problem"), (r"motivation|动机", "motivation"),
                          (r"contribution|贡献", "contribution")):
        if re.search(pattern, text):
            return kind
    return "background"


def _evidence_status(anchor_ids: list[str], anchors: dict[str, dict]) -> str:
    statuses = [anchors.get(a, {}).get("locator_status", "missing") for a in anchor_ids]
    if "stale" in statuses:
        return "stale"
    if not statuses or all(s == "missing" for s in statuses):
        return "missing"
    return "located" if all(s == "valid" for s in statuses) else "partial"


def _legacy_resources(roadmap: dict) -> list[Resource]:
    values = _items(roadmap.get("resource_library")) or _items(roadmap.get("resources"))
    if not values:
        values = [r for p in _items(roadmap.get("phases")) if isinstance(p, dict) for r in _items(p.get("resources"))]
    target = _mapping(_mapping(roadmap.get("paper_lens")).get("target"))
    if not values and target:
        values = [{**target, "type": "paper"}]
    allowed = {f.name for f in fields(Resource)} - {"local_path"}
    output = []
    for value in values[:64]:
        if not isinstance(value, dict):
            continue
        kwargs = {k: copy.deepcopy(v) for k, v in value.items() if k in allowed}
        for key in ("title", "url", "source", "type"):
            kwargs[key] = str(kwargs.get(key) or ("paper" if key == "type" else ""))
        output.append(Resource(**kwargs))
    return output


def _with_legacy_segments(roadmap: dict, resources: list[Resource]) -> list[Resource]:
    lens = _mapping(roadmap.get("paper_lens"))
    target_url = _safe_url(_mapping(lens.get("target")).get("url"))
    candidates = [r for r in resources if r.type == "paper" or _mapping(r.metadata).get("target_paper")]
    target = next((r for r in candidates if target_url and _safe_url(r.url) == target_url), None)
    if target is None and len(candidates) == 1:
        target = candidates[0]
    segments = _items(lens.get("segments"))
    if target is None or not segments:
        return resources
    output = []
    for resource in resources:
        metadata = copy.deepcopy(_mapping(resource.metadata))
        if resource is target:
            metadata["paper_segments"] = _items(metadata.get("paper_segments")) + segments
        output.append(replace(resource, metadata=metadata))
    return output


def build_research_context(roadmap: dict, resources: list[Resource] | None = None, *, previous_context: dict | None = None) -> dict:
    """Build a deterministic public snapshot; never execute or fetch materials.

    Raw Resource paths are private inputs only. Legacy roadmap dictionaries are
    adapted without authorizing filesystem reads. Explicit claims accept
    source_id/source_url plus locator, or existing anchor_ids. Supplied
    relations reference source/claim IDs and remain unreviewed by default.
    """
    roadmap = _mapping(roadmap)
    private_resources = _with_legacy_segments(roadmap, list(resources) if resources is not None else _legacy_resources(roadmap))
    evidence = extract_project_evidence(private_resources)
    sources = evidence["sources"]
    anchors = evidence["anchors"]
    profile = _mapping(roadmap.get("profile"))
    target = roadmap.get("target_id") or _mapping(roadmap.get("target")).get("id")
    if not target:
        explicit_url = _safe_url(_mapping(_mapping(roadmap.get("paper_lens")).get("target")).get("url") or _mapping(roadmap.get("target")).get("url"))
        resource_identity = []
        for index, resource in enumerate(private_resources):
            metadata = _mapping(resource.metadata)
            if not metadata.get("target_paper") and resource.critical_path_role != "core-paper":
                continue
            path = Path(resource.local_path).expanduser().absolute() if resource.local_path else None
            root_value = metadata.get("project_root") or metadata.get("explicit_root")
            root = Path(root_value).expanduser().absolute() if isinstance(root_value, str) else None
            if path and root and not path.is_relative_to(root):
                continue
            resource_identity.append(_source_identity(resource, path, root, index))
        papers_for_identity = [s for s in sources if s["kind"] == "paper"]
        if not resource_identity and len(papers_for_identity) == 1:
            resource_identity = [papers_for_identity[0]["id"]]
        target = [roadmap.get("target_kind"), explicit_url or sorted(set(resource_identity)) or profile.get("goal") or roadmap.get("title") or "unspecified-target"]
    bundle_id = _id("bundle", target)
    options = {k: roadmap[k] for k in ("paper_map_options", "paper_lens_options", "research_options", "key_options") if k in roadmap}
    options["profile"] = {k: profile[k] for k in ("goal", "output_language", "learning_outcome", "known_topics", "levels", "route_depth", "planner_preset", "target_kind") if k in profile}
    # Hash inputs before invalidation adds historical sources or review flags.
    semantics = {"claims": _items(roadmap.get("claims"))[:256], "relations": _items(roadmap.get("relations"))[:512]}
    snapshot_id = _id("snapshot", [sorted((s["id"], s["kind"], s["fingerprint"]) for s in sources), options, semantics])
    context = {"schema_version": 1, "bundle_id": bundle_id, "snapshot_id": snapshot_id,
               "sources": sources, "anchors": anchors, "claims": [], "relations": [], "learning_steps": [],
               "coverage": evidence["coverage"], "changes": {"changed_source_ids": [], "removed_source_ids": [], "review_required": False}}
    previous = _mapping(previous_context)
    if previous.get("bundle_id") == bundle_id:
        old_sources = {s["id"]: s for s in _items(previous.get("sources")) if isinstance(s, dict) and isinstance(s.get("id"), str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", s["id"])}
        current = {s["id"]: s for s in sources}
        changed = {sid for sid in old_sources.keys() & current.keys() if old_sources[sid].get("fingerprint") != current[sid]["fingerprint"]}
        removed = old_sources.keys() - current.keys()
        context["changes"] = {"changed_source_ids": sorted(changed), "removed_source_ids": sorted(removed), "review_required": bool(changed or removed or previous.get("snapshot_id") != snapshot_id)}
        for sid in sorted(removed):
            old = old_sources[sid]
            kind = old.get("kind")
            kind = kind if isinstance(kind, str) and kind in SOURCE_KINDS else "paper"
            retained = {"id": sid, "kind": kind, "title": _public_text(old.get("title")) or "Unavailable material",
                        "fingerprint": old.get("fingerprint") if isinstance(old.get("fingerprint"), str) and re.fullmatch(r"[a-f0-9]{64}", old["fingerprint"]) else _digest(old.get("fingerprint")), "availability": "missing"}
            if relative := _safe_relative(old.get("relative_path")):
                retained["relative_path"] = relative
            if url := _safe_url(old.get("url")):
                retained["url"] = url
            if isinstance(old.get("resource_id"), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,128}", old["resource_id"]):
                retained["resource_id"] = old["resource_id"]
            sources.append(retained)
        affected = changed | removed
        for anchor in anchors:
            if anchor["source_id"] in affected:
                anchor["locator_status"] = "stale"
        existing = {a["id"] for a in anchors}
        for old in _items(previous.get("anchors")):
            if isinstance(old, dict) and old.get("source_id") in affected and old.get("id") not in existing and len(anchors) < MAX_ANCHORS:
                retained = _anchor(old["source_id"], _mapping(old.get("locator")), old.get("snippet"), status="stale")
                retained["id"] = old["id"]
                anchors.append(retained)
                existing.add(old["id"])
    source_lookup = {s["id"]: s for s in sources}
    anchor_lookup = {a["id"]: a for a in anchors}
    target_url = _safe_url(_mapping(_mapping(roadmap.get("paper_lens")).get("target")).get("url") or _mapping(roadmap.get("target")).get("url"))
    target_resources = [r for r in private_resources if _mapping(r.metadata).get("target_paper") or r.critical_path_role == "core-paper"]
    target_urls = {_safe_url(r.url) for r in target_resources if _safe_url(r.url)}
    target_rids = {str(_mapping(r.metadata).get("resource_id") or _mapping(r.metadata).get("local_resource_id") or _resource_id(r)) for r in target_resources}
    primary_ids = {s["id"] for s in sources if s["kind"] == "paper" and (s.get("resource_id") in target_rids or s.get("url") in target_urls)}
    if target_url:
        matched = [s["id"] for s in sources if s["kind"] == "paper" and s.get("url") == target_url]
        if len(matched) == 1:
            primary_ids = set(matched)
    papers = [s for s in sources if s["kind"] == "paper" and s.get("availability") != "missing"]
    if not primary_ids and len(papers) == 1:
        primary_ids = {papers[0]["id"]}
    context["primary_source_ids"] = sorted(primary_ids)
    aliases = {}
    for resource in private_resources:
        metadata = _mapping(resource.metadata)
        raw_id = metadata.get("research_source_id") or metadata.get("source_id")
        if isinstance(raw_id, str):
            candidate = _id("source", ["supplied", raw_id, ""])
            if candidate in source_lookup:
                aliases[raw_id] = candidate

    def find_source(spec: dict) -> str | None:
        sid = spec.get("source_id")
        if isinstance(sid, str) and (sid in source_lookup or sid in aliases):
            return aliases.get(sid, sid)
        url = _safe_url(spec.get("source_url") or spec.get("url"))
        matches = [s["id"] for s in sources if url and s.get("url") == url]
        return matches[0] if len(matches) == 1 else None

    claim_aliases = {}

    def add_claim(spec: dict, *, automatic: bool = False) -> None:
        statement = _public_text(spec.get("statement") or spec.get("text") or spec.get("snippet"), 1200)
        if not statement:
            return
        aids = [a for a in _items(spec.get("anchor_ids")) if isinstance(a, str) and a in anchor_lookup]
        unknown = [a for a in _items(spec.get("anchor_ids")) if not isinstance(a, str) or a not in anchor_lookup]
        if unknown:
            context["coverage"]["skipped"].append({"reason": "invalid_claim_anchor_reference", "count": len(unknown)})
            if aids and len(anchors) < MAX_ANCHORS:
                missing = _anchor(anchor_lookup[aids[0]]["source_id"], {}, "An explicit citation could not be located", status="missing", identity=["unresolved", spec.get("id"), unknown])
                if missing["id"] not in anchor_lookup:
                    anchors.append(missing)
                    anchor_lookup[missing["id"]] = missing
                aids.append(missing["id"])
        source_id = find_source(spec)
        if source_id and not aids:
            locator = _locator(spec.get("locator"))
            matched = [a["id"] for a in anchors if a["source_id"] == source_id and locator and all(a["locator"].get(k) == v for k, v in locator.items())]
            aids = matched
            if not aids and len(anchors) < MAX_ANCHORS:
                new = _anchor(source_id, locator, statement, status="missing", identity=spec.get("id") or statement)
                anchors.append(new)
                anchor_lookup[new["id"]] = new
                aids = [new["id"]]
        kind = _claim_kind(spec.get("kind"))
        cid = _id("claim", ["supplied", spec["id"]]) if spec.get("id") else _id("claim", [kind, aids or statement])
        if isinstance(spec.get("id"), str):
            claim_aliases[spec["id"]] = cid
        if any(c["id"] == cid for c in context["claims"]):
            return
        claim = {"id": cid, "kind": kind, "statement": statement, "anchor_ids": aids,
                 "evidence_status": _evidence_status(aids, anchor_lookup)}
        if "mandatory" in spec:
            claim["mandatory"] = bool(spec["mandatory"])
        elif automatic:
            claim["mandatory"] = any(source_lookup.get(anchor_lookup[a]["source_id"], {}).get("kind") == "paper" for a in aids)
        if spec.get("topic"):
            claim["topic"] = _public_text(spec["topic"])
        context["claims"].append(claim)

    for spec in _items(roadmap.get("claims"))[:256]:
        if isinstance(spec, dict):
            add_claim(spec)
    for index, resource in enumerate(private_resources):
        metadata = _mapping(resource.metadata)
        path = Path(resource.local_path).expanduser().absolute() if resource.local_path else None
        root_value = metadata.get("project_root") or metadata.get("explicit_root")
        root = Path(root_value).expanduser().absolute() if isinstance(root_value, str) else None
        if path and root and not path.is_relative_to(root):
            continue
        sid = _source_identity(resource, path, root, index)
        for spec in (_items(metadata.get("claims")) + _items(_mapping(metadata.get("paper_metadata")).get("claims")))[:256]:
            if isinstance(spec, dict):
                add_claim({"source_id": sid, **spec})
    for anchor in list(anchors):
        if anchor.get("scope") == "page_preview":
            continue
        source = source_lookup.get(anchor["source_id"], {})
        if anchor["source_id"] in primary_ids or (not papers and source.get("kind") == "readme"):
            add_claim({"kind": anchor.get("hint_kind") or anchor["locator"].get("section"), "statement": anchor["snippet"], "anchor_ids": [anchor["id"]]}, automatic=True)
    # Preserve stale citations when a previously referenced symbol/section vanished.
    for old in _items(previous.get("claims")) if previous.get("bundle_id") == bundle_id else []:
        if isinstance(old, dict) and old.get("id") not in {c["id"] for c in context["claims"]}:
            aids = [a for a in _items(old.get("anchor_ids")) if a in anchor_lookup]
            if any(anchor_lookup[a]["locator_status"] == "stale" for a in aids):
                claim = {"id": old["id"], "kind": _claim_kind(old.get("kind")), "statement": _public_text(old.get("statement"), 1200), "anchor_ids": aids, "evidence_status": "stale"}
                context["claims"].append(claim)
    entities = set(source_lookup) | {c["id"] for c in context["claims"]}
    all_aliases = aliases | claim_aliases
    for spec in _items(roadmap.get("relations"))[:512]:
        if not isinstance(spec, dict) or spec.get("kind") not in RELATION_KINDS:
            continue
        start, end = spec.get("from"), spec.get("to")
        if not isinstance(start, str) or not isinstance(end, str):
            continue
        start, end = all_aliases.get(start, start), all_aliases.get(end, end)
        if start not in entities or end not in entities:
            context["coverage"]["skipped"].append({"reason": "invalid_relation_reference"})
            continue
        origin = spec.get("origin") if spec.get("origin") in {"supplied", "rule", "model", "human"} else "supplied"
        review = spec.get("review_status", "unreviewed")
        if review not in {"unreviewed", "accepted", "rejected"} or origin in {"rule", "model"}:
            review = "unreviewed"
        relation = {"id": _id("relation", [start, end, spec["kind"]]), "from": start, "to": end, "kind": spec["kind"],
                    "anchor_ids": [a for a in _items(spec.get("anchor_ids")) if isinstance(a, str) and a in anchor_lookup], "origin": origin, "review_status": review}
        stale_claims = {c["id"] for c in context["claims"] if c["evidence_status"] == "stale"}
        affected = set(context["changes"]["changed_source_ids"] + context["changes"]["removed_source_ids"]) | stale_claims
        if any(anchor_lookup[a]["locator_status"] == "stale" for a in relation["anchor_ids"]) or start in affected or end in affected:
            relation["review_status"] = "unreviewed"
            relation["review_required"] = True
        context["relations"].append(relation)
    # Lexical overlap supplies a navigational candidate, never verification.
    for claim in context["claims"][:256]:
        if claim["kind"] not in {"methodology", "experiment", "result"}:
            continue
        titles = " ".join(source_lookup.get(anchor_lookup[a]["source_id"], {}).get("title", "") for a in claim["anchor_ids"])
        terms = set(re.findall(r"[a-zA-Z]{4,}|[\u4e00-\u9fff]{2,}", (claim["statement"] + " " + titles).lower())) - {"this", "that", "with", "from", "method", "demonstration"}
        for source in sources:
            if source["kind"] not in {"code", "config", "result", "notebook"} or source.get("availability") == "missing":
                continue
            source_anchors = [a for a in anchors if a["source_id"] == source["id"]]
            text = (source["title"] + " " + " ".join(a["snippet"] for a in source_anchors)).lower()
            if not terms.intersection(re.findall(r"[a-zA-Z]{4,}|[\u4e00-\u9fff]{2,}", text)):
                continue
            kind = {"code": "implements", "notebook": "implements", "config": "uses_config", "result": "evaluated_by"}[source["kind"]]
            rid = _id("relation", [claim["id"], source["id"], kind])
            if any(r["id"] == rid for r in context["relations"]):
                continue
            context["relations"].append({"id": rid, "from": claim["id"], "to": source["id"], "kind": kind,
                                         "anchor_ids": claim["anchor_ids"] + [a["id"] for a in source_anchors[:3]],
                                         "origin": "rule", "review_status": "unreviewed", "candidate": True})
    # Never describe absent implementation/configuration/results as supplied.
    context["coverage"]["missing_material_kinds"] = [k for k in ("code", "config", "result") if not any(s["kind"] == k and s.get("availability") == "available" for s in sources)]
    return context


def bind_context_links(context: dict, study_bundle: dict) -> dict:
    """Return a copy with portable bundle links; no parsing or regeneration.

    Match stable source/resource IDs first, then unique public URL. Titles and
    basenames alone are never identities. Only successful bundle entries bind.
    """
    bound = copy.deepcopy(_mapping(context))
    entries = [e for e in _items(_mapping(study_bundle).get("resources")) if isinstance(e, dict) and e.get("status") in {"copied", "downloaded", "snapshotted", "generated"}]
    sources = [s for s in _items(bound.get("sources")) if isinstance(s, dict)]
    for source in sources:
        source.pop("local_href", None)
        matches = []
        for entry in entries:
            metadata = _mapping(entry.get("metadata"))
            source_id = entry.get("source_id") or metadata.get("source_id")
            resource_id = entry.get("resource_id") or metadata.get("resource_id") or metadata.get("local_resource_id")
            unique_resource = resource_id and sum(s.get("resource_id") == resource_id for s in sources) == 1
            exact_relative = "/" in source.get("relative_path", "") and _safe_relative(entry.get("relative_path")) == source["relative_path"]
            if source_id == source.get("id") or (resource_id and resource_id == source.get("resource_id") and (unique_resource or exact_relative)):
                matches.append(entry)
        if not matches and source.get("url"):
            if sum(s.get("url") == source["url"] for s in sources) == 1:
                matches = [e for e in entries if _safe_url(e.get("url")) == source["url"]]
        if len(matches) > 1:
            # Full relative path can disambiguate a directory Resource, not basename.
            relative = source.get("relative_path", "")
            matches = [e for e in matches if "/" in relative and _safe_relative(e.get("relative_path")) == relative]
        if len(matches) == 1:
            entry = matches[0]
            href = _safe_relative(entry.get("local_href"))
            if not href and entry.get("file"):
                portable = _portable_href(entry.get("local_href"))
                file = _safe_relative(entry["file"])
                # File verification is required for any leading ../ segments.
                if portable and file and (portable == file or portable.endswith("/" + file)):
                    href = portable
            if not href and entry.get("file") and not entry.get("local_href"):
                file = _safe_relative(entry["file"])
                prefix = _safe_relative(study_bundle.get("relative_dir") or "study-assets")
                href = _safe_relative(f"{prefix}/{file}") if file and prefix else ""
            if href:
                source["local_href"] = href
    return bound


def validate_research_context(context: dict) -> dict:
    """Validate structure, enums, locators and references without metadata throws.

    Issues are structured {path, code, message} records; validation is read-only.
    task_ids are checked when optional context.study_tasks/task_ids is supplied.
    """
    issues = []

    def issue(path: str, code: str, message: str) -> None:
        issues.append({"path": path, "code": code, "message": message})

    if not isinstance(context, dict):
        return {"valid": False, "issues": [{"path": "$", "code": "type", "message": "Expected a context object"}]}
    if context.get("schema_version") != 1 or isinstance(context.get("schema_version"), bool):
        issue("schema_version", "version", "Expected schema_version 1")
    for name in ("bundle_id", "snapshot_id"):
        if not isinstance(context.get(name), str) or not context[name]:
            issue(name, "required", "Expected a nonempty identifier")
    groups, indexes = {}, {}
    global_ids = set()
    for group in ("sources", "anchors", "claims", "relations", "learning_steps"):
        value = context.get(group)
        if not isinstance(value, list):
            issue(group, "type", "Expected an array")
        groups[group] = []
        indexes[group] = set()
        for i, item in enumerate(_items(value)):
            path = f"{group}[{i}]"
            if not isinstance(item, dict):
                issue(path, "type", "Expected an object")
                continue
            groups[group].append((path, item))
            identifier = item.get("id")
            if not isinstance(identifier, str) or not identifier:
                issue(path + ".id", "required", "Expected a nonempty identifier")
            elif identifier in global_ids:
                issue(path + ".id", "duplicate", "Duplicate identifier")
            else:
                global_ids.add(identifier)
                indexes[group].add(identifier)

    def enum(path: str, value: Any, allowed: set[str]) -> None:
        if not isinstance(value, str) or value not in allowed:
            issue(path, "enum", "Unexpected value")

    def text(path: str, value: Any, *, limit: int | None = None) -> None:
        if not isinstance(value, str) or not value:
            issue(path, "type", "Expected nonempty text")
        elif limit and len(value) > limit:
            issue(path, "length", "Text exceeds limit")

    def refs(path: str, value: Any, allowed: set[str] | None) -> None:
        if not isinstance(value, list):
            issue(path, "type", "Expected an identifier array")
            return
        for i, identifier in enumerate(value):
            if not isinstance(identifier, str) or (allowed is not None and identifier not in allowed):
                issue(f"{path}[{i}]", "reference", "Unknown or invalid reference")

    for path, source in groups["sources"]:
        enum(path + ".kind", source.get("kind"), SOURCE_KINDS)
        text(path + ".title", source.get("title"))
        text(path + ".fingerprint", source.get("fingerprint"))
        for key in ("relative_path", "local_href"):
            if key in source and not (_portable_href(source[key]) if key == "local_href" else _safe_relative(source[key])):
                issue(path + "." + key, "private_path", "Expected a safe relative link")
        if "url" in source and _safe_url(source["url"]) != source["url"]:
            issue(path + ".url", "unsafe_url", "Expected a public URL without credentials or query")
    for path, anchor in groups["anchors"]:
        sid = anchor.get("source_id")
        if not isinstance(sid, str) or sid not in indexes["sources"]:
            issue(path + ".source_id", "reference", "Unknown source")
        enum(path + ".locator_status", anchor.get("locator_status"), {"valid", "missing", "stale"})
        if not isinstance(anchor.get("snippet"), str) or len(anchor.get("snippet", "")) > 300:
            issue(path + ".snippet", "length", "Expected a snippet of at most 300 characters")
        locator = anchor.get("locator")
        if not isinstance(locator, dict):
            issue(path + ".locator", "type", "Expected a locator object")
            continue
        if anchor.get("locator_status") == "valid" and not locator:
            issue(path + ".locator", "missing", "A valid locator must specify a location")
        for key, value in locator.items():
            if key not in LOCATOR_KEYS:
                issue(path + ".locator", "key", "Unsupported locator field")
            elif key in {"page", "row", "line_start", "line_end"}:
                if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                    issue(path + ".locator." + key, "number", "Expected a positive integer")
            elif not isinstance(value, str) or (not value and key != "json_pointer"):
                issue(path + ".locator." + key, "type", "Expected a text locator")
            elif key == "json_pointer" and value and (not value.startswith("/") or re.search(r"~(?![01])", value)):
                issue(path + ".locator.json_pointer", "pointer", "Invalid JSON pointer")
        start, end = locator.get("line_start"), locator.get("line_end")
        if isinstance(start, int) and isinstance(end, int) and end < start:
            issue(path + ".locator", "range", "Reversed line range")
    anchor_index = {a["id"]: a for _, a in groups["anchors"] if isinstance(a.get("id"), str)}
    for path, claim in groups["claims"]:
        enum(path + ".kind", claim.get("kind"), CLAIM_KINDS)
        text(path + ".statement", claim.get("statement"))
        refs(path + ".anchor_ids", claim.get("anchor_ids"), indexes["anchors"])
        enum(path + ".evidence_status", claim.get("evidence_status"), {"located", "partial", "missing", "stale"})
        aids = claim.get("anchor_ids")
        if isinstance(aids, list) and all(isinstance(a, str) and a in anchor_index for a in aids):
            if claim.get("evidence_status") != _evidence_status(aids, anchor_index):
                issue(path + ".evidence_status", "consistency", "Evidence status disagrees with anchors")
    for path, relation in groups["relations"]:
        enum(path + ".kind", relation.get("kind"), RELATION_KINDS)
        enum(path + ".origin", relation.get("origin"), {"supplied", "rule", "model", "human"})
        enum(path + ".review_status", relation.get("review_status"), {"unreviewed", "accepted", "rejected"})
        for key in ("from", "to"):
            value = relation.get(key)
            if not isinstance(value, str) or value not in indexes["sources"] | indexes["claims"]:
                issue(path + "." + key, "reference", "Unknown entity")
        refs(path + ".anchor_ids", relation.get("anchor_ids"), indexes["anchors"])
    task_ids = context.get("task_ids")
    tasks = context.get("study_tasks")
    allowed_tasks = {t for t in _items(task_ids) if isinstance(t, str)} if isinstance(task_ids, list) else None
    if isinstance(tasks, list):
        allowed_tasks = {t["id"] for t in tasks if isinstance(t, dict) and isinstance(t.get("id"), str)}
    for path, step in groups["learning_steps"]:
        text(path + ".title", step.get("title"))
        text(path + ".reason", step.get("reason"))
        enum(path + ".status", step.get("status"), {"available", "needs_material"})
        refs(path + ".claim_ids", step.get("claim_ids"), indexes["claims"])
        refs(path + ".anchor_ids", step.get("anchor_ids"), indexes["anchors"])
        refs(path + ".task_ids", step.get("task_ids"), allowed_tasks)
        refs(path + ".prerequisite_ids", step.get("prerequisite_ids"), indexes["learning_steps"])
        estimate = step.get("estimated_minutes")
        if "estimated_minutes" not in step or (estimate is not None and (not isinstance(estimate, (int, float)) or isinstance(estimate, bool) or not 0 < estimate < float("inf"))):
            issue(path + ".estimated_minutes", "estimate", "Expected positive minutes or null")
    return {"valid": not issues, "issues": issues}
