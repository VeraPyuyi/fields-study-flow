from __future__ import annotations

import copy
import json
import re
from html import escape
from pathlib import Path
from typing import Any

from fields_study_flow.artifact_templates import enforce_artifact_requirements, write_artifact_template
from fields_study_flow.models import LearnerProfile, Resource


OUTPUT_FILES = [
    "learner_profile.json",
    "resource_index.json",
    "local_resource_analysis.json",
    "source_registry_snapshot.json",
    "roadmap.md",
    "roadmap.json",
    "roadmap.svg",
    "roadmap.html",
]

PRIVATE_PATH_RE = re.compile(r"(?:file://[^\s)\]}\"'<]+|(?<![A-Za-z0-9])[A-Za-z]:[\\/][^)\]}\"'<\r\n]+|/(?:Users|home)/[^)\]}\"'<\r\n]+)")


def sanitize_roadmap_for_export(roadmap: dict[str, Any]) -> dict[str, Any]:
    """Return a shareable roadmap copy with private local paths redacted."""

    return _sanitize_private_values(copy.deepcopy(roadmap))


def _sanitize_private_values(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for child_key, child_value in value.items():
            if child_key == "local_path":
                sanitized[child_key] = None
            elif child_key == "url" and isinstance(child_value, str) and _contains_private_path(child_value):
                sanitized[child_key] = _safe_local_url(value)
            else:
                sanitized[child_key] = _sanitize_private_values(child_value)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_private_values(item) for item in value]
    if isinstance(value, str):
        return _redact_private_paths(value)
    return value


def _contains_private_path(value: str) -> bool:
    return bool(PRIVATE_PATH_RE.search(value))


def _redact_private_paths(value: str) -> str:
    if not _contains_private_path(value):
        return value
    return PRIVATE_PATH_RE.sub("[private local path]", value)


def _safe_local_url(resource: dict[str, Any]) -> str:
    metadata = resource.get("metadata")
    local_id = metadata.get("local_resource_id") if isinstance(metadata, dict) else None
    slug_source = local_id or resource.get("title") or "private-resource"
    return f"local://{_safe_slug(str(slug_source))}"


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "private-resource"


REPORT_LABELS: dict[str, tuple[str, str]] = {
    "goal": ("Goal", "目标"),
    "output_language": ("Output language", "输出语言"),
    "resource_language_preference": ("Resource language preference", "资料语言偏好"),
    "mastery_path_strategy": ("Mastery Path Strategy", "掌握路径策略"),
    "mode": ("Mode", "模式"),
    "target_kind": ("Target kind", "目标类型"),
    "learning_style": ("Learning style", "学习风格"),
    "mastery_standard": ("Mastery standard", "掌握标准"),
    "estimated_total_time": ("Estimated total time", "预计总耗时"),
    "selected_resources": ("Selected resources", "已选资源"),
    "resource_library": ("Learning Resource Library", "学习资料库"),
    "all_resources": ("All resources", "全部资料"),
    "resource_status": ("Route status", "路线状态"),
    "selected": ("selected", "已进入最短路线"),
    "generated_resource": ("generated", "自动生成"),
    "omitted": ("omitted", "未进入最短路线"),
    "phase": ("Phase", "阶段"),
    "reason": ("Reason", "原因"),
    "principle": ("Principle", "路线原则"),
    "paper_metadata": ("Paper Metadata", "论文元数据"),
    "title": ("Title", "标题"),
    "authors": ("Authors", "作者"),
    "status": ("Status", "状态"),
    "concepts": ("Concepts", "关键概念"),
    "sections": ("Sections", "章节"),
    "abstract": ("Abstract", "摘要"),
    "keywords": ("Keywords", "关键词"),
    "formula_candidates": ("Formula candidates", "公式候选"),
    "code_links": ("Code links", "代码链接"),
    "artifact_requirements": ("Artifact Requirements", "产物要求"),
    "requires_runnable_artifact": ("Requires runnable artifact", "需要可运行产物"),
    "runnable": ("Runnable", "可运行"),
    "policy": ("Policy", "策略"),
    "satisfied_by": ("Satisfied by", "满足资源"),
    "generated": ("Generated", "已生成"),
    "generated_artifacts": ("Generated artifacts", "已生成产物"),
    "artifact_gaps": ("Artifact Gaps", "产物缺口"),
    "resolved_by": ("Resolved by", "由此补足"),
    "phases": ("Phases", "阶段"),
    "source": ("Source", "来源"),
    "difficulty": ("Difficulty", "难度"),
    "time": ("Time", "耗时"),
    "trust": ("Trust", "可信度"),
    "critical_path_role": ("Critical path role", "关键路径角色"),
    "key_points": ("Key points", "学习关键点"),
    "focus": ("Focus", "重点"),
    "why": ("Why", "推荐理由"),
    "access": ("Access", "访问说明"),
    "translation": ("Translation", "翻译说明"),
    "final_artifact": ("Final Artifact", "最终产物"),
    "type": ("Type", "类型"),
    "evidence": ("Evidence", "验收证据"),
    "checkpoints": ("Checkpoints", "验收任务"),
    "safety_policy": ("Safety Policy", "安全边界"),
    "resources": ("Resources", "资源"),
    "total_time": ("Total time", "总耗时"),
    "mastery_graph": ("Mastery Graph", "掌握图谱"),
    "plan_quality": ("Plan Quality", "计划质量"),
    "route_audit": ("Route Audit", "路线审计"),
    "next_actions": ("Next Actions", "下一步行动"),
    "study_tasks": ("Study Tasks", "学习任务"),
    "coverage": ("Coverage", "覆盖度"),
    "readiness": ("Readiness", "路线可信度"),
    "coverage_gate": ("Coverage Gate", "覆盖门槛"),
    "recommended_action": ("Recommended action", "建议动作"),
    "omitted_resources": ("Omitted resources", "省略资源"),
    "level": ("Level", "等级"),
    "evidence": ("Evidence", "证据"),
    "live_search": ("Live search", "实时搜索"),
    "not_available": ("not available", "不可用"),
    "not_tagged": ("not tagged", "未标注"),
    "not_specified": ("not specified", "未指定"),
    "unknown": ("unknown", "未知"),
}


def _label(language: str, key: str) -> str:
    en, zh = REPORT_LABELS.get(key, (key.replace("_", " ").title(), key))
    if language == "zh-CN":
        return zh
    if language == "bilingual":
        return f"{en} / {zh}"
    return en


def _roadmap_language(roadmap: dict[str, Any]) -> str:
    return str(roadmap.get("profile", {}).get("output_language", "en"))


def _localized(profile: LearnerProfile, en: str, zh: str) -> str:
    if profile.output_language == "zh-CN":
        return zh
    if profile.output_language == "bilingual":
        return f"{en} / {zh}"
    return en


def build_roadmap(profile: LearnerProfile, resources: list[Resource], live_search: dict[str, Any] | None = None) -> dict[str, Any]:
    target_kind = _infer_target_kind(profile, resources)
    final_artifact = _final_artifact(profile, target_kind)
    selected_resources = _select_route_resources(profile, resources)
    selected_resources, artifact_requirements, artifact_gaps, generated_artifacts = enforce_artifact_requirements(
        profile,
        target_kind,
        final_artifact,
        selected_resources,
        resources,
    )
    selected_resources = _compress_short_route_prerequisites(profile, selected_resources)
    selected_resources = _trim_to_route_limit_after_artifacts(profile, selected_resources)
    phases = _build_phases(profile, selected_resources)
    total_minutes = sum(_resource_minutes(resource) or 0 for resource in selected_resources)
    candidate_count = len(resources) + sum(1 for resource in selected_resources if resource.metadata.get("generated_template"))
    mastery_graph = _mastery_graph(profile, selected_resources, target_kind, final_artifact)
    study_tasks = _study_tasks(profile, selected_resources, target_kind)
    route_audit = _route_audit(profile, resources, selected_resources, study_tasks)
    coverage_gate = _coverage_gate(profile, resources, route_audit, target_kind)
    if coverage_gate["status"] == "insufficient-evidence":
        final_artifact = _resource_discovery_artifact(profile)
        selected_resources = [_resource_discovery_checklist(profile, route_audit)]
        artifact_requirements = {
            "type": final_artifact["type"],
            "requires_runnable": False,
            "policy": "resource-discovery-first",
            "satisfied_by": [selected_resources[0].title],
            "evidence": final_artifact["evidence"],
        }
        artifact_gaps = _resource_gap_messages(profile, route_audit, resources)
        generated_artifacts = []
        phases = _build_phases(profile, selected_resources)
        total_minutes = sum(_resource_minutes(resource) or 0 for resource in selected_resources)
        mastery_graph = _mastery_graph(profile, selected_resources, target_kind, final_artifact)
        study_tasks = _resource_discovery_tasks(profile, route_audit)
        route_audit = _route_audit(profile, resources, selected_resources, study_tasks)
        route_audit["coverage_gate"] = coverage_gate
    else:
        route_audit["coverage_gate"] = coverage_gate
    resource_library = _resource_library(profile, resources, selected_resources, phases, route_audit)
    quality_report = _quality_report(profile, selected_resources, study_tasks, route_audit, artifact_requirements, generated_artifacts)
    next_actions = _next_actions(study_tasks)
    generated_selected_count = sum(
        1
        for resource in selected_resources
        if resource.metadata.get("generated_template")
        or resource.metadata.get("generated_prerequisite_sprint")
        or resource.metadata.get("generated_resource_discovery")
    )
    roadmap = {
        "title": _title(profile),
        "profile": profile.to_dict(),
        "path_strategy": {
            "mode": profile.route_depth,
            "route_depth": profile.route_depth,
            "target_kind": target_kind,
            "learning_style": profile.learning_style,
            "mastery_standard": "explain_derive_reproduce_critique",
            "principle": _strategy_principle(profile),
            "readiness": coverage_gate["status"],
            "estimated_total_minutes": total_minutes or None,
            "estimated_total_time": _format_minutes(total_minutes) if total_minutes else "unknown",
            "candidate_resources": len(resources) + generated_selected_count,
            "selected_resources": len(selected_resources),
        },
        "outputs": OUTPUT_FILES.copy() + generated_artifacts,
        "mastery_graph": mastery_graph,
        "study_tasks": study_tasks,
        "next_actions": next_actions,
        "resource_library": resource_library,
        "route_audit": route_audit,
        "quality_report": quality_report,
        "final_artifact": final_artifact,
        "artifact_requirements": artifact_requirements,
        "artifact_gaps": artifact_gaps,
        "generated_artifacts": generated_artifacts,
        "live_search": live_search or {"enabled": False, "status": "not_requested"},
        "phases": phases,
        "checkpoints": _checkpoints(profile),
        "safety_policy": _safety_policy(profile),
    }
    return sanitize_roadmap_for_export(roadmap)


def write_outputs(
    output_dir: Path,
    profile: LearnerProfile,
    ranked_resources: list[Resource],
    roadmap: dict[str, Any],
    source_registry_snapshot: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    public_roadmap = sanitize_roadmap_for_export(roadmap)
    (output_dir / "learner_profile.json").write_text(json.dumps(profile.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "resource_index.json").write_text(
        json.dumps([resource.to_dict() for resource in ranked_resources], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "local_resource_analysis.json").write_text(
        json.dumps([resource.to_dict() for resource in ranked_resources if resource.source == "local-library" or resource.local_path], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "source_registry_snapshot.json").write_text(json.dumps(source_registry_snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "roadmap.json").write_text(json.dumps(public_roadmap, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "roadmap.md").write_text(render_markdown(public_roadmap), encoding="utf-8")
    (output_dir / "roadmap.svg").write_text(render_svg(public_roadmap), encoding="utf-8")
    (output_dir / "roadmap.html").write_text(render_html(public_roadmap), encoding="utf-8")
    write_artifact_template(output_dir, public_roadmap)


def render_markdown(roadmap: dict[str, Any]) -> str:
    roadmap = sanitize_roadmap_for_export(roadmap)
    profile = roadmap["profile"]
    strategy = roadmap.get("path_strategy", {})
    language = _roadmap_language(roadmap)
    lines = [
        f"# {roadmap['title']}",
        "",
        f"- {_label(language, 'goal')}: {profile['goal']}",
        f"- {_label(language, 'output_language')}: {profile['output_language']}",
        f"- {_label(language, 'resource_language_preference')}: {profile['resource_language_preference']}",
        "",
        f"## {_label(language, 'mastery_path_strategy')}",
        "",
        f"- {_label(language, 'mode')}: {strategy.get('mode', 'balanced')}",
        f"- {_label(language, 'target_kind')}: {strategy.get('target_kind', 'auto')}",
        f"- {_label(language, 'learning_style')}: {strategy.get('learning_style', 'practical')}",
        f"- {_label(language, 'mastery_standard')}: {strategy.get('mastery_standard', 'explain_derive_reproduce_critique')}",
        f"- {_label(language, 'readiness')}: {strategy.get('readiness', 'ready')}",
        f"- {_label(language, 'estimated_total_time')}: {strategy.get('estimated_total_time', _label(language, 'unknown'))}",
        f"- {_label(language, 'selected_resources')}: {strategy.get('selected_resources', 0)} / {strategy.get('candidate_resources', 0)}",
        f"- {_label(language, 'principle')}: {strategy.get('principle', _label(language, 'not_specified'))}",
        "",
    ]
    quality_report = roadmap.get("quality_report", {})
    if quality_report:
        lines.extend([f"## {_label(language, 'plan_quality')}", ""])
        for name, item in quality_report.get("dimensions", {}).items():
            lines.append(f"- {name}: {item.get('level', 'unknown')} - {item.get('evidence', '')}")
        lines.append("")
    route_audit = roadmap.get("route_audit", {})
    if route_audit:
        lines.extend(
            [
                f"## {_label(language, 'route_audit')}",
                "",
                f"- {_label(language, 'coverage')}: {route_audit.get('coverage_ratio', 0):.2f}",
                f"- {_label(language, 'coverage_gate')}: {route_audit.get('coverage_gate', {}).get('status', 'ready')}",
                f"- {_label(language, 'recommended_action')}: {route_audit.get('coverage_gate', {}).get('recommended_action', _label(language, 'not_specified'))}",
                f"- {_label(language, 'omitted_resources')}: {len(route_audit.get('omitted_resources', []))}",
            ]
        )
        for omitted in route_audit.get("omitted_resources", [])[:5]:
            lines.append(f"  - {omitted.get('title', '')}: {omitted.get('reason', '')}")
        lines.append("")
    if roadmap.get("next_actions"):
        lines.extend([f"## {_label(language, 'next_actions')}", ""])
        for action in roadmap.get("next_actions", []):
            lines.append(f"- {action.get('title', '')}: {action.get('evidence', '')}")
        lines.append("")
    paper_metadata = _paper_metadata_from_roadmap(roadmap)
    if paper_metadata:
        lines.extend(
            [
                f"## {_label(language, 'paper_metadata')}",
                "",
                f"- {_label(language, 'title')}: {paper_metadata.get('title', _label(language, 'unknown'))}",
                f"- {_label(language, 'authors')}: {_join_or_unknown(paper_metadata.get('authors', []), language)}",
                f"- {_label(language, 'status')}: {paper_metadata.get('metadata_status', 'partial')}",
                f"- {_label(language, 'concepts')}: {_join_or_unknown(paper_metadata.get('concepts', []), language)}",
                f"- {_label(language, 'sections')}: {_join_or_unknown(paper_metadata.get('sections', []), language)}",
                f"- {_label(language, 'abstract')}: {paper_metadata.get('abstract_snippet', '') or _label(language, 'not_available')}",
                f"- {_label(language, 'keywords')}: {_join_or_unknown(paper_metadata.get('keywords', []), language)}",
                f"- {_label(language, 'formula_candidates')}: {_join_or_unknown(paper_metadata.get('formula_candidates', []), language)}",
                f"- {_label(language, 'code_links')}: {_join_or_unknown(paper_metadata.get('code_links', []), language)}",
                "",
            ]
        )
    artifact_requirements = roadmap.get("artifact_requirements", {})
    if artifact_requirements:
        lines.extend(
            [
                f"## {_label(language, 'artifact_requirements')}",
                "",
                f"- {_label(language, 'requires_runnable_artifact')}: {artifact_requirements.get('requires_runnable', False)}",
                f"- {_label(language, 'policy')}: {artifact_requirements.get('policy', 'not-required')}",
                f"- {_label(language, 'satisfied_by')}: {_join_or_unknown(artifact_requirements.get('satisfied_by', []), language)}",
                f"- {_label(language, 'generated_artifacts')}: {_join_or_unknown(roadmap.get('generated_artifacts', []), language)}",
                "",
            ]
        )
    artifact_gaps = roadmap.get("artifact_gaps", [])
    if artifact_gaps:
        lines.extend([f"## {_label(language, 'artifact_gaps')}", ""])
        for gap in artifact_gaps:
            lines.extend(
                [
                    f"- {gap.get('status', 'open')}: {gap.get('message', '')}",
                    f"  - {_label(language, 'resolved_by')}: {gap.get('resolved_by', _label(language, 'not_available'))}",
                ]
            )
        lines.append("")
    resource_library = roadmap.get("resource_library", [])
    if resource_library:
        lines.extend([f"## {_label(language, 'resource_library')}", ""])
        selected_count = sum(1 for resource in resource_library if resource.get("selected"))
        lines.append(f"- {_label(language, 'all_resources')}: {len(resource_library)}")
        lines.append(f"- {_label(language, 'selected_resources')}: {selected_count} / {len(resource_library)}")
        lines.append("")
        for resource in resource_library:
            route_status = str(resource.get("route_status", "omitted"))
            status_label = _route_status_label(language, route_status)
            phase = resource.get("selected_phase") or _label(language, "not_available")
            reason = resource.get("route_reason") or _label(language, "not_specified")
            lines.extend(
                [
                    f"- [{resource.get('title', 'Resource')}]({resource.get('url', '#')})",
                    f"  - {_label(language, 'resource_status')}: {status_label}",
                    f"  - {_label(language, 'source')}: {resource.get('source', _label(language, 'unknown'))} / {resource.get('type', _label(language, 'unknown'))} / {resource.get('language', _label(language, 'unknown'))}",
                    f"  - {_label(language, 'phase')}: {phase}",
                    f"  - {_label(language, 'reason')}: {reason}",
                    f"  - {_label(language, 'difficulty')}: {resource.get('difficulty', _label(language, 'unknown'))} | {_label(language, 'time')}: {resource.get('estimated_time', _label(language, 'unknown'))} | {_label(language, 'trust')}: {resource.get('trust_score', _label(language, 'unknown'))}",
                    f"  - {_label(language, 'concepts')}: {', '.join(resource.get('concepts', [])) or _label(language, 'not_tagged')}",
                    f"  - {_label(language, 'key_points')}: {', '.join(resource.get('learning_key_points', [])) or _label(language, 'not_tagged')}",
                    f"  - {_label(language, 'focus')}: {', '.join(resource.get('focus_areas', [])) or _label(language, 'not_tagged')}",
                    f"  - {_label(language, 'why')}: {resource.get('why_recommended', '')}",
                    f"  - {_label(language, 'access')}: {resource.get('license_or_access_note', '')}",
                ]
            )
        lines.append("")
    lines.extend([f"## {_label(language, 'phases')}", ""])
    for phase in roadmap["phases"]:
        lines.extend([f"### {phase['name']}", phase["objective"], ""])
        if not phase["resources"]:
            lines.append("- No resources selected yet; add sources with `fields-study-flow ingest-url` or `--local-resource`.")
        for resource in phase["resources"]:
            lines.extend(
                [
                    f"- [{resource['title']}]({resource['url']})",
                    f"  - {_label(language, 'source')}: {resource['source']} / {resource['type']} / {resource['language']}",
                    f"  - {_label(language, 'difficulty')}: {resource['difficulty']} | {_label(language, 'time')}: {resource['estimated_time']} | {_label(language, 'trust')}: {resource['trust_score']}",
                    f"  - {_label(language, 'critical_path_role')}: {resource.get('critical_path_role', 'support')}",
                    f"  - {_label(language, 'concepts')}: {', '.join(resource['concepts']) or _label(language, 'not_tagged')}",
                    f"  - {_label(language, 'key_points')}: {', '.join(resource.get('learning_key_points', [])) or _label(language, 'not_tagged')}",
                    f"  - {_label(language, 'focus')}: {', '.join(resource.get('focus_areas', [])) or _label(language, 'not_tagged')}",
                    f"  - {_label(language, 'why')}: {resource['why_recommended']}",
                    f"  - {_label(language, 'access')}: {resource['license_or_access_note']}",
                    f"  - {_label(language, 'translation')}: {resource['translation_note']}",
                ]
            )
        lines.append("")
    artifact = roadmap.get("final_artifact", {})
    if artifact:
        lines.extend(
            [
                f"## {_label(language, 'final_artifact')}",
                "",
                f"- {_label(language, 'type')}: {artifact.get('type', _label(language, 'unknown'))}",
                f"- {_label(language, 'evidence')}: {artifact.get('evidence', _label(language, 'not_specified'))}",
                "",
            ]
        )
    lines.extend([f"## {_label(language, 'checkpoints')}", ""])
    for checkpoint in roadmap["checkpoints"]:
        lines.append(f"- {checkpoint}")
    lines.extend(["", f"## {_label(language, 'safety_policy')}", ""])
    for policy in roadmap["safety_policy"]:
        lines.append(f"- {policy}")
    lines.append("")
    return "\n".join(lines)


def _paper_metadata_from_roadmap(roadmap: dict[str, Any]) -> dict[str, Any]:
    for phase in roadmap.get("phases", []):
        for resource in phase.get("resources", []):
            metadata = resource.get("metadata", {})
            paper_metadata = metadata.get("paper_metadata")
            if metadata.get("target_paper") and isinstance(paper_metadata, dict):
                safe = dict(paper_metadata)
                safe["local_path"] = None
                return safe
    return {}


def _join_or_unknown(values: Any, language: str = "en") -> str:
    if not values:
        return _label(language, "not_available")
    if isinstance(values, str):
        return values
    return ", ".join(str(value) for value in values if value) or _label(language, "not_available")


def _route_status_label(language: str, status: str) -> str:
    if status == "selected":
        return _label(language, "selected")
    if status == "generated":
        return _label(language, "generated_resource")
    return _label(language, "omitted")


def render_svg(roadmap: dict[str, Any]) -> str:
    roadmap = sanitize_roadmap_for_export(roadmap)
    language = _roadmap_language(roadmap)
    phases = roadmap.get("phases", [])
    width = 1180
    phase_height = 176
    paper_metadata = _paper_metadata_from_roadmap(roadmap)
    artifact_requirements = roadmap.get("artifact_requirements", {})
    generated_artifacts = roadmap.get("generated_artifacts", [])
    artifact_gaps = roadmap.get("artifact_gaps", [])
    quality_report = roadmap.get("quality_report", {})
    has_summary_panels = bool(paper_metadata or artifact_requirements)
    summary_panel_height = 118 if has_summary_panels else 0
    phase_start_y = 125 + summary_panel_height
    height = max(540, 176 + summary_panel_height + len(phases) * phase_height)
    colors = ["#62A9D9", "#85C996", "#9F8FE8", "#F3C85E"]
    strategy = roadmap.get("path_strategy", {})
    summary = (
        f"{_label(language, 'mode')}: {strategy.get('mode', 'balanced')} | "
        f"{strategy.get('estimated_total_time', 'unknown')} | "
        f"{strategy.get('selected_resources', 0)}/{strategy.get('candidate_resources', 0)} {_label(language, 'resources')}"
    )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "text{font-family:Arial,'Microsoft YaHei',sans-serif;fill:#172033}",
        ".muted{fill:#687287}.tiny{font-size:13px}.small{font-size:15px}.title{font-size:28px;font-weight:700}.phase{font-size:19px;font-weight:700}",
        "</style>",
        f'<rect width="{width}" height="{height}" rx="24" fill="#F7FAFD"/>',
        f'<text x="48" y="58" class="title">{_svg_escape(_truncate(roadmap.get("title", "Learning Roadmap"), 70))}</text>',
        f'<rect x="724" y="28" width="418" height="48" rx="18" fill="#FFFFFF" stroke="#D4DEE9"/>',
        f'<text x="933" y="58" class="small" text-anchor="middle" fill="#4F9FD8" font-weight="700">{_svg_escape(summary)}</text>',
        '<line x1="48" y1="92" x2="1132" y2="92" stroke="#D8E1EC" stroke-width="2"/>',
    ]
    if has_summary_panels:
        if paper_metadata:
            parts.extend(
                [
                    '<rect x="48" y="108" width="520" height="92" rx="14" fill="#FFFFFF" stroke="#9F8FE8" stroke-width="2"/>',
                    f'<text x="66" y="136" class="phase">{_svg_escape(_truncate(_label(language, "paper_metadata"), 34))}</text>',
                    f'<text x="66" y="160" class="small muted">{_svg_escape(_truncate(str(paper_metadata.get("title", "unknown")), 58))}</text>',
                    f'<text x="66" y="182" class="tiny muted">{_svg_escape(_label(language, "concepts"))}: {_svg_escape(_truncate(_join_or_unknown(paper_metadata.get("concepts", []), language), 56))}</text>',
                ]
            )
        if artifact_requirements:
            generated = _join_or_unknown(generated_artifacts, language)
            gap_status = _join_or_unknown([gap.get("status") for gap in artifact_gaps if isinstance(gap, dict)], language)
            parts.extend(
                [
                    '<rect x="588" y="108" width="544" height="92" rx="14" fill="#FFFFFF" stroke="#85C996" stroke-width="2"/>',
                    f'<text x="606" y="136" class="phase">{_svg_escape(_truncate(_label(language, "artifact_requirements"), 34))}</text>',
                    f'<text x="606" y="160" class="small muted">{_svg_escape(_label(language, "policy"))}: {_svg_escape(_truncate(str(artifact_requirements.get("policy", "not-required")), 38))}</text>',
                    f'<text x="606" y="182" class="tiny muted">{_svg_escape(_label(language, "generated"))}: {_svg_escape(_truncate(generated, 34))} | {_svg_escape(_label(language, "artifact_gaps"))}: {_svg_escape(_truncate(gap_status, 18))}</text>',
                    f'<text x="606" y="197" class="tiny muted">{_svg_escape(_label(language, "plan_quality"))}: {_svg_escape(str(quality_report.get("overall", "unknown")))}</text>',
                ]
            )

    for index, phase in enumerate(phases):
        y = phase_start_y + index * phase_height
        color = colors[index % len(colors)]
        resources = phase.get("resources", [])
        parts.extend(
            [
                f'<rect x="48" y="{y}" width="1084" height="{phase_height - 28}" rx="18" fill="#FFFFFF" stroke="{color}" stroke-width="2"/>',
                f'<circle cx="82" cy="{y + 30}" r="18" fill="{color}"/>',
                f'<text x="82" y="{y + 36}" fill="#FFFFFF" font-size="17" font-weight="700" text-anchor="middle">{index + 1}</text>',
                f'<text x="112" y="{y + 36}" class="phase">{_svg_escape(_truncate(phase.get("name", "Phase"), 60))}</text>',
                f'<text x="112" y="{y + 62}" class="small muted">{_svg_escape(_truncate(phase.get("objective", ""), 112))}</text>',
                f'<text x="1000" y="{y + 36}" class="small muted" text-anchor="end">{_svg_escape(phase.get("estimated_time", "unknown"))}</text>',
            ]
        )
        card_width = 330
        for resource_index, resource in enumerate(resources[:3]):
            x = 78 + resource_index * (card_width + 28)
            cy = y + 82
            local_badge = "LOCAL" if resource.get("source") == "local-library" else resource.get("source", "")
            key_points = ", ".join(resource.get("learning_key_points", [])[:2]) or "key points"
            focus = ", ".join(resource.get("focus_areas", [])[:2]) or "focus"
            parts.extend(
                [
                    f'<rect x="{x}" y="{cy}" width="{card_width}" height="72" rx="12" fill="#F8FAFF" stroke="#DCE5F2"/>',
                    f'<text x="{x + 16}" y="{cy + 24}" class="small" font-weight="700">{_svg_escape(_truncate(resource.get("title", "Resource"), 36))}</text>',
                    f'<text x="{x + 16}" y="{cy + 44}" class="tiny muted">{_svg_escape(resource.get("critical_path_role", "support"))} | {_svg_escape(resource.get("estimated_time", "unknown"))} | {_svg_escape(local_badge)}</text>',
                    f'<text x="{x + 16}" y="{cy + 64}" class="tiny muted">{_svg_escape(_truncate(key_points + " -> " + focus, 46))}</text>',
                ]
            )
    parts.append("</svg>")
    return "\n".join(parts)


def render_html(roadmap: dict[str, Any]) -> str:
    roadmap = sanitize_roadmap_for_export(roadmap)
    language = _roadmap_language(roadmap)
    strategy = roadmap.get("path_strategy", {})
    profile = roadmap.get("profile", {})
    graph = roadmap.get("mastery_graph", {})
    artifact = roadmap.get("final_artifact", {})
    live_search = roadmap.get("live_search", {})
    title = escape(str(roadmap.get("title", "Learning Roadmap")))
    paper_metadata = _paper_metadata_from_roadmap(roadmap)
    artifact_requirements = roadmap.get("artifact_requirements", {})
    generated_artifacts = roadmap.get("generated_artifacts", [])
    artifact_gaps = roadmap.get("artifact_gaps", [])
    paper_panel = ""
    if paper_metadata:
        paper_panel = f"""
        <section class="graph-panel paper-metadata-panel">
          <h2>{escape(_label(language, 'paper_metadata'))}</h2>
          <div class="info-grid">
            <div><b>{escape(_label(language, 'title'))}</b><span>{escape(str(paper_metadata.get('title', _label(language, 'unknown'))))}</span></div>
            <div><b>{escape(_label(language, 'authors'))}</b><span>{escape(_join_or_unknown(paper_metadata.get('authors', []), language))}</span></div>
            <div><b>{escape(_label(language, 'status'))}</b><span>{escape(str(paper_metadata.get('metadata_status', 'partial')))}</span></div>
            <div><b>{escape(_label(language, 'concepts'))}</b><span>{escape(_join_or_unknown(paper_metadata.get('concepts', []), language))}</span></div>
          </div>
          <p class="meta">{escape(str(paper_metadata.get('abstract_snippet', '') or _label(language, 'not_available')))}</p>
          <p class="meta"><strong>{escape(_label(language, 'sections'))}:</strong> {escape(_join_or_unknown(paper_metadata.get('sections', []), language))}</p>
          <p class="meta"><strong>{escape(_label(language, 'keywords'))}:</strong> {escape(_join_or_unknown(paper_metadata.get('keywords', []), language))}</p>
          <p class="meta"><strong>{escape(_label(language, 'formula_candidates'))}:</strong> {escape(_join_or_unknown(paper_metadata.get('formula_candidates', []), language))}</p>
          <p class="meta"><strong>{escape(_label(language, 'code_links'))}:</strong> {escape(_join_or_unknown(paper_metadata.get('code_links', []), language))}</p>
        </section>
        """
    artifact_panel = ""
    if artifact_requirements:
        artifact_panel = f"""
        <section class="graph-panel artifact-panel">
          <h2>{escape(_label(language, 'artifact_requirements'))}</h2>
          <div class="info-grid">
            <div><b>{escape(_label(language, 'runnable'))}</b><span>{escape(str(artifact_requirements.get('requires_runnable', False)))}</span></div>
            <div><b>{escape(_label(language, 'policy'))}</b><span>{escape(str(artifact_requirements.get('policy', 'not-required')))}</span></div>
            <div><b>{escape(_label(language, 'satisfied_by'))}</b><span>{escape(_join_or_unknown(artifact_requirements.get('satisfied_by', []), language))}</span></div>
            <div><b>{escape(_label(language, 'generated'))}</b><span>{escape(_join_or_unknown(generated_artifacts, language))}</span></div>
          </div>
        </section>
        """
    gaps_panel = ""
    if artifact_gaps:
        gap_items = "".join(
            f"<li><strong>{escape(str(gap.get('status', 'open')))}</strong>: {escape(str(gap.get('message', '')))} <span class=\"meta\">{escape(_label(language, 'resolved_by'))} {escape(str(gap.get('resolved_by', _label(language, 'not_available'))))}</span></li>"
            for gap in artifact_gaps
            if isinstance(gap, dict)
        )
        gaps_panel = f"""
        <section class="graph-panel artifact-gaps-panel">
          <h2>{escape(_label(language, 'artifact_gaps'))}</h2>
          <ul>{gap_items}</ul>
        </section>
        """

    quality_panel = ""
    quality_report = roadmap.get("quality_report", {})
    if quality_report:
        quality_items = "".join(
            f"<li><strong>{escape(str(name))}</strong>: {escape(str(item.get('level', 'unknown')))} <span class=\"meta\">{escape(str(item.get('evidence', '')))}</span></li>"
            for name, item in quality_report.get("dimensions", {}).items()
            if isinstance(item, dict)
        )
        quality_panel = f"""
        <section class="graph-panel quality-panel">
          <h2>{escape(_label(language, 'plan_quality'))}</h2>
          <ul>{quality_items}</ul>
        </section>
        """

    route_panel = ""
    route_audit = roadmap.get("route_audit", {})
    if route_audit:
        omitted_items = "".join(
            f"<li><strong>{escape(str(item.get('title', '')))}</strong>: {escape(str(item.get('reason', '')))}</li>"
            for item in route_audit.get("omitted_resources", [])[:6]
            if isinstance(item, dict)
        )
        route_panel = f"""
        <section class="graph-panel route-audit-panel">
          <h2>{escape(_label(language, 'route_audit'))}</h2>
          <p class="meta">{escape(_label(language, 'coverage'))}: {escape(f"{route_audit.get('coverage_ratio', 0):.2f}")}</p>
          <p class="meta">{escape(_label(language, 'coverage_gate'))}: {escape(str(route_audit.get('coverage_gate', {}).get('status', 'ready')))}</p>
          <p class="meta">{escape(_label(language, 'recommended_action'))}: {escape(str(route_audit.get('coverage_gate', {}).get('recommended_action', _label(language, 'not_specified'))))}</p>
          <ul>{omitted_items or f'<li>{escape(_label(language, "not_available"))}</li>'}</ul>
        </section>
        """

    next_actions_panel = ""
    if roadmap.get("next_actions"):
        action_items = "".join(
            f"<li><strong>{escape(str(action.get('title', '')))}</strong> <span class=\"meta\">{escape(str(action.get('evidence', '')))}</span></li>"
            for action in roadmap.get("next_actions", [])
            if isinstance(action, dict)
        )
        next_actions_panel = f"""
        <section class="graph-panel next-actions-panel">
          <h2>{escape(_label(language, 'next_actions'))}</h2>
          <ol>{action_items}</ol>
        </section>
        """

    resource_library_panel = ""
    resource_library = roadmap.get("resource_library", [])
    if resource_library:
        library_cards: list[str] = []
        for resource in resource_library:
            route_status = str(resource.get("route_status", "omitted"))
            status_label = _route_status_label(language, route_status)
            phase = resource.get("selected_phase") or _label(language, "not_available")
            reason = resource.get("route_reason") or _label(language, "not_specified")
            concepts = ", ".join(str(item) for item in resource.get("concepts", [])[:6]) or _label(language, "not_tagged")
            key_points = "".join(f"<li>{escape(str(item))}</li>" for item in resource.get("learning_key_points", [])[:3])
            focus = ", ".join(str(item) for item in resource.get("focus_areas", [])[:5]) or _label(language, "not_tagged")
            library_cards.append(
                f"""
                <article class="library-card">
                  <div class="resource-head">
                    <h3><a href="{escape(str(resource.get('url', '#')))}">{escape(str(resource.get('title', 'Resource')))}</a></h3>
                    <span class="badge {escape(route_status)}">{escape(status_label)}</span>
                  </div>
                  <p class="meta">{escape(str(resource.get('source', _label(language, 'unknown'))))} / {escape(str(resource.get('type', _label(language, 'unknown'))))} / {escape(str(resource.get('language', _label(language, 'unknown'))))} / {escape(str(resource.get('estimated_time', _label(language, 'unknown'))))}</p>
                  <p class="meta"><strong>{escape(_label(language, 'phase'))}:</strong> {escape(str(phase))}</p>
                  <p class="meta"><strong>{escape(_label(language, 'reason'))}:</strong> {escape(str(reason))}</p>
                  <p class="meta"><strong>{escape(_label(language, 'concepts'))}:</strong> {escape(concepts)}</p>
                  <p class="meta"><strong>{escape(_label(language, 'focus'))}:</strong> {escape(focus)}</p>
                  <ul>{key_points or f'<li>{escape(_label(language, "not_tagged"))}</li>'}</ul>
                </article>
                """
            )
        selected_count = sum(1 for resource in resource_library if isinstance(resource, dict) and resource.get("selected"))
        resource_library_panel = f"""
        <section class="graph-panel resource-library-panel">
          <div class="phase-title-row">
            <h2>{escape(_label(language, 'resource_library'))}</h2>
            <span class="meta">{escape(_label(language, 'selected_resources'))}: {escape(str(selected_count))} / {escape(str(len(resource_library)))}</span>
          </div>
          <div class="library-grid">{''.join(library_cards)}</div>
        </section>
        """

    phase_cards: list[str] = []
    for phase_index, phase in enumerate(roadmap.get("phases", []), start=1):
        resource_cards = []
        for resource in phase.get("resources", []):
            key_points = "".join(f"<li>{escape(str(item))}</li>" for item in resource.get("learning_key_points", [])[:4])
            focus = "".join(f"<li>{escape(str(item))}</li>" for item in resource.get("focus_areas", [])[:4])
            local_badge = '<span class="badge local">LOCAL</span>' if resource.get("source") == "local-library" else ""
            resource_cards.append(
                f"""
                <article class="resource-card">
                  <div class="resource-head">
                    <h3><a href="{escape(str(resource.get('url', '#')))}">{escape(str(resource.get('title', 'Resource')))}</a></h3>
                    {local_badge}<span class="badge">{escape(str(resource.get('critical_path_role', 'support')))}</span>
                  </div>
                  <p class="meta">{escape(str(resource.get('source', _label(language, 'unknown'))))} / {escape(str(resource.get('type', _label(language, 'unknown'))))} / {escape(str(resource.get('language', _label(language, 'unknown'))))} / {escape(str(resource.get('estimated_time', _label(language, 'unknown'))))}</p>
                  <div class="mini-grid">
                    <section><strong>{escape(_label(language, 'key_points'))}</strong><ul>{key_points or f'<li>{escape(_label(language, "not_tagged"))}</li>'}</ul></section>
                    <section><strong>{escape(_label(language, 'focus'))}</strong><ul>{focus or f'<li>{escape(_label(language, "not_tagged"))}</li>'}</ul></section>
                  </div>
                  <p class="why">{escape(str(resource.get('why_recommended', '')))}</p>
                </article>
                """
            )
        phase_cards.append(
            f"""
            <section class="phase-card">
              <div class="phase-number">{phase_index}</div>
              <div class="phase-body">
                <div class="phase-title-row">
                  <h2>{escape(str(phase.get('name', 'Phase')))}</h2>
                  <span>{escape(str(phase.get('estimated_time', 'unknown')))}</span>
                </div>
                <p>{escape(str(phase.get('objective', '')))}</p>
                <div class="resource-grid">{''.join(resource_cards) or f'<p class="empty">{escape(_label(language, "not_available"))}</p>'}</div>
              </div>
            </section>
            """
        )

    checkpoints = "".join(f"<li>{escape(str(item))}</li>" for item in roadmap.get("checkpoints", []))
    graph_nodes = "".join(
        f"<span class=\"graph-pill {escape(str(node.get('kind', 'node')))}\">{escape(str(node.get('label', 'node')))}</span>"
        for node in graph.get("nodes", [])[:18]
    )
    manual_sources = ", ".join(live_search.get("manual_link_only_sources", []) or [])
    manual_note = f"; manual-link-only: {escape(manual_sources)}" if manual_sources else ""
    html_lang = "zh-CN" if language == "zh-CN" else "en"

    return f"""<!doctype html>
<html lang="{html_lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <style>
    :root {{
      --ink:#172033; --muted:#657085; --line:#d9e3ef; --paper:#f7fafd;
      --blue:#4f9fd8; --green:#70bd82; --purple:#8f7ce8; --gold:#e8bc45;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0; font-family:Arial,"Microsoft YaHei",sans-serif; color:var(--ink);
      background:linear-gradient(180deg,#fbfdff 0%,#f1f6fb 100%);
      overflow-wrap:anywhere; word-break:break-word;
    }}
    h1, h2, h3, p, li, span, a {{ overflow-wrap:anywhere; word-break:break-word; }}
    main {{ max-width:1180px; margin:0 auto; padding:28px clamp(16px,3vw,34px) 42px; }}
    header {{ border-bottom:2px solid var(--line); padding-bottom:18px; margin-bottom:22px; }}
    h1 {{ margin:0 0 12px; font-size:clamp(26px,4vw,42px); line-height:1.08; letter-spacing:0; }}
    .summary-grid, .roadmap-grid {{ display:grid; gap:14px; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); }}
    .summary-card, .phase-card, .graph-panel {{
      background:#fff; border:1px solid var(--line); border-radius:8px; box-shadow:0 10px 28px rgba(44,72,105,.08);
    }}
    .summary-card {{ padding:14px 16px; min-width:0; }}
    .summary-card b {{ display:block; color:var(--muted); font-size:12px; text-transform:uppercase; margin-bottom:6px; }}
    .summary-card span {{ display:block; font-size:17px; font-weight:700; }}
    .roadmap-grid {{ margin-top:18px; }}
    .phase-card {{ display:grid; grid-template-columns:54px minmax(0,1fr); gap:0; overflow:hidden; }}
    .phase-number {{ display:grid; place-items:center; color:#fff; font-weight:800; font-size:22px; background:var(--blue); }}
    .phase-card:nth-child(2n) .phase-number {{ background:var(--green); }}
    .phase-card:nth-child(3n) .phase-number {{ background:var(--purple); }}
    .phase-body {{ min-width:0; padding:18px; }}
    .phase-title-row {{ display:flex; align-items:flex-start; justify-content:space-between; gap:12px; flex-wrap:wrap; }}
    h2 {{ margin:0; font-size:22px; line-height:1.2; letter-spacing:0; }}
    .phase-body p, .meta, .why {{ color:var(--muted); line-height:1.5; }}
    .resource-grid, .library-grid {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); margin-top:14px; }}
    .library-grid {{ grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); }}
    .resource-card, .library-card {{ min-width:0; border:1px solid #e4ebf4; background:#f9fbff; border-radius:8px; padding:14px; }}
    .resource-head {{ display:flex; align-items:flex-start; gap:8px; flex-wrap:wrap; }}
    h3 {{ flex:1 1 170px; min-width:0; margin:0; font-size:17px; line-height:1.25; letter-spacing:0; }}
    a {{ color:#255f9f; text-decoration:none; }}
    .badge {{ display:inline-flex; align-items:center; min-height:24px; padding:3px 8px; border-radius:999px; background:#eef4fb; color:#41607e; font-size:12px; font-weight:700; }}
    .badge.local {{ background:#e7f6ec; color:#247144; }}
    .badge.selected {{ background:#e7f6ec; color:#247144; }}
    .badge.generated {{ background:#fff4d7; color:#7a5a00; }}
    .badge.omitted {{ background:#f1f4f8; color:#647085; }}
    .mini-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); gap:10px; }}
    ul {{ margin:6px 0 0; padding-left:18px; }}
    li {{ margin:4px 0; line-height:1.42; }}
    .graph-panel {{ margin-top:16px; padding:16px; }}
    .info-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(190px,1fr)); gap:10px; }}
    .info-grid div {{ min-width:0; padding:10px 12px; border:1px solid #e4ebf4; border-radius:8px; background:#f9fbff; }}
    .info-grid b {{ display:block; color:var(--muted); font-size:12px; text-transform:uppercase; margin-bottom:5px; }}
    .info-grid span {{ display:block; font-weight:700; line-height:1.35; }}
    .graph-pills {{ display:flex; flex-wrap:wrap; gap:8px; }}
    .graph-pill {{ padding:7px 10px; border-radius:8px; background:#eef4fb; font-size:13px; font-weight:700; }}
    .graph-pill.resource {{ background:#e8f4ff; }} .graph-pill.task {{ background:#fff4d7; }} .graph-pill.assessment {{ background:#eee9ff; }}
    .empty {{ margin:0; color:var(--muted); }}
    @media (max-width:640px) {{
      main {{ padding-inline:12px; }}
      h1 {{ font-size:24px; line-height:1.16; }}
      .phase-card {{ grid-template-columns:42px minmax(0,1fr); }}
      .phase-body {{ padding:14px; }}
      .resource-grid, .library-grid {{ grid-template-columns:1fr; }}
    }}
    @media (max-width:520px) {{
      .summary-grid, .info-grid, .mini-grid {{ grid-template-columns:1fr; }}
      .graph-panel {{ padding:14px; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <h1>{title}</h1>
    <div class="summary-grid">
      <div class="summary-card"><b>{escape(_label(language, 'goal'))}</b><span>{escape(str(profile.get('goal', '')))}</span></div>
      <div class="summary-card"><b>{escape(_label(language, 'mode'))}</b><span>{escape(str(strategy.get('mode', 'balanced')))} / {escape(str(strategy.get('target_kind', 'auto')))}</span></div>
      <div class="summary-card"><b>{escape(_label(language, 'readiness'))}</b><span>{escape(str(strategy.get('readiness', 'ready')))}</span></div>
      <div class="summary-card"><b>{escape(_label(language, 'total_time'))}</b><span>{escape(str(strategy.get('estimated_total_time', _label(language, 'unknown'))))}</span></div>
      <div class="summary-card"><b>{escape(_label(language, 'resources'))}</b><span>{escape(str(strategy.get('selected_resources', 0)))} / {escape(str(strategy.get('candidate_resources', 0)))}</span></div>
    </div>
  </header>
  {paper_panel}
  {artifact_panel}
  {gaps_panel}
  {quality_panel}
  {route_panel}
  {next_actions_panel}
  {resource_library_panel}
  <section class="graph-panel">
    <h2>{escape(_label(language, 'mastery_graph'))}</h2>
    <p>{escape(str(strategy.get('principle', '')))}</p>
    <div class="graph-pills">{graph_nodes}</div>
  </section>
  <div class="roadmap-grid">{''.join(phase_cards)}</div>
  <section class="graph-panel">
    <h2>{escape(_label(language, 'final_artifact'))}</h2>
    <p><strong>{escape(str(artifact.get('type', 'unknown')))}</strong>: {escape(str(artifact.get('evidence', '')))}</p>
    <h2>{escape(_label(language, 'checkpoints'))}</h2>
    <ul>{checkpoints}</ul>
    <p class="meta">{escape(_label(language, 'live_search'))}: {escape(str(live_search.get('status', 'not_requested')))}{manual_note}</p>
  </section>
</main>
</body>
</html>
"""


def _build_phases(profile: LearnerProfile, resources: list[Resource]) -> list[dict[str, Any]]:
    if not resources:
        return [
            {
                "name": _phase_name(profile, "Phase 1", "阶段 1", "Foundation", "基础"),
                "objective": _objective(profile, "Establish prerequisites before collecting resources.", "先补齐关键前置知识，再继续收集资源。"),
                "resources": [],
            }
        ]
    buckets = [
        ("Foundation", "基础", "Build only the prerequisites that unblock the target.", "只补齐能解锁目标的前置知识。", {"prerequisite"}),
        ("Core Understanding", "核心理解", "Study the target paper or core concepts with the fewest high-yield resources.", "用少量高收益资料理解论文或核心概念。", {"core-paper", "focused-support", "support"}),
        ("Practice and Reproduction", "实践复现", "Validate mastery through the smallest runnable or derivation checkpoint.", "用最小可运行复现、推导或项目检查点验证掌握。", {"practice-validation"}),
    ]
    phases: list[dict[str, Any]] = []
    used_ids: set[int] = set()
    for index, (en_name, zh_name, en_obj, zh_obj, roles) in enumerate(buckets):
        chunk = [resource for resource in resources if resource.critical_path_role in roles]
        if index == 1:
            chunk_ids = {id(resource) for resource in chunk}
            chunk.extend(
                resource
                for resource in resources
                if id(resource) not in used_ids and id(resource) not in chunk_ids and resource.critical_path_role not in {"prerequisite", "practice-validation"}
            )
        used_ids.update(id(resource) for resource in chunk)
        if not chunk:
            continue
        minutes = sum(_resource_minutes(resource) or 0 for resource in chunk)
        phases.append(
            {
                "name": _phase_name(profile, f"Phase {index + 1}", f"阶段 {index + 1}", en_name, zh_name),
                "objective": _objective(profile, en_obj, zh_obj),
                "estimated_minutes": minutes or None,
                "estimated_time": _format_minutes(minutes) if minutes else "unknown",
                "resources": [resource.to_dict() for resource in chunk],
            }
        )
    return phases


def _title(profile: LearnerProfile) -> str:
    if profile.output_language == "bilingual":
        return f"Learning Roadmap / 学习路线: {profile.goal}"
    if profile.output_language == "en":
        return f"Learning Roadmap: {profile.goal}"
    return f"学习路线: {profile.goal}"


def _phase_name(profile: LearnerProfile, prefix_en: str, prefix_zh: str, name_en: str, name_zh: str | None = None) -> str:
    name_zh = name_zh or name_en
    if profile.output_language == "bilingual":
        return f"{prefix_en} / {prefix_zh}: {name_en} / {name_zh}"
    if profile.output_language == "en":
        return f"{prefix_en}: {name_en}"
    return f"{prefix_zh}: {name_zh}"


def _objective(profile: LearnerProfile, en: str, zh: str) -> str:
    if profile.output_language == "bilingual":
        return f"{en} / {zh}"
    if profile.output_language == "en":
        return en
    return zh


def _checkpoints(profile: LearnerProfile) -> list[str]:
    if profile.output_language == "en":
        return [
            "Explain the core idea, assumptions, and contribution without notes.",
            "Derive one key equation, proof step, or mechanism.",
            "Reproduce a minimal implementation, experiment, or project checkpoint.",
            "Critique limitations, failure modes, and when to use the method.",
        ]
    if profile.output_language == "bilingual":
        return [
            "Explain the core idea, assumptions, and contribution without notes. / 不看笔记讲清核心思想、假设和贡献。",
            "Derive one key equation, proof step, or mechanism. / 推导一个关键公式、证明步骤或机制。",
            "Reproduce a minimal implementation, experiment, or project checkpoint. / 复现一个最小实现、实验或项目检查点。",
            "Critique limitations, failure modes, and when to use the method. / 批判局限、失败模式和适用边界。",
        ]
    return [
        "不看笔记讲清核心思想、假设和贡献。",
        "推导一个关键公式、证明步骤或机制。",
        "复现一个最小实现、实验或项目检查点。",
        "批判局限、失败模式和适用边界。",
    ]


def _strategy_principle(profile: LearnerProfile) -> str:
    if profile.route_depth == "fastest":
        return _localized(profile, "Choose the minimum resource set that can still pass explain, derive, reproduce, and critique checkpoints.", "选择仍能通过讲解、推导、复现、批判验收的最小资源集。")
    if profile.route_depth == "complete":
        return _localized(profile, "Cover the mastery graph broadly, including core resources, implementation practice, and high-value synthesis material.", "广泛覆盖掌握图谱，包括核心资料、实现练习和高价值综合材料。")
    return _localized(profile, "Balance shortest-path efficiency with enough support material to pass explain, derive, reproduce, and critique checkpoints.", "在最短路径效率和必要支撑材料之间平衡，确保能通过讲解、推导、复现、批判验收。")


def _safety_policy(profile: LearnerProfile) -> list[str]:
    pairs = [
        ("Use official APIs, open resources, or user-provided URLs.", "使用官方 API、开放资源或用户显式提供的链接。"),
        ("Do not bypass login, scrape restricted pages, or download videos.", "不绕过登录、不抓取受限页面、不下载视频。"),
        ("Summarize and link copyrighted material instead of copying long excerpts.", "对版权材料只摘要和链接，不复制长篇内容。"),
        ("Do not expose private local paths in shareable outputs.", "共享输出中不暴露私有本地路径。"),
    ]
    return [_localized(profile, en, zh) for en, zh in pairs]


def _infer_target_kind(profile: LearnerProfile, resources: list[Resource]) -> str:
    if profile.target_kind != "auto":
        return profile.target_kind
    goal = profile.goal.lower()
    if any(resource.metadata.get("target_paper") for resource in resources):
        return "paper"
    if any(term in goal for term in ("paper", "arxiv", "doi", "论文", "推导", "复现")):
        return "paper"
    if any(term in goal for term in ("course", "curriculum", "syllabus", "课程")):
        return "course"
    return "field"


def _final_artifact(profile: LearnerProfile, target_kind: str) -> dict[str, str]:
    goal = profile.goal.lower()
    if target_kind == "paper":
        return {
            "type": "paper-mastery",
            "evidence": _localized(profile, "Explain the paper, derive one key step, reproduce the core method, and critique limitations.", "讲清论文、推导一个关键步骤、复现核心方法，并批判局限。"),
        }
    project_terms = ("build", "implement", "reproduce", "deploy", "project", "code", "复现", "实现", "项目")
    survey_terms = ("survey", "review", "literature", "map", "综述", "调研", "知识图谱")
    wants_project = any(term in goal for term in project_terms)
    wants_survey = any(term in goal for term in survey_terms)
    if wants_project and wants_survey:
        return {"type": "project+survey", "evidence": _localized(profile, "Ship a minimal runnable project and a one-page paper/concept map.", "交付一个最小可运行项目，并完成一页论文/概念图。")}
    if wants_project:
        return {"type": "project", "evidence": _localized(profile, "Ship a minimal runnable implementation with notes that connect code to the core concepts.", "交付一个最小可运行实现，并用笔记说明代码如何对应核心概念。")}
    if wants_survey:
        return {"type": "survey", "evidence": _localized(profile, "Write a concise field synthesis with key papers, concept edges, and open questions.", "写出一份简洁领域综述，包含关键论文、概念关系和开放问题。")}
    if target_kind == "course":
        return {"type": "course-portfolio", "evidence": _localized(profile, "Complete staged exercises plus one synthesis note or mini-project.", "完成分阶段练习，并交付一份综合笔记或小项目。")}
    return {"type": "project+survey", "evidence": _localized(profile, "Build a small runnable artifact and summarize the field's key papers and concept map.", "构建一个小型可运行产物，并总结领域关键论文和概念图。")}


def _study_tasks(profile: LearnerProfile, resources: list[Resource], target_kind: str) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for index, title in enumerate(_mastery_tasks(target_kind), start=1):
        task_type = _task_key(title)
        supporting = _resources_for_task(task_type, resources)
        if not supporting and resources:
            supporting = resources[:1]
        resource_titles = [resource.title for resource in supporting[:3]]
        tasks.append(
            {
                "id": f"task-{index}-{task_type}",
                "type": task_type,
                "title": title,
                "resource_titles": resource_titles,
                "estimated_minutes": _task_minutes(task_type, supporting),
                "evidence": _task_evidence(profile, task_type),
                "acceptance": _task_acceptance(profile, task_type),
            }
        )
    return tasks


def _task_minutes(task_type: str, resources: list[Resource]) -> int:
    default_minutes = {
        "explain": 45,
        "derive": 75,
        "reproduce": 120,
        "critique": 45,
        "synthesize": 60,
    }.get(task_type, 45)
    if not resources:
        return default_minutes
    shortest = min((_resource_minutes(resource) or default_minutes) for resource in resources)
    return max(30, min(default_minutes, shortest))


def _task_evidence(profile: LearnerProfile, task_type: str) -> str:
    evidence = {
        "explain": ("A no-notes explanation or short concept note.", "不看笔记讲解或写出简短概念笔记。"),
        "derive": ("A traced equation, proof step, or mechanism with variables named.", "写出变量清楚的公式、证明步骤或机制推导。"),
        "reproduce": ("A command output, notebook result, or filled reproduction log.", "留下命令输出、Notebook 结果或填写好的复现记录。"),
        "critique": ("A limitation note with failure cases and fit boundaries.", "写出包含失败情形和适用边界的局限分析。"),
        "synthesize": ("A one-page concept map or synthesis note.", "完成一页概念图或综合笔记。"),
    }
    en, zh = evidence.get(task_type, evidence["explain"])
    return _localized(profile, en, zh)


def _task_acceptance(profile: LearnerProfile, task_type: str) -> str:
    acceptance = {
        "explain": ("Another learner can follow the problem, assumptions, and contribution.", "别人能跟上问题、假设和贡献。"),
        "derive": ("Each transformation or implementation step maps back to a claim.", "每一步变换或实现都能对应回论文主张。"),
        "reproduce": ("The smallest runnable checkpoint executes or has a clear blocker recorded.", "最小可运行检查点能运行，或清楚记录阻塞原因。"),
        "critique": ("At least one concrete limitation changes how the method would be used.", "至少一个具体局限能改变方法使用方式。"),
        "synthesize": ("Prerequisites, core ideas, papers, and project choices are connected.", "前置知识、核心概念、论文和项目选择能连起来。"),
    }
    en, zh = acceptance.get(task_type, acceptance["explain"])
    return _localized(profile, en, zh)


def _next_actions(study_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for index, task in enumerate(study_tasks[:3], start=1):
        resources = task.get("resource_titles", [])
        resource_hint = resources[0] if resources else "selected route resource"
        actions.append(
            {
                "order": index,
                "task_id": task.get("id", f"task-{index}"),
                "title": f"Start {task.get('type', 'task')} with {resource_hint}",
                "estimated_minutes": task.get("estimated_minutes", 45),
                "evidence": task.get("evidence", ""),
            }
        )
    return actions


def _coverage_gate(profile: LearnerProfile, resources: list[Resource], route_audit: dict[str, Any], target_kind: str) -> dict[str, Any]:
    coverage = float(route_audit.get("coverage_ratio", 0.0))
    threshold = _coverage_readiness_threshold(profile, target_kind)
    has_real_resource = any(not _is_generated_resource(resource) for resource in resources)
    if coverage >= threshold and has_real_resource:
        return {
            "status": "ready",
            "threshold": threshold,
            "coverage_ratio": coverage,
            "recommended_action": _localized(profile, "Proceed with the mastery route.", "可以进入掌握路线。"),
        }
    missing_terms = [term for term in route_audit.get("needed_terms", []) if term not in route_audit.get("covered_terms", [])][:8]
    return {
        "status": "insufficient-evidence",
        "threshold": threshold,
        "coverage_ratio": coverage,
        "missing_terms": missing_terms,
        "recommended_action": _localized(
            profile,
            "Add target-specific papers, official docs, course notes, or enable live search before treating this as a mastery route.",
            "先添加目标相关论文、官方文档、课程笔记，或开启实时搜索；在此之前不要把它当成完整掌握路线。",
        ),
    }


def _coverage_readiness_threshold(profile: LearnerProfile, target_kind: str) -> float:
    if target_kind == "paper":
        return 0.55 if profile.route_depth == "fastest" else 0.68
    if target_kind == "course":
        return 0.58
    if profile.route_depth == "fastest":
        return 0.6
    if profile.route_depth == "complete":
        return 0.72
    return 0.66


def _resource_discovery_artifact(profile: LearnerProfile) -> dict[str, str]:
    return {
        "type": "resource-discovery-plan",
        "evidence": _localized(
            profile,
            "Collect enough target-specific resources to regenerate a trustworthy mastery route.",
            "先收集足够目标相关资料，再重新生成可信掌握路线。",
        ),
    }


def _resource_discovery_checklist(profile: LearnerProfile, route_audit: dict[str, Any]) -> Resource:
    missing_terms = route_audit.get("coverage_gate", {}).get("missing_terms") or route_audit.get("needed_terms", [])[:6]
    concepts = [str(term) for term in missing_terms if str(term)][:6] or sorted(_terms(profile.goal))[:6] or ["target topic"]
    return Resource(
        title="fields-study-flow-resource-discovery-checklist",
        url="local://fields-study-flow-resource-discovery-checklist",
        source="fields-study-flow",
        type="checklist",
        language="en",
        difficulty="beginner",
        concepts=concepts,
        estimated_time="60min",
        estimated_minutes=60,
        learning_key_points=[
            "find one primary paper or official reference for each missing concept",
            "prefer official docs, maintained repositories, and recognized courses",
            "rerun the planner after adding the collected sources",
        ],
        focus_areas=concepts,
        critical_path_role="prerequisite",
        trust_score=0.64,
        why_recommended="The current candidate set does not cover the goal well enough, so the next useful step is resource discovery rather than a mastery route.",
        license_or_access_note="Generated checklist; add legal open resources or explicit local files.",
        metadata={"generated_resource_discovery": True},
    )


def _resource_discovery_tasks(profile: LearnerProfile, route_audit: dict[str, Any]) -> list[dict[str, Any]]:
    missing_terms = route_audit.get("coverage_gate", {}).get("missing_terms") or route_audit.get("needed_terms", [])[:6]
    missing = ", ".join(str(term) for term in missing_terms[:6]) or profile.goal
    tasks = [
        (
            "discover",
            "Collect target-specific resources",
            f"Find at least one authoritative paper, book chapter, official doc, or maintained repository for: {missing}.",
            "At least three goal-aligned sources are saved as URLs or local files.",
        ),
        (
            "verify",
            "Verify resource relevance",
            "Reject sources that do not share the goal concepts or do not support explain, reproduce, or synthesize tasks.",
            "Each retained source has a reason and expected role in the route.",
        ),
        (
            "regenerate",
            "Regenerate the roadmap",
            "Run fields-study-flow again with the collected URLs or local resources.",
            "Coverage is above the readiness threshold and the plan has concrete resources.",
        ),
    ]
    return [
        {
            "id": f"task-{index}-{task_type}",
            "type": task_type,
            "title": title,
            "resource_titles": ["fields-study-flow-resource-discovery-checklist"],
            "estimated_minutes": 30,
            "evidence": _localized(profile, evidence, evidence),
            "acceptance": _localized(profile, acceptance, acceptance),
        }
        for index, (task_type, title, evidence, acceptance) in enumerate(tasks, start=1)
    ]


def _resource_gap_messages(profile: LearnerProfile, route_audit: dict[str, Any], resources: list[Resource]) -> list[dict[str, str]]:
    missing_terms = route_audit.get("coverage_gate", {}).get("missing_terms") or route_audit.get("needed_terms", [])[:6]
    return [
        {
            "kind": "resource-coverage",
            "status": "resource-discovery-required",
            "message": _localized(
                profile,
                f"Current resources cover only {route_audit.get('coverage_ratio', 0):.2f} of the goal terms. Missing: {', '.join(str(term) for term in missing_terms[:6]) or 'target-specific concepts'}.",
                f"当前资源只覆盖目标词的 {route_audit.get('coverage_ratio', 0):.2f}。缺口：{', '.join(str(term) for term in missing_terms[:6]) or '目标相关概念'}。",
            ),
            "resolved_by": "add-live-search-or-local-resources",
        },
        {
            "kind": "candidate-quality",
            "status": "not-enough-aligned-resources",
            "message": _localized(
                profile,
                f"Only {len(resources)} candidate resources were available, and the selected set is not sufficient for mastery.",
                f"当前只有 {len(resources)} 个候选资源，且不足以支撑掌握路线。",
            ),
            "resolved_by": "collect-authoritative-sources",
        },
    ]


def _is_generated_resource(resource: Resource) -> bool:
    return bool(
        resource.metadata.get("generated_template")
        or resource.metadata.get("generated_prerequisite_sprint")
        or resource.metadata.get("generated_resource_discovery")
    )


def _resource_library(
    profile: LearnerProfile,
    candidate_resources: list[Resource],
    selected_resources: list[Resource],
    phases: list[dict[str, Any]],
    route_audit: dict[str, Any],
) -> list[dict[str, Any]]:
    selected_ids = {id(resource) for resource in selected_resources}
    candidate_ids = {id(resource) for resource in candidate_resources}
    phase_by_key: dict[tuple[str, str], str] = {}
    for phase in phases:
        phase_name = str(phase.get("name", ""))
        for item in phase.get("resources", []):
            phase_by_key[_resource_dict_key(item)] = phase_name

    omitted_by_title = {
        str(item.get("title", "")): str(item.get("reason", ""))
        for item in route_audit.get("omitted_resources", [])
        if isinstance(item, dict)
    }
    needed = _needed_terms(profile.goal, candidate_resources or selected_resources)
    ordered_resources = [
        *candidate_resources,
        *[resource for resource in selected_resources if id(resource) not in candidate_ids],
    ]
    library: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for resource in ordered_resources:
        public = resource.to_dict()
        key = _resource_dict_key(public)
        if key in seen:
            continue
        seen.add(key)

        is_generated = _is_generated_resource(resource)
        is_selected = id(resource) in selected_ids
        route_status = "generated" if is_generated else "selected" if is_selected else "omitted"
        phase_name = phase_by_key.get(key, "")
        if is_selected:
            reason = f"included-in-shortest-path: {phase_name}" if phase_name else "included-in-shortest-path"
        elif is_generated:
            reason = "generated-to-preserve-shortest-verifiable-path"
        else:
            reason = omitted_by_title.get(resource.title) or _omission_reason(profile, resource, needed)

        public.update(
            {
                "route_status": route_status,
                "selected": is_selected,
                "selected_phase": phase_name or None,
                "route_reason": reason,
            }
        )
        library.append(public)
    return library


def _resource_dict_key(resource: dict[str, Any]) -> tuple[str, str]:
    return (str(resource.get("title", "")), str(resource.get("url", "")))


def _route_audit(profile: LearnerProfile, candidate_resources: list[Resource], selected_resources: list[Resource], study_tasks: list[dict[str, Any]]) -> dict[str, Any]:
    selected_ids = {id(resource) for resource in selected_resources}
    needed = _needed_terms(profile.goal, candidate_resources or selected_resources)
    covered: set[str] = set()
    for resource in selected_resources:
        covered.update(_resource_terms(resource))
    coverage_ratio = len(needed & covered) / len(needed) if needed else 1.0
    omitted = [
        {
            "title": resource.title,
            "reason": _omission_reason(profile, resource, needed),
            "estimated_minutes": _resource_minutes(resource),
            "critical_path_role": resource.critical_path_role,
        }
        for resource in candidate_resources
        if id(resource) not in selected_ids
    ]
    selected_minutes = sum(_resource_minutes(resource) or 0 for resource in selected_resources)
    candidate_minutes = sum(_resource_minutes(resource) or 0 for resource in candidate_resources)
    supported_task_types = sorted({task.get("type", "") for task in study_tasks if task.get("resource_titles")})
    return {
        "coverage_ratio": round(coverage_ratio, 3),
        "needed_terms": sorted(needed)[:18],
        "covered_terms": sorted(needed & covered)[:18],
        "selected_minutes": selected_minutes,
        "candidate_minutes": candidate_minutes,
        "estimated_minutes_saved": max(0, candidate_minutes - selected_minutes),
        "supported_task_types": supported_task_types,
        "omitted_resources": omitted[:12],
        "shortest_path_claim": _localized(
            profile,
            "Shortest among the visible candidates under the selected route depth and mastery gates.",
            "在当前候选资源、路线深度和掌握验收门槛下的最短可行路径。",
        ),
    }


def _omission_reason(profile: LearnerProfile, resource: Resource, needed: set[str]) -> str:
    minutes = _resource_minutes(resource) or 0
    terms = _resource_terms(resource)
    if resource.metadata.get("candidate_decision") == "supplement-only":
        return "supplement-only"
    if resource.critical_path_role == "prerequisite" and minutes > 240 and profile.route_depth in {"fastest", "balanced"}:
        return "broad-detour"
    if not (terms & needed):
        return "off-target"
    return "lower-marginal-value"


def _quality_report(
    profile: LearnerProfile,
    selected_resources: list[Resource],
    study_tasks: list[dict[str, Any]],
    route_audit: dict[str, Any],
    artifact_requirements: dict[str, Any],
    generated_artifacts: list[str],
) -> dict[str, Any]:
    coverage_gate = route_audit.get("coverage_gate", {})
    if coverage_gate.get("status") == "insufficient-evidence":
        dimensions = {
            "usefulness": _dimension_level(
                "medium",
                "The report is useful as a resource-discovery plan, but current evidence is insufficient for a mastery route.",
            ),
            "usability": _dimension_level(
                "high",
                "The report explicitly flags insufficient coverage and provides next actions.",
            ),
            "convenience": _dimension_level(
                "medium",
                "The plan prevents a false route, but the learner still needs to collect target-specific resources.",
            ),
            "novelty": _dimension_level(
                "high",
                "Combines coverage gating, resource discovery tasks, and local/private resource policy.",
            ),
            "completeness": _dimension_level(
                "medium",
                "Mastery gates are deferred until the resource set covers the target.",
            ),
        }
        return {"overall": "needs-resources", "dimensions": dimensions}

    task_types = {task.get("type") for task in study_tasks if task.get("resource_titles")}
    has_validation = artifact_requirements.get("requires_runnable") is False or artifact_requirements.get("policy") in {
        "existing-runnable-resource",
        "auto-generated-template",
        "not-required",
    }
    dimensions = {
        "usefulness": _dimension(
            bool(selected_resources) and bool(study_tasks) and has_validation,
            "Route has selected resources, mastery tasks, and an explicit final-artifact policy.",
        ),
        "usability": _dimension(
            bool(study_tasks) and bool(route_audit) and profile.output_language in {"zh-CN", "en", "bilingual"},
            "Reports expose tasks, route audit, and the selected output language.",
        ),
        "convenience": _dimension(
            bool(route_audit.get("estimated_minutes_saved", 0) >= 0) and bool(study_tasks[:1]),
            "The plan gives next actions, time estimates, and omitted-resource reasons.",
        ),
        "novelty": _dimension(
            bool(generated_artifacts or artifact_requirements) and bool(route_audit.get("shortest_path_claim")),
            "Combines mastery graph, shortest-path audit, local/private resource policy, and artifact enforcement.",
        ),
        "completeness": _dimension(
            {"explain", "derive", "reproduce", "critique"} <= task_types or (len(task_types) >= 4 and has_validation),
            "Explain, derive, reproduce, and critique gates are represented with evidence tasks.",
        ),
    }
    overall = "high" if all(item["level"] == "high" for item in dimensions.values()) else "medium"
    return {"overall": overall, "dimensions": dimensions}


def _dimension(condition: bool, evidence: str) -> dict[str, str]:
    return {"level": "high" if condition else "medium", "evidence": evidence}


def _dimension_level(level: str, evidence: str) -> dict[str, str]:
    return {"level": level, "evidence": evidence}


def _mastery_graph(profile: LearnerProfile, resources: list[Resource], target_kind: str, final_artifact: dict[str, str]) -> dict[str, Any]:
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    concept_ids: dict[str, str] = {}
    resource_ids: dict[int, str] = {}
    for resource in resources:
        for concept in resource.concepts[:4]:
            key = concept.lower()
            if key not in concept_ids:
                node_id = f"concept-{len(concept_ids) + 1}"
                concept_ids[key] = node_id
                nodes.append({"id": node_id, "kind": "concept", "label": concept})
    if not concept_ids:
        for term in sorted(_needed_terms(profile.goal, resources))[:4]:
            node_id = f"concept-{len(concept_ids) + 1}"
            concept_ids[term] = node_id
            nodes.append({"id": node_id, "kind": "concept", "label": term})

    for index, resource in enumerate(resources, start=1):
        resource_id = f"resource-{index}"
        resource_ids[id(resource)] = resource_id
        nodes.append({"id": resource_id, "kind": "resource", "label": resource.title})
        for concept in resource.concepts[:3]:
            concept_id = concept_ids.get(concept.lower())
            if concept_id:
                edges.append({"from": concept_id, "to": resource_id, "label": "covered_by"})

    tasks = _graph_tasks(target_kind, final_artifact)
    for index, task in enumerate(tasks, start=1):
        task_id = f"task-{index}"
        nodes.append({"id": task_id, "kind": "task", "label": task})
        task_key = _task_key(task)
        supporting_resources = _resources_for_task(task_key, resources)
        if not supporting_resources and resources:
            supporting_resources = resources[:1]
        for resource in supporting_resources[:4]:
            resource_id = resource_ids.get(id(resource))
            if resource_id:
                edges.append({"from": resource_id, "to": task_id, "label": f"supports_{task_key}"})
    nodes.append({"id": "assessment-1", "kind": "assessment", "label": final_artifact.get("type", "final artifact")})
    for index, _task in enumerate(tasks, start=1):
        edges.append({"from": f"task-{index}", "to": "assessment-1", "label": "required_for"})
    return {"nodes": nodes, "edges": edges}


def _task_key(task: str) -> str:
    lowered = task.lower()
    if "discover" in lowered or "verify" in lowered or "regenerate" in lowered:
        return "discover"
    if "derive" in lowered or "equation" in lowered or "proof" in lowered:
        return "derive"
    if "reproduce" in lowered or "implement" in lowered or "run" in lowered:
        return "reproduce"
    if "critique" in lowered or "trade-off" in lowered or "limitation" in lowered:
        return "critique"
    if "connect" in lowered or "synthesis" in lowered:
        return "synthesize"
    return "explain"


def _resources_for_task(task_key: str, resources: list[Resource]) -> list[Resource]:
    if task_key == "reproduce":
        runnable = [
            resource
            for resource in resources
            if resource.critical_path_role == "practice-validation"
            or resource.type in {"repository", "code", "notebook", "practice"}
            or resource.metadata.get("generated_template")
        ]
        return runnable
    if task_key == "derive":
        derivation = [
            resource
            for resource in resources
            if resource.metadata.get("target_paper")
            or resource.critical_path_role == "core-paper"
            or _resource_mentions(resource, ("derive", "equation", "proof", "method", "mechanism"))
        ]
        return derivation
    if task_key == "critique":
        critique = [
            resource
            for resource in resources
            if resource.type == "paper"
            or resource.critical_path_role in {"core-paper", "focused-support"}
            or _resource_mentions(resource, ("limit", "failure", "critique", "trade-off"))
        ]
        return critique
    if task_key == "synthesize":
        return [resource for resource in resources if resource.critical_path_role in {"core-paper", "focused-support", "support"}] or resources
    return [resource for resource in resources if resource.critical_path_role != "practice-validation"] or resources


def _resource_mentions(resource: Resource, terms: tuple[str, ...]) -> bool:
    haystack = " ".join([resource.title, *resource.learning_key_points, *resource.focus_areas, *resource.concepts]).lower()
    return any(term in haystack for term in terms)


def _mastery_tasks(target_kind: str) -> list[str]:
    if target_kind == "paper":
        return [
            "Explain the problem, contribution, and assumptions",
            "Derive one key equation or proof step",
            "Reproduce the minimal method or experiment",
            "Critique limitations and failure modes",
        ]
    return [
        "Explain the field map and prerequisite chain",
        "Implement or run a minimal representative example",
        "Connect key papers, tools, and concepts",
        "Critique trade-offs and choose next steps",
    ]


def _graph_tasks(target_kind: str, final_artifact: dict[str, str]) -> list[str]:
    if final_artifact.get("type") == "resource-discovery-plan":
        return [
            "Discover target-specific resources",
            "Verify resource relevance",
            "Regenerate the roadmap",
        ]
    return _mastery_tasks(target_kind)


def _compress_short_route_prerequisites(profile: LearnerProfile, resources: list[Resource]) -> list[Resource]:
    should_compress = profile.route_depth == "fastest" or (
        profile.route_depth == "balanced" and profile.learning_style in {"practical", "auto"}
    )
    if not should_compress:
        return resources
    output: list[Resource] = []
    sprint_added = False
    for resource in resources:
        minutes = _resource_minutes(resource)
        if resource.critical_path_role == "prerequisite" and minutes and minutes > 240:
            if not sprint_added:
                output.append(_focused_prerequisite_sprint(profile, resources))
                sprint_added = True
            continue
        output.append(resource)
    return output


def _trim_to_route_limit_after_artifacts(profile: LearnerProfile, resources: list[Resource]) -> list[Resource]:
    has_target_paper = any(resource.metadata.get("target_paper") for resource in resources)
    limit = _route_resource_limit(profile, len(resources), has_target_paper)
    if len(resources) <= limit:
        return resources
    keep = sorted(resources, key=_post_artifact_keep_value, reverse=True)[:limit]
    keep_ids = {id(resource) for resource in keep}
    return [resource for resource in resources if id(resource) in keep_ids]


def _post_artifact_keep_value(resource: Resource) -> float:
    value = _marginal_route_value(resource, _resource_terms(resource), _resource_requirements(resource))
    if resource.metadata.get("target_paper"):
        value += 100
    if resource.metadata.get("generated_template"):
        value += 90
    if resource.critical_path_role == "practice-validation":
        value += 75
    if resource.metadata.get("generated_prerequisite_sprint"):
        value += 65
    if resource.critical_path_role == "prerequisite":
        value += 30
    value -= min(_resource_minutes(resource) or 0, 720) / 1000
    return value


def _focused_prerequisite_sprint(profile: LearnerProfile, resources: list[Resource]) -> Resource:
    concepts: list[str] = []
    for resource in resources:
        if resource.critical_path_role != "prerequisite":
            concepts.extend(resource.concepts[:4])
    if not concepts:
        concepts.extend(sorted(_needed_terms(profile.goal, resources))[:4])
    concepts = list(dict.fromkeys(concepts))[:6] or ["target prerequisites"]
    return Resource(
        title="Focused prerequisite sprint",
        url="local://fields-study-flow-prerequisite-sprint",
        source="fields-study-flow",
        type="checklist",
        language="en",
        difficulty="beginner",
        concepts=concepts,
        estimated_time="90min",
        estimated_minutes=90,
        learning_key_points=[
            "review only definitions used by the target paper or project",
            "derive one tiny example for each blocker concept",
            "stop when the core resource becomes readable",
        ],
        focus_areas=concepts[:4],
        critical_path_role="prerequisite",
        trust_score=0.66,
        why_recommended="Short practical routes compress broad prerequisite courses into a targeted sprint so the route stays focused.",
        license_or_access_note="Generated study checklist; use open notes or your own materials for the listed blockers.",
        metadata={"generated_prerequisite_sprint": True, "route_depth": profile.route_depth},
    )


def _select_route_resources(profile: LearnerProfile, resources: list[Resource]) -> list[Resource]:
    target_resources = [resource for resource in resources if resource.metadata.get("target_paper")]
    selected: list[Resource] = []
    selected_ids: set[int] = set()
    needed = _needed_terms(profile.goal, resources)
    covered: set[str] = set()
    max_resources = _route_resource_limit(profile, len(resources), bool(target_resources))
    coverage_threshold = _route_coverage_threshold(profile)

    anchor = _best_anchor_target(target_resources, needed)
    if anchor:
        selected.append(anchor)
        selected_ids.add(id(anchor))
        covered.update(_resource_terms(anchor))

    missing_requirements = _available_requirements(profile, resources)
    for resource in selected:
        missing_requirements -= _resource_requirements(resource)

    candidates = [resource for resource in resources if id(resource) not in selected_ids]
    while candidates and len(selected) < max_resources:
        best_resource: Resource | None = None
        best_value = 0.0
        best_new_terms: set[str] = set()
        best_new_requirements: set[str] = set()
        for resource in candidates:
            terms = _resource_terms(resource)
            new_terms = (terms & needed) - covered
            new_requirements = _resource_requirements(resource) & missing_requirements
            shortcut_overlap = _is_local_shortcut(resource) and bool(terms & needed) and not any(item.source == "local-library" for item in selected)
            if not new_terms and not new_requirements and not shortcut_overlap:
                continue
            value = _marginal_route_value(resource, new_terms, new_requirements)
            if shortcut_overlap:
                value += 0.6 / max(0.5, (_resource_minutes(resource) or 120) / 60)
            if value > best_value:
                best_resource = resource
                best_value = value
                best_new_terms = new_terms
                best_new_requirements = new_requirements
        if best_resource is None:
            break
        selected.append(best_resource)
        selected_ids.add(id(best_resource))
        candidates = [resource for resource in candidates if id(resource) != id(best_resource)]
        covered.update(best_new_terms)
        missing_requirements -= best_new_requirements
        if _coverage_satisfied(needed, covered, coverage_threshold) and not missing_requirements and profile.route_depth != "complete":
            break

    if profile.route_depth == "complete" and len(selected) < max_resources:
        selected = _fill_complete_path(resources, selected, selected_ids, needed, max_resources)

    if not selected:
        candidates = sorted(resources, key=lambda resource: _marginal_route_value(resource, _resource_terms(resource), _resource_requirements(resource)), reverse=True)
        selected = candidates[: min(3, len(candidates))]

    return sorted(selected, key=lambda resource: resources.index(resource))


def _route_resource_limit(profile: LearnerProfile, candidate_count: int, has_target_paper: bool) -> int:
    if candidate_count <= 0:
        return 0
    if profile.route_depth == "fastest":
        return min(candidate_count, 3 if has_target_paper else 4)
    if profile.route_depth == "complete":
        return min(candidate_count, 12)
    return min(candidate_count, 6 if has_target_paper else 7)


def _route_coverage_threshold(profile: LearnerProfile) -> float:
    if profile.route_depth == "fastest":
        return 0.66
    if profile.route_depth == "complete":
        return 0.95
    return 0.8


def _fill_complete_path(resources: list[Resource], selected: list[Resource], selected_ids: set[int], needed: set[str], max_resources: int) -> list[Resource]:
    output = list(selected)
    for resource in sorted(resources, key=lambda item: _complete_path_value(item, needed), reverse=True):
        if len(output) >= max_resources:
            break
        if id(resource) in selected_ids:
            continue
        if resource.metadata.get("candidate_decision") == "supplement-only" and not (_resource_terms(resource) & needed):
            continue
        if _complete_path_value(resource, needed) <= 0:
            continue
        output.append(resource)
        selected_ids.add(id(resource))
    return output


def _complete_path_value(resource: Resource, needed: set[str]) -> float:
    relevance = len(_resource_terms(resource) & needed)
    role_bonus = {
        "core-paper": 4.0,
        "practice-validation": 3.0,
        "focused-support": 2.0,
        "prerequisite": 1.4,
        "support": 1.0,
    }.get(resource.critical_path_role, 0.8)
    live_bonus = 0.3 if resource.metadata.get("live_search") else 0.0
    local_bonus = 0.5 if _is_local_shortcut(resource) else 0.0
    return relevance + role_bonus + (resource.score or 0.5) + live_bonus + local_bonus


def _best_anchor_target(target_resources: list[Resource], needed: set[str]) -> Resource | None:
    if not target_resources:
        return None
    return max(target_resources, key=lambda resource: _marginal_route_value(resource, _resource_terms(resource) & needed, {"core"}))


def _available_requirements(profile: LearnerProfile, resources: list[Resource]) -> set[str]:
    requirements = {"core"}
    roles = {resource.critical_path_role for resource in resources}
    if "practice-validation" in roles and _goal_needs_validation(profile.goal):
        requirements.add("validation")
    if "prerequisite" in roles and _profile_needs_prerequisites(profile):
        requirements.add("prerequisite")
    return requirements


def _resource_requirements(resource: Resource) -> set[str]:
    role = resource.critical_path_role
    requirements: set[str] = set()
    if role in {"core-paper", "focused-support", "support"}:
        requirements.add("core")
    if role == "practice-validation":
        requirements.add("validation")
    if role == "prerequisite":
        requirements.add("prerequisite")
    return requirements


def _goal_needs_validation(goal: str) -> bool:
    normalized = goal.lower()
    return any(term in normalized for term in ("master", "fully", "reproduce", "derive", "implement", "paper", "掌握", "完全", "复现", "推导", "实现", "论文"))


def _profile_needs_prerequisites(profile: LearnerProfile) -> bool:
    levels = set(profile.levels.values())
    return not profile.known_topics or bool({"beginner", "初学"} & levels)


def _coverage_satisfied(needed: set[str], covered: set[str], threshold: float = 0.8) -> bool:
    if not needed:
        return True
    return len(needed & covered) / len(needed) >= threshold


def _marginal_route_value(resource: Resource, new_terms: set[str], new_requirements: set[str]) -> float:
    minutes = _resource_minutes(resource) or 120
    local_bonus = 0.2 if _is_local_shortcut(resource) else 0.0
    structure_bonus = 0.2 if resource.learning_key_points or resource.focus_areas else 0.0
    style_bonus = 0.15 if resource.critical_path_role == "practice-validation" else 0.0
    marginal_gain = len(new_terms) + 1.75 * len(new_requirements)
    return (marginal_gain + (resource.score or 0.5) + local_bonus + structure_bonus + style_bonus) / max(0.5, minutes / 60)


def _is_local_shortcut(resource: Resource) -> bool:
    return resource.source == "local-library" and resource.metadata.get("candidate_decision") == "critical-path-candidate"


def _needed_terms(goal: str, resources: list[Resource]) -> set[str]:
    terms = _terms(goal)
    has_target_paper = False
    for resource in resources:
        if resource.metadata.get("target_paper"):
            has_target_paper = True
            terms.update(_resource_terms(resource))
    if has_target_paper:
        return terms
    if not terms:
        for resource in resources[:3]:
            terms.update(_resource_terms(resource))
    return terms


def _resource_terms(resource: Resource) -> set[str]:
    values = [resource.title, resource.type, *resource.concepts, *resource.prerequisites, *resource.learning_key_points, *resource.focus_areas]
    return _terms(" ".join(values))


def _terms(value: str) -> set[str]:
    generic = {
        "and",
        "arxiv",
        "beginner",
        "build",
        "course",
        "derive",
        "doi",
        "field",
        "from",
        "fully",
        "group",
        "implement",
        "learn",
        "learning",
        "master",
        "paper",
        "papers",
        "path",
        "project",
        "projects",
        "quickly",
        "read",
        "reading",
        "reproduce",
        "study",
        "survey",
        "target",
        "understand",
        "unknown",
        "with",
        "write",
    }
    normalized = value.lower().replace("/", " ").replace("-", " ")
    tokens = {token.strip(".,:;()[]{}") for token in normalized.split() if len(token.strip(".,:;()[]{}")) >= 3 and token.strip(".,:;()[]{}") not in generic}
    tokens = {token for token in tokens if not any(char.isdigit() for char in token)}
    tokens.update({token[:-1] for token in list(tokens) if len(token) > 4 and token.endswith("s")})
    for keyword in (
        "transformer",
        "attention",
        "diffusion",
        "yolo",
        "cnn",
        "ppo",
        "trpo",
        "python",
        "pddl",
        "planning",
        "symbolic planning",
        "chain of thought",
        "chain-of-thought",
        "planbench",
        "instruction tuning",
        "deep learning",
        "neural network",
        "neural networks",
        "pytorch",
    ):
        if keyword in normalized:
            tokens.add(keyword)
    return {token for token in tokens if not _is_route_intent_term(token)}


def _is_route_intent_term(token: str) -> bool:
    if token in {"学习", "掌握", "论文", "阅读", "推导", "复现", "实现"}:
        return True
    return "完成" in token or "项目" in token


def _resource_minutes(resource: Resource) -> int | None:
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
    if minutes <= 0:
        return "unknown"
    if minutes < 60:
        return f"{minutes}min"
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{minutes / 60:.1f}h"


def _svg_escape(value: object) -> str:
    text = str(value)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _truncate(value: object, limit: int) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."
