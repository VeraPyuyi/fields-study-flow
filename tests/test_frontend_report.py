from __future__ import annotations

import json
from pathlib import Path

from fields_study_flow import frontend_report
from fields_study_flow.frontend_report import copy_frontend_assets, render_evidence_coverage_markdown, render_frontend_report, render_mastery_worksheet_markdown, render_quick_brief_markdown, render_report_index, render_study_cards_markdown, render_study_quiz_markdown


def test_checked_in_frontend_dist_has_package_visible_manifest():
    manifest = frontend_report.FRONTEND_DIST_DIR / "manifest.json"

    assert manifest.exists()
    assert frontend_report.frontend_assets_available()
    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["index.html"]["file"].startswith("assets/")
    assert (frontend_report.FRONTEND_DIST_DIR / data["index.html"]["file"]).exists()
    for css_file in data["index.html"].get("css", []):
        assert css_file.startswith("assets/")
        assert (frontend_report.FRONTEND_DIST_DIR / css_file).exists()


def test_paper_map_mobile_canvas_keeps_readable_space_without_minimap_overlap():
    css = Path("frontend/src/styles.css").read_text(encoding="utf-8")

    assert "@media (max-width: 720px)" in css
    mobile_section = css.split("@media (max-width: 720px)", 1)[1]
    assert ".flow-shell" in mobile_section
    assert "min-height: 640px" in mobile_section
    assert ".whiteboard-minimap" in mobile_section
    assert "display: none" in mobile_section
    assert ".density-control" in mobile_section
    assert "max-width: calc(100vw - 42px)" in mobile_section


def test_checked_in_frontend_dist_references_existing_built_assets():
    manifest = json.loads((frontend_report.FRONTEND_DIST_DIR / "manifest.json").read_text(encoding="utf-8"))
    entry = manifest["index.html"]

    assert (frontend_report.FRONTEND_DIST_DIR / entry["file"]).exists()
    css_payloads = []
    for css_file in entry.get("css", []):
        css_path = frontend_report.FRONTEND_DIST_DIR / css_file
        assert css_path.exists()
        css_payloads.append(css_path.read_text(encoding="utf-8"))

    normalized_css = "".join(css_payloads).replace(" ", "")
    assert "@media(max-width:720px)" in normalized_css
    assert ".whiteboard-minimap{display:none}" in normalized_css


def test_frontend_report_shell_copies_assets_and_embeds_payload(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (assets / "app.js").write_text("console.log('ok')", encoding="utf-8")
    (assets / "app.css").write_text("body{color:#111}", encoding="utf-8")
    (dist / "manifest.json").write_text(
        json.dumps(
            {
                "index.html": {
                    "file": "assets/app.js",
                    "css": ["assets/app.css"],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("fields_study_flow.frontend_report.FRONTEND_DIST_DIR", dist)

    copied = copy_frontend_assets(tmp_path)
    html = render_frontend_report(
        "paper_lens",
        {"title": "Private", "secret": "C:/Users/example/private.pdf"},
        asset_base=copied,
    )

    assert copied == "assets/study-flow-app"
    assert (tmp_path / copied / "assets" / "app.js").exists()
    assert 'id="root"' in html
    assert 'data-report-kind="paper_lens"' in html
    assert "<style>body{color:#111}</style>" in html
    assert "<script>console.log('ok')</script>" in html
    assert 'src="assets/study-flow-app/assets/app.js"' not in html
    assert 'href="assets/study-flow-app/assets/app.css"' not in html
    payload = html.split('<script type="application/json" id="fields-study-flow-data">', 1)[1].split("</script>", 1)[0]
    data = json.loads(payload)
    assert data["reportKind"] == "paper_lens"
    assert "C:/Users/example" not in html


def test_frontend_report_shell_has_readable_no_script_fallback(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    assets = dist / "assets"
    assets.mkdir(parents=True)
    (assets / "app.js").write_text("throw new Error('asset failed')", encoding="utf-8")
    (assets / "app.css").write_text(".app{color:#111}", encoding="utf-8")
    (dist / "manifest.json").write_text(
        json.dumps({"index.html": {"file": "assets/app.js", "css": ["assets/app.css"]}}),
        encoding="utf-8",
    )
    monkeypatch.setattr("fields_study_flow.frontend_report.FRONTEND_DIST_DIR", dist)

    html = render_frontend_report(
        "paper_map",
        {
            "title": "Teaching LLMs to Plan",
            "profile": {"output_language": "zh-CN"},
            "paper_lens": {"segments": [{"id": "seg-1"}]},
        },
    )

    assert 'data-report-static-fallback="paper_map"' in html
    assert "<noscript>" in html
    assert "如果页面没有正常启动" in html
    assert "进入段落精读" in html
    assert "roadmap.html" in html
    assert "C:/Users/example" not in html


def test_report_index_prioritizes_learning_entries_and_redacts_private_paths():
    html = render_report_index(
        {
            "title": "Learning Roadmap: Teaching LLMs to Plan",
            "profile": {
                "goal": "Read C:/Users/example/private.pdf",
                "output_language": "zh-CN",
                "route_depth": "fastest",
            },
            "path_strategy": {
                "estimated_total_time": "2h 30m",
                "selected_resources": 6,
            },
            "paper_map": {"nodes": [{"id": "target"}]},
            "paper_lens": {"segments": [{"id": "seg-1"}]},
        }
    )

    assert "从这里开始" in html
    assert 'data-market-value-panel="true"' in html
    assert "为什么它不只是 PDF 总结器" in html
    assert "roadmap.sh / React Flow" in html
    assert "Explainpaper / PaperQA2" in html
    assert "NotebookLM / Elicit" in html
    assert "Get It" in html
    assert 'data-recommended-action-panel="true"' in html
    assert 'data-recommended-first-action="true" href="paper_map.html"' in html
    assert "推荐第一步" in html
    assert "第一步：打开论文逻辑图" in html
    assert "如果要汇报" in html
    assert "如果要掌握" in html
    assert "如果要换论文" in html
    assert 'data-learning-outcome-contract="true"' in html
    assert "学完后你应该能交付什么" in html
    assert 'data-outcome="explain"' in html
    assert 'data-outcome="derive"' in html
    assert 'data-outcome="reproduce"' in html
    assert 'data-outcome="critique"' in html
    assert "3 分钟讲明白论文主线" in html
    assert "留下最小复现实验记录" in html
    assert 'data-learning-guide-panel="starter-questions"' in html
    assert 'data-starter-question="paper-main-chain"' in html
    assert 'data-starter-question="paper-core-evidence"' in html
    assert 'data-starter-question="paper-mastery-proof"' in html
    assert "fields-study-flow ask --roadmap roadmap.json" in html
    assert 'data-active-recall-panel="five-minute-check"' in html
    assert 'data-recall-card="recall-main-chain"' in html
    assert 'data-recall-card="recall-method"' in html
    assert 'data-recall-card="recall-experiment"' in html
    assert 'data-recall-card="recall-limits"' in html
    assert 'data-first-session-plan="true"' in html
    assert 'data-session-step="session-paper-map"' in html
    assert 'data-session-step="session-paper-evidence"' in html
    assert 'data-session-step="session-recall"' in html
    assert 'data-session-step="session-mastery-task"' in html
    session_html = html.split('data-first-session-plan="true"', 1)[1].split("</section>", 1)[0]
    assert 'href="paper_map.html"' in session_html
    assert 'href="paper_lens.html"' in session_html
    assert 'href="roadmap.html"' in session_html
    assert session_html.index("paper_map.html") < session_html.index("paper_lens.html") < session_html.index("roadmap.html")
    assert "<details" in html
    assert "quickstart-panel" in html
    assert 'class="quickstart-panel fresh-user-flow-panel"' in html
    assert 'data-fresh-user-flow="first-10-minutes"' in html
    assert 'class="intent-router-panel"' in html
    assert 'data-intent-router="learning-goal"' in html
    assert "按你的目的选择入口" in html
    assert "我只想先看懂这篇" in html
    assert "我要能讲给别人听" in html
    assert "我要留下可检查结果" in html
    assert 'data-intent="quick-understand" href="paper_map.html"' in html
    assert 'data-intent="presentation-ready" href="paper_lens.html"' in html
    assert 'data-intent="mastery-proof" href="roadmap.html"' in html
    assert "10 分钟入门" in html
    assert "适合单篇论文" in html
    assert "先看主图" in html
    assert "再读关键段落" in html
    assert "最后做验收" in html
    assert html.index("paper_map.html") < html.index("paper_lens.html") < html.index("roadmap.html")
    assert "换成自己的论文" in html
    assert "fields-study-flow paper --url" in html
    assert "fields-study-flow paper --url ./my-paper.pdf" in html
    secondary_start = html.index('<details class="secondary-guidance-panel" data-secondary-guidance-panel="collapsed">')
    secondary_end = html.index("</details>", secondary_start) + len("</details>")
    secondary_html = html[secondary_start:secondary_end]
    outside_secondary = html[:secondary_start] + html[secondary_end:]
    for token in (
        'data-market-value-panel="true"',
        'data-learning-outcome-contract="true"',
        'data-learning-guide-panel="starter-questions"',
        'data-fresh-user-flow="first-10-minutes"',
        'data-intent-router="learning-goal"',
        'class="report-health-panel"',
        'class="scenario-panel"',
        'class="next-paper-panel"',
    ):
        assert token in secondary_html
        assert token not in outside_secondary
    assert '<details class="support-panel" data-support-files-panel="collapsed">' in html
    assert "需要原始数据或导出文件时再展开" in html
    assert "roadmap.json" in html
    assert "study_cards.md" in html
    assert "study_quiz.md" in html
    assert "mastery_worksheet.md" in html
    assert "quick_brief.md" in html
    assert "evidence_coverage.md" in html
    assert "C:/Users/example" not in html


def test_study_cards_markdown_reuses_active_recall_prompts():
    markdown = render_study_cards_markdown(
        {
            "profile": {"output_language": "en"},
            "paper_map": {"nodes": [{"id": "target"}]},
            "paper_lens": {"segments": [{"id": "seg-1"}]},
        }
    )

    assert "# Active Recall Study Cards" in markdown
    assert "Without the report, can you explain the paper's main chain in one sentence?" in markdown
    assert "[Find evidence](paper_map.html)" in markdown
    assert "Check:" in markdown
    assert "C:/Users/example" not in markdown


def test_study_quiz_markdown_reuses_cards_with_answer_key():
    markdown = render_study_quiz_markdown(
        {
            "profile": {"output_language": "en"},
            "paper_map": {"nodes": [{"id": "target"}]},
            "paper_lens": {"segments": [{"id": "seg-1"}]},
        }
    )

    assert "# Evidence-Linked Study Quiz" in markdown
    assert "Without the report, can you explain the paper's main chain in one sentence?" in markdown
    assert "## Answer Key" in markdown
    assert "[Evidence](paper_map.html)" in markdown
    assert "C:/Users/example" not in markdown


def test_mastery_worksheet_markdown_has_fillable_evidence_slots_and_links():
    markdown = render_mastery_worksheet_markdown(
        {
            "title": "Learning Roadmap: Transformer",
            "profile": {"goal": "master Transformer", "output_language": "en"},
            "mastery_evidence": {
                "final_artifact": "paper-mastery",
                "required_evidence": [
                    {
                        "task_id": "task-1-explain",
                        "task_type": "explain",
                        "title": "Explain the main chain",
                        "evidence": "A no-notes explanation.",
                        "pass_criteria": "Another learner can follow it.",
                        "resources": ["Attention Is All You Need"],
                        "estimated_minutes": 45,
                        "evidence_chunks": [
                            {
                                "resource_title": "Attention Is All You Need",
                                "snippet": "The Transformer is based solely on attention mechanisms.",
                                "detail_anchor": "paper_lens.html#detail-seg-1",
                            }
                        ],
                    }
                ],
            },
            "study_bundle": {
                "resources": [
                    {
                        "title": "Attention Is All You Need",
                        "local_href": "study-assets/attention.pdf",
                    }
                ]
            },
        }
    )

    assert "# Learning Roadmap: Transformer - Mastery Evidence Worksheet" in markdown
    assert "## Evidence Slots" in markdown
    assert "[Paper Map](paper_map.html)" in markdown
    assert "[Attention Is All You Need](study-assets/attention.pdf)" in markdown
    assert "[Attention Is All You Need](paper_lens.html#detail-seg-1)" in markdown
    assert "**My Evidence**" in markdown
    assert "C:/Users/example" not in markdown


def test_quick_brief_markdown_summarizes_paper_logic_and_evidence():
    markdown = render_quick_brief_markdown(
        {
            "title": "Learning Roadmap: Transformer",
            "profile": {"goal": "master Transformer", "output_language": "en"},
            "paper_map": {
                "nodes": [
                    {
                        "id": "problem",
                        "role": "core",
                        "kind": "problem",
                        "label": "Sequence modeling bottleneck",
                        "plain_explanation": "The paper targets sequence modeling without recurrent bottlenecks.",
                        "talking_point": "It asks whether attention alone can replace recurrence.",
                        "evidence": [
                            {
                                "source_title": "Attention Is All You Need",
                                "snippet": "The Transformer is based solely on attention mechanisms.",
                                "detail_anchor": "paper_lens.html#detail-seg-1",
                            }
                        ],
                    },
                    {
                        "id": "methodology",
                        "role": "core",
                        "kind": "methodology",
                        "plain_explanation": "The method uses self-attention and feed-forward layers.",
                    },
                    {
                        "id": "contribution",
                        "role": "core",
                        "kind": "contribution",
                        "plain_explanation": "It shows attention-only models can be strong and parallelizable.",
                    },
                ]
            },
            "next_actions": [{"title": "Explain the main chain", "estimated_minutes": 30, "evidence": "No-notes explanation."}],
            "study_bundle": {
                "resources": [
                    {
                        "title": "Attention Is All You Need",
                        "local_href": "study-assets/attention.pdf",
                        "selected": True,
                        "why_recommended": "Target paper.",
                    }
                ]
            },
        }
    )

    assert "# Learning Roadmap: Transformer - 5-Minute Research Brief" in markdown
    assert "## One-Sentence Takeaway" in markdown
    assert "## Paper Logic Chain" in markdown
    assert "[Attention Is All You Need](paper_lens.html#detail-seg-1)" in markdown
    assert "[Attention Is All You Need](study-assets/attention.pdf)" in markdown
    assert "study_quiz.md" in markdown
    assert "C:/Users/example" not in markdown


def test_quick_brief_field_route_uses_roadmap_start_without_paper_only_links():
    markdown = render_quick_brief_markdown(
        {
            "title": "Learning Roadmap: Diffusion Models",
            "profile": {"goal": "learn diffusion models", "output_language": "en", "target_kind": "field"},
            "phases": [{"name": "Core Concepts", "objective": "Understand denoising score matching and sampling."}],
            "study_bundle": {
                "resources": [
                    {
                        "title": "Diffusion Tutorial",
                        "href": "https://example.com/diffusion",
                        "selected": True,
                        "why_recommended": "Best compact overview.",
                    }
                ]
            },
        }
    )

    assert "[Roadmap](roadmap.html)" in markdown
    assert "paper_map.html" not in markdown
    assert "paper_lens.html" not in markdown
    assert "## Route at a Glance" in markdown
    assert markdown.count("Open These Resources First") == 1
    assert "[Diffusion Tutorial](https://example.com/diffusion)" in markdown


def test_evidence_coverage_markdown_tracks_claims_tasks_resources_and_redacts_paths():
    markdown = render_evidence_coverage_markdown(
        {
            "title": "Learning Roadmap: Transformer",
            "profile": {"goal": "master Transformer", "output_language": "en"},
            "paper_map": {
                "nodes": [
                    {
                        "id": "problem",
                        "role": "core",
                        "kind": "problem",
                        "label": "Problem",
                        "plain_explanation": "The paper removes recurrent bottlenecks.",
                        "evidence": [{"source_title": "Attention", "snippet": "attention only", "detail_anchor": "paper_lens.html#detail-1"}],
                    },
                    {
                        "id": "limitation",
                        "role": "core",
                        "kind": "limitation",
                        "label": "Limitation",
                        "plain_explanation": "Needs more evidence from C:/Users/example/private.pdf.",
                    },
                ]
            },
            "paper_lens": {
                "segments": [{"id": "seg-1", "section_kind": "method", "original_text": "Self-attention paragraph."}],
                "inline_explanations": [{"segment_id": "seg-1", "plain_meaning": "Explains the method.", "evidence_refs": ["paper_lens.html#detail-1"]}],
            },
            "study_tasks": [{"type": "explain", "title": "Explain the chain", "resource_titles": ["Attention Is All You Need"], "evidence": "No-notes explanation."}],
            "study_bundle": {
                "resources": [
                    {
                        "title": "Attention Is All You Need",
                        "local_href": "study-assets/attention.pdf",
                        "selected": True,
                        "metadata": {"rag": {"evidence_chunks": [{"snippet": "Transformer uses attention.", "file_name": "attention.pdf"}]}},
                    }
                ]
            },
        }
    )

    assert "# Learning Roadmap: Transformer - Evidence Coverage Matrix" in markdown
    assert "## Coverage Summary" in markdown
    assert "## Paper Logic Coverage" in markdown
    assert "## Reading Paragraph Coverage" in markdown
    assert "## Mastery Task Coverage" in markdown
    assert "## Resource Evidence Coverage" in markdown
    assert "[Problem](paper_lens.html#detail-1)" in markdown
    assert "[Attention Is All You Need](study-assets/attention.pdf)" in markdown
    assert "needs evidence" in markdown
    assert "C:/Users/example/private" not in markdown


def test_evidence_coverage_field_route_uses_roadmap_links_without_paper_pages():
    markdown = render_evidence_coverage_markdown(
        {
            "title": "Learning Roadmap: Diffusion Models",
            "profile": {"goal": "learn diffusion models", "output_language": "en", "target_kind": "field"},
            "study_tasks": [{"type": "explain", "title": "Explain diffusion", "resource_titles": ["Diffusion Tutorial"]}],
            "study_bundle": {"resources": [{"title": "Diffusion Tutorial", "href": "https://example.com/diffusion", "selected": True}]},
        }
    )

    assert "paper_map.html" not in markdown
    assert "paper_lens.html" not in markdown
    assert "roadmap.html#mastery-checklist-title" in markdown
    assert "[Diffusion Tutorial](https://example.com/diffusion)" in markdown


def test_report_index_starter_questions_fall_back_for_field_routes():
    html = render_report_index(
        {
            "title": "Diffusion field route",
            "profile": {"goal": "learn diffusion models", "output_language": "en", "target_kind": "field"},
            "path_strategy": {"estimated_total_time": "6h", "selected_resources": 5},
            "phases": [{"name": "Prerequisites"}],
        }
    )

    assert 'data-learning-guide-panel="starter-questions"' in html
    assert 'data-starter-question="route-prerequisites"' in html
    assert 'data-starter-question="route-resource-priority"' in html
    assert 'data-starter-question="route-final-artifact"' in html
    assert 'data-active-recall-panel="five-minute-check"' in html
    assert 'data-recall-card="recall-prereq"' in html
    assert 'data-recall-card="recall-core-concept"' in html
    assert 'data-recall-card="recall-resource"' in html
    assert 'data-recall-card="recall-artifact"' in html
    assert 'data-first-session-plan="true"' in html
    assert 'data-session-step="session-prereq-scan"' in html
    assert 'data-session-step="session-core-resource"' in html
    assert 'data-session-step="session-route-recall"' in html
    assert 'data-session-step="session-route-artifact"' in html
    assert "3 starter questions" in html
    assert "5-minute active recall" in html
    assert "fields-study-flow ask --roadmap roadmap.json" in html
    session_html = html.split('data-first-session-plan="true"', 1)[1].split("</section>", 1)[0]
    assert "paper_lens.html" not in session_html


def test_report_index_field_routes_ignore_incidental_paper_lens_for_first_session():
    html = render_report_index(
        {
            "title": "Diffusion field route",
            "profile": {"goal": "learn diffusion models", "output_language": "en", "target_kind": "field"},
            "path_strategy": {"estimated_total_time": "6h", "selected_resources": 5},
            "paper_lens": {"segments": [{"id": "seg-1"}]},
            "phases": [{"name": "Prerequisites"}],
        }
    )

    session_html = html.split('data-first-session-plan="true"', 1)[1].split("</section>", 1)[0]
    assert 'data-session-step="session-prereq-scan"' in session_html
    assert 'data-session-step="session-core-resource"' in session_html
    assert 'data-session-step="session-route-recall"' in session_html
    assert 'data-session-step="session-route-artifact"' in session_html
    assert "paper_lens.html" not in session_html


def test_report_index_surfaces_quality_health_status_for_new_users():
    html = render_report_index(
        {
            "title": "Teaching LLMs to Plan",
            "profile": {"goal": "理解论文", "output_language": "zh-CN"},
            "path_strategy": {"estimated_total_time": "3h", "selected_resources": 4},
            "paper_map": {"nodes": [{"id": "target"}]},
            "paper_lens": {
                "segments": [{"id": "seg-1"}],
                "inline_explanations": [{"evidence_refs": [{"snippet": "method evidence"}]}],
            },
            "knowledge_graph": {"summary": {"edges": 8, "evidence_backed_edges": 5}},
            "study_bundle": {
                "resources": [
                    {"title": "Target paper", "status": "downloaded", "local_href": "assets/paper.pdf"},
                    {"title": "Notes", "status": "snapshotted", "local_href": "assets/notes.html"},
                    {"title": "Checklist", "status": "generated", "local_href": "artifact_template/README.md"},
                    {"title": "Repository", "status": "link-only"},
                ]
            },
            "resource_library": [
                {
                    "title": "Target paper",
                    "metadata": {"rag": {"evidence_chunks": [{"snippet": "target-paper evidence"}]}},
                }
            ],
        }
    )

    assert 'class="report-health-panel"' in html
    assert "报告健康状态" in html
    assert "本地资料" in html
    assert "3/4" in html
    assert "证据覆盖" in html
    assert "5 条边" in html
    assert "隐私已脱敏" in html
    assert "排版安全" in html
    assert "report_audit.json" in html


def test_report_index_counts_only_traceable_evidence_chunks():
    html = render_report_index(
        {
            "title": "Teaching LLMs to Plan",
            "profile": {"goal": "理解论文", "output_language": "zh-CN"},
            "path_strategy": {"estimated_total_time": "3h", "selected_resources": 2},
            "study_bundle": {
                "resources": [
                    {
                        "title": "Target paper",
                        "status": "downloaded",
                        "local_href": "assets/paper.pdf",
                        "metadata": {"rag": {"evidence_chunks": [None, {}, "", {"snippet": "method evidence"}]}},
                    }
                ]
            },
        }
    )

    assert "证据覆盖" in html
    assert "1 条片段" in html


def test_report_index_marks_evidence_coverage_pending_when_no_traceable_chunks():
    html = render_report_index(
        {
            "title": "Teaching LLMs to Plan",
            "profile": {"goal": "理解论文", "output_language": "zh-CN"},
            "path_strategy": {"estimated_total_time": "3h", "selected_resources": 1},
            "study_bundle": {
                "resources": [
                    {
                        "title": "Placeholder",
                        "status": "link-only",
                        "metadata": {"rag": {"evidence_chunks": [None, {}, ""]}},
                    }
                ]
            },
        }
    )

    assert "证据覆盖" in html
    assert "未发现可追溯证据片段" in html


def test_report_index_explains_three_core_learning_scenarios():
    html = render_report_index(
        {
            "title": "Teaching LLMs to Plan",
            "profile": {"goal": "理解论文", "output_language": "zh-CN"},
            "path_strategy": {"estimated_total_time": "3h", "selected_resources": 4},
            "paper_map": {"nodes": [{"id": "target"}]},
            "paper_lens": {"segments": [{"id": "seg-1"}]},
        }
    )

    assert 'class="scenario-panel"' in html
    assert "支持三种学习场景" in html
    assert "单篇论文" in html
    assert "多篇论文 / 文献组" in html
    assert "领域 / 课程路线" in html
    assert "fields-study-flow paper --url ./paper.pdf" in html
    assert "fields-study-flow roadmap --goal" in html
