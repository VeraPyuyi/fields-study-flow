"""Evidence-first learning steps for understanding, presenting or extending.

This module plans questions and checks; it never executes experiments or marks
understanding as mastered. Null cost means unknown, not free.
"""
from __future__ import annotations

import copy
import heapq
import math
from typing import Any

from fields_study_flow.project_evidence import _id, _items, _mapping, _public_text


_ZH = {
    "Understand the question, method and boundary": "理解研究问题、方法与边界",
    "What question is addressed, how does the method work, and where does its evidence stop?": "研究要回答什么问题，方法如何工作，证据的适用边界在哪里？",
    "Locate the question and mechanism in supplied materials": "在已有材料中定位研究问题和方法机制",
    "Separate a stated boundary from a demonstrated result": "区分作者声明的边界与已有结果实际支持的范围",
    "Review a sourced claim": "核对有出处的论点",
    "What does this claim say, and which source location supports reading it?": "这个论点表达了什么，应回到哪个原文位置核对？",
    "Read each referenced anchor": "阅读每个引用位置",
    "Distinguish source location from scientific validation": "区分材料定位与科学正确性验证",
    "Prepare a sourced research brief": "准备带出处的研究汇报",
    "Can you explain the question, method, result and limits with source citations?": "能否引用具体出处说明研究问题、方法、结果与局限？",
    "Attach anchors to each factual point": "为每个事实陈述绑定出处",
    "State missing evidence explicitly": "明确说明缺失的证据",
    "Prepare evidence-bounded questions": "准备有证据边界的问答",
    "Which questions can the supplied evidence answer, and which remain open?": "已有证据可以回答哪些问题，哪些问题仍未解决？",
    "Give a source for each answer": "为每个回答给出出处",
    "Keep unsupported answers as open questions": "将缺少依据的回答保留为待研究问题",
    "Inspect the implementation entry point": "核对实现入口",
    "Which supplied symbol or cell could implement the method, and is that association reviewed?": "哪个已有符号或单元格可能对应方法，这个关联是否经过核对？",
    "Inspect changeable configuration": "核对可修改的配置",
    "Which configuration keys control the proposed change?": "哪些配置键控制拟议的改动？",
    "Inspect existing experiment results": "核对已有实验结果",
    "What existing observations and conditions could serve as a comparison?": "哪些已有观察和实验条件可以作为对照？",
    "Identify the actual material and its locator": "确认真实材料及其定位",
    "Do not infer reproduction from names or keywords": "不以名称或关键词推断已复现",
    "Form a next-change hypothesis": "形成下一步改动假设",
    "What one change would you propose, why, and what observable outcome would challenge the hypothesis?": "拟进行哪一项改动，依据是什么，什么可观察结果能够反驳假设？",
    "Bind an implementation entry, configuration key and comparison result when supplied": "在材料具备时绑定实现入口、配置键与对照结果",
    "Record assumptions and missing materials before running anything": "运行前记录假设与缺失材料",
    "What can the supplied evidence establish, and what is still missing?": "已有证据能支持什么，还有哪些材料缺失？",
    "Read the cited materials": "阅读引用材料",
    "Record uncertainty without claiming mastery": "记录不确定性，不自动认定已掌握",
    "Review supplied evidence": "核对已有证据",
    "Answer a concrete research question using the available source locations; missing material remains explicit.": "依据已有出处回答具体研究问题，并明确保留材料缺失状态。",
}

_TASK_TYPES = {
    "orientation": {"explain"}, "sourced_brief": {"synthesize", "present"},
    "questions": {"critique"}, "implementation": {"reproduce"},
    "configuration": {"configure"}, "results": {"evaluate"},
    "change_hypothesis": {"extend"},
}


_CLAIM_STEP_TITLES = {
    "background": ("核对必要背景", "Review necessary background"),
    "experiment": ("理解实验如何验证方法", "Understand how experiments evaluate the method"),
    "result": ("核对已有结果及其条件", "Review reported results and conditions"),
    "contribution": ("厘清实际贡献", "Identify the actual contribution"),
}


def _minutes(value: Any) -> int | float | None:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0 else None


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _task_bindings(template: dict, tasks: dict[str, dict], step_id: str, claim_ids: list[str], anchor_ids: list[str], activity: str) -> list[str]:
    bound = [tid for tid in _items(template.get("task_ids")) if isinstance(tid, str) and tid in tasks]
    claims, anchors = set(claim_ids), set(anchor_ids)
    matching_types = _TASK_TYPES.get(activity, set())
    for tid, task in tasks.items():
        associations = {key: task.get(key) for key in ("claim_ids", "anchor_ids", "learning_step_ids")}
        explicit_match = (
            bool(claims.intersection(c for c in _items(associations["claim_ids"]) if isinstance(c, str)))
            or bool(anchors.intersection(a for a in _items(associations["anchor_ids"]) if isinstance(a, str)))
            or step_id in _items(associations["learning_step_ids"])
        )
        # A malformed/nonmatching explicit citation must not become a type match.
        has_association = any(associations.values())
        fallback_match = not has_association and (
            bool(activity) and task.get("activity") == activity
            or isinstance(task.get("type"), str) and task["type"] in matching_types
        )
        if explicit_match or fallback_match:
            bound.append(tid)
    return _unique(bound)


def build_learning_path(context: dict, profile: dict, study_tasks: list[dict]) -> list[dict]:
    """Return new normalized steps with a stable topological prerequisite order.

    Existing context.learning_steps is an explicit prerequisite template graph;
    otherwise generate an outcome-specific path. Optional template fields:
    topic, mandatory, activity, answer_questions, check_points. Unknown/missing
    dependencies and cycles are exposed as diagnostic fields, never hidden.
    Task requirements remain untouched; bindings use IDs, not resource titles.
    """
    context, profile = _mapping(context), _mapping(profile)
    language = str(profile.get("output_language") or "en").lower()

    def controlled(value: str) -> str:
        if language in {"bilingual", "zh-en", "en-zh", "zh-cn+en"}:
            return f"{_ZH[value]} / {value}" if value in _ZH else value
        if language.startswith("zh"):
            return _ZH.get(value, value)
        return value
    claims = {c["id"]: c for c in _items(context.get("claims")) if isinstance(c, dict) and isinstance(c.get("id"), str)}
    anchors = {a["id"]: a for a in _items(context.get("anchors")) if isinstance(a, dict) and isinstance(a.get("id"), str)}
    sources = {s["id"]: s for s in _items(context.get("sources")) if isinstance(s, dict) and isinstance(s.get("id"), str)}
    tasks = {t["id"]: t for t in _items(study_tasks) if isinstance(t, dict) and isinstance(t.get("id"), str)}
    known = {str(t).casefold().strip() for t in _items(profile.get("known_topics"))}
    for topic, level in _mapping(profile.get("levels")).items():
        if str(level).casefold() in {"familiar", "advanced", "expert", "proficient", "mastered", "known", "熟悉", "熟练", "精通"} or (isinstance(level, (int, float)) and not isinstance(level, bool) and level >= 3):
            known.add(str(topic).casefold().strip())

    def skip_claim(claim: dict) -> bool:
        if claim.get("kind") != "background" or claim.get("mandatory", True):
            return False
        return str(claim.get("topic") or claim.get("statement") or "").casefold().strip() in known

    selected = {cid: c for cid, c in claims.items() if not skip_claim(c)}
    outcome = str(profile.get("learning_outcome") or "understand").lower()
    if outcome not in {"understand", "present", "extend"}:
        outcome = "understand"
    templates = [copy.deepcopy(s) for s in _items(context.get("learning_steps")) if isinstance(s, dict)]
    if not templates:
        primary = [cid for kind in ("problem", "motivation", "methodology", "limitation") for cid, c in selected.items() if c.get("kind") == kind]

        def step(activity: str, title: str, ids: list[str], question: str, checks: list[str], **extra) -> dict:
            return {"id": _id("step", [context.get("bundle_id"), outcome, activity, ids]), "activity": activity,
                    "title": controlled(title), "claim_ids": ids, "prerequisite_ids": [],
                    "answer_questions": [controlled(question)], "check_points": [controlled(c) for c in checks], **extra}

        missing_core = [kind for kind in ("problem", "methodology", "limitation") if not any(c.get("kind") == kind for c in selected.values())]
        templates.append(step("orientation", "Understand the question, method and boundary", primary,
                              "What question is addressed, how does the method work, and where does its evidence stop?",
                              ["Locate the question and mechanism in supplied materials", "Separate a stated boundary from a demonstrated result"], missing_claim_kinds=missing_core))
        groups: dict[str, list[str]] = {}
        for cid, claim in selected.items():
            if cid not in primary:
                groups.setdefault(str(claim.get("kind") or "claim"), []).append(cid)
        for kind, ids in groups.items():
            zh_title, en_title = _CLAIM_STEP_TITLES.get(kind, ("核对已有论点", "Review sourced claims"))
            title = f"{zh_title} / {en_title}" if language == "bilingual" else zh_title if language.startswith("zh") else en_title
            templates.append(step("background" if kind == "background" else "claim", title, ids,
                                  "What does this claim say, and which source location supports reading it?",
                                  ["Read each referenced anchor", "Distinguish source location from scientific validation"]))
        if outcome == "present":
            ids = list(selected)
            templates.append(step("sourced_brief", "Prepare a sourced research brief", ids,
                                  "Can you explain the question, method, result and limits with source citations?",
                                  ["Attach anchors to each factual point", "State missing evidence explicitly"]))
            templates.append(step("questions", "Prepare evidence-bounded questions", ids,
                                  "Which questions can the supplied evidence answer, and which remain open?",
                                  ["Give a source for each answer", "Keep unsupported answers as open questions"]))
        if outcome == "extend":
            for activity, kind, title, question in (
                ("implementation", "code", "Inspect the implementation entry point", "Which supplied symbol or cell could implement the method, and is that association reviewed?"),
                ("configuration", "config", "Inspect changeable configuration", "Which configuration keys control the proposed change?"),
                ("results", "result", "Inspect existing experiment results", "What existing observations and conditions could serve as a comparison?"),
            ):
                kinds = {kind, "notebook"} if kind == "code" else {kind}
                aids = [aid for aid, a in anchors.items() if sources.get(a.get("source_id"), {}).get("kind") in kinds and sources.get(a.get("source_id"), {}).get("availability") != "missing"]
                templates.append(step(activity, title, [], question, ["Identify the actual material and its locator", "Do not infer reproduction from names or keywords"], anchor_ids=aids, required_material_kind=kind))
            templates.append(step("change_hypothesis", "Form a next-change hypothesis", primary,
                                  "What one change would you propose, why, and what observable outcome would challenge the hypothesis?",
                                  ["Bind an implementation entry, configuration key and comparison result when supplied", "Record assumptions and missing materials before running anything"], required_material_kinds=["code", "config", "result"]))
        # Make generated ordering an explicit graph, not just list position.
        previous = None
        for template in templates:
            if previous:
                template["prerequisite_ids"] = [previous]
            previous = template["id"]

    steps = []
    skipped = set()
    for index, template in enumerate(templates):
        cid_values = [c for c in _items(template.get("claim_ids")) if isinstance(c, str)]
        cid_values = _unique(cid_values)
        if cid_values and all(c in claims and skip_claim(claims[c]) for c in cid_values) and not template.get("mandatory"):
            if isinstance(template.get("id"), str):
                skipped.add(template["id"])
            continue
        sid = template.get("id")
        sid = sid if isinstance(sid, str) and sid else _id("step", [index, template.get("title"), cid_values])
        if sid in {s["id"] for s in steps}:
            continue
        cids = [c for c in cid_values if c in selected]
        aids = _unique([a for a in _items(template.get("anchor_ids")) if isinstance(a, str) and a in anchors] + [a for cid in cids for a in _items(claims[cid].get("anchor_ids")) if isinstance(a, str) and a in anchors])
        activity = template.get("activity") if isinstance(template.get("activity"), str) else ""
        task_ids = _task_bindings(template, tasks, sid, cids, aids, activity)
        estimate = _minutes(template.get("estimated_minutes"))
        if estimate is None and task_ids:
            values = [_minutes(tasks[tid].get("estimated_minutes")) for tid in task_ids]
            if all(v is not None for v in values):
                estimate = sum(values)
        questions = [_public_text(q, 500) for q in _items(template.get("answer_questions")) if isinstance(q, str) and q]
        checks = [_public_text(q, 500) for q in _items(template.get("check_points")) if isinstance(q, str) and q]
        questions = questions or [_public_text(template.get("question"), 500) or controlled("What can the supplied evidence establish, and what is still missing?")]
        checks = checks or [controlled("Read the cited materials"), controlled("Record uncertainty without claiming mastery")]
        missing_claims = [c for c in cid_values if c not in claims]
        available = bool(aids) and all(anchors[a].get("locator_status") == "valid" for a in aids) and all(claims[c].get("evidence_status") == "located" for c in cids)
        if template.get("missing_claim_kinds") or missing_claims:
            available = False
        if template.get("required_material_kinds"):
            available = available and all(any(s.get("kind") in ({kind, "notebook"} if kind == "code" else {kind}) and s.get("availability") != "missing" and any(a.get("source_id") == s["id"] and a.get("locator_status") == "valid" for a in anchors.values()) for s in sources.values()) for kind in template["required_material_kinds"])
        step = {"id": sid, "title": _public_text(template.get("title"), 160) or controlled("Review supplied evidence"), "claim_ids": cids,
                "prerequisite_ids": _unique([p for p in _items(template.get("prerequisite_ids")) if isinstance(p, str)]),
                "anchor_ids": aids, "task_ids": task_ids, "estimated_minutes": estimate,
                "reason": _public_text(template.get("reason"), 500) or controlled("Answer a concrete research question using the available source locations; missing material remains explicit."),
                "status": "available" if available else "needs_material", "answer_questions": questions, "check_points": checks,
                "question": questions[0], "checkpoints": checks}
        for key in ("activity", "required_material_kind", "required_material_kinds", "missing_claim_kinds"):
            if key in template:
                step[key] = copy.deepcopy(template[key])
        if missing_claims:
            step["missing_claim_ids"] = missing_claims
        steps.append(step)
    ids = {s["id"] for s in steps}
    for step in steps:
        missing = [p for p in step["prerequisite_ids"] if p not in ids and p not in skipped]
        step["prerequisite_ids"] = [p for p in step["prerequisite_ids"] if p in ids]
        if missing:
            step["missing_prerequisite_ids"] = missing
            step["status"] = "needs_material"
    order = {step["id"]: i for i, step in enumerate(steps)}
    by_id = {step["id"]: step for step in steps}
    incoming = {step["id"]: len(step["prerequisite_ids"]) for step in steps}
    children = {sid: [] for sid in ids}
    for step in steps:
        for parent in step["prerequisite_ids"]:
            children[parent].append(step["id"])
    ready = [(order[sid], sid) for sid, count in incoming.items() if count == 0]
    heapq.heapify(ready)
    result = []
    while ready:
        _, sid = heapq.heappop(ready)
        result.append(by_id[sid])
        for child in children[sid]:
            incoming[child] -= 1
            if incoming[child] == 0:
                heapq.heappush(ready, (order[child], child))
    remaining = [s for s in steps if incoming[s["id"]] > 0]
    # Iterative reachability detects cycle membership without recursion limits.
    for step in remaining:
        start = step["id"]
        pending = list(children[start])
        visited = set()
        cyclic = False
        while pending:
            sid = pending.pop()
            if sid == start:
                cyclic = True
                break
            if sid not in visited:
                visited.add(sid)
                pending.extend(children[sid])
        step["prerequisite_cycle"] = cyclic
        step["prerequisite_review_required"] = True
        if not cyclic:
            step["blocked_by_cycle"] = True
    return result + remaining
