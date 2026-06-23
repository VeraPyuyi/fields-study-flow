from __future__ import annotations

import json
import re

from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.paper_map import build_paper_map, render_paper_map_html
from fields_study_flow.roadmap import build_roadmap, write_outputs


def _paper_map_roadmap() -> dict:
    text_preview = "\n\n".join(
        [
            "Abstract",
            "Large language models struggle with symbolic planning because valid plans must satisfy action preconditions and effects.",
            "Logical chain-of-thought traces expose state transitions so the model learns why a plan step is allowed.",
            "Introduction",
            "Symbolic planning needs machine-checkable plans, but language models often produce plausible text that violates PDDL constraints.",
            "The motivation is to teach models to reason through action preconditions, effects, and state transitions before outputting a plan.",
            "Method",
            "We construct PDDL-Instruct examples that pair natural language tasks with PDDL domains and logical reasoning traces.",
            "The trace names the current state, checks preconditions, applies effects, and moves to the next state.",
            "Experiments",
            "PlanBench evaluates whether generated plans are executable under PDDL-style domain constraints.",
            "VAL-style validation checks whether the proposed action sequence actually reaches the goal.",
            "Results",
            "Results show that logical traces help models produce plans that better obey symbolic constraints.",
            "Limitations",
            "The approach depends on the quality and coverage of generated planning traces and may fail on unseen domains.",
        ]
    )
    target = Resource(
        title="Teaching LLMs to Plan: Logical Chain-of-Thought Instruction Tuning for Symbolic Planning",
        url="https://arxiv.org/abs/2402.12345",
        source="arxiv",
        type="paper",
        concepts=["PDDL", "Logical CoT", "symbolic planning", "PlanBench", "VAL validation"],
        metadata={
            "target_paper": True,
            "paper_metadata": {
                "title": "Teaching LLMs to Plan: Logical Chain-of-Thought Instruction Tuning for Symbolic Planning",
                "authors": ["Example Author"],
                "abstract_snippet": "Large language models struggle with symbolic planning because valid plans must satisfy action preconditions and effects.",
                "concepts": ["PDDL", "Logical CoT", "symbolic planning", "PlanBench", "VAL validation"],
                "method_hints": ["PDDL-Instruct pairs planning tasks with logical chain-of-thought traces."],
                "experiment_hints": ["PlanBench and VAL-style validation test whether generated plans are executable."],
                "limitations_hints": ["Coverage and quality of generated traces limit generalization to unseen domains."],
                "keywords": ["PDDL", "Logical CoT", "PlanBench", "VAL"],
                "text_preview": text_preview,
                "metadata_status": "ok",
            },
        },
    )
    support = Resource(
        title="PDDL Notes",
        url="https://example.com/pddl",
        source="web",
        type="article",
        concepts=["PDDL", "preconditions", "effects"],
        metadata={"local_href": "../study-assets/pddl-notes.html"},
    )
    roadmap = build_roadmap(LearnerProfile(goal="中文掌握 Teaching LLMs to Plan", output_language="zh-CN", target_kind="paper"), [target, support])
    roadmap["study_bundle"] = {
        "resources": [
            {
                "title": target.title,
                "url": target.url,
                "local_href": "../study-assets/teaching-llms-to-plan.pdf",
                "status": "downloaded",
                "file_name": "teaching-llms-to-plan.pdf",
            },
            {
                "title": support.title,
                "url": support.url,
                "local_href": "../study-assets/pddl-notes.html",
                "status": "snapshotted",
                "file_name": "pddl-notes.html",
            },
        ]
    }
    roadmap["rag_evidence"] = {
        "summary": {"chunks": 2, "resources": 1},
        "evidence": [
            {
                "chunk_id": "chunk-method",
                "resource_title": target.title,
                "file_name": "teaching-llms-to-plan.pdf",
                "snippet": "PDDL-Instruct examples pair natural language tasks with PDDL domains and logical reasoning traces.",
                "score": 0.9,
            },
            {
                "chunk_id": "chunk-experiment",
                "resource_title": target.title,
                "file_name": "teaching-llms-to-plan.pdf",
                "snippet": "PlanBench and VAL-style validation check whether proposed action sequences reach the goal.",
                "score": 0.88,
            },
        ],
    }
    return roadmap


def test_build_paper_map_creates_causal_chain_with_evidence_and_chinese():
    roadmap = _paper_map_roadmap()

    paper_map = build_paper_map(roadmap, paper_map_language="zh-CN", paper_map_depth="standard")

    assert paper_map["mode"] == "single-paper"
    assert paper_map["provider"] == {"mode": "local", "llm_extension_ready": True}
    core_kinds = [node["kind"] for node in paper_map["nodes"] if node["role"] == "core"]
    assert core_kinds == ["background", "motivation", "problem", "methodology", "experiment", "contribution", "limitation"]
    labels = " ".join(node["label"] for node in paper_map["nodes"])
    assert "PDDL" in labels or "Logical CoT" in labels
    assert any("PlanBench" in node["label"] or "VAL" in node["label"] for node in paper_map["nodes"])
    assert {edge["label"] for edge in paper_map["edges"]} >= {"motivates", "addresses", "implements", "evaluated_by", "claims", "bounded_by"}
    for node in [node for node in paper_map["nodes"] if node["role"] == "core"]:
        assert node["plain_explanation"]
        assert node["why_it_matters"]
        assert node["talking_point"]
        assert node["confidence"] > 0
        assert "evidence" in node
    serialized = json.dumps(paper_map, ensure_ascii=False)
    assert "C:/" not in serialized
    assert "D:/" not in serialized


def test_build_paper_map_adds_xmind_flow_layout_for_graphical_canvas():
    roadmap = _paper_map_roadmap()

    paper_map = build_paper_map(roadmap, paper_map_language="zh-CN", paper_map_depth="standard")

    assert paper_map["layout"]["kind"] == "xmind-flow"
    assert paper_map["layout"]["coordinate_system"] == "absolute"
    assert paper_map["layout"]["canvas"]["width"] >= 1600
    assert paper_map["layout"]["canvas"]["height"] >= 900
    target_node = next(node for node in paper_map["nodes"] if node["role"] == "target")
    assert target_node["layout"]["layer"] == 0
    assert isinstance(target_node["layout"]["x"], int)
    assert isinstance(target_node["layout"]["y"], int)
    core_nodes = [node for node in paper_map["nodes"] if node["role"] == "core"]
    assert all(node["layout"]["layer"] == 1 for node in core_nodes)
    assert all("branch_group" in node["layout"] for node in core_nodes)
    branch_nodes = [node for node in paper_map["nodes"] if node["role"] not in {"target", "core"}]
    assert branch_nodes
    assert all(node["layout"]["layer"] >= 2 for node in branch_nodes)
    assert any(node["layout"].get("collapsed") is False for node in core_nodes)


def test_render_paper_map_html_is_interactive_and_script_json_is_parseable():
    roadmap = _paper_map_roadmap()
    roadmap["paper_map"] = build_paper_map(roadmap, paper_map_language="zh-CN", paper_map_depth="standard")

    html = render_paper_map_html(roadmap)

    assert "paper-map-app" in html
    assert "paper-map-node" in html
    assert "paper-map-edge" in html
    assert "paper-map-detail-panel" in html
    assert "进入精读阅读器" in html
    assert "论文逻辑图" in html
    data_match = re.search(r'<script type="application/json" id="paper-map-data">(.*?)</script>', html, re.S)
    assert data_match
    assert "&quot;" not in data_match.group(1)
    assert json.loads(data_match.group(1))["nodes"]
    assert "document.addEventListener('click'" in html
    assert "overflow-wrap:anywhere" in html
    assert "C:/" not in html
    assert "D:/" not in html


def test_render_paper_map_html_contains_xmind_canvas_controls_and_graph_edges():
    roadmap = _paper_map_roadmap()
    roadmap["paper_map"] = build_paper_map(roadmap, paper_map_language="zh-CN", paper_map_depth="standard")

    html = render_paper_map_html(roadmap)

    assert "paper-map-canvas" in html
    assert "paper-map-svg-edge" in html
    assert "paper-map-zoom-control" in html
    assert "data-paper-map-fit" in html
    assert "data-paper-map-reset" in html
    assert "data-paper-map-show-all" in html
    assert "data-paper-map-collapse-detail" in html
    assert "data-paper-map-source-dock" in html
    assert "data-paper-map-source-toggle" in html
    assert "paper-map-source-dock collapsed" in html
    assert "data-paper-map-expand-toggle" in html
    assert "data-paper-map-viewport" in html
    assert "localStorage" in html
    assert "sourceDockCollapsed" in html
    assert "visibleNodeBounds" in html
    assert "node.role !== 'resource'" in html
    assert "pointerdown" in html
    assert "wheel" in html
    assert "updateEdges" in html
    assert "translate(" in html
    assert "scale(" in html
    assert "paper-map-branch-node" in html
    data_match = re.search(r'<script type="application/json" id="paper-map-data">(.*?)</script>', html, re.S)
    assert data_match
    payload = json.loads(data_match.group(1))
    assert payload["layout"]["kind"] == "xmind-flow"


def test_write_outputs_writes_paper_map_and_links_from_roadmap(tmp_path):
    roadmap = _paper_map_roadmap()
    profile = LearnerProfile(goal="中文掌握 Teaching LLMs to Plan", output_language="zh-CN", target_kind="paper")

    write_outputs(tmp_path, profile, [], roadmap, {})

    exported = json.loads((tmp_path / "roadmap.json").read_text(encoding="utf-8"))
    assert "paper_map" in exported
    assert "paper_map.html" in exported["outputs"]
    assert (tmp_path / "paper_map.html").exists()
    roadmap_html = (tmp_path / "roadmap.html").read_text(encoding="utf-8")
    paper_map_html = (tmp_path / "paper_map.html").read_text(encoding="utf-8")
    assert 'data-report-kind="roadmap"' in roadmap_html
    assert "fields-study-flow-data" in roadmap_html
    assert "paper_map.html" in roadmap_html
    assert 'data-report-kind="paper_map"' in paper_map_html
    assert "fields-study-flow-data" in paper_map_html
