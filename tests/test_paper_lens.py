from __future__ import annotations

import json

from fields_study_flow.paper_lens import build_paper_lens, render_paper_lens_html


def _roadmap_with_target_paper() -> dict:
    return {
        "title": "Teaching LLMs to Plan Learning Roadmap",
        "profile": {
            "goal": "master Teaching LLMs to Plan",
            "output_language": "zh-CN",
            "resource_language_preference": "balanced",
        },
        "phases": [
            {
                "name": "Phase 1",
                "resources": [
                    {
                        "title": "Teaching LLMs to Plan",
                        "url": "local://paper-teaching-llms-to-plan",
                        "source": "local-library",
                        "type": "paper",
                        "local_path": None,
                        "metadata": {
                            "target_paper": True,
                            "paper_metadata": {
                                "title": "Teaching LLMs to Plan: Logical Chain-of-Thought Instruction Tuning for Symbolic Planning",
                                "authors": ["Example Author"],
                                "abstract_snippet": "The paper studies logical chain-of-thought instruction tuning for symbolic planning.",
                                "concepts": ["symbolic planning", "logical chain-of-thought", "PDDL"],
                                "sections": ["Introduction", "Method", "Experiments", "Limitations"],
                                "method_hints": ["The method constructs logical chain-of-thought traces for planning instruction tuning."],
                                "experiment_hints": ["Experiments evaluate generated plans with PDDL-style symbolic planning tasks."],
                                "limitations_hints": ["The approach depends on the quality of planning traces and task coverage."],
                                "formula_candidates": ["a_t = planner(s_t, g, PDDL)"],
                                "keywords": ["PDDL", "planning", "chain-of-thought"],
                                "code_links": ["https://github.com/example/planning-code"],
                                "metadata_status": "ok",
                                "local_path": None,
                            },
                        },
                    },
                    {
                        "title": "PDDL Notes",
                        "url": "https://planning.wiki/ref/pddl",
                        "source": "documentation",
                        "type": "documentation",
                        "concepts": ["PDDL", "action preconditions"],
                    },
                ],
            }
        ],
        "resource_library": [
            {
                "title": "Teaching LLMs to Plan",
                "url": "local://paper-teaching-llms-to-plan",
                "source": "local-library",
                "type": "paper",
                "selected": True,
                "concepts": ["symbolic planning", "logical chain-of-thought"],
                "learning_key_points": ["problem, contribution, and assumptions"],
            },
            {
                "title": "PDDL Notes",
                "url": "https://planning.wiki/ref/pddl",
                "source": "documentation",
                "type": "documentation",
                "selected": True,
                "concepts": ["PDDL", "action preconditions"],
                "learning_key_points": ["Action preconditions decide whether a plan step can run."],
            },
        ],
        "study_bundle": {
            "resources": [
                {
                    "title": "Teaching LLMs to Plan",
                    "url": "local://paper-teaching-llms-to-plan",
                    "status": "copied",
                    "type": "paper",
                    "local_href": "../study-assets/01-teaching-llms-to-plan.pdf",
                },
                {
                    "title": "PDDL Notes",
                    "url": "https://planning.wiki/ref/pddl",
                    "status": "snapshotted",
                    "type": "documentation",
                    "local_href": "../study-assets/02-pddl-notes.html",
                },
            ]
        },
        "rag_evidence": {
            "top_chunks": [
                {
                    "resource_id": "pddl-notes",
                    "resource_title": "PDDL Notes",
                    "source": "documentation",
                    "type": "documentation",
                    "file_name": "02-pddl-notes.html",
                    "snippet": "PDDL action preconditions determine whether a planning action is applicable.",
                    "score": 4.2,
                }
            ]
        },
        "study_tasks": [
            {
                "id": "task-1-explain",
                "type": "explain",
                "title": "Explain the target paper",
                "resource_titles": ["Teaching LLMs to Plan", "PDDL Notes"],
                "evidence_chunks": [
                    {
                        "resource_title": "PDDL Notes",
                        "file_name": "02-pddl-notes.html",
                        "snippet": "PDDL action preconditions determine whether a planning action is applicable.",
                        "score": 4.2,
                    }
                ],
            }
        ],
    }


def test_build_paper_lens_maps_bundle_and_evidence_to_target_sections():
    roadmap = _roadmap_with_target_paper()

    lens = build_paper_lens(roadmap)

    assert lens["mode"] == "single-target"
    assert lens["target_papers"][0]["local_href"] == "../study-assets/01-teaching-llms-to-plan.pdf"
    section_kinds = {section["kind"] for section in lens["sections"]}
    assert {"abstract", "method", "experiment", "limitation", "formula"} <= section_kinds
    method = next(section for section in lens["sections"] if section["kind"] == "method")
    assert method["annotations"]
    assert any(annotation["local_href"] == "../study-assets/02-pddl-notes.html" for annotation in method["annotations"])
    assert any(annotation["task_ids"] == ["task-1-explain"] for annotation in method["annotations"])
    serialized = json.dumps(lens, ensure_ascii=False)
    assert "C:/" not in serialized
    assert "D:/" not in serialized


def test_render_paper_lens_html_is_interactive_local_first_and_chinese():
    roadmap = _roadmap_with_target_paper()
    roadmap["paper_lens"] = build_paper_lens(roadmap)

    html = render_paper_lens_html(roadmap)

    assert "paper-lens-app" in html
    assert "data-lens-section" in html
    assert "data-lens-filter" in html
    assert "localStorage" in html
    assert "overflow-wrap:anywhere" in html
    assert "目标论文增强阅读器" in html
    assert "打开本地论文" in html
    assert "../study-assets/01-teaching-llms-to-plan.pdf" in html
    assert "../study-assets/02-pddl-notes.html" in html
    assert "C:/" not in html
    assert "D:/" not in html
