from __future__ import annotations

import json
import math
import re
import hashlib
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PRIVATE_PATH_RE = re.compile(r"(?:file://[^\s)\]}\"'<]+|\\\\[A-Za-z0-9._$-]+[\\/][A-Za-z0-9._$-]+(?:[\\/][^)\]}\"'<\r\n]+)?|(?<![A-Za-z0-9])[A-Za-z]:[\\/][^)\]}\"'<\r\n]+|/(?:Users|home)/[^)\]}\"'<\r\n]+)")
VISIBLE_MOJIBAKE_RE = re.compile(r"(?:\ufffd|锟斤拷|Ã.|Â.|â[€\x80-\x9f]|ðŸ)")


VISIBLE_DECORATIVE_ELLIPSIS_RE = re.compile(r"(?:\.\.\.|…)")
PAYLOAD_DECORATIVE_ELLIPSIS_RE = re.compile(r"(?:\.\.\.|…|\\u2026)", re.IGNORECASE)
FIELDS_STUDY_FLOW_DATA_RE = re.compile(
    r"(?is)<script\b(?=[^>]*\bid=[\"']fields-study-flow-data[\"'])(?=[^>]*\btype=[\"']application/json[\"'])[^>]*>(.*?)</script>"
)
BROWSER_SNAPSHOT_VIEWPORTS = (
    {"id": "desktop-1280x720", "width": 1280, "height": 720},
    {"id": "mobile-390x844", "width": 390, "height": 844},
)
MARKET_SAMPLE_SCENARIOS = ("single-paper", "paper-set", "field-course")
BrowserSnapshotRenderer = Callable[[Path, dict[str, int | str], Path], dict[str, Any] | None]
BrowserInteractionRunner = Callable[[Path], dict[str, Any] | None]


class BrowserSnapshotUnavailable(RuntimeError):
    """Raised when optional browser screenshot capture cannot run on this machine."""


def audit_report_directory(report_dir: Path | str) -> dict[str, Any]:
    root = Path(report_dir)
    checks: list[dict[str, str]] = []
    html_files = sorted(path for path in root.glob("*.html") if path.is_file())
    for html_file in html_files:
        try:
            html = html_file.read_text(encoding="utf-8")
        except OSError as exc:
            checks.append(_check(html_file.name, "readable", "fail", str(exc)))
            continue
        checks.extend(_audit_html_file(html_file.name, html))
    failed = [item for item in checks if item["status"] == "fail"]
    return {
        "status": "fail" if failed else "pass",
        "summary": {
            "checked_files": len(html_files),
            "checks": len(checks),
            "failed_checks": len(failed),
        },
        "checks": checks,
    }


def audit_report_directory_json(report_dir: Path | str) -> str:
    return json.dumps(audit_report_directory(report_dir), ensure_ascii=False, indent=2)


def build_report_audit(report_dir: Path | str, roadmap: dict[str, Any]) -> dict[str, Any]:
    """Build the shareable audit artifact for an exported report directory."""

    root = Path(report_dir)
    surfaces = _report_surfaces(root)
    visual_audit = audit_report_directory(root)
    experience_risks = _experience_risks(root, roadmap, surfaces, visual_audit)
    fresh_user_flow = _fresh_user_flow(root, roadmap, surfaces)
    viewport_risks = _viewport_risks(root, roadmap, surfaces, visual_audit)
    visual_snapshot_matrix = _visual_snapshot_matrix(root, roadmap, surfaces, visual_audit)
    competitive_benchmark = _competitive_benchmark(root, roadmap, surfaces, visual_audit, experience_risks, viewport_risks)
    return {
        "status": visual_audit["status"],
        "recommended_first_action": _recommended_first_action(roadmap, surfaces),
        "surfaces": surfaces,
        "visual_audit": visual_audit,
        "experience_risks": experience_risks,
        "fresh_user_flow": fresh_user_flow,
        "viewport_risks": viewport_risks,
        "visual_snapshot_matrix": visual_snapshot_matrix,
        "competitive_benchmark": competitive_benchmark,
        "market_readiness": _market_readiness(
            roadmap,
            surfaces,
            visual_audit,
            experience_risks,
            fresh_user_flow,
            viewport_risks,
            visual_snapshot_matrix,
            competitive_benchmark,
        ),
    }


def write_report_audit(report_dir: Path | str, roadmap: dict[str, Any]) -> dict[str, Any]:
    audit = build_report_audit(report_dir, roadmap)
    target = Path(report_dir) / "report_audit.json"
    target.write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    return audit


def evaluate_market_sample_matrix(
    report_dirs: list[Path | str],
    *,
    required_scenarios: tuple[str, ...] = MARKET_SAMPLE_SCENARIOS,
) -> dict[str, Any]:
    """Evaluate whether market-readiness evidence spans the core product scenarios.

    A single polished demo is useful, but it is weak proof for a market-facing
    product that promises single-paper, paper-set, and field/course learning.
    This matrix keeps that claim honest without changing the default one-report
    audit flow.
    """

    samples: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    coverage = {scenario: 0 for scenario in required_scenarios}
    for raw_dir in report_dirs:
        sample = _market_sample_summary(Path(raw_dir))
        samples.append(sample)
        scenario = str(sample.get("scenario") or "unknown")
        if scenario in coverage and sample.get("sample_status") == "pass":
            coverage[scenario] += 1
        checks.extend(_market_sample_checks(sample))
    for scenario in required_scenarios:
        checks.append(
            _experience_check(
                f"scenario_coverage:{scenario}",
                f"{scenario} sample coverage",
                coverage.get(scenario, 0) > 0,
                f"Add at least one passing {scenario} report to the market sample matrix before claiming broad market readiness.",
            )
        )
    failures = [item for item in checks if item.get("status") == "fail"]
    warnings = [item for item in checks if item.get("status") == "warn"]
    missing = [scenario for scenario in required_scenarios if coverage.get(scenario, 0) == 0]
    return {
        "status": "fail" if failures else ("warn" if warnings else "pass"),
        "summary": {
            "sample_count": len(samples),
            "required_scenarios": list(required_scenarios),
            "covered_scenarios": [scenario for scenario in required_scenarios if coverage.get(scenario, 0) > 0],
            "missing_scenarios": missing,
            "checks": len(checks),
            "failures": len(failures),
            "warnings": len(warnings),
        },
        "samples": samples,
        "checks": checks,
    }


def capture_browser_snapshots(
    report_dir: Path | str,
    *,
    output_dir: Path | str | None = None,
    surfaces: list[str] | None = None,
    renderer: BrowserSnapshotRenderer | None = None,
) -> dict[str, Any]:
    """Optionally capture desktop/mobile screenshots for exported report pages.

    The default renderer uses Python Playwright when it is installed. Missing
    browser tooling is reported as a skipped optional check so the base offline
    report flow stays lightweight.
    """

    root = Path(report_dir)
    snapshot_root = Path(output_dir) if output_dir else root / "visual-snapshots"
    html_names = surfaces or _report_surfaces(root)
    html_files = [root / name for name in html_names if name.endswith(".html") and (root / name).is_file()]
    checks: list[dict[str, Any]] = []
    captures: list[dict[str, Any]] = []
    if not html_files:
        result = _browser_snapshot_result(
            "skipped",
            checks,
            captures,
            "No HTML report surfaces were found to capture.",
            snapshot_root,
        )
        _write_browser_snapshot_manifest(snapshot_root, result)
        return result
    renderer = renderer or _playwright_snapshot_renderer
    try:
        snapshot_root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _browser_snapshot_result("fail", checks, captures, f"Could not create screenshot directory: {exc}", snapshot_root)
    for html_file in html_files:
        for viewport in BROWSER_SNAPSHOT_VIEWPORTS:
            screenshot_file = snapshot_root / f"{html_file.stem}.{viewport['id']}.png"
            try:
                render_metadata = renderer(html_file, viewport, screenshot_file) or {}
            except BrowserSnapshotUnavailable as exc:
                result = _browser_snapshot_result("skipped", checks, captures, str(exc), snapshot_root)
                _write_browser_snapshot_manifest(snapshot_root, result)
                return result
            except Exception as exc:  # pragma: no cover - exact browser failures vary by platform.
                checks.append(
                    {
                        "file": html_file.name,
                        "viewport": viewport["id"],
                        "status": "fail",
                        "message": str(exc),
                    }
                )
                continue
            relative_path = _relative_posix_path(screenshot_file, root)
            checks.append(
                {
                    "file": html_file.name,
                    "viewport": viewport["id"],
                    "check": "screenshot_file",
                    "status": "pass",
                    "path": relative_path,
                }
            )
            checks.extend(_browser_render_metadata_checks(html_file.name, str(viewport["id"]), render_metadata))
            captures.append(
                {
                    "file": html_file.name,
                    "viewport": viewport["id"],
                    "width": viewport["width"],
                    "height": viewport["height"],
                    "path": relative_path,
                    **_snapshot_file_fingerprint(screenshot_file),
                    **_public_browser_render_metadata(render_metadata),
                }
            )
    result = _browser_snapshot_result("fail" if any(item["status"] == "fail" for item in checks) else "pass", checks, captures, "", snapshot_root)
    _write_browser_snapshot_manifest(snapshot_root, result)
    return result


def compare_browser_snapshot_baseline(current: dict[str, Any], baseline: Path | str | dict[str, Any]) -> dict[str, Any]:
    """Compare current browser snapshot metadata with a saved golden manifest."""

    baseline_data = _load_snapshot_baseline(baseline)
    current_captures = _capture_index(current)
    baseline_captures = _capture_index(baseline_data)
    checks: list[dict[str, Any]] = []
    if not baseline_captures:
        checks.append(
            {
                "id": "baseline_has_captures",
                "status": "fail",
                "message": "Snapshot baseline does not contain any captures.",
            }
        )
    for key, expected in sorted(baseline_captures.items()):
        current_item = current_captures.get(key)
        file_name, viewport = key
        present = current_item is not None
        checks.append(
            {
                "id": f"snapshot_present:{file_name}:{viewport}",
                "file": file_name,
                "viewport": viewport,
                "status": "pass" if present else "fail",
                "message": "Current snapshot exists for the baseline capture." if present else "Current snapshot is missing for the baseline capture.",
            }
        )
        if not current_item:
            continue
        size_matches = int(current_item.get("width") or 0) == int(expected.get("width") or 0) and int(current_item.get("height") or 0) == int(expected.get("height") or 0)
        checks.append(
            {
                "id": f"snapshot_viewport:{file_name}:{viewport}",
                "file": file_name,
                "viewport": viewport,
                "status": "pass" if size_matches else "fail",
                "message": "Viewport dimensions match the baseline." if size_matches else "Viewport dimensions differ from the baseline.",
            }
        )
        expected_hash = expected.get("sha256")
        current_hash = current_item.get("sha256")
        if expected_hash and current_hash:
            checks.append(
                {
                    "id": f"snapshot_hash:{file_name}:{viewport}",
                    "file": file_name,
                    "viewport": viewport,
                    "status": "pass" if current_hash == expected_hash else "fail",
                    "message": "Screenshot hash matches the baseline." if current_hash == expected_hash else "Screenshot hash differs from the baseline.",
                }
            )
    failed = [item for item in checks if item.get("status") == "fail"]
    return {
        "status": "fail" if failed else "pass",
        "summary": {
            "mode": "browser-snapshot-baseline",
            "baseline_captures": len(baseline_captures),
            "current_captures": len(current_captures),
            "checks": len(checks),
            "failed_checks": len(failed),
        },
        "checks": checks,
    }


def probe_browser_interactions(
    report_dir: Path | str,
    *,
    surfaces: list[str] | None = None,
    runner: BrowserInteractionRunner | None = None,
) -> dict[str, Any]:
    """Optionally smoke-test exported report interactions in a real browser."""

    root = Path(report_dir)
    html_names = surfaces or _report_surfaces(root)
    interactive_names = {"paper_map.html", "paper_lens.html", "roadmap.html"}
    html_files = [
        root / name
        for name in html_names
        if name in interactive_names and name.endswith(".html") and (root / name).is_file()
    ]
    checks: list[dict[str, Any]] = []
    probes: list[dict[str, Any]] = []
    if not html_files:
        return _browser_interaction_result(
            "skipped",
            checks,
            probes,
            "No interactive report surfaces were found to probe.",
        )
    runner = runner or _playwright_interaction_runner
    for html_file in html_files:
        try:
            metadata = runner(html_file) or {}
        except BrowserSnapshotUnavailable as exc:
            return _browser_interaction_result("skipped", checks, probes, str(exc))
        except Exception as exc:  # pragma: no cover - exact browser failures vary by platform.
            checks.append(
                {
                    "file": html_file.name,
                    "check": "interaction_probe",
                    "status": "fail",
                    "message": str(exc),
                }
            )
            continue
        checks.extend(_browser_interaction_metadata_checks(html_file.name, metadata))
        probes.append({"file": html_file.name, **_public_browser_interaction_metadata(metadata)})
    failed = [item for item in checks if item.get("status") == "fail"]
    return _browser_interaction_result("fail" if failed else "pass", checks, probes, "")


def evaluate_fresh_user_timing(measured_minutes: float, *, target_minutes: float = 10.0) -> dict[str, Any]:
    """Evaluate whether a fresh learner reached the first mastery task quickly enough."""

    measured = round(float(measured_minutes), 2)
    target = round(float(target_minutes), 2)
    if not math.isfinite(measured) or not math.isfinite(target) or measured <= 0 or target <= 0:
        raise ValueError("fresh-user timing values must be positive finite minutes")
    within_target = measured <= target
    checks = [
        {
            "id": "fresh_user_minutes_recorded",
            "status": "pass",
            "message": "A measured fresh-user run time was provided.",
        },
        {
            "id": "first_mastery_within_target",
            "status": "pass" if within_target else "fail",
            "message": (
                "Fresh learner reached the first mastery task within the target time."
                if within_target
                else "Fresh learner took longer than the target time to reach the first mastery task."
            ),
        },
    ]
    over_target = round(max(0.0, measured - target), 2)
    minutes_saved = round(max(0.0, target - measured), 2)
    return {
        "status": "pass" if within_target else "fail",
        "summary": {
            "mode": "fresh-user-timing",
            "measured_minutes": measured,
            "target_minutes": target,
            "minutes_saved": minutes_saved,
            "minutes_over_target": over_target,
        },
        "checks": checks,
    }


def write_fresh_user_worksheet(
    report_dir: Path | str,
    *,
    target_minutes: float = 10.0,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Write a manual first-run usability worksheet next to an exported report."""

    root = Path(report_dir)
    target = Path(output_path) if output_path else root / "fresh_user_test.md"
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_fresh_user_worksheet_markdown(float(target_minutes)), encoding="utf-8")
    except OSError as exc:
        return {
            "status": "fail",
            "summary": {
                "path": _relative_posix_path(target, root),
                "target_minutes": round(float(target_minutes), 2),
                "error": str(exc),
            },
        }
    return {
        "status": "pass",
        "summary": {
            "path": _relative_posix_path(target, root),
            "target_minutes": round(float(target_minutes), 2),
            "checkpoints": 7,
        },
    }


def _fresh_user_worksheet_markdown(target_minutes: float) -> str:
    target = f"{round(float(target_minutes), 2):g}"
    return "\n".join(
        [
            "# Fresh User Test Worksheet",
            "",
            f"Target: reach the first mastery task within {target} minutes.",
            "",
            "Use this worksheet with a person who has not seen this report before. Start the timer when they open the report folder. Stop when they can point to the first mastery task and say what they would do next.",
            "",
            "## Run Info",
            "",
            "- Report folder nickname:",
            "- Tester role / background:",
            "- Date:",
            "- Measured minutes:",
            "- Did the user reach the first mastery task? yes / no",
            "",
            "## Checkpoints",
            "",
            "| Step | Expected action | Time | Blocker / confusion | Product fix idea |",
            "| --- | --- | --- | --- | --- |",
            "| 1 | Open `index.html` | | | |",
            "| 2 | Identify the recommended first action | | | |",
            "| 3 | Open `paper_map.html` or the recommended map/route entry | | | |",
            "| 4 | Explain the main logic chain in one sentence | | | |",
            "| 5 | Open `paper_lens.html` or the paragraph/detail reader | | | |",
            "| 6 | Open one local resource or resource-library item | | | |",
            "| 7 | Find the first mastery task and describe the next concrete action | | | |",
            "",
            "## Notes",
            "",
            "- What wording was unclear?",
            "- Which button, link, or panel did the user miss?",
            "- Which page felt visually crowded?",
            "- What should be moved earlier, hidden, or renamed?",
            "",
            "## Audit Command",
            "",
            "After timing the run, record the result with:",
            "",
            "```bash",
            "fields-study-flow audit-report --report-dir . --fresh-user-minutes <measured-minutes>",
            "```",
            "",
        ]
    )


def summarize_fresh_user_worksheets(worksheet_paths: list[Path | str]) -> dict[str, Any]:
    """Aggregate completed fresh-user worksheets into a ranked blocker backlog."""

    entries: list[dict[str, str]] = []
    unreadable = 0
    for worksheet_path in worksheet_paths:
        path = Path(worksheet_path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            unreadable += 1
            continue
        entries.extend(_fresh_user_blocker_entries(text))
    groups: dict[str, dict[str, Any]] = {}
    for entry in entries:
        blocker = _sanitize_public_text(entry["blocker"])
        if not blocker:
            continue
        key = _normalize_blocker(blocker)
        group = groups.setdefault(
            key,
            {
                "blocker": blocker,
                "occurrences": 0,
                "steps": set(),
                "fix_ideas": [],
                "examples": [],
            },
        )
        group["occurrences"] += 1
        if entry.get("step"):
            group["steps"].add(entry["step"])
        fix = _sanitize_public_text(entry.get("fix_idea", ""))
        if fix and fix not in group["fix_ideas"]:
            group["fix_ideas"].append(fix)
        if blocker not in group["examples"]:
            group["examples"].append(blocker)
    backlog = []
    for group in groups.values():
        occurrences = int(group["occurrences"])
        steps = sorted(group["steps"], key=_step_sort_key)
        backlog.append(
            {
                "blocker": group["blocker"],
                "occurrences": occurrences,
                "priority_score": occurrences * 10 + len(steps),
                "steps": steps,
                "fix_ideas": group["fix_ideas"],
                "examples": group["examples"][:3],
            }
        )
    backlog.sort(key=lambda item: (-int(item["priority_score"]), str(item["blocker"]).lower()))
    return {
        "status": "pass" if worksheet_paths and not unreadable else "warn",
        "summary": {
            "worksheets": len(worksheet_paths),
            "unreadable": unreadable,
            "blockers": len(entries),
            "unique_blockers": len(backlog),
        },
        "backlog": backlog,
    }


def write_fresh_user_backlog(
    worksheet_paths: list[Path | str],
    report_dir: Path | str,
    *,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(report_dir)
    target = Path(output_path) if output_path else root / "fresh_user_backlog.md"
    summary = summarize_fresh_user_worksheets(worksheet_paths)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_fresh_user_backlog_markdown(summary), encoding="utf-8")
    except OSError as exc:
        return {
            "status": "fail",
            "summary": {
                **summary.get("summary", {}),
                "path": _relative_posix_path(target, root),
                "error": str(exc),
            },
            "backlog": summary.get("backlog", []),
        }
    return {
        "status": "pass" if summary.get("status") == "pass" else "warn",
        "summary": {
            **summary.get("summary", {}),
            "path": _relative_posix_path(target, root),
        },
        "backlog": summary.get("backlog", []),
    }


def summarize_fresh_user_backlogs(backlog_paths: list[Path | str]) -> dict[str, Any]:
    """Aggregate ranked fresh-user backlog files into a cross-report trend summary."""

    items: list[dict[str, Any]] = []
    unreadable = 0
    for backlog_path in backlog_paths:
        path = Path(backlog_path)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            unreadable += 1
            continue
        for item in _fresh_user_backlog_items(text):
            item["report"] = path.name
            items.append(item)
    groups: dict[str, dict[str, Any]] = {}
    for item in items:
        blocker = _sanitize_public_text(str(item.get("blocker") or ""))
        if not blocker or blocker == "No blockers recorded yet":
            continue
        key = _normalize_blocker(blocker)
        group = groups.setdefault(
            key,
            {
                "blocker": blocker,
                "total_occurrences": 0,
                "reports": set(),
                "steps": set(),
                "fix_ideas": [],
            },
        )
        group["total_occurrences"] += int(item.get("occurrences") or 0)
        if item.get("report"):
            group["reports"].add(item["report"])
        for step in item.get("steps", []):
            group["steps"].add(str(step))
        for fix in item.get("fix_ideas", []):
            clean_fix = _sanitize_public_text(str(fix))
            if clean_fix and clean_fix != "-" and clean_fix not in group["fix_ideas"]:
                group["fix_ideas"].append(clean_fix)
    trends = []
    for group in groups.values():
        reports = len(group["reports"])
        total_occurrences = int(group["total_occurrences"])
        trend = "recurring" if reports >= 2 else "single-report"
        trends.append(
            {
                "blocker": group["blocker"],
                "total_occurrences": total_occurrences,
                "reports": reports,
                "trend": trend,
                "priority_score": reports * 100 + total_occurrences * 10 + len(group["steps"]),
                "steps": sorted(group["steps"], key=_step_sort_key),
                "fix_ideas": group["fix_ideas"],
            }
        )
    trends.sort(key=lambda item: (-int(item["priority_score"]), str(item["blocker"]).lower()))
    recurring = sum(1 for item in trends if item["trend"] == "recurring")
    return {
        "status": "pass" if backlog_paths and not unreadable else "warn",
        "summary": {
            "backlog_files": len(backlog_paths),
            "unreadable": unreadable,
            "blocker_rows": len(items),
            "unique_blockers": len(trends),
            "recurring_blockers": recurring,
        },
        "trends": trends,
    }


def write_fresh_user_trend_report(
    backlog_paths: list[Path | str],
    report_dir: Path | str,
    *,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    root = Path(report_dir)
    target = Path(output_path) if output_path else root / "fresh_user_trends.md"
    summary = summarize_fresh_user_backlogs(backlog_paths)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_fresh_user_trend_report_markdown(summary), encoding="utf-8")
    except OSError as exc:
        return {
            "status": "fail",
            "summary": {
                **summary.get("summary", {}),
                "path": _relative_posix_path(target, root),
                "error": str(exc),
            },
            "trends": summary.get("trends", []),
        }
    return {
        "status": "pass" if summary.get("status") == "pass" else "warn",
        "summary": {
            **summary.get("summary", {}),
            "path": _relative_posix_path(target, root),
        },
        "trends": summary.get("trends", []),
    }


def write_release_readiness_report(
    report_dir: Path | str,
    audit_result: dict[str, Any],
    *,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Write a human-readable release decision dashboard for exported reports."""

    root = Path(report_dir)
    target = Path(output_path) if output_path else root / "release_readiness.md"
    html_target = target.with_suffix(".html")
    report_audit = _load_report_audit(root)
    summary = _release_readiness_summary(report_audit, audit_result)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(_release_readiness_markdown(summary), encoding="utf-8")
        html_target.write_text(_release_readiness_html(summary), encoding="utf-8")
        _attach_release_readiness_index_entry(root, summary, html_target)
    except OSError as exc:
        return {
            "status": "fail",
            "summary": {
                **summary,
                "path": _relative_posix_path(target, root),
                "html_path": _relative_posix_path(html_target, root),
                "error": str(exc),
            },
        }
    return {
        "status": summary["status"],
        "summary": {
            **summary,
            "path": _relative_posix_path(target, root),
            "html_path": _relative_posix_path(html_target, root),
        },
    }


def write_release_readiness_history(
    report_dir: Path | str,
    release_readiness_result: dict[str, Any],
    *,
    output_path: Path | str | None = None,
) -> dict[str, Any]:
    """Append a sanitized release decision entry and rewrite a readable history."""

    root = Path(report_dir)
    target = Path(output_path) if output_path else root / "release_readiness_history.md"
    jsonl_target = target.with_suffix(".jsonl")
    html_target = target.with_suffix(".html")
    summary = release_readiness_result.get("summary") if isinstance(release_readiness_result.get("summary"), dict) else release_readiness_result
    summary = dict(summary)
    if not summary.get("status") and release_readiness_result.get("status"):
        summary["status"] = release_readiness_result["status"]
    entry = _release_readiness_history_entry(summary)
    entries = [*(_load_release_readiness_history(jsonl_target)), entry]
    trend = _release_readiness_history_trend(entries)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        jsonl_target.write_text("".join(json.dumps(item, ensure_ascii=False) + "\n" for item in entries), encoding="utf-8")
        target.write_text(_release_readiness_history_markdown(entries, trend), encoding="utf-8")
        html_target.write_text(_release_readiness_history_html(entries, trend), encoding="utf-8")
        _attach_release_history_index_entry(root, trend, html_target)
        _attach_release_history_readiness_entry(root, trend, html_target)
    except OSError as exc:
        return {
            "status": "fail",
            "summary": {
                "path": _relative_posix_path(target, root),
                "jsonl_path": _relative_posix_path(jsonl_target, root),
                "html_path": _relative_posix_path(html_target, root),
                "error": str(exc),
            },
        }
    return {
        "status": str(entry.get("status") or "pass"),
        "summary": {
            "path": _relative_posix_path(target, root),
            "jsonl_path": _relative_posix_path(jsonl_target, root),
            "html_path": _relative_posix_path(html_target, root),
            "entries": len(entries),
            "latest_decision": entry["decision"],
            **trend,
        },
    }


def _release_readiness_history_entry(summary: dict[str, Any]) -> dict[str, Any]:
    next_actions = summary.get("next_actions") if isinstance(summary.get("next_actions"), list) else []
    return {
        "recorded_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": _sanitize_public_text(str(summary.get("status") or "pass")),
        "decision": _sanitize_public_text(str(summary.get("decision") or "ship")),
        "score": int(summary.get("score") or 0),
        "market_status": _sanitize_public_text(str(summary.get("market_status") or "unknown")),
        "visual_status": _sanitize_public_text(str(summary.get("visual_status") or "unknown")),
        "benchmark_status": _sanitize_public_text(str(summary.get("benchmark_status") or "unknown")),
        "snapshot_status": _sanitize_public_text(str(summary.get("snapshot_status") or "not_run")),
        "baseline_status": _sanitize_public_text(str(summary.get("baseline_status") or "not_run")),
        "interaction_status": _sanitize_public_text(str(summary.get("interaction_status") or "not_run")),
        "fresh_user_timing_status": _sanitize_public_text(str(summary.get("fresh_user_timing_status") or "not_run")),
        "fresh_user_trend_status": _sanitize_public_text(str(summary.get("fresh_user_trend_status") or "not_run")),
        "recurring_blockers": int(summary.get("recurring_blockers") or 0),
        "release_report": _sanitize_public_text(str(summary.get("html_path") or summary.get("path") or "release_readiness.html")),
        "next_actions": [_sanitize_public_text(str(action)) for action in next_actions[:3] if action],
    }


def _load_release_readiness_history(jsonl_path: Path) -> list[dict[str, Any]]:
    try:
        lines = jsonl_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            entries.append(item)
    return entries


def _release_readiness_history_trend(entries: list[dict[str, Any]]) -> dict[str, Any]:
    if len(entries) < 2:
        return {
            "trend": "first_run",
            "score_delta": 0,
            "recurring_blockers_delta": 0,
        }
    previous = entries[-2]
    latest = entries[-1]
    score_delta = int(latest.get("score") or 0) - int(previous.get("score") or 0)
    blockers_delta = int(latest.get("recurring_blockers") or 0) - int(previous.get("recurring_blockers") or 0)
    if score_delta > 0 and blockers_delta <= 0:
        trend = "improving"
    elif score_delta < 0 or blockers_delta > 0:
        trend = "regressing"
    else:
        trend = "steady"
    return {
        "trend": trend,
        "score_delta": score_delta,
        "recurring_blockers_delta": blockers_delta,
    }


def _format_signed(value: int) -> str:
    return f"+{value}" if value > 0 else str(value)


def _release_readiness_history_markdown(entries: list[dict[str, Any]], trend: dict[str, Any] | None = None) -> str:
    trend = trend or _release_readiness_history_trend(entries)
    rows = [
        "# Release Readiness History",
        "",
        "A sanitized timeline of release decisions for comparing market readiness across report versions.",
        "",
        "## Trend Summary",
        "",
        f"- Trend: {trend.get('trend', 'first_run')}",
        f"- Score change: {_format_signed(int(trend.get('score_delta') or 0))}",
        f"- Recurring blockers change: {_format_signed(int(trend.get('recurring_blockers_delta') or 0))}",
        "",
        "| Run | Decision | Status | Score | Visual | Timing | Recurring blockers | Report | Next actions |",
        "| --- | --- | --- | ---: | --- | --- | ---: | --- | --- |",
    ]
    for item in entries:
        rows.append(
            "| {run} | {decision} | {status} | {score} | {visual} | {timing} | {blockers} | {report} | {actions} |".format(
                run=_markdown_cell(str(item.get("recorded_at") or "")),
                decision=_markdown_cell(str(item.get("decision") or "")),
                status=_markdown_cell(str(item.get("status") or "")),
                score=int(item.get("score") or 0),
                visual=_markdown_cell(str(item.get("visual_status") or "")),
                timing=_markdown_cell(str(item.get("fresh_user_timing_status") or "")),
                blockers=int(item.get("recurring_blockers") or 0),
                report=_markdown_cell(str(item.get("release_report") or "")),
                actions=_markdown_cell("; ".join(str(action) for action in item.get("next_actions", []) if action) or "-"),
            )
        )
    rows.append("")
    return "\n".join(rows)


def _release_readiness_history_html(entries: list[dict[str, Any]], trend: dict[str, Any] | None = None) -> str:
    trend = trend or _release_readiness_history_trend(entries)
    latest = entries[-1] if entries else {}
    rows = "".join(
        """
        <tr>
          <td>{run}</td><td>{decision}</td><td>{status}</td><td>{score}</td>
          <td>{visual}</td><td>{timing}</td><td>{blockers}</td><td>{report}</td><td>{actions}</td>
        </tr>
        """.format(
            run=_html_escape(str(item.get("recorded_at") or "")),
            decision=_html_escape(str(item.get("decision") or "")),
            status=_html_escape(str(item.get("status") or "")),
            score=int(item.get("score") or 0),
            visual=_html_escape(str(item.get("visual_status") or "")),
            timing=_html_escape(str(item.get("fresh_user_timing_status") or "")),
            blockers=int(item.get("recurring_blockers") or 0),
            report=_html_escape(str(item.get("release_report") or "")),
            actions=_html_escape("; ".join(str(action) for action in item.get("next_actions", []) if action) or "-"),
        )
        for item in entries
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Release Readiness History</title>
  <style>
    :root {{ color-scheme:light; --ink:#18201d; --muted:#657066; --line:#d9e2d7; --surface:#fffdfa; --soft:#f3f7ee; --accent:#2f6f73; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#f6f4ef; color:var(--ink); font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Noto Sans SC","Source Han Sans SC",Arial,sans-serif; line-height:1.65; }}
    .release-history {{ width:min(1180px, calc(100vw - 32px)); margin:0 auto; padding:28px 0 42px; overflow-wrap:anywhere; }}
    .hero, .panel {{ border:1px solid var(--line); border-radius:22px; background:var(--surface); box-shadow:0 18px 48px rgba(43,53,45,.09); }}
    .hero {{ padding:28px; }}
    .eyebrow {{ margin:0 0 8px; color:var(--accent); font-size:.82rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }}
    h1, h2, p {{ margin-top:0; }}
    h1 {{ margin-bottom:12px; font-size:clamp(2rem, 5vw, 3.8rem); line-height:1.08; letter-spacing:0; }}
    .trend-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; margin-top:18px; }}
    .trend-card {{ border:1px solid var(--line); border-radius:16px; padding:14px; background:var(--soft); min-width:0; }}
    .trend-card span {{ display:block; color:var(--muted); font-size:.85rem; }}
    .trend-card strong {{ display:block; margin-top:4px; font-size:1.2rem; }}
    .panel {{ margin-top:18px; padding:22px; }}
    .table-wrap {{ overflow-x:auto; }}
    table {{ width:100%; border-collapse:collapse; min-width:820px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:10px; text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:.82rem; }}
    @media (max-width:760px) {{ .release-history {{ width:min(100vw - 20px, 720px); }} .hero, .panel {{ border-radius:18px; }} }}
  </style>
</head>
<body>
  <main class="release-history" data-release-history-trend="{_html_escape(str(trend.get('trend') or 'first_run'))}">
    <section class="hero">
      <p class="eyebrow">Quality Trend / 质量趋势</p>
      <h1>Release Readiness History</h1>
      <p>用脱敏的跨版本记录判断报告是否真的变得更好，而不是只看单次通过。</p>
      <div class="trend-grid" aria-label="Trend Summary">
        <article class="trend-card"><span>Trend Summary</span><strong>{_html_escape(str(trend.get('trend') or 'first_run'))}</strong></article>
        <article class="trend-card"><span>Score change</span><strong>{_html_escape(_format_signed(int(trend.get('score_delta') or 0)))}</strong></article>
        <article class="trend-card"><span>Recurring blockers change</span><strong>{_html_escape(_format_signed(int(trend.get('recurring_blockers_delta') or 0)))}</strong></article>
        <article class="trend-card"><span>Latest decision</span><strong>{_html_escape(str(latest.get('decision') or '-'))}</strong></article>
      </div>
    </section>
    <section class="panel">
      <h2>Decision Timeline / 决策时间线</h2>
      <div class="table-wrap">
        <table>
          <thead><tr><th>Run</th><th>Decision</th><th>Status</th><th>Score</th><th>Visual</th><th>Timing</th><th>Blockers</th><th>Report</th><th>Next actions</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
    </section>
  </main>
</body>
</html>"""


def _attach_release_readiness_index_entry(root: Path, summary: dict[str, Any], html_target: Path) -> None:
    index_path = root / "index.html"
    try:
        html = index_path.read_text(encoding="utf-8")
    except OSError:
        return

    entry = _release_readiness_index_entry(summary, _relative_posix_path(html_target, root))
    marker = 'data-release-readiness-entry="true"'
    if marker in html:
        updated = re.sub(
            r"\s*<section\b(?=[^>]*data-release-readiness-entry=\"true\")[\s\S]*?</section>",
            "\n" + entry,
            html,
            count=1,
        )
    elif "</main>" in html:
        updated = html.replace("</main>", entry + "\n</main>", 1)
    elif "</body>" in html:
        updated = html.replace("</body>", entry + "\n</body>", 1)
    else:
        updated = html.rstrip() + "\n" + entry + "\n"
    index_path.write_text(updated, encoding="utf-8")


def _attach_release_history_index_entry(root: Path, trend: dict[str, Any], html_target: Path) -> None:
    index_path = root / "index.html"
    try:
        html = index_path.read_text(encoding="utf-8")
    except OSError:
        return

    entry = _release_history_index_entry(trend, _relative_posix_path(html_target, root))
    marker = 'data-release-history-entry="true"'
    if marker in html:
        updated = re.sub(
            r"\s*<section\b(?=[^>]*data-release-history-entry=\"true\")[\s\S]*?</section>",
            "\n" + entry,
            html,
            count=1,
        )
    elif "</main>" in html:
        updated = html.replace("</main>", entry + "\n</main>", 1)
    elif "</body>" in html:
        updated = html.replace("</body>", entry + "\n</body>", 1)
    else:
        updated = html.rstrip() + "\n" + entry + "\n"
    index_path.write_text(updated, encoding="utf-8")


def _attach_release_history_readiness_entry(root: Path, trend: dict[str, Any], html_target: Path) -> None:
    readiness_path = root / "release_readiness.html"
    try:
        html = readiness_path.read_text(encoding="utf-8")
    except OSError:
        return

    entry = _release_history_readiness_entry(trend, _relative_posix_path(html_target, root))
    marker = 'data-release-history-link="true"'
    if marker in html:
        updated = re.sub(
            r"\s*<section\b(?=[^>]*data-release-history-link=\"true\")[\s\S]*?</section>",
            "\n" + entry,
            html,
            count=1,
        )
    elif "</main>" in html:
        updated = html.replace("</main>", entry + "\n</main>", 1)
    elif "</body>" in html:
        updated = html.replace("</body>", entry + "\n</body>", 1)
    else:
        updated = html.rstrip() + "\n" + entry + "\n"
    readiness_path.write_text(updated, encoding="utf-8")


def _release_history_readiness_entry(trend: dict[str, Any], href: str) -> str:
    trend_label = _sanitize_public_text(str(trend.get("trend") or "first_run"))
    score_delta = _format_signed(int(trend.get("score_delta") or 0))
    blockers_delta = _format_signed(int(trend.get("recurring_blockers_delta") or 0))
    return f"""
<section class="panel release-history-link" data-release-history-link="true" aria-labelledby="release-history-link-title">
  <p class="eyebrow" id="release-history-link-title">Quality trend / 质量趋势</p>
  <h2>跨版本质量趋势</h2>
  <p>当前趋势：<strong>{_html_escape(trend_label)}</strong>，分数变化：<strong>{_html_escape(score_delta)}</strong>，反复卡点变化：<strong>{_html_escape(blockers_delta)}</strong>。如果本次决策可发布，再看趋势面板确认产品是否持续变好。</p>
  <p><a href="{_html_escape(href)}">打开质量趋势面板</a></p>
</section>""".strip()


def _release_history_index_entry(trend: dict[str, Any], href: str) -> str:
    trend_label = _sanitize_public_text(str(trend.get("trend") or "first_run"))
    score_delta = _format_signed(int(trend.get("score_delta") or 0))
    blockers_delta = _format_signed(int(trend.get("recurring_blockers_delta") or 0))
    return f"""
<section class="support-panel release-history-entry" data-release-history-entry="true" aria-labelledby="release-history-entry-title">
  <p class="eyebrow" id="release-history-entry-title">Quality trend / 质量趋势</p>
  <h2>发布质量趋势</h2>
  <p>当前趋势：<strong>{_html_escape(trend_label)}</strong>，分数变化：<strong>{_html_escape(score_delta)}</strong>，反复卡点变化：<strong>{_html_escape(blockers_delta)}</strong>。打开趋势面板可以比较多次发布是否真的更接近可用、好看、易上手。</p>
  <div class="support-links">
    <a href="{_html_escape(href)}">打开发布质量趋势</a>
  </div>
</section>""".strip()


def _release_readiness_index_entry(summary: dict[str, Any], href: str) -> str:
    decision = _sanitize_public_text(str(summary.get("decision") or "needs_work"))
    status = _sanitize_public_text(str(summary.get("status") or "warn"))
    score = int(summary.get("score") or 0)
    return f"""
<section class="support-panel release-readiness-entry" data-release-readiness-entry="true" aria-labelledby="release-readiness-entry-title">
  <p class="eyebrow" id="release-readiness-entry-title">Release decision / 发布决策</p>
  <h2>发布准备度面板</h2>
  <p>当前决策：<strong>{_html_escape(decision)}</strong>，状态：<strong>{_html_escape(status)}</strong>，市场准备度分数：<strong>{score}</strong>。打开面板可以一起检查视觉、证据、资料包、新用户上手和竞品启发门槛。</p>
  <div class="support-links">
    <a href="{_html_escape(href)}">打开发布准备度面板</a>
  </div>
</section>""".strip()


def _load_report_audit(root: Path) -> dict[str, Any]:
    try:
        data = json.loads((root / "report_audit.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _market_sample_summary(root: Path) -> dict[str, Any]:
    exists = root.exists() and root.is_dir()
    roadmap = _load_json_file(root / "roadmap.json") if exists else {}
    report_audit = _load_json_file(root / "report_audit.json") if exists else {}
    if exists and roadmap and not report_audit:
        try:
            report_audit = build_report_audit(root, roadmap)
        except Exception as exc:  # pragma: no cover - defensive for malformed exported reports.
            report_audit = {"status": "warn", "error": str(exc)}
    market = report_audit.get("market_readiness") if isinstance(report_audit.get("market_readiness"), dict) else {}
    visual = report_audit.get("visual_audit") if isinstance(report_audit.get("visual_audit"), dict) else {}
    benchmark = report_audit.get("competitive_benchmark") if isinstance(report_audit.get("competitive_benchmark"), dict) else {}
    has_roadmap = bool(roadmap)
    has_audit = bool(report_audit)
    market_ready = str(market.get("status") or "") == "market_ready"
    visual_pass = str(visual.get("status") or report_audit.get("status") or "") == "pass"
    benchmark_pass = str(benchmark.get("status") or "pass") == "pass"
    sample_status = "pass" if exists and has_roadmap and has_audit and market_ready and visual_pass and benchmark_pass else "warn"
    if not exists or not has_roadmap:
        sample_status = "fail"
    return {
        "report": _sanitize_public_text(root.name or "."),
        "scenario": _infer_market_sample_scenario(roadmap),
        "sample_status": sample_status,
        "exists": exists,
        "has_roadmap": has_roadmap,
        "has_report_audit": has_audit,
        "market_status": str(market.get("status") or "unknown"),
        "visual_status": str(visual.get("status") or report_audit.get("status") or "unknown"),
        "benchmark_status": str(benchmark.get("status") or "unknown"),
        "score": int(market.get("score") or 0),
    }


def _infer_market_sample_scenario(roadmap: dict[str, Any]) -> str:
    if not roadmap:
        return "unknown"
    if _has_paper_set(roadmap):
        return "paper-set"
    if _is_field_or_course_target(roadmap):
        return "field-course"
    profile = roadmap.get("profile") if isinstance(roadmap.get("profile"), dict) else {}
    target_kind = str(profile.get("target_kind") or roadmap.get("target_kind") or "").lower()
    if target_kind == "paper" or roadmap.get("paper_map") or roadmap.get("paper_lens"):
        return "single-paper"
    return "unknown"


def _has_paper_set(roadmap: dict[str, Any]) -> bool:
    if isinstance(roadmap.get("paper_set"), dict):
        return True
    target_papers = _list_at(roadmap, "paper_lens", "target_papers")
    if len(target_papers) > 1:
        return True
    profile = roadmap.get("profile") if isinstance(roadmap.get("profile"), dict) else {}
    target_kind = str(profile.get("target_kind") or roadmap.get("target_kind") or "").lower()
    return target_kind in {"paper-set", "multi-paper", "papers"}


def _market_sample_checks(sample: dict[str, Any]) -> list[dict[str, Any]]:
    label = str(sample.get("report") or "sample")
    return [
        _experience_check(
            f"sample_exists:{label}",
            f"{label} exists",
            bool(sample.get("exists")),
            "Remove missing sample directories or regenerate the market sample report before release review.",
        ),
        _experience_check(
            f"sample_roadmap:{label}",
            f"{label} has roadmap.json",
            bool(sample.get("has_roadmap")),
            "Every market sample must include roadmap.json so scenario and product-depth checks are auditable.",
        ),
        _experience_check(
            f"sample_audit:{label}",
            f"{label} has report_audit.json",
            bool(sample.get("has_report_audit")),
            "Run fields-study-flow audit-report for every market sample before aggregating the matrix.",
        ),
        _experience_check(
            f"sample_ready:{label}",
            f"{label} is market ready",
            sample.get("sample_status") == "pass",
            "Each sample should be market_ready with visual and competitor benchmark checks passing before it counts as proof.",
        ),
    ]


def _release_readiness_summary(report_audit: dict[str, Any], audit_result: dict[str, Any]) -> dict[str, Any]:
    market = report_audit.get("market_readiness") if isinstance(report_audit.get("market_readiness"), dict) else {}
    benchmark = report_audit.get("competitive_benchmark") if isinstance(report_audit.get("competitive_benchmark"), dict) else {}
    timing = audit_result.get("fresh_user_timing") if isinstance(audit_result.get("fresh_user_timing"), dict) else {}
    trend = audit_result.get("fresh_user_trend_report") if isinstance(audit_result.get("fresh_user_trend_report"), dict) else {}
    snapshot = audit_result.get("browser_snapshot_capture") if isinstance(audit_result.get("browser_snapshot_capture"), dict) else {}
    baseline = audit_result.get("browser_snapshot_baseline") if isinstance(audit_result.get("browser_snapshot_baseline"), dict) else {}
    interaction = audit_result.get("browser_interaction_probe") if isinstance(audit_result.get("browser_interaction_probe"), dict) else {}
    sample_matrix = audit_result.get("market_sample_matrix") if isinstance(audit_result.get("market_sample_matrix"), dict) else {}
    recurring = int(((trend.get("summary") if isinstance(trend.get("summary"), dict) else {}) or {}).get("recurring_blockers") or 0)
    visual_status = str(audit_result.get("status") or "unknown")
    market_status = str(market.get("status") or "unknown")
    snapshot_status = str(snapshot.get("status") or "not_run")
    baseline_status = str(baseline.get("status") or "not_run")
    interaction_status = str(interaction.get("status") or "not_run")
    timing_status = str(timing.get("status") or "not_run")
    trend_status = str(trend.get("status") or "not_run")
    sample_matrix_status = str(sample_matrix.get("status") or "not_run")
    has_visual_evidence = snapshot_status == "pass" or baseline_status == "pass"
    has_interaction_evidence = interaction_status == "pass"
    hard_fail = visual_status == "fail" or snapshot_status == "fail" or baseline_status == "fail" or interaction_status == "fail"
    needs_work = (
        market_status != "market_ready"
        or timing_status not in {"pass", "skipped"}
        or not has_visual_evidence
        or not has_interaction_evidence
        or trend_status not in {"pass", "skipped", "not_run"}
        or sample_matrix_status not in {"pass", "skipped", "not_run"}
        or recurring > 0
    )
    if hard_fail:
        decision = "do_not_ship"
        status = "fail"
    elif needs_work:
        decision = "needs_work"
        status = "warn"
    else:
        decision = "ship"
        status = "pass"
    summary = {
        "status": status,
        "decision": decision,
        "score": int(market.get("score") or 0),
        "market_status": market_status,
        "visual_status": visual_status,
        "benchmark_status": str(benchmark.get("status") or "unknown"),
        "snapshot_status": snapshot_status,
        "baseline_status": baseline_status,
        "interaction_status": interaction_status,
        "fresh_user_timing_status": timing_status,
        "fresh_user_trend_status": trend_status,
        "market_sample_matrix_status": sample_matrix_status,
        "market_sample_matrix_summary": sample_matrix.get("summary", {}) if isinstance(sample_matrix.get("summary"), dict) else {},
        "recurring_blockers": recurring,
        "dimensions": [item for item in market.get("dimensions", []) if isinstance(item, dict)],
        "benchmark_warnings": [
            item
            for item in benchmark.get("checks", [])
            if isinstance(item, dict) and item.get("status") not in {"pass", None}
        ],
        "next_actions": _release_next_actions(market, benchmark, trend, timing, snapshot, baseline, interaction, sample_matrix),
        "trends": [item for item in trend.get("trends", []) if isinstance(item, dict)],
    }
    summary["market_positioning"] = _market_positioning_matrix(summary)
    summary["market_opportunity_backlog"] = _market_opportunity_backlog(summary)
    summary["market_experience_scorecard"] = _market_experience_scorecard(summary)
    return summary


def _market_positioning_matrix(summary: dict[str, Any]) -> list[dict[str, str]]:
    """Translate competitor lessons into current product proof requirements."""

    evidence_signal = _dimension_signal(summary, "learning_depth", "plain_explanation")
    navigation_signal = _dimension_signal(summary, "onboarding", "visual_polish")
    canvas_signal = _release_status_signal(summary.get("interaction_status")) or _benchmark_signal(summary, "xyflow_canvas_affordance")
    bundle_signal = _dimension_signal(summary, "resource_completeness")
    mastery_signal = _dimension_signal(summary, "actionability", "mastery_actionability")
    matrix_signal = _release_status_signal(summary.get("market_sample_matrix_status"))
    return [
        {
            "competitor": "Elicit / systematic review AI",
            "source_url": "https://elicit.com/",
            "strength": "Large-scale paper search, structured research reports, extraction tables, sentence-level citations.",
            "gap": "Optimized for evidence review, not for turning one target paper into a shortest mastery path with runnable validation.",
            "wedge": "Keep the target paper at the center and connect every resource to explain, derive, reproduce, and critique tasks.",
            "current_evidence": evidence_signal,
            "next_proof": "Show source-backed Paper Map nodes plus local resources for every mastery task.",
            "backlog_theme": "Evidence-backed Paper Map",
            "backlog_action": "Prove every core Paper Map and mastery task has visible evidence, local resources, and a clear source trail.",
        },
        {
            "competitor": "PaperQA2 / scientific RAG",
            "source_url": "https://github.com/Future-House/paper-qa",
            "strength": "High-accuracy RAG over scientific documents with cited answers and metadata-aware retrieval.",
            "gap": "Answers questions well, but does not package a visual learning route, study bundle, and mastery artifact by default.",
            "wedge": "Use RAG as evidence infrastructure, then render a learner-facing logic map, paragraph lens, and exportable evidence checklist.",
            "current_evidence": evidence_signal,
            "next_proof": "Keep chunk citations visible in Paper Lens, roadmap resources, and generated artifacts.",
            "backlog_theme": "Grounded RAG route",
            "backlog_action": "Use evidence chunks as the ranking backbone, then expose citations in Paper Lens, roadmap resources, and artifacts.",
        },
        {
            "competitor": "Explainpaper / passage explanations",
            "source_url": "https://www.explainpaper.com/",
            "strength": "Highlight confusing paper text and get context-aware explanations in many languages.",
            "gap": "Great for local confusion, weaker for showing the whole paper's causal logic and final mastery proof.",
            "wedge": "Pair paragraph explanations with Paper Map causal nodes and a concrete report/reproduction checklist.",
            "current_evidence": evidence_signal,
            "next_proof": "Verify paragraph explanations are non-repetitive, language-aware, and linked to map nodes.",
            "backlog_theme": "Plain paragraph understanding",
            "backlog_action": "Keep paragraph explanations language-aware, non-repetitive, and tied to the paper logic map.",
        },
        {
            "competitor": "roadmap.sh / visual learning paths",
            "source_url": "https://github.com/nilbuild/developer-roadmap",
            "strength": "Interactive roadmaps make a broad topic scannable and give learners a clear first click.",
            "gap": "Generic routes are not automatically grounded in the user's target paper, local files, or evidence snippets.",
            "wedge": "Generate route structure from the paper/resources and prove coverage with a cross-scenario sample matrix.",
            "current_evidence": f"{navigation_signal}; matrix={matrix_signal}",
            "next_proof": "Keep single-paper, paper-set, and field/course samples market-ready in one command.",
            "backlog_theme": "Cross-scenario route proof",
            "backlog_action": "Keep single-paper, paper-set, and field/course demos passing in one market sample matrix.",
        },
        {
            "competitor": "React Flow / xyflow canvas standard",
            "source_url": "https://github.com/xyflow/xyflow",
            "strength": "Mature pan, zoom, drag, node UI, and customization patterns for graph-based products.",
            "gap": "It is an interaction library, not a learning product or evidence pipeline.",
            "wedge": "Adopt strong canvas affordances while keeping semantic learning nodes, evidence, tasks, and local resources attached.",
            "current_evidence": canvas_signal,
            "next_proof": "Run browser interaction probes for drag, zoom, branch toggle, and detail-panel updates.",
            "backlog_theme": "Canvas interaction proof",
            "backlog_action": "Verify drag, zoom, branch collapse, node selection, and detail-panel updates with browser interaction probes.",
        },
        {
            "competitor": "Get It / measurable mastery map",
            "source_url": "https://github.com/beltromatti/get-it",
            "strength": "PDF-centered mastery map with concept scores, visualizations, flashcards, quizzes, and Feynman-style proof.",
            "gap": "Focused on a desktop study loop; less emphasis on multi-source literature discovery and field/course route export.",
            "wedge": "Compete on source discovery, local bundles, paper-set comparison, and portable report artifacts while preserving mastery proof.",
            "current_evidence": mastery_signal,
            "next_proof": "Add stronger learner progress evidence and keep generated worksheets/export artifacts easy to use.",
            "backlog_theme": "Measurable mastery proof",
            "backlog_action": "Make explain, derive, reproduce, and critique outputs easy to find, complete, and reuse after reading.",
        },
        {
            "competitor": "Litmaps / ResearchRabbit literature maps",
            "source_url": "https://www.litmaps.com/",
            "strength": "Visual discovery maps help researchers see related work, gaps, and citation neighborhoods.",
            "gap": "Discovery graphs can become detached from what the learner must read, explain, derive, or reproduce next.",
            "wedge": "Attach discovered papers to the target paper logic and only promote resources that shorten the mastery route.",
            "current_evidence": bundle_signal,
            "next_proof": "Show strongest evidence snippets and local-first links for selected and supplemental resources.",
            "backlog_theme": "Resource discovery discipline",
            "backlog_action": "Attach related papers and resources only when they shorten the target mastery route or improve evidence coverage.",
        },
    ]


def _market_opportunity_backlog(summary: dict[str, Any]) -> list[dict[str, str]]:
    """Turn market positioning lessons into release-review backlog items."""

    positioning = [item for item in summary.get("market_positioning", []) if isinstance(item, dict)]
    sample_matrix_status = str(summary.get("market_sample_matrix_status") or "not_run")
    interaction_status = str(summary.get("interaction_status") or "not_run")
    decision = str(summary.get("decision") or "needs_work")
    backlog: list[dict[str, str]] = []
    for item in positioning:
        competitor = _sanitize_public_text(str(item.get("competitor") or "Unknown"))
        evidence = _sanitize_public_text(str(item.get("current_evidence") or "not measured"))
        next_proof = _sanitize_public_text(str(item.get("next_proof") or item.get("wedge") or "Add a measurable release proof."))
        priority = _market_backlog_priority(competitor, evidence, sample_matrix_status, interaction_status, decision)
        theme = _sanitize_public_text(str(item.get("backlog_theme") or "Market proof"))
        action = _sanitize_public_text(str(item.get("backlog_action") or next_proof))
        release_proof = _sanitize_public_text(str(item.get("backlog_release_proof") or _market_backlog_release_proof(theme, next_proof)))
        backlog.append(
            {
                "priority": priority,
                "theme": theme,
                "competitor": competitor,
                "current_evidence": evidence,
                "action": action,
                "release_proof": release_proof,
            }
        )
    return sorted(backlog, key=lambda item: {"P0": 0, "P1": 1, "P2": 2}.get(item.get("priority", "P2"), 2))


def _market_backlog_priority(
    competitor: str,
    evidence: str,
    sample_matrix_status: str,
    interaction_status: str,
    decision: str,
) -> str:
    competitor_lower = competitor.lower()
    evidence_lower = evidence.lower()
    if decision == "ship":
        if any(marker in competitor_lower for marker in ("elicit", "paperqa2", "get it")):
            return "P1"
        return "P2"
    if any(marker in evidence_lower for marker in ("not measured", "not_run", "warn", "fail", "unknown")):
        return "P0"
    if "roadmap.sh" in competitor_lower and sample_matrix_status not in {"pass", "skipped", "not_run"}:
        return "P0"
    if "react flow" in competitor_lower and interaction_status != "pass":
        return "P0"
    if any(marker in competitor_lower for marker in ("elicit", "paperqa2", "get it")):
        return "P1"
    return "P2"


def _market_backlog_release_proof(theme: str, next_proof: str) -> str:
    return f"{theme}: {next_proof}"


def _market_experience_scorecard(summary: dict[str, Any]) -> list[dict[str, Any]]:
    """Summarize user-facing competitiveness across the product experience."""

    dimension_map = {
        str(item.get("id") or ""): item
        for item in summary.get("dimensions", [])
        if isinstance(item, dict)
    }
    warning_ids = {
        str(item.get("id") or "")
        for item in summary.get("benchmark_warnings", [])
        if isinstance(item, dict)
    }
    return [
        _market_experience_card(
            "ui_interface",
            "UI/interface polish",
            "React Flow / roadmap.sh",
            "The report should feel like a clear product, not a generated document pile.",
            _average_dimension_score(dimension_map, "visual_polish", "onboarding"),
            _dimension_evidence(dimension_map, "visual_polish", "onboarding"),
            "Keep Paper Map readable, draggable, zoomable, and visually stable on desktop and mobile.",
            warning_ids,
            warning_markers={"xyflow_canvas_affordance", "roadmap_interactive_first_step"},
            status_penalties=_status_penalties(summary, "visual_status", "interaction_status"),
        ),
        _market_experience_card(
            "content_depth",
            "Content depth",
            "Elicit / PaperQA2 / Get It",
            "A learner should get a real path to mastery, not just a summary or link list.",
            _average_dimension_score(dimension_map, "learning_depth", "actionability"),
            _dimension_evidence(dimension_map, "learning_depth", "actionability"),
            "Keep Paper Map, Paper Lens, KG, and explain/derive/reproduce/critique evidence connected.",
            warning_ids,
            warning_markers={"paperqa_grounded_evidence", "get_it_measurable_mastery_map"},
        ),
        _market_experience_card(
            "plain_clarity",
            "Plain-language clarity",
            "Explainpaper / NotebookLM",
            "The explanations should be direct enough that a reader can retell the paper in their own words.",
            _average_dimension_score(dimension_map, "plain_explanation"),
            _dimension_evidence(dimension_map, "plain_explanation"),
            "Use paragraph-level, non-repetitive explanations that explain why each part matters.",
            warning_ids,
            warning_markers={"explainpaper_contextual_explanations"},
        ),
        _market_experience_card(
            "first_run_ease",
            "First-run ease",
            "roadmap.sh / NotebookLM",
            "A new user should know the first click and reach the first mastery task quickly.",
            _average_dimension_score(dimension_map, "onboarding"),
            _dimension_evidence(dimension_map, "onboarding") + _timing_evidence(summary),
            "Measure the first 10 minutes and remove repeated fresh-user blockers before calling the report market-ready.",
            warning_ids,
            warning_markers={"roadmap_interactive_first_step"},
            status_penalties=_status_penalties(summary, "fresh_user_timing_status", "fresh_user_trend_status"),
        ),
        _market_experience_card(
            "evidence_trust",
            "Evidence trust",
            "Elicit / PaperQA2",
            "Every claim, explanation, and recommended task should be easy to trace back to sources.",
            _average_dimension_score(dimension_map, "learning_depth", "plain_explanation"),
            _dimension_evidence(dimension_map, "learning_depth", "plain_explanation"),
            "Keep citations, evidence snippets, and local review links visible from map nodes, lens paragraphs, and resources.",
            warning_ids,
            warning_markers={"paperqa_grounded_evidence", "resource_evidence_snippets", "resource_evidence_review_links"},
        ),
        _market_experience_card(
            "resource_completeness",
            "Resource completeness",
            "ResearchRabbit / Litmaps / local-first study apps",
            "The route should include enough downloadable, local-first material to actually study without hunting links.",
            _average_dimension_score(dimension_map, "resource_completeness"),
            _dimension_evidence(dimension_map, "resource_completeness"),
            "Download, copy, snapshot, or generate the resources that shorten the mastery path; leave only unavailable items as links.",
            warning_ids,
            warning_markers={"local_first_bundle", "resource_provenance_coverage"},
        ),
        _market_experience_card(
            "portable_outputs",
            "Portable outputs",
            "NotebookLM / Scholarcy",
            "The report should leave the learner with reusable notes, checklists, and presentation-ready artifacts.",
            _average_dimension_score(dimension_map, "actionability"),
            _dimension_evidence(dimension_map, "actionability"),
            "Keep generated worksheets, presentation notes, and artifact checklists close to the learning path.",
            warning_ids,
            warning_markers={"notebooklm_portable_study_outputs", "scholarcy_structured_review_cards"},
        ),
    ]


def _market_experience_card(
    id_: str,
    label: str,
    competitor_reference: str,
    user_value: str,
    base_score: int,
    evidence: list[str],
    next_improvement: str,
    warning_ids: set[str],
    *,
    warning_markers: set[str] | None = None,
    status_penalties: int = 0,
) -> dict[str, Any]:
    warning_markers = warning_markers or set()
    warning_penalty = 15 if warning_ids & warning_markers else 0
    score = max(0, min(100, int(base_score) - warning_penalty - status_penalties))
    status = "strong" if score >= 80 else "adequate" if score >= 60 else "weak"
    clean_evidence = [_sanitize_public_text(str(item)) for item in evidence if item]
    if warning_ids & warning_markers:
        clean_evidence.append("competitor benchmark warning: " + ", ".join(sorted(warning_ids & warning_markers)))
    return {
        "id": id_,
        "label": label,
        "competitor_reference": competitor_reference,
        "user_value": user_value,
        "score": score,
        "status": status,
        "evidence": clean_evidence or ["not measured"],
        "next_improvement": next_improvement,
    }


def _average_dimension_score(dimension_map: dict[str, dict[str, Any]], *ids: str) -> int:
    scores = [
        int(dimension_map[id_].get("score") or 0)
        for id_ in ids
        if id_ in dimension_map
    ]
    return round(sum(scores) / len(scores)) if scores else 0


def _dimension_evidence(dimension_map: dict[str, dict[str, Any]], *ids: str) -> list[str]:
    evidence: list[str] = []
    for id_ in ids:
        item = dimension_map.get(id_)
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or id_)
        for value in item.get("evidence", []) if isinstance(item.get("evidence"), list) else []:
            evidence.append(f"{label}: {value}")
    return evidence


def _timing_evidence(summary: dict[str, Any]) -> list[str]:
    evidence = [f"fresh-user timing status: {summary.get('fresh_user_timing_status', 'not_run')}"]
    blockers = int(summary.get("recurring_blockers") or 0)
    if blockers:
        evidence.append(f"recurring blockers: {blockers}")
    return evidence


def _status_penalties(summary: dict[str, Any], *status_keys: str) -> int:
    penalty = 0
    for key in status_keys:
        status = str(summary.get(key) or "not_run")
        if status in {"fail", "do_not_ship"}:
            penalty += 30
        elif status in {"warn", "needs_work", "needs_improvement"}:
            penalty += 20
        elif status == "not_run":
            penalty += 10
    return min(penalty, 35)


def _release_next_actions(
    market: dict[str, Any],
    benchmark: dict[str, Any],
    trend: dict[str, Any],
    timing: dict[str, Any] | None = None,
    snapshot: dict[str, Any] | None = None,
    baseline: dict[str, Any] | None = None,
    interaction: dict[str, Any] | None = None,
    sample_matrix: dict[str, Any] | None = None,
) -> list[str]:
    actions: list[str] = []
    timing_status = str((timing or {}).get("status") or "not_run")
    has_timing_evidence = timing_status in {"pass", "skipped"}
    if timing_status not in {"pass", "skipped"}:
        actions.append("Run a fresh-user timing test with --fresh-user-minutes before calling this report release-ready.")
    snapshot_status = str((snapshot or {}).get("status") or "not_run")
    baseline_status = str((baseline or {}).get("status") or "not_run")
    has_visual_evidence = snapshot_status == "pass" or baseline_status == "pass"
    if snapshot_status != "pass" and baseline_status != "pass":
        actions.append("Install the visual extra and run --capture-screenshots, or compare a passing screenshot baseline, before calling this report visually release-ready.")
    interaction_status = str((interaction or {}).get("status") or "not_run")
    has_interaction_evidence = interaction_status == "pass"
    if interaction_status != "pass":
        actions.append("Install the visual extra and run --probe-interactions to verify Paper Map, Paper Lens, and resource-library clicks before calling this report interaction-ready.")
    sample_matrix_status = str((sample_matrix or {}).get("status") or "not_run")
    if sample_matrix_status not in {"pass", "skipped", "not_run"}:
        summary = (sample_matrix or {}).get("summary") if isinstance((sample_matrix or {}).get("summary"), dict) else {}
        missing = summary.get("missing_scenarios") if isinstance(summary.get("missing_scenarios"), list) else []
        missing_text = ", ".join(str(item) for item in missing) if missing else "single-paper, paper-set, or field-course"
        actions.append(
            "Run a market sample matrix with --market-sample-dir for single-paper, paper-set, and field/course reports before claiming broad market readiness. Missing: "
            + missing_text
        )
    for item in market.get("next_best_actions", []):
        if isinstance(item, dict) and item.get("action"):
            action = _sanitize_public_text(str(item["action"]))
            normalized_action = action.lower()
            if has_timing_evidence and "fresh-user" in normalized_action and "time" in normalized_action:
                continue
            if has_visual_evidence and "screenshot" in normalized_action:
                continue
            if has_interaction_evidence and ("interaction" in normalized_action or "canvas" in normalized_action):
                continue
            actions.append(action)
    for item in benchmark.get("checks", []):
        if isinstance(item, dict) and item.get("status") not in {"pass", None}:
            action = item.get("recommendation") or item.get("fix")
            if action:
                actions.append(_sanitize_public_text(str(action)))
    for item in trend.get("trends", []):
        if not isinstance(item, dict):
            continue
        for fix in item.get("fix_ideas", []) if isinstance(item.get("fix_ideas"), list) else []:
            actions.append(_sanitize_public_text(str(fix)))
    seen: set[str] = set()
    unique: list[str] = []
    for action in actions:
        normalized = action.lower()
        if action and normalized not in seen:
            seen.add(normalized)
            unique.append(action)
    return unique[:8]


def _release_readiness_markdown(summary: dict[str, Any]) -> str:
    positioning = [item for item in summary.get("market_positioning", []) if isinstance(item, dict)]
    opportunity_backlog = [item for item in summary.get("market_opportunity_backlog", []) if isinstance(item, dict)]
    experience_scorecard = [item for item in summary.get("market_experience_scorecard", []) if isinstance(item, dict)]
    rows = [
        "# Release Readiness Dashboard",
        "",
        f"Decision: {summary['decision']}",
        f"Market-readiness score: {summary['score']}",
        "",
        "## Status Signals",
        "",
        "| Signal | Status |",
        "| --- | --- |",
        f"| Visual audit | {_markdown_cell(str(summary['visual_status']))} |",
        f"| Market readiness | {_markdown_cell(str(summary['market_status']))} |",
        f"| Competitive benchmark | {_markdown_cell(str(summary['benchmark_status']))} |",
        f"| Browser screenshots | {_markdown_cell(str(summary['snapshot_status']))} |",
        f"| Snapshot baseline | {_markdown_cell(str(summary['baseline_status']))} |",
        f"| Browser interactions | {_markdown_cell(str(summary['interaction_status']))} |",
        f"| Fresh-user timing | {_markdown_cell(str(summary['fresh_user_timing_status']))} |",
        f"| Fresh-user trends | {_markdown_cell(str(summary['fresh_user_trend_status']))} |",
        f"| Market sample matrix | {_markdown_cell(str(summary.get('market_sample_matrix_status', 'not_run')))} |",
        f"| Recurring blockers | {int(summary['recurring_blockers'])} |",
        "",
        "## Market Experience Scorecard",
        "",
        "| Area | Competes with | Score | Status | User value | Evidence | Next improvement |",
        "| --- | --- | ---: | --- | --- | --- | --- |",
    ]
    if experience_scorecard:
        for item in experience_scorecard:
            rows.append(
                "| {label} | {reference} | {score} | {status} | {value} | {evidence} | {improvement} |".format(
                    label=_markdown_cell(_sanitize_public_text(str(item.get("label") or ""))),
                    reference=_markdown_cell(_sanitize_public_text(str(item.get("competitor_reference") or ""))),
                    score=int(item.get("score") or 0),
                    status=_markdown_cell(_sanitize_public_text(str(item.get("status") or ""))),
                    value=_markdown_cell(_sanitize_public_text(str(item.get("user_value") or ""))),
                    evidence=_markdown_cell("; ".join(_sanitize_public_text(str(value)) for value in item.get("evidence", []) if value) or "-"),
                    improvement=_markdown_cell(_sanitize_public_text(str(item.get("next_improvement") or ""))),
                )
            )
    else:
        rows.append("| Market experience | - | 0 | weak | Not measured | - | Run release readiness audit with report_audit.json. |")
    rows.extend(
        [
            "",
            "## Competitor-Inspired Gates",
            "",
            "| Gate | What it protects | Current signal |",
            "| --- | --- | --- |",
            f"| Elicit/SciSpace evidence transparency | Every claim should point back to evidence, not just a summary. | {_dimension_signal(summary, 'learning_depth', 'plain_explanation')} |",
            f"| ResearchRabbit/roadmap.sh visual navigation | Learners should see a clear map and know the first click. | {_dimension_signal(summary, 'onboarding', 'visual_polish')} |",
            f"| React Flow canvas affordance | The Paper Map should feel draggable, zoomable, and stable. | {_release_status_signal(summary.get('interaction_status')) or _benchmark_signal(summary, 'xyflow_canvas_affordance')} |",
            f"| Local-first study bundle | Resources should open locally when possible, with links as fallback. | {_dimension_signal(summary, 'resource_completeness')} |",
            f"| Mastery proof | Understanding should end in explain/derive/reproduce/critique evidence. | {_dimension_signal(summary, 'actionability', 'mastery_actionability')} |",
            "",
            "## Market Positioning Matrix",
            "",
            "| Competitor / category | What users like | Their gap | fields-study-flow wedge | Current evidence | Next proof |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for item in positioning:
        source = str(item.get("source_url") or "")
        competitor = str(item.get("competitor") or "Unknown")
        competitor_cell = f"[{competitor}]({source})" if source else competitor
        rows.append(
            "| {competitor} | {strength} | {gap} | {wedge} | {evidence} | {next_proof} |".format(
                competitor=_markdown_cell(competitor_cell),
                strength=_markdown_cell(_sanitize_public_text(str(item.get("strength") or ""))),
                gap=_markdown_cell(_sanitize_public_text(str(item.get("gap") or ""))),
                wedge=_markdown_cell(_sanitize_public_text(str(item.get("wedge") or ""))),
                evidence=_markdown_cell(_sanitize_public_text(str(item.get("current_evidence") or ""))),
                next_proof=_markdown_cell(_sanitize_public_text(str(item.get("next_proof") or ""))),
            )
        )
    rows.extend(
        [
            "",
            "## Market Opportunity Backlog",
            "",
            "| Priority | Theme | Competitor lesson | Current evidence | Action | Release proof |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if opportunity_backlog:
        for item in opportunity_backlog:
            rows.append(
                "| {priority} | {theme} | {competitor} | {evidence} | {action} | {proof} |".format(
                    priority=_markdown_cell(_sanitize_public_text(str(item.get("priority") or "P2"))),
                    theme=_markdown_cell(_sanitize_public_text(str(item.get("theme") or ""))),
                    competitor=_markdown_cell(_sanitize_public_text(str(item.get("competitor") or ""))),
                    evidence=_markdown_cell(_sanitize_public_text(str(item.get("current_evidence") or ""))),
                    action=_markdown_cell(_sanitize_public_text(str(item.get("action") or ""))),
                    proof=_markdown_cell(_sanitize_public_text(str(item.get("release_proof") or ""))),
                )
            )
    else:
        rows.append("| P2 | Market proof | - | - | Keep monitoring competitor lessons after each release check. | - |")
    rows.extend(
        [
            "",
            "## Next Actions",
            "",
        ]
    )
    actions = summary.get("next_actions", [])
    if actions:
        rows.extend(f"- {_markdown_cell(_sanitize_public_text(str(action)))}" for action in actions)
    else:
        rows.append("- No urgent release blockers recorded. Keep the timing, screenshot, and interaction gates in future release checks.")
    trends = summary.get("trends", [])
    sample_matrix_summary = summary.get("market_sample_matrix_summary") if isinstance(summary.get("market_sample_matrix_summary"), dict) else {}
    if sample_matrix_summary:
        rows.extend(
            [
                "",
                "## Market Sample Matrix",
                "",
                f"- Covered scenarios: {_markdown_cell(', '.join(str(item) for item in sample_matrix_summary.get('covered_scenarios', [])) or '-')}",
                f"- Missing scenarios: {_markdown_cell(', '.join(str(item) for item in sample_matrix_summary.get('missing_scenarios', [])) or '-')}",
            ]
        )
    if trends:
        rows.extend(["", "## Fresh-User Recurring Blockers", "", "| Reports | Occurrences | Blocker | Fix ideas |", "| ---: | ---: | --- | --- |"])
        for item in trends[:5]:
            rows.append(
                "| {reports} | {occurrences} | {blocker} | {fixes} |".format(
                    reports=int(item.get("reports") or 0),
                    occurrences=int(item.get("total_occurrences") or 0),
                    blocker=_markdown_cell(_sanitize_public_text(str(item.get("blocker") or ""))),
                    fixes=_markdown_cell("; ".join(_sanitize_public_text(str(fix)) for fix in item.get("fix_ideas", []) if fix) or "-"),
                )
            )
    rows.append("")
    return "\n".join(rows)


def _release_readiness_html(summary: dict[str, Any]) -> str:
    decision = _sanitize_public_text(str(summary.get("decision") or "needs_work"))
    status_rows = [
        ("Visual audit", summary.get("visual_status")),
        ("Market readiness", summary.get("market_status")),
        ("Competitive benchmark", summary.get("benchmark_status")),
        ("Browser screenshots", summary.get("snapshot_status")),
        ("Snapshot baseline", summary.get("baseline_status")),
        ("Browser interactions", summary.get("interaction_status")),
        ("Fresh-user timing", summary.get("fresh_user_timing_status")),
        ("Fresh-user trends", summary.get("fresh_user_trend_status")),
        ("Market sample matrix", summary.get("market_sample_matrix_status", "not_run")),
        ("Recurring blockers", summary.get("recurring_blockers")),
    ]
    gate_rows = [
        (
            "Elicit/SciSpace evidence transparency",
            "Every claim should point back to evidence, not just a summary.",
            _dimension_signal(summary, "learning_depth", "plain_explanation"),
        ),
        (
            "ResearchRabbit/roadmap.sh visual navigation",
            "Learners should see a clear map and know the first click.",
            _dimension_signal(summary, "onboarding", "visual_polish"),
        ),
        (
            "React Flow canvas affordance",
            "The Paper Map should feel draggable, zoomable, and stable.",
            _release_status_signal(summary.get("interaction_status")) or _benchmark_signal(summary, "xyflow_canvas_affordance"),
        ),
        (
            "Local-first study bundle",
            "Resources should open locally when possible, with links as fallback.",
            _dimension_signal(summary, "resource_completeness"),
        ),
        (
            "Mastery proof",
            "Understanding should end in explain/derive/reproduce/critique evidence.",
            _dimension_signal(summary, "actionability", "mastery_actionability"),
        ),
    ]
    actions = summary.get("next_actions", [])
    trends = summary.get("trends", [])
    positioning = [item for item in summary.get("market_positioning", []) if isinstance(item, dict)]
    opportunity_backlog = [item for item in summary.get("market_opportunity_backlog", []) if isinstance(item, dict)]
    experience_scorecard = [item for item in summary.get("market_experience_scorecard", []) if isinstance(item, dict)]
    action_items = "".join(f"<li>{_html_escape(_sanitize_public_text(str(action)))}</li>" for action in actions) or "<li>No urgent release blockers recorded. Keep the timing, screenshot, and interaction gates in future release checks.</li>"
    sample_matrix_summary = summary.get("market_sample_matrix_summary") if isinstance(summary.get("market_sample_matrix_summary"), dict) else {}
    sample_matrix_html = ""
    if sample_matrix_summary:
        covered = ", ".join(str(item) for item in sample_matrix_summary.get("covered_scenarios", [])) or "-"
        missing = ", ".join(str(item) for item in sample_matrix_summary.get("missing_scenarios", [])) or "-"
        sample_matrix_html = f"""
        <section class="panel">
          <h2>Market Sample Matrix / 市场样本矩阵</h2>
          <div class="status-grid">
            <article><span>Covered scenarios</span><strong>{_html_escape(_sanitize_public_text(covered))}</strong></article>
            <article><span>Missing scenarios</span><strong>{_html_escape(_sanitize_public_text(missing))}</strong></article>
          </div>
        </section>
        """
    trend_rows = "".join(
        "<tr><td>{reports}</td><td>{occurrences}</td><td>{blocker}</td><td>{fixes}</td></tr>".format(
            reports=int(item.get("reports") or 0),
            occurrences=int(item.get("total_occurrences") or 0),
            blocker=_html_escape(_sanitize_public_text(str(item.get("blocker") or ""))),
            fixes=_html_escape("; ".join(_sanitize_public_text(str(fix)) for fix in item.get("fix_ideas", []) if fix) or "-"),
        )
        for item in trends[:5]
        if isinstance(item, dict)
    )
    trends_html = (
        f"""
        <section class="panel">
          <h2>Fresh-User Recurring Blockers / 新用户反复卡点</h2>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Reports</th><th>Occurrences</th><th>Blocker</th><th>Fix ideas</th></tr></thead>
              <tbody>{trend_rows}</tbody>
            </table>
          </div>
        </section>
        """
        if trend_rows
        else ""
    )
    status_cards = "".join(
        f"<article><span>{_html_escape(label)}</span><strong>{_html_escape(_sanitize_public_text(str(value)))}</strong></article>"
        for label, value in status_rows
    )
    gate_cards = "".join(
        """
        <article class="gate-card">
          <h3>{name}</h3>
          <p>{purpose}</p>
          <strong>{signal}</strong>
        </article>
        """.format(
            name=_html_escape(name),
            purpose=_html_escape(purpose),
            signal=_html_escape(_sanitize_public_text(str(signal))),
        )
        for name, purpose, signal in gate_rows
    )
    experience_cards = "".join(
        """
        <article class="experience-card status-{status_class}">
          <div class="experience-card-top">
            <h3>{label}</h3>
            <strong>{score}</strong>
          </div>
          <p class="reference">{reference}</p>
          <p>{value}</p>
          <p><strong>Evidence:</strong> {evidence}</p>
          <p class="proof"><strong>Next:</strong> {improvement}</p>
        </article>
        """.format(
            status_class=_html_escape(_sanitize_public_text(str(item.get("status") or "weak"))),
            label=_html_escape(_sanitize_public_text(str(item.get("label") or ""))),
            score=int(item.get("score") or 0),
            reference=_html_escape(_sanitize_public_text(str(item.get("competitor_reference") or ""))),
            value=_html_escape(_sanitize_public_text(str(item.get("user_value") or ""))),
            evidence=_html_escape("; ".join(_sanitize_public_text(str(value)) for value in item.get("evidence", []) if value) or "-"),
            improvement=_html_escape(_sanitize_public_text(str(item.get("next_improvement") or ""))),
        )
        for item in experience_scorecard
    )
    experience_html = (
        f"""
        <section class="panel" data-market-experience-scorecard>
          <h2>Market Experience Scorecard / 市场体验评分卡</h2>
          <p class="panel-note">A market-facing readout for the exact product qualities that matter: UI, learning depth, plain explanations, first-run ease, trust, resources, and reusable outputs.</p>
          <div class="experience-grid">{experience_cards}</div>
        </section>
        """
        if experience_cards
        else ""
    )
    positioning_rows = "".join(
        """
        <tr>
          <td><a href="{source}">{competitor}</a></td>
          <td>{strength}</td>
          <td>{gap}</td>
          <td>{wedge}</td>
          <td>{evidence}</td>
          <td>{next_proof}</td>
        </tr>
        """.format(
            source=_html_escape(_sanitize_public_text(str(item.get("source_url") or "#"))),
            competitor=_html_escape(_sanitize_public_text(str(item.get("competitor") or "Unknown"))),
            strength=_html_escape(_sanitize_public_text(str(item.get("strength") or ""))),
            gap=_html_escape(_sanitize_public_text(str(item.get("gap") or ""))),
            wedge=_html_escape(_sanitize_public_text(str(item.get("wedge") or ""))),
            evidence=_html_escape(_sanitize_public_text(str(item.get("current_evidence") or ""))),
            next_proof=_html_escape(_sanitize_public_text(str(item.get("next_proof") or ""))),
        )
        for item in positioning
    )
    positioning_html = (
        f"""
        <section class="panel" data-market-positioning>
          <h2>Market Positioning Matrix / 市场定位矩阵</h2>
          <p class="panel-note">A compact competitor landscape that turns external product lessons into current evidence and next proof for this report.</p>
          <div class="table-wrap">
            <table>
              <thead><tr><th>Competitor / category</th><th>What users like</th><th>Their gap</th><th>fields-study-flow wedge</th><th>Current evidence</th><th>Next proof</th></tr></thead>
              <tbody>{positioning_rows}</tbody>
            </table>
          </div>
        </section>
        """
        if positioning_rows
        else ""
    )
    backlog_cards = "".join(
        """
        <article class="backlog-card priority-{priority_class}">
          <span class="priority-pill">{priority}</span>
          <h3>{theme}</h3>
          <p><strong>Competitor lesson:</strong> {competitor}</p>
          <p><strong>Current evidence:</strong> {evidence}</p>
          <p>{action}</p>
          <p class="proof"><strong>Release proof:</strong> {proof}</p>
        </article>
        """.format(
            priority_class=_html_escape(_sanitize_public_text(str(item.get("priority") or "P2")).lower()),
            priority=_html_escape(_sanitize_public_text(str(item.get("priority") or "P2"))),
            theme=_html_escape(_sanitize_public_text(str(item.get("theme") or ""))),
            competitor=_html_escape(_sanitize_public_text(str(item.get("competitor") or ""))),
            evidence=_html_escape(_sanitize_public_text(str(item.get("current_evidence") or ""))),
            action=_html_escape(_sanitize_public_text(str(item.get("action") or ""))),
            proof=_html_escape(_sanitize_public_text(str(item.get("release_proof") or ""))),
        )
        for item in opportunity_backlog
    )
    backlog_html = (
        f"""
        <section class="panel" data-market-opportunity-backlog>
          <h2>Market Opportunity Backlog / 市场机会待办</h2>
          <p class="panel-note">The positioning matrix becomes a prioritized product backlog: each item has an action and release proof, so market learning turns into product work.</p>
          <div class="backlog-grid">{backlog_cards}</div>
        </section>
        """
        if backlog_cards
        else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Release Readiness Dashboard</title>
  <style>
    :root {{ color-scheme: light; --ink:#18201d; --muted:#657066; --line:#d9e2d7; --surface:#fffdfa; --soft:#f3f7ee; --accent:#2f6f73; --warn:#9a5a13; --danger:#b3261e; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#f6f4ef; color:var(--ink); font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Noto Sans SC","Source Han Sans SC",Arial,sans-serif; line-height:1.65; }}
    .release-readiness {{ width:min(1180px, calc(100vw - 32px)); margin:0 auto; padding:28px 0 42px; overflow-wrap:anywhere; }}
    .hero {{ display:grid; grid-template-columns:minmax(0, 1.2fr) minmax(260px, .8fr); gap:18px; align-items:stretch; }}
    .hero-copy, .score-card, .panel {{ border:1px solid var(--line); border-radius:22px; background:var(--surface); box-shadow:0 18px 48px rgba(43,53,45,.09); }}
    .hero-copy {{ padding:28px; }}
    .eyebrow {{ margin:0 0 8px; color:var(--accent); font-size:.82rem; font-weight:800; letter-spacing:.06em; text-transform:uppercase; }}
    h1, h2, h3, p {{ margin-top:0; }}
    h1 {{ margin-bottom:12px; font-size:clamp(2rem, 5vw, 4rem); line-height:1.05; letter-spacing:0; }}
    h2 {{ font-size:1.28rem; line-height:1.25; }}
    h3 {{ font-size:1rem; line-height:1.3; }}
    .decision-pill {{ display:inline-flex; align-items:center; border-radius:999px; padding:8px 13px; color:white; background:var(--accent); font-weight:900; }}
    .decision-pill.needs_work {{ background:var(--warn); }}
    .decision-pill.do_not_ship {{ background:var(--danger); }}
    .score-card {{ display:grid; align-content:center; gap:8px; padding:28px; background:linear-gradient(135deg,#ffffff,#eef6f4); }}
    .score-card strong {{ font-size:3rem; line-height:1; }}
    .status-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(170px,1fr)); gap:12px; margin:18px 0; }}
    .status-grid article {{ border:1px solid var(--line); border-radius:16px; padding:14px; background:var(--soft); min-width:0; }}
    .status-grid span {{ display:block; color:var(--muted); font-size:.85rem; }}
    .status-grid strong {{ display:block; margin-top:4px; font-size:1.02rem; }}
    .panel {{ margin-top:18px; padding:22px; }}
    .panel-note {{ color:var(--muted); max-width:78ch; }}
    .gate-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:14px; }}
    .gate-card {{ min-width:0; border:1px solid var(--line); border-radius:18px; padding:16px; background:#fff; }}
    .gate-card p {{ color:var(--muted); }}
    .gate-card strong {{ display:block; padding-top:8px; border-top:1px solid var(--line); }}
    .experience-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:14px; }}
    .experience-card {{ min-width:0; border:1px solid var(--line); border-radius:18px; padding:16px; background:#fff; }}
    .experience-card.status-weak {{ border-color:#efb4ad; background:#fff6f4; }}
    .experience-card.status-adequate {{ border-color:#e7d08d; background:#fffbea; }}
    .experience-card.status-strong {{ border-color:#8ec7b3; background:#f2fbf6; }}
    .experience-card-top {{ display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }}
    .experience-card-top strong {{ flex:0 0 auto; font-size:2rem; line-height:1; color:var(--accent); }}
    .experience-card .reference {{ color:var(--accent); font-weight:800; }}
    .experience-card p {{ color:var(--muted); }}
    .experience-card .proof {{ color:var(--ink); }}
    .backlog-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:14px; }}
    .backlog-card {{ min-width:0; border:1px solid var(--line); border-radius:18px; padding:16px; background:#fff; position:relative; }}
    .backlog-card.priority-p0 {{ border-color:#e7b46d; background:#fff8ec; }}
    .backlog-card.priority-p1 {{ border-color:#9cc9c4; background:#f1fbf9; }}
    .priority-pill {{ display:inline-flex; align-items:center; border-radius:999px; padding:5px 10px; background:var(--ink); color:white; font-size:.78rem; font-weight:900; }}
    .backlog-card p {{ color:var(--muted); }}
    .backlog-card .proof {{ color:var(--ink); }}
    .actions {{ margin:0; padding-left:22px; }}
    .actions li + li {{ margin-top:8px; }}
    .table-wrap {{ overflow-x:auto; }}
    table {{ width:100%; border-collapse:collapse; min-width:640px; }}
    th, td {{ border-bottom:1px solid var(--line); padding:10px; text-align:left; vertical-align:top; }}
    th {{ color:var(--muted); font-size:.82rem; }}
    @media (max-width: 760px) {{ .release-readiness {{ width:min(100vw - 20px, 720px); }} .hero {{ grid-template-columns:1fr; }} .hero-copy, .score-card, .panel {{ border-radius:18px; }} }}
  </style>
</head>
<body>
  <main class="release-readiness" data-release-decision="{_html_escape(decision)}">
    <section class="hero">
      <div class="hero-copy">
        <p class="eyebrow">Release Readiness / 发布决策</p>
        <h1>Release Readiness Dashboard</h1>
        <p>中文友好的离线发布面板，把视觉、证据、资料、上手速度和竞品门槛合成一个可执行决策。</p>
        <span class="decision-pill {_html_escape(decision)}">{_html_escape(decision)}</span>
      </div>
      <aside class="score-card" aria-label="Market-readiness score">
        <span>Market-readiness score</span>
        <strong>{int(summary.get("score") or 0)}</strong>
        <p>Use this as a release gate, then inspect the actions below.</p>
      </aside>
    </section>
    <section class="status-grid" aria-label="Status signals">{status_cards}</section>
    {experience_html}
    <section class="panel">
      <h2>Competitor-Inspired Gates / 竞品启发门槛</h2>
      <div class="gate-grid">{gate_cards}</div>
    </section>
    {positioning_html}
    {backlog_html}
    <section class="panel">
      <h2>Next Actions / 下一步</h2>
      <ol class="actions">{action_items}</ol>
    </section>
    {sample_matrix_html}
    {trends_html}
  </main>
</body>
</html>"""


def _html_escape(value: str) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _dimension_signal(summary: dict[str, Any], *ids: str) -> str:
    dimensions = summary.get("dimensions", [])
    found = [
        item
        for item in dimensions
        if isinstance(item, dict) and str(item.get("id") or "") in ids
    ]
    if not found:
        return "not measured"
    return " / ".join(f"{item.get('id')}: {item.get('score', 0)}" for item in found)


def _benchmark_signal(summary: dict[str, Any], id_: str) -> str:
    for item in summary.get("benchmark_warnings", []):
        if isinstance(item, dict) and item.get("id") == id_:
            return f"{item.get('status', 'warn')}: {item.get('label') or item.get('recommendation') or item.get('fix') or id_}"
    return "pass or not explicitly warned"


def _release_status_signal(status: Any) -> str:
    value = str(status or "").strip()
    if not value or value == "not_run":
        return "not measured"
    return value


def _fresh_user_blocker_entries(text: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "Blocker / confusion" in stripped or re.fullmatch(r"\|?\s*-[-|\s]*\|?", stripped):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 5:
            continue
        step, expected, time_value, blocker, fix_idea = cells[:5]
        if not blocker:
            continue
        entries.append(
            {
                "step": step,
                "expected_action": expected,
                "time": time_value,
                "blocker": blocker,
                "fix_idea": fix_idea,
            }
        )
    return entries


def _fresh_user_backlog_markdown(summary: dict[str, Any]) -> str:
    rows = [
        "# Fresh User Backlog",
        "",
        "Ranked blockers aggregated from completed fresh-user worksheets.",
        "",
        "| Rank | Occurrences | Steps | Blocker | Fix ideas |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for index, item in enumerate(summary.get("backlog", []), start=1):
        rows.append(
            "| {rank} | {occurrences} | {steps} | {blocker} | {fixes} |".format(
                rank=index,
                occurrences=item.get("occurrences", 0),
                steps=", ".join(item.get("steps", [])) or "-",
                blocker=_markdown_cell(str(item.get("blocker") or "")),
                fixes=_markdown_cell("; ".join(item.get("fix_ideas", [])) or "-"),
            )
        )
    if not summary.get("backlog"):
        rows.append("| 1 | 0 | - | No blockers recorded yet | Run at least one filled worksheet |")
    rows.extend(
        [
            "",
            "## Summary",
            "",
            f"- Worksheets: {(summary.get('summary') or {}).get('worksheets', 0)}",
            f"- Blocker notes: {(summary.get('summary') or {}).get('blockers', 0)}",
            f"- Unique blockers: {(summary.get('summary') or {}).get('unique_blockers', 0)}",
            "",
        ]
    )
    return "\n".join(rows)


def _fresh_user_backlog_items(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "Occurrences" in stripped or re.fullmatch(r"\|?\s*-[-:|\s]*\|?", stripped):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 5:
            continue
        _rank, occurrences, steps, blocker, fix_ideas = cells[:5]
        try:
            occurrence_count = int(str(occurrences).strip())
        except ValueError:
            occurrence_count = 0
        clean_blocker = _sanitize_public_text(blocker)
        if not clean_blocker:
            continue
        items.append(
            {
                "occurrences": occurrence_count,
                "steps": [step.strip() for step in steps.split(",") if step.strip() and step.strip() != "-"],
                "blocker": clean_blocker,
                "fix_ideas": [_sanitize_public_text(item.strip()) for item in fix_ideas.split(";") if item.strip()],
            }
        )
    return items


def _fresh_user_trend_report_markdown(summary: dict[str, Any]) -> str:
    rows = [
        "# Fresh User Trend Report",
        "",
        "Recurring onboarding blockers aggregated across ranked fresh-user backlogs.",
        "",
        "| Rank | Reports | Total occurrences | Trend | Steps | Blocker | Fix ideas |",
        "| --- | ---: | ---: | --- | --- | --- | --- |",
    ]
    for index, item in enumerate(summary.get("trends", []), start=1):
        rows.append(
            "| {rank} | {reports} | {occurrences} | {trend} | {steps} | {blocker} | {fixes} |".format(
                rank=index,
                reports=item.get("reports", 0),
                occurrences=item.get("total_occurrences", 0),
                trend=item.get("trend", ""),
                steps=", ".join(item.get("steps", [])) or "-",
                blocker=_markdown_cell(str(item.get("blocker") or "")),
                fixes=_markdown_cell("; ".join(item.get("fix_ideas", [])) or "-"),
            )
        )
    if not summary.get("trends"):
        rows.append("| 1 | 0 | 0 | none | - | No recurring blockers recorded yet | Run filled worksheets and backlog aggregation |")
    rows.extend(
        [
            "",
            "## Summary",
            "",
            f"- Backlog files: {(summary.get('summary') or {}).get('backlog_files', 0)}",
            f"- Unique blockers: {(summary.get('summary') or {}).get('unique_blockers', 0)}",
            f"- Recurring blockers: {(summary.get('summary') or {}).get('recurring_blockers', 0)}",
            "",
        ]
    )
    return "\n".join(rows)


def _sanitize_public_text(value: str) -> str:
    return PRIVATE_PATH_RE.sub("[private path]", str(value)).strip()


def _normalize_blocker(value: str) -> str:
    return re.sub(r"\s+", " ", _sanitize_public_text(value).lower()).strip()


def _step_sort_key(value: str) -> tuple[int, str]:
    try:
        return (int(str(value)), str(value))
    except ValueError:
        return (10_000, str(value))


def _markdown_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def _load_snapshot_baseline(baseline: Path | str | dict[str, Any]) -> dict[str, Any]:
    if isinstance(baseline, dict):
        return baseline
    try:
        return json.loads(Path(baseline).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"captures": [], "error": str(exc)}


def _capture_index(result: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    captures = result.get("captures")
    if not isinstance(captures, list):
        return {}
    output: dict[tuple[str, str], dict[str, Any]] = {}
    for item in captures:
        if not isinstance(item, dict):
            continue
        file_name = str(item.get("file") or "")
        viewport = str(item.get("viewport") or "")
        if file_name and viewport:
            output[(file_name, viewport)] = item
    return output


def _snapshot_file_fingerprint(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
    except OSError:
        return {"bytes": 0, "sha256": ""}
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def _public_browser_render_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in (
        "rendered_text_length",
        "root_width",
        "root_height",
        "render_width",
        "render_height",
        "visible_marker_count",
        "rendered_decorative_ellipsis_count",
    ):
        value = metadata.get(key)
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            output[key] = int(value)
    return output


def _browser_render_metadata_checks(file_name: str, viewport_id: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    if not metadata:
        return []
    checks: list[dict[str, Any]] = []
    text_length = int(metadata.get("rendered_text_length") or 0)
    checks.append(
        {
            "file": file_name,
            "viewport": viewport_id,
            "check": "rendered_text",
            "status": "pass" if text_length >= 24 else "fail",
            "message": (
                f"Rendered page text length is {text_length}."
                if text_length >= 24
                else "Rendered page appears blank or nearly blank after JavaScript execution."
            ),
            "rendered_text_length": text_length,
        }
    )
    root_width = int(metadata.get("root_width") or 0)
    root_height = int(metadata.get("root_height") or 0)
    render_width = int(metadata.get("render_width") or root_width or 0)
    render_height = int(metadata.get("render_height") or root_height or 0)
    checks.append(
        {
            "file": file_name,
            "viewport": viewport_id,
            "check": "root_box",
            "status": "pass" if render_width > 0 and render_height > 0 else "fail",
            "message": (
                f"Rendered container measured at {render_width}x{render_height}."
                if render_width > 0 and render_height > 0
                else "Rendered container has no measurable size."
            ),
            "root_width": root_width,
            "root_height": root_height,
            "render_width": render_width,
            "render_height": render_height,
        }
    )
    ellipsis_count = int(metadata.get("rendered_decorative_ellipsis_count") or 0)
    checks.append(
        {
            "file": file_name,
            "viewport": viewport_id,
            "check": "rendered_decorative_ellipsis",
            "status": "pass" if ellipsis_count == 0 else "fail",
            "message": (
                "Rendered page text does not contain decorative clipping ellipses."
                if ellipsis_count == 0
                else f"Rendered page text contains {ellipsis_count} decorative clipping ellipsis marker(s)."
            ),
            "rendered_decorative_ellipsis_count": ellipsis_count,
        }
    )
    return checks


def _public_browser_interaction_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for key in (
        "console_errors",
        "paper_map_nodes_before",
        "paper_map_nodes_after_branch",
        "paper_lens_paragraphs",
        "roadmap_resources_before",
        "roadmap_resources_after_filter",
        "roadmap_filter_attempts",
        "paper_lens_active_before",
        "paper_lens_active_after",
        "roadmap_filter_method",
    ):
        value = metadata.get(key)
        if isinstance(value, bool):
            output[key] = value
        elif isinstance(value, (int, float)):
            output[key] = int(value)
        elif isinstance(value, str):
            output[key] = _sanitize_public_text(value)
    for key in (
        "paper_map_canvas_present",
        "paper_map_branch_toggle_available",
        "paper_map_branch_revealed",
        "paper_map_detail_changed",
        "paper_map_zoom_changed",
        "paper_map_zoom_method",
        "roadmap_filter_changed",
        "paper_lens_detail_changed",
    ):
        if isinstance(metadata.get(key), bool):
            output[key] = bool(metadata[key])
        elif isinstance(metadata.get(key), str):
            output[key] = _sanitize_public_text(str(metadata[key]))
    return output


def _browser_interaction_metadata_checks(file_name: str, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    console_errors = int(metadata.get("console_errors") or 0)
    checks.append(
        {
            "file": file_name,
            "check": "console_errors",
            "status": "pass" if console_errors == 0 else "fail",
            "message": (
                "No browser console errors were recorded during the interaction probe."
                if console_errors == 0
                else f"Browser recorded {console_errors} console error(s) during the interaction probe."
            ),
            "console_errors": console_errors,
        }
    )
    if file_name == "paper_map.html":
        nodes_before = int(metadata.get("paper_map_nodes_before") or 0)
        branch_applicable = (
            bool(metadata.get("paper_map_branch_toggle_available"))
            or bool(metadata.get("paper_map_branch_revealed"))
            or (
                "paper_map_branch_toggle_available" not in metadata
                and nodes_before > 1
            )
        )
        checks.extend(
            [
                _interaction_bool_check(
                    file_name,
                    "paper_map_canvas_present",
                    bool(metadata.get("paper_map_canvas_present")),
                    "Paper Map canvas rendered in the browser.",
                    "Paper Map canvas did not render in the browser.",
                ),
                _interaction_bool_check(
                    file_name,
                    "paper_map_branch_revealed",
                    bool(metadata.get("paper_map_branch_revealed")) if branch_applicable else None,
                    "Paper Map branch toggle revealed supporting nodes.",
                    "Paper Map branch toggle did not reveal supporting nodes.",
                    skip_message="Paper Map has no enabled branch toggle in this concise layout, so branch expansion is not applicable.",
                ),
                _interaction_bool_check(
                    file_name,
                    "paper_map_detail_changed",
                    bool(metadata.get("paper_map_detail_changed")) if nodes_before > 1 else None,
                    "Clicking a Paper Map node updated the detail panel.",
                    "Clicking a Paper Map node did not update the detail panel.",
                    skip_message="Paper Map has fewer than two nodes, so node-to-node detail switching is not applicable.",
                ),
                _interaction_bool_check(
                    file_name,
                    "paper_map_zoom_changed",
                    bool(metadata.get("paper_map_zoom_changed")),
                    "Paper Map zoom/pan viewport transform changed after a zoom control or wheel input.",
                    "Paper Map zoom/pan viewport transform did not change after zoom controls or wheel input.",
                ),
            ]
        )
    elif file_name == "roadmap.html":
        resources_before = int(metadata.get("roadmap_resources_before") or 0)
        checks.append(
            _interaction_bool_check(
                file_name,
                "roadmap_resources_present",
                resources_before > 0,
                "Roadmap resource library rendered at least one resource row before filtering.",
                "Roadmap resource library had no rendered resource rows to filter.",
            )
        )
        checks.append(
            _interaction_bool_check(
                file_name,
                "roadmap_filter_changed",
                resources_before > 0 and bool(metadata.get("roadmap_filter_changed")),
                "Roadmap resource filtering changed the visible resource set.",
                "Roadmap resource filtering did not change the visible resource set.",
            )
        )
    elif file_name == "paper_lens.html":
        paragraphs_value = metadata.get("paper_lens_paragraphs")
        paragraphs = int(paragraphs_value or 0)
        lens_detail_applicable = paragraphs > 1 or "paper_lens_paragraphs" not in metadata
        checks.append(
            _interaction_bool_check(
                file_name,
                "paper_lens_detail_changed",
                bool(metadata.get("paper_lens_detail_changed")) if lens_detail_applicable else None,
                "Clicking a Paper Lens paragraph updated the detail panel.",
                "Clicking a Paper Lens paragraph did not update the detail panel.",
                skip_message="Paper Lens has fewer than two paragraphs, so paragraph-to-paragraph detail switching is not applicable.",
            )
        )
    return checks


def _interaction_bool_check(
    file_name: str,
    check: str,
    passed: bool | None,
    pass_message: str,
    fail_message: str,
    *,
    skip_message: str | None = None,
) -> dict[str, Any]:
    if passed is None:
        return {
            "file": file_name,
            "check": check,
            "status": "skipped",
            "message": skip_message or "Interaction check is not applicable for this report.",
        }
    return {
        "file": file_name,
        "check": check,
        "status": "pass" if passed else "fail",
        "message": pass_message if passed else fail_message,
    }


def _browser_interaction_result(
    status: str,
    checks: list[dict[str, Any]],
    probes: list[dict[str, Any]],
    reason: str,
) -> dict[str, Any]:
    failed = sum(1 for item in checks if item.get("status") == "fail")
    return {
        "status": status,
        "summary": {
            "mode": "browser-interaction",
            "pages": len(probes),
            "checks": len(checks),
            "failed_checks": failed,
            "reason": reason,
        },
        "probes": probes,
        "checks": checks,
    }


def _browser_snapshot_result(
    status: str,
    checks: list[dict[str, Any]],
    captures: list[dict[str, Any]],
    reason: str,
    snapshot_root: Path,
) -> dict[str, Any]:
    failed = sum(1 for item in checks if item.get("status") == "fail")
    return {
        "status": status,
        "summary": {
            "mode": "browser-backed",
            "viewports": [item["id"] for item in BROWSER_SNAPSHOT_VIEWPORTS],
            "screenshots": len(captures),
            "failed_screenshots": failed,
            "reason": reason,
            "manifest": _relative_posix_path(snapshot_root / "manifest.json", snapshot_root.parent),
        },
        "captures": captures,
        "checks": checks,
    }


def _write_browser_snapshot_manifest(snapshot_root: Path, result: dict[str, Any]) -> None:
    try:
        snapshot_root.mkdir(parents=True, exist_ok=True)
        (snapshot_root / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        return


def _relative_posix_path(path: Path, root: Path) -> str:
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        relative = path.name
    return relative.as_posix()


def _playwright_snapshot_renderer(html_file: Path, viewport: dict[str, int | str], screenshot_file: Path) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on optional local tooling.
        raise BrowserSnapshotUnavailable(
            "Python Playwright is not installed; install an optional browser runtime to capture real screenshots."
        ) from exc
    try:  # pragma: no cover - exercised only when optional browser runtime exists.
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": int(viewport["width"]), "height": int(viewport["height"])})
            page.goto(html_file.resolve().as_uri(), wait_until="networkidle")
            try:
                page.wait_for_function("document.body && document.body.innerText.trim().length > 20", timeout=3000)
            except Exception:
                pass
            render_metadata = page.evaluate(
                """() => {
                    const root = document.getElementById("root");
                    const fallback = document.querySelector("main") || document.body || document.documentElement;
                    const container = root || fallback;
                    const rect = container ? container.getBoundingClientRect() : { width: 0, height: 0 };
                    const rootRect = root ? root.getBoundingClientRect() : { width: 0, height: 0 };
                    const renderedText = (document.body && document.body.innerText || "").trim();
                    const ellipsisMatches = renderedText.match(/\\.{3}|…/g) || [];
                    const visibleMarkers = document.querySelectorAll(
                        "a,button,[data-report-kind],[data-report-static-fallback],.paper-map-node,.paragraph-card,.resource-row"
                    ).length;
                    return {
                        rendered_text_length: renderedText.length,
                        root_width: Math.round(rootRect.width || 0),
                        root_height: Math.round(rootRect.height || 0),
                        render_width: Math.round(rect.width || 0),
                        render_height: Math.round(rect.height || 0),
                        visible_marker_count: visibleMarkers,
                        rendered_decorative_ellipsis_count: ellipsisMatches.length,
                    };
                }"""
            )
            page.screenshot(path=str(screenshot_file), full_page=True)
            browser.close()
            return render_metadata
    except Exception as exc:  # pragma: no cover - exact browser install errors vary by machine.
        message = str(exc)
        if "Executable doesn't exist" in message or "playwright install" in message.lower():
            raise BrowserSnapshotUnavailable(
                "Playwright is installed, but no browser binary is available; run the Playwright browser installer before capturing screenshots."
            ) from exc
        raise


def _playwright_interaction_runner(html_file: Path) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # pragma: no cover - depends on optional local tooling.
        raise BrowserSnapshotUnavailable(
            "Python Playwright is not installed; install an optional browser runtime to probe real report interactions."
        ) from exc
    try:  # pragma: no cover - exercised only when optional browser runtime exists.
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            console_errors: list[str] = []
            page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))
            page.goto(html_file.resolve().as_uri(), wait_until="networkidle")
            try:
                page.wait_for_function("document.body && document.body.innerText.trim().length > 20", timeout=4000)
            except Exception:
                pass
            page.wait_for_timeout(250)
            metadata: dict[str, Any] = {"console_errors": len(console_errors)}
            if html_file.name == "paper_map.html":
                metadata.update(_probe_paper_map_page(page))
            elif html_file.name == "roadmap.html":
                metadata.update(_probe_roadmap_page(page))
            elif html_file.name == "paper_lens.html":
                metadata.update(_probe_paper_lens_page(page))
            browser.close()
            return metadata
    except Exception as exc:  # pragma: no cover - exact browser install errors vary by machine.
        message = str(exc)
        if "Executable doesn't exist" in message or "playwright install" in message.lower():
            raise BrowserSnapshotUnavailable(
                "Playwright is installed, but no browser binary is available; run the Playwright browser installer before probing interactions."
            ) from exc
        raise


def _probe_paper_map_page(page: Any) -> dict[str, Any]:
    canvas = page.locator("[data-paper-map-canvas]")
    canvas_present = canvas.count() > 0
    node_locator = page.locator(".react-flow__node")
    nodes_before = node_locator.count()
    branch_revealed = False
    branch_toggle = page.locator("[data-paper-map-branch-toggle]")
    branch_toggle_available = branch_toggle.count() > 0 and branch_toggle.first.is_enabled()
    if branch_toggle_available:
        try:
            branch_toggle.first.click()
            page.wait_for_timeout(250)
            branch_revealed = node_locator.count() > nodes_before or branch_toggle.first.get_attribute("aria-pressed") == "true"
        except Exception:
            branch_revealed = False
    nodes_after_branch = node_locator.count()
    detail_before = _safe_locator_text(page, ".detail-rail h2")
    detail_changed = False
    if node_locator.count() > 1:
        try:
            node_locator.nth(1).click()
            page.wait_for_timeout(200)
            detail_changed = _safe_locator_text(page, ".detail-rail h2") != detail_before
        except Exception:
            detail_changed = False
    transform_before = _paper_map_viewport_transform(page)
    zoom_changed = False
    zoom_method = ""
    zoom_button = page.locator(".react-flow__controls-zoomin, [data-paper-map-zoom-in]")
    if zoom_button.count() > 0:
        try:
            zoom_button.first.click()
            page.wait_for_timeout(250)
            zoom_changed = _paper_map_viewport_transform(page) != transform_before
            if zoom_changed:
                zoom_method = "button"
        except Exception:
            zoom_changed = False
    if not zoom_changed and canvas_present:
        try:
            box = canvas.first.bounding_box()
            if box:
                page.mouse.move(float(box["x"]) + float(box["width"]) / 2, float(box["y"]) + float(box["height"]) / 2)
            else:
                page.mouse.move(640, 360)
            page.mouse.wheel(0, -500)
            page.wait_for_timeout(250)
            zoom_changed = _paper_map_viewport_transform(page) != transform_before
            if zoom_changed:
                zoom_method = "wheel"
        except Exception:
            zoom_changed = False
    return {
        "paper_map_canvas_present": canvas_present,
        "paper_map_nodes_before": nodes_before,
        "paper_map_nodes_after_branch": nodes_after_branch,
        "paper_map_branch_toggle_available": branch_toggle_available,
        "paper_map_branch_revealed": branch_revealed,
        "paper_map_detail_changed": detail_changed,
        "paper_map_zoom_changed": zoom_changed,
        "paper_map_zoom_method": zoom_method,
    }


def _probe_roadmap_page(page: Any) -> dict[str, Any]:
    resource_cards = page.locator("#resource-library .resource-row, #resource-library article, [data-library-card]")
    before = resource_cards.count()
    filter_changed = False
    filter_method = ""
    filter_attempts = 0
    after = before
    filter_chips = page.locator('#resource-library [data-resource-filter]:not([data-resource-filter="all"])')
    for index in range(filter_chips.count()):
        try:
            chip = filter_chips.nth(index)
            chip.click()
            page.wait_for_timeout(200)
            after = resource_cards.count()
            filter_attempts += 1
            if after != before:
                filter_changed = True
                filter_method = str(chip.get_attribute("data-resource-filter") or "chip")
                break
        except Exception:
            after = resource_cards.count()
    if not filter_changed and before > 0:
        search = page.locator("#resource-library input")
        if search.count() > 0:
            try:
                search.first.fill("__fields_study_flow_no_match__")
                page.wait_for_timeout(200)
                after = resource_cards.count()
                filter_attempts += 1
                if after != before:
                    filter_changed = True
                    filter_method = "search"
            except Exception:
                after = resource_cards.count()
    return {
        "roadmap_resources_before": before,
        "roadmap_resources_after_filter": after,
        "roadmap_filter_changed": filter_changed,
        "roadmap_filter_method": filter_method,
        "roadmap_filter_attempts": filter_attempts,
    }


def _probe_paper_lens_page(page: Any) -> dict[str, Any]:
    paragraphs = page.locator(".paragraph-card")
    paragraph_count = paragraphs.count()
    active_before = _safe_locator_text(page, ".detail-rail h2")
    detail_changed = False
    if paragraph_count > 1:
        try:
            paragraphs.nth(1).click()
            page.wait_for_timeout(200)
            detail_changed = _safe_locator_text(page, ".detail-rail h2") != active_before
        except Exception:
            detail_changed = False
    return {
        "paper_lens_paragraphs": paragraph_count,
        "paper_lens_active_before": active_before,
        "paper_lens_active_after": _safe_locator_text(page, ".detail-rail h2"),
        "paper_lens_detail_changed": detail_changed,
    }


def _paper_map_viewport_transform(page: Any) -> str:
    try:
        return str(
            page.evaluate(
                """() => {
                    const el = document.querySelector(".react-flow__viewport, [data-paper-map-viewport]");
                    if (!el) return "";
                    const style = el.getAttribute("style") || "";
                    const transform = el.getAttribute("transform") || "";
                    const computed = window.getComputedStyle(el).transform || "";
                    return `${style}|${transform}|${computed}`;
                }"""
            )
        )
    except Exception:
        try:
            return _safe_locator_attribute(page.locator(".react-flow__viewport, [data-paper-map-viewport]"), "style")
        except Exception:
            return ""


def _safe_locator_text(page: Any, selector: str) -> str:
    try:
        locator = page.locator(selector)
        if locator.count() <= 0:
            return ""
        return str(locator.first.inner_text(timeout=500))
    except Exception:
        return ""


def _safe_locator_attribute(locator: Any, name: str) -> str:
    try:
        if locator.count() <= 0:
            return ""
        return str(locator.first.get_attribute(name) or "")
    except Exception:
        return ""


def _report_surfaces(root: Path) -> list[str]:
    preferred = ["index.html", "paper_map.html", "paper_lens.html", "roadmap.html"]
    existing = {path.name for path in root.glob("*.html") if path.is_file()}
    ordered = [name for name in preferred if name in existing]
    ordered.extend(sorted(name for name in existing if name not in set(preferred)))
    return ordered


def _recommended_first_action(roadmap: dict[str, Any], surfaces: list[str]) -> dict[str, str]:
    language = str((roadmap.get("profile") or {}).get("output_language") or "").lower()
    is_zh = language.startswith("zh")
    if roadmap.get("paper_map") or "paper_map.html" in surfaces:
        return {
            "href": "paper_map.html",
            "label": "进入论文逻辑图" if is_zh else "Open Paper Map",
            "reason": "先用图形主链抓住论文背景、动机、方法、实验和贡献。" if is_zh else "Start with the visual logic chain before deep reading.",
        }
    if roadmap.get("paper_lens") or "paper_lens.html" in surfaces:
        return {
            "href": "paper_lens.html",
            "label": "进入段落精读" if is_zh else "Open Paper Lens",
            "reason": "先读目标论文关键段落和证据解释。" if is_zh else "Start with the target paper paragraphs and evidence.",
        }
    if "roadmap.html" in surfaces:
        return {
            "href": "roadmap.html",
            "label": "进入学习路线" if is_zh else "Open Roadmap",
            "reason": "从学习阶段、资料包和验收任务开始。" if is_zh else "Start from phases, resources, and mastery tasks.",
        }
    return {
        "href": "index.html" if "index.html" in surfaces else "",
        "label": "打开报告首页" if is_zh else "Open Report Index",
        "reason": "当前目录只找到有限报告页面。" if is_zh else "Only limited report surfaces were found.",
    }


def _market_readiness(
    roadmap: dict[str, Any],
    surfaces: list[str],
    visual_audit: dict[str, Any],
    experience_risks: dict[str, Any] | None = None,
    fresh_user_flow: dict[str, Any] | None = None,
    viewport_risks: dict[str, Any] | None = None,
    visual_snapshot_matrix: dict[str, Any] | None = None,
    competitive_benchmark: dict[str, Any] | None = None,
) -> dict[str, Any]:
    dimensions = [
        _onboarding_dimension(roadmap, surfaces, visual_audit),
        _visual_polish_dimension(visual_audit),
        _learning_depth_dimension(roadmap),
        _plain_explanation_dimension(roadmap),
        _resource_completeness_dimension(roadmap),
        _actionability_dimension(roadmap),
    ]
    warning_count = int(((experience_risks or {}).get("summary") or {}).get("warnings") or 0)
    warning_count += int(((fresh_user_flow or {}).get("summary") or {}).get("warnings") or 0)
    warning_count += int(((viewport_risks or {}).get("summary") or {}).get("warnings") or 0)
    warning_count += int(((visual_snapshot_matrix or {}).get("summary") or {}).get("warnings") or 0)
    warning_count += int(((competitive_benchmark or {}).get("summary") or {}).get("warnings") or 0)
    score = max(0, round(sum(item["score"] for item in dimensions) / max(len(dimensions), 1)) - min(warning_count * 5, 20))
    blockers = [item for item in dimensions if item["score"] < 60]
    risk_statuses = {
        (experience_risks or {}).get("status", "pass"),
        (fresh_user_flow or {}).get("status", "pass"),
        (viewport_risks or {}).get("status", "pass"),
        (visual_snapshot_matrix or {}).get("status", "pass"),
        (competitive_benchmark or {}).get("status", "pass"),
    }
    status = (
        "market_ready"
        if score >= 80 and not blockers and visual_audit.get("status") == "pass" and risk_statuses == {"pass"}
        else "needs_improvement"
    )
    return {
        "status": status,
        "score": score,
        "dimensions": dimensions,
        "blockers": [{"id": item["id"], "label": item["label"], "score": item["score"]} for item in blockers],
        "next_best_actions": _market_next_best_actions(dimensions, status, competitive_benchmark, fresh_user_flow, visual_snapshot_matrix),
        "competitive_positioning": _competitive_positioning(roadmap),
    }


def _competitive_benchmark(
    root: Path,
    roadmap: dict[str, Any],
    surfaces: list[str],
    visual_audit: dict[str, Any],
    experience_risks: dict[str, Any],
    viewport_risks: dict[str, Any],
) -> dict[str, Any]:
    html = {name: _read_text(root / name) for name in surfaces}
    if _is_field_or_course_target(roadmap):
        return _field_course_competitive_benchmark(roadmap, surfaces, html)
    lens = roadmap.get("paper_lens") if isinstance(roadmap.get("paper_lens"), dict) else {}
    explanations = [item for item in lens.get("inline_explanations", []) if isinstance(item, dict)]
    confidence_values = {str(item.get("confidence")) for item in explanations if item.get("confidence") is not None}
    kg_summary = _dict_at(roadmap, "knowledge_graph", "summary")
    tasks = _list_at(roadmap, "study_tasks")
    task_types = {str(item.get("type") or "") for item in tasks if isinstance(item, dict)}
    required_evidence = _list_at(roadmap, "mastery_evidence", "required_evidence")
    paper_map_html = html.get("paper_map.html", "")
    checks = [
        _benchmark_check(
            "paperqa_grounded_evidence",
            "PaperQA-style grounded evidence",
            bool(explanations)
            and (
                len(confidence_values) >= 2
                or int(kg_summary.get("evidence_backed_edges") or 0) > 0
                or any(item.get("evidence_refs") for item in explanations)
            ),
            "Add evidence-backed paragraph explanations with varied confidence or source references, not just prose summaries.",
            "PaperQA2",
        ),
        _benchmark_check(
            "explainpaper_contextual_explanations",
            "Explainpaper-style contextual explanations",
            _paper_lens_contextual_explanations(roadmap, html),
            "Provide paragraph-level explanations that are grounded in the target paper context, not only generic summaries.",
            "Explainpaper",
        ),
        _benchmark_check(
            "scholarcy_structured_review_cards",
            "Scholarcy-style structured review cards",
            _structured_quick_review_surface(roadmap, html),
            "Give learners a structured skim surface: paper logic, paragraph focus, and portable notes or worksheet output.",
            "Scholarcy",
        ),
        _benchmark_check(
            "get_it_measurable_mastery_map",
            "Get It-style measurable mastery map",
            bool(roadmap.get("paper_map"))
            and bool(roadmap.get("paper_lens"))
            and len(task_types & {"explain", "derive", "reproduce", "critique"}) >= 3
            and bool(required_evidence),
            "Keep the target paper at the center and connect the map to concrete mastery evidence.",
            "Get It",
        ),
        _benchmark_check(
            "notebooklm_portable_study_outputs",
            "NotebookLM-style portable study outputs",
            _portable_study_output_count(roadmap, html) >= 2,
            "Give learners study outputs they can carry away: presentation notes, a concise reading export, or concrete mastery artifacts.",
            "NotebookLM / Elicit",
        ),
        _benchmark_check(
            "roadmap_interactive_first_step",
            "roadmap.sh-style first interaction",
            "index.html" in surfaces
            and _contains_any_text(
                html.get("index.html", ""),
                ("10 分钟入门", "10-minute quickstart", "换成自己的论文", "Bring Your Own Paper"),
            ),
            "Give new users one obvious first action before they face the full report.",
            "roadmap.sh",
        ),
        _benchmark_check(
            "litmaps_research_context_boundary",
            "Litmaps-style research context boundary",
            _resource_evidence_review_link_count(roadmap, html) > 0
            and _contains_any_text(html.get("paper_map.html", ""), ("Evidence coverage", "证据覆盖", "璇佹嵁瑕嗙洊")),
            "Show which supporting literature or resource evidence belongs to the target-paper map, rather than leaving discovery as a loose graph.",
            "Litmaps / ResearchRabbit",
        ),
        _benchmark_check(
            "xyflow_canvas_affordance",
            "React Flow-style canvas affordance",
            bool(roadmap.get("paper_map"))
            and _contains_any_text(paper_map_html, ("data-paper-map-canvas", "react-flow"))
            and _contains_any_text(
                paper_map_html,
                ("Reading Density", "阅读密度", "Core Chain", "速览主链"),
            ),
            "Expose a real zoomable/draggable node canvas instead of a static card report.",
            "React Flow / xyflow",
        ),
        _benchmark_check(
            "local_first_bundle",
            "Local-first study bundle",
            _local_resource_ratio(roadmap) >= 0.5,
            "Download, copy, snapshot, or generate the resources that matter so the report is useful offline.",
            "Get It / local-first study apps",
        ),
        _benchmark_check(
            "resource_purpose_badges",
            "Resource purpose badges",
            _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-purpose-badge", "为什么读", "Why read")),
            "Explain why each resource is in the path, not only where to open it.",
            "roadmap.sh / study-product UX",
        ),
        _benchmark_check(
            "resource_strength_signals",
            "Resource strength and provenance signals",
            _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-strength-badge", "证据强度", "Evidence strength")),
            "Show whether a resource is core evidence, recommended support, or a fallback link.",
            "PaperQA-style trust / study-product UX",
        ),
        _benchmark_check(
            "resource_provenance_coverage",
            "Resource provenance and paper-logic coverage",
            _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-provenance-badge", "来源", "Provenance"))
            and _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-coverage-badge", "覆盖范围", "Coverage")),
            "Show where each resource comes from and which paper-logic surface it helps cover.",
            "Elicit / PaperQA / ResearchRabbit",
        ),
        _benchmark_check(
            "resource_evidence_snippets",
            "Resource evidence snippets",
            _resource_library_has_evidence(roadmap)
            and _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-evidence-snippet", "最强证据", "Strongest evidence")),
            "Expose the strongest supporting snippet for high-value resources so learners can verify why a source was selected.",
            "Elicit / citation-backed research UX",
        ),
        _benchmark_check(
            "resource_evidence_review_links",
            "Resource evidence review links",
            _resource_evidence_review_link_count(roadmap, html) > 0,
            "Link the strongest resource evidence back to Paper Lens, a downloaded file, or the original source so learners can review the citation trail.",
            "Elicit / PaperQA / PaperQA2",
        ),
    ]
    warnings = [item for item in checks if item["status"] == "warn"]
    return {
        "status": "warn" if warnings else "pass",
        "summary": {
            "checks": len(checks),
            "passed_checks": len(checks) - len(warnings),
            "warnings": len(warnings),
        },
        "basis": [
            {
                "project": "PaperQA2",
                "lesson": "Scientific readers win trust when answers are grounded in retrievable evidence.",
            },
            {
                "project": "Explainpaper",
                "lesson": "Fast paper readers need contextual explanations at the confusing passage, not generic summaries.",
            },
            {
                "project": "Scholarcy",
                "lesson": "Structured review cards and exports make skimming useful when learners must explain the paper later.",
            },
            {
                "project": "Get It",
                "lesson": "Single-document learning is strongest when it becomes a measurable mastery map.",
            },
            {
                "project": "NotebookLM / Elicit",
                "lesson": "Learning assistants become sticky when the source set turns into portable outputs: briefs, presentations, and checkable artifacts.",
            },
            {
                "project": "roadmap.sh",
                "lesson": "A clear first click makes a large learning path approachable.",
            },
            {
                "project": "React Flow / xyflow",
                "lesson": "Node-based learning maps need mature canvas affordances: pan, zoom, drag, and fit-to-view.",
            },
            {
                "project": "Litmaps / ResearchRabbit",
                "lesson": "Literature context is most useful when it stays connected to the target paper's logic, not as a loose discovery graph.",
            },
        ],
        "checks": checks,
    }


def _field_course_competitive_benchmark(roadmap: dict[str, Any], surfaces: list[str], html: dict[str, str]) -> dict[str, Any]:
    tasks = _list_at(roadmap, "study_tasks")
    task_types = {str(item.get("type") or "") for item in tasks if isinstance(item, dict)}
    required_evidence = _list_at(roadmap, "mastery_evidence", "required_evidence")
    kg_summary = _dict_at(roadmap, "knowledge_graph", "summary")
    checks = [
        _benchmark_check(
            "roadmap_interactive_first_step",
            "roadmap.sh-style first interaction",
            "index.html" in surfaces
            and _contains_any_text(
                html.get("index.html", ""),
                ("10 分钟入门", "10-minute quickstart", "换成自己的论文", "Bring Your Own Paper"),
            ),
            "Give new users one obvious first action before they face the full route.",
            "roadmap.sh",
        ),
        _benchmark_check(
            "field_course_path_structure",
            "Field/course path structure",
            len(_list_at(roadmap, "phases")) >= 3
            and int(kg_summary.get("edges") or 0) >= 8
            and (len(_list_at(roadmap, "learning_key_points")) + len(_list_at(roadmap, "focus_areas"))) >= 4,
            "For field/course goals, show prerequisites, core concepts, implementation/project, synthesis, and a navigable knowledge graph.",
            "roadmap.sh / course planners",
        ),
        _benchmark_check(
            "field_course_measurable_mastery",
            "Field/course measurable mastery",
            len(task_types & {"explain", "derive", "reproduce", "critique"}) >= 3 and bool(required_evidence),
            "Field/course routes still need concrete explain, derive, reproduce, and critique evidence.",
            "Get It / mastery learning",
        ),
        _benchmark_check(
            "scenario_coverage_entry",
            "Scenario coverage entry",
            _contains_any_text(
                html.get("index.html", ""),
                ("scenario-panel", "支持三种学习场景", "Three Learning Scenarios", "Field / course route"),
            ),
            "Make it obvious that the product handles single papers, paper sets, and field/course routes.",
            "roadmap.sh / product onboarding",
        ),
        _benchmark_check(
            "local_first_bundle",
            "Local-first study bundle",
            _local_resource_ratio(roadmap) >= 0.5,
            "Download, copy, snapshot, or generate the resources that matter so the report is useful offline.",
            "Get It / local-first study apps",
        ),
        _benchmark_check(
            "resource_purpose_badges",
            "Resource purpose badges",
            _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-purpose-badge", "为什么读", "Why read")),
            "Explain why each resource is in the path, not only where to open it.",
            "roadmap.sh / study-product UX",
        ),
        _benchmark_check(
            "resource_strength_signals",
            "Resource strength and provenance signals",
            _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-strength-badge", "证据强度", "Evidence strength")),
            "Show whether each resource is core evidence, recommended support, or a fallback link.",
            "Elicit / study-product UX",
        ),
        _benchmark_check(
            "resource_provenance_coverage",
            "Resource provenance and learning-surface coverage",
            _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-provenance-badge", "来源", "Provenance"))
            and _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-coverage-badge", "覆盖范围", "Coverage")),
            "Show where each resource comes from and which concept, task, or validation surface it covers.",
            "Elicit / PaperQA / ResearchRabbit",
        ),
        _benchmark_check(
            "resource_evidence_snippets",
            "Resource evidence snippets",
            _resource_library_has_evidence(roadmap)
            and _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-evidence-snippet", "最强证据", "Strongest evidence")),
            "Expose the strongest supporting snippet for high-value resources so learners can verify why a source was selected.",
            "Elicit / citation-backed research UX",
        ),
        _benchmark_check(
            "resource_evidence_review_links",
            "Resource evidence review links",
            _resource_evidence_review_link_count(roadmap, html) > 0,
            "Link the strongest resource evidence back to a downloaded file, Paper Lens, or the original source so learners can review why the resource belongs in the path.",
            "Elicit / PaperQA",
        ),
    ]
    warnings = [item for item in checks if item["status"] == "warn"]
    return {
        "status": "warn" if warnings else "pass",
        "summary": {
            "checks": len(checks),
            "passed_checks": len(checks) - len(warnings),
            "warnings": len(warnings),
        },
        "basis": [
            {
                "project": "roadmap.sh",
                "lesson": "Field learning wins when the first route is structured and scannable.",
            },
            {
                "project": "Elicit",
                "lesson": "Resources need evidence and provenance signals, not just a title list.",
            },
            {
                "project": "Get It",
                "lesson": "Learning products become useful when progress is measurable through artifacts.",
            },
        ],
        "checks": checks,
    }


def _benchmark_check(id_: str, label: str, passed: bool, recommendation: str, competitor: str) -> dict[str, str]:
    item = _experience_check(id_, label, passed, recommendation)
    item["competitor_reference"] = competitor
    return item


def _portable_study_output_count(roadmap: dict[str, Any], html: dict[str, str]) -> int:
    outputs = 0
    paper_map_html = html.get("paper_map.html", "")
    paper_lens_html = html.get("paper_lens.html", "")
    roadmap_html = html.get("roadmap.html", "")
    if _contains_any_text(
        paper_map_html,
        (
            "data-presentation-script",
            "Download presentation notes",
            "paper_map_presentation.md",
            "下载汇报稿",
            "汇报稿",
        ),
    ):
        outputs += 1
    lens = roadmap.get("paper_lens") if isinstance(roadmap.get("paper_lens"), dict) else {}
    latex_export = lens.get("latex_export") if isinstance(lens.get("latex_export"), dict) else {}
    if latex_export.get("pdf_file") or latex_export.get("tex_file") or _contains_any_text(
        paper_lens_html,
        (
            "paper_lens.pdf",
            "paper_lens.tex",
            "PDF",
            "LaTeX",
            "打开 PDF",
            "精简版",
        ),
    ):
        outputs += 1
    task_types = {str(item.get("type") or "") for item in _list_at(roadmap, "study_tasks") if isinstance(item, dict)}
    required_evidence = _list_at(roadmap, "mastery_evidence", "required_evidence")
    if (
        len(task_types & {"explain", "derive", "reproduce", "critique"}) >= 3
        and bool(required_evidence)
        and _contains_any_text(
            roadmap_html,
            (
                "data-mastery-export",
                "mastery_worksheet.md",
                "复制证据清单",
                "下载 worksheet",
                "Copy evidence worksheet",
                "Download worksheet",
            ),
        )
    ):
        outputs += 1
    return outputs


def _experience_risks(root: Path, roadmap: dict[str, Any], surfaces: list[str], visual_audit: dict[str, Any]) -> dict[str, Any]:
    html = {name: _read_text(root / name) for name in surfaces}
    checks = [
        _experience_check(
            "first_screen_quickstart",
            "First-screen quickstart",
            _contains_any_text(html.get("index.html", ""), ("10 分钟入门", "10-minute quickstart")),
            "Add a visible 10-minute quickstart so a new learner knows the first three actions.",
        ),
        _experience_check(
            "intent_router_choice",
            "Intent-based entry choice",
            _contains_any_text(
                html.get("index.html", ""),
                ("intent-router-panel", "data-intent-router", "按你的目的选择入口", "Choose by what you need"),
            ),
            "Add an intent-based router on index.html so learners can choose fastest understanding, presentation preparation, or mastery validation without learning the report structure first.",
        ),
        _experience_check(
            "market_value_panel",
            "Market value proposition panel",
            _contains_any_text(
                html.get("index.html", ""),
                ("data-market-value-panel", "为什么它不只是 PDF 总结器", "Why this is more than a PDF summarizer", "Differentiated value"),
            ),
            "Show a compact value proposition on index.html so new users understand the product wedge before opening the detailed reports.",
        ),
        _experience_check(
            "recommended_first_action_panel",
            "Recommended first action panel",
            _contains_any_text(
                html.get("index.html", ""),
                ("data-recommended-action-panel", "data-recommended-first-action", "推荐第一步", "Recommended first action"),
            )
            or (
                _contains_any_text(html.get("index.html", ""), ("intent-router-panel", "data-intent-router"))
                and _contains_any_text(html.get("index.html", ""), ("fresh-user-flow-panel", "data-fresh-user-flow", "10-minute quickstart", "10 分钟入门"))
            ),
            "Show one explicit recommended first click so new users do not need to compare every report surface before starting.",
        ),
        _experience_check(
            "learning_outcome_contract",
            "Learning outcome contract",
            _contains_any_text(
                html.get("index.html", ""),
                ("data-learning-outcome-contract", "学完后你应该能交付什么", "What you should be able to deliver", "Outcome contract"),
            )
            or _contains_any_text(
                html.get("roadmap.html", ""),
                ("data-mastery-export", "mastery_worksheet.md", "Copy evidence worksheet", "下载 worksheet"),
            ),
            "Make the expected learning outputs explicit: explain, derive, reproduce, and critique should feel like concrete deliverables, not hidden implementation details.",
        ),
        _experience_check(
            "support_files_progressive_disclosure",
            "Support files progressive disclosure",
            ("support-panel" not in html.get("index.html", ""))
            or _contains_any_text(
                html.get("index.html", ""),
                ("data-support-files-panel", "<details", "Open only when you need data or export files", "需要原始数据或导出文件时再展开"),
            ),
            "Keep technical JSON/Markdown/SVG support files behind a collapsed disclosure so new learners see the learning path before implementation artifacts.",
        ),
        _experience_check(
            "fresh_user_one_minute_start",
            "Fresh-user one-minute start",
            _contains_any_text(html.get("roadmap.html", ""), ("1分钟上手", "1 分钟上手", "1-minute start")),
            "Add a compact one-minute start panel in roadmap.html so a fresh learner knows what to click first.",
        ),
        _experience_check(
            "report_health_panel",
            "Report health panel",
            _contains_any_text(
                html.get("index.html", ""),
                ("report-health-panel", "报告健康状态", "Report Health", "report_audit.json"),
            ),
            "Show a visible report-health panel on index.html so users can trust local assets, privacy redaction, layout safety, and the audit trail.",
        ),
        _experience_check(
            "scenario_coverage_panel",
            "Scenario coverage panel",
            _contains_any_text(
                html.get("index.html", ""),
                ("scenario-panel", "支持三种学习场景", "Three Learning Scenarios", "Single paper", "Field / course route"),
            ),
            "Show single-paper, paper-set, and field/course entry points so the product is not perceived as only a one-off paper report.",
        ),
        _experience_check(
            "route_recovery_next_steps",
            "Route recovery next steps",
            not _needs_route_recovery(roadmap)
            or _contains_any_text(
                html.get("roadmap.html", ""),
                ("data-route-recovery", "Next steps to complete the route"),
            ),
            "When phases, mastery tasks, or resources are explicitly empty, show concrete recovery actions instead of leaving an empty report.",
        ),
        _experience_check(
            "frontend_static_fallback",
            "Frontend static fallback",
            _interactive_pages_have_static_fallback(html),
            "Keep a readable static fallback in interactive report pages so users do not see a blank page if JavaScript fails.",
        ),
        _experience_check(
            "paper_map_canvas_interaction",
            "Paper Map canvas interaction",
            _is_field_or_course_target(roadmap)
            or (
                bool(roadmap.get("paper_map"))
                and _contains_any_text(html.get("paper_map.html", ""), ("data-paper-map-canvas", "react-flow"))
                and _contains_any_text(html.get("paper_map.html", ""), ("Reading Density", "阅读密度", "Core Chain", "速览主链"))
            ),
            "Expose the graph canvas controls: reading density, core-chain mode, zoom, pan, and draggable nodes.",
        ),
        _experience_check(
            "paper_map_branch_deferral",
            "Paper Map branch deferral",
            _is_field_or_course_target(roadmap)
            or (
                bool(roadmap.get("paper_map"))
                and _contains_any_text(html.get("paper_map.html", ""), ("Full Exploration", "完整探索", "推荐资料（按需展开）", "按需展开"))
            ),
            "Keep resources and evidence branches collapsed by default so the main logic chain stays readable.",
        ),
        _experience_check(
            "paper_map_evidence_coverage",
            "Paper Map evidence coverage",
            _is_field_or_course_target(roadmap)
            or (
                bool(roadmap.get("paper_map"))
                and _contains_any_text(html.get("paper_map.html", ""), ("证据覆盖", "Evidence coverage"))
            ),
            "Show evidence coverage on Paper Map nodes so learners can see which claims are ready to trust and which need review.",
        ),
        _experience_check(
            "paper_map_presentation_export",
            "Paper Map presentation export",
            _is_field_or_course_target(roadmap)
            or (
                bool(roadmap.get("paper_map"))
                and _contains_any_text(
                    html.get("paper_map.html", ""),
                    ("下载汇报稿.md", "Download presentation notes", "presentation.md"),
                )
            ),
            "Let learners export the Paper Map logic chain as presentation notes instead of only reading it on screen.",
        ),
        _experience_check(
            "paper_lens_paragraph_focus",
            "Paragraph-level paper lens",
            _is_field_or_course_target(roadmap)
            or (bool(roadmap.get("paper_lens")) and _contains_any_text(html.get("paper_lens.html", ""), ("paragraph", "段落"))),
            "Use paragraph-level reading instead of sentence fragments to reduce repetition and visual weight.",
        ),
        _experience_check(
            "paper_lens_support_explainer",
            "Paper Lens explanation support label",
            _is_field_or_course_target(roadmap)
            or (
                bool(roadmap.get("paper_lens"))
                and _contains_any_text(
                    html.get("paper_lens.html", ""),
                    ("段落解释支撑度", "解释支撑度", "Explanation support"),
                )
                and _contains_any_text(
                    html.get("paper_lens.html", ""),
                    ("不是资源可信度", "not a resource trust score", "not resource trust"),
                )
            ),
            "Explain paragraph support scores clearly so learners do not confuse them with resource trust scores.",
        ),
        _experience_check(
            "resource_local_first",
            "Local-first resources",
            _local_resource_ratio(roadmap) > 0 or _contains_any_text(" ".join(html.values()), ("打开本地", "Open local", "local_href")),
            "Prefer local links for downloaded/copied/snapshotted resources, with network links as fallback.",
        ),
        _experience_check(
            "resource_purpose_badges",
            "Resource purpose badges",
            _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-purpose-badge", "为什么读", "Why read")),
            "Show why each resource matters: primary evidence, background, implementation, or validation.",
        ),
        _experience_check(
            "resource_strength_signals",
            "Resource strength and provenance signals",
            _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-strength-badge", "证据强度", "Evidence strength")),
            "Show whether each resource is a core source, recommended supplement, or manual fallback.",
        ),
        _experience_check(
            "resource_provenance_coverage",
            "Resource provenance and coverage",
            _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-provenance-badge", "来源", "Provenance"))
            and _resource_library_marker(roadmap, html.get("roadmap.html", ""), ("resource-coverage-badge", "覆盖范围", "Coverage")),
            "Show source provenance and which learning surface each resource supports, so learners can decide what to open first.",
        ),
        _experience_check(
            "mobile_wrap_layout",
            "Mobile and long-text layout safety",
            visual_audit.get("status") == "pass" and _all_core_pages_have_check(visual_audit, "wrap_safeguard"),
            "Keep viewport metadata, wrapping safeguards, and width constraints across all report pages.",
        ),
    ]
    warnings = [item for item in checks if item["status"] == "warn"]
    return {
        "status": "warn" if warnings else "pass",
        "summary": {"checks": len(checks), "warnings": len(warnings)},
        "checks": checks,
    }


def _fresh_user_flow(root: Path, roadmap: dict[str, Any], surfaces: list[str]) -> dict[str, Any]:
    html = {name: _read_text(root / name) for name in surfaces}
    index_html = html.get("index.html", "")
    roadmap_html = html.get("roadmap.html", "")
    combined = "\n".join(html.values())
    resources = [item for item in _bundle_resources(roadmap) if isinstance(item, dict)]
    has_local_resource = _local_resource_ratio(roadmap) > 0
    has_failed_resource = any(str(item.get("status") or "") == "failed" for item in resources)
    first_action = _recommended_first_action(roadmap, surfaces)
    paper_report = not _is_field_or_course_target(roadmap)
    checks = [
        _experience_check(
            "first_action_visible",
            "First action is visible",
            bool(first_action.get("href")) and _contains_any_text(index_html, ("Start Here", "从这里开始", "开始")),
            "Make the first report action visible on index.html before secondary artifacts.",
        ),
        _experience_check(
            "ten_minute_path_visible",
            "First 10-minute path is visible",
            _contains_any_text(
                index_html,
                ("data-fresh-user-flow", "fresh-user-flow-panel", "10-minute quickstart", "10 分钟入门"),
            )
            and (
                ("roadmap.html" in index_html and not paper_report)
                or all(term in index_html for term in ("paper_map.html", "paper_lens.html", "roadmap.html"))
            ),
            "Show a first-10-minutes path that links map, deep reading, and mastery checklist.",
        ),
        _experience_check(
            "paper_map_first_step",
            "Paper Map first step",
            (not paper_report)
            or (not roadmap.get("paper_map"))
            or ("paper_map.html" in index_html and "paper_map.html" in surfaces),
            "For paper reports, make Paper Map the first step from the start page.",
        ),
        _experience_check(
            "paper_lens_second_step",
            "Paper Lens second step",
            (not paper_report)
            or (not roadmap.get("paper_lens"))
            or ("paper_lens.html" in index_html and "paper_lens.html" in surfaces),
            "For paper reports, make Paper Lens the second step after the map.",
        ),
        _experience_check(
            "mastery_task_finish",
            "Mastery task finish step",
            bool(_list_at(roadmap, "study_tasks"))
            and _contains_any_text(combined, ("roadmap.html", "mastery", "验收")),
            "End the first learning loop with at least one visible mastery task.",
        ),
        _experience_check(
            "local_resource_available",
            "Local resource available",
            has_local_resource
            and _contains_any_text(combined, ("local_href", "Open local", "打开本地", "Local assets")),
            "Give the learner at least one local/openable resource in the first loop.",
        ),
        _experience_check(
            "failed_resource_recovery",
            "Failed resource recovery",
            (not has_failed_resource) or _contains_any_text(combined, ("retry", "failed", "重试", "失败")),
            "If any resource failed to download, show a visible retry or fallback cue.",
        ),
    ]
    warnings = [item for item in checks if item["status"] == "warn"]
    return {
        "status": "warn" if warnings else "pass",
        "summary": {
            "checks": len(checks),
            "warnings": len(warnings),
            "first_loop": ["paper_map.html", "paper_lens.html", "roadmap.html"] if paper_report else ["roadmap.html"],
        },
        "checks": checks,
    }


def _viewport_risks(root: Path, roadmap: dict[str, Any], surfaces: list[str], visual_audit: dict[str, Any]) -> dict[str, Any]:
    html = {name: _read_text(root / name) for name in surfaces}
    combined = "\n".join(html.values()).lower()
    paper_map_html = html.get("paper_map.html", "").lower()
    roadmap_html = html.get("roadmap.html", "").lower()
    checks = [
        _experience_check(
            "responsive_breakpoints",
            "Responsive breakpoint coverage",
            "@media" in combined and ("max-width" in combined or "min-width" in combined),
            "Add mobile breakpoints so desktop layouts collapse cleanly on narrow screens.",
        ),
        _experience_check(
            "long_text_wrap_budget",
            "Long text wrap budget",
            _all_core_pages_have_check(visual_audit, "wrap_safeguard") and _all_core_pages_have_check(visual_audit, "width_constraint"),
            "Keep overflow-wrap and width constraints on every report surface to protect long Chinese titles and English abstracts.",
        ),
        _experience_check(
            "paper_map_canvas_budget",
            "Paper Map canvas budget",
            not roadmap.get("paper_map")
            or (
                _contains_any_text(paper_map_html, ("react-flow", "data-paper-map-canvas"))
                and _contains_any_text(paper_map_html, ("flow-shell", "min-height", "height:"))
            ),
            "Give the Paper Map a stable canvas region with enough height for zooming, panning, and node dragging.",
        ),
        _experience_check(
            "resource_list_mobile_budget",
            "Resource list mobile budget",
            "<table" not in roadmap_html or "overflow-x" in roadmap_html or "resource-list" in roadmap_html,
            "Avoid wide resource tables as the primary mobile experience; use cards or horizontally protected containers.",
        ),
    ]
    warnings = [item for item in checks if item["status"] == "warn"]
    return {
        "status": "warn" if warnings else "pass",
        "summary": {
            "viewports": ["desktop-1280x720", "mobile-390x844"],
            "checks": len(checks),
            "warnings": len(warnings),
        },
        "checks": checks,
    }


def _visual_snapshot_matrix(root: Path, roadmap: dict[str, Any], surfaces: list[str], visual_audit: dict[str, Any]) -> dict[str, Any]:
    html = {name: _read_text(root / name) for name in surfaces}
    combined = "\n".join(html.values()).lower()
    index_html = html.get("index.html", "")
    paper_map_html = html.get("paper_map.html", "")
    roadmap_html = html.get("roadmap.html", "")
    resources = [item for item in _bundle_resources(roadmap) if isinstance(item, dict)]
    paper_map = roadmap.get("paper_map") if isinstance(roadmap.get("paper_map"), dict) else {}
    nodes = paper_map.get("nodes") if isinstance(paper_map.get("nodes"), list) else []
    long_text_stress = _long_text_stress(roadmap, html)
    dense_resources = len(resources) >= 10
    dense_map = len(nodes) >= 10
    stress_count = sum(1 for item in (long_text_stress, dense_resources, dense_map) if item)
    checks = [
        _experience_check(
            "long_text_resilience",
            "Long title and abstract resilience",
            (not long_text_stress)
            or (
                _all_core_pages_have_check(visual_audit, "wrap_safeguard")
                and _all_core_pages_have_check(visual_audit, "width_constraint")
                and "overflow-wrap" in combined
            ),
            "For long Chinese titles or English abstracts, keep wrapping and width constraints on every exported page.",
        ),
        _experience_check(
            "dense_resource_library_controls",
            "Dense resource library controls",
            (not dense_resources)
            or (
                _contains_any_text(roadmap_html, ("resource-list", "resource-row"))
                and _contains_any_text(roadmap_html, ("resource-filter", "resource-search", "filter", "筛选", "chips"))
                and ("<table" not in roadmap_html.lower() or "overflow-x" in roadmap_html.lower())
            ),
            "For large resource bundles, keep searchable/filterable card lists instead of unprotected wide tables.",
        ),
        _experience_check(
            "paper_map_canvas_density",
            "Paper Map dense canvas controls",
            (not dense_map)
            or (
                _contains_any_text(paper_map_html, ("react-flow", "data-paper-map-canvas"))
                and _contains_any_text(paper_map_html, ("controls", "minimap", "zoom", "pan", "拖拽", "缩放"))
                and _canvas_has_large_budget(paper_map_html)
            ),
            "For dense Paper Maps, keep pan/zoom controls, minimap/controls affordances, and enough canvas height.",
        ),
        _experience_check(
            "mobile_viewport_readability",
            "Mobile viewport readability",
            "@media" in combined
            and ("max-width" in combined or "min-width" in combined)
            and 'name="viewport"' in combined,
            "Keep viewport metadata and mobile breakpoints so the report remains readable on narrow screens.",
        ),
        _experience_check(
            "start_page_snapshot_path",
            "Start-page snapshot path",
            _contains_any_text(index_html, ("fresh-user-flow-panel", "data-fresh-user-flow", "10-minute quickstart", "10 分钟入门")),
            "Keep a visible first-10-minutes path on the start page in screenshot-style checks.",
        ),
    ]
    warnings = [item for item in checks if item["status"] == "warn"]
    return {
        "status": "warn" if warnings else "pass",
        "summary": {
            "mode": "static-snapshot-proxy",
            "viewports": ["desktop-1280x720", "mobile-390x844"],
            "stress_scenarios": max(1, stress_count),
            "checks": len(checks),
            "warnings": len(warnings),
        },
        "checks": checks,
    }


def _experience_check(id_: str, label: str, passed: bool, recommendation: str) -> dict[str, str]:
    return {
        "id": id_,
        "label": label,
        "status": "pass" if passed else "warn",
        "recommendation": recommendation,
    }


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _contains_any_text(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _all_core_pages_have_check(visual_audit: dict[str, Any], check_name: str) -> bool:
    checks = visual_audit.get("checks", [])
    if not isinstance(checks, list):
        return False
    core_checks = [
        item
        for item in checks
        if isinstance(item, dict) and item.get("check") == check_name and str(item.get("file") or "").endswith(".html")
    ]
    return bool(core_checks) and all(item.get("status") == "pass" for item in core_checks)


def _local_resource_ratio(roadmap: dict[str, Any]) -> float:
    resources = [item for item in _bundle_resources(roadmap) if isinstance(item, dict)]
    if not resources:
        return 0.0
    local_count = sum(1 for item in resources if item.get("local_href") or str(item.get("status") or "") in {"downloaded", "copied", "snapshotted", "generated"})
    return local_count / len(resources)


def _paper_lens_contextual_explanations(roadmap: dict[str, Any], html: dict[str, str]) -> bool:
    lens = roadmap.get("paper_lens") if isinstance(roadmap.get("paper_lens"), dict) else {}
    segments = [item for item in lens.get("segments", []) if isinstance(item, dict)]
    explanations = [item for item in lens.get("inline_explanations", []) if isinstance(item, dict)]
    if not segments or not explanations:
        return False
    explanatory_fields = ("plain_meaning", "why_it_matters", "method_note", "related_map_nodes", "evidence_refs")
    has_specific_explanation = any(any(item.get(field) for field in explanatory_fields) for item in explanations)
    return has_specific_explanation and _contains_any_text(
        html.get("paper_lens.html", ""),
        ("paragraph", "段落", "Explanation support", "解释支撑度"),
    )


def _structured_quick_review_surface(roadmap: dict[str, Any], html: dict[str, str]) -> bool:
    if not roadmap.get("paper_map") or not roadmap.get("paper_lens"):
        return False
    has_map_structure = _contains_any_text(
        html.get("paper_map.html", ""),
        ("Core Chain", "速览主链", "Download presentation notes", "presentation.md"),
    )
    has_lens_structure = _paper_lens_contextual_explanations(roadmap, html)
    return has_map_structure and has_lens_structure and _portable_study_output_count(roadmap, html) >= 2


def _resource_library_marker(roadmap: dict[str, Any], html: str, terms: tuple[str, ...]) -> bool:
    return bool(_all_resource_entries(roadmap)) and _contains_any_text(html, terms)


def _resource_library_has_evidence(roadmap: dict[str, Any]) -> bool:
    return any(_resource_evidence_chunks(item) for item in _all_resource_entries(roadmap) if isinstance(item, dict))


def _resource_evidence_review_link_count(roadmap: dict[str, Any], html: dict[str, str]) -> int:
    roadmap_html = html.get("roadmap.html", "")
    if not _contains_any_text(roadmap_html, ("resource-evidence-link", "查看证据", "Review evidence")):
        return 0
    resources = [item for item in _all_resource_entries(roadmap) if isinstance(item, dict)]
    return sum(1 for item in resources if _resource_has_reviewable_evidence(item))


def _all_resource_entries(roadmap: dict[str, Any]) -> list[Any]:
    resources: list[Any] = []
    resources.extend(_list_at(roadmap, "study_bundle", "resources"))
    resources.extend(_list_at(roadmap, "resource_library"))
    return resources


def _resource_has_reviewable_evidence(resource: dict[str, Any]) -> bool:
    resource_href = any(resource.get(key) for key in ("local_href", "href", "url"))
    for chunk in _resource_evidence_chunks(resource):
        if not isinstance(chunk, dict):
            continue
        snippet = str(chunk.get("snippet") or chunk.get("text") or "").strip()
        if not snippet:
            continue
        if any(chunk.get(key) for key in ("detail_anchor", "local_href", "href", "url")) or resource_href:
            return True
    return False


def _resource_evidence_chunks(resource: dict[str, Any]) -> list[Any]:
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    rag = metadata.get("rag") if isinstance(metadata.get("rag"), dict) else {}
    chunks: list[Any] = []
    for key in ("evidence_chunks", "top_chunks", "chunks"):
        value = rag.get(key) or metadata.get(key)
        if isinstance(value, list):
            chunks.extend(value)
    return chunks


def _long_text_stress(roadmap: dict[str, Any], html: dict[str, str]) -> bool:
    candidates: list[str] = [
        str(roadmap.get("title") or ""),
        str((roadmap.get("profile") or {}).get("goal") or "") if isinstance(roadmap.get("profile"), dict) else "",
    ]
    candidates.extend(str(item.get("title") or "") for item in _bundle_resources(roadmap) if isinstance(item, dict))
    lens = roadmap.get("paper_lens") if isinstance(roadmap.get("paper_lens"), dict) else {}
    segments = lens.get("segments") if isinstance(lens.get("segments"), list) else []
    candidates.extend(str(item.get("original_text") or "") for item in segments if isinstance(item, dict))
    if any(len(text) >= 120 or _long_unbroken_token(text) >= 44 for text in candidates):
        return True
    visible = re.sub(r"(?is)<script.*?</script>|<style.*?</style>|<[^>]+>", " ", "\n".join(html.values()))
    return bool(re.search(r"[A-Za-z0-9_\-]{48,}", visible))


def _long_unbroken_token(text: str) -> int:
    tokens = re.findall(r"[A-Za-z0-9_\-/.:]{2,}", text)
    return max((len(token) for token in tokens), default=0)


def _canvas_has_large_budget(html: str) -> bool:
    lowered = html.lower()
    if any(term in lowered for term in ("min-height:560", "min-height: 560", "min-height:600", "min-height: 600", "min-height:640", "min-height: 640")):
        return True
    heights = [int(match.group(1)) for match in re.finditer(r"(?:min-)?height\s*:\s*(\d+)px", lowered)]
    return any(height >= 520 for height in heights)


def _needs_route_recovery(roadmap: dict[str, Any]) -> bool:
    return (
        _explicit_empty_list(roadmap, "phases")
        or _explicit_empty_list(roadmap, "study_tasks")
        or _explicit_empty_bundle_resources(roadmap)
    )


def _explicit_empty_list(value: dict[str, Any], key: str) -> bool:
    return key in value and isinstance(value.get(key), list) and not value.get(key)


def _explicit_empty_bundle_resources(roadmap: dict[str, Any]) -> bool:
    bundle = roadmap.get("study_bundle")
    if isinstance(bundle, dict) and "resources" in bundle:
        resources = bundle.get("resources")
        return isinstance(resources, list) and not resources
    if "resource_library" in roadmap:
        resources = roadmap.get("resource_library")
        return isinstance(resources, list) and not resources
    return False


def _interactive_pages_have_static_fallback(html: dict[str, str]) -> bool:
    interactive_pages = [
        content
        for name, content in html.items()
        if name in {"paper_map.html", "paper_lens.html", "roadmap.html"}
        and _contains_any_text(content, ("fields-study-flow-data", "react-flow", 'id="root"', "data-report-kind"))
    ]
    return not interactive_pages or all("data-report-static-fallback" in content for content in interactive_pages)


def _target_kind(roadmap: dict[str, Any]) -> str:
    profile = roadmap.get("profile") if isinstance(roadmap.get("profile"), dict) else {}
    return str(profile.get("target_kind") or roadmap.get("target_kind") or "").lower()


def _is_field_or_course_target(roadmap: dict[str, Any]) -> bool:
    return _target_kind(roadmap) in {"field", "course"}


def _competitive_positioning(roadmap: dict[str, Any]) -> dict[str, Any]:
    if _is_field_or_course_target(roadmap):
        return {
            "product_wedge": "field_course_mastery_path",
            "differentiates_from": [
                "generic_roadmap_only",
                "static_link_collection",
                "literature_search_only",
                "chat_with_pdf_only",
            ],
            "rationale": "For field and course goals, the report is strongest when it turns prerequisites, concepts, resources, projects, and assessments into a measurable local-first mastery path.",
        }
    return {
        "product_wedge": "paper_centered_mastery",
        "differentiates_from": [
            "literature_search_only",
            "chat_with_pdf_only",
            "generic_roadmap_only",
            "static_link_collection",
        ],
        "rationale": "The report is strongest when it turns a target paper into a visual logic map, paragraph explanations, local resources, and mastery evidence.",
    }


def _onboarding_dimension(roadmap: dict[str, Any], surfaces: list[str], visual_audit: dict[str, Any]) -> dict[str, Any]:
    score = 0
    evidence: list[str] = []
    if "index.html" in surfaces:
        score += 30
        evidence.append("start page exported")
    first_action = _recommended_first_action(roadmap, surfaces)
    if first_action.get("href"):
        score += 25
        evidence.append(f"recommended first action: {first_action['href']}")
    if len(surfaces) >= 3:
        score += 15
        evidence.append("multiple report surfaces are discoverable")
    if _check_passed(visual_audit, "index.html", "start_entry"):
        score += 15
        evidence.append("start entry marker present")
    if _check_passed(visual_audit, "index.html", "bring_your_own_paper"):
        score += 15
        evidence.append("bring-your-own-paper cue present")
    return _dimension("onboarding", "Onboarding clarity", score, evidence, "Add a start page, a recommended first action, and bring-your-own-paper commands.")


def _visual_polish_dimension(visual_audit: dict[str, Any]) -> dict[str, Any]:
    summary = visual_audit.get("summary", {}) if isinstance(visual_audit.get("summary"), dict) else {}
    checks = int(summary.get("checks") or 0)
    failed = int(summary.get("failed_checks") or 0)
    if checks <= 0:
        score = 0
    else:
        score = round(100 * max(0, checks - failed) / checks)
    evidence = [f"{checks - failed}/{checks} visual checks passed"] if checks else []
    return _dimension("visual_polish", "Visual polish and layout safety", score, evidence, "Fix viewport, wrapping, width constraints, font stack, and report-specific affordances.")


def _learning_depth_dimension(roadmap: dict[str, Any]) -> dict[str, Any]:
    if _is_field_or_course_target(roadmap):
        return _field_course_learning_depth_dimension(roadmap)
    score = 0
    evidence: list[str] = []
    if roadmap.get("paper_map"):
        score += 25
        evidence.append("paper map available")
    if roadmap.get("paper_lens"):
        score += 25
        evidence.append("paper lens available")
    kg_summary = _dict_at(roadmap, "knowledge_graph", "summary")
    if int(kg_summary.get("evidence_backed_edges") or 0) > 0 or int(kg_summary.get("edges") or 0) >= 8:
        score += 20
        evidence.append("knowledge graph has evidence-backed structure")
    if len(_list_at(roadmap, "study_tasks")) >= 3:
        score += 30
        evidence.append("study tasks cover multiple mastery moves")
    return _dimension("learning_depth", "Learning depth", score, evidence, "Add Paper Map, Paper Lens, knowledge graph evidence, and explain/derive/reproduce/critique tasks.")


def _field_course_learning_depth_dimension(roadmap: dict[str, Any]) -> dict[str, Any]:
    score = 0
    evidence: list[str] = []
    phases = _list_at(roadmap, "phases")
    if len(phases) >= 3:
        score += 25
        evidence.append(f"{len(phases)} learning phases")
    kg_summary = _dict_at(roadmap, "knowledge_graph", "summary")
    if int(kg_summary.get("evidence_backed_edges") or 0) > 0 or int(kg_summary.get("edges") or 0) >= 8:
        score += 25
        evidence.append("knowledge graph connects concepts, resources, tasks, and assessments")
    if len(_bundle_resources(roadmap)) >= 3:
        score += 20
        evidence.append("resource set supports the route")
    if len(_list_at(roadmap, "study_tasks")) >= 3:
        score += 30
        evidence.append("study tasks cover multiple mastery moves")
    return _dimension("learning_depth", "Learning depth", score, evidence, "Add phases, knowledge graph coverage, local resources, and explain/derive/reproduce/critique tasks.")


def _plain_explanation_dimension(roadmap: dict[str, Any]) -> dict[str, Any]:
    if _is_field_or_course_target(roadmap):
        return _field_course_plain_explanation_dimension(roadmap)
    lens = roadmap.get("paper_lens") if isinstance(roadmap.get("paper_lens"), dict) else {}
    explanations = lens.get("inline_explanations") if isinstance(lens, dict) else []
    if explanations is None:
        explanations = []
    explanations = [item for item in explanations if isinstance(item, dict)]
    segments = lens.get("segments") if isinstance(lens, dict) else []
    if segments is None:
        segments = []
    score = 0
    evidence: list[str] = []
    if explanations:
        score += 35
        evidence.append(f"{len(explanations)} paragraph explanations")
    if segments:
        score += 20
        evidence.append(f"{len(segments)} source segments")
    plain_notes = [str(item.get("plain_meaning") or "") for item in explanations]
    if len(set(plain_notes)) >= min(2, len(plain_notes)):
        score += 20
        evidence.append("explanations are not all identical")
    if any(len(note) >= 24 for note in plain_notes):
        score += 15
        evidence.append("plain explanations contain enough detail")
    confidence_values = {str(item.get("confidence")) for item in explanations if item.get("confidence") is not None}
    if len(confidence_values) >= 2:
        score += 10
        evidence.append("confidence values vary")
    return _dimension("plain_explanation", "Plain-language explanation quality", score, evidence, "Use paragraph-level, non-repetitive explanations tied to the paper logic.")


def _field_course_plain_explanation_dimension(roadmap: dict[str, Any]) -> dict[str, Any]:
    phases = [item for item in _list_at(roadmap, "phases") if isinstance(item, dict)]
    phase_notes = [str(item.get("objective") or item.get("name") or "") for item in phases]
    key_points = [str(item) for item in _list_at(roadmap, "learning_key_points")]
    focus_areas = [str(item) for item in _list_at(roadmap, "focus_areas")]
    notes = [item for item in phase_notes + key_points + focus_areas if item]
    score = 0
    evidence: list[str] = []
    if len(phase_notes) >= 3:
        score += 35
        evidence.append(f"{len(phase_notes)} phase objectives")
    if len(key_points) >= 3:
        score += 25
        evidence.append(f"{len(key_points)} learning key points")
    if len(focus_areas) >= 2:
        score += 20
        evidence.append(f"{len(focus_areas)} focus areas")
    if len(set(notes)) >= min(3, len(notes)):
        score += 10
        evidence.append("route explanations are not all identical")
    if any(len(note) >= 24 for note in notes):
        score += 10
        evidence.append("plain route explanations contain enough detail")
    return _dimension("plain_explanation", "Plain-language explanation quality", score, evidence, "Use clear phase objectives, key points, and focus areas tied to the field/course goal.")


def _resource_completeness_dimension(roadmap: dict[str, Any]) -> dict[str, Any]:
    resources = _bundle_resources(roadmap)
    count = len(resources)
    local_count = sum(1 for item in resources if isinstance(item, dict) and item.get("local_href"))
    materialized_count = sum(1 for item in resources if isinstance(item, dict) and str(item.get("status") or "") in {"downloaded", "copied", "snapshotted", "generated"})
    score = 0
    evidence: list[str] = []
    if count:
        score += min(30, count * 10)
        evidence.append(f"{count} resources listed")
    if count and local_count:
        score += round(40 * local_count / count)
        evidence.append(f"{local_count}/{count} resources have local links")
    if count and materialized_count:
        score += round(30 * materialized_count / count)
        evidence.append(f"{materialized_count}/{count} resources are materialized")
    return _dimension("resource_completeness", "Resource completeness", score, evidence, "Prefer downloaded, copied, snapshotted, or generated local resources over link-only lists.")


def _actionability_dimension(roadmap: dict[str, Any]) -> dict[str, Any]:
    tasks = _list_at(roadmap, "study_tasks")
    task_types = {str(item.get("type") or "") for item in tasks if isinstance(item, dict)}
    required = {"explain", "derive", "reproduce", "critique"}
    evidence_items = _list_at(roadmap, "mastery_evidence", "required_evidence")
    score = 0
    evidence: list[str] = []
    if tasks:
        score += min(30, len(tasks) * 8)
        evidence.append(f"{len(tasks)} study tasks")
    if task_types:
        coverage = len(task_types & required) / len(required)
        score += round(45 * coverage)
        evidence.append("mastery task coverage: " + ", ".join(sorted(task_types & required)))
    if evidence_items:
        score += 25
        evidence.append(f"{len(evidence_items)} required evidence items")
    return _dimension("actionability", "Actionability and mastery evidence", score, evidence, "Add concrete evidence tasks for explain, derive, reproduce, and critique.")


def _dimension(id_: str, label: str, score: int | float, evidence: list[str], improvement: str) -> dict[str, Any]:
    score_int = max(0, min(100, round(float(score))))
    status = "strong" if score_int >= 80 else "adequate" if score_int >= 60 else "weak"
    return {
        "id": id_,
        "label": label,
        "score": score_int,
        "status": status,
        "evidence": evidence,
        "improvement": improvement,
    }


def _market_next_best_actions(
    dimensions: list[dict[str, Any]],
    status: str,
    competitive_benchmark: dict[str, Any] | None = None,
    fresh_user_flow: dict[str, Any] | None = None,
    visual_snapshot_matrix: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    weak = sorted((item for item in dimensions if item["score"] < 80), key=lambda item: item["score"])
    if weak:
        return [
            {"dimension": item["id"], "action": str(item["improvement"])}
            for item in weak[:3]
        ]
    fresh_warnings = [
        item
        for item in (fresh_user_flow or {}).get("checks", [])
        if isinstance(item, dict) and item.get("status") == "warn"
    ]
    if fresh_warnings:
        return [
            {"dimension": str(item["id"]), "action": str(item["recommendation"])}
            for item in fresh_warnings[:3]
        ]
    snapshot_warnings = [
        item
        for item in (visual_snapshot_matrix or {}).get("checks", [])
        if isinstance(item, dict) and item.get("status") == "warn"
    ]
    if snapshot_warnings:
        return [
            {"dimension": str(item["id"]), "action": str(item["recommendation"])}
            for item in snapshot_warnings[:3]
        ]
    benchmark_warnings = [
        item
        for item in (competitive_benchmark or {}).get("checks", [])
        if isinstance(item, dict) and item.get("status") == "warn"
    ]
    if benchmark_warnings:
        return [
            {"dimension": str(item["id"]), "action": str(item["recommendation"])}
            for item in benchmark_warnings[:3]
        ]
    if status == "market_ready":
        return [
            {"dimension": "visual_polish", "action": "Optionally run browser-backed screenshot capture to validate the static visual snapshot matrix against real rendered pixels."},
            {"dimension": "onboarding", "action": "Time a fresh-user run to measure how quickly a learner reaches the first mastery task."},
        ]
    return [{"dimension": "overall", "action": "Inspect the weakest readiness dimensions and regenerate the report after fixes."}]


def _check_passed(visual_audit: dict[str, Any], file_name: str, check_name: str) -> bool:
    checks = visual_audit.get("checks", [])
    if not isinstance(checks, list):
        return False
    return any(
        isinstance(item, dict)
        and item.get("file") == file_name
        and item.get("check") == check_name
        and item.get("status") == "pass"
        for item in checks
    )


def _dict_at(value: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _list_at(value: dict[str, Any], *keys: str) -> list[Any]:
    current: Any = value
    for key in keys:
        if not isinstance(current, dict):
            return []
        current = current.get(key)
    return current if isinstance(current, list) else []


def _bundle_resources(roadmap: dict[str, Any]) -> list[Any]:
    resources = _list_at(roadmap, "study_bundle", "resources")
    if resources:
        return resources
    return _list_at(roadmap, "resource_library")


def _audit_html_file(file_name: str, html: str) -> list[dict[str, str]]:
    lower = html.lower()
    checks = [
        _check(
            file_name,
            "private_path_redaction",
            "fail" if PRIVATE_PATH_RE.search(html) else "pass",
            "No private absolute local paths are present.",
        ),
        _check(
            file_name,
            "responsive_viewport",
            "pass" if 'name="viewport"' in lower or "name='viewport'" in lower else "fail",
            "HTML includes a mobile viewport meta tag.",
        ),
        _check(
            file_name,
            "wrap_safeguard",
            "pass" if "overflow-wrap" in lower or "word-break" in lower else "fail",
            "Long Chinese, English, and command text has wrapping safeguards.",
        ),
        _check(
            file_name,
            "width_constraint",
            "pass" if "max-width" in lower or "width: min" in lower or "minmax(" in lower else "fail",
            "Layout includes width constraints instead of unconstrained text blocks.",
        ),
        _check(
            file_name,
            "font_stack",
            "pass" if "font-family" in lower else "fail",
            "HTML includes an explicit font stack.",
        ),
        _check(
            file_name,
            "encoding_integrity",
            "fail" if VISIBLE_MOJIBAKE_RE.search(_visible_html_for_encoding_check(html)) else "pass",
            "Visible report text does not contain replacement characters or common mojibake fragments.",
        ),
        _check(
            file_name,
            "visible_decorative_ellipsis",
            "fail" if VISIBLE_DECORATIVE_ELLIPSIS_RE.search(_visible_html_for_text_quality_check(html)) else "pass",
            "Visible report text does not use decorative clipping ellipses; long text should wrap or be expandable.",
        ),
        _check(
            file_name,
            "payload_decorative_ellipsis",
            "fail" if PAYLOAD_DECORATIVE_ELLIPSIS_RE.search(_react_payload_for_text_quality_check(html)) else "pass",
            "Embedded report data does not contain decorative clipping ellipses that React would render.",
        ),
    ]
    checks.extend(_file_specific_checks(file_name, html))
    return checks


def _visible_html_for_encoding_check(html: str) -> str:
    return re.sub(r"(?is)<script.*?</script>|<style.*?</style>", "", html)


def _visible_html_for_text_quality_check(html: str) -> str:
    visible = _visible_html_for_encoding_check(html)
    return re.sub(r"(?is)<[^>]+>", " ", visible)


def _react_payload_for_text_quality_check(html: str) -> str:
    return "\n".join(match.group(1) for match in FIELDS_STUDY_FLOW_DATA_RE.finditer(html))


def _file_specific_checks(file_name: str, html: str) -> list[dict[str, str]]:
    if file_name == "index.html":
        return [
            _contains_any(file_name, "start_entry", html, ("从这里开始", "Start Here")),
            _contains_any(file_name, "quickstart_path", html, ("10 分钟入门", "10-minute quickstart")),
            _contains_any(file_name, "bring_your_own_paper", html, ("换成自己的论文", "Bring Your Own Paper")),
            _contains_any(file_name, "market_value_panel", html, ("data-market-value-panel", "Why this is more than a PDF summarizer", "为什么它不只是 PDF 总结器")),
        ]
    if file_name == "paper_map.html":
        return [
            _contains_any(file_name, "paper_map_density_control", html, ("阅读密度", "Reading Density")),
            _contains_any(file_name, "paper_map_core_mode", html, ("速览主链", "Core Chain")),
            _contains_any(file_name, "paper_map_explore_mode", html, ("完整探索", "Full Exploration")),
        ]
    if file_name == "paper_lens.html":
        return [
            _contains_any(file_name, "paper_lens_paragraph_reading", html, ("段落精读", "paragraph")),
            _contains_any(file_name, "paper_lens_evidence", html, ("证据", "evidence")),
        ]
    if file_name == "roadmap.html":
        return [
            _contains_any(file_name, "roadmap_console", html, ("学习中控台", "learning console")),
            _contains_any(file_name, "roadmap_mastery_checklist", html, ("掌握验收", "mastery")),
        ]
    return []


def _contains_any(file_name: str, check_name: str, html: str, terms: tuple[str, ...]) -> dict[str, str]:
    return _check(
        file_name,
        check_name,
        "pass" if any(term in html for term in terms) else "fail",
        f"Expected a localized or English report affordance marker for {check_name}.",
    )


def _check(file_name: str, check_name: str, status: str, message: str) -> dict[str, str]:
    return {"file": file_name, "check": check_name, "status": status, "message": message}
