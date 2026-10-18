from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fields_study_flow.models import LearnerProfile, Resource


OUTPUT_FILES = [
    "learner_profile.json",
    "resource_index.json",
    "source_registry_snapshot.json",
    "roadmap.md",
    "roadmap.json",
]


def build_roadmap(profile: LearnerProfile, resources: list[Resource]) -> dict[str, Any]:
    from fields_study_flow.prerequisites import order_resources, prerequisite_nodes, schedule
    nodes = prerequisite_nodes(profile, resources)
    ordered = order_resources(profile, nodes, resources)
    phases = _build_phases(profile, ordered)
    return {
        'prerequisites': nodes,
        'schedule': schedule(profile, nodes, ordered),
        "title": _title(profile),
        "profile": profile.to_dict(),
        "outputs": OUTPUT_FILES.copy(),
        "phases": phases,
        "checkpoints": _checkpoints(profile),
        "safety_policy": [
            "Use official APIs, open resources, or user-provided URLs.",
            "Do not bypass login, scrape restricted pages, or download videos.",
            "Summarize and link copyrighted material instead of copying long excerpts.",
        ],
    }


def write_outputs(
    output_dir: Path,
    profile: LearnerProfile,
    ranked_resources: list[Resource],
    roadmap: dict[str, Any],
    source_registry_snapshot: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "learner_profile.json").write_text(
        json.dumps(profile.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "resource_index.json").write_text(
        json.dumps([resource.to_dict() for resource in ranked_resources], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "source_registry_snapshot.json").write_text(
        json.dumps(source_registry_snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "roadmap.json").write_text(
        json.dumps(roadmap, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "roadmap.md").write_text(render_markdown(roadmap), encoding="utf-8")


def render_markdown(roadmap: dict[str, Any]) -> str:
    lines = [f"# {roadmap['title']}", ""]
    profile = roadmap["profile"]
    lines.extend(
        [
            f"- Goal: {profile['goal']}",
            f"- Output language: {profile['output_language']}",
            f"- Resource language preference: {profile['resource_language_preference']}",
            "",
            "## Phases",
            "",
        ]
    )
    for phase in roadmap["phases"]:
        lines.extend([f"### {phase['name']}", phase["objective"], ""])
        if not phase["resources"]:
            lines.append("- No resources selected yet; add sources with `fields-study-flow ingest-url`.")
        for resource in phase["resources"]:
            lines.extend(
                [
                    f"- [{resource['title']}]({resource['url']})",
                    f"  - Source: {resource['source']} / {resource['type']} / {resource['language']}",
                    f"  - Difficulty: {resource['difficulty']} | Time: {resource['estimated_time']} | Trust: {resource['trust_score']}",
                    f"  - Concepts: {', '.join(resource['concepts']) or 'not tagged'}",
                    f"  - Why: {resource['why_recommended']}",
                    f"  - Access: {resource['license_or_access_note']}",
                    f"  - Translation: {resource['translation_note']}",
                ]
            )
        lines.append("")
    lines.extend(['## Prerequisites', ''])
    for node in roadmap.get('prerequisites', []):
        lines.append(f"- {node['id']}: {node['status']} ({node['reason']}); {node['estimated_hours']}h")
    lines.extend(['', '## Schedule', ''])
    schedule = roadmap.get('schedule', {})
    lines.append(f"- Estimated weeks: {schedule.get('total_weeks', 'unknown')}; target date: {schedule.get('target_date') or 'not set'}")
    lines.append(f"- Deadline feasible: {schedule.get('deadline_feasible')}; unknown durations: {len(schedule.get('unknown_estimates', []))}")
    for item in schedule.get('items', []):
        lines.append(f"- {item['id']}: {item['hours'] if item['hours'] is not None else 'unknown'}h; weeks {item['start_week']}–{item['end_week']}")
    lines.extend(['', "## Checkpoints", ""])
    for checkpoint in roadmap["checkpoints"]:
        lines.append(f"- {checkpoint}")
    lines.extend(["", "## Safety Policy", ""])
    for policy in roadmap["safety_policy"]:
        lines.append(f"- {policy}")
    lines.append("")
    return "\n".join(lines)


def _build_phases(profile: LearnerProfile, resources: list[Resource]) -> list[dict[str, Any]]:
    if not resources:
        return [
            {
                "name": _phase_name(profile, "Phase 1", "阶段 1", "Foundation"),
                "objective": _objective(profile, "Establish prerequisites before collecting resources.", "先补齐关键前置知识。"),
                "resources": [],
            }
        ]
    buckets = [
        ("Foundation", "基础", "Build prerequisites and vocabulary.", "补齐前置知识和术语。"),
        ("Core Understanding", "核心理解", "Study the target concepts with primary resources.", "学习目标概念和核心材料。"),
        ("Practice and Reproduction", "实践复现", "Turn understanding into code, notes, or proof steps.", "把理解转成代码、笔记或推导步骤。"),
    ]
    phases: list[dict[str, Any]] = []
    target_index = next((i for i, resource in enumerate(resources) if resource.metadata.get('target_paper')), None)
    if target_index is None:
        chunk_size = max(1, (len(resources) + len(buckets) - 1) // len(buckets))
        chunks = [resources[i * chunk_size:(i + 1) * chunk_size] for i in range(len(buckets))]
    else:
        # Change phase boundaries, never the dependency order. A target paper
        # follows every foundation resource and precedes its dependent practice.
        core_end = max(i for i, resource in enumerate(resources) if resource.metadata.get('target_paper')) + 1
        chunks = [resources[:target_index], resources[target_index:core_end], resources[core_end:]]
    for index, (en_name, zh_name, en_obj, zh_obj) in enumerate(buckets):
        chunk = chunks[index]
        if not chunk and index > 0:
            continue
        phases.append(
            {
                "name": _phase_name(profile, f"Phase {index + 1}", f"阶段 {index + 1}", en_name, zh_name),
                "objective": _objective(profile, en_obj, zh_obj),
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
            "Explain the core idea without notes.",
            "Reproduce one derivation, proof step, or minimal implementation.",
            "Write a one-page summary with remaining questions.",
        ]
    if profile.output_language == "bilingual":
        return [
            "Explain the core idea without notes. / 不看笔记讲清核心思想。",
            "Reproduce one derivation, proof step, or minimal implementation. / 复现一个推导、证明步骤或最小实现。",
            "Write a bilingual one-page summary with remaining questions. / 写一页双语总结和未解决问题。",
        ]
    return [
        "不看笔记讲清核心思想。",
        "复现一个推导、证明步骤或最小实现。",
        "写一页总结，列出仍然卡住的问题。",
    ]
