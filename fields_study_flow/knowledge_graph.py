from __future__ import annotations

import re
from typing import Any

from fields_study_flow.models import LearnerProfile, Resource


PRIVATE_PATH_RE = re.compile(r"(?:file://[^\s)\]}\"'<]+|(?<![A-Za-z0-9])[A-Za-z]:[\\/][^)\]}\"'<\r\n]+|/(?:Users|home)/[^)\]}\"'<\r\n]+)")

STOP_TERMS = {
    "about",
    "and",
    "are",
    "can",
    "for",
    "from",
    "how",
    "learn",
    "master",
    "paper",
    "study",
    "that",
    "the",
    "this",
    "with",
}

KNOWN_PHRASES = (
    "action preconditions",
    "automated planning",
    "chain of thought",
    "chain-of-thought",
    "diffusion models",
    "instruction tuning",
    "large language model",
    "plan validation",
    "state transitions",
    "symbolic planning",
    "val plan validation",
)


def build_knowledge_graph(
    profile: LearnerProfile,
    resources: list[Resource],
    study_tasks: list[dict[str, Any]],
    mastery_evidence: dict[str, Any],
    rag_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    concept_labels = _select_concepts(profile, resources, study_tasks, rag_evidence or {})
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    concept_ids: dict[str, str] = {}
    resource_ids: dict[str, str] = {}
    task_ids: dict[str, str] = {}

    for label in concept_labels:
        node_id = f"concept-{len(concept_ids) + 1}"
        concept_ids[_norm(label)] = node_id
        nodes.append({"id": node_id, "kind": "concept", "label": label})

    for index, resource in enumerate(resources, start=1):
        node_id = f"resource-{index}"
        resource_ids[resource.title] = node_id
        evidence_chunks = _resource_evidence(resource)
        nodes.append(
            {
                "id": node_id,
                "kind": "resource",
                "label": resource.title,
                "detail": f"{resource.source} / {resource.type}",
                "evidence_count": len(evidence_chunks),
            }
        )
        for concept in _resource_concepts(resource):
            concept_id = concept_ids.get(_norm(concept))
            if concept_id:
                edges.append(_edge(profile, concept_id, node_id, "covered_by"))

    for index, task in enumerate(study_tasks, start=1):
        task_id = str(task.get("id") or f"task-{index}")
        task_ids[task_id] = task_id
        nodes.append(
            {
                "id": task_id,
                "kind": "task",
                "label": str(task.get("title") or task.get("type") or "task"),
                "detail": str(task.get("type", "task")),
                "evidence_count": len(task.get("evidence_chunks", []) or []),
            }
        )
        for resource_title in task.get("resource_titles", []) or []:
            resource_id = resource_ids.get(str(resource_title))
            if resource_id:
                edge = _edge(profile, resource_id, task_id, "supports")
                chunks = _public_chunks(task.get("evidence_chunks", []) or [])
                if chunks:
                    edge["evidence_chunks"] = chunks
                edges.append(edge)

    assessment_id = "assessment-1"
    assessment_label = str(mastery_evidence.get("final_artifact") or "final artifact")
    nodes.append({"id": assessment_id, "kind": "assessment", "label": assessment_label})
    for task in study_tasks:
        task_id = str(task.get("id", ""))
        if task_id in task_ids:
            edges.append(_edge(profile, task_id, assessment_id, "required_for"))

    edges = _dedupe_edges(edges)
    nodes = _sanitize_nodes(nodes)
    edges = _sanitize_edges(edges)
    summary = {
        "concepts": sum(1 for node in nodes if node["kind"] == "concept"),
        "resources": sum(1 for node in nodes if node["kind"] == "resource"),
        "tasks": sum(1 for node in nodes if node["kind"] == "task"),
        "assessments": sum(1 for node in nodes if node["kind"] == "assessment"),
        "edges": len(edges),
        "evidence_backed_edges": sum(1 for edge in edges if edge.get("evidence_chunks")),
    }
    return {"summary": summary, "nodes": nodes, "edges": edges}


def _select_concepts(
    profile: LearnerProfile,
    resources: list[Resource],
    study_tasks: list[dict[str, Any]],
    rag_evidence: dict[str, Any],
    limit: int = 12,
) -> list[str]:
    labels: list[str] = []
    for resource in resources:
        labels.extend(_resource_concepts(resource))
    for task in study_tasks:
        labels.extend(_extract_terms(str(task.get("title", ""))))
    for chunk in rag_evidence.get("top_chunks", []) or []:
        if isinstance(chunk, dict):
            labels.extend(_extract_terms(str(chunk.get("snippet", ""))))
    if not labels:
        labels.extend(_extract_terms(profile.goal))
    return _unique_labels(labels, limit=limit)


def _edge(profile: LearnerProfile, source: str, target: str, label: str) -> dict[str, Any]:
    return {"from": source, "to": target, "label": label, "localized_label": _edge_label(profile, label)}


def _edge_label(profile: LearnerProfile, label: str) -> str:
    zh = {"covered_by": "由资料覆盖", "supports": "支撑任务", "required_for": "验收必需"}
    en = {"covered_by": "covered by", "supports": "supports", "required_for": "required for"}
    if profile.output_language == "zh-CN":
        return zh.get(label, label)
    if profile.output_language == "bilingual":
        return f"{en.get(label, label)} / {zh.get(label, label)}"
    return en.get(label, label)


def _resource_concepts(resource: Resource) -> list[str]:
    labels: list[str] = []
    labels.extend(resource.concepts)
    labels.extend(resource.focus_areas)
    for item in resource.learning_key_points:
        labels.extend(_extract_terms(item))
    metadata = resource.metadata.get("rag") if isinstance(resource.metadata, dict) else None
    if isinstance(metadata, dict):
        for chunk in metadata.get("top_chunks", []) or []:
            if isinstance(chunk, dict):
                labels.extend(_extract_terms(str(chunk.get("snippet", ""))))
    return _unique_labels(labels, limit=8)


def _resource_evidence(resource: Resource) -> list[dict[str, Any]]:
    metadata = resource.metadata.get("rag") if isinstance(resource.metadata, dict) else None
    if not isinstance(metadata, dict):
        return []
    return _public_chunks(metadata.get("top_chunks", []) or [])


def _extract_terms(text: str) -> list[str]:
    normalized = text.lower().replace("-", " ")
    terms: list[str] = [phrase.replace("-", " ") for phrase in KNOWN_PHRASES if phrase.replace("-", " ") in normalized]
    tokens = [
        token.strip(".,:;()[]{}<>\"'`")
        for token in re.split(r"\s+", normalized)
        if len(token.strip(".,:;()[]{}<>\"'`")) >= 3
    ]
    tokens = [token for token in tokens if token not in STOP_TERMS and not token.isdigit()]
    for size in (3, 2):
        for index in range(0, max(0, len(tokens) - size + 1)):
            phrase = " ".join(tokens[index : index + size])
            if not any(part in STOP_TERMS for part in phrase.split()):
                terms.append(phrase)
    return terms


def _public_chunks(chunks: list[Any], limit: int = 3) -> list[dict[str, Any]]:
    public: list[dict[str, Any]] = []
    allowed = {"resource_title", "file_name", "snippet", "score", "source", "type", "chunk_index"}
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        public.append({key: _sanitize_value(chunk[key]) for key in allowed if key in chunk and chunk[key] not in {None, ""}})
        if len(public) >= limit:
            break
    return public


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for edge in edges:
        key = (str(edge.get("from", "")), str(edge.get("to", "")), str(edge.get("label", "")))
        if key in seen:
            continue
        seen.add(key)
        output.append(edge)
    return output


def _sanitize_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: _sanitize_value(value) for key, value in node.items()} for node in nodes]


def _sanitize_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{key: _sanitize_value(value) for key, value in edge.items()} for edge in edges]


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _sanitize_value(child) for key, child in value.items() if key != "text"}
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, str):
        return PRIVATE_PATH_RE.sub("[private local path]", value)
    return value


def _unique_labels(labels: list[str], limit: int) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for label in labels:
        clean = _clean_label(label)
        key = _norm(clean)
        if not clean or key in seen:
            continue
        seen.add(key)
        output.append(clean)
        if len(output) >= limit:
            break
    return output


def _clean_label(label: str) -> str:
    clean = re.sub(r"\s+", " ", str(label)).strip(" .,:;")
    if len(clean) > 72:
        return clean[:69].rstrip() + "..."
    return clean


def _norm(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip().lower())
