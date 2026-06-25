from __future__ import annotations

import json

from fields_study_flow import frontend_report
from fields_study_flow.frontend_report import copy_frontend_assets, render_frontend_report, render_report_index


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
    assert "roadmap.json" in html
    assert "C:/Users/example" not in html


def test_report_index_surfaces_quality_health_status_for_new_users():
    html = render_report_index(
        {
            "title": "Teaching LLMs to Plan",
            "profile": {"goal": "理解论文", "output_language": "zh-CN"},
            "path_strategy": {"estimated_total_time": "3h", "selected_resources": 4},
            "paper_map": {"nodes": [{"id": "target"}]},
            "paper_lens": {"segments": [{"id": "seg-1"}]},
            "study_bundle": {
                "resources": [
                    {"title": "Target paper", "status": "downloaded", "local_href": "assets/paper.pdf"},
                    {"title": "Notes", "status": "snapshotted", "local_href": "assets/notes.html"},
                    {"title": "Checklist", "status": "generated", "local_href": "artifact_template/README.md"},
                    {"title": "Repository", "status": "link-only"},
                ]
            },
        }
    )

    assert 'class="report-health-panel"' in html
    assert "报告健康状态" in html
    assert "本地资料" in html
    assert "3/4" in html
    assert "隐私已脱敏" in html
    assert "排版安全" in html
    assert "report_audit.json" in html


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
