from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fields_study_flow.models import LearnerProfile, Resource


TEMPLATE_RESOURCE_TITLE = "fields-study-flow-template"
TEMPLATE_ARTIFACT_PATHS = [
    "artifact_template/README.md",
    "artifact_template/task_checklist.md",
    "artifact_template/reproduction_log.md",
    "artifact_template/notebook_skeleton.ipynb",
    "artifact_template/src/main.py",
]

RUNNABLE_RESOURCE_TYPES = {"repository", "code", "notebook", "practice"}
RUNNABLE_ARTIFACT_TYPES = {"project", "project+survey", "course-portfolio", "paper-mastery"}


def enforce_artifact_requirements(
    profile: LearnerProfile,
    target_kind: str,
    final_artifact: dict[str, str],
    selected_resources: list[Resource],
    candidate_resources: list[Resource],
) -> tuple[list[Resource], dict[str, Any], list[dict[str, str]], list[str]]:
    requires_runnable = _requires_runnable(profile, target_kind, final_artifact)
    if not requires_runnable:
        return (
            selected_resources,
            {
                "type": final_artifact.get("type", "unknown"),
                "requires_runnable": False,
                "policy": "not-required",
                "satisfied_by": [],
            },
            [],
            [],
        )

    selected_runnable = [resource for resource in selected_resources if is_runnable_resource(resource) and _is_relevant_runnable(profile, resource, candidate_resources)]
    if len(selected_runnable) != len([resource for resource in selected_resources if is_runnable_resource(resource)]):
        selected_resources = [
            resource
            for resource in selected_resources
            if not is_runnable_resource(resource) or _is_relevant_runnable(profile, resource, candidate_resources)
        ]
    if selected_runnable:
        return (
            selected_resources,
            _requirements(final_artifact, "existing-runnable-resource", selected_runnable),
            [],
            [],
        )

    selected_ids = {id(resource) for resource in selected_resources}
    runnable_candidates = [
        resource
        for resource in candidate_resources
        if id(resource) not in selected_ids and is_runnable_resource(resource) and _is_relevant_runnable(profile, resource, candidate_resources)
    ]
    if runnable_candidates:
        chosen = max(runnable_candidates, key=_runnable_value)
        return (
            [*selected_resources, chosen],
            _requirements(final_artifact, "existing-runnable-resource", [chosen]),
            [],
            [],
        )

    template = generated_template_resource(profile, target_kind, final_artifact, candidate_resources)
    gap = {
        "kind": "runnable-resource",
        "status": "template-required",
        "message": "No target-aligned runnable repository, notebook, or code file was selected. A local template was generated, but the learner still needs to fill in the minimal implementation and evidence log.",
        "resolved_by": TEMPLATE_RESOURCE_TITLE,
    }
    return (
        [*selected_resources, template],
        _requirements(final_artifact, "auto-generated-template", [template]),
        [gap],
        TEMPLATE_ARTIFACT_PATHS.copy(),
    )


def is_runnable_resource(resource: Resource) -> bool:
    return resource.critical_path_role == "practice-validation" or resource.type in RUNNABLE_RESOURCE_TYPES


def generated_template_resource(
    profile: LearnerProfile,
    target_kind: str,
    final_artifact: dict[str, str],
    resources: list[Resource],
) -> Resource:
    concepts = _template_concepts(profile, resources)
    return Resource(
        title=TEMPLATE_RESOURCE_TITLE,
        url="local://fields-study-flow-template",
        source="fields-study-flow",
        type="notebook",
        language="en",
        difficulty="intermediate",
        concepts=concepts,
        estimated_time="2h",
        estimated_minutes=120,
        learning_key_points=[
            "define the minimal runnable target",
            "connect code steps to concepts or paper sections",
            "record evidence for explain, derive, reproduce, and critique",
        ],
        focus_areas=[final_artifact.get("type", "artifact"), target_kind, *concepts[:3]],
        critical_path_role="practice-validation",
        trust_score=0.68,
        why_recommended="No runnable resource was selected, so fields-study-flow generated a minimal artifact template for verifiable learning.",
        license_or_access_note="Generated local study template. Fill it with your own notes, code, and experiment results.",
        metadata={
            "generated_template": True,
            "template_paths": TEMPLATE_ARTIFACT_PATHS.copy(),
            "final_artifact_type": final_artifact.get("type", "unknown"),
        },
    )


def write_artifact_template(output_dir: Path, roadmap: dict[str, Any]) -> None:
    generated = set(roadmap.get("generated_artifacts", []))
    template_dir = output_dir / "artifact_template"
    if not generated:
        if template_dir.exists():
            shutil.rmtree(template_dir)
        return
    src_dir = template_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    (template_dir / "README.md").write_text(_readme(roadmap), encoding="utf-8")
    (template_dir / "task_checklist.md").write_text(_task_checklist(roadmap), encoding="utf-8")
    (template_dir / "reproduction_log.md").write_text(_reproduction_log(roadmap), encoding="utf-8")
    (template_dir / "notebook_skeleton.ipynb").write_text(json.dumps(_notebook(roadmap), ensure_ascii=False, indent=2), encoding="utf-8")
    (src_dir / "main.py").write_text(_main_py(), encoding="utf-8")


def _requires_runnable(profile: LearnerProfile, target_kind: str, final_artifact: dict[str, str]) -> bool:
    artifact_type = final_artifact.get("type", "")
    if artifact_type in RUNNABLE_ARTIFACT_TYPES:
        return True
    goal = profile.goal.lower()
    if target_kind == "paper" and any(term in goal for term in ("reproduce", "implement", "code", "复现", "实现")):
        return True
    return any(term in goal for term in ("build", "implement", "reproduce", "project", "code", "复现", "实现", "项目"))


def _requirements(final_artifact: dict[str, str], policy: str, resources: list[Resource]) -> dict[str, Any]:
    return {
        "type": final_artifact.get("type", "unknown"),
        "requires_runnable": True,
        "policy": policy,
        "satisfied_by": [resource.title for resource in resources],
        "evidence": final_artifact.get("evidence", ""),
    }


def _runnable_value(resource: Resource) -> float:
    minutes = resource.estimated_minutes or 180
    score = resource.score or resource.trust_score
    generated_penalty = -0.2 if resource.metadata.get("generated_template") else 0.0
    return score + generated_penalty - min(minutes, 720) / 1000


def _is_relevant_runnable(profile: LearnerProfile, resource: Resource, candidate_resources: list[Resource]) -> bool:
    if resource.metadata.get("generated_template"):
        return True
    if resource.source == "local-library" and resource.metadata.get("candidate_decision") == "critical-path-candidate":
        return True
    target_terms = _tokens(profile.goal)
    for candidate in candidate_resources:
        if candidate.metadata.get("target_paper"):
            target_terms.update(_tokens(" ".join(candidate.concepts)))
            paper_metadata = candidate.metadata.get("paper_metadata", {})
            if isinstance(paper_metadata, dict):
                target_terms.update(_tokens(str(paper_metadata.get("title", ""))))
                target_terms.update(_tokens(" ".join(str(item) for item in paper_metadata.get("concepts", []))))
    resource_terms = _tokens(
        " ".join(
            [
                resource.title,
                resource.type,
                *resource.concepts,
                *resource.learning_key_points,
                *resource.focus_areas,
            ]
        )
    )
    return bool(target_terms & resource_terms)


def _tokens(value: str) -> set[str]:
    stopwords = {
        "a",
        "an",
        "and",
        "arxiv",
        "build",
        "code",
        "derive",
        "doi",
        "fully",
        "implement",
        "paper",
        "project",
        "reading",
        "reproduce",
        "understand",
        "the",
    }
    normalized = value.lower().replace("/", " ").replace("-", " ")
    tokens = {token.strip(".,:;()[]{}") for token in normalized.split() if token.strip()}
    return {token for token in tokens if len(token) >= 4 and token not in stopwords}


def _template_concepts(profile: LearnerProfile, resources: list[Resource]) -> list[str]:
    concepts: list[str] = []
    for resource in resources:
        concepts.extend(resource.concepts[:4])
    if not concepts:
        concepts.extend(term for term in profile.goal.lower().replace("/", " ").replace("-", " ").split() if len(term) >= 4)
    return list(dict.fromkeys(concepts))[:8] or ["reproducibility"]


def _target_paper_metadata(roadmap: dict[str, Any]) -> dict[str, Any]:
    for phase in roadmap.get("phases", []):
        for resource in phase.get("resources", []):
            metadata = resource.get("metadata", {})
            paper_metadata = metadata.get("paper_metadata")
            if metadata.get("target_paper") and isinstance(paper_metadata, dict):
                return paper_metadata
    return {}


def _paper_target_lines(paper_metadata: dict[str, Any]) -> list[str]:
    if not paper_metadata:
        return []
    lines = ["Paper-derived targets:"]
    for label, value in [
        ("Method", _first(paper_metadata.get("method_hints"))),
        ("Formula", _first(paper_metadata.get("formula_candidates"))),
        ("Experiment", _first(paper_metadata.get("experiment_hints"))),
        ("Limitation", _first(paper_metadata.get("limitations_hints"))),
        ("Code", _first(paper_metadata.get("code_links"))),
    ]:
        if value:
            lines.append(f"- {label}: {value}")
    lines.append("")
    return lines if len(lines) > 2 else []


def _paper_target_lines_localized(roadmap: dict[str, Any], paper_metadata: dict[str, Any]) -> list[str]:
    if not paper_metadata:
        return []
    lines = [_template_text(roadmap, "Paper-derived targets:", "论文解析得到的验收目标：")]
    for label_en, label_zh, value in [
        ("Method", "方法", _first(paper_metadata.get("method_hints"))),
        ("Formula", "公式", _first(paper_metadata.get("formula_candidates"))),
        ("Experiment", "实验", _first(paper_metadata.get("experiment_hints"))),
        ("Limitation", "局限", _first(paper_metadata.get("limitations_hints"))),
        ("Code", "代码", _first(paper_metadata.get("code_links"))),
    ]:
        if value:
            lines.append(f"- {_template_text(roadmap, label_en, label_zh)}: {value}")
    lines.append("")
    return lines if len(lines) > 2 else []


def _paper_checklist_lines(paper_metadata: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    formula = _first(paper_metadata.get("formula_candidates"))
    code_link = _first(paper_metadata.get("code_links"))
    method = _first(paper_metadata.get("method_hints"))
    experiment = _first(paper_metadata.get("experiment_hints"))
    limitation = _first(paper_metadata.get("limitations_hints"))
    if formula:
        lines.append(f"- [ ] Derive or trace this formula candidate: `{formula}`")
    if code_link:
        lines.append(f"- [ ] Inspect runnable reference or implementation link: {code_link}")
    if method:
        lines.append(f"- [ ] Map implementation steps to method hint: {method}")
    if experiment:
        lines.append(f"- [ ] Define one minimal experiment from hint: {experiment}")
    if limitation:
        lines.append(f"- [ ] Record at least one failure mode or limitation: {limitation}")
    if lines:
        lines.append("")
    return lines


def _paper_checklist_lines_localized(roadmap: dict[str, Any], paper_metadata: dict[str, Any]) -> list[str]:
    lines: list[str] = []
    formula = _first(paper_metadata.get("formula_candidates"))
    code_link = _first(paper_metadata.get("code_links"))
    method = _first(paper_metadata.get("method_hints"))
    experiment = _first(paper_metadata.get("experiment_hints"))
    limitation = _first(paper_metadata.get("limitations_hints"))
    if formula:
        lines.append(f"- [ ] {_template_text(roadmap, 'Derive or trace this formula candidate', '推导或追踪这个公式候选')}: `{formula}`")
    if code_link:
        lines.append(f"- [ ] {_template_text(roadmap, 'Inspect runnable reference or implementation link', '检查可运行参考或实现链接')}: {code_link}")
    if method:
        lines.append(f"- [ ] {_template_text(roadmap, 'Map implementation steps to method hint', '将实现步骤对应到方法提示')}: {method}")
    if experiment:
        lines.append(f"- [ ] {_template_text(roadmap, 'Define one minimal experiment from hint', '根据提示定义一个最小实验')}: {experiment}")
    if limitation:
        lines.append(f"- [ ] {_template_text(roadmap, 'Record at least one failure mode or limitation', '记录至少一个失败模式或局限')}: {limitation}")
    if lines:
        lines.append("")
    return lines


def _paper_log_rows(paper_metadata: dict[str, Any]) -> list[str]:
    rows: list[str] = []
    formula = _first(paper_metadata.get("formula_candidates"))
    code_link = _first(paper_metadata.get("code_links"))
    experiment = _first(paper_metadata.get("experiment_hints"))
    limitation = _first(paper_metadata.get("limitations_hints"))
    if formula:
        rows.append(f"| formula | derive or trace `{formula}` | matching dimensions, variables, and intuition |  |  |")
    if code_link:
        rows.append(f"| code | inspect {code_link} | runnable reference or implementation delta noted |  |  |")
    if experiment:
        rows.append(f"| experiment | {experiment} | metric, dataset, or toy proxy recorded |  |  |")
    if limitation:
        rows.append(f"| limitation | {limitation} | concrete boundary or failure mode written |  |  |")
    return rows


def _paper_log_rows_localized(roadmap: dict[str, Any], paper_metadata: dict[str, Any]) -> list[str]:
    if _template_language(roadmap) == "en":
        return _paper_log_rows(paper_metadata)
    rows: list[str] = []
    formula = _first(paper_metadata.get("formula_candidates"))
    code_link = _first(paper_metadata.get("code_links"))
    experiment = _first(paper_metadata.get("experiment_hints"))
    limitation = _first(paper_metadata.get("limitations_hints"))
    if formula:
        rows.append(f"| 公式 | 推导或追踪 `{formula}` | 变量、维度和直觉能对应上 |  |  |")
    if code_link:
        rows.append(f"| 代码 | 检查 {code_link} | 记录可运行参考或实现差异 |  |  |")
    if experiment:
        rows.append(f"| 实验 | {experiment} | 记录指标、数据集或玩具替代实验 |  |  |")
    if limitation:
        rows.append(f"| 局限 | {limitation} | 写出具体边界或失败模式 |  |  |")
    return rows


def _first(values: Any) -> str:
    if isinstance(values, str):
        return values
    if isinstance(values, list) and values:
        return str(values[0])
    return ""


def _template_language(roadmap: dict[str, Any]) -> str:
    return str(roadmap.get("profile", {}).get("output_language", "en"))


def _template_text(roadmap: dict[str, Any], en: str, zh: str) -> str:
    language = _template_language(roadmap)
    if language == "zh-CN":
        return zh
    if language == "bilingual":
        return f"{en} / {zh}"
    return en


def _readme(roadmap: dict[str, Any]) -> str:
    profile = roadmap.get("profile", {})
    artifact = roadmap.get("final_artifact", {})
    paper_metadata = _target_paper_metadata(roadmap)
    paper_lines = _paper_target_lines_localized(roadmap, paper_metadata)
    return "\n".join(
        [
            f"# fields-study-flow {_template_text(roadmap, 'Artifact Template', '产物模板')}",
            "",
            f"{_template_text(roadmap, 'Goal', '目标')}: {profile.get('goal', 'unknown')}",
            f"{_template_text(roadmap, 'Final artifact', '最终产物')}: {artifact.get('type', 'unknown')}",
            "",
            _template_text(roadmap, "This template is a generated study scaffold, not a completed reproduction.", "这个模板是生成的学习验收骨架，不代表已经完成复现。"),
            _template_text(roadmap, "Fill in the checklist, run the minimal code path, and record evidence in reproduction_log.md.", "请填写验收清单，运行最小代码路径，并在 reproduction_log.md 中记录证据。"),
            "",
            _template_text(roadmap, "Expected evidence:", "预期证据："),
            f"- {_template_text(roadmap, 'Explain the target idea without notes.', '不看笔记讲清目标思想。')}",
            f"- {_template_text(roadmap, 'Derive or trace one key mechanism.', '推导或追踪一个关键机制。')}",
            f"- {_template_text(roadmap, 'Run or implement the smallest meaningful checkpoint.', '运行或实现最小有意义检查点。')}",
            f"- {_template_text(roadmap, 'Critique limitations and failure modes.', '批判局限和失败模式。')}",
            "",
            *paper_lines,
        ]
    )


def _task_checklist(roadmap: dict[str, Any]) -> str:
    checkpoints = roadmap.get("checkpoints", [])
    lines = [f"# {_template_text(roadmap, 'Artifact Checklist', '产物验收清单')}", ""]
    for checkpoint in checkpoints or [_template_text(roadmap, "Run the minimal template and record evidence.", "运行最小模板并记录证据。")]:
        lines.append(f"- [ ] {checkpoint}")
    paper_metadata = _target_paper_metadata(roadmap)
    lines.extend(_paper_checklist_lines_localized(roadmap, paper_metadata))
    lines.extend(
        [
            f"- [ ] {_template_text(roadmap, 'Record commands, results, and blockers in reproduction_log.md', '在 reproduction_log.md 中记录命令、结果和阻塞点')}",
            f"- [ ] {_template_text(roadmap, 'Link each code step back to a concept, section, or paper claim', '把每个代码步骤对应回概念、章节或论文主张')}",
            "",
        ]
    )
    return "\n".join(lines)


def _reproduction_log(roadmap: dict[str, Any]) -> str:
    paper_metadata = _target_paper_metadata(roadmap)
    rows = _paper_log_rows_localized(roadmap, paper_metadata)
    if _template_language(roadmap) == "en":
        header = "| Step | Command or action | Expected evidence | Result | Notes |"
        separator = "| --- | --- | --- | --- | --- |"
        defaults = [
            "| 1 | `python src/main.py` | Template runs and prints next steps |  |  |",
            "| 2 |  | Minimal implementation or experiment output |  |  |",
            "| 3 |  | Limitation or failure-mode note |  |  |",
        ]
    else:
        header = "| 步骤 | 命令或动作 | 预期证据 | 结果 | 备注 |"
        separator = "| --- | --- | --- | --- | --- |"
        defaults = [
            "| 1 | `python src/main.py` | 模板能运行并打印下一步 |  |  |",
            "| 2 |  | 最小实现或实验输出 |  |  |",
            "| 3 |  | 局限或失败模式记录 |  |  |",
        ]
    return "\n".join(
        [
            f"# {_template_text(roadmap, 'Reproduction Log', '复现记录')}",
            "",
            header,
            separator,
            *defaults,
            *rows,
            "",
        ]
    )


def _notebook(roadmap: dict[str, Any]) -> dict[str, Any]:
    goal = roadmap.get("profile", {}).get("goal", "fields-study-flow goal")
    return {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    f"# fields-study-flow {_template_text(roadmap, 'Notebook Skeleton', 'Notebook 骨架')}\n",
                    f"{_template_text(roadmap, 'Goal', '目标')}: {goal}\n",
                    "\n",
                    _template_text(roadmap, "Use this notebook to connect concepts, code, and evidence.\n", "用这个 Notebook 连接概念、代码和验收证据。\n"),
                ],
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": ["from pathlib import Path\n", "print('Artifact template ready')\n"],
            },
        ],
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _main_py() -> str:
    return "\n".join(
        [
            '"""Minimal generated entrypoint for a fields-study-flow artifact."""',
            "",
            "",
            "def main() -> None:",
            "    print('fields-study-flow artifact template ready')",
            "    print('Fill in the minimal runnable experiment for your paper or project.')",
            "",
            "",
            "if __name__ == '__main__':",
            "    main()",
            "",
        ]
    )
