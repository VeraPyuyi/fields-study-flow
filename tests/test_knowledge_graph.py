from __future__ import annotations

import json

from fields_study_flow.knowledge_graph import build_knowledge_graph
from fields_study_flow.models import LearnerProfile, Resource


def test_knowledge_graph_builds_four_layer_evidence_edges_without_private_paths():
    evidence = {
        "resource_title": "Private PDDL Notes",
        "file_name": "private-pddl-notes.md",
        "snippet": "PDDL action preconditions and VAL plan validation decide whether symbolic plans are valid.",
        "score": 3.2,
        "text": "full private chunk text should not be exported",
    }
    resource = Resource(
        title="Private PDDL Notes",
        url="local://private-pddl-notes",
        source="local-library",
        type="notes",
        local_path="C:/Users/example/private/pddl-notes.md",
        concepts=["PDDL", "symbolic planning"],
        focus_areas=["VAL plan validation"],
        learning_key_points=["action preconditions"],
        metadata={"rag": {"top_chunks": [evidence]}},
    )
    study_tasks = [
        {
            "id": "task-1-explain",
            "type": "explain",
            "title": "Explain PDDL action preconditions",
            "resource_titles": ["Private PDDL Notes"],
            "evidence_chunks": [evidence],
        }
    ]
    mastery_evidence = {
        "final_artifact": "paper-mastery",
        "required_evidence": [{"task_id": "task-1-explain", "task_type": "explain", "resources": ["Private PDDL Notes"]}],
    }
    rag_evidence = {"top_chunks": [evidence], "summary": {"chunks": 1, "resources": 1}}

    graph = build_knowledge_graph(
        LearnerProfile(goal="master PDDL action preconditions and VAL plan validation", output_language="en"),
        [resource],
        study_tasks,
        mastery_evidence,
        rag_evidence,
    )

    node_kinds = {node["kind"] for node in graph["nodes"]}
    edge_labels = {edge["label"] for edge in graph["edges"]}
    concept_labels = {node["label"] for node in graph["nodes"] if node["kind"] == "concept"}
    evidence_edges = [edge for edge in graph["edges"] if edge.get("evidence_chunks")]
    serialized = json.dumps(graph, ensure_ascii=False)

    assert {"concept", "resource", "task", "assessment"} <= node_kinds
    assert {"covered_by", "supports", "required_for"} <= edge_labels
    assert any("action preconditions" in label.lower() for label in concept_labels)
    assert evidence_edges
    assert all("text" not in chunk for edge in evidence_edges for chunk in edge["evidence_chunks"])
    assert "C:/Users/example/private" not in serialized
