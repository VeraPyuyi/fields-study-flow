import copy
import json
from pathlib import Path

import pytest

from fields_study_flow.models import Resource
from fields_study_flow.research_context import build_research_context, validate_research_context, bind_context_links
from fields_study_flow.learning_path import build_learning_path


CASES = json.loads((Path(__file__).parent / "fixtures/research_workbench/cases.json").read_text())["cases"]


def paper(case):
    return Resource(title=case["title"], url=f"https://example.org/demonstration/{case['id']}",
                    source="demonstration", type="paper", metadata={"segments": case["sections"]})


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["id"])
def test_crossdomain_reference_equality_and_determinism(case):
    roadmap = {"target_id": case["id"], "profile": {"goal": case["title"]}}
    context = build_research_context(roadmap, [paper(case)])
    assert context == build_research_context(roadmap, [paper(case)])
    assert context["schema_version"] == 1
    assert validate_research_context(context) == {"valid": True, "issues": []}
    context["learning_steps"] = build_learning_path(context, {"learning_outcome": "present"}, [])
    assert validate_research_context(context)["valid"]
    claims = {c["id"]: c for c in context["claims"]}
    anchors = {a["id"]: a for a in context["anchors"]}
    for step in context["learning_steps"]:
        assert all(a in anchors for a in step["anchor_ids"])
        assert all(c in claims for c in step["claim_ids"])
        assert set(a for c in step["claim_ids"] for a in claims[c]["anchor_ids"]) <= set(step["anchor_ids"])


def test_legacy_resource_library_and_unlocated_hints_not_fabricated():
    roadmap = {"profile": {"goal": "legacy"}, "resource_library": [{"title": "Legacy paper", "url": "https://example.org/legacy", "source": "paper", "type": "paper", "metadata": {"paper_metadata": {"method_hints": ["A method hint with no page"]}}}]}
    context = build_research_context(roadmap)
    assert context["sources"]
    assert any(c["kind"] == "methodology" and c["evidence_status"] == "missing" for c in context["claims"])
    assert all(a["locator_status"] == "missing" for a in context["anchors"])


def test_similar_unrelated_code_is_only_candidate(tmp_path):
    code = tmp_path / "planning.py"
    code.write_text("def planning_grocery_list():\n    return ['milk']\n")
    context = build_research_context({"target_id": "planning"}, [paper(CASES[0]), Resource(title="Planning implementation", url="", source="local-library", type="code", local_path=str(code))])
    candidates = [r for r in context["relations"] if r["kind"] == "implements"]
    assert candidates
    assert all(r["review_status"] == "unreviewed" and r["origin"] == "rule" and r["candidate"] for r in candidates)
    assert not any(r["review_status"] == "accepted" for r in context["relations"])


def test_source_change_invalidates_only_related_anchors(tmp_path):
    a, b = tmp_path / "a.md", tmp_path / "b.md"
    a.write_text("# Method\nFirst method\n")
    b.write_text("# Limitations\nUnchanged boundary\n")
    resources = [Resource(title=p.name, url="", source="local-library", type="paper", local_path=str(p)) for p in (a, b)]
    resources[0].metadata["target_paper"] = True
    first = build_research_context({"target_id": "fixed"}, resources)
    a.write_text("# Method\nUpdated method\n")
    second = build_research_context({"target_id": "fixed"}, resources, previous_context=first)
    changed_id = first["sources"][0]["id"]
    assert first["bundle_id"] == second["bundle_id"]
    assert first["snapshot_id"] != second["snapshot_id"]
    assert all(x["locator_status"] == "stale" for x in second["anchors"] if x["source_id"] == changed_id)
    assert all(x["locator_status"] == "valid" for x in second["anchors"] if x["source_id"] != changed_id)
    assert any(c["evidence_status"] == "stale" for c in second["claims"])
    assert validate_research_context(second)["valid"]


def test_snapshot_changes_for_options_not_bundle_identity():
    one = build_research_context({"target_id": "one", "paper_map_options": {"depth": "standard"}}, [paper(CASES[0])])
    two = build_research_context({"target_id": "one", "paper_map_options": {"depth": "dense"}}, [paper(CASES[0])])
    assert one["bundle_id"] == two["bundle_id"]
    assert one["snapshot_id"] != two["snapshot_id"]
    assert one["bundle_id"] != build_research_context({"target_id": "other"}, [paper(CASES[0])])["bundle_id"]


@pytest.mark.parametrize("change", ["statement", "relation", "review", "config"])
def test_snapshot_tracks_explicit_semantics_and_requires_review(change):
    resource = paper(CASES[0])
    resource.metadata["source_id"] = "target"
    roadmap = {
        "target_id": "semantic-snapshot",
        "claims": [{"id": "method", "kind": "methodology", "statement": "Original method interpretation", "source_id": "target", "locator": {"section": "Method"}}],
        "relations": [{"from": "method", "to": "target", "kind": "supports", "origin": "human", "review_status": "accepted"}],
        "research_options": {"depth": "standard"},
    }
    previous = build_research_context(roadmap, [resource])
    edited = copy.deepcopy(roadmap)
    if change == "statement":
        edited["claims"][0]["statement"] = "Revised method interpretation"
    elif change == "relation":
        edited["relations"][0]["kind"] = "addresses"
    elif change == "review":
        edited["relations"][0]["review_status"] = "rejected"
    else:
        edited["research_options"]["depth"] = "dense"
    rebuilt = build_research_context(edited, [resource], previous_context=previous)
    assert rebuilt["bundle_id"] == previous["bundle_id"]
    assert rebuilt["snapshot_id"] != previous["snapshot_id"]
    assert rebuilt["changes"]["review_required"]
    assert rebuilt["changes"]["changed_source_ids"] == []
    assert all(a["locator_status"] == "valid" for a in rebuilt["anchors"])
    assert validate_research_context(rebuilt)["valid"]
    assert build_research_context(edited, [resource], previous_context=rebuilt)["snapshot_id"] == rebuilt["snapshot_id"]


def test_unchanged_explicit_snapshot_does_not_request_review():
    roadmap = {"target_id": "unchanged", "claims": [{"id": "question", "kind": "problem", "statement": "Unchanged question"}], "key_options": {"depth": 1}}
    before = build_research_context(roadmap, [paper(CASES[0])])
    after = build_research_context(copy.deepcopy(roadmap), [paper(CASES[0])], previous_context=before)
    assert after["snapshot_id"] == before["snapshot_id"]
    assert not after["changes"]["review_required"]


@pytest.mark.parametrize("marked", [False, True])
def test_primary_target_identity_precedes_shared_generic_goal(marked):
    first, second = paper(CASES[0]), paper(CASES[1])
    if marked:
        first.metadata["target_paper"] = second.metadata["target_paper"] = True
    roadmap = {"profile": {"goal": "Understand and present the target paper"}}
    a = build_research_context(roadmap, [first])
    b = build_research_context(roadmap, [second], previous_context=a)
    assert a["bundle_id"] != b["bundle_id"]
    assert not b["changes"]["removed_source_ids"]


def test_primary_bundle_ignores_goal_wording_support_order_and_file_changes(tmp_path):
    path = tmp_path / "target.md"
    path.write_text("# Method\nOriginal method\n")
    target = Resource(title="Target", url="", source="local-library", type="paper", local_path=str(path), metadata={"target_paper": True})
    first = build_research_context({"profile": {"goal": "Understand the target"}}, [target])
    path.write_text("# Method\nChanged method\n")
    second = build_research_context({"profile": {"goal": "Present the target"}}, [paper(CASES[1]), target])
    assert first["bundle_id"] == second["bundle_id"]
    assert first["snapshot_id"] != second["snapshot_id"]


def test_binding_duplicate_titles_safe_relocatable_and_nonmutating():
    resources = [paper(CASES[0]), paper(CASES[1])]
    resources[1].title = resources[0].title
    context = build_research_context({"target_id": "binding"}, resources)
    original = copy.deepcopy(context)
    manifest = {"resources": [{"title": r.title, "url": r.url, "status": "copied", "local_href": f"study-assets/{i}.md"} for i, r in enumerate(resources)]}
    bound = bind_context_links(context, manifest)
    assert [s["local_href"] for s in bound["sources"]] == ["study-assets/0.md", "study-assets/1.md"]
    assert context == original
    assert bound["claims"] == context["claims"]
    assert bound["snapshot_id"] == context["snapshot_id"]
    manifest["resources"][0]["local_href"] = "../../secret.txt"
    assert "local_href" not in bind_context_links(context, manifest)["sources"][0]
    title_only = {"resources": [{"title": resources[0].title, "status": "copied", "local_href": "assets/unsafe.md"}]}
    assert all("local_href" not in s for s in bind_context_links(context, title_only)["sources"])


def test_verified_crossdirectory_bundle_link_and_wrong_file_rejected():
    r = paper(CASES[0])
    context = build_research_context({"target_id": "crossdirectory"}, [r])
    entry = {"url": r.url, "status": "copied", "file": "01-paper.pdf", "local_href": "../../study-assets/teaching-llms-to-plan/01-paper.pdf"}
    bound = bind_context_links(context, {"resources": [entry]})
    assert bound["sources"][0]["local_href"] == entry["local_href"]
    assert validate_research_context(bound)["valid"]
    entry["local_href"] = "../../unrelated/other.pdf"
    assert "local_href" not in bind_context_links(context, {"resources": [entry]})["sources"][0]


def test_support_papers_do_not_become_core_claims():
    target = paper(CASES[0])
    target.metadata["target_paper"] = True
    supports = [Resource(title="Support", url=f"https://example.org/support/{i}", source="support", type="paper", metadata={"segments": [{"section": "Method", "text": f"Unrelated support method {i}"}]}) for i in range(20)]
    context = build_research_context({"target_id": "primary"}, [target, *supports])
    assert len(context["sources"]) == 21
    assert len(context["primary_source_ids"]) == 1
    assert len(context["claims"]) == 4
    assert not any("Unrelated support" in c["statement"] for c in context["claims"])
    assert all(c["mandatory"] for c in context["claims"])


def test_lens_unique_target_selects_primary_without_resource_flag():
    context = build_research_context({"paper_lens": {"target": {"url": paper(CASES[0]).url}}}, [paper(CASES[0]), paper(CASES[1])])
    assert len(context["claims"]) == 4
    assert len(context["primary_source_ids"]) == 1


def test_bundle_identity_stable_when_support_material_is_added():
    target = paper(CASES[0])
    target.metadata["target_paper"] = True
    roadmap = {"profile": {"goal": "Understand the planning target"}}
    first = build_research_context(roadmap, [target])
    second = build_research_context(roadmap, [target, paper(CASES[1])])
    assert first["bundle_id"] == second["bundle_id"]
    assert first["snapshot_id"] != second["snapshot_id"]


def test_changed_claim_downgrades_explicit_reviewed_relation_without_direct_anchors():
    r = paper(CASES[0])
    r.metadata["source_id"] = "target"
    roadmap = {"target_id": "review", "claims": [{"id": "method", "kind": "methodology", "statement": "Method", "source_id": "target", "locator": {"section": "Method"}}], "relations": [{"from": "method", "to": "target", "kind": "implements", "origin": "human", "review_status": "accepted"}]}
    previous = build_research_context(roadmap, [r])
    r.metadata["segments"] = [*CASES[0]["sections"], {"section": "Experiment", "text": "An added experiment"}]
    changed = build_research_context(roadmap, [r], previous_context=previous)
    assert changed["relations"][0]["review_status"] == "unreviewed"
    assert changed["relations"][0]["review_required"]


def test_deleted_file_missing_material_not_marked_available(tmp_path):
    missing = tmp_path / "missing-results.json"
    r = Resource(title="Missing results", url="", source="local-library", type="result", local_path=str(missing))
    context = build_research_context({"target_id": "missing-file"}, [r])
    assert "result" in context["coverage"]["missing_material_kinds"]
    assert context["sources"][0]["availability"] == "missing"


def test_directory_resource_id_cannot_bind_one_file_to_every_child():
    root = Path(__file__).parent / "fixtures/research_workbench/toy_project"
    r = Resource(title="Toy", url="", source="local-library", type="code", local_path=str(root))
    context = build_research_context({"target_id": "directory"}, [r])
    rid = context["sources"][0]["resource_id"]
    entry = {"resource_id": rid, "file": "planner.py", "local_href": "assets/planner.py", "status": "copied"}
    assert all("local_href" not in s for s in bind_context_links(context, {"resources": [entry]})["sources"])


def test_removed_source_stales_old_citations():
    r = paper(CASES[0])
    old = build_research_context({"target_id": "removed"}, [r])
    new = build_research_context({"target_id": "removed"}, [], previous_context=old)
    assert new["changes"]["removed_source_ids"] == [old["sources"][0]["id"]]
    assert all(a["locator_status"] == "stale" for a in new["anchors"])
    assert all(c["evidence_status"] == "stale" for c in new["claims"])
    assert validate_research_context(new)["valid"]


def test_explicit_resource_claim_and_supplied_relation():
    r = paper(CASES[0])
    r.metadata["source_id"] = "paper-source"
    r.metadata["claims"] = [{"id": "explicit", "kind": "contribution", "statement": "Explicit supplied observation", "locator": {"section": "Method"}}]
    context = build_research_context({"target_id": "explicit", "claims": [{"id": "problem", "kind": "problem", "statement": "Explicit question", "source_id": "paper-source", "locator": {"section": "Problem"}}], "relations": [{"from": "explicit", "to": "problem", "kind": "addresses"}]}, [r])
    explicit = next(c for c in context["claims"] if c["statement"] == "Explicit supplied observation")
    assert explicit["evidence_status"] == "located"
    relation = next(r for r in context["relations"] if r["from"] == explicit["id"])
    assert relation["origin"] == "supplied" and relation["review_status"] == "unreviewed"


def test_unresolved_explicit_anchor_not_silently_fully_located():
    r = paper(CASES[0])
    first = build_research_context({"target_id": "partial"}, [r])
    valid = first["anchors"][0]["id"]
    context = build_research_context({"target_id": "partial", "claims": [{"id": "partial", "kind": "methodology", "statement": "Partially located", "anchor_ids": [valid, "unknown"]}]}, [r])
    claim = next(c for c in context["claims"] if c["statement"] == "Partially located")
    assert claim["evidence_status"] == "partial"
    assert validate_research_context(context)["valid"]
    assert any(s["reason"] == "invalid_claim_anchor_reference" for s in context["coverage"]["skipped"])


def test_removed_previous_source_public_fields_resanitized():
    previous = build_research_context({"target_id": "privacy-old"}, [paper(CASES[0])])
    previous["sources"][0].update(title="D:\\private\\paper.pdf", relative_path="C:\\private\\paper.pdf", url="https://user:password@example.org/paper?token=SECRET_TEST")
    context = build_research_context({"target_id": "privacy-old"}, [], previous_context=previous)
    assert "private\\\\paper" not in json.dumps(context)
    assert "SECRET_TEST" not in json.dumps(context)
    assert validate_research_context(context)["valid"]


@pytest.mark.parametrize("bad", [None, [], {"schema_version": 2}, {"schema_version": 1, "sources": [None], "anchors": "bad", "claims": [{}], "relations": [3], "learning_steps": [{}]}])
def test_validation_metadata_errors_never_throw(bad):
    result = validate_research_context(bad)
    assert not result["valid"] and result["issues"]


def test_validator_references_locator_status_and_unknown_estimate():
    context = build_research_context({"target_id": "test"}, [paper(CASES[0])])
    context["anchors"][0]["source_id"] = "unknown"
    context["anchors"][0]["locator"] = {"line_start": 10, "line_end": 1}
    context["claims"][0]["anchor_ids"] = ["ghost"]
    context["learning_steps"] = [{"id": "step", "title": "Step", "claim_ids": [], "anchor_ids": [], "task_ids": [], "prerequisite_ids": ["ghost"], "estimated_minutes": 0, "reason": "test", "status": "available"}]
    result = validate_research_context(context)
    assert not result["valid"]
    assert len(result["issues"]) >= 4


def test_empty_project_reports_honest_missing_material_and_no_path_tokens():
    context = build_research_context({"target_id": "empty", "claims": [{"kind": "result", "statement": "Raw results needed"}], "profile": {"goal": "read D:\\private\\paper.pdf token=secret-value"}})
    assert context["claims"][0]["evidence_status"] == "missing"
    assert not context["sources"]
    public = json.dumps(context)
    assert "D:\\\\private" not in public and "secret-value" not in public
