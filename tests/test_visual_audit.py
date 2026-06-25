import json
import subprocess
import sys

import pytest

from fields_study_flow import visual_audit
from fields_study_flow.visual_audit import (
    audit_report_directory,
    build_report_audit,
    capture_browser_snapshots,
    compare_browser_snapshot_baseline,
    evaluate_market_sample_matrix,
    evaluate_fresh_user_timing,
    probe_browser_interactions,
    summarize_fresh_user_backlogs,
    summarize_fresh_user_worksheets,
    write_release_readiness_report,
    write_fresh_user_backlog,
    write_fresh_user_trend_report,
    write_fresh_user_worksheet,
)


def test_audit_report_directory_passes_complete_offline_report(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        '<body><h1>从这里开始</h1><section data-market-value-panel="true">为什么它不只是 PDF 总结器</section>'
        '<section>10 分钟入门 适合单篇论文</section><section>换成自己的论文</section></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "paper_map.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>.map-node{font-family:Arial;overflow-wrap:anywhere;max-width:100%}</style></head>"
        '<body><div data-report-kind="paper_map">阅读密度 速览主链 完整探索</div></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "paper_lens.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>.paragraph-card{font-family:Arial;overflow-wrap:anywhere;max-width:100%}</style></head>"
        '<body><div data-report-kind="paper_lens">段落精读 证据置信度</div></body></html>',
        encoding="utf-8",
    )
    (tmp_path / "roadmap.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>.resource-row{font-family:Arial;overflow-wrap:anywhere;max-width:100%}</style></head>"
        '<body><div data-report-kind="roadmap">学习中控台 掌握验收</div></body></html>',
        encoding="utf-8",
    )

    audit = audit_report_directory(tmp_path)

    assert audit["status"] == "pass"
    assert audit["summary"]["checked_files"] == 4
    assert audit["summary"]["failed_checks"] == 0


def test_audit_report_directory_flags_visual_risks_and_private_paths(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><body><h1>从这里开始</h1><p>C:/Users/example/private.pdf</p></body></html>',
        encoding="utf-8",
    )

    audit = audit_report_directory(tmp_path)

    assert audit["status"] == "fail"
    failed = {(item["file"], item["check"]) for item in audit["checks"] if item["status"] == "fail"}
    assert ("index.html", "responsive_viewport") in failed
    assert ("index.html", "wrap_safeguard") in failed
    assert ("index.html", "private_path_redaction") in failed


def test_audit_report_directory_flags_visible_mojibake(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body><h1>���￪ʼ</h1><p>10 分钟入门</p></body></html>",
        encoding="utf-8",
    )

    audit = audit_report_directory(tmp_path)

    failed = {(item["file"], item["check"]) for item in audit["checks"] if item["status"] == "fail"}
    assert audit["status"] == "fail"
    assert ("index.html", "encoding_integrity") in failed


def test_audit_report_directory_flags_visible_decorative_ellipsis(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body><h1>Start Here...</h1><p>Long clipped summary…</p>"
        "<script>const spread = (...args) => args.length;</script></body></html>",
        encoding="utf-8",
    )

    audit = audit_report_directory(tmp_path)

    failed = {(item["file"], item["check"]) for item in audit["checks"] if item["status"] == "fail"}
    assert audit["status"] == "fail"
    assert ("index.html", "visible_decorative_ellipsis") in failed


def test_audit_report_directory_flags_decorative_ellipsis_in_react_payload(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer"
        '<script type="application/json" id="fields-study-flow-data">'
        '{"roadmap":{"title":"A clipped title...","summary":"A clipped summary…"}}'
        "</script></body></html>",
        encoding="utf-8",
    )

    audit = audit_report_directory(tmp_path)

    failed = {(item["file"], item["check"]) for item in audit["checks"] if item["status"] == "fail"}
    assert audit["status"] == "fail"
    assert ("index.html", "payload_decorative_ellipsis") in failed


def test_audit_report_directory_does_not_echo_internal_marker_terms(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )

    audit = audit_report_directory(tmp_path)

    messages = [str(item["message"]) for item in audit["checks"]]
    assert all("Expected one of:" not in message for message in messages)


def test_cli_audit_report_outputs_json(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        '<body>从这里开始 10 分钟入门 <section data-market-value-panel="true">为什么它不只是 PDF 总结器</section> 换成自己的论文</body></html>',
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "fields_study_flow.cli", "audit-report", "--report-dir", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["status"] == "pass"
    assert data["summary"]["checked_files"] == 1


def test_cli_audit_report_refreshes_report_audit_json_when_roadmap_exists(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "roadmap.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>learning console mastery checklist</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "roadmap.json").write_text(
        json.dumps({"profile": {"output_language": "en"}, "study_tasks": []}),
        encoding="utf-8",
    )
    (tmp_path / "report_audit.json").write_text(
        json.dumps({"stale": True}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, "-m", "fields_study_flow.cli", "audit-report", "--report-dir", str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    refreshed = json.loads((tmp_path / "report_audit.json").read_text(encoding="utf-8"))
    assert "stale" not in refreshed
    assert "competitive_benchmark" in refreshed
    assert refreshed["recommended_first_action"]["href"] == "roadmap.html"


def test_evaluate_fresh_user_timing_measures_time_to_first_mastery_task():
    fast = evaluate_fresh_user_timing(7.5, target_minutes=10)
    slow = evaluate_fresh_user_timing(12.25, target_minutes=10)

    assert fast["status"] == "pass"
    assert fast["summary"]["measured_minutes"] == 7.5
    assert fast["summary"]["target_minutes"] == 10
    assert fast["summary"]["minutes_saved"] == 2.5
    assert slow["status"] == "fail"
    assert slow["summary"]["minutes_over_target"] == 2.25
    assert any(item["id"] == "first_mastery_within_target" and item["status"] == "fail" for item in slow["checks"])


def test_evaluate_fresh_user_timing_rejects_non_positive_or_non_finite_values():
    for measured, target in [(-1, 10), (0, 10), (float("nan"), 10), (8, 0), (8, float("inf"))]:
        with pytest.raises(ValueError, match="positive finite"):
            evaluate_fresh_user_timing(measured, target_minutes=target)


def test_write_fresh_user_worksheet_creates_actionable_markdown(tmp_path):
    result = write_fresh_user_worksheet(tmp_path, target_minutes=10)

    assert result["status"] == "pass"
    assert result["summary"]["path"] == "fresh_user_test.md"
    worksheet = tmp_path / "fresh_user_test.md"
    assert worksheet.exists()
    text = worksheet.read_text(encoding="utf-8")
    assert "Fresh User Test Worksheet" in text
    assert "Target: reach the first mastery task within 10 minutes" in text
    assert "Open `index.html`" in text
    assert "Open `paper_map.html`" in text
    assert "Open `paper_lens.html`" in text
    assert "Blocker / confusion" in text
    assert str(tmp_path) not in text


def test_cli_audit_report_writes_fresh_user_worksheet(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--write-fresh-user-worksheet",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["fresh_user_worksheet"]["status"] == "pass"
    assert data["fresh_user_worksheet"]["summary"]["path"] == "fresh_user_test.md"
    assert (tmp_path / "fresh_user_test.md").exists()


def test_summarize_fresh_user_worksheets_ranks_repeated_blockers(tmp_path):
    first = tmp_path / "first.md"
    first.write_text(
        "\n".join(
            [
                "| Step | Expected action | Time | Blocker / confusion | Product fix idea |",
                "| --- | --- | --- | --- | --- |",
                "| 2 | Identify the recommended first action | 2:10 | Could not find first action | Rename the start card |",
                "| 3 | Open `paper_map.html` | 4:05 | Paper Map looked too small | Enlarge canvas by default |",
            ]
        ),
        encoding="utf-8",
    )
    second = tmp_path / "second.md"
    second.write_text(
        "\n".join(
            [
                "| Step | Expected action | Time | Blocker / confusion | Product fix idea |",
                "| --- | --- | --- | --- | --- |",
                "| 2 | Identify the recommended first action | 1:40 | could not find first action | Put the first action above the fold |",
            ]
        ),
        encoding="utf-8",
    )

    result = summarize_fresh_user_worksheets([first, second])

    assert result["status"] == "pass"
    assert result["summary"]["worksheets"] == 2
    assert result["summary"]["blockers"] == 3
    assert result["summary"]["unique_blockers"] == 2
    top = result["backlog"][0]
    assert top["blocker"] == "Could not find first action"
    assert top["occurrences"] == 2
    assert top["steps"] == ["2"]
    assert "Rename the start card" in top["fix_ideas"]
    assert "Put the first action above the fold" in top["fix_ideas"]


def test_write_fresh_user_backlog_creates_ranked_markdown_without_private_paths(tmp_path):
    worksheet = tmp_path / "fresh_user_test.md"
    worksheet.write_text(
        "\n".join(
            [
                "| Step | Expected action | Time | Blocker / confusion | Product fix idea |",
                "| --- | --- | --- | --- | --- |",
                "| 6 | Open one local resource | 6:30 | Could not open D:\\secret\\paper.pdf | Show local resource button earlier |",
            ]
        ),
        encoding="utf-8",
    )

    result = write_fresh_user_backlog([worksheet], tmp_path)

    assert result["status"] == "pass"
    assert result["summary"]["path"] == "fresh_user_backlog.md"
    backlog = tmp_path / "fresh_user_backlog.md"
    assert backlog.exists()
    text = backlog.read_text(encoding="utf-8")
    assert "Fresh User Backlog" in text
    assert "[private path]" in text
    assert "D:\\secret" not in text
    assert str(tmp_path) not in text


def test_cli_audit_report_writes_fresh_user_backlog_from_inputs(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )
    worksheet = tmp_path / "fresh_user_test.md"
    worksheet.write_text(
        "\n".join(
            [
                "| Step | Expected action | Time | Blocker / confusion | Product fix idea |",
                "| --- | --- | --- | --- | --- |",
                "| 4 | Explain the main logic chain | 5:20 | Main chain wording was unclear | Add plainer labels |",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--fresh-user-worksheet-input",
            str(worksheet),
            "--write-fresh-user-backlog",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["fresh_user_backlog"]["status"] == "pass"
    assert data["fresh_user_backlog"]["summary"]["path"] == "fresh_user_backlog.md"
    assert (tmp_path / "fresh_user_backlog.md").exists()


def test_summarize_fresh_user_backlogs_tracks_recurring_blockers_across_reports(tmp_path):
    first = tmp_path / "release-1.md"
    first.write_text(
        "\n".join(
            [
                "| Rank | Occurrences | Steps | Blocker | Fix ideas |",
                "| --- | ---: | --- | --- | --- |",
                "| 1 | 2 | 2 | Could not find first action | Move first action above the fold |",
                "| 2 | 1 | 3 | Paper Map looked too small | Increase default zoom |",
            ]
        ),
        encoding="utf-8",
    )
    second = tmp_path / "release-2.md"
    second.write_text(
        "\n".join(
            [
                "| Rank | Occurrences | Steps | Blocker | Fix ideas |",
                "| --- | ---: | --- | --- | --- |",
                "| 1 | 1 | 2 | could not find first action | Rename start card |",
            ]
        ),
        encoding="utf-8",
    )

    result = summarize_fresh_user_backlogs([first, second])

    assert result["status"] == "pass"
    assert result["summary"]["backlog_files"] == 2
    assert result["summary"]["unique_blockers"] == 2
    assert result["summary"]["recurring_blockers"] == 1
    top = result["trends"][0]
    assert top["blocker"] == "Could not find first action"
    assert top["total_occurrences"] == 3
    assert top["reports"] == 2
    assert top["trend"] == "recurring"
    assert "Move first action above the fold" in top["fix_ideas"]
    assert "Rename start card" in top["fix_ideas"]


def test_write_fresh_user_trend_report_redacts_private_paths(tmp_path):
    backlog = tmp_path / "fresh_user_backlog.md"
    backlog.write_text(
        "\n".join(
            [
                "| Rank | Occurrences | Steps | Blocker | Fix ideas |",
                "| --- | ---: | --- | --- | --- |",
                "| 1 | 1 | 6 | Could not open C:\\private\\paper.pdf | Add a local file button |",
            ]
        ),
        encoding="utf-8",
    )

    result = write_fresh_user_trend_report([backlog], tmp_path)

    assert result["status"] == "pass"
    assert result["summary"]["path"] == "fresh_user_trends.md"
    trends = tmp_path / "fresh_user_trends.md"
    assert trends.exists()
    text = trends.read_text(encoding="utf-8")
    assert "Fresh User Trend Report" in text
    assert "[private path]" in text
    assert "C:\\private" not in text
    assert str(tmp_path) not in text


def test_cli_audit_report_writes_fresh_user_trend_report(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )
    backlog = tmp_path / "fresh_user_backlog.md"
    backlog.write_text(
        "\n".join(
            [
                "| Rank | Occurrences | Steps | Blocker | Fix ideas |",
                "| --- | ---: | --- | --- | --- |",
                "| 1 | 2 | 4 | Main chain wording was unclear | Add plainer labels |",
            ]
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--fresh-user-backlog-input",
            str(backlog),
            "--write-fresh-user-trend-report",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["fresh_user_trend_report"]["status"] == "pass"
    assert data["fresh_user_trend_report"]["summary"]["path"] == "fresh_user_trends.md"
    assert (tmp_path / "fresh_user_trends.md").exists()


def _write_market_sample(path, roadmap, *, market_status="market_ready", benchmark_status="pass"):
    path.mkdir()
    (path / "roadmap.json").write_text(json.dumps(roadmap), encoding="utf-8")
    (path / "report_audit.json").write_text(
        json.dumps(
            {
                "status": "pass",
                "visual_audit": {"status": "pass"},
                "market_readiness": {"status": market_status, "score": 96 if market_status == "market_ready" else 72},
                "competitive_benchmark": {"status": benchmark_status, "checks": []},
            }
        ),
        encoding="utf-8",
    )


def test_evaluate_market_sample_matrix_requires_cross_scenario_evidence(tmp_path):
    single = tmp_path / "single-paper"
    field = tmp_path / "field-course"
    paper_set = tmp_path / "paper-set"
    _write_market_sample(single, {"profile": {"target_kind": "paper"}, "paper_map": {"nodes": []}, "paper_lens": {"segments": []}})
    _write_market_sample(field, {"profile": {"target_kind": "field"}, "phases": [{"name": "Core"}]})

    partial = evaluate_market_sample_matrix([single, field])

    assert partial["status"] == "warn"
    assert partial["summary"]["covered_scenarios"] == ["single-paper", "field-course"]
    assert partial["summary"]["missing_scenarios"] == ["paper-set"]
    assert any(item["id"] == "scenario_coverage:paper-set" and item["status"] == "warn" for item in partial["checks"])

    _write_market_sample(paper_set, {"profile": {"target_kind": "paper-set"}, "paper_set": {"papers": [{"title": "A"}, {"title": "B"}]}})
    complete = evaluate_market_sample_matrix([single, field, paper_set])

    assert complete["status"] == "pass"
    assert complete["summary"]["missing_scenarios"] == []


def test_write_release_readiness_report_uses_market_sample_matrix(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body><main><h1>Start Here</h1></main></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "report_audit.json").write_text(
        json.dumps({"market_readiness": {"status": "market_ready", "score": 96, "dimensions": []}, "competitive_benchmark": {"status": "pass", "checks": []}}),
        encoding="utf-8",
    )
    matrix = {
        "status": "warn",
        "summary": {
            "covered_scenarios": ["single-paper", "field-course"],
            "missing_scenarios": ["paper-set"],
        },
    }

    result = write_release_readiness_report(
        tmp_path,
        {
            "status": "pass",
            "fresh_user_timing": {"status": "pass", "summary": {"minutes": 8.25, "target_minutes": 10}},
            "browser_snapshot_capture": {"status": "pass", "summary": {"mode": "browser-backed", "checked_files": 3}},
            "browser_interaction_probe": {"status": "pass", "summary": {"mode": "browser-interaction", "pages": 3, "failed_checks": 0}},
            "market_sample_matrix": matrix,
        },
    )

    assert result["status"] == "warn"
    assert result["summary"]["decision"] == "needs_work"
    assert result["summary"]["market_sample_matrix_status"] == "warn"
    assert any(item["competitor"] == "PaperQA2 / scientific RAG" for item in result["summary"]["market_positioning"])
    scorecard = result["summary"]["market_experience_scorecard"]
    scorecard_ids = {item["id"] for item in scorecard}
    assert {"ui_interface", "content_depth", "plain_clarity", "first_run_ease", "evidence_trust", "resource_completeness", "portable_outputs"} <= scorecard_ids
    assert all(item.get("score") is not None and item.get("next_improvement") for item in scorecard)
    backlog = result["summary"]["market_opportunity_backlog"]
    assert len(backlog) == len(result["summary"]["market_positioning"])
    assert all(item.get("priority") and item.get("theme") and item.get("competitor") and item.get("action") and item.get("release_proof") for item in backlog)
    assert any(item["priority"] == "P0" and item["theme"] == "Evidence-backed Paper Map" for item in backlog)
    roadmap_item = next(item for item in backlog if item["theme"] == "Cross-scenario route proof")
    assert roadmap_item["priority"] == "P0"
    assert "single-paper, paper-set, and field/course" in roadmap_item["release_proof"]
    assert any("paper-set" in action for action in result["summary"]["next_actions"])
    text = (tmp_path / "release_readiness.md").read_text(encoding="utf-8")
    html = (tmp_path / "release_readiness.html").read_text(encoding="utf-8")
    assert "Market Positioning Matrix" in text
    assert "Market Experience Scorecard" in text
    assert "UI/interface polish" in text
    assert "First-run ease" in text
    assert "Market Opportunity Backlog" in text
    assert "not measured" in text
    assert "Prove every core Paper Map and mastery task" in text
    assert "PaperQA2 / scientific RAG" in text
    assert "Get It / measurable mastery map" in text
    assert "data-market-positioning" in html
    assert "data-market-experience-scorecard" in html
    assert "市场体验评分卡" in html
    assert "data-market-opportunity-backlog" in html
    assert "Evidence-backed Paper Map" in html
    assert "市场机会待办" in html
    assert "Current evidence" in html
    assert "Market Positioning Matrix" in html
    assert "Elicit / systematic review AI" in html
    assert "Market Sample Matrix" in text
    assert "paper-set" in text
    assert "Market Sample Matrix" in html
    assert "市场样本矩阵" in html


def test_write_release_readiness_report_combines_market_audit_and_fresh_user_trends(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body><main><h1>Start Here</h1></main></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "report_audit.json").write_text(
        json.dumps(
            {
                "market_readiness": {
                    "status": "needs_improvement",
                    "score": 82,
                    "dimensions": [
                        {"id": "visual_polish", "label": "Visual polish", "score": 78},
                        {"id": "learning_depth", "label": "Learning depth", "score": 90},
                        {"id": "actionability", "label": "Actionability", "score": 88},
                    ],
                    "next_best_actions": [
                        {"dimension": "visual_polish", "action": "Fix crowded Paper Map spacing."},
                    ],
                },
                "competitive_benchmark": {
                    "status": "warn",
                    "checks": [
                        {
                            "id": "xyflow_canvas_affordance",
                            "status": "warn",
                            "label": "Canvas interaction",
                            "fix": "Make drag and zoom controls more obvious.",
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )
    audit_result = {
        "status": "pass",
        "summary": {"checked_files": 4, "checks": 42, "failed_checks": 0},
        "fresh_user_timing": {"status": "pass", "summary": {"minutes": 7.5, "target_minutes": 10}},
        "fresh_user_trend_report": {
            "status": "warn",
            "summary": {"recurring_blockers": 1},
            "trends": [
                {
                    "blocker": "Users could not find C:\\private\\paper.pdf or \\\\server\\share\\paper.pdf",
                    "total_occurrences": 3,
                    "reports": 2,
                    "fix_ideas": ["Add local file entry"],
                }
            ],
        },
    }

    result = write_release_readiness_report(tmp_path, audit_result)

    assert result["status"] == "warn"
    assert result["summary"]["path"] == "release_readiness.md"
    assert result["summary"]["html_path"] == "release_readiness.html"
    assert result["summary"]["decision"] == "needs_work"
    assert any(item["id"] == "content_depth" and item["score"] >= 80 for item in result["summary"]["market_experience_scorecard"])
    assert any(item["theme"] == "Canvas interaction proof" for item in result["summary"]["market_opportunity_backlog"])
    text = (tmp_path / "release_readiness.md").read_text(encoding="utf-8")
    html = (tmp_path / "release_readiness.html").read_text(encoding="utf-8")
    assert "Release Readiness Dashboard" in text
    assert "Decision: needs_work" in text
    assert "Elicit/SciSpace evidence transparency" in text
    assert "ResearchRabbit/roadmap.sh visual navigation" in text
    assert "React Flow canvas affordance" in text
    assert "Market Experience Scorecard" in text
    assert "Evidence trust" in text
    assert "Market Opportunity Backlog" in text
    assert "Canvas interaction proof" in text
    assert "actionability: 88" in text
    assert "Fix crowded Paper Map spacing." in text
    assert "[private path]" in text
    assert "C:\\private" not in text
    assert "\\\\server\\share" not in text
    assert '<main class="release-readiness"' in html
    assert 'data-release-decision="needs_work"' in html
    assert "中文友好" in html
    assert "发布决策" in html
    assert "overflow-wrap:anywhere" in html
    assert "Microsoft YaHei UI" in html
    assert "Elicit/SciSpace evidence transparency" in html
    assert "data-market-experience-scorecard" in html
    assert "Evidence trust" in html
    assert "data-market-opportunity-backlog" in html
    assert "Canvas interaction proof" in html
    assert "[private path]" in html
    assert "C:\\private" not in html
    assert "\\\\server\\share" not in html
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'data-release-readiness-entry="true"' in index
    assert 'href="release_readiness.html"' in index
    assert "Release decision" in index


def test_write_release_readiness_report_does_not_duplicate_index_entry(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width"></head>'
        "<body><main><h1>Start Here</h1></main></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "report_audit.json").write_text(
        json.dumps(
            {
                "market_readiness": {
                    "status": "market_ready",
                    "score": 96,
                    "dimensions": [],
                    "next_best_actions": [
                        {
                            "dimension": "visual_polish",
                            "action": "Optionally run browser-backed screenshot capture to validate the static visual snapshot matrix against real rendered pixels.",
                        },
                        {
                            "dimension": "onboarding",
                            "action": "Time a fresh-user run to measure how quickly a learner reaches the first mastery task.",
                        },
                    ],
                }
            }
        ),
        encoding="utf-8",
    )

    write_release_readiness_report(tmp_path, {"status": "pass"})
    write_release_readiness_report(tmp_path, {"status": "pass"})

    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert index.count('data-release-readiness-entry="true"') == 1


def test_write_release_readiness_history_records_decisions_without_private_paths(tmp_path):
    writer = getattr(visual_audit, "write_release_readiness_history", None)
    assert writer is not None
    readiness = {
        "status": "warn",
        "summary": {
            "decision": "needs_work",
            "score": 82,
            "market_status": "needs_improvement",
            "visual_status": "pass",
            "benchmark_status": "warn",
            "snapshot_status": "not_run",
            "baseline_status": "pass",
            "fresh_user_timing_status": "warn",
            "fresh_user_trend_status": "pass",
            "recurring_blockers": 1,
            "path": "release_readiness.md",
            "html_path": "release_readiness.html",
            "next_actions": ["Fix C:\\private\\paper.pdf spacing before launch."],
        },
    }

    result = writer(tmp_path, readiness)

    assert result["status"] == "warn"
    assert result["summary"]["path"] == "release_readiness_history.md"
    assert result["summary"]["jsonl_path"] == "release_readiness_history.jsonl"
    jsonl = (tmp_path / "release_readiness_history.jsonl").read_text(encoding="utf-8")
    markdown = (tmp_path / "release_readiness_history.md").read_text(encoding="utf-8")
    entries = [json.loads(line) for line in jsonl.splitlines() if line.strip()]
    assert len(entries) == 1
    assert entries[0]["decision"] == "needs_work"
    assert entries[0]["score"] == 82
    assert entries[0]["release_report"] == "release_readiness.html"
    assert "[private path]" in jsonl
    assert "C:\\private" not in jsonl
    assert "Release Readiness History" in markdown
    assert "needs_work" in markdown
    assert "release_readiness.html" in markdown
    assert "[private path]" in markdown
    assert "C:\\private" not in markdown


def test_write_release_readiness_history_summarizes_score_delta(tmp_path):
    writer = getattr(visual_audit, "write_release_readiness_history", None)
    assert writer is not None
    previous = {
        "recorded_at": "2026-06-22T00:00:00Z",
        "status": "warn",
        "decision": "needs_work",
        "score": 78,
        "market_status": "needs_improvement",
        "visual_status": "pass",
        "benchmark_status": "warn",
        "fresh_user_timing_status": "warn",
        "recurring_blockers": 2,
        "release_report": "release_readiness_old.html",
        "next_actions": ["Fix crowded map"],
    }
    (tmp_path / "release_readiness_history.jsonl").write_text(json.dumps(previous, ensure_ascii=False) + "\n", encoding="utf-8")
    readiness = {
        "status": "pass",
        "summary": {
            "decision": "ship",
            "score": 88,
            "market_status": "market_ready",
            "visual_status": "pass",
            "benchmark_status": "pass",
            "fresh_user_timing_status": "pass",
            "recurring_blockers": 0,
            "html_path": "release_readiness.html",
        },
    }

    result = writer(tmp_path, readiness)

    assert result["summary"]["entries"] == 2
    assert result["summary"]["score_delta"] == 10
    assert result["summary"]["trend"] == "improving"
    markdown = (tmp_path / "release_readiness_history.md").read_text(encoding="utf-8")
    assert "Trend Summary" in markdown
    assert "Score change: +10" in markdown
    assert "Trend: improving" in markdown
    assert "Recurring blockers change: -2" in markdown


def test_write_release_readiness_history_exports_html_and_index_entry(tmp_path):
    writer = getattr(visual_audit, "write_release_readiness_history", None)
    assert writer is not None
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width"></head>'
        "<body><main><h1>Start Here</h1></main></body></html>",
        encoding="utf-8",
    )
    (tmp_path / "release_readiness.html").write_text(
        '<html><body><main class="release-readiness"><h1>Release Readiness</h1></main></body></html>',
        encoding="utf-8",
    )
    readiness = {
        "status": "pass",
        "summary": {
            "decision": "ship",
            "score": 91,
            "market_status": "market_ready",
            "visual_status": "pass",
            "benchmark_status": "pass",
            "fresh_user_timing_status": "pass",
            "recurring_blockers": 0,
            "html_path": "release_readiness.html",
            "next_actions": ["Keep screenshot baselines current."],
        },
    }

    result = writer(tmp_path, readiness)
    writer(tmp_path, readiness)

    assert result["summary"]["html_path"] == "release_readiness_history.html"
    html = (tmp_path / "release_readiness_history.html").read_text(encoding="utf-8")
    assert '<main class="release-history"' in html
    assert "Trend Summary" in html
    assert "Score change" in html
    assert "release_readiness.html" in html
    assert "overflow-wrap:anywhere" in html
    assert "Microsoft YaHei UI" in html
    assert "D:\\" not in html
    index = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert index.count('data-release-history-entry="true"') == 1
    assert 'href="release_readiness_history.html"' in index
    assert "Quality trend" in index
    assert "D:\\" not in index
    readiness_html = (tmp_path / "release_readiness.html").read_text(encoding="utf-8")
    assert readiness_html.count('data-release-history-link="true"') == 1
    assert 'href="release_readiness_history.html"' in readiness_html
    assert "Quality trend" in readiness_html
    assert "D:\\" not in readiness_html


def test_cli_audit_report_writes_release_readiness_report(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "report_audit.json").write_text(
        json.dumps({"market_readiness": {"status": "market_ready", "score": 96, "dimensions": []}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--write-release-readiness",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["release_readiness_report"]["status"] == "warn"
    assert data["release_readiness_report"]["summary"]["decision"] == "needs_work"
    assert data["release_readiness_report"]["summary"]["fresh_user_timing_status"] == "not_run"
    assert any("fresh-user timing" in action for action in data["release_readiness_report"]["summary"]["next_actions"])
    assert data["release_readiness_report"]["summary"]["path"] == "release_readiness.md"
    assert data["release_readiness_report"]["summary"]["html_path"] == "release_readiness.html"
    assert (tmp_path / "release_readiness.md").exists()
    assert (tmp_path / "release_readiness.html").exists()
    assert 'href="release_readiness.html"' in (tmp_path / "index.html").read_text(encoding="utf-8")


def test_cli_audit_report_includes_market_sample_matrix(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "report_audit.json").write_text(
        json.dumps({"market_readiness": {"status": "market_ready", "score": 96, "dimensions": []}}),
        encoding="utf-8",
    )
    single = tmp_path / "single-paper-sample"
    field = tmp_path / "field-course-sample"
    _write_market_sample(single, {"profile": {"target_kind": "paper"}, "paper_map": {"nodes": []}})
    _write_market_sample(field, {"profile": {"target_kind": "course"}, "phases": [{"name": "Core"}]})

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--market-sample-dir",
            str(single),
            "--market-sample-dir",
            str(field),
            "--write-release-readiness",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["market_sample_matrix"]["status"] == "warn"
    assert data["market_sample_matrix"]["summary"]["missing_scenarios"] == ["paper-set"]
    assert data["release_readiness_report"]["summary"]["market_sample_matrix_status"] == "warn"
    assert any("paper-set" in action for action in data["release_readiness_report"]["summary"]["next_actions"])


def test_cli_audit_report_requires_visual_evidence_after_fresh_user_timing(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "report_audit.json").write_text(
        json.dumps({"market_readiness": {"status": "market_ready", "score": 96, "dimensions": []}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--fresh-user-minutes",
            "8.25",
            "--write-release-readiness",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["fresh_user_timing"]["status"] == "pass"
    assert data["release_readiness_report"]["status"] == "warn"
    assert data["release_readiness_report"]["summary"]["decision"] == "needs_work"
    assert data["release_readiness_report"]["summary"]["fresh_user_timing_status"] == "pass"
    assert data["release_readiness_report"]["summary"]["snapshot_status"] == "not_run"
    assert data["release_readiness_report"]["summary"]["baseline_status"] == "not_run"
    assert any("--capture-screenshots" in action for action in data["release_readiness_report"]["summary"]["next_actions"])
    assert not any("fresh-user timing" in action for action in data["release_readiness_report"]["summary"]["next_actions"])


def test_write_release_readiness_report_ships_after_timing_visual_and_interaction_evidence(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "report_audit.json").write_text(
        json.dumps({"market_readiness": {"status": "market_ready", "score": 96, "dimensions": []}}),
        encoding="utf-8",
    )

    result = write_release_readiness_report(
        tmp_path,
        {
            "status": "pass",
            "fresh_user_timing": {"status": "pass", "summary": {"minutes": 8.25, "target_minutes": 10}},
            "browser_snapshot_capture": {
                "status": "pass",
                "summary": {"mode": "browser-backed", "checked_files": 3},
            },
            "browser_interaction_probe": {
                "status": "pass",
                "summary": {"mode": "browser-interaction", "pages": 3, "failed_checks": 0},
            },
        },
    )

    assert result["status"] == "pass"
    assert result["summary"]["decision"] == "ship"
    assert result["summary"]["fresh_user_timing_status"] == "pass"
    assert result["summary"]["snapshot_status"] == "pass"
    assert result["summary"]["interaction_status"] == "pass"
    assert result["summary"]["market_opportunity_backlog"]
    assert not any(item["priority"] == "P0" for item in result["summary"]["market_opportunity_backlog"])
    assert not any("screenshot" in action.lower() for action in result["summary"]["next_actions"])
    assert not any("fresh-user" in action.lower() for action in result["summary"]["next_actions"])


def test_cli_audit_report_writes_release_readiness_history(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "report_audit.json").write_text(
        json.dumps({"market_readiness": {"status": "market_ready", "score": 96, "dimensions": []}}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--fresh-user-minutes",
            "8.25",
            "--write-release-readiness",
            "--write-release-history",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["release_readiness_report"]["status"] == "warn"
    assert data["release_readiness_report"]["summary"]["decision"] == "needs_work"
    assert data["release_readiness_history"]["status"] == "warn"
    assert data["release_readiness_history"]["summary"]["latest_decision"] == "needs_work"
    assert data["release_readiness_history"]["summary"]["path"] == "release_readiness_history.md"
    assert data["release_readiness_history"]["summary"]["jsonl_path"] == "release_readiness_history.jsonl"
    assert data["release_readiness_history"]["summary"]["html_path"] == "release_readiness_history.html"
    generated_checks = data["generated_artifact_audit"]["checks"]
    assert any(item["file"] == "release_readiness.html" for item in generated_checks)
    assert any(item["file"] == "release_readiness_history.html" for item in generated_checks)
    assert data["generated_artifact_audit"]["status"] == "pass"
    assert (tmp_path / "release_readiness_history.md").exists()
    assert (tmp_path / "release_readiness_history.jsonl").exists()
    assert (tmp_path / "release_readiness_history.html").exists()
    history = (tmp_path / "release_readiness_history.md").read_text(encoding="utf-8")
    assert "Release Readiness History" in history
    assert "needs_work" in history
    assert "--capture-screenshots" in history
    assert "--probe-interactions" in history
    assert "fresh-user timing test" not in history
    assert "release_readiness.html" in history


def test_cli_audit_report_fails_when_fresh_user_timing_exceeds_target(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--fresh-user-minutes",
            "13.5",
            "--fresh-user-target-minutes",
            "10",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["fresh_user_timing"]["status"] == "fail"
    assert data["fresh_user_timing"]["summary"]["minutes_over_target"] == 3.5


def test_cli_audit_report_accepts_fresh_user_timing_under_target(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--fresh-user-minutes",
            "8.25",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["fresh_user_timing"]["status"] == "pass"


def test_capture_browser_snapshots_writes_manifest_with_injected_renderer(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "paper_map.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>Reading Density Core Chain Full Exploration</body></html>",
        encoding="utf-8",
    )

    calls = []

    def fake_renderer(html_file, viewport, screenshot_file):
        calls.append((html_file.name, viewport["id"], screenshot_file.name))
        screenshot_file.write_bytes(b"fake png")

    result = capture_browser_snapshots(tmp_path, renderer=fake_renderer)

    assert result["status"] == "pass"
    assert result["summary"]["screenshots"] == 4
    assert len(calls) == 4
    manifest = tmp_path / "visual-snapshots" / "manifest.json"
    assert manifest.exists()
    manifest_text = manifest.read_text(encoding="utf-8")
    assert str(tmp_path) not in manifest_text
    data = json.loads(manifest_text)
    assert data["summary"]["screenshots"] == 4
    assert all(str(item["path"]).startswith("visual-snapshots/") for item in data["captures"])
    assert all(item["sha256"] for item in data["captures"])
    assert all(item["bytes"] == len(b"fake png") for item in data["captures"])


def test_capture_browser_snapshots_fails_when_rendered_page_is_blank(tmp_path):
    (tmp_path / "paper_lens.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        '<body><div id="root"></div><script type="application/json" id="fields-study-flow-data">{}</script></body></html>',
        encoding="utf-8",
    )

    def blank_renderer(html_file, viewport, screenshot_file):
        screenshot_file.write_bytes(b"blank png")
        return {
            "rendered_text_length": 0,
            "root_width": 0,
            "root_height": 0,
            "visible_marker_count": 0,
        }

    result = capture_browser_snapshots(tmp_path, surfaces=["paper_lens.html"], renderer=blank_renderer)

    assert result["status"] == "fail"
    failed_checks = [item for item in result["checks"] if item["status"] == "fail"]
    assert any(item["check"] == "rendered_text" for item in failed_checks)
    assert any(item["check"] == "root_box" for item in failed_checks)
    assert result["captures"][0]["rendered_text_length"] == 0


def test_capture_browser_snapshots_accepts_static_body_render_box(tmp_path):
    (tmp_path / "release_readiness.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body><main>Release Readiness Dashboard with real rendered content</main></body></html>",
        encoding="utf-8",
    )

    def static_renderer(html_file, viewport, screenshot_file):
        screenshot_file.write_bytes(b"rendered png")
        return {
            "rendered_text_length": 58,
            "root_width": 0,
            "root_height": 0,
            "render_width": 960,
            "render_height": 540,
            "visible_marker_count": 1,
        }

    result = capture_browser_snapshots(tmp_path, surfaces=["release_readiness.html"], renderer=static_renderer)

    assert result["status"] == "pass"
    box_checks = [item for item in result["checks"] if item["check"] == "root_box"]
    assert box_checks and box_checks[0]["status"] == "pass"
    assert result["captures"][0]["render_width"] == 960


def test_capture_browser_snapshots_fails_when_rendered_text_has_ellipsis(tmp_path):
    (tmp_path / "paper_map.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        '<body><div id="root">论文逻辑图</div></body></html>',
        encoding="utf-8",
    )

    def ellipsis_renderer(html_file, viewport, screenshot_file):
        screenshot_file.write_bytes(b"rendered png")
        return {
            "rendered_text_length": 48,
            "root_width": 960,
            "root_height": 540,
            "visible_marker_count": 1,
            "rendered_decorative_ellipsis_count": 2,
        }

    result = capture_browser_snapshots(tmp_path, surfaces=["paper_map.html"], renderer=ellipsis_renderer)

    assert result["status"] == "fail"
    failed_checks = [item for item in result["checks"] if item["status"] == "fail"]
    assert any(item["check"] == "rendered_decorative_ellipsis" for item in failed_checks)
    assert result["captures"][0]["rendered_decorative_ellipsis_count"] == 2


def test_probe_browser_interactions_passes_with_injected_runner(tmp_path):
    for name in ("paper_map.html", "paper_lens.html", "roadmap.html"):
        (tmp_path / name).write_text(
            '<!doctype html><html><head><meta name="viewport" content="width=device-width"></head>'
            f"<body>{name}</body></html>",
            encoding="utf-8",
        )

    def fake_runner(html_file):
        if html_file.name == "paper_map.html":
            return {
                "console_errors": 0,
                "paper_map_canvas_present": True,
                "paper_map_nodes_before": 3,
                "paper_map_nodes_after_branch": 7,
                "paper_map_branch_revealed": True,
                "paper_map_detail_changed": True,
                "paper_map_zoom_changed": True,
            }
        if html_file.name == "roadmap.html":
            return {
                "console_errors": 0,
                "roadmap_resources_before": 5,
                "roadmap_resources_after_filter": 3,
                "roadmap_filter_changed": True,
            }
        return {
            "console_errors": 0,
            "paper_lens_active_before": "Abstract",
            "paper_lens_active_after": "Method",
            "paper_lens_detail_changed": True,
        }

    result = probe_browser_interactions(tmp_path, runner=fake_runner)

    assert result["status"] == "pass"
    assert result["summary"]["mode"] == "browser-interaction"
    assert result["summary"]["pages"] == 3
    assert any(item["check"] == "paper_map_branch_revealed" and item["status"] == "pass" for item in result["checks"])
    assert any(item["check"] == "roadmap_filter_changed" and item["status"] == "pass" for item in result["checks"])
    assert any(item["check"] == "paper_lens_detail_changed" and item["status"] == "pass" for item in result["checks"])
    dumped = json.dumps(result, ensure_ascii=False)
    assert str(tmp_path) not in dumped


def test_probe_browser_interactions_fails_when_paper_map_buttons_do_not_work(tmp_path):
    (tmp_path / "paper_map.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width"></head>'
        "<body>paper map</body></html>",
        encoding="utf-8",
    )

    def broken_runner(html_file):
        return {
            "console_errors": 0,
            "paper_map_canvas_present": True,
            "paper_map_nodes_before": 3,
            "paper_map_nodes_after_branch": 3,
            "paper_map_branch_revealed": False,
            "paper_map_detail_changed": False,
            "paper_map_zoom_changed": False,
        }

    result = probe_browser_interactions(tmp_path, runner=broken_runner)

    assert result["status"] == "fail"
    failed_checks = {item["check"] for item in result["checks"] if item["status"] == "fail"}
    assert {"paper_map_branch_revealed", "paper_map_detail_changed", "paper_map_zoom_changed"} <= failed_checks


def test_probe_browser_interactions_skips_paper_map_branch_checks_when_not_applicable(tmp_path):
    (tmp_path / "paper_map.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width"></head>'
        "<body>paper map</body></html>",
        encoding="utf-8",
    )

    def concise_runner(html_file):
        return {
            "console_errors": 0,
            "paper_map_canvas_present": True,
            "paper_map_nodes_before": 1,
            "paper_map_nodes_after_branch": 1,
            "paper_map_branch_toggle_available": False,
            "paper_map_branch_revealed": False,
            "paper_map_detail_changed": False,
            "paper_map_zoom_changed": True,
        }

    result = probe_browser_interactions(tmp_path, runner=concise_runner)

    assert result["status"] == "pass"
    statuses = {item["check"]: item["status"] for item in result["checks"]}
    assert statuses["paper_map_branch_revealed"] == "skipped"
    assert statuses["paper_map_detail_changed"] == "skipped"


def test_probe_browser_interactions_skips_paper_lens_detail_switch_for_single_paragraph(tmp_path):
    (tmp_path / "paper_lens.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width"></head>'
        "<body>paper lens</body></html>",
        encoding="utf-8",
    )

    def single_paragraph_runner(html_file):
        return {
            "console_errors": 0,
            "paper_lens_paragraphs": 1,
            "paper_lens_active_before": "段落 1",
            "paper_lens_active_after": "段落 1",
            "paper_lens_detail_changed": False,
        }

    result = probe_browser_interactions(tmp_path, runner=single_paragraph_runner)

    assert result["status"] == "pass"
    statuses = {item["check"]: item["status"] for item in result["checks"]}
    assert statuses["paper_lens_detail_changed"] == "skipped"


def test_resource_library_markers_require_actual_resource_data():
    html = "<script>resource-purpose-badge resource-strength-badge resource-provenance-badge</script>"

    assert not visual_audit._resource_library_marker({}, html, ("resource-purpose-badge",))
    assert visual_audit._resource_library_marker({"resource_library": [{"title": "Target paper"}]}, html, ("resource-purpose-badge",))


def test_probe_browser_interactions_fails_when_roadmap_filter_has_no_resources(tmp_path):
    (tmp_path / "roadmap.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width"></head>'
        "<body>roadmap</body></html>",
        encoding="utf-8",
    )

    def empty_resource_runner(html_file):
        return {
            "console_errors": 0,
            "roadmap_resources_before": 0,
            "roadmap_resources_after_filter": 0,
            "roadmap_filter_changed": True,
        }

    result = probe_browser_interactions(tmp_path, runner=empty_resource_runner)

    assert result["status"] == "fail"
    failed_checks = {item["check"] for item in result["checks"] if item["status"] == "fail"}
    assert {"roadmap_resources_present", "roadmap_filter_changed"} <= failed_checks


def test_cli_audit_report_probe_interactions_degrades_without_browser_runtime(tmp_path):
    (tmp_path / "paper_map.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width"></head>'
        "<body>paper map</body></html>",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--probe-interactions",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode in {0, 1}
    data = json.loads(result.stdout)
    assert "browser_interaction_probe" in data
    assert data["browser_interaction_probe"]["summary"]["mode"] == "browser-interaction"
    assert data["browser_interaction_probe"]["status"] in {"pass", "skipped", "fail"}


def test_compare_browser_snapshot_baseline_detects_pixel_and_viewport_regressions(tmp_path):
    baseline = {
        "captures": [
            {
                "file": "index.html",
                "viewport": "desktop-1280x720",
                "width": 1280,
                "height": 720,
                "sha256": "abc",
                "path": "visual-snapshots/index.desktop-1280x720.png",
            },
            {
                "file": "paper_map.html",
                "viewport": "mobile-390x844",
                "width": 390,
                "height": 844,
                "sha256": "def",
                "path": "visual-snapshots/paper_map.mobile-390x844.png",
            },
        ]
    }
    current = {
        "captures": [
            {
                "file": "index.html",
                "viewport": "desktop-1280x720",
                "width": 1280,
                "height": 720,
                "sha256": "changed",
                "path": "visual-snapshots/index.desktop-1280x720.png",
            }
        ]
    }
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    result = compare_browser_snapshot_baseline(current, baseline_path)

    assert result["status"] == "fail"
    failed = {item["id"] for item in result["checks"] if item["status"] == "fail"}
    assert {"snapshot_hash:index.html:desktop-1280x720", "snapshot_present:paper_map.html:mobile-390x844"} <= failed


def test_cli_audit_report_can_compare_existing_snapshot_baseline(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )
    manifest = {
        "status": "pass",
        "summary": {"mode": "browser-backed", "screenshots": 1},
        "captures": [
            {
                "file": "index.html",
                "viewport": "desktop-1280x720",
                "width": 1280,
                "height": 720,
                "sha256": "same",
                "path": "visual-snapshots/index.desktop-1280x720.png",
            }
        ],
    }
    snapshot_dir = tmp_path / "visual-snapshots"
    snapshot_dir.mkdir()
    (snapshot_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--snapshot-baseline",
            str(baseline_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["browser_snapshot_baseline"]["status"] == "pass"


def test_cli_audit_report_fails_when_snapshot_baseline_differs(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )
    current = {
        "status": "pass",
        "captures": [
            {
                "file": "index.html",
                "viewport": "desktop-1280x720",
                "width": 1280,
                "height": 720,
                "sha256": "new",
                "path": "visual-snapshots/index.desktop-1280x720.png",
            }
        ],
    }
    baseline = {
        "status": "pass",
        "captures": [
            {
                "file": "index.html",
                "viewport": "desktop-1280x720",
                "width": 1280,
                "height": 720,
                "sha256": "old",
                "path": "visual-snapshots/index.desktop-1280x720.png",
            }
        ],
    }
    snapshot_dir = tmp_path / "visual-snapshots"
    snapshot_dir.mkdir()
    (snapshot_dir / "manifest.json").write_text(json.dumps(current), encoding="utf-8")
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--snapshot-baseline",
            str(baseline_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["browser_snapshot_baseline"]["status"] == "fail"


def test_cli_audit_report_capture_screenshots_degrades_without_browser_runtime(tmp_path):
    (tmp_path / "index.html").write_text(
        '<html><head><meta name="viewport" content="width=device-width">'
        "<style>body{overflow-wrap:anywhere;max-width:100%;font-family:Arial}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "audit-report",
            "--report-dir",
            str(tmp_path),
            "--capture-screenshots",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert "browser_snapshot_capture" in data
    assert data["browser_snapshot_capture"]["summary"]["mode"] == "browser-backed"
    assert data["browser_snapshot_capture"]["status"] in {"pass", "skipped"}


def test_build_report_audit_scores_market_readiness_dimensions(tmp_path):
    for name, marker in {
        "index.html": "Start Here Bring Your Own Paper report-health-panel Report Health Evidence coverage 5 evidence-backed edges report_audit.json scenario-panel Three Learning Scenarios Single paper Paper set Field / course route fresh-user-flow-panel data-fresh-user-flow 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer intent-router-panel data-intent-router Choose by what you need data-learning-guide-panel 3 starter questions data-starter-question fields-study-flow ask paper_map.html paper_lens.html roadmap.html Local assets",
        "paper_map.html": 'Reading Density Core Chain Full Exploration Evidence coverage data-report-static-fallback="paper_map" data-paper-map-canvas react-flow Download presentation notes',
        "paper_lens.html": "paragraph evidence Explanation support not a resource trust score",
            "roadmap.html": "learning console mastery 1-minute start data-mastery-export 下载 worksheet resource-purpose-badge 为什么读 resource-strength-badge 证据强度 resource-provenance-badge resource-coverage-badge 覆盖范围 最强证据 resource-evidence-link 查看证据",
    }.items():
        (tmp_path / name).write_text(
            '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
            "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}.flow-shell{min-height:520px}@media (max-width: 820px){body{max-width:100%}}</style></head>"
            f"<body>{marker} 10 分钟入门</body></html>",
            encoding="utf-8",
        )
    roadmap = {
        "profile": {"output_language": "zh-CN"},
        "paper_map": {"nodes": [{"id": "background"}, {"id": "method"}]},
        "paper_lens": {
            "segments": [{"id": "seg-1"}, {"id": "seg-2"}],
            "inline_explanations": [
                {"plain_meaning": "This paragraph explains the motivation.", "confidence": 0.82},
                {"plain_meaning": "This paragraph explains the method.", "confidence": 0.78},
            ],
        },
        "study_tasks": [
            {"type": "explain", "title": "Explain"},
            {"type": "derive", "title": "Derive"},
            {"type": "reproduce", "title": "Reproduce"},
            {"type": "critique", "title": "Critique"},
        ],
        "mastery_evidence": {"required_evidence": [{"task_id": "task-1"}, {"task_id": "task-2"}]},
        "knowledge_graph": {"summary": {"edges": 12, "evidence_backed_edges": 5}},
        "study_bundle": {
            "resources": [
                {"title": "Target paper", "local_href": "assets/paper.pdf", "status": "downloaded"},
                {"title": "Support notes", "local_href": "assets/notes.html", "status": "snapshotted"},
                {"title": "Code", "local_href": "assets/code.zip", "status": "downloaded"},
            ]
        },
        "resource_library": [
            {
                "title": "Target paper",
                "metadata": {
                    "rag": {
                        "evidence_chunks": [
                            {
                                "snippet": "Target-paper evidence supports this resource.",
                                "detail_anchor": "detail-seg-1",
                                "score": 2.4,
                            }
                        ]
                    }
                },
            }
        ],
    }

    audit = build_report_audit(tmp_path, roadmap)

    readiness = audit["market_readiness"]
    assert readiness["status"] == "market_ready"
    assert readiness["score"] >= 80
    dimension_ids = {item["id"] for item in readiness["dimensions"]}
    assert {
        "onboarding",
        "visual_polish",
        "learning_depth",
        "plain_explanation",
        "resource_completeness",
        "actionability",
    } <= dimension_ids
    assert readiness["competitive_positioning"]["product_wedge"] == "paper_centered_mastery"
    assert readiness["next_best_actions"]
    experience = audit["experience_risks"]
    assert experience["status"] == "pass"
    check_ids = {item["id"] for item in experience["checks"]}
    assert {
        "first_screen_quickstart",
        "paper_map_canvas_interaction",
        "paper_map_branch_deferral",
        "paper_lens_paragraph_focus",
        "recommended_first_action_panel",
        "learning_outcome_contract",
        "starter_questions_panel",
        "support_files_progressive_disclosure",
        "report_health_evidence_summary",
        "resource_local_first",
        "resource_purpose_badges",
        "resource_strength_signals",
        "mobile_wrap_layout",
    } <= check_ids
    viewport = audit["viewport_risks"]
    assert viewport["status"] == "pass"
    viewport_ids = {item["id"] for item in viewport["checks"]}
    assert {
        "responsive_breakpoints",
        "long_text_wrap_budget",
        "paper_map_canvas_budget",
        "resource_list_mobile_budget",
    } <= viewport_ids
    fresh_flow = audit["fresh_user_flow"]
    assert fresh_flow["status"] == "pass"
    assert fresh_flow["summary"]["warnings"] == 0
    fresh_ids = {item["id"] for item in fresh_flow["checks"]}
    assert {
        "first_action_visible",
        "ten_minute_path_visible",
        "paper_map_first_step",
        "paper_lens_second_step",
        "mastery_task_finish",
        "local_resource_available",
    } <= fresh_ids
    snapshot = audit["visual_snapshot_matrix"]
    assert snapshot["status"] == "pass"
    assert snapshot["summary"]["stress_scenarios"] >= 1
    snapshot_ids = {item["id"] for item in snapshot["checks"]}
    assert {
        "long_text_resilience",
        "dense_resource_library_controls",
        "paper_map_canvas_density",
        "mobile_viewport_readability",
    } <= snapshot_ids


def test_build_report_audit_flags_market_readiness_gaps(tmp_path):
    (tmp_path / "roadmap.html").write_text(
        '<html><head><style>body{font-family:Arial}</style></head><body>links only</body></html>',
        encoding="utf-8",
    )

    audit = build_report_audit(tmp_path, {"profile": {"output_language": "en"}, "study_tasks": []})

    readiness = audit["market_readiness"]
    assert readiness["status"] == "needs_improvement"
    assert readiness["score"] < 80
    assert readiness["next_best_actions"]
    assert any(item["id"] == "onboarding" and item["score"] < 70 for item in readiness["dimensions"])
    assert audit["experience_risks"]["status"] == "warn"
    assert audit["experience_risks"]["summary"]["warnings"] > 0
    assert any(item["id"] == "first_screen_quickstart" and item["status"] == "warn" for item in audit["experience_risks"]["checks"])
    assert audit["fresh_user_flow"]["status"] == "warn"


def test_visual_snapshot_matrix_warns_on_dense_ugly_report(tmp_path):
    long_title = "Teaching LLMs to Plan Logical Chain-of-Thought Instruction Tuning for Symbolic Planning " * 4
    resources = [
        {"title": f"Very Long Resource Title About Planning Preconditions Effects State Transitions Validation {index}", "status": "link-only"}
        for index in range(14)
    ]
    for name, marker in {
        "index.html": "Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer intent-router-panel data-intent-router Choose by what you need fresh-user-flow-panel data-fresh-user-flow paper_map.html paper_lens.html roadmap.html Local assets report-health-panel Report Health scenario-panel Three Learning Scenarios",
        "paper_map.html": "Reading Density Core Chain Full Exploration Evidence coverage data-report-static-fallback=\"paper_map\" data-paper-map-canvas",
        "paper_lens.html": "paragraph evidence Explanation support not a resource trust score",
        "roadmap.html": "learning console mastery resource-purpose-badge Why read resource-strength-badge Evidence strength resource-provenance-badge resource-coverage-badge Coverage",
    }.items():
        (tmp_path / name).write_text(
            '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
            "<style>body{font-family:Arial;max-width:100%}.flow-shell{height:160px}</style></head>"
            f"<body><h1>{long_title}</h1><table><tr><td>{marker}</td></tr></table></body></html>",
            encoding="utf-8",
        )
    roadmap = {
        "title": long_title,
        "profile": {"output_language": "en"},
        "paper_map": {"nodes": [{"id": f"node-{index}"} for index in range(16)]},
        "paper_lens": {
            "segments": [{"id": "seg-1", "original_text": long_title}],
            "inline_explanations": [
                {"plain_meaning": "This paragraph explains the target paper motivation.", "confidence": 0.82},
                {"plain_meaning": "This paragraph explains the target paper method.", "confidence": 0.78},
            ],
        },
        "study_tasks": [{"type": kind} for kind in ("explain", "derive", "reproduce", "critique")],
        "mastery_evidence": {"required_evidence": [{"task_id": "task-1"}]},
        "knowledge_graph": {"summary": {"edges": 10, "evidence_backed_edges": 4}},
        "study_bundle": {"resources": resources},
    }

    audit = build_report_audit(tmp_path, roadmap)

    matrix = audit["visual_snapshot_matrix"]
    assert matrix["status"] == "warn"
    assert matrix["summary"]["warnings"] >= 2
    failed = {item["id"] for item in matrix["checks"] if item["status"] == "warn"}
    assert {"long_text_resilience", "dense_resource_library_controls", "paper_map_canvas_density"} <= failed
    assert audit["market_readiness"]["status"] == "needs_improvement"


def test_fresh_user_flow_warning_prevents_market_ready_status(tmp_path):
    for name, marker in {
        "index.html": "Start Here Bring Your Own Paper report-health-panel Report Health report_audit.json scenario-panel Three Learning Scenarios Single paper Paper set Field / course route",
        "paper_map.html": 'Reading Density Core Chain Full Exploration Evidence coverage data-report-static-fallback="paper_map" data-paper-map-canvas react-flow Download presentation notes',
        "paper_lens.html": "paragraph evidence Explanation support not a resource trust score",
        "roadmap.html": "learning console mastery 1-minute start resource-purpose-badge Why read resource-strength-badge Evidence strength resource-provenance-badge resource-coverage-badge Coverage",
    }.items():
        (tmp_path / name).write_text(
            '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
            "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}.flow-shell{min-height:520px}@media (max-width: 820px){body{max-width:100%}}</style></head>"
            f"<body>{marker}</body></html>",
            encoding="utf-8",
        )
    roadmap = {
        "profile": {"output_language": "en"},
        "paper_map": {"nodes": [{"id": "target"}, {"id": "method"}]},
        "paper_lens": {
            "segments": [{"id": "seg-1"}, {"id": "seg-2"}],
            "inline_explanations": [
                {"plain_meaning": "This paragraph explains the motivation.", "confidence": 0.82},
                {"plain_meaning": "This paragraph explains the method.", "confidence": 0.78},
            ],
        },
        "study_tasks": [
            {"type": "explain"},
            {"type": "derive"},
            {"type": "reproduce"},
            {"type": "critique"},
        ],
        "mastery_evidence": {"required_evidence": [{"task_id": "task-1"}, {"task_id": "task-2"}]},
        "knowledge_graph": {"summary": {"edges": 12, "evidence_backed_edges": 5}},
        "study_bundle": {"resources": [{"title": "Paper", "local_href": "assets/paper.pdf", "status": "downloaded"}]},
    }

    audit = build_report_audit(tmp_path, roadmap)

    assert audit["fresh_user_flow"]["status"] == "warn"
    assert any(item["id"] == "ten_minute_path_visible" and item["status"] == "warn" for item in audit["fresh_user_flow"]["checks"])
    assert audit["market_readiness"]["status"] == "needs_improvement"


def test_experience_warnings_prevent_market_ready_status(tmp_path):
    for name, marker in {
        "index.html": "Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer intent-router-panel data-intent-router Choose by what you need data-learning-guide-panel 3 starter questions data-starter-question fields-study-flow ask fresh-user-flow-panel data-fresh-user-flow paper_map.html paper_lens.html roadmap.html Local assets report-health-panel Report Health Evidence coverage 5 evidence-backed edges report_audit.json scenario-panel Three Learning Scenarios Single paper Paper set Field / course route",
        "paper_map.html": "Reading Density Core Chain Full Exploration",
        "paper_lens.html": "paragraph evidence",
        "roadmap.html": "learning console mastery",
    }.items():
        (tmp_path / name).write_text(
            '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
            "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
            f"<body>{marker}</body></html>",
            encoding="utf-8",
        )
    roadmap = {
        "profile": {"output_language": "en"},
        "paper_map": {"nodes": [{"id": "background"}]},
        "paper_lens": {
            "segments": [{"id": "seg-1"}],
            "inline_explanations": [
                {"plain_meaning": "This paragraph explains the target paper motivation.", "confidence": 0.82},
                {"plain_meaning": "This paragraph explains the target paper method.", "confidence": 0.78},
            ],
        },
        "study_tasks": [
            {"type": "explain"},
            {"type": "derive"},
            {"type": "reproduce"},
            {"type": "critique"},
        ],
        "mastery_evidence": {"required_evidence": [{"task_id": "task-1"}]},
        "knowledge_graph": {"summary": {"edges": 10, "evidence_backed_edges": 4}},
        "study_bundle": {"resources": [{"title": "Paper", "local_href": "assets/paper.pdf", "status": "downloaded"}]},
    }

    audit = build_report_audit(tmp_path, roadmap)

    assert audit["experience_risks"]["status"] == "warn"
    assert audit["market_readiness"]["status"] == "needs_improvement"
    assert audit["market_readiness"]["score"] < 100


def test_sparse_roadmap_requires_route_recovery_next_steps(tmp_path):
    (tmp_path / "roadmap.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>learning console mastery 1-minute start</body></html>",
        encoding="utf-8",
    )
    roadmap = {"profile": {"output_language": "en"}, "phases": [], "study_tasks": [], "study_bundle": {"resources": []}}

    audit = build_report_audit(tmp_path, roadmap)
    checks = {item["id"]: item for item in audit["experience_risks"]["checks"]}

    assert checks["route_recovery_next_steps"]["status"] == "warn"
    assert audit["experience_risks"]["status"] == "warn"

    (tmp_path / "roadmap.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        '<body><section data-route-recovery>下一步补齐路线</section></body></html>',
        encoding="utf-8",
    )

    recovered = build_report_audit(tmp_path, roadmap)
    recovered_checks = {item["id"]: item for item in recovered["experience_risks"]["checks"]}

    assert recovered_checks["route_recovery_next_steps"]["status"] == "pass"


def test_interactive_reports_require_static_fallback_against_blank_pages(tmp_path):
    (tmp_path / "paper_map.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}.flow-shell{min-height:520px}</style></head>"
        "<body>Reading Density Core Chain Full Exploration Evidence coverage data-paper-map-canvas react-flow</body></html>",
        encoding="utf-8",
    )
    roadmap = {"profile": {"output_language": "en"}, "paper_map": {"nodes": [{"id": "target"}]}}

    audit = build_report_audit(tmp_path, roadmap)
    checks = {item["id"]: item for item in audit["experience_risks"]["checks"]}

    assert checks["frontend_static_fallback"]["status"] == "warn"

    (tmp_path / "paper_map.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}.flow-shell{min-height:520px}</style></head>"
        '<body><section data-report-static-fallback="paper_map">If the interactive app does not start</section>'
        "Reading Density Core Chain Full Exploration Evidence coverage data-paper-map-canvas react-flow</body></html>",
        encoding="utf-8",
    )

    recovered = build_report_audit(tmp_path, roadmap)
    recovered_checks = {item["id"]: item for item in recovered["experience_risks"]["checks"]}

    assert recovered_checks["frontend_static_fallback"]["status"] == "pass"


def test_experience_risks_require_report_health_panel_on_start_page(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )
    roadmap = {"profile": {"output_language": "en"}, "study_bundle": {"resources": [{"status": "downloaded", "local_href": "assets/paper.pdf"}]}}

    audit = build_report_audit(tmp_path, roadmap)
    checks = {item["id"]: item for item in audit["experience_risks"]["checks"]}

    assert checks["report_health_panel"]["status"] == "warn"

    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        '<body><section class="report-health-panel">Report Health Local assets Privacy redacted Layout safe report_audit.json</section>'
        "Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer</body></html>",
        encoding="utf-8",
    )

    recovered = build_report_audit(tmp_path, roadmap)
    recovered_checks = {item["id"]: item for item in recovered["experience_risks"]["checks"]}

    assert recovered_checks["report_health_panel"]["status"] == "pass"


def test_experience_risks_require_evidence_summary_inside_report_health_panel(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer "
        "report-health-panel Report Health report_audit.json scenario-panel Three Learning Scenarios Single paper Paper set Field / course route</body></html>",
        encoding="utf-8",
    )
    (tmp_path / "roadmap.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>resource-evidence-link Strongest evidence Review evidence</body></html>",
        encoding="utf-8",
    )
    roadmap = {
        "profile": {"output_language": "en"},
        "knowledge_graph": {"summary": {"edges": 8, "evidence_backed_edges": 3}},
        "study_bundle": {"resources": [{"status": "downloaded", "local_href": "assets/paper.pdf"}]},
    }

    audit = build_report_audit(tmp_path, roadmap)
    checks = {item["id"]: item for item in audit["experience_risks"]["checks"]}

    assert checks["report_health_evidence_summary"]["status"] == "warn"

    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        '<body><section class="report-health-panel">Report Health Local assets report_audit.json</section>'
        '<aside>Evidence coverage 3 evidence-backed edges</aside>'
        "Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer "
        "scenario-panel Three Learning Scenarios Single paper Paper set Field / course route</body></html>",
        encoding="utf-8",
    )

    outside_panel = build_report_audit(tmp_path, roadmap)
    outside_panel_checks = {item["id"]: item for item in outside_panel["experience_risks"]["checks"]}

    assert outside_panel_checks["report_health_evidence_summary"]["status"] == "warn"

    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer "
        "report-health-panel Report Health Evidence coverage 3 evidence-backed edges report_audit.json "
        "scenario-panel Three Learning Scenarios Single paper Paper set Field / course route</body></html>",
        encoding="utf-8",
    )

    recovered = build_report_audit(tmp_path, roadmap)
    recovered_checks = {item["id"]: item for item in recovered["experience_risks"]["checks"]}

    assert recovered_checks["report_health_evidence_summary"]["status"] == "pass"


def test_experience_risks_require_three_scenario_coverage_on_start_page(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer report-health-panel Report Health</body></html>",
        encoding="utf-8",
    )
    roadmap = {"profile": {"output_language": "en"}}

    audit = build_report_audit(tmp_path, roadmap)
    checks = {item["id"]: item for item in audit["experience_risks"]["checks"]}

    assert checks["scenario_coverage_panel"]["status"] == "warn"

    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        '<body><section class="scenario-panel">Three Learning Scenarios Single paper Paper set Field / course route</section>'
        "Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer report-health-panel Report Health</body></html>",
        encoding="utf-8",
    )

    recovered = build_report_audit(tmp_path, roadmap)
    recovered_checks = {item["id"]: item for item in recovered["experience_risks"]["checks"]}

    assert recovered_checks["scenario_coverage_panel"]["status"] == "pass"


def test_experience_risks_require_market_value_panel_on_start_page(tmp_path):
    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>Start Here Bring Your Own Paper 10-minute quickstart report-health-panel Report Health scenario-panel Three Learning Scenarios Single paper Field / course route</body></html>",
        encoding="utf-8",
    )
    roadmap = {"profile": {"output_language": "en"}}

    audit = build_report_audit(tmp_path, roadmap)
    checks = {item["id"]: item for item in audit["experience_risks"]["checks"]}
    visual_checks = {(item["file"], item["check"]): item for item in audit["visual_audit"]["checks"]}

    assert checks["market_value_panel"]["status"] == "warn"
    assert visual_checks[("index.html", "market_value_panel")]["status"] == "fail"

    (tmp_path / "index.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        '<body><section data-market-value-panel="true">Why this is more than a PDF summarizer Differentiated value</section>'
        "Start Here Bring Your Own Paper 10-minute quickstart report-health-panel Report Health scenario-panel Three Learning Scenarios Single paper Field / course route</body></html>",
        encoding="utf-8",
    )

    recovered = build_report_audit(tmp_path, roadmap)
    recovered_checks = {item["id"]: item for item in recovered["experience_risks"]["checks"]}
    recovered_visual_checks = {(item["file"], item["check"]): item for item in recovered["visual_audit"]["checks"]}

    assert recovered_checks["market_value_panel"]["status"] == "pass"
    assert recovered_visual_checks[("index.html", "market_value_panel")]["status"] == "pass"


def test_viewport_warnings_prevent_market_ready_status(tmp_path):
    for name, marker in {
        "index.html": "Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer intent-router-panel data-intent-router Choose by what you need data-learning-guide-panel 3 starter questions data-starter-question fields-study-flow ask fresh-user-flow-panel data-fresh-user-flow roadmap.html Local assets report-health-panel Report Health Evidence coverage 4 evidence-backed edges report_audit.json scenario-panel Three Learning Scenarios Single paper Paper set Field / course route",
        "paper_map.html": 'Reading Density Core Chain Full Exploration Evidence coverage data-report-static-fallback="paper_map" data-paper-map-canvas react-flow Download presentation notes',
        "paper_lens.html": "paragraph evidence",
        "roadmap.html": "learning console mastery",
    }.items():
        (tmp_path / name).write_text(
            '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
            "<style>body{font-family:Arial;max-width:100%}.flow-shell{height:160px}</style></head>"
            f"<body><h1>{'VeryLongTitle' * 18}</h1><table><tr><td>{marker}</td></tr></table></body></html>",
            encoding="utf-8",
        )
    roadmap = {
        "profile": {"output_language": "en"},
        "paper_map": {"nodes": [{"id": "background"}]},
        "paper_lens": {
            "segments": [{"id": "seg-1"}],
            "inline_explanations": [
                {"plain_meaning": "This paragraph explains the target paper motivation.", "confidence": 0.82},
                {"plain_meaning": "This paragraph explains the target paper method.", "confidence": 0.78},
            ],
        },
        "study_tasks": [
            {"type": "explain"},
            {"type": "derive"},
            {"type": "reproduce"},
            {"type": "critique"},
        ],
        "mastery_evidence": {"required_evidence": [{"task_id": "task-1"}]},
        "knowledge_graph": {"summary": {"edges": 10, "evidence_backed_edges": 4}},
        "study_bundle": {"resources": [{"title": "Paper", "local_href": "assets/paper.pdf", "status": "downloaded"}]},
    }

    audit = build_report_audit(tmp_path, roadmap)

    assert audit["viewport_risks"]["status"] == "warn"
    assert audit["viewport_risks"]["summary"]["warnings"] > 0
    assert audit["market_readiness"]["status"] == "needs_improvement"


def test_competitive_benchmark_passes_paper_centered_mastery_report(tmp_path):
    for name, marker in {
        "index.html": "Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer intent-router-panel data-intent-router Choose by what you need data-learning-guide-panel 3 starter questions data-starter-question fields-study-flow ask fresh-user-flow-panel data-fresh-user-flow paper_map.html paper_lens.html roadmap.html Local assets report-health-panel Report Health Evidence coverage 5 evidence-backed edges report_audit.json scenario-panel Three Learning Scenarios Single paper Paper set Field / course route",
        "paper_map.html": 'Reading Density Core Chain Full Exploration Evidence coverage data-report-static-fallback="paper_map" data-paper-map-canvas react-flow Download presentation notes',
        "paper_lens.html": "paragraph evidence Explanation support not a resource trust score",
        "roadmap.html": "learning console mastery 1-minute start data-mastery-export 下载 worksheet resource-list resource-purpose-badge 为什么读 resource-strength-badge 证据强度 resource-provenance-badge resource-coverage-badge 覆盖范围 最强证据 resource-evidence-link 查看证据 paper_lens.html#detail-seg-1",
    }.items():
        (tmp_path / name).write_text(
            '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
            "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}.flow-shell{min-height:560px}@media (max-width: 820px){body{max-width:100%}}</style></head>"
            f"<body>{marker}</body></html>",
            encoding="utf-8",
        )
    roadmap = {
        "profile": {"output_language": "en"},
        "paper_map": {"nodes": [{"id": "target"}, {"id": "background"}, {"id": "method"}, {"id": "experiment"}]},
        "paper_lens": {
            "segments": [{"id": "seg-1"}, {"id": "seg-2"}],
            "inline_explanations": [
                {"plain_meaning": "This paragraph explains the paper gap and motivation.", "confidence": 0.81},
                {"plain_meaning": "This paragraph explains the method and validation path.", "confidence": 0.76},
            ],
        },
        "study_tasks": [
            {"type": "explain"},
            {"type": "derive"},
            {"type": "reproduce"},
            {"type": "critique"},
        ],
        "mastery_evidence": {"required_evidence": [{"task_id": "explain"}, {"task_id": "reproduce"}]},
        "knowledge_graph": {"summary": {"edges": 12, "evidence_backed_edges": 5}},
        "study_bundle": {
            "resources": [
                {"title": "Target paper", "local_href": "assets/paper.pdf", "status": "downloaded"},
                {"title": "Support code", "local_href": "assets/code.zip", "status": "copied"},
                {"title": "Background snapshot", "local_href": "assets/background.html", "status": "snapshotted"},
            ]
        },
        "resource_library": [
            {
                "title": "Target paper",
                "metadata": {
                    "rag": {
                        "evidence_chunks": [
                            {
                                "snippet": "The paper evidence explains why the target resource is selected.",
                                "detail_anchor": "detail-seg-1",
                                "score": 2.5,
                            }
                        ]
                    }
                },
            }
        ],
    }

    audit = build_report_audit(tmp_path, roadmap)

    benchmark = audit["competitive_benchmark"]
    assert benchmark["status"] == "pass"
    assert benchmark["summary"]["passed_checks"] == benchmark["summary"]["checks"]
    check_ids = {item["id"] for item in benchmark["checks"]}
    assert {
        "paperqa_grounded_evidence",
        "explainpaper_contextual_explanations",
        "scholarcy_structured_review_cards",
        "get_it_measurable_mastery_map",
        "notebooklm_portable_study_outputs",
        "roadmap_interactive_first_step",
        "litmaps_research_context_boundary",
        "xyflow_canvas_affordance",
        "local_first_bundle",
        "resource_purpose_badges",
        "resource_strength_signals",
        "resource_evidence_snippets",
        "resource_evidence_review_links",
    } <= check_ids
    assert audit["market_readiness"]["status"] == "market_ready"


def test_competitive_benchmark_requires_contextual_paper_lens_explanations(tmp_path):
    for name, marker in {
        "index.html": "Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer intent-router-panel data-intent-router Choose by what you need fresh-user-flow-panel data-fresh-user-flow paper_map.html paper_lens.html roadmap.html Local assets report-health-panel Report Health report_audit.json scenario-panel Three Learning Scenarios Single paper Paper set Field / course route",
        "paper_map.html": 'Reading Density Core Chain Full Exploration Evidence coverage data-report-static-fallback="paper_map" data-paper-map-canvas react-flow Download presentation notes',
        "paper_lens.html": "paragraph evidence Explanation support not a resource trust score",
        "roadmap.html": "learning console mastery 1-minute start data-mastery-export Download worksheet resource-list resource-purpose-badge Why read resource-strength-badge Evidence strength resource-provenance-badge resource-coverage-badge Coverage Strongest evidence resource-evidence-link Review evidence paper_lens.html#detail-seg-1",
    }.items():
        (tmp_path / name).write_text(
            '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
            "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}.flow-shell{min-height:560px}@media (max-width: 820px){body{max-width:100%}}</style></head>"
            f"<body>{marker}</body></html>",
            encoding="utf-8",
        )
    roadmap = {
        "profile": {"output_language": "en"},
        "paper_map": {"nodes": [{"id": "target"}, {"id": "method"}]},
        "paper_lens": {
            "segments": [{"id": "seg-1"}],
            "inline_explanations": [],
        },
        "study_tasks": [{"type": "explain"}, {"type": "derive"}, {"type": "reproduce"}, {"type": "critique"}],
        "mastery_evidence": {"required_evidence": [{"task_id": "explain"}]},
        "knowledge_graph": {"summary": {"edges": 12, "evidence_backed_edges": 5}},
        "study_bundle": {
            "resources": [
                {"title": "Target paper", "local_href": "assets/paper.pdf", "status": "downloaded"},
                {"title": "Support code", "local_href": "assets/code.zip", "status": "copied"},
            ]
        },
        "resource_library": [
            {
                "title": "Target paper",
                "metadata": {
                    "rag": {
                        "evidence_chunks": [
                            {
                                "snippet": "The paper evidence explains why the target resource is selected.",
                                "detail_anchor": "detail-seg-1",
                            }
                        ]
                    }
                },
            }
        ],
    }

    audit = build_report_audit(tmp_path, roadmap)

    statuses = {item["id"]: item["status"] for item in audit["competitive_benchmark"]["checks"]}
    assert statuses["explainpaper_contextual_explanations"] == "warn"
    assert statuses["scholarcy_structured_review_cards"] == "warn"
    assert audit["market_readiness"]["status"] == "needs_improvement"


def test_field_course_report_can_be_market_ready_without_paper_map_or_lens(tmp_path):
    for name, marker in {
        "index.html": "Start Here Bring Your Own Paper 10-minute quickstart data-market-value-panel Why this is more than a PDF summarizer intent-router-panel data-intent-router Choose by what you need data-learning-guide-panel 3 starter questions data-starter-question fields-study-flow ask fresh-user-flow-panel data-fresh-user-flow roadmap.html Local assets report-health-panel Report Health Evidence coverage 4 evidence-backed edges report_audit.json scenario-panel Three Learning Scenarios Single paper Paper set Field / course route",
        "roadmap.html": "learning console mastery 1-minute start data-mastery-export Download worksheet resource-list resource-purpose-badge Why read resource-strength-badge Evidence strength resource-provenance-badge resource-coverage-badge Coverage Strongest evidence resource-evidence-link Review evidence",
    }.items():
        (tmp_path / name).write_text(
            '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
            "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}@media (max-width: 820px){body{max-width:100%}}</style></head>"
            f"<body>{marker}</body></html>",
            encoding="utf-8",
        )
    roadmap = {
        "profile": {"output_language": "en", "target_kind": "field", "goal": "learn diffusion models"},
        "phases": [
            {"name": "Prerequisites", "objective": "Review probability, score matching, and neural network basics."},
            {"name": "Core concepts", "objective": "Understand forward noise, reverse denoising, and training objectives."},
            {"name": "Project", "objective": "Run a tiny denoising experiment and explain the failure modes."},
            {"name": "Synthesis", "objective": "Compare DDPM, score-based models, and guided sampling."},
        ],
        "learning_key_points": ["forward diffusion", "reverse denoising", "score matching", "guided sampling"],
        "focus_areas": ["math intuition", "implementation", "evaluation"],
        "knowledge_graph": {"summary": {"concepts": 5, "resources": 4, "tasks": 4, "assessments": 4, "edges": 14, "evidence_backed_edges": 4}},
        "study_tasks": [
            {"type": "explain", "title": "Explain diffusion"},
            {"type": "derive", "title": "Derive objective"},
            {"type": "reproduce", "title": "Run tiny sampler"},
            {"type": "critique", "title": "Compare limits"},
        ],
        "mastery_evidence": {"required_evidence": [{"task_id": "explain"}, {"task_id": "derive"}, {"task_id": "reproduce"}, {"task_id": "critique"}]},
        "study_bundle": {
            "resources": [
                {"title": "DDPM paper", "local_href": "assets/ddpm.pdf", "status": "downloaded"},
                {"title": "Course notes", "local_href": "assets/notes.html", "status": "snapshotted"},
                {"title": "Tiny project", "local_href": "artifact_template/README.md", "status": "generated"},
                {"title": "Checklist", "local_href": "assets/checklist.md", "status": "generated"},
            ]
        },
        "resource_library": [
            {
                "title": "DDPM paper",
                "metadata": {
                    "rag": {
                        "evidence_chunks": [
                            {
                                "snippet": "Forward diffusion evidence supports this field route resource.",
                                "local_href": "assets/ddpm.pdf",
                                "score": 2.2,
                            }
                        ]
                    }
                },
            }
        ],
    }

    audit = build_report_audit(tmp_path, roadmap)

    assert audit["competitive_benchmark"]["status"] == "pass"
    assert audit["market_readiness"]["status"] == "market_ready"
    assert audit["market_readiness"]["competitive_positioning"]["product_wedge"] == "field_course_mastery_path"


def test_competitive_benchmark_blocks_market_ready_when_core_wedge_is_missing(tmp_path):
    (tmp_path / "roadmap.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>learning console links only</body></html>",
        encoding="utf-8",
    )
    roadmap = {
        "profile": {"output_language": "en"},
        "study_tasks": [{"type": "explain"}],
        "study_bundle": {"resources": [{"title": "External paper", "status": "link-only"}]},
    }

    audit = build_report_audit(tmp_path, roadmap)

    benchmark = audit["competitive_benchmark"]
    assert benchmark["status"] == "warn"
    assert benchmark["summary"]["warnings"] >= 3
    assert any(item["id"] == "get_it_measurable_mastery_map" and item["status"] == "warn" for item in benchmark["checks"])
    assert any(item["id"] == "paperqa_grounded_evidence" and item["status"] == "warn" for item in benchmark["checks"])
    assert any(item["id"] == "notebooklm_portable_study_outputs" and item["status"] == "warn" for item in benchmark["checks"])
    assert any(item["id"] == "resource_evidence_review_links" and item["status"] == "warn" for item in benchmark["checks"])
    assert audit["market_readiness"]["status"] == "needs_improvement"


def test_resource_provenance_coverage_requires_both_markers(tmp_path):
    (tmp_path / "roadmap.html").write_text(
        '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
        "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}</style></head>"
        "<body>learning console mastery 1-minute start resource-list "
        "resource-purpose-badge Why read resource-strength-badge Evidence strength "
        "resource-coverage-badge Coverage Strongest evidence resource-evidence-link Review evidence</body></html>",
        encoding="utf-8",
    )
    roadmap = {
        "profile": {"target_kind": "field", "output_language": "en"},
        "study_tasks": [{"type": "explain"}, {"type": "reproduce"}],
        "study_bundle": {
            "resources": [
                {"title": "Local paper", "local_href": "assets/paper.pdf", "status": "downloaded"},
                {"title": "Local code", "local_href": "assets/code.zip", "status": "copied"},
            ]
        },
    }

    audit = build_report_audit(tmp_path, roadmap)

    benchmark_statuses = {item["id"]: item["status"] for item in audit["competitive_benchmark"]["checks"]}
    experience_statuses = {item["id"]: item["status"] for item in audit["experience_risks"]["checks"]}
    assert benchmark_statuses["resource_provenance_coverage"] == "warn"
    assert experience_statuses["resource_provenance_coverage"] == "warn"


def test_competitive_benchmark_recognizes_chinese_react_report_terms(tmp_path):
    for name, marker in {
        "index.html": "从这里开始 换成自己的论文 10 分钟入门 intent-router-panel data-intent-router 按你的目的选择入口",
        "paper_map.html": "阅读密度 速览主链 完整探索 证据覆盖 下载汇报稿.md data-paper-map-canvas react-flow",
        "paper_lens.html": "段落精读 段落解释支撑度 不是资源可信度",
        "roadmap.html": "学习中控台 掌握验收 1-minute start resource-list",
    }.items():
        (tmp_path / name).write_text(
            '<!doctype html><html><head><meta name="viewport" content="width=device-width">'
            "<style>body{font-family:Arial;max-width:100%;overflow-wrap:anywhere}.flow-shell{min-height:560px}@media (max-width: 820px){body{max-width:100%}}</style></head>"
            f"<body>{marker}</body></html>",
            encoding="utf-8",
        )
    roadmap = {
        "profile": {"output_language": "zh-CN"},
        "paper_map": {"nodes": [{"id": "target"}, {"id": "background"}, {"id": "method"}]},
        "paper_lens": {
            "segments": [{"id": "seg-1"}, {"id": "seg-2"}],
            "inline_explanations": [
                {"plain_meaning": "这段说明论文为什么要解决规划任务。", "confidence": 0.81},
                {"plain_meaning": "这段说明方法如何把逻辑链条转成训练数据。", "confidence": 0.76},
            ],
        },
        "study_tasks": [{"type": "explain"}, {"type": "derive"}, {"type": "reproduce"}, {"type": "critique"}],
        "mastery_evidence": {"required_evidence": [{"task_id": "explain"}]},
        "knowledge_graph": {"summary": {"edges": 8, "evidence_backed_edges": 3}},
        "study_bundle": {
            "resources": [
                {"title": "目标论文", "local_href": "assets/paper.pdf", "status": "downloaded"},
                {"title": "代码", "local_href": "assets/code.zip", "status": "copied"},
            ]
        },
    }

    audit = build_report_audit(tmp_path, roadmap)

    failed_ids = {item["id"] for item in audit["competitive_benchmark"]["checks"] if item["status"] != "pass"}
    experience_statuses = {item["id"]: item["status"] for item in audit["experience_risks"]["checks"]}
    assert "roadmap_interactive_first_step" not in failed_ids
    assert "xyflow_canvas_affordance" not in failed_ids
    assert experience_statuses["paper_map_evidence_coverage"] == "pass"
    assert experience_statuses["paper_lens_support_explainer"] == "pass"
    assert experience_statuses["fresh_user_one_minute_start"] == "pass"
    assert experience_statuses["paper_map_presentation_export"] == "pass"
