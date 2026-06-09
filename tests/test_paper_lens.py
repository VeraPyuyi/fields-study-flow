from __future__ import annotations

import json
import re

from fields_study_flow.paper_lens import build_paper_lens, render_paper_lens_html, write_paper_lens_latex


def _roadmap_with_target_paper() -> dict:
    text_preview = "\n\n".join(
        [
            "Abstract",
            "Large language models struggle with symbolic planning because valid plans must satisfy action preconditions and effects.",
            "Logical chain-of-thought traces expose state transitions so the model learns why a plan step is allowed.",
            "Introduction",
            "Symbolic planning is different from open-ended text generation because every action changes a structured world state.",
            "A planner must check whether the current state contains the facts required by the next action.",
            "Method",
            "We construct PDDL-Instruct examples that pair natural language tasks with PDDL domains and logical reasoning traces.",
            "The trace acts like a worked example: it names the current state, checks preconditions, applies effects, and moves to the next state.",
            "The model is instruction tuned on these logical traces instead of only final answers.",
            "Formula",
            "The state transition can be written as s_{t+1} = apply(a_t, s_t) when preconditions(a_t) are satisfied.",
            "Experiments",
            "PlanBench evaluates whether generated plans are executable under PDDL-style domain constraints.",
            "VAL-style validation checks whether the proposed action sequence actually reaches the goal.",
            "Results show that logical traces help models produce plans that better obey symbolic constraints.",
            "Limitations",
            "The approach depends on the quality and coverage of generated planning traces.",
            "It may still fail when the planning domain is unseen or when long-horizon dependencies become too complex.",
            "Future work should improve self-verification and broaden PDDL domain coverage.",
        ]
    )
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
                                "text_preview": text_preview,
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


def test_build_paper_lens_generates_dense_segments_and_chinese_inline_explanations():
    roadmap = _roadmap_with_target_paper()

    dense = build_paper_lens(roadmap, paper_lens_language="zh-CN", paper_lens_density="dense")
    key = build_paper_lens(roadmap, paper_lens_language="zh-CN", paper_lens_density="key")

    assert len(dense["segments"]) > len(key["segments"])
    assert len(dense["segments"]) <= 120
    first_segment = dense["segments"][0]
    assert {"id", "section_kind", "order", "original_text", "source_language", "importance_score"} <= set(first_segment)
    assert any(segment["section_kind"] == "method" for segment in dense["segments"])
    assert any(segment["section_kind"] == "experiment" for segment in dense["segments"])
    assert any(segment["section_kind"] == "limitation" for segment in dense["segments"])

    explanation = dense["inline_explanations"][0]
    assert {"plain_meaning", "why_it_matters", "method_note", "related_resources", "evidence_refs", "detail_anchor", "confidence"} <= set(explanation)
    assert not explanation["plain_meaning"].startswith("这句话在说什么")
    assert not explanation["why_it_matters"].startswith("为什么重要")
    assert not explanation["method_note"].startswith("方法怎么理解")
    assert "接下来读什么" not in explanation["related_resources"][0]
    for field in ("plain_meaning", "why_it_matters", "method_note"):
        assert len({item[field] for item in dense["inline_explanations"]}) >= min(8, len(dense["inline_explanations"]))
    assert dense["reading_recommendations"]
    first_recommendation = dense["reading_recommendations"][0]
    assert {"section_id", "section_title", "summary", "resources"} <= set(first_recommendation)
    assert any(resource["local_href"] == "../study-assets/02-pddl-notes.html" for resource in first_recommendation["resources"])
    assert dense["explanation_provider"] == {"mode": "local", "llm_extension_ready": True}
    assert dense["explanation_summary"]["language"] == "zh-CN"
    assert dense["explanation_summary"]["density"] == "dense"


def test_paper_lens_section_summary_follows_prompt_language():
    roadmap = _roadmap_with_target_paper()

    zh_lens = build_paper_lens(roadmap, paper_lens_language="zh-CN", paper_lens_density="key")
    en_lens = build_paper_lens(roadmap, paper_lens_language="en", paper_lens_density="key")

    zh_abstract = next(section for section in zh_lens["sections"] if section["kind"] == "abstract")
    en_abstract = next(section for section in en_lens["sections"] if section["kind"] == "abstract")

    assert "先抓住论文主线" in zh_abstract["summary"]
    assert "模型" in zh_abstract["summary"]
    assert "The paper studies logical chain-of-thought" not in zh_abstract["summary"]
    assert "The paper studies logical chain-of-thought" in en_abstract["summary"]


def test_render_paper_lens_html_is_interactive_local_first_and_chinese():
    roadmap = _roadmap_with_target_paper()
    roadmap["paper_lens"] = build_paper_lens(roadmap, paper_lens_language="zh-CN", paper_lens_density="dense")
    roadmap["paper_lens"]["latex_export"] = {"compile_status": "compiled", "tex_file": "paper_lens.tex", "pdf_file": "paper_lens.pdf"}

    html = render_paper_lens_html(roadmap)

    assert "paper-lens-app" in html
    assert 'data-mode="quick"' in html
    data_match = re.search(r'<script type="application/json" id="paper-lens-data">(.*?)</script>', html, re.S)
    assert data_match
    assert "&quot;" not in data_match.group(1)
    assert json.loads(data_match.group(1))["storageKey"].startswith("fields-study-flow-paper-lens:")
    assert 'data-view-mode="quick"' in html
    assert 'data-view-mode="deep"' in html
    assert "data-view-mode-status" in html
    assert "data-deep-start" in html
    assert "setViewMode" in html
    assert "getAttribute('data-view-mode')" in html
    assert "document.addEventListener('click'" in html
    assert "setViewMode(button.getAttribute('data-view-mode') || 'quick', true);\n    applyFilters();\n  });\n  detailLinks" in html
    assert "cssEscape" in html
    assert "data-detail-link" in html
    assert "revealHashTarget" in html
    assert "hashchange" in html
    assert "target.closest('.deep-only')" in html
    assert "revealHashTarget(window.location.hash, true)" in html
    assert 'tabindex="-1"' in html
    assert "三分钟读懂" in html
    assert "关键句速读" in html
    assert "精读模式" in html
    assert "deep-only" in html
    assert "data-quick-overview" in html
    assert "data-lens-section" in html
    assert "data-lens-filter" in html
    assert "data-paper-segment" in html
    assert "data-explanation-card" in html
    assert "data-detail-anchor" in html
    assert "localStorage" in html
    assert "overflow-wrap:anywhere" in html
    assert "目标论文增强阅读器" in html
    assert "打开本地论文" in html
    assert "打开 PDF 精简版" in html
    assert "paper_lens.pdf" in html
    assert "paper_lens.tex" in html
    assert "这句话在说什么" in html
    assert "为什么重要" in html
    assert "方法怎么理解" in html
    assert "以上内容推荐阅读" in html
    assert "读完一组句段后" in html
    assert "接下来读什么" not in html
    assert "展开详解" in html
    assert "<strong>这句话在说什么</strong> 这句话在说什么" not in html
    assert "<strong>为什么重要</strong> 为什么重要" not in html
    assert "<strong>方法怎么理解</strong> 方法怎么理解" not in html
    detail_links = [match for match in re.findall(r'href="#([^"]+)"', html) if match.startswith("detail-")]
    detail_ids = set(re.findall(r'id="(detail-[^"]+)"', html))
    assert detail_links
    assert set(detail_links) <= detail_ids
    assert "../study-assets/01-teaching-llms-to-plan.pdf" in html
    assert "../study-assets/02-pddl-notes.html" in html
    assert "C:/" not in html
    assert "D:/" not in html


def test_write_paper_lens_latex_writes_source_without_requiring_compiler(tmp_path):
    roadmap = _roadmap_with_target_paper()
    roadmap["paper_lens"] = build_paper_lens(roadmap, paper_lens_language="zh-CN", paper_lens_density="key")

    export = write_paper_lens_latex(tmp_path, roadmap, compile_pdf=False)

    tex_path = tmp_path / "paper_lens.tex"
    assert export["tex_file"] == "paper_lens.tex"
    assert export["compile_status"] == "skipped"
    assert tex_path.exists()
    source = tex_path.read_text(encoding="utf-8")
    assert "\\documentclass" in source
    assert "三分钟读懂" in source
    assert "关键句速读" in source
    assert "以上内容推荐阅读" in source
    assert "C:/" not in source
    assert "D:/" not in source
