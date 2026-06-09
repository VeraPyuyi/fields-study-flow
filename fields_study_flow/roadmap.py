from __future__ import annotations

import copy
import json
import re
from html import escape
from pathlib import Path
from typing import Any

from fields_study_flow.artifact_templates import enforce_artifact_requirements, write_artifact_template
from fields_study_flow.knowledge_graph import build_knowledge_graph
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.paper_lens import build_paper_lens, has_target_paper, render_paper_lens_html


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
PAPER_LENS_FILE = "paper_lens.html"

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
    "selected": ("selected", "已选择"),
    "generated_resource": ("generated", "已生成"),
    "omitted": ("omitted", "未选入"),
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
    "learning_knowledge_graph": ("Learning Knowledge Graph", "学习知识图谱"),
    "plan_quality": ("Plan Quality", "计划质量"),
    "route_audit": ("Route Audit", "路线审计"),
    "mastery_evidence": ("Mastery Evidence", "掌握证据"),
    "evidence_contract": ("Evidence contract", "证据契约"),
    "required_evidence": ("Required evidence", "必填证据"),
    "pass_criteria": ("Pass criteria", "通过标准"),
    "review_status": ("Review status", "复查状态"),
    "evidence_files": ("Evidence files", "证据文件"),
    "next_actions": ("Next Actions", "下一步行动"),
    "study_tasks": ("Study Tasks", "学习任务"),
    "coverage": ("Coverage", "覆盖度"),
    "coverage_note": ("Coverage note", "覆盖说明"),
    "readiness": ("Readiness", "路线可信度"),
    "coverage_gate": ("Coverage Gate", "覆盖门槛"),
    "recommended_action": ("Recommended action", "建议动作"),
    "omitted_resources": ("Omitted resources", "省略资源"),
    "level": ("Level", "等级"),
    "evidence": ("Evidence", "证据"),
    "live_search": ("Live search", "实时搜索"),
    "study_bundle": ("Study Asset Bundle", "学习资料包"),
    "bundle_manifest": ("Bundle manifest", "资料包清单"),
    "bundle_links": ("Fallback links", "备用链接"),
    "bundle_readme": ("Bundle README", "资料包说明"),
    "bundle_policy": ("Bundle policy", "打包策略"),
    "bundle_summary": ("Bundle summary", "打包摘要"),
    "bundle_completion": ("Bundle completion", "资料包完成度"),
    "download_status": ("Download status", "下载状态"),
    "download_manager": ("Download Manager", "下载管理"),
    "download_queue": ("Download queue", "下载队列"),
    "bundle_scope": ("Bundle scope", "资料包范围"),
    "downloaded_selected": ("Downloaded selected", "已下载路线资料"),
    "downloaded_omitted": ("Downloaded omitted", "已下载补充资料"),
    "retry_file": ("Retry file", "重试清单"),
    "copied": ("copied", "已复制"),
    "downloaded": ("downloaded", "已下载"),
    "snapshotted": ("snapshotted", "已快照"),
    "link_only": ("link-only", "仅链接"),
    "failed": ("failed", "失败"),
    "completed": ("completed", "已完成"),
    "retryable": ("retryable", "可重试"),
    "attempts": ("Attempts", "尝试次数"),
    "file_or_link": ("File or link", "文件或链接"),
    "open_local_resource": ("Open local file", "打开本地资料"),
    "original_link": ("Original link", "查看原始链接"),
    "local_available": ("Local available", "本地可打开"),
    "retry": ("Retry", "重试"),
    "route": ("Route", "路线"),
    "full_resource_table": ("Full resource table", "完整资料表"),
    "total": ("total", "总计"),
    "all": ("all", "全部"),
    "search_resources": ("Search resources", "搜索资料"),
    "show_original_evidence": ("Original evidence", "原文证据"),
    "collapse": ("Collapse", "折叠"),
    "expand": ("Expand", "展开"),
    "edges": ("edges", "边"),
    "evidence_backed": ("evidence-backed", "有证据支撑"),
    "learning_console": ("Learning Console", "学习中控台"),
    "kg_network": ("Learning Path Network", "学习路径网络"),
    "task_guide": ("Task Guide", "任务向导"),
    "task_progress": ("Task progress", "任务进度"),
    "current_task_resources": ("Current task resources", "当前任务资料"),
    "only_current_task": ("Only current task resources", "只看当前任务资料"),
    "show_all_tasks": ("Show all task resources", "显示全部任务资料"),
    "show_local_resources": ("Local files only", "只看本地可打开"),
    "clear_filters": ("Clear filters", "清空筛选"),
    "reset_layout": ("Reset layout", "重置布局"),
    "fit_view": ("Fit view", "适应窗口"),
    "zoom_in": ("Zoom in", "放大"),
    "zoom_out": ("Zoom out", "缩小"),
    "storage_warning": ("Local progress storage is unavailable in this browser, so checks are temporary.", "当前浏览器无法使用本地进度存储，勾选状态仅临时保留。"),
    "score": ("score", "分数"),
    "chunks": ("chunks", "片段"),
    "resource_count": ("resources", "资料数"),
    "rag_mode": ("retrieval mode", "检索模式"),
    "light_rag": ("light retrieval", "轻量检索"),
    "auto_rag": ("auto retrieval", "自动检索"),
    "embedding_rag": ("local embedding retrieval", "本地向量检索"),
    "off_rag": ("retrieval off", "检索关闭"),
    "filter_route": ("Route", "路线状态"),
    "filter_download": ("Download", "下载状态"),
    "filter_type": ("Type", "资料类型"),
    "filter_source": ("Source", "资料来源"),
    "yes": ("yes", "是"),
    "no": ("no", "否"),
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


def _bundle_summary_text(summary: dict[str, Any], language: str) -> str:
    ordered = [
        ("copied", "copied"),
        ("downloaded", "downloaded"),
        ("snapshotted", "snapshotted"),
        ("generated", "generated"),
        ("link-only", "link_only"),
        ("failed", "failed"),
        ("completed", "completed"),
        ("retryable", "retryable"),
        ("downloaded_selected", "downloaded_selected"),
        ("downloaded_omitted", "downloaded_omitted"),
        ("total", "total"),
    ]
    parts = []
    for source_key, label_key in ordered:
        if source_key in summary:
            parts.append(f"{_label(language, label_key)}={summary.get(source_key, 0)}")
    return ", ".join(parts) or _label(language, "not_available")


def _bundle_resource_detail(resource: dict[str, Any], language: str) -> str:
    status = str(resource.get("status", _label(language, "unknown")))
    status_label = _bundle_status_label(language, status)
    file_name = resource.get("file")
    reason = _bundle_reason_label(language, resource.get("reason"))
    parts = [status_label]
    if file_name:
        parts.append(str(file_name))
    if reason:
        parts.append(str(reason))
    return " - ".join(parts)


def _bundle_file_or_link(resource: dict[str, Any], language: str) -> str:
    for key in ("local_href", "file", "download_url", "snapshot_url", "url"):
        value = resource.get(key)
        if value:
            return str(value)
    return str(resource.get("reason") or _label(language, "not_available"))


def _resource_lookup_key(resource: dict[str, Any]) -> tuple[str, str]:
    return (str(resource.get("title", "")).strip().lower(), str(resource.get("url", "")).strip())


def _title_lookup_key(resource: dict[str, Any]) -> str:
    return str(resource.get("title", "")).strip().lower()


def _bundle_lookup(study_bundle: dict[str, Any]) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    by_title: dict[str, list[dict[str, Any]]] = {}
    for item in study_bundle.get("resources", []):
        if not isinstance(item, dict) or not item.get("title"):
            continue
        by_key[_resource_lookup_key(item)] = item
        by_title.setdefault(_title_lookup_key(item), []).append(item)
    return by_key, by_title


def _bundle_for_resource(
    resource: dict[str, Any],
    by_key: dict[tuple[str, str], dict[str, Any]],
    by_title: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    exact = by_key.get(_resource_lookup_key(resource))
    if exact:
        return exact
    candidates = by_title.get(_title_lookup_key(resource), [])
    if not candidates:
        return {}
    for candidate in candidates:
        if candidate.get("local_href"):
            return candidate
    return candidates[0]


def _primary_resource_href(resource: dict[str, Any], bundle_item: dict[str, Any] | None = None) -> str:
    bundle_item = bundle_item or {}
    return str(bundle_item.get("local_href") or resource.get("local_href") or resource.get("url") or "#")


def _original_resource_href(resource: dict[str, Any], bundle_item: dict[str, Any] | None = None) -> str:
    bundle_item = bundle_item or {}
    return str(resource.get("url") or bundle_item.get("url") or bundle_item.get("download_url") or bundle_item.get("snapshot_url") or "")


def _resource_link_actions(resource: dict[str, Any], bundle_item: dict[str, Any] | None, language: str) -> str:
    bundle_item = bundle_item or {}
    local_href = str(bundle_item.get("local_href") or resource.get("local_href") or "")
    original_href = _original_resource_href(resource, bundle_item)
    actions: list[str] = []
    if local_href:
        actions.append(f'<a class="resource-action local-action" href="{escape(local_href)}">{escape(_label(language, "open_local_resource"))}</a>')
    if original_href and original_href != local_href and not original_href.startswith("local://"):
        actions.append(f'<a class="resource-action original-action" href="{escape(original_href)}">{escape(_label(language, "original_link"))}</a>')
    return f'<div class="resource-actions">{"".join(actions)}</div>' if actions else ""


def _bundle_link_actions(resource: dict[str, Any], language: str) -> str:
    local_href = str(resource.get("local_href") or "")
    original_href = str(resource.get("url") or resource.get("download_url") or resource.get("snapshot_url") or "")
    actions: list[str] = []
    if local_href:
        actions.append(f'<a class="table-link" href="{escape(local_href)}">{escape(_label(language, "open_local_resource"))}</a>')
    if original_href and original_href != local_href and not original_href.startswith("local://"):
        actions.append(f'<a class="table-link original-link" href="{escape(original_href)}">{escape(_label(language, "original_link"))}</a>')
    if not actions:
        actions.append(f'<span class="table-link">{escape(_bundle_file_or_link(resource, language))}</span>')
    return "".join(actions)


def _md_cell(value: Any) -> str:
    text = str(value).replace("\n", " ").replace("|", "\\|")
    return text.strip()


def _bundle_status_label(language: str, status: str) -> str:
    labels = {
        "copied": "copied",
        "downloaded": "downloaded",
        "snapshotted": "snapshotted",
        "link-only": "link_only",
        "failed": "failed",
        "generated": "generated",
    }
    return _label(language, labels.get(status, status.replace("-", "_")))


def _bundle_status_filters(status_counts: dict[str, int]) -> list[str]:
    ordered = ["downloaded", "copied", "snapshotted", "generated", "link-only", "failed"]
    filters = ["all"]
    filters.extend(status for status in ordered if status_counts.get(status, 0) > 0)
    filters.extend(status for status in status_counts if status not in filters)
    return filters


def _bundle_filter_label(language: str, status: str) -> str:
    if status == "all":
        return _label(language, "all_resources")
    return _bundle_status_label(language, status)


def _localized_rag_mode(language: str, mode: Any) -> str:
    value = str(mode or "light")
    labels = {
        "light": "light_rag",
        "auto": "auto_rag",
        "embedding": "embedding_rag",
        "off": "off_rag",
    }
    return _label(language, labels.get(value, "rag_mode"))


def _bundle_reason_label(language: str, reason: Any) -> str:
    reason_text = str(reason or "")
    if reason_text == "existing_bundle_file_reused":
        if language == "zh-CN":
            return "已复用已有文件"
        if language == "bilingual":
            return "Reused existing file / 已复用已有文件"
        return "Reused existing file"
    return reason_text


def _localized(profile: LearnerProfile, en: str, zh: str) -> str:
    if profile.output_language == "zh-CN":
        return zh
    if profile.output_language == "bilingual":
        return f"{en} / {zh}"
    return en


def _localized_artifact_type(language: str, artifact_type: Any) -> str:
    value = str(artifact_type or "unknown")
    zh = {
        "paper-mastery": "论文掌握",
        "project": "项目",
        "project+survey": "项目与综述",
        "survey": "综述",
        "course-portfolio": "课程作品集",
        "resource-discovery-plan": "资料发现计划",
        "final artifact": "最终产物",
        "unknown": "未知",
    }
    en = {
        "paper-mastery": "paper mastery",
        "project": "project",
        "project+survey": "project and survey",
        "survey": "survey",
        "course-portfolio": "course portfolio",
        "resource-discovery-plan": "resource discovery plan",
        "final artifact": "final artifact",
        "unknown": "unknown",
    }
    return _localized_value(language, value, en, zh)


def _localized_status_label(language: str, status: Any) -> str:
    value = str(status or "unknown")
    zh = {
        "ready": "准备就绪",
        "ready-for-evidence": "准备填写证据",
        "needs-resources": "需要补充资料",
        "needs-tasks": "需要生成任务",
        "insufficient-evidence": "证据不足",
        "open": "待复查",
        "not_requested": "未请求",
        "not-required": "不需要",
        "partial": "部分解析",
        "complete": "完整解析",
        "resolved": "已解析",
        "resource-discovery-first": "先补资料",
        "existing-runnable-resource": "已有可运行资源",
        "auto-generated-template": "已生成模板",
        "insufficient-target-aligned-resources": "目标相关资料不足",
        "no-candidate-resources": "没有候选资料",
        "resource-discovery-required": "需要补充资料发现",
        "not-enough-aligned-resources": "相关资料不足",
        "unknown": "未知",
        "high": "高",
        "medium": "中",
        "low": "低",
    }
    en = {
        "ready": "ready",
        "ready-for-evidence": "ready for evidence",
        "needs-resources": "needs resources",
        "needs-tasks": "needs tasks",
        "insufficient-evidence": "insufficient evidence",
        "open": "open",
        "not_requested": "not requested",
        "not-required": "not required",
        "partial": "partial",
        "complete": "complete",
        "resolved": "resolved",
        "resource-discovery-first": "resource discovery first",
        "existing-runnable-resource": "existing runnable resource",
        "auto-generated-template": "auto-generated template",
        "insufficient-target-aligned-resources": "insufficient target-aligned resources",
        "no-candidate-resources": "no candidate resources",
        "resource-discovery-required": "resource discovery required",
        "not-enough-aligned-resources": "not enough aligned resources",
        "unknown": "unknown",
        "high": "high",
        "medium": "medium",
        "low": "low",
    }
    return _localized_value(language, value, en, zh)


def _localized_task_type(language: str, task_type: Any) -> str:
    value = str(task_type or "task")
    zh = {
        "explain": "解释",
        "derive": "推导",
        "reproduce": "复现",
        "critique": "批判",
        "synthesize": "综合",
        "discover": "发现",
        "verify": "验证",
        "regenerate": "重新生成",
        "task": "任务",
    }
    en = {
        "explain": "explain",
        "derive": "derive",
        "reproduce": "reproduce",
        "critique": "critique",
        "synthesize": "synthesize",
        "discover": "discover",
        "verify": "verify",
        "regenerate": "regenerate",
        "task": "task",
    }
    return _localized_value(language, value, en, zh)


def _localized_role_label(language: str, role: Any) -> str:
    value = str(role or "support")
    zh = {
        "core-paper": "核心论文",
        "focused-support": "聚焦支撑",
        "support": "支撑资料",
        "prerequisite": "前置知识",
        "practice-validation": "实践验收",
    }
    en = {
        "core-paper": "core paper",
        "focused-support": "focused support",
        "support": "support",
        "prerequisite": "prerequisite",
        "practice-validation": "practice validation",
    }
    return _localized_value(language, value, en, zh)


def _localized_dimension_label(language: str, name: Any) -> str:
    value = str(name or "unknown")
    zh = {
        "usefulness": "实用性",
        "usability": "可用性",
        "convenience": "便捷性",
        "novelty": "新颖性",
        "completeness": "完整性",
    }
    en = {
        "usefulness": "usefulness",
        "usability": "usability",
        "convenience": "convenience",
        "novelty": "novelty",
        "completeness": "completeness",
    }
    return _localized_value(language, value, en, zh)


def _localized_reason_label(language: str, reason: Any) -> str:
    value = str(reason or "not_specified")
    phase_suffix = ""
    if value.startswith("included-in-shortest-path:"):
        phase_suffix = value.split(":", 1)[1].strip()
        value = "included-in-shortest-path"
    zh = {
        "included-in-shortest-path": "已纳入最短可验收路线",
        "generated-to-preserve-shortest-verifiable-path": "为保证可验收路线自动生成",
        "supplement-only": "仅作为补充资料",
        "broad-detour": "耗时较长，暂不进入最短路线",
        "off-target": "与目标概念覆盖不足",
        "lower-marginal-value": "边际收益较低",
        "collect-authoritative-sources": "收集权威资料",
        "add-live-search-or-local-resources": "开启实时搜索或添加本地资料",
        "not_specified": "未指定",
    }
    en = {
        "included-in-shortest-path": "included in shortest path",
        "generated-to-preserve-shortest-verifiable-path": "generated to preserve a verifiable path",
        "supplement-only": "supplement only",
        "broad-detour": "broad detour",
        "off-target": "off target",
        "lower-marginal-value": "lower marginal value",
        "collect-authoritative-sources": "collect authoritative sources",
        "add-live-search-or-local-resources": "add live search or local resources",
        "not_specified": "not specified",
    }
    label = _localized_value(language, value, en, zh)
    if phase_suffix:
        return f"{label}: {phase_suffix}"
    return label


def _localized_edge_label(language: str, edge: dict[str, Any]) -> str:
    raw = str(edge.get("label", "edge"))
    if language in {"zh-CN", "bilingual"} and edge.get("localized_label"):
        return str(edge.get("localized_label"))
    if raw.startswith("supports_"):
        task_label = _localized_task_type(language, raw.replace("supports_", ""))
        if language == "zh-CN":
            return f"支撑{task_label}"
        if language == "bilingual":
            return f"supports {task_label}"
        return f"supports {raw.replace('supports_', '')}"
    zh = {"covered_by": "由资料覆盖", "supports": "支撑任务", "required_for": "验收必需"}
    en = {"covered_by": "covered by", "supports": "supports", "required_for": "required for"}
    return _localized_value(language, raw, en, zh)


def _localized_node_label(language: str, node: dict[str, Any]) -> str:
    label = str(node.get("label", "node"))
    artifact_labels = {"paper-mastery", "project", "project+survey", "survey", "course-portfolio", "resource-discovery-plan"}
    if node.get("kind") == "assessment" or label in artifact_labels:
        return _localized_artifact_type(language, label)
    if node.get("kind") == "task" and language == "zh-CN":
        return _known_task_title_zh(label)
    if node.get("kind") == "task" and language == "bilingual":
        zh = _known_task_title_zh(label)
        return f"{label} / {zh}" if zh != label else label
    return label


def _localized_value(language: str, value: str, en: dict[str, str], zh: dict[str, str]) -> str:
    if language == "zh-CN":
        return zh.get(value, value)
    if language == "bilingual":
        en_label = en.get(value, value)
        zh_label = zh.get(value, value)
        return f"{en_label} / {zh_label}" if zh_label != en_label else en_label
    return en.get(value, value)


CONTROLLED_TEXT_ZH = {
    "action preconditions": "动作前置条件",
    "symbolic planning": "符号规划",
    "VAL plan validation": "VAL 计划验证",
    "paper-mastery": "论文掌握",
    "paper": "论文",
    "define the minimal runnable target": "定义最小可运行目标",
    "connect code steps to concepts or paper sections": "将代码步骤连接到概念或论文章节",
    "record evidence for explain, derive, reproduce, and critique": "记录解释、推导、复现和批判证据",
    "No runnable resource was selected, so fields-study-flow generated a minimal artifact template for verifiable learning.": "未选择可运行资源，因此 fields-study-flow 生成了最小验收模板。",
    "Route has selected resources, mastery tasks, and an explicit final-artifact policy.": "路线包含已选资料、掌握任务和明确的最终产物策略。",
    "Reports expose tasks, route audit, and the selected output language.": "报告展示任务、路线审计和用户选择的输出语言。",
    "The plan gives next actions, time estimates, and omitted-resource reasons.": "计划给出下一步行动、耗时估计和未选资料原因。",
    "Combines mastery graph, shortest-path audit, local/private resource policy, and artifact enforcement.": "结合掌握图谱、最短路径审计、本地隐私资源策略和产物验收约束。",
    "Explain, derive, reproduce, and critique gates are represented with evidence tasks.": "解释、推导、复现和批判门槛都由证据任务承接。",
    "The report is useful as a resource-discovery plan, but current evidence is insufficient for a mastery route.": "当前报告可作为资料发现计划使用，但证据还不足以支撑完整掌握路线。",
    "The report explicitly flags insufficient coverage and provides next actions.": "报告明确标出覆盖不足，并给出下一步行动。",
    "The plan prevents a false route, but the learner still needs to collect target-specific resources.": "计划避免生成虚假的掌握路线，但学习者仍需补充目标相关资料。",
    "Combines coverage gating, resource discovery tasks, and local/private resource policy.": "结合覆盖门槛、资料发现任务和本地隐私资源策略。",
    "Mastery gates are deferred until the resource set covers the target.": "在资料集覆盖目标之前，掌握验收门槛会暂缓。",
}


def _localized_controlled_text(language: str, value: Any) -> str:
    text = str(value)
    if language == "zh-CN":
        return CONTROLLED_TEXT_ZH.get(text, text)
    if language == "bilingual" and text in CONTROLLED_TEXT_ZH:
        return f"{text} / {CONTROLLED_TEXT_ZH[text]}"
    return text


def build_roadmap(
    profile: LearnerProfile,
    resources: list[Resource],
    live_search: dict[str, Any] | None = None,
    rag_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
        discovery_route_audit = _route_audit(profile, resources, selected_resources, study_tasks)
        route_audit = _resource_discovery_route_audit(profile, route_audit, discovery_route_audit, coverage_gate)
    else:
        route_audit["coverage_gate"] = coverage_gate
    resource_library = _resource_library(profile, resources, selected_resources, phases, route_audit)
    quality_report = _quality_report(profile, selected_resources, study_tasks, route_audit, artifact_requirements, generated_artifacts)
    next_actions = _next_actions(profile, study_tasks)
    mastery_evidence = _mastery_evidence(profile, study_tasks, final_artifact, route_audit, generated_artifacts)
    knowledge_graph = build_knowledge_graph(profile, selected_resources, study_tasks, mastery_evidence, rag_evidence or {})
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
        "knowledge_graph": knowledge_graph,
        "study_tasks": study_tasks,
        "next_actions": next_actions,
        "mastery_evidence": mastery_evidence,
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
    roadmap = _ensure_paper_lens(roadmap)
    return sanitize_roadmap_for_export(roadmap)


def write_outputs(
    output_dir: Path,
    profile: LearnerProfile,
    ranked_resources: list[Resource],
    roadmap: dict[str, Any],
    source_registry_snapshot: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    _remove_obsolete_html_reports(output_dir)
    public_roadmap = _ensure_paper_lens(sanitize_roadmap_for_export(roadmap))
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
    if public_roadmap.get("paper_lens"):
        (output_dir / PAPER_LENS_FILE).write_text(render_paper_lens_html(public_roadmap), encoding="utf-8")
    write_artifact_template(output_dir, public_roadmap)


def _ensure_paper_lens(roadmap: dict[str, Any]) -> dict[str, Any]:
    if roadmap.get("paper_lens_disabled") or not has_target_paper(roadmap):
        return roadmap
    updated = copy.deepcopy(roadmap)
    updated["paper_lens"] = build_paper_lens(updated)
    outputs = list(updated.get("outputs", []))
    if updated.get("paper_lens") and PAPER_LENS_FILE not in outputs:
        outputs.append(PAPER_LENS_FILE)
    updated["outputs"] = outputs
    return updated


def _remove_obsolete_html_reports(output_dir: Path) -> None:
    for name in (
        "roadmap-basic.html",
        "roadmap-lite.html",
        "roadmap-static.html",
        "roadmap-interactive.html",
        "roadmap_full.html",
        "roadmap-full.html",
    ):
        target = output_dir / name
        if target.exists() and target.is_file():
            target.unlink()


def render_markdown(roadmap: dict[str, Any]) -> str:
    roadmap = sanitize_roadmap_for_export(roadmap)
    profile = roadmap["profile"]
    strategy = roadmap.get("path_strategy", {})
    language = _roadmap_language(roadmap)
    study_bundle = roadmap.get("study_bundle", {})
    bundle_by_key, bundle_by_title = _bundle_lookup(study_bundle)
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
        lines.extend([f"## {_label(language, 'route_audit')}", ""])
        lines.extend(
            [
                f"- {_label(language, 'coverage')}: {route_audit.get('coverage_ratio', 0):.2f}",
                f"- {_label(language, 'coverage_gate')}: {_localized_status_label(language, route_audit.get('coverage_gate', {}).get('status', 'ready'))}",
                f"- {_label(language, 'recommended_action')}: {_localized_controlled_text(language, route_audit.get('coverage_gate', {}).get('recommended_action', _label(language, 'not_specified')))}",
            ]
        )
        if route_audit.get("coverage_note"):
            lines.append(f"- {_label(language, 'coverage_note')}: {route_audit.get('coverage_note')}")
        lines.append(f"- {_label(language, 'omitted_resources')}: {len(route_audit.get('omitted_resources', []))}")
        for omitted in route_audit.get("omitted_resources", [])[:5]:
            lines.append(f"  - {omitted.get('title', '')}: {_localized_reason_label(language, omitted.get('reason', ''))}")
        lines.append("")
    rag_evidence = roadmap.get("rag_evidence", {})
    if rag_evidence:
        lines.extend([f"## {_label(language, 'evidence')}", ""])
        summary = rag_evidence.get("summary", {})
        lines.append(
            f"- {_label(language, 'rag_mode')}: {_localized_rag_mode(language, rag_evidence.get('mode', 'light'))} | "
            f"{_label(language, 'chunks')}: {summary.get('chunks', 0)} | "
            f"{_label(language, 'resource_count')}: {summary.get('resources', 0)}"
        )
        lines.append("")
        for item in rag_evidence.get("top_chunks", []):
            if not isinstance(item, dict):
                continue
            source = " / ".join(str(value) for value in [item.get("resource_title"), item.get("file_name")] if value)
            score = item.get("score")
            score_text = f" {_label(language, 'score')}: {score}" if score is not None else ""
            lines.append(f"- {source}{score_text}: {item.get('snippet', '')}")
        lines.append("")
    mastery_evidence = roadmap.get("mastery_evidence", {})
    if mastery_evidence:
        lines.extend([f"## {_label(language, 'mastery_evidence')}", ""])
        lines.extend(
            [
                f"- {_label(language, 'status')}: {_localized_status_label(language, mastery_evidence.get('status', _label(language, 'unknown')))}",
                f"- {_label(language, 'evidence_contract')}: {mastery_evidence.get('claim', '')}",
                f"- {_label(language, 'final_artifact')}: {_localized_artifact_type(language, mastery_evidence.get('final_artifact', _label(language, 'unknown')))}",
                f"- {_label(language, 'evidence_files')}: {_join_or_unknown(mastery_evidence.get('evidence_files', []), language)}",
                "",
                f"| {_label(language, 'type')} | {_label(language, 'required_evidence')} | {_label(language, 'pass_criteria')} | {_label(language, 'resources')} | {_label(language, 'review_status')} |",
                "|---|---|---|---|---|",
            ]
        )
        for item in mastery_evidence.get("required_evidence", []):
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(_localized_task_type(language, item.get("task_type", "task"))),
                        _md_cell(item.get("evidence", "")),
                        _md_cell(item.get("pass_criteria", "")),
                        _md_cell(_join_or_unknown(item.get("resources", []), language)),
                        _md_cell(_localized_status_label(language, item.get("review_status", "open"))),
                    ]
                )
                + " |"
            )
        lines.append("")
    if study_bundle:
        summary = study_bundle.get("summary", {})
        manager = study_bundle.get("download_manager", {})
        lines.extend([f"## {_label(language, 'study_bundle')}", ""])
        lines.extend(
            [
                f"- {_label(language, 'bundle_manifest')}: {study_bundle.get('manifest_file', 'study_bundle_manifest.json')}",
                f"- {_label(language, 'bundle_links')}: {study_bundle.get('links_file', 'links.md')}",
                f"- {_label(language, 'bundle_summary')}: {_bundle_summary_text(summary, language)}",
                f"- {_label(language, 'bundle_policy')}: {study_bundle.get('policy', _label(language, 'not_specified'))}",
            ]
        )
        if manager:
            lines.extend(
                [
                    f"- {_label(language, 'download_queue')}: {manager.get('download_queue_file', 'download_queue.json')}",
                    f"- {_label(language, 'retry_file')}: {manager.get('retry_file', 'retry_failed.md')}",
                    f"- {_label(language, 'completed')}: {manager.get('completed', summary.get('completed', 0))}",
                    f"- {_label(language, 'retryable')}: {manager.get('retryable', summary.get('retryable', 0))}",
                ]
            )
        lines.extend(
            [
                "",
                f"## {_label(language, 'download_manager')}",
                "",
                f"| # | {_label(language, 'title')} | {_label(language, 'download_status')} | {_label(language, 'route')} | {_label(language, 'file_or_link')} | {_label(language, 'attempts')} | {_label(language, 'retry')} |",
                "|---|---|---|---|---|---:|---|",
            ]
        )
        for row_index, resource in enumerate(study_bundle.get("resources", []), start=1):
            if not isinstance(resource, dict):
                continue
            number = resource.get("index") or row_index
            status = _bundle_status_label(language, str(resource.get("status", "unknown")))
            route = _route_status_label(language, str(resource.get("route_status", "unknown")))
            retry = _label(language, "retryable") if resource.get("retryable") else _label(language, "no")
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md_cell(number),
                        _md_cell(resource.get("title", _label(language, "unknown"))),
                        _md_cell(status),
                        _md_cell(route),
                        _md_cell(_bundle_file_or_link(resource, language)),
                        _md_cell(resource.get("attempts", 0)),
                        _md_cell(retry),
                    ]
                )
                + " |"
            )
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
                f"- {_label(language, 'status')}: {_localized_status_label(language, paper_metadata.get('metadata_status', 'partial'))}",
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
                f"- {_label(language, 'requires_runnable_artifact')}: {_label(language, 'yes') if artifact_requirements.get('requires_runnable', False) else _label(language, 'no')}",
                f"- {_label(language, 'policy')}: {_localized_status_label(language, artifact_requirements.get('policy', 'not-required'))}",
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
                    f"- {_localized_status_label(language, gap.get('status', 'open'))}: {gap.get('message', '')}",
                    f"  - {_label(language, 'resolved_by')}: {_localized_reason_label(language, gap.get('resolved_by', _label(language, 'not_available')))}",
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
            bundle_item = _bundle_for_resource(resource, bundle_by_key, bundle_by_title)
            href = _primary_resource_href(resource, bundle_item)
            original_href = _original_resource_href(resource, bundle_item)
            route_status = str(resource.get("route_status", "omitted"))
            status_label = _route_status_label(language, route_status)
            phase = resource.get("selected_phase") or _label(language, "not_available")
            reason = resource.get("route_reason") or _label(language, "not_specified")
            lines.extend(
                [
                    f"- [{resource.get('title', 'Resource')}]({href})",
                    *(
                        [f"  - {_label(language, 'original_link')}: {original_href}"]
                        if original_href and original_href != href and not original_href.startswith("local://")
                        else []
                    ),
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
            bundle_item = _bundle_for_resource(resource, bundle_by_key, bundle_by_title)
            href = _primary_resource_href(resource, bundle_item)
            original_href = _original_resource_href(resource, bundle_item)
            lines.extend(
                [
                    f"- [{resource['title']}]({href})",
                    *(
                        [f"  - {_label(language, 'original_link')}: {original_href}"]
                        if original_href and original_href != href and not original_href.startswith("local://")
                        else []
                    ),
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
                f"- {_label(language, 'type')}: {_localized_artifact_type(language, artifact.get('type', _label(language, 'unknown')))}",
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


def _html_evidence_chunk(item: dict[str, Any], language: str, *, compact: bool = False) -> str:
    title = str(item.get("resource_title") or _label(language, "unknown"))
    file_name = str(item.get("file_name") or "")
    score = item.get("score")
    source = " / ".join(part for part in [title, file_name] if part)
    score_text = f"{_label(language, 'score')} {score}" if score is not None else ""
    class_name = "evidence-chip compact" if compact else "evidence-chip"
    return f"""
    <article class="{class_name}" data-evidence-chip>
      <details open>
        <summary class="evidence-toggle">{escape(_label(language, 'show_original_evidence'))}: {escape(source)}</summary>
        <p>{escape(str(item.get('snippet', '')))}</p>
        <span class="meta">{escape(score_text)}</span>
      </details>
    </article>
    """


def _html_knowledge_graph_panel(
    knowledge_graph: dict[str, Any],
    language: str,
    study_tasks: list[dict[str, Any]] | None = None,
    mastery_evidence: dict[str, Any] | None = None,
) -> str:
    if not knowledge_graph:
        return ""
    nodes = [node for node in knowledge_graph.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in knowledge_graph.get("edges", []) if isinstance(edge, dict)]
    if not nodes:
        return ""
    nodes_by_id = {str(node.get("id", "")): node for node in nodes}
    edges_by_node: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        edges_by_node.setdefault(str(edge.get("from", "")), []).append(edge)
        edges_by_node.setdefault(str(edge.get("to", "")), []).append(edge)
    positions = _kg_network_positions(nodes)
    edge_paths: list[str] = []
    for edge in edges:
        source_id = str(edge.get("from", ""))
        target_id = str(edge.get("to", ""))
        if source_id not in positions or target_id not in positions:
            continue
        sx, sy = positions[source_id]
        tx, ty = positions[target_id]
        bend = max(8.0, abs(tx - sx) * 0.36)
        path = f"M {sx:.1f} {sy:.1f} C {sx + bend:.1f} {sy:.1f}, {tx - bend:.1f} {ty:.1f}, {tx:.1f} {ty:.1f}"
        edge_paths.append(
            f'<path class="kg-network-edge" data-kg-from="{escape(source_id)}" data-kg-to="{escape(target_id)}" d="{escape(path)}"></path>'
        )
    network_nodes: list[str] = []
    for node in nodes[:24]:
        node_id = str(node.get("id", ""))
        kind = str(node.get("kind", "node"))
        x, y = positions.get(node_id, (50.0, 50.0))
        related_count = len(edges_by_node.get(node_id, []))
        node_label = _localized_node_label(language, node)
        task_id = node_id if kind == "task" else ""
        evidence_count = node.get("evidence_count") or 0
        network_nodes.append(
            f"""
            <button type="button" class="kg-node kg-node-button kg-network-node {escape(kind)}"
              style="--kg-x:{x:.1f}%; --kg-y:{y:.1f}%;"
              data-kg-node="{escape(node_id)}"
              data-kg-node-card="{escape(node_id)}"
              data-kg-kind="{escape(kind)}"
              data-task-id="{escape(task_id)}"
              data-kg-initial-x="{x:.1f}"
              data-kg-initial-y="{y:.1f}"
              title="{escape(node_label)}">
              <span class="kg-node-kind">{escape(_localized_node_kind(language, kind))}</span>
              <strong>{escape(node_label)}</strong>
              <span class="meta">{escape(str(related_count))} {escape(_label(language, 'edges'))} · {escape(str(evidence_count))} {escape(_label(language, 'evidence'))}</span>
            </button>
            """
        )
    task_rail = _html_task_guide_rail(study_tasks or [], mastery_evidence or {}, nodes, language)
    column_labels = {
        "concept": _label(language, "concepts"),
        "resource": _label(language, "resources"),
        "task": _label(language, "study_tasks"),
        "assessment": _label(language, "final_artifact"),
    }
    columns: list[str] = []
    for kind in ("concept", "resource", "task", "assessment"):
        cards: list[str] = []
        for node in [item for item in nodes if item.get("kind") == kind][:8]:
            node_id = str(node.get("id", ""))
            related_edges = edges_by_node.get(node_id, [])[:5]
            chips = "".join(_html_kg_edge_chip(edge, node_id, nodes_by_id, language) for edge in related_edges)
            evidence_count = node.get("evidence_count")
            evidence_label = _label(language, "evidence")
            evidence_badge = f'<span class="badge">{escape(str(evidence_count))} {escape(evidence_label)}</span>' if evidence_count else ""
            node_label = _localized_node_label(language, node)
            cards.append(
                f"""
                <article class="kg-node {escape(kind)}" data-kg-node-card="{escape(node_id)}">
                  <div class="resource-head">
                    <h3><button type="button" class="kg-node-button" data-kg-node="{escape(node_id)}" data-kg-kind="{escape(kind)}">{escape(node_label)}</button></h3>
                    {evidence_badge}
                  </div>
                  <p class="meta">{escape(str(node.get('detail', kind)))}</p>
                  <div class="kg-edge-list">{chips}</div>
                </article>
                """
            )
        columns.append(
            f"""
            <section class="kg-column">
              <h3>{escape(column_labels[kind])}</h3>
              <div class="kg-node-list">{''.join(cards) or f'<p class="empty">{escape(_label(language, "not_available"))}</p>'}</div>
            </section>
            """
        )
    summary = knowledge_graph.get("summary", {})
    return f"""
    <section class="graph-panel knowledge-graph-panel kg-network-panel">
      <div class="phase-title-row">
        <h2>{escape(_label(language, 'learning_console'))}</h2>
        <span class="meta">{escape(str(summary.get('edges', 0)))} {escape(_label(language, 'edges'))} / {escape(str(summary.get('evidence_backed_edges', 0)))} {escape(_label(language, 'evidence_backed'))}</span>
      </div>
      <div class="kg-network-controls" data-kg-controls>
        <button type="button" data-kg-zoom="in">{escape(_label(language, 'zoom_in'))}</button>
        <button type="button" data-kg-zoom="out">{escape(_label(language, 'zoom_out'))}</button>
        <button type="button" data-kg-fit>{escape(_label(language, 'fit_view'))}</button>
        <button type="button" data-kg-reset>{escape(_label(language, 'reset_layout'))}</button>
      </div>
      <div class="learning-console-grid">
        <section class="kg-network-stage" aria-label="{escape(_label(language, 'kg_network'))}">
          <div class="kg-network-canvas" data-kg-canvas>
            <svg class="kg-network-svg" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
              {''.join(edge_paths)}
            </svg>
            {''.join(network_nodes)}
          </div>
        </section>
        {task_rail}
      </div>
      <div class="kg-flow">{''.join(columns)}</div>
    </section>
    """


def _html_kg_edge_chip(edge: dict[str, Any], node_id: str, nodes_by_id: dict[str, dict[str, Any]], language: str) -> str:
    if str(edge.get("from", "")) == node_id:
        related_id = str(edge.get("to", ""))
        direction = "to"
    else:
        related_id = str(edge.get("from", ""))
        direction = "from"
    related = nodes_by_id.get(related_id, {})
    direction_label = {"zh-CN": {"to": "指向", "from": "来自"}, "bilingual": {"to": "to / 指向", "from": "from / 来自"}}.get(
        language, {"to": "to", "from": "from"}
    )[direction]
    chunks = edge.get("evidence_chunks") if isinstance(edge.get("evidence_chunks"), list) else []
    snippet = ""
    if chunks and isinstance(chunks[0], dict):
        snippet = str(chunks[0].get("snippet", ""))
    return f"""
    <span class="kg-edge-chip" data-kg-from="{escape(str(edge.get('from', '')))}" data-kg-to="{escape(str(edge.get('to', '')))}">
      <b>{escape(_localized_edge_label(language, edge))}</b>
      {escape(direction_label)} {escape(_localized_node_label(language, related) if related else related_id)}
      {f'<em>{escape(snippet)}</em>' if snippet else ''}
    </span>
    """


def _kg_network_positions(nodes: list[dict[str, Any]]) -> dict[str, tuple[float, float]]:
    groups: dict[str, list[dict[str, Any]]] = {kind: [] for kind in ("concept", "resource", "task", "assessment")}
    for node in nodes:
        groups.setdefault(str(node.get("kind", "node")), []).append(node)
    anchors = {
        "concept": 16.0,
        "resource": 42.0,
        "task": 67.0,
        "assessment": 88.0,
    }
    positions: dict[str, tuple[float, float]] = {}
    for kind, items in groups.items():
        x = anchors.get(kind, 50.0)
        total = max(1, min(len(items), 8))
        for index, node in enumerate(items[:8]):
            if total == 1:
                y = 50.0
            else:
                y = 18.0 + (64.0 * index / (total - 1))
            positions[str(node.get("id", ""))] = (x, y)
        for overflow_index, node in enumerate(items[8:], start=1):
            positions[str(node.get("id", ""))] = (min(94.0, x + 4.0), min(92.0, 14.0 + overflow_index * 7.0))
    return positions


def _localized_node_kind(language: str, kind: Any) -> str:
    value = str(kind or "node")
    zh = {"concept": "概念", "resource": "资料", "task": "任务", "assessment": "验收", "node": "节点"}
    en = {"concept": "concept", "resource": "resource", "task": "task", "assessment": "assessment", "node": "node"}
    return _localized_value(language, value, en, zh)


def _html_task_guide_rail(
    study_tasks: list[dict[str, Any]],
    mastery_evidence: dict[str, Any],
    nodes: list[dict[str, Any]],
    language: str,
) -> str:
    tasks = _console_tasks(study_tasks, mastery_evidence, nodes)
    task_cards: list[str] = []
    for task in tasks:
        task_id = str(task.get("id") or task.get("task_id") or "")
        task_type = str(task.get("type") or task.get("task_type") or "task")
        raw_title = str(task.get("title") or _localized_task_type(language, task_type))
        title = _known_task_title_zh(raw_title) if language == "zh-CN" else _localized_controlled_text(language, raw_title)
        resources = _join_or_unknown(task.get("resource_titles") or task.get("resources") or [], language)
        evidence = _localized_controlled_text(language, task.get("evidence", ""))
        acceptance = _localized_controlled_text(language, task.get("acceptance") or task.get("pass_criteria") or "")
        minutes = task.get("estimated_minutes")
        minutes_text = _format_minutes(int(minutes)) if isinstance(minutes, int) and minutes > 0 else _label(language, "not_available")
        chunk_cards = "".join(
            _html_evidence_chunk(chunk, language, compact=True)
            for chunk in task.get("evidence_chunks", [])[:2]
            if isinstance(chunk, dict)
        )
        task_cards.append(
            f"""
            <article class="task-guide-card" data-guide-task="{escape(task_id)}">
              <label class="task-progress-row">
                <input type="checkbox" class="task-progress-checkbox" data-task-id="{escape(task_id)}">
                <span>
                  <b>{escape(_localized_task_type(language, task_type))}</b>
                  <strong>{escape(title)}</strong>
                </span>
              </label>
              <p class="meta">{escape(_label(language, 'time'))}: {escape(minutes_text)}</p>
              <p class="meta">{escape(_label(language, 'resources'))}: {escape(resources)}</p>
              <p>{escape(evidence)}</p>
              <p class="meta"><strong>{escape(_label(language, 'pass_criteria'))}:</strong> {escape(acceptance)}</p>
              {f'<div class="chunk-list">{chunk_cards}</div>' if chunk_cards else ''}
            </article>
            """
        )
    return f"""
    <aside class="task-guide-rail">
      <div class="phase-title-row">
        <h3>{escape(_label(language, 'task_guide'))}</h3>
        <span class="badge" data-task-progress-label>0 / {escape(str(len(tasks)))}</span>
      </div>
      <p class="meta" data-storage-warning hidden>{escape(_label(language, 'storage_warning'))}</p>
      <button type="button" class="current-task-filter" data-current-task-filter>{escape(_label(language, 'only_current_task'))}</button>
      <div class="task-guide-list">{''.join(task_cards) or f'<p class="empty">{escape(_label(language, "not_available"))}</p>'}</div>
    </aside>
    """


def _console_tasks(study_tasks: list[dict[str, Any]], mastery_evidence: dict[str, Any], nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for task in study_tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or task.get("task_id") or f"task-{len(tasks) + 1}")
        tasks[task_id] = dict(task, id=task_id)
    for item in mastery_evidence.get("required_evidence", []) if isinstance(mastery_evidence, dict) else []:
        if not isinstance(item, dict):
            continue
        task_id = str(item.get("task_id") or item.get("id") or f"task-{len(tasks) + 1}")
        merged = tasks.get(task_id, {"id": task_id})
        merged.update(
            {
                "type": merged.get("type") or item.get("task_type"),
                "title": merged.get("title") or item.get("title"),
                "resource_titles": merged.get("resource_titles") or item.get("resources"),
                "evidence": merged.get("evidence") or item.get("evidence"),
                "acceptance": merged.get("acceptance") or item.get("pass_criteria"),
                "estimated_minutes": merged.get("estimated_minutes") or item.get("estimated_minutes"),
                "evidence_chunks": merged.get("evidence_chunks") or item.get("evidence_chunks") or [],
            }
        )
        tasks[task_id] = merged
    for node in nodes:
        if node.get("kind") != "task":
            continue
        task_id = str(node.get("id") or f"task-{len(tasks) + 1}")
        tasks.setdefault(
            task_id,
            {
                "id": task_id,
                "type": str(node.get("detail") or "task"),
                "title": str(node.get("label") or "task"),
                "resource_titles": [],
                "evidence_chunks": [],
            },
        )
    return list(tasks.values())


def _task_refs_by_resource(study_tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
    refs: dict[str, list[str]] = {}
    for task in study_tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or task.get("task_id") or "")
        if not task_id:
            continue
        for title in task.get("resource_titles", []) or task.get("resources", []) or []:
            key = str(title).strip().lower()
            if key:
                refs.setdefault(key, []).append(task_id)
    return refs


def _localized_resource_type(language: str, resource_type: Any) -> str:
    value = str(resource_type or "unknown")
    zh = {
        "paper": "论文",
        "book": "书籍",
        "course": "课程",
        "repository": "代码仓库",
        "notebook": "Notebook",
        "article": "文章",
        "template": "模板",
        "video": "视频",
        "notes": "笔记",
        "unknown": "未知",
    }
    en = {
        "paper": "paper",
        "book": "book",
        "course": "course",
        "repository": "repository",
        "notebook": "notebook",
        "article": "article",
        "template": "template",
        "video": "video",
        "notes": "notes",
        "unknown": "unknown",
    }
    return _localized_value(language, value, en, zh)


def _localized_source_label(language: str, source: Any) -> str:
    value = str(source or "unknown")
    zh = {
        "arxiv": "arXiv",
        "github": "GitHub",
        "local-library": "本地资料",
        "generated": "生成模板",
        "web": "网页",
        "course": "课程",
        "unknown": "未知",
    }
    en = {
        "arxiv": "arXiv",
        "github": "GitHub",
        "local-library": "local library",
        "generated": "generated",
        "web": "web",
        "course": "course",
        "unknown": "unknown",
    }
    return _localized_value(language, value, en, zh)


def _localized_route_depth(language: str, value: Any) -> str:
    raw = str(value or "balanced")
    zh = {"fastest": "最快", "balanced": "均衡", "complete": "完整"}
    en = {"fastest": "fastest", "balanced": "balanced", "complete": "complete"}
    return _localized_value(language, raw, en, zh)


def _localized_target_kind(language: str, value: Any) -> str:
    raw = str(value or "auto")
    zh = {"paper": "单篇论文", "field": "领域", "course": "课程", "auto": "自动"}
    en = {"paper": "paper", "field": "field", "course": "course", "auto": "auto"}
    return _localized_value(language, raw, en, zh)


def _localized_bundle_scope(language: str, value: Any) -> str:
    raw = str(value or "all")
    zh = {"all": "全部可获取资料", "selected": "仅最短路线资料"}
    en = {"all": "all resources", "selected": "selected route only"}
    return _localized_value(language, raw, en, zh)


def _html_filter_chips(language: str, group: str, label_key: str, values: list[str]) -> str:
    if not values:
        return ""

    def value_label(value: str) -> str:
        if group == "route":
            return _route_status_label(language, value)
        if group == "download":
            return _bundle_status_label(language, value)
        if group == "type":
            return _localized_resource_type(language, value)
        if group == "source":
            return _localized_source_label(language, value)
        if group == "local":
            return _label(language, "local_available") if value == "yes" else _label(language, "not_available")
        return value

    chips = "".join(
        f'<button type="button" class="resource-filter-chip" data-filter-group="{escape(group)}" data-filter-value="{escape(value)}">{escape(value_label(value))}</button>'
        for value in values
    )
    return f"""
    <div class="filter-chip-row" data-filter-row="{escape(group)}">
      <span class="meta">{escape(_label(language, label_key))}</span>
      <div class="filter-chip-list">{chips}</div>
    </div>
    """


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
        f"{_label(language, 'mode')}: {_localized_route_depth(language, strategy.get('mode', 'balanced'))} | "
        f"{strategy.get('estimated_total_time', 'unknown')} | "
        f"{strategy.get('selected_resources', 0)}/{strategy.get('candidate_resources', 0)} {_label(language, 'resources')}"
    )
    bundle_summary = roadmap.get("study_bundle", {}).get("summary", {})
    if bundle_summary:
        summary = (
            f"{summary} | "
            f"{_label(language, 'downloaded')}={bundle_summary.get('downloaded', 0)}, "
            f"{_label(language, 'link_only')}={bundle_summary.get('link-only', 0)}, "
            f"{_label(language, 'failed')}={bundle_summary.get('failed', 0)}"
        )
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>",
        "text{font-family:'Microsoft YaHei UI','Microsoft YaHei','PingFang SC','Noto Sans SC','Source Han Sans SC',Arial,sans-serif;fill:#172033}",
        ".muted{fill:#687287}.tiny{font-size:13px}.small{font-size:15px}.title{font-size:28px;font-weight:700}.phase{font-size:19px;font-weight:700}",
        "</style>",
        f'<rect width="{width}" height="{height}" rx="24" fill="#F7FAFD"/>',
        f'<text x="48" y="58" class="title">{_svg_escape(_truncate(roadmap.get("title", "Learning Roadmap"), 70))}</text>',
        f'<rect x="724" y="28" width="418" height="48" rx="18" fill="#FFFFFF" stroke="#D4DEE9"/>',
        f'<text x="933" y="58" class="small" text-anchor="middle" fill="#4F9FD8" font-weight="700">{_svg_escape(_truncate(summary, 82))}</text>',
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
    knowledge_graph = roadmap.get("knowledge_graph", {})
    artifact = roadmap.get("final_artifact", {})
    live_search = roadmap.get("live_search", {})
    title = escape(_html_display_title(roadmap, language))
    full_title = escape(str(roadmap.get("title", "Learning Roadmap")))
    paper_metadata = _paper_metadata_from_roadmap(roadmap)
    study_bundle = roadmap.get("study_bundle", {})
    bundle_by_key, bundle_by_title = _bundle_lookup(study_bundle)
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
            <div><b>{escape(_label(language, 'status'))}</b><span>{escape(_localized_status_label(language, paper_metadata.get('metadata_status', 'partial')))}</span></div>
            <div><b>{escape(_label(language, 'concepts'))}</b><span>{escape(_join_or_unknown(paper_metadata.get('concepts', []), language))}</span></div>
          </div>
          <p class="meta">{escape(str(paper_metadata.get('abstract_snippet', '') or _label(language, 'not_available')))}</p>
          <p class="meta"><strong>{escape(_label(language, 'sections'))}:</strong> {escape(_join_or_unknown(paper_metadata.get('sections', []), language))}</p>
          <p class="meta"><strong>{escape(_label(language, 'keywords'))}:</strong> {escape(_join_or_unknown(paper_metadata.get('keywords', []), language))}</p>
          <p class="meta"><strong>{escape(_label(language, 'formula_candidates'))}:</strong> {escape(_join_or_unknown(paper_metadata.get('formula_candidates', []), language))}</p>
          <p class="meta"><strong>{escape(_label(language, 'code_links'))}:</strong> {escape(_join_or_unknown(paper_metadata.get('code_links', []), language))}</p>
        </section>
        """
    paper_lens_panel = ""
    if roadmap.get("paper_lens"):
        if language == "en":
            lens_title = "Target Paper Lens"
            lens_text = "Open the paper-centered reader that attaches resources, evidence, and tasks back to the target paper sections."
            lens_button = "Open Paper Lens"
        elif language == "bilingual":
            lens_title = "Target Paper Lens / 目标论文增强阅读器"
            lens_text = "Open the paper-centered reader that attaches resources, evidence, and tasks back to the target paper sections. / 打开以目标论文为中心的阅读器，把资料、证据和任务挂回论文章节。"
            lens_button = "Open Paper Lens / 进入目标论文阅读器"
        else:
            lens_title = "目标论文增强阅读器"
            lens_text = "打开以目标论文为中心的阅读器，把资料、证据和任务挂回论文章节。"
            lens_button = "进入目标论文阅读器"
        paper_lens_panel = f"""
        <section class="graph-panel paper-lens-entry-panel">
          <div class="phase-title-row">
            <h2>{escape(lens_title)}</h2>
            <a class="resource-action local-action" href="{escape(PAPER_LENS_FILE)}">{escape(lens_button)}</a>
          </div>
          <p class="meta">{escape(lens_text)}</p>
        </section>
        """
    artifact_panel = ""
    if artifact_requirements:
        artifact_panel = f"""
        <section class="graph-panel artifact-panel">
          <h2>{escape(_label(language, 'artifact_requirements'))}</h2>
          <div class="info-grid">
            <div><b>{escape(_label(language, 'runnable'))}</b><span>{escape(str(artifact_requirements.get('requires_runnable', False)))}</span></div>
            <div><b>{escape(_label(language, 'policy'))}</b><span>{escape(_localized_status_label(language, artifact_requirements.get('policy', 'not-required')))}</span></div>
            <div><b>{escape(_label(language, 'satisfied_by'))}</b><span>{escape(_join_or_unknown(artifact_requirements.get('satisfied_by', []), language))}</span></div>
            <div><b>{escape(_label(language, 'generated'))}</b><span>{escape(_join_or_unknown(generated_artifacts, language))}</span></div>
          </div>
        </section>
        """
    gaps_panel = ""
    if artifact_gaps:
        gap_items = "".join(
            f"<li><strong>{escape(_localized_status_label(language, gap.get('status', 'open')))}</strong>: {escape(str(gap.get('message', '')))} <span class=\"meta\">{escape(_label(language, 'resolved_by'))} {escape(_localized_reason_label(language, gap.get('resolved_by', _label(language, 'not_available'))))}</span></li>"
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
            f"<li><strong>{escape(_localized_dimension_label(language, name))}</strong>: {escape(_localized_status_label(language, item.get('level', 'unknown')))} <span class=\"meta\">{escape(_localized_controlled_text(language, item.get('evidence', '')))}</span></li>"
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
            f"<li><strong>{escape(str(item.get('title', '')))}</strong>: {escape(_localized_reason_label(language, item.get('reason', '')))}</li>"
            for item in route_audit.get("omitted_resources", [])[:6]
            if isinstance(item, dict)
        )
        coverage_note_html = ""
        if route_audit.get("coverage_note"):
            coverage_note_html = f"<p class=\"meta\">{escape(_label(language, 'coverage_note'))}: {escape(str(route_audit.get('coverage_note')))}</p>"
        route_panel = f"""
        <section class="graph-panel route-audit-panel">
          <h2>{escape(_label(language, 'route_audit'))}</h2>
          <p class="meta">{escape(_label(language, 'coverage'))}: {escape(f"{route_audit.get('coverage_ratio', 0):.2f}")}</p>
          <p class="meta">{escape(_label(language, 'coverage_gate'))}: {escape(_localized_status_label(language, route_audit.get('coverage_gate', {}).get('status', 'ready')))}</p>
          <p class="meta">{escape(_label(language, 'recommended_action'))}: {escape(str(route_audit.get('coverage_gate', {}).get('recommended_action', _label(language, 'not_specified'))))}</p>
          {coverage_note_html}
          <ul>{omitted_items or f'<li>{escape(_label(language, "not_available"))}</li>'}</ul>
        </section>
        """

    rag_panel = ""
    rag_evidence = roadmap.get("rag_evidence", {})
    if rag_evidence:
        summary = rag_evidence.get("summary", {})
        evidence_items = "".join(
            _html_evidence_chunk(item, language)
            for item in rag_evidence.get("top_chunks", [])
            if isinstance(item, dict)
        )
        rag_panel = f"""
        <section class="graph-panel rag-evidence-panel">
          <div class="phase-title-row">
            <h2>{escape(_label(language, 'evidence'))}</h2>
            <span class="badge">{escape(_localized_rag_mode(language, rag_evidence.get('mode', 'light')))}</span>
          </div>
          <p class="meta">{escape(_label(language, 'chunks'))}: {escape(str(summary.get('chunks', 0)))} / {escape(_label(language, 'resource_count'))}: {escape(str(summary.get('resources', 0)))}</p>
          <div class="evidence-grid">{evidence_items or f'<p class="empty">{escape(_label(language, "not_available"))}</p>'}</div>
        </section>
        """

    mastery_panel = ""
    mastery_evidence = roadmap.get("mastery_evidence", {})
    if mastery_evidence:
        evidence_cards: list[str] = []
        for item in mastery_evidence.get("required_evidence", []):
            if not isinstance(item, dict):
                continue
            resources = _join_or_unknown(item.get("resources", []), language)
            chunk_cards = "".join(
                _html_evidence_chunk(chunk, language, compact=True)
                for chunk in item.get("evidence_chunks", [])
                if isinstance(chunk, dict)
            )
            evidence_cards.append(
                f"""
                <article class="evidence-card">
                  <div class="resource-head">
                    <h3>{escape(str(item.get('title') or _localized_task_type(language, item.get('task_type', 'task'))))}</h3>
                    <span class="badge">{escape(_localized_status_label(language, item.get('review_status', 'open')))}</span>
                  </div>
                  <p class="meta"><strong>{escape(_label(language, 'required_evidence'))}:</strong> {escape(str(item.get('evidence', '')))}</p>
                  <p class="meta"><strong>{escape(_label(language, 'pass_criteria'))}:</strong> {escape(str(item.get('pass_criteria', '')))}</p>
                  <p class="meta"><strong>{escape(_label(language, 'resources'))}:</strong> {escape(resources)}</p>
                  {f'<div class="chunk-list">{chunk_cards}</div>' if chunk_cards else ''}
                </article>
                """
            )
        evidence_files = _join_or_unknown(mastery_evidence.get("evidence_files", []), language)
        mastery_panel = f"""
        <section class="graph-panel mastery-evidence-panel">
          <div class="phase-title-row">
            <h2>{escape(_label(language, 'mastery_evidence'))}</h2>
            <span class="badge">{escape(_localized_status_label(language, mastery_evidence.get('status', _label(language, 'unknown'))))}</span>
          </div>
          <p class="meta"><strong>{escape(_label(language, 'evidence_contract'))}:</strong> {escape(str(mastery_evidence.get('claim', '')))}</p>
          <p class="meta"><strong>{escape(_label(language, 'evidence_files'))}:</strong> {escape(evidence_files)}</p>
          <div class="evidence-grid">{''.join(evidence_cards) or f'<p class="empty">{escape(_label(language, "not_available"))}</p>'}</div>
        </section>
        """

    knowledge_graph_panel = _html_knowledge_graph_panel(
        knowledge_graph,
        language,
        roadmap.get("study_tasks", []),
        roadmap.get("mastery_evidence", {}),
    )

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

    study_bundle_panel = ""
    if study_bundle:
        summary = study_bundle.get("summary", {})
        manager = study_bundle.get("download_manager", {})
        bundle_rows: list[str] = []
        status_counts: dict[str, int] = {}
        completed = int(manager.get("completed", summary.get("completed", 0)) or 0)
        total = int(summary.get("total", 0) or 0)
        completion_percent = round((completed / total) * 100) if total else 0
        for row_index, resource in enumerate(study_bundle.get("resources", []), start=1):
            if not isinstance(resource, dict):
                continue
            status = str(resource.get("status", "unknown"))
            status_counts[status] = status_counts.get(status, 0) + 1
            route_status = str(resource.get("route_status", "unknown"))
            file_or_link = _bundle_link_actions(resource, language)
            retryable = bool(resource.get("retryable"))
            retry_label = _label(language, "retryable") if retryable else _label(language, "no")
            reason = _bundle_reason_label(language, resource.get("reason"))
            number = resource.get("index") or row_index
            local_available = "yes" if resource.get("local_href") else "no"
            bundle_rows.append(
                f"""
                <tr data-status="{escape(status)}" data-route="{escape(route_status)}" data-local="{escape(local_available)}" data-title="{escape(str(resource.get('title', ''))).lower()}">
                  <td class="num-cell">{escape(str(number))}</td>
                  <td class="title-cell">
                    <strong>{escape(str(resource.get('title', _label(language, 'unknown'))))}</strong>
                    <span class="meta">{escape(_localized_source_label(language, resource.get('source', _label(language, 'unknown'))))} / {escape(_localized_resource_type(language, resource.get('type', _label(language, 'unknown'))))}</span>
                  </td>
                  <td><span class="badge {escape(status)}">{escape(_bundle_status_label(language, status))}</span></td>
                  <td><span class="badge {escape(route_status)}">{escape(_route_status_label(language, route_status))}</span></td>
                  <td>{file_or_link}</td>
                  <td>{escape(str(resource.get('attempts', 0)))}</td>
                  <td>
                    <span class="badge {'failed' if retryable else 'omitted'}">{escape(retry_label)}</span>
                    <span class="meta">{escape(reason)}</span>
                  </td>
                </tr>
                """
            )
        status_filters = _bundle_status_filters(status_counts)
        filter_buttons = "".join(
            f'<button type="button" data-bundle-filter="{escape(status)}">{escape(_bundle_filter_label(language, status))}</button>'
            for status in status_filters
        )
        status_cards = "".join(
            f"""
            <div class="bundle-stat-card">
              <b>{escape(_bundle_status_label(language, status))}</b>
              <span>{escape(str(summary.get(status, 0)))}</span>
            </div>
            """
            for status in ("downloaded", "copied", "snapshotted", "generated", "link-only", "failed")
            if status in summary
        )
        study_bundle_panel = f"""
        <section class="graph-panel study-bundle-panel download-manager-panel">
          <div class="phase-title-row">
            <h2>{escape(_label(language, 'study_bundle'))}</h2>
            <span class="badge">{escape(_label(language, 'download_manager'))}</span>
            <span class="meta">{escape(_label(language, 'bundle_manifest'))}: {escape(str(study_bundle.get('manifest_file', 'study_bundle_manifest.json')))}</span>
          </div>
          <div class="bundle-summary-hero">
            <div>
              <span class="meta">{escape(_label(language, 'bundle_completion'))}</span>
              <strong>{escape(str(completed))} / {escape(str(total))}</strong>
            </div>
            <div class="bundle-progress" aria-label="{escape(_label(language, 'bundle_completion'))}">
              <span style="width:{completion_percent}%"></span>
            </div>
            <span class="badge">{escape(str(completion_percent))}%</span>
          </div>
          <div class="bundle-stat-grid">{status_cards}</div>
          <div class="info-grid bundle-dashboard">
            <div><b>{escape(_label(language, 'bundle_summary'))}</b><span>{escape(_bundle_summary_text(summary, language))}</span></div>
            <div><b>{escape(_label(language, 'bundle_scope'))}</b><span>{escape(_localized_bundle_scope(language, study_bundle.get('bundle_scope', summary.get('bundle_scope', 'all'))))}</span></div>
            <div><b>{escape(_label(language, 'downloaded_selected'))}</b><span>{escape(str(summary.get('downloaded_selected', 0)))}</span></div>
            <div><b>{escape(_label(language, 'downloaded_omitted'))}</b><span>{escape(str(summary.get('downloaded_omitted', 0)))}</span></div>
            <div><b>{escape(_label(language, 'completed'))}</b><span>{escape(str(completed))} / {escape(str(total))}</span></div>
            <div><b>{escape(_label(language, 'retryable'))}</b><span>{escape(str(manager.get('retryable', summary.get('retryable', 0))))}</span></div>
            <div><b>{escape(_label(language, 'bundle_readme'))}</b><span>{escape(str(study_bundle.get('readme_file', 'README.md')))}</span></div>
            <div><b>{escape(_label(language, 'download_queue'))}</b><span>{escape(str(manager.get('download_queue_file', 'download_queue.json')))}</span></div>
            <div><b>{escape(_label(language, 'retry_file'))}</b><span>{escape(str(manager.get('retry_file', 'retry_failed.md')))}</span></div>
            <div><b>{escape(_label(language, 'bundle_links'))}</b><span>{escape(str(study_bundle.get('links_file', 'links.md')))}</span></div>
          </div>
          <p class="meta">{escape(_label(language, 'bundle_policy'))}: {escape(str(study_bundle.get('policy', _label(language, 'not_specified'))))}</p>
          <div class="bundle-controls">
            <input type="search" data-bundle-search placeholder="{escape(_label(language, 'full_resource_table'))}">
            <div class="segmented">{filter_buttons}</div>
          </div>
          <div class="bundle-table-shell">
            <table class="bundle-table">
              <thead>
                <tr>
                  <th class="num-cell">#</th>
                  <th>{escape(_label(language, 'title'))}</th>
                  <th>{escape(_label(language, 'download_status'))}</th>
                  <th>{escape(_label(language, 'route'))}</th>
                  <th>{escape(_label(language, 'file_or_link'))}</th>
                  <th>{escape(_label(language, 'attempts'))}</th>
                  <th>{escape(_label(language, 'retry'))}</th>
                </tr>
              </thead>
              <tbody>{''.join(bundle_rows) or f'<tr><td colspan="7">{escape(_label(language, "not_available"))}</td></tr>'}</tbody>
            </table>
          </div>
        </section>
        """

    resource_library_panel = ""
    resource_library = roadmap.get("resource_library", [])
    if resource_library:
        library_cards: list[str] = []
        task_refs = _task_refs_by_resource(roadmap.get("study_tasks", []))
        route_values: set[str] = set()
        download_values: set[str] = set()
        type_values: set[str] = set()
        source_values: set[str] = set()
        local_values: set[str] = set()
        for resource in resource_library:
            route_status = str(resource.get("route_status", "omitted"))
            localized = resource.get("localized") if isinstance(resource.get("localized"), dict) else {}
            status_label = str(localized.get("route_status") or _route_status_label(language, route_status))
            phase = resource.get("selected_phase") or _label(language, "not_available")
            reason = localized.get("route_reason") or _localized_reason_label(language, resource.get("route_reason") or _label(language, "not_specified"))
            concepts = ", ".join(_localized_controlled_text(language, item) for item in resource.get("concepts", [])[:6]) or _label(language, "not_tagged")
            key_points = "".join(f"<li>{escape(_localized_controlled_text(language, item))}</li>" for item in resource.get("learning_key_points", [])[:3])
            focus = ", ".join(_localized_controlled_text(language, item) for item in resource.get("focus_areas", [])[:5]) or _label(language, "not_tagged")
            resource_type = str(resource.get("type", _label(language, "unknown")))
            resource_source = str(resource.get("source", _label(language, "unknown")))
            title_key = str(resource.get("title", "")).strip().lower()
            bundle_item = _bundle_for_resource(resource, bundle_by_key, bundle_by_title)
            download_status = str(bundle_item.get("status", "not_available"))
            task_ref_value = " ".join(task_refs.get(title_key, []))
            local_available = "yes" if bundle_item.get("local_href") else "no"
            primary_href = _primary_resource_href(resource, bundle_item)
            route_values.add(route_status)
            download_values.add(download_status)
            type_values.add(resource_type)
            source_values.add(resource_source)
            local_values.add(local_available)
            library_cards.append(
                f"""
                <article class="library-card" data-library-card
                  data-route="{escape(route_status)}"
                  data-download="{escape(download_status)}"
                  data-local="{escape(local_available)}"
                  data-source="{escape(resource_source)}"
                  data-type="{escape(resource_type)}"
                  data-task-refs="{escape(task_ref_value)}"
                  data-title="{escape(str(resource.get('title', '')).lower())}"
                  data-search="{escape(' '.join([str(resource.get('title', '')), concepts, focus, resource_source, resource_type, str(reason)]).lower())}">
                  <div class="resource-head">
                    <h3><a href="{escape(primary_href)}">{escape(str(resource.get('title', 'Resource')))}</a></h3>
                    <span class="badge {escape(route_status)}">{escape(status_label)}</span>
                    <span class="badge {escape(download_status)}">{escape(_bundle_status_label(language, download_status))}</span>
                  </div>
                  {_resource_link_actions(resource, bundle_item, language)}
                  <p class="meta">{escape(_localized_source_label(language, resource_source))} / {escape(_localized_resource_type(language, resource_type))} / {escape(str(resource.get('language', _label(language, 'unknown'))))} / {escape(str(resource.get('estimated_time', _label(language, 'unknown'))))}</p>
                  <p class="meta"><strong>{escape(_label(language, 'phase'))}:</strong> {escape(str(phase))}</p>
                  <p class="meta"><strong>{escape(_label(language, 'reason'))}:</strong> {escape(str(reason))}</p>
                  <p class="meta"><strong>{escape(_label(language, 'concepts'))}:</strong> {escape(concepts)}</p>
                  <p class="meta"><strong>{escape(_label(language, 'focus'))}:</strong> {escape(focus)}</p>
                  <ul>{key_points or f'<li>{escape(_label(language, "not_tagged"))}</li>'}</ul>
                </article>
                """
            )
        selected_count = sum(1 for resource in resource_library if isinstance(resource, dict) and resource.get("selected"))
        route_order = [value for value in ("selected", "generated", "omitted") if value in route_values]
        download_order = [
            value
            for value in ("downloaded", "copied", "snapshotted", "generated", "link-only", "failed", "not_available")
            if value in download_values
        ]
        download_order.extend(sorted(download_values - set(download_order)))
        type_order = sorted(type_values)
        source_order = sorted(source_values)
        local_order = [value for value in ("yes", "no") if value in local_values]
        filter_chips = "".join(
            [
                _html_filter_chips(language, "route", "filter_route", route_order),
                _html_filter_chips(language, "download", "filter_download", download_order),
                _html_filter_chips(language, "local", "local_available", local_order),
                _html_filter_chips(language, "type", "filter_type", type_order),
                _html_filter_chips(language, "source", "filter_source", source_order),
            ]
        )
        resource_library_panel = f"""
        <section class="graph-panel resource-library-panel">
          <div class="phase-title-row">
            <h2>{escape(_label(language, 'resource_library'))}</h2>
            <span class="meta">{escape(_label(language, 'selected_resources'))}: {escape(str(selected_count))} / {escape(str(len(resource_library)))}</span>
          </div>
          <div class="library-controls">
            <input class="resource-library-filter" type="search" data-library-search placeholder="{escape(_label(language, 'search_resources'))}">
            <button type="button" class="resource-filter-chip" data-local-only-filter>{escape(_label(language, 'show_local_resources'))}</button>
            <button type="button" class="resource-filter-chip clear-filter-chip" data-clear-resource-filters>{escape(_label(language, 'clear_filters'))}</button>
          </div>
          <div class="resource-filter-toolbar">{filter_chips}</div>
          <div class="library-grid">{''.join(library_cards)}</div>
        </section>
        """

    phase_cards: list[str] = []
    task_refs = _task_refs_by_resource(roadmap.get("study_tasks", []))
    for phase_index, phase in enumerate(roadmap.get("phases", []), start=1):
        resource_cards = []
        for resource in phase.get("resources", []):
            bundle_item = _bundle_for_resource(resource, bundle_by_key, bundle_by_title)
            primary_href = _primary_resource_href(resource, bundle_item)
            title_key = str(resource.get("title", "")).strip().lower()
            task_ref_value = " ".join(task_refs.get(title_key, []))
            key_points = "".join(f"<li>{escape(_localized_controlled_text(language, item))}</li>" for item in resource.get("learning_key_points", [])[:4])
            focus = "".join(f"<li>{escape(_localized_controlled_text(language, item))}</li>" for item in resource.get("focus_areas", [])[:4])
            local_badge = '<span class="badge local">LOCAL</span>' if resource.get("source") == "local-library" else ""
            resource_cards.append(
                f"""
                <article class="resource-card" data-phase-resource-card data-task-refs="{escape(task_ref_value)}">
                  <div class="resource-head">
                    <h3><a href="{escape(primary_href)}">{escape(str(resource.get('title', 'Resource')))}</a></h3>
                    {local_badge}<span class="badge">{escape(_localized_role_label(language, resource.get('critical_path_role', 'support')))}</span>
                  </div>
                  {_resource_link_actions(resource, bundle_item, language)}
                  <p class="meta">{escape(_localized_source_label(language, resource.get('source', _label(language, 'unknown'))))} / {escape(_localized_resource_type(language, resource.get('type', _label(language, 'unknown'))))} / {escape(str(resource.get('language', _label(language, 'unknown'))))} / {escape(str(resource.get('estimated_time', _label(language, 'unknown'))))}</p>
                  <div class="mini-grid">
                    <section><strong>{escape(_label(language, 'key_points'))}</strong><ul>{key_points or f'<li>{escape(_label(language, "not_tagged"))}</li>'}</ul></section>
                    <section><strong>{escape(_label(language, 'focus'))}</strong><ul>{focus or f'<li>{escape(_label(language, "not_tagged"))}</li>'}</ul></section>
                  </div>
                  <p class="why">{escape(_localized_controlled_text(language, resource.get('why_recommended', '')))}</p>
                </article>
                """
            )
        phase_cards.append(
            f"""
            <section class="phase-card" data-phase-card>
              <div class="phase-number">{phase_index}</div>
              <div class="phase-body">
                <div class="phase-title-row">
                  <h2>{escape(str(phase.get('name', 'Phase')))}</h2>
                  <div class="phase-actions">
                    <span>{escape(str(phase.get('estimated_time', 'unknown')))}</span>
                    <button type="button" class="phase-collapse-button" data-phase-toggle>{escape(_label(language, 'collapse'))}</button>
                  </div>
                </div>
                <div class="phase-content">
                  <p>{escape(str(phase.get('objective', '')))}</p>
                  <div class="resource-grid">{''.join(resource_cards) or f'<p class="empty">{escape(_label(language, "not_available"))}</p>'}</div>
                </div>
              </div>
            </section>
            """
        )

    checkpoints = "".join(f"<li>{escape(str(item))}</li>" for item in roadmap.get("checkpoints", []))
    graph_nodes = "".join(
        f"<span class=\"graph-pill {escape(str(node.get('kind', 'node')))}\">{escape(_localized_node_label(language, node))}</span>"
        for node in graph.get("nodes", [])[:18]
    )
    manual_sources = ", ".join(live_search.get("manual_link_only_sources", []) or [])
    manual_note = f"; manual-link-only: {escape(manual_sources)}" if manual_sources else ""
    html_lang = "zh-CN" if language == "zh-CN" else "en"
    collapse_label = json.dumps(_label(language, "collapse"), ensure_ascii=False)
    expand_label = json.dumps(_label(language, "expand"), ensure_ascii=False)
    only_current_label = json.dumps(_label(language, "only_current_task"), ensure_ascii=False)
    show_all_tasks_label = json.dumps(_label(language, "show_all_tasks"), ensure_ascii=False)
    download_manager_script = """
<script>
(() => {
  const collapseLabel = __COLLAPSE_LABEL__;
  const expandLabel = __EXPAND_LABEL__;
  const onlyCurrentLabel = __ONLY_CURRENT_LABEL__;
  const showAllTasksLabel = __SHOW_ALL_TASKS_LABEL__;
  const storage = (() => {
    try {
      const key = 'fields-study-flow-storage-test';
      window.localStorage.setItem(key, '1');
      window.localStorage.removeItem(key);
      return window.localStorage;
    } catch (error) {
      return null;
    }
  })();
  const progressKey = 'fields-study-flow-progress:' + location.pathname + ':' + document.title;
  let activeTask = '';
  let currentTaskOnly = false;
  const storageWarning = document.querySelector('[data-storage-warning]');
  if (!storage && storageWarning) storageWarning.hidden = false;

  const bundlePanel = document.querySelector('.download-manager-panel');
  if (bundlePanel) {
    const rows = Array.from(bundlePanel.querySelectorAll('.bundle-table tbody tr'));
    const search = bundlePanel.querySelector('[data-bundle-search]');
    const buttons = Array.from(bundlePanel.querySelectorAll('[data-bundle-filter]'));
    let activeStatus = 'all';
    function applyBundleFilter() {
      const query = (search?.value || '').trim().toLowerCase();
      rows.forEach((row) => {
        const status = row.dataset.status || '';
        const title = row.dataset.title || row.textContent.toLowerCase();
        const matchesStatus = activeStatus === 'all' || status === activeStatus;
        const matchesQuery = !query || title.includes(query);
        row.hidden = !(matchesStatus && matchesQuery);
      });
    }
    buttons.forEach((button) => {
      if (button.dataset.bundleFilter === 'all') button.classList.add('is-active');
      button.addEventListener('click', () => {
        activeStatus = button.dataset.bundleFilter || 'all';
        buttons.forEach((item) => item.classList.toggle('is-active', item === button));
        applyBundleFilter();
      });
    });
    search?.addEventListener('input', applyBundleFilter);
  }

  const libraryPanel = document.querySelector('.resource-library-panel');
  const currentTaskButton = document.querySelector('[data-current-task-filter]');
  if (libraryPanel) {
    const cards = Array.from(libraryPanel.querySelectorAll('[data-library-card]'));
    const search = libraryPanel.querySelector('[data-library-search]');
    const chips = Array.from(libraryPanel.querySelectorAll('.resource-filter-chip[data-filter-group]'));
    const clearButton = libraryPanel.querySelector('[data-clear-resource-filters]');
    const localOnlyButton = libraryPanel.querySelector('[data-local-only-filter]');
    const activeFilters = { route: new Set(), download: new Set(), local: new Set(), type: new Set(), source: new Set() };
    let localOnly = false;
    function matchesGroup(card, group) {
      const selected = activeFilters[group];
      if (!selected || selected.size === 0) return true;
      return selected.has(card.dataset[group] || '');
    }
    function matchesCurrentTask(card) {
      if (!currentTaskOnly || !activeTask) return true;
      const refs = (card.dataset.taskRefs || '').split(/\\s+/).filter(Boolean);
      return refs.includes(activeTask);
    }
    function matchesLocal(card) {
      return !localOnly || card.dataset.local === 'yes';
    }
    function applyLibraryFilter() {
      const query = (search?.value || '').trim().toLowerCase();
      cards.forEach((card) => {
        const haystack = [card.dataset.search || '', card.dataset.title || '', card.dataset.source || '', card.dataset.type || '', card.textContent.toLowerCase()].join(' ');
        const matchesFilters = matchesGroup(card, 'route') && matchesGroup(card, 'download') && matchesGroup(card, 'local') && matchesGroup(card, 'type') && matchesGroup(card, 'source');
        const matchesQuery = !query || haystack.includes(query);
        card.hidden = !(matchesFilters && matchesQuery && matchesCurrentTask(card) && matchesLocal(card));
      });
    }
    chips.forEach((chip) => {
      chip.addEventListener('click', () => {
        const group = chip.dataset.filterGroup || '';
        const value = chip.dataset.filterValue || '';
        if (!activeFilters[group]) return;
        if (activeFilters[group].has(value)) {
          activeFilters[group].delete(value);
          chip.classList.remove('is-active');
        } else {
          activeFilters[group].add(value);
          chip.classList.add('is-active');
        }
        applyLibraryFilter();
      });
    });
    clearButton?.addEventListener('click', () => {
      Object.values(activeFilters).forEach((set) => set.clear());
      chips.forEach((chip) => chip.classList.remove('is-active'));
      currentTaskOnly = false;
      localOnly = false;
      localOnlyButton?.classList.remove('is-active');
      if (currentTaskButton) {
        currentTaskButton.textContent = onlyCurrentLabel;
        currentTaskButton.classList.remove('is-active');
      }
      applyLibraryFilter();
    });
    localOnlyButton?.addEventListener('click', () => {
      localOnly = !localOnly;
      localOnlyButton.classList.toggle('is-active', localOnly);
      applyLibraryFilter();
    });
    search?.addEventListener('input', applyLibraryFilter);
    window.fieldsStudyFlowApplyLibraryFilter = applyLibraryFilter;
  }

  const kgPanel = document.querySelector('.knowledge-graph-panel');
  if (kgPanel) {
    const nodeButtons = Array.from(kgPanel.querySelectorAll('.kg-node-button, .kg-network-node'));
    const nodeCards = Array.from(kgPanel.querySelectorAll('[data-kg-node-card], .kg-network-node'));
    const edgeChips = Array.from(kgPanel.querySelectorAll('.kg-edge-chip, .kg-network-edge'));
    const stage = kgPanel.querySelector('.kg-network-stage');
    const canvas = kgPanel.querySelector('[data-kg-canvas]');
    const networkNodes = Array.from(kgPanel.querySelectorAll('.kg-network-node'));
    const edgePaths = Array.from(kgPanel.querySelectorAll('.kg-network-edge'));
    const layoutKey = 'fields-study-flow-kg-layout:' + location.pathname + ':' + document.title;
    let view = { x: 0, y: 0, scale: 1 };
    let dragState = null;
    let suppressNodeClick = false;
    function readLayout() {
      if (!storage) return {};
      try {
        return JSON.parse(storage.getItem(layoutKey) || '{}') || {};
      } catch (error) {
        return {};
      }
    }
    function writeLayout(extra = {}) {
      if (!storage) return;
      const positions = {};
      networkNodes.forEach((node) => {
        positions[node.dataset.kgNode || ''] = nodePosition(node);
      });
      try {
        storage.setItem(layoutKey, JSON.stringify({ view, positions, ...extra }));
      } catch (error) {
        if (storageWarning) storageWarning.hidden = false;
      }
    }
    function nodePosition(node) {
      return {
        x: Number.parseFloat(node.style.getPropertyValue('--kg-x')) || 50,
        y: Number.parseFloat(node.style.getPropertyValue('--kg-y')) || 50,
      };
    }
    function setNodePosition(node, x, y) {
      const clampedX = Math.max(4, Math.min(96, x));
      const clampedY = Math.max(8, Math.min(92, y));
      node.style.setProperty('--kg-x', clampedX.toFixed(1) + '%');
      node.style.setProperty('--kg-y', clampedY.toFixed(1) + '%');
    }
    function applyView() {
      if (!canvas) return;
      canvas.style.transform = `translate(${view.x}px, ${view.y}px) scale(${view.scale})`;
    }
    function edgePath(from, to) {
      const sx = from.x;
      const sy = from.y;
      const tx = to.x;
      const ty = to.y;
      const bend = Math.max(8, Math.abs(tx - sx) * 0.36);
      return `M ${sx.toFixed(1)} ${sy.toFixed(1)} C ${(sx + bend).toFixed(1)} ${sy.toFixed(1)}, ${(tx - bend).toFixed(1)} ${ty.toFixed(1)}, ${tx.toFixed(1)} ${ty.toFixed(1)}`;
    }
    function updateEdges() {
      const byId = new Map(networkNodes.map((node) => [node.dataset.kgNode || '', node]));
      edgePaths.forEach((path) => {
        const fromNode = byId.get(path.dataset.kgFrom || '');
        const toNode = byId.get(path.dataset.kgTo || '');
        if (!fromNode || !toNode) return;
        path.setAttribute('d', edgePath(nodePosition(fromNode), nodePosition(toNode)));
      });
    }
    function applySavedLayout() {
      const saved = readLayout();
      if (saved.view && Number.isFinite(saved.view.scale)) {
        view = {
          x: Number(saved.view.x) || 0,
          y: Number(saved.view.y) || 0,
          scale: Math.max(0.55, Math.min(2.2, Number(saved.view.scale) || 1)),
        };
      }
      if (saved.positions) {
        networkNodes.forEach((node) => {
          const position = saved.positions[node.dataset.kgNode || ''];
          if (position) setNodePosition(node, Number(position.x), Number(position.y));
        });
      }
      applyView();
      updateEdges();
    }
    function zoomBy(delta) {
      view.scale = Math.max(0.55, Math.min(2.2, view.scale + delta));
      applyView();
      writeLayout();
    }
    kgPanel.querySelector('[data-kg-zoom="in"]')?.addEventListener('click', () => zoomBy(0.12));
    kgPanel.querySelector('[data-kg-zoom="out"]')?.addEventListener('click', () => zoomBy(-0.12));
    kgPanel.querySelector('[data-kg-fit]')?.addEventListener('click', () => {
      view = { x: 0, y: 0, scale: 1 };
      applyView();
      writeLayout();
    });
    kgPanel.querySelector('[data-kg-reset]')?.addEventListener('click', () => {
      if (storage) storage.removeItem(layoutKey);
      networkNodes.forEach((node) => {
        setNodePosition(node, Number(node.dataset.kgInitialX) || 50, Number(node.dataset.kgInitialY) || 50);
      });
      view = { x: 0, y: 0, scale: 1 };
      applyView();
      updateEdges();
    });
    stage?.addEventListener('wheel', (event) => {
      event.preventDefault();
      zoomBy(event.deltaY < 0 ? 0.08 : -0.08);
    }, { passive: false });
    stage?.addEventListener('pointerdown', (event) => {
      const node = event.target.closest?.('.kg-network-node');
      if (node) {
        const position = nodePosition(node);
        dragState = { type: 'node', node, startX: event.clientX, startY: event.clientY, nodeX: position.x, nodeY: position.y, moved: false };
      } else {
        dragState = { type: 'pan', startX: event.clientX, startY: event.clientY, viewX: view.x, viewY: view.y, moved: false };
      }
      stage.setPointerCapture?.(event.pointerId);
    });
    stage?.addEventListener('pointermove', (event) => {
      if (!dragState) return;
      const dx = event.clientX - dragState.startX;
      const dy = event.clientY - dragState.startY;
      if (Math.abs(dx) + Math.abs(dy) > 3) dragState.moved = true;
      if (dragState.type === 'node') {
        const rect = stage.getBoundingClientRect();
        const x = dragState.nodeX + (dx / Math.max(1, rect.width * view.scale)) * 100;
        const y = dragState.nodeY + (dy / Math.max(1, rect.height * view.scale)) * 100;
        setNodePosition(dragState.node, x, y);
        updateEdges();
      } else {
        view.x = dragState.viewX + dx;
        view.y = dragState.viewY + dy;
        applyView();
      }
    });
    stage?.addEventListener('pointerup', () => {
      if (!dragState) return;
      suppressNodeClick = Boolean(dragState.moved);
      writeLayout();
      dragState = null;
      window.setTimeout(() => { suppressNodeClick = false; }, 0);
    });
    applySavedLayout();
    function neighborIds(nodeId) {
      const ids = new Set([nodeId]);
      edgeChips.forEach((edge) => {
        if (edge.dataset.kgFrom === nodeId) ids.add(edge.dataset.kgTo || '');
        if (edge.dataset.kgTo === nodeId) ids.add(edge.dataset.kgFrom || '');
      });
      return ids;
    }
    function setActiveNode(nodeId) {
      const neighbors = neighborIds(nodeId);
      nodeCards.forEach((card) => {
        const id = card.dataset.kgNodeCard || card.dataset.kgNode || '';
        card.classList.toggle('kg-node-active', id === nodeId);
        card.classList.toggle('kg-node-neighbor', id !== nodeId && neighbors.has(id));
      });
      edgeChips.forEach((edge) => {
        const active = edge.dataset.kgFrom === nodeId || edge.dataset.kgTo === nodeId;
        edge.classList.toggle('kg-edge-active', active);
      });
      const taskNode = nodeButtons.find((button) => (button.dataset.kgNode || '') === nodeId);
      if (taskNode?.dataset.taskId) setActiveTask(taskNode.dataset.taskId, false, false, true);
    }
    nodeButtons.forEach((button) => {
      button.addEventListener('click', () => {
        if (suppressNodeClick) return;
        setActiveNode(button.dataset.kgNode || '');
      });
    });
  }

  const taskCards = Array.from(document.querySelectorAll('[data-guide-task]'));
  const progressChecks = Array.from(document.querySelectorAll('.task-progress-checkbox'));
  const progressLabel = document.querySelector('[data-task-progress-label]');
  function readProgress() {
    if (!storage) return {};
    try {
      return JSON.parse(storage.getItem(progressKey) || '{}') || {};
    } catch (error) {
      return {};
    }
  }
  function writeProgress(progress) {
    if (!storage) return;
    try {
      storage.setItem(progressKey, JSON.stringify(progress));
    } catch (error) {
      if (storageWarning) storageWarning.hidden = false;
    }
  }
  function updateProgressLabel() {
    const done = progressChecks.filter((box) => box.checked).length;
    if (progressLabel) progressLabel.textContent = done + ' / ' + progressChecks.length;
  }
  function taskRefsContain(element, taskId) {
    return (element.dataset.taskRefs || '').split(/\\s+/).filter(Boolean).includes(taskId);
  }
  function setActiveTask(taskId, syncNode = true, scrollToContext = false, scrollTaskCard = false) {
    activeTask = taskId || activeTask;
    taskCards.forEach((card) => card.classList.toggle('task-guide-active', card.dataset.guideTask === activeTask));
    if (scrollTaskCard) {
      const activeCard = taskCards.find((card) => card.dataset.guideTask === activeTask);
      activeCard?.scrollIntoView?.({ behavior: 'smooth', block: 'nearest' });
    }
    const relatedResources = Array.from(document.querySelectorAll('[data-phase-resource-card], [data-library-card]'));
    relatedResources.forEach((card) => card.classList.toggle('task-resource-active', taskRefsContain(card, activeTask)));
    if (syncNode) {
      document.querySelectorAll('.kg-network-node').forEach((node) => {
        const related = node.dataset.taskId === activeTask || node.dataset.kgNode === activeTask;
        node.classList.toggle('kg-node-active', related);
      });
      document.querySelectorAll('.kg-network-edge, .kg-edge-chip').forEach((edge) => {
        const related = edge.dataset.kgFrom === activeTask || edge.dataset.kgTo === activeTask;
        edge.classList.toggle('kg-edge-active', related);
      });
    }
    if (window.fieldsStudyFlowApplyLibraryFilter) window.fieldsStudyFlowApplyLibraryFilter();
    if (scrollToContext) {
      const target = relatedResources.find((card) => taskRefsContain(card, activeTask) && !card.hidden) || relatedResources.find((card) => taskRefsContain(card, activeTask));
      target?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
    }
  }
  const savedProgress = readProgress();
  progressChecks.forEach((box) => {
    box.checked = Boolean(savedProgress[box.dataset.taskId || '']);
    box.addEventListener('change', () => {
      const progress = readProgress();
      progress[box.dataset.taskId || ''] = box.checked;
      writeProgress(progress);
      updateProgressLabel();
    });
  });
  taskCards.forEach((card) => {
    card.addEventListener('click', (event) => {
      if (event.target?.matches?.('input')) return;
      setActiveTask(card.dataset.guideTask || '', true, true);
    });
  });
  currentTaskButton?.addEventListener('click', () => {
    if (!activeTask && taskCards[0]) setActiveTask(taskCards[0].dataset.guideTask || '', false);
    currentTaskOnly = !currentTaskOnly;
    currentTaskButton.classList.toggle('is-active', currentTaskOnly);
    currentTaskButton.textContent = currentTaskOnly ? showAllTasksLabel : onlyCurrentLabel;
    if (window.fieldsStudyFlowApplyLibraryFilter) window.fieldsStudyFlowApplyLibraryFilter();
  });
  updateProgressLabel();
  if (taskCards[0]) setActiveTask(taskCards[0].dataset.guideTask || '', false);

  document.querySelectorAll('[data-phase-toggle]').forEach((button) => {
    button.addEventListener('click', () => {
      const card = button.closest('[data-phase-card]');
      const content = card?.querySelector('.phase-content');
      if (!content) return;
      const collapsed = content.hidden;
      content.hidden = !collapsed;
      card.classList.toggle('is-collapsed', !collapsed);
      button.textContent = collapsed ? collapseLabel : expandLabel;
    });
  });
})();
</script>
""".replace("__COLLAPSE_LABEL__", collapse_label).replace("__EXPAND_LABEL__", expand_label).replace("__ONLY_CURRENT_LABEL__", only_current_label).replace("__SHOW_ALL_TASKS_LABEL__", show_all_tasks_label)

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
      margin:0; font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Noto Sans SC","Source Han Sans SC",Arial,sans-serif; color:var(--ink);
      background:linear-gradient(180deg,#fbfdff 0%,#f1f6fb 100%);
      font-size:15px; line-height:1.6;
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
    .phase-actions {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; }}
    h2 {{ margin:0; font-size:21px; line-height:1.28; letter-spacing:0; font-weight:750; }}
    .phase-body p, .meta, .why {{ color:var(--muted); line-height:1.5; }}
    .resource-grid, .library-grid {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(250px,1fr)); margin-top:14px; }}
    .library-grid {{ grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); }}
    .evidence-grid {{ display:grid; gap:12px; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); margin-top:14px; }}
    .resource-card, .library-card, .evidence-card, .evidence-chip {{ min-width:0; border:1px solid #e4ebf4; background:#f9fbff; border-radius:8px; padding:14px; }}
    .evidence-chip {{ background:#fffdf6; border-color:#eadca8; }}
    .evidence-chip.compact {{ padding:10px; margin-top:8px; background:#fff; }}
    .evidence-chip p {{ margin:8px 0; color:var(--ink); line-height:1.55; }}
    .evidence-toggle {{ cursor:pointer; font-weight:700; color:#41607e; overflow-wrap:anywhere; }}
    .chunk-list {{ display:grid; gap:8px; margin-top:10px; }}
    .resource-head {{ display:flex; align-items:flex-start; gap:8px; flex-wrap:wrap; }}
    h3 {{ flex:1 1 170px; min-width:0; margin:0; font-size:17px; line-height:1.25; letter-spacing:0; }}
    a {{ color:#255f9f; text-decoration:none; }}
    .badge {{ display:inline-flex; align-items:center; min-height:24px; padding:3px 8px; border-radius:999px; background:#eef4fb; color:#41607e; font-size:12px; font-weight:700; }}
    .badge.local {{ background:#e7f6ec; color:#247144; }}
    .badge.selected {{ background:#e7f6ec; color:#247144; }}
    .badge.generated {{ background:#fff4d7; color:#7a5a00; }}
    .badge.omitted {{ background:#f1f4f8; color:#647085; }}
    .badge.downloaded, .badge.copied {{ background:#e7f6ec; color:#247144; }}
    .badge.snapshotted {{ background:#e8f4ff; color:#255f9f; }}
    .badge.link-only {{ background:#fff4d7; color:#7a5a00; }}
    .badge.failed {{ background:#fdecec; color:#9b2f2d; }}
    .bundle-list .badge {{ margin-left:8px; margin-right:8px; }}
    .resource-actions {{ display:flex; flex-wrap:wrap; gap:7px; margin:9px 0 2px; }}
    .resource-action, .table-link {{
      display:inline-flex; align-items:center; max-width:100%; border:1px solid #d8e3ef; border-radius:8px;
      background:#fff; color:#255f9f; padding:5px 8px; font-size:12px; font-weight:700;
      overflow-wrap:anywhere; word-break:break-word;
    }}
    .local-action, .table-link[href] {{ background:#e7f6ec; border-color:#b7dfc4; color:#247144; }}
    .original-action, .original-link {{ background:#f7fafd; color:#41607e; }}
    .task-resource-active {{ outline:3px solid rgba(232,188,69,.28); background:#fffdf5; }}
    .bundle-summary-hero {{
      display:grid; grid-template-columns:minmax(140px,auto) minmax(180px,1fr) auto; gap:12px;
      align-items:center; padding:12px; border:1px solid #dfe8f3; border-radius:8px; background:#f8fbff; margin:12px 0;
    }}
    .bundle-summary-hero strong {{ display:block; font-size:22px; line-height:1.1; }}
    .bundle-progress {{ height:12px; border-radius:999px; overflow:hidden; background:#e5edf6; }}
    .bundle-progress span {{ display:block; height:100%; border-radius:inherit; background:linear-gradient(90deg,#70bd82,#4f9fd8); }}
    .bundle-stat-grid {{ display:grid; gap:10px; grid-template-columns:repeat(auto-fit,minmax(128px,1fr)); margin:10px 0 12px; }}
    .bundle-stat-card {{ border:1px solid #e4ebf4; border-radius:8px; background:#fff; padding:10px 12px; }}
    .bundle-stat-card b {{ display:block; color:#657085; font-size:12px; margin-bottom:4px; }}
    .bundle-stat-card span {{ font-size:20px; font-weight:800; }}
    .bundle-dashboard {{ grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); }}
    .bundle-controls {{ display:flex; align-items:center; justify-content:space-between; gap:10px; margin:14px 0 10px; flex-wrap:wrap; }}
    .bundle-controls input {{ min-width:min(100%,260px); flex:1 1 260px; border:1px solid #d8e3ef; border-radius:8px; padding:9px 11px; font:inherit; color:var(--ink); background:#fff; }}
    .library-controls {{ display:flex; align-items:center; justify-content:space-between; gap:10px; margin:14px 0 10px; flex-wrap:wrap; }}
    .library-controls input {{ min-width:min(100%,260px); flex:1 1 260px; border:1px solid #d8e3ef; border-radius:8px; padding:9px 11px; font:inherit; color:var(--ink); background:#fff; }}
    .phase-collapse-button, .kg-node-button {{
      border:1px solid #d8e3ef; border-radius:8px; background:#fff; color:#255f9f; padding:6px 9px;
      font:inherit; font-size:13px; font-weight:700; cursor:pointer; text-align:left; max-width:100%;
    }}
    .kg-node-button {{ border:0; padding:0; background:transparent; color:var(--ink); font-size:inherit; line-height:inherit; }}
    .phase-card.is-collapsed {{ opacity:.92; }}
    .segmented {{ display:flex; gap:6px; flex-wrap:wrap; }}
    .segmented button {{ border:1px solid #d8e3ef; border-radius:8px; background:#f7fafd; color:#41607e; padding:7px 10px; font:inherit; font-size:13px; font-weight:700; cursor:pointer; }}
    .segmented button.is-active {{ background:#255f9f; border-color:#255f9f; color:#fff; }}
    .bundle-table-shell {{ max-height:520px; overflow:auto; border:1px solid #dfe8f3; border-radius:8px; background:#fff; }}
    .bundle-table {{ width:100%; min-width:860px; table-layout:fixed; border-collapse:separate; border-spacing:0; }}
    .bundle-table th, .bundle-table td {{ padding:10px 11px; border-bottom:1px solid #e7edf5; vertical-align:top; text-align:left; overflow-wrap:anywhere; word-break:break-word; }}
    .bundle-table th {{ position:sticky; top:0; z-index:1; background:#eef4fb; color:#41607e; font-size:12px; text-transform:uppercase; }}
    .bundle-table th:nth-child(1), .bundle-table td:nth-child(1) {{ width:48px; text-align:right; }}
    .bundle-table th:nth-child(2), .bundle-table td:nth-child(2) {{ width:28%; }}
    .bundle-table th:nth-child(5), .bundle-table td:nth-child(5) {{ width:28%; }}
    .bundle-table th:nth-child(6), .bundle-table td:nth-child(6) {{ width:86px; text-align:right; }}
    .title-cell strong, .title-cell .meta, .table-link {{ display:block; min-width:0; }}
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
    .kg-flow {{ display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:12px; margin-top:14px; align-items:start; }}
    .kg-column {{ min-width:0; border:1px solid #dfe8f3; border-radius:8px; background:#f8fbff; padding:10px; }}
    .kg-column h3 {{ margin:0 0 10px; font-size:15px; color:#41607e; }}
    .kg-node-list {{ display:grid; gap:10px; }}
    .kg-node {{ min-width:0; border:1px solid #e4ebf4; border-radius:8px; background:#fff; padding:10px; }}
    .kg-node-active {{ outline:3px solid rgba(79,159,216,.24); background:#f5fbff; }}
    .kg-node.concept {{ border-left:4px solid var(--blue); }}
    .kg-node.resource {{ border-left:4px solid var(--green); }}
    .kg-node.task {{ border-left:4px solid var(--gold); }}
    .kg-node.assessment {{ border-left:4px solid var(--purple); }}
    .kg-edge-list {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }}
    .kg-edge-chip {{ display:inline-flex; flex-direction:column; max-width:100%; gap:2px; padding:6px 8px; border-radius:8px; background:#eef4fb; color:#41607e; font-size:12px; line-height:1.3; overflow-wrap:anywhere; word-break:break-word; }}
    .kg-edge-active {{ background:#dff1ff; color:#1f5d93; box-shadow:inset 0 0 0 1px #8fc7ef; }}
    .kg-edge-chip b {{ color:#172033; }}
    .kg-edge-chip em {{ color:#657085; font-style:normal; }}
    .learning-console-grid {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(280px,340px); gap:14px; margin-top:14px; align-items:stretch; }}
    .kg-network-controls {{ display:flex; gap:8px; flex-wrap:wrap; margin:12px 0 4px; }}
    .kg-network-controls button {{
      border:1px solid #d8e3ef; border-radius:8px; background:#fff; color:#255f9f;
      padding:7px 10px; font:inherit; font-size:13px; font-weight:700; cursor:pointer;
    }}
    .kg-network-stage {{ position:relative; min-height:440px; border:1px solid #dfe8f3; border-radius:8px; background:radial-gradient(circle at 50% 48%,#ffffff 0%,#f6fbff 58%,#eef6ff 100%); overflow:hidden; }}
    .kg-network-stage {{ cursor:grab; touch-action:none; }}
    .kg-network-stage:active {{ cursor:grabbing; }}
    .kg-network-canvas {{ position:absolute; inset:0; transform-origin:0 0; transition:transform .08s ease-out; }}
    .kg-network-svg {{ position:absolute; inset:0; width:100%; height:100%; pointer-events:none; }}
    .kg-network-edge {{ fill:none; stroke:#b8cbe0; stroke-width:1.2; vector-effect:non-scaling-stroke; opacity:.82; transition:stroke .16s ease, opacity .16s ease, stroke-width .16s ease; }}
    .kg-network-edge.kg-edge-active {{ stroke:#2e7fbd; stroke-width:2.2; opacity:1; }}
    .kg-network-node {{
      position:absolute; left:var(--kg-x); top:var(--kg-y); transform:translate(-50%,-50%);
      width:min(190px,26%); min-height:74px; display:flex; flex-direction:column; gap:3px;
      border:1px solid #d7e3f0; border-left-width:5px; border-radius:8px; background:#fff; color:var(--ink);
      padding:9px 10px; box-shadow:0 10px 24px rgba(44,72,105,.12); text-align:left; cursor:pointer; z-index:2;
      font:inherit; overflow-wrap:anywhere; word-break:break-word; user-select:none; touch-action:none;
    }}
    .kg-network-node strong {{ display:block; font-size:13px; line-height:1.25; max-height:3.8em; overflow:hidden; }}
    .kg-network-node .meta {{ font-size:11px; line-height:1.25; margin:0; }}
    .kg-node-kind {{ color:#41607e; font-size:11px; font-weight:800; }}
    .kg-network-node.concept {{ border-left-color:var(--blue); }}
    .kg-network-node.resource {{ border-left-color:var(--green); }}
    .kg-network-node.task {{ border-left-color:var(--gold); }}
    .kg-network-node.assessment {{ border-left-color:var(--purple); }}
    .kg-network-node.kg-node-active, .kg-node.kg-node-active {{ outline:3px solid rgba(79,159,216,.26); background:#f5fbff; }}
    .kg-network-node.kg-node-neighbor {{ box-shadow:0 10px 24px rgba(79,159,216,.18); }}
    .task-guide-rail {{ min-width:0; border:1px solid #dfe8f3; border-radius:8px; background:#fbfdff; padding:12px; display:flex; flex-direction:column; gap:10px; }}
    .task-guide-rail h3 {{ flex:0 1 auto; font-size:16px; }}
    .task-guide-list {{ display:grid; gap:10px; max-height:520px; overflow:auto; padding-right:2px; }}
    .task-guide-card {{ border:1px solid #e4ebf4; background:#fff; border-radius:8px; padding:11px; cursor:pointer; }}
    .task-guide-card.task-guide-active {{ border-color:#8fc7ef; background:#f5fbff; box-shadow:inset 0 0 0 1px #d6edff; }}
    .task-progress-row {{ display:grid; grid-template-columns:22px minmax(0,1fr); gap:8px; align-items:start; cursor:pointer; }}
    .task-progress-checkbox {{ width:18px; height:18px; margin-top:3px; accent-color:#255f9f; }}
    .task-progress-row span, .task-progress-row strong, .task-progress-row b {{ min-width:0; overflow-wrap:anywhere; word-break:break-word; }}
    .task-progress-row b {{ display:block; color:#41607e; font-size:12px; }}
    .task-progress-row strong {{ display:block; font-size:14px; line-height:1.35; }}
    .current-task-filter, .resource-filter-chip {{
      border:1px solid #d8e3ef; border-radius:8px; background:#f7fafd; color:#41607e;
      padding:7px 10px; font:inherit; font-size:13px; font-weight:700; cursor:pointer; text-align:left;
    }}
    .current-task-filter.is-active, .resource-filter-chip.is-active {{ background:#255f9f; border-color:#255f9f; color:#fff; }}
    .resource-filter-toolbar {{ display:grid; gap:8px; margin:10px 0 14px; }}
    .filter-chip-row {{ display:grid; grid-template-columns:96px minmax(0,1fr); gap:8px; align-items:start; }}
    .filter-chip-list {{ display:flex; gap:6px; flex-wrap:wrap; min-width:0; }}
    .clear-filter-chip {{ background:#fff; }}
    .empty {{ margin:0; color:var(--muted); }}
    @media (max-width:640px) {{
      main {{ padding-inline:12px; }}
      h1 {{ font-size:24px; line-height:1.16; }}
      .phase-card {{ grid-template-columns:42px minmax(0,1fr); }}
      .phase-body {{ padding:14px; }}
      .resource-grid, .library-grid, .evidence-grid {{ grid-template-columns:1fr; }}
      .learning-console-grid {{ grid-template-columns:1fr; }}
      .kg-network-stage {{ min-height:620px; overflow:auto; }}
      .kg-network-node {{ width:min(210px,42%); }}
      .task-guide-list {{ max-height:none; overflow:visible; }}
      .filter-chip-row {{ grid-template-columns:1fr; }}
      .kg-flow {{ grid-template-columns:1fr; }}
      .bundle-summary-hero {{ grid-template-columns:1fr; }}
      .bundle-table {{ min-width:720px; }}
    }}
    @media (max-width:520px) {{
      .summary-grid, .info-grid, .mini-grid {{ grid-template-columns:1fr; }}
      .graph-panel {{ padding:14px; }}
    }}
  </style>
</head>
<body>
<main class="interactive-roadmap" data-learning-console="learning-console">
  <header>
    <h1>{title}</h1>
    <div class="summary-grid">
      <div class="summary-card"><b>{escape(_label(language, 'goal'))}</b><span>{escape(str(profile.get('goal', '')))}</span></div>
      <div class="summary-card"><b>{escape(_label(language, 'mode'))}</b><span>{escape(_localized_route_depth(language, strategy.get('mode', 'balanced')))} / {escape(_localized_target_kind(language, strategy.get('target_kind', 'auto')))}</span></div>
      <div class="summary-card"><b>{escape(_label(language, 'readiness'))}</b><span>{escape(_localized_status_label(language, strategy.get('readiness', 'ready')))}</span></div>
      <div class="summary-card"><b>{escape(_label(language, 'total_time'))}</b><span>{escape(str(strategy.get('estimated_total_time', _label(language, 'unknown'))))}</span></div>
      <div class="summary-card"><b>{escape(_label(language, 'resources'))}</b><span>{escape(str(strategy.get('selected_resources', 0)))} / {escape(str(strategy.get('candidate_resources', 0)))}</span></div>
    </div>
  </header>
  {paper_lens_panel}
  {paper_panel}
  {artifact_panel}
  {gaps_panel}
  {quality_panel}
  {route_panel}
  {rag_panel}
  {mastery_panel}
  {knowledge_graph_panel}
  {next_actions_panel}
  {study_bundle_panel}
  {resource_library_panel}
  <section class="graph-panel">
    <h2>{escape(_label(language, 'mastery_graph'))}</h2>
    <p>{escape(str(strategy.get('principle', '')))}</p>
    <div class="graph-pills">{graph_nodes}</div>
  </section>
  <div class="roadmap-grid">{''.join(phase_cards)}</div>
  <section class="graph-panel">
    <h2>{escape(_label(language, 'final_artifact'))}</h2>
    <p><strong>{escape(_localized_artifact_type(language, artifact.get('type', 'unknown')))}</strong>: {escape(str(artifact.get('evidence', '')))}</p>
    <h2>{escape(_label(language, 'checkpoints'))}</h2>
    <ul>{checkpoints}</ul>
    <p class="meta">{escape(_label(language, 'live_search'))}: {escape(_localized_status_label(language, live_search.get('status', 'not_requested')))}{manual_note}</p>
  </section>
</main>
{download_manager_script}
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


def _html_display_title(roadmap: dict[str, Any], language: str) -> str:
    paper_metadata = _paper_metadata_from_roadmap(roadmap)
    base = str(paper_metadata.get("title", "")).strip()
    if not base:
        goal = str(roadmap.get("profile", {}).get("goal") or roadmap.get("title") or "Learning Roadmap")
        base = _compact_goal_title(goal)
    else:
        base = _compact_academic_title(base)
    if language == "zh-CN":
        return f"{base} 学习路线"
    if language == "bilingual":
        return f"{base} Roadmap / 学习路线"
    return f"{base} Roadmap"


def _compact_goal_title(goal: str) -> str:
    text = re.sub(r"^(Learning Roadmap|学习路线)\s*[:：]\s*", "", goal).strip()
    for separator in ("，", ",", "；", ";"):
        if separator in text:
            text = text.split(separator, 1)[0].strip()
    if ":" in text:
        right = text.rsplit(":", 1)[-1].strip()
        if 8 <= len(right) <= 90:
            text = right
    return _truncate(text or "Learning Roadmap", 72)


def _compact_academic_title(title: str) -> str:
    text = re.sub(r"\s+", " ", title).strip()
    if ":" in text:
        prefix = text.split(":", 1)[0].strip()
        if 6 <= len(prefix) <= 52:
            return prefix
    return _truncate(text, 72)


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
    for index, (task_type, title) in enumerate(_mastery_task_specs(profile, target_kind), start=1):
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
                "evidence_chunks": _task_evidence_chunks(task_type, supporting),
            }
        )
    return tasks


def _task_evidence_chunks(task_type: str, resources: list[Resource]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for resource in resources:
        metadata = resource.metadata.get("rag") if isinstance(resource.metadata, dict) else None
        if not isinstance(metadata, dict):
            continue
        for chunk in metadata.get("top_chunks", []):
            if not isinstance(chunk, dict):
                continue
            public_chunk = {key: value for key, value in chunk.items() if key != "text"}
            public_chunk["task_type"] = task_type
            chunks.append(public_chunk)
            if len(chunks) >= 3:
                return chunks
    return chunks


def _mastery_evidence(
    profile: LearnerProfile,
    study_tasks: list[dict[str, Any]],
    final_artifact: dict[str, Any],
    route_audit: dict[str, Any],
    generated_artifacts: list[str],
) -> dict[str, Any]:
    coverage_status = str(route_audit.get("coverage_gate", {}).get("status", "ready"))
    status = "needs-resources" if coverage_status == "insufficient-evidence" else "ready-for-evidence"
    if not study_tasks:
        status = "needs-tasks"
    required_evidence: list[dict[str, Any]] = []
    for task in study_tasks:
        resources = [str(title) for title in task.get("resource_titles", []) if str(title)]
        required_evidence.append(
            {
                "task_id": str(task.get("id", "")),
                "task_type": str(task.get("type", "task")),
                "title": str(task.get("title", "")),
                "evidence": str(task.get("evidence", "")),
                "pass_criteria": str(task.get("acceptance", "")),
                "resources": resources,
                "estimated_minutes": task.get("estimated_minutes"),
                "evidence_chunks": task.get("evidence_chunks", []),
                "review_status": "open",
            }
        )
    evidence_files = [
        path
        for path in generated_artifacts
        if path.startswith("artifact_template/") and path.endswith((".md", ".ipynb", ".py"))
    ]
    return {
        "status": status,
        "claim": _localized(
            profile,
            "Learning is not complete until every evidence item is filled and reviewable.",
            "只有每项证据都填写并可复查，才算完成学习。",
        ),
        "final_artifact": final_artifact.get("type", "unknown"),
        "required_evidence": required_evidence,
        "evidence_files": evidence_files,
    }


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


def _next_actions(profile: LearnerProfile, study_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for index, task in enumerate(study_tasks[:3], start=1):
        resources = task.get("resource_titles", [])
        resource_hint = resources[0] if resources else "selected route resource"
        actions.append(
            {
                "order": index,
                "task_id": task.get("id", f"task-{index}"),
                "title": _next_action_title(profile, task, resource_hint),
                "estimated_minutes": task.get("estimated_minutes", 45),
                "evidence": task.get("evidence", ""),
            }
        )
    return actions


def _next_action_title(profile: LearnerProfile, task: dict[str, Any], resource_hint: str) -> str:
    task_title = str(task.get("title") or task.get("type") or "task")
    task_type = str(task.get("type") or "task")
    return _localized(
        profile,
        f"Start {task_type} with {resource_hint}",
        f"从 {resource_hint} 开始：{task_title}",
    )


def _resource_discovery_route_audit(
    profile: LearnerProfile,
    original_route_audit: dict[str, Any],
    discovery_route_audit: dict[str, Any],
    coverage_gate: dict[str, Any],
) -> dict[str, Any]:
    route_audit = dict(discovery_route_audit)
    original_ratio = float(coverage_gate.get("coverage_ratio", original_route_audit.get("coverage_ratio", 0.0)))
    route_audit["coverage_ratio"] = round(original_ratio, 3)
    route_audit["needed_terms"] = original_route_audit.get("needed_terms", [])
    route_audit["covered_terms"] = original_route_audit.get("covered_terms", [])
    route_audit["candidate_minutes"] = original_route_audit.get("candidate_minutes", route_audit.get("candidate_minutes", 0))
    route_audit["estimated_minutes_saved"] = original_route_audit.get("estimated_minutes_saved", route_audit.get("estimated_minutes_saved", 0))
    route_audit["coverage_gate"] = coverage_gate
    route_audit["fallback_selected_coverage_ratio"] = discovery_route_audit.get("coverage_ratio", 0)
    route_audit["coverage_note"] = _localized(
        profile,
        "Coverage is measured against the original target-specific candidate resources before the resource-discovery fallback.",
        "覆盖率按进入资源发现兜底前的目标相关候选资源计算。",
    )
    return route_audit


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
        language="zh-CN" if profile.output_language == "zh-CN" else "en",
        difficulty="beginner",
        concepts=concepts,
        estimated_time="60min",
        estimated_minutes=60,
        learning_key_points=[
            _localized(profile, "find one primary paper or official reference for each missing concept", "为每个缺口概念找到一篇主论文或官方参考资料"),
            _localized(profile, "prefer official docs, maintained repositories, and recognized courses", "优先选择官方文档、维护良好的代码仓库和公认课程"),
            _localized(profile, "rerun the planner after adding the collected sources", "补充资料后重新生成学习路线"),
        ],
        focus_areas=concepts,
        critical_path_role="prerequisite",
        trust_score=0.64,
        why_recommended=_localized(
            profile,
            "The current candidate set does not cover the goal well enough, so the next useful step is resource discovery rather than a mastery route.",
            "当前候选资料还不足以覆盖目标，下一步应该先补资料，而不是直接进入掌握路线。",
        ),
        license_or_access_note=_localized(
            profile,
            "Generated checklist; add legal open resources or explicit local files.",
            "自动生成的资料发现清单；请补充合法开放资源或显式本地文件。",
        ),
        metadata={"generated_resource_discovery": True},
    )


def _resource_discovery_tasks(profile: LearnerProfile, route_audit: dict[str, Any]) -> list[dict[str, Any]]:
    missing_terms = route_audit.get("coverage_gate", {}).get("missing_terms") or route_audit.get("needed_terms", [])[:6]
    missing = ", ".join(str(term) for term in missing_terms[:6]) or profile.goal
    tasks = [
        (
            "discover",
            "Collect target-specific resources",
            "收集目标相关资料",
            f"Find at least one authoritative paper, book chapter, official doc, or maintained repository for: {missing}.",
            f"围绕这些缺口至少找到一项权威论文、书籍章节、官方文档或维护良好的代码仓库：{missing}。",
            "At least three goal-aligned sources are saved as URLs or local files.",
            "至少保存 3 个与目标高度相关的 URL 或本地文件。",
        ),
        (
            "verify",
            "Verify resource relevance",
            "验证资料相关性",
            "Reject sources that do not share the goal concepts or do not support explain, reproduce, or synthesize tasks.",
            "剔除不覆盖目标概念、也不能支撑解释/推导/复现/综合任务的资料。",
            "Each retained source has a reason and expected role in the route.",
            "每个保留资料都有推荐理由和预期路线角色。",
        ),
        (
            "regenerate",
            "Regenerate the roadmap",
            "重新生成学习路线",
            "Run fields-study-flow again with the collected URLs or local resources.",
            "带上新增 URL 或本地资料重新运行 fields-study-flow。",
            "Coverage is above the readiness threshold and the plan has concrete resources.",
            "覆盖率超过可信门槛，并且路线包含具体可学习资料。",
        ),
    ]
    return [
        {
            "id": f"task-{index}-{task_type}",
            "type": task_type,
            "title": _localized(profile, en_title, zh_title),
            "resource_titles": ["fields-study-flow-resource-discovery-checklist"],
            "estimated_minutes": 30,
            "evidence": _localized(profile, en_evidence, zh_evidence),
            "acceptance": _localized(profile, en_acceptance, zh_acceptance),
        }
        for index, (task_type, en_title, zh_title, en_evidence, zh_evidence, en_acceptance, zh_acceptance) in enumerate(tasks, start=1)
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
                "localized": _localized_resource_public(profile, public, route_status, reason, phase_name),
            }
        )
        library.append(public)
    return library


def _localized_resource_public(
    profile: LearnerProfile,
    public: dict[str, Any],
    route_status: str,
    reason: str,
    phase_name: str,
) -> dict[str, str | None]:
    language = profile.output_language
    return {
        "route_status": _route_status_label(language, route_status),
        "route_reason": _localized_reason_label(language, reason),
        "selected_phase": phase_name or None,
        "critical_path_role": _localized_role_label(language, public.get("critical_path_role", "")),
        "type": str(public.get("type", "")),
        "source": str(public.get("source", "")),
    }


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

    tasks = _graph_tasks(profile, target_kind, final_artifact)
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
    if "discover" in lowered or "verify" in lowered or "regenerate" in lowered or "收集" in lowered or "验证" in lowered or "重新生成" in lowered:
        return "discover"
    if "derive" in lowered or "equation" in lowered or "proof" in lowered or "推导" in lowered or "公式" in lowered or "证明" in lowered:
        return "derive"
    if "reproduce" in lowered or "implement" in lowered or "run" in lowered or "复现" in lowered or "实现" in lowered or "运行" in lowered:
        return "reproduce"
    if "critique" in lowered or "trade-off" in lowered or "limitation" in lowered or "批判" in lowered or "局限" in lowered or "边界" in lowered:
        return "critique"
    if "connect" in lowered or "synthesis" in lowered or "综合" in lowered or "连接" in lowered:
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
        "Derive or trace the core mechanism behind one representative method",
        "Implement or run a minimal representative example",
        "Connect key papers, tools, and concepts",
        "Critique trade-offs and choose next steps",
    ]


def _mastery_task_specs(profile: LearnerProfile, target_kind: str) -> list[tuple[str, str]]:
    if target_kind == "paper":
        specs = [
            ("explain", "Explain the problem, contribution, and assumptions", "解释问题、贡献和假设"),
            ("derive", "Derive one key equation or proof step", "推导一个关键公式或证明步骤"),
            ("reproduce", "Reproduce the minimal method or experiment", "复现最小方法或实验"),
            ("critique", "Critique limitations and failure modes", "批判局限与失败模式"),
        ]
    else:
        specs = [
            ("explain", "Explain the field map and prerequisite chain", "解释领域地图与前置链条"),
            (
                "derive",
                "Derive or trace the core mechanism behind one representative method",
                "推导或追踪一个代表性方法的核心机制",
            ),
            ("reproduce", "Implement or run a minimal representative example", "实现或运行一个最小代表例子"),
            ("synthesize", "Connect key papers, tools, and concepts", "连接关键论文、工具和概念"),
            ("critique", "Critique trade-offs and choose next steps", "批判权衡并选择下一步"),
        ]
    return [(task_type, _localized(profile, en, zh)) for task_type, en, zh in specs]


def _known_task_title_zh(label: str) -> str:
    mapping = {
        "Explain the problem, contribution, and assumptions": "解释问题、贡献和假设",
        "Derive one key equation or proof step": "推导一个关键公式或证明步骤",
        "Reproduce the minimal method or experiment": "复现最小方法或实验",
        "Critique limitations and failure modes": "批判局限与失败模式",
        "Explain the field map and prerequisite chain": "解释领域地图与前置链条",
        "Derive or trace the core mechanism behind one representative method": "推导或追踪一个代表性方法的核心机制",
        "Implement or run a minimal representative example": "实现或运行一个最小代表例子",
        "Connect key papers, tools, and concepts": "连接关键论文、工具和概念",
        "Critique trade-offs and choose next steps": "批判权衡并选择下一步",
        "Discover target-specific resources": "发现目标相关资料",
        "Verify resource relevance": "验证资料相关性",
        "Regenerate the roadmap": "重新生成学习路线",
    }
    return mapping.get(label, label)


def _graph_tasks(profile: LearnerProfile, target_kind: str, final_artifact: dict[str, str]) -> list[str]:
    if final_artifact.get("type") == "resource-discovery-plan":
        tasks = [
            ("Discover target-specific resources", "发现目标相关资料"),
            ("Verify resource relevance", "验证资料相关性"),
            ("Regenerate the roadmap", "重新生成学习路线"),
        ]
        return [_localized(profile, en, zh) for en, zh in tasks]
    return [title for _task_type, title in _mastery_task_specs(profile, target_kind)]


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
