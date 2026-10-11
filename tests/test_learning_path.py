import copy

import pytest

from fields_study_flow.learning_path import build_learning_path


def context():
    kinds = ["background", "problem", "methodology", "limitation", "result"]
    return {"sources": [{"id": "paper", "kind": "paper"}],
            "anchors": [{"id": f"a{i}", "source_id": "paper", "locator": {"section": k}, "locator_status": "valid", "snippet": k} for i, k in enumerate(kinds)],
            "claims": [{"id": k, "kind": k, "statement": k, "anchor_ids": [f"a{i}"], "evidence_status": "located", "topic": "linear algebra", "mandatory": k != "background"} for i, k in enumerate(kinds)],
            "relations": [], "learning_steps": []}


def test_understand_starts_with_question_method_boundary_and_skips_known():
    data = context()
    before = copy.deepcopy(data)
    steps = build_learning_path(data, {}, [])
    assert data == before
    assert steps[0]["claim_ids"] == ["problem", "methodology", "limitation"]
    known = build_learning_path(data, {"known_topics": ["linear algebra"]}, [])
    assert len(known) < len(steps)
    assert all("background" not in s["claim_ids"] for s in known)
    data["claims"][0]["mandatory"] = True
    assert any("background" in s["claim_ids"] for s in build_learning_path(data, {"levels": {"linear algebra": "advanced"}}, []))
    assert before == context()


def test_present_sourced_brief_and_questions_unknown_cost():
    steps = build_learning_path(context(), {"learning_outcome": "present"}, [])
    assert any(s.get("activity") == "sourced_brief" and s["anchor_ids"] for s in steps)
    assert any(s.get("activity") == "questions" for s in steps)
    assert all(s["estimated_minutes"] is None for s in steps)
    assert all(s.get("question") and s.get("checkpoints") for s in steps)


def test_extend_missing_project_not_assumed_reproducible():
    steps = build_learning_path(context(), {"learning_outcome": "extend"}, [])
    for activity in ("implementation", "configuration", "results"):
        assert next(s for s in steps if s.get("activity") == activity)["status"] == "needs_material"
    assert any(s.get("activity") == "change_hypothesis" for s in steps)


def test_extend_uses_actual_source_anchors_not_title_matching():
    data = context()
    for kind in ("code", "config", "result"):
        data["sources"].append({"id": kind, "kind": kind})
        data["anchors"].append({"id": f"{kind}-anchor", "source_id": kind, "locator_status": "valid"})
    steps = build_learning_path(data, {"learning_outcome": "extend"}, [])
    assert next(s for s in steps if s.get("activity") == "implementation")["anchor_ids"] == ["code-anchor"]
    assert next(s for s in steps if s.get("activity") == "results")["status"] == "available"


def test_explicit_prerequisites_topological_order_tasks_and_estimates():
    data = context()
    data["learning_steps"] = [
        {"id": "late", "title": "Late", "claim_ids": ["result"], "prerequisite_ids": ["early"], "task_ids": ["task"]},
        {"id": "early", "title": "Early", "claim_ids": ["methodology"], "prerequisite_ids": []},
    ]
    steps = build_learning_path(data, {}, [{"id": "task", "estimated_minutes": 25, "claim_ids": ["result"]}])
    assert [s["id"] for s in steps] == ["early", "late"]
    assert steps[1]["estimated_minutes"] == 25
    assert steps[0]["estimated_minutes"] is None
    assert steps[1]["anchor_ids"] == ["a4"]


def test_circular_prerequisites_stable_flagged_fallback():
    data = context()
    data["learning_steps"] = [{"id": "b", "title": "B", "prerequisite_ids": ["a"]}, {"id": "a", "title": "A", "prerequisite_ids": ["b"]}]
    steps = build_learning_path(data, {}, [])
    assert [s["id"] for s in steps] == ["b", "a"]
    assert all(s["prerequisite_cycle"] for s in steps)
    assert steps == build_learning_path(data, {}, [])


def test_missing_prerequisite_reported_and_no_zero_estimate():
    data = context()
    data["learning_steps"] = [{"id": "a", "title": "A", "prerequisite_ids": ["unknown"], "estimated_minutes": 0}]
    step = build_learning_path(data, {}, [])[0]
    assert step["status"] == "needs_material"
    assert step["missing_prerequisite_ids"] == ["unknown"]
    assert step["estimated_minutes"] is None


def test_localized_controlled_text_preserves_raw_claim_and_familiar_skip():
    data = context()
    data["claims"][4]["statement"] = "Original external result statement"
    zh = build_learning_path(data, {"output_language": "zh-CN", "levels": {"linear algebra": "familiar"}}, [])
    assert zh[0]["title"] == "理解研究问题、方法与边界"
    assert "研究" in zh[0]["answer_questions"][0]
    assert all("background" not in s["claim_ids"] for s in zh)
    assert next(s for s in zh if s["claim_ids"] == ["result"])["title"] == "核对已有结果及其条件"
    assert any(c["statement"] == "Original external result statement" for c in data["claims"])
    bilingual = build_learning_path(data, {"output_language": "bilingual"}, [])
    assert "理解" in bilingual[0]["title"] and "Understand" in bilingual[0]["title"]
    bilingual = build_learning_path(data, {"output_language": "zh-en"}, [])
    assert "理解" in bilingual[0]["title"] and "Understand" in bilingual[0]["title"]


def test_existing_task_types_bound_without_mutating_requirements():
    tasks = [{"id": "explain", "type": "explain", "estimated_minutes": 35, "acceptance": "Original acceptance"}, {"id": "critique", "type": "critique", "estimated_minutes": None}]
    before = copy.deepcopy(tasks)
    steps = build_learning_path(context(), {"learning_outcome": "present"}, tasks)
    assert steps[0]["task_ids"] == ["explain"]
    assert steps[0]["estimated_minutes"] == 35
    assert next(s for s in steps if s.get("activity") == "questions")["task_ids"] == ["critique"]
    assert tasks == before


@pytest.mark.parametrize("association", [{"claim_ids": ["result"]}, {"anchor_ids": ["a4"]}, {"learning_step_ids": ["another-step"]}])
def test_type_and_activity_fallback_cannot_override_explicit_task_evidence(association):
    data = context()
    data["learning_steps"] = [{"id": "selected-step", "title": "Selected method", "activity": "orientation", "claim_ids": ["methodology"]}]
    tasks = [{"id": "unrelated", "type": "explain", "activity": "orientation", "estimated_minutes": 99, **association}]
    before = copy.deepcopy(tasks)
    step = build_learning_path(data, {}, tasks)[0]
    assert step["task_ids"] == []
    assert step["estimated_minutes"] is None
    assert tasks == before


@pytest.mark.parametrize("association", [{"claim_ids": ["methodology"]}, {"anchor_ids": ["a2"]}, {"learning_step_ids": ["selected-step"]}])
def test_explicit_task_evidence_matches_even_when_task_type_differs(association):
    data = context()
    data["learning_steps"] = [{"id": "selected-step", "title": "Selected method", "activity": "orientation", "claim_ids": ["methodology"]}]
    tasks = [{"id": "explicit", "type": "different-type", "estimated_minutes": 12, **association}]
    step = build_learning_path(data, {}, tasks)[0]
    assert step["task_ids"] == ["explicit"]
    assert step["estimated_minutes"] == 12


def test_unassociated_type_fallback_survives_without_unrelated_99_minute_cost():
    data = context()
    data["learning_steps"] = [{"id": "selected-step", "title": "Selected method", "activity": "orientation", "claim_ids": ["methodology"]}]
    tasks = [{"id": "plain", "type": "explain", "estimated_minutes": 35},
             {"id": "unrelated", "type": "explain", "claim_ids": ["result"], "estimated_minutes": 99}]
    step = build_learning_path(data, {}, tasks)[0]
    assert step["task_ids"] == ["plain"]
    assert step["estimated_minutes"] == 35


def test_missing_core_not_invented_and_material_status_propagates():
    data = {"claims": [], "anchors": [], "sources": []}
    steps = build_learning_path(data, {"learning_outcome": "extend"}, [])
    assert steps[0]["claim_ids"] == []
    assert steps[0]["missing_claim_kinds"] == ["problem", "methodology", "limitation"]
    assert all(s["status"] == "needs_material" for s in steps)


def test_cycle_dependent_is_flagged_separately_from_cycle_members():
    data = context()
    data["learning_steps"] = [{"id": "c", "title": "C", "prerequisite_ids": ["b"]}, {"id": "b", "title": "B", "prerequisite_ids": ["a"]}, {"id": "a", "title": "A", "prerequisite_ids": ["b"]}]
    steps = build_learning_path(data, {}, [])
    assert steps[0]["blocked_by_cycle"] and not steps[0]["prerequisite_cycle"]
    assert all(s["prerequisite_cycle"] for s in steps[1:])
