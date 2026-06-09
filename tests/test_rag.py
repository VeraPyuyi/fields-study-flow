from __future__ import annotations

import json

from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.rag import answer_from_bundle, apply_rag_to_resources, build_rag_index, retrieve_evidence, write_bundle_rag_index


def test_rag_index_chunks_local_markdown_without_private_paths(tmp_path):
    note = tmp_path / "private-pddl-notes.md"
    note.write_text(
        "# PDDL Notes\n\nAction preconditions decide whether a symbolic planning action can run. "
        "State transitions remove delete effects and add new facts.",
        encoding="utf-8",
    )
    resource = Resource(
        title="Private PDDL Notes",
        url="local://private-pddl-notes",
        source="local-library",
        type="notes",
        local_path=str(note.resolve()),
        concepts=["pddl", "symbolic planning"],
    )

    index = build_rag_index([resource], query="PDDL action preconditions", mode="light")

    assert index["summary"]["chunks"] >= 1
    serialized = json.dumps(index, ensure_ascii=False)
    assert str(note.resolve()) not in serialized
    assert index["chunks"][0]["file_name"] == "private-pddl-notes.md"
    assert index["chunks"][0]["private"] is True


def test_retrieve_evidence_returns_ranked_snippets():
    resource = Resource(
        title="Planning Note",
        url="https://example.com/planning",
        source="documentation",
        type="article",
        concepts=["pddl", "symbolic planning"],
        learning_key_points=["VAL validates whether generated plans satisfy PDDL constraints."],
    )
    index = build_rag_index([resource], query="VAL plan validation", mode="light")

    results = retrieve_evidence("How does VAL validate PDDL plans?", index=index, limit=2)

    assert results
    assert results[0]["score"] > 0
    assert "VAL" in results[0]["snippet"]
    assert results[0]["resource_title"] == "Planning Note"


def test_apply_rag_to_resources_attaches_evidence_and_reranks():
    relevant = Resource(
        title="Specific VAL Notes",
        url="https://example.com/val",
        source="documentation",
        type="article",
        concepts=["pddl"],
        learning_key_points=["VAL checks plan validity and action preconditions in symbolic planning."],
        score=0.4,
    )
    broad = Resource(
        title="Broad Machine Learning Book",
        url="https://example.com/ml",
        source="book",
        type="book",
        concepts=["machine learning"],
        learning_key_points=["General optimization overview."],
        score=0.9,
    )
    profile = LearnerProfile(goal="learn VAL plan validity for PDDL", output_language="en", route_depth="fastest")

    ranked, index = apply_rag_to_resources(profile, [broad, relevant], mode="light")

    assert index["summary"]["chunks"] >= 2
    assert ranked[0].title == "Specific VAL Notes"
    assert ranked[0].metadata["rag"]["evidence_score"] > 0
    assert ranked[0].metadata["rag"]["top_chunks"]


def test_write_bundle_rag_index_and_answer_from_bundle(tmp_path):
    resource_dir = tmp_path / "bundle"
    resource_dir.mkdir()
    note = resource_dir / "01-pddl-notes.md"
    note.write_text("PDDL action applicability depends on preconditions. VAL can validate plans.", encoding="utf-8")
    manifest = {
        "resources": [
            {
                "index": 1,
                "title": "PDDL Notes",
                "source": "local-library",
                "type": "notes",
                "status": "copied",
                "file": note.name,
                "selected": True,
            }
        ]
    }

    index = write_bundle_rag_index(resource_dir, manifest, query="PDDL validation", mode="light")
    answer = answer_from_bundle(resource_dir, "What checks action applicability?", limit=2)

    assert (resource_dir / ".rag_index" / "manifest.json").exists()
    assert index["summary"]["chunks"] == 1
    assert answer["status"] == "ok"
    assert "PDDL action applicability" in answer["answer"]
    assert answer["sources"][0]["file_name"] == note.name


def test_answer_from_bundle_refuses_when_no_evidence(tmp_path):
    resource_dir = tmp_path / "bundle"
    (resource_dir / ".rag_index").mkdir(parents=True)
    (resource_dir / ".rag_index" / "manifest.json").write_text(
        json.dumps({"chunks": [], "summary": {"chunks": 0}}, ensure_ascii=False),
        encoding="utf-8",
    )

    answer = answer_from_bundle(resource_dir, "What is the paper about?")

    assert answer["status"] == "no-evidence"
    assert "not found" in answer["answer"].lower()
