from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from urllib.parse import urlparse

from fields_study_flow.language import normalize_output_language, normalize_resource_language_preference
from fields_study_flow.live_search import search_live_resources
from fields_study_flow.local_resources import analyze_local_resources
from fields_study_flow.mcp_tools import ingestUrl
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.offline_catalog import offline_resources_for_goal
from fields_study_flow.paper_metadata import paper_metadata_to_resource, resolve_paper_metadata
from fields_study_flow.rag import answer_from_bundle, apply_rag_to_resources, public_rag_evidence, write_bundle_rag_index
from fields_study_flow.ranking import rank_resources
from fields_study_flow.resource_bundle import attach_study_bundle, bundle_study_resources
from fields_study_flow.roadmap import build_roadmap, write_outputs
from fields_study_flow.sources import SourceRegistry
from fields_study_flow.visual_audit import (
    audit_report_directory,
    capture_browser_snapshots,
    compare_browser_snapshot_baseline,
    evaluate_market_sample_matrix,
    evaluate_fresh_user_timing,
    probe_browser_interactions,
    summarize_fresh_user_worksheets,
    summarize_fresh_user_backlogs,
    write_report_audit,
    write_fresh_user_backlog,
    write_fresh_user_trend_report,
    write_fresh_user_worksheet,
    write_release_readiness_history,
    write_release_readiness_report,
)


PLANNER_PRESETS: dict[str, dict[str, str]] = {
    "fastest": {"route_depth": "fastest", "learning_style": "practical"},
    "balanced": {"route_depth": "balanced", "learning_style": "practical"},
    "complete": {"route_depth": "complete", "learning_style": "theory"},
    "paper-fastest": {"target_kind": "paper", "route_depth": "fastest", "learning_style": "practical"},
    "paper-deep": {"target_kind": "paper", "route_depth": "complete", "learning_style": "theory"},
    "field-project": {"target_kind": "field", "route_depth": "balanced", "learning_style": "practical"},
    "course-complete": {"target_kind": "course", "route_depth": "complete", "learning_style": "theory"},
}


def _positive_minutes(value: str) -> float:
    try:
        minutes = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("minutes must be a positive finite number") from exc
    if not math.isfinite(minutes) or minutes <= 0:
        raise argparse.ArgumentTypeError("minutes must be a positive finite number")
    return minutes


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "roadmap":
        return _roadmap(args)
    if args.command == "paper":
        return _paper(args)
    if args.command == "ingest-url":
        return _ingest_url(args)
    if args.command == "analyze-local":
        return _analyze_local(args)
    if args.command == "discover-sources":
        return _discover_sources(args)
    if args.command == "export":
        return _export(args)
    if args.command == "ask":
        return _ask(args)
    if args.command == "demo":
        return _demo(args)
    if args.command == "audit-report":
        return _audit_report(args)
    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fields-study-flow", description="Generate AI/CS learning roadmaps from multi-source resources.")
    subparsers = parser.add_subparsers(dest="command")

    roadmap = subparsers.add_parser("roadmap", help="Generate a learning roadmap.")
    roadmap.add_argument("--goal")
    roadmap.add_argument("--sources", default="auto")
    roadmap.add_argument("--output-language", default="zh-CN")
    roadmap.add_argument("--resource-language", default="balanced")
    roadmap.add_argument("--known-topic", action="append", default=[])
    roadmap.add_argument("--level", action="append", default=[], help="Domain level as domain=beginner|familiar|advanced")
    roadmap.add_argument("--weekly-hours", type=int)
    roadmap.add_argument("--target-date")
    _add_unified_planner_args(roadmap)
    roadmap.add_argument("--local-resource", action="append", default=[], help="Explicit local file or folder to analyze as a shortcut candidate.")
    roadmap.add_argument("--output-dir", default="fields-study-flow-output")
    roadmap.add_argument("--resource-dir", help="Copy/download the full study resource library into this private local directory.")
    roadmap.add_argument("--bundle-scope", choices=["selected", "all"], default="all", help="Download/copy only selected route resources or all candidate resources.")
    roadmap.add_argument("--download-retries", type=int, default=2, help="Retry each downloadable resource this many times after the first failed attempt.")
    roadmap.add_argument("--quiet-downloads", action="store_true", help="Do not print per-resource bundle progress.")
    roadmap.add_argument("--no-paper-lens", action="store_true", help="Do not generate the standalone paper_lens.html reader even when a target paper is present.")
    roadmap.add_argument("--paper-lens-language", choices=["auto", "zh-CN", "en", "bilingual"], default="auto", help="Language for generated Paper Lens explanations.")
    roadmap.add_argument("--paper-lens-density", choices=["key", "section", "dense"], default="dense", help="How many target-paper segments to explain in paper_lens.html.")
    roadmap.add_argument("--paper-lens-granularity", choices=["paragraph", "sentence"], default="paragraph", help="Whether Paper Lens explains paragraph blocks or individual sentence units.")
    roadmap.add_argument("--no-paper-map", action="store_true", help="Do not generate the standalone paper_map.html logic map even when a target paper is present.")
    roadmap.add_argument("--paper-map-language", choices=["auto", "zh-CN", "en", "bilingual"], default="auto", help="Language for generated Paper Map explanations.")
    roadmap.add_argument("--paper-map-depth", choices=["quick", "standard", "complete"], default="standard", help="How many supporting branches to include in paper_map.html.")
    roadmap.add_argument("--paper-map-layout", choices=["xmind-flow"], default="xmind-flow", help="Graphical layout style for paper_map.html.")
    roadmap.add_argument("--paper-map-provider", choices=["local", "auto", "llm"], default="auto", help="Extraction provider policy for Paper Map generation.")
    roadmap.add_argument("--interactive", action="store_true", help="Ask for language, storage, and learning preferences before generating the plan.")
    roadmap.add_argument("--offline", action="store_true", help="Use the bundled deterministic resource catalog and disable live search.")
    roadmap.add_argument("--no-live-search", action="store_true", help="Disable default live resource discovery.")
    roadmap.add_argument("--rag", choices=["off", "light", "auto", "embedding"], default="auto", help="Evidence retrieval mode for ranking and reports.")

    paper = subparsers.add_parser("paper", help="Generate a paper deep-reading roadmap.")
    paper.add_argument("--url")
    paper.add_argument("--goal", default="fully understand, derive, and reproduce the paper")
    paper.add_argument("--with-videos", action="store_true")
    paper.add_argument("--output-language", default="zh-CN")
    paper.add_argument("--resource-language", default="balanced")
    _add_unified_planner_args(paper, default_target_kind="paper")
    paper.add_argument("--local-resource", action="append", default=[], help="Explicit local file or folder to analyze as a shortcut candidate.")
    paper.add_argument("--no-live-search", action="store_true", help="Disable default live resource discovery.")
    paper.add_argument("--output-dir", default="fields-study-flow-paper-output")
    paper.add_argument("--resource-dir", help="Copy/download the full study resource library into this private local directory.")
    paper.add_argument("--bundle-scope", choices=["selected", "all"], default="all", help="Download/copy only selected route resources or all candidate resources.")
    paper.add_argument("--download-retries", type=int, default=2, help="Retry each downloadable resource this many times after the first failed attempt.")
    paper.add_argument("--quiet-downloads", action="store_true", help="Do not print per-resource bundle progress.")
    paper.add_argument("--no-paper-lens", action="store_true", help="Do not generate the standalone paper_lens.html reader.")
    paper.add_argument("--paper-lens-language", choices=["auto", "zh-CN", "en", "bilingual"], default="auto", help="Language for generated Paper Lens explanations.")
    paper.add_argument("--paper-lens-density", choices=["key", "section", "dense"], default="dense", help="How many target-paper segments to explain in paper_lens.html.")
    paper.add_argument("--paper-lens-granularity", choices=["paragraph", "sentence"], default="paragraph", help="Whether Paper Lens explains paragraph blocks or individual sentence units.")
    paper.add_argument("--no-paper-map", action="store_true", help="Do not generate the standalone paper_map.html logic map.")
    paper.add_argument("--paper-map-language", choices=["auto", "zh-CN", "en", "bilingual"], default="auto", help="Language for generated Paper Map explanations.")
    paper.add_argument("--paper-map-depth", choices=["quick", "standard", "complete"], default="standard", help="How many supporting branches to include in paper_map.html.")
    paper.add_argument("--paper-map-layout", choices=["xmind-flow"], default="xmind-flow", help="Graphical layout style for paper_map.html.")
    paper.add_argument("--paper-map-provider", choices=["local", "auto", "llm"], default="auto", help="Extraction provider policy for Paper Map generation.")
    paper.add_argument("--interactive", action="store_true", help="Ask for language, storage, and learning preferences before generating the plan.")
    paper.add_argument("--rag", choices=["off", "light", "auto", "embedding"], default="auto", help="Evidence retrieval mode for ranking and reports.")

    ingest = subparsers.add_parser("ingest-url", help="Parse a user-provided resource URL at metadata level.")
    ingest.add_argument("url")
    ingest.add_argument("--source-hint")

    local = subparsers.add_parser("analyze-local", help="Analyze explicit local files/folders as shortest-path learning resources.")
    local.add_argument("--goal", required=True)
    local.add_argument("--path", action="append", required=True, help="Local file or folder path. Repeat to add more.")
    local.add_argument("--resource-language", default="balanced")
    local.add_argument("--max-files", type=int, default=30)

    discover = subparsers.add_parser("discover-sources", help="List source adapters for a goal and language policy.")
    discover.add_argument("--goal", required=True)
    discover.add_argument("--language", default="balanced")
    discover.add_argument("--source-policy", default="open", choices=["open", "all"])

    export = subparsers.add_parser("export", help="Export an existing roadmap JSON.")
    export.add_argument("--input", default="fields-study-flow-output/roadmap.json")
    export.add_argument("--format", choices=["markdown", "json", "svg", "html", "anki", "all"], default="json")
    export.add_argument("--output-dir", default="fields-study-flow-export")

    ask = subparsers.add_parser("ask", help="Answer a question from a generated local study bundle.")
    ask.add_argument("--roadmap", required=True, help="Path to a generated roadmap.json.")
    ask.add_argument("--question", required=True)
    ask.add_argument("--resource-dir", help="Directory containing the downloaded/copied study bundle.")
    ask.add_argument("--limit", type=int, default=5)

    demo = subparsers.add_parser("demo", help="Generate a zero-setup sample report for first-time evaluation.")
    demo.add_argument("--sample", choices=["transformer-paper", "diffusion-paper-set", "diffusion-field-course", "all-market"], default="transformer-paper")
    demo.add_argument("--output-language", choices=["zh-CN", "en", "bilingual"], default="zh-CN")
    demo.add_argument("--output-dir", default="fields-study-flow-demo")
    demo.add_argument("--market-check", action="store_true", help="After generating the demo, write a market-readiness audit summary into the demo folder.")
    demo.add_argument("--market-fresh-user-minutes", type=_positive_minutes, help="Measured minutes for a fresh learner to reach the first mastery task in the demo market check.")
    demo.add_argument("--market-check-screenshots", action="store_true", help="Include optional browser screenshots in --market-check when Playwright is available.")
    demo.add_argument("--market-check-interactions", action="store_true", help="Include optional browser interaction probes in --market-check when Playwright is available.")

    audit = subparsers.add_parser("audit-report", help="Audit exported HTML reports for visual and privacy risks.")
    audit.add_argument("--report-dir", default="fields-study-flow-output")
    audit.add_argument("--capture-screenshots", action="store_true", help="Optionally capture desktop/mobile screenshots when Playwright is available.")
    audit.add_argument("--probe-interactions", action="store_true", help="Optionally smoke-test exported report clicks, filters, and Paper Map canvas interactions when Playwright is available.")
    audit.add_argument("--screenshot-dir", help="Directory for optional audit screenshots; defaults to REPORT_DIR/visual-snapshots.")
    audit.add_argument("--snapshot-baseline", help="Compare browser screenshot metadata against a saved visual-snapshots/manifest.json baseline.")
    audit.add_argument("--fresh-user-minutes", type=_positive_minutes, help="Measured minutes for a fresh learner to reach the first mastery task.")
    audit.add_argument("--fresh-user-target-minutes", type=_positive_minutes, default=10.0, help="Maximum acceptable fresh-user time-to-first-mastery-task. Default: 10.")
    audit.add_argument("--write-fresh-user-worksheet", action="store_true", help="Write a manual first-run usability worksheet into the report directory.")
    audit.add_argument("--fresh-user-worksheet", help="Optional output path for the first-run usability worksheet.")
    audit.add_argument("--fresh-user-worksheet-input", action="append", default=[], help="Completed fresh-user worksheet to aggregate into a ranked blocker backlog. Repeat to add more.")
    audit.add_argument("--write-fresh-user-backlog", action="store_true", help="Write a ranked fresh-user blocker backlog from worksheet inputs.")
    audit.add_argument("--fresh-user-backlog", help="Optional output path for the ranked fresh-user blocker backlog.")
    audit.add_argument("--fresh-user-backlog-input", action="append", default=[], help="Ranked fresh-user backlog to aggregate into a cross-report trend report. Repeat to add more.")
    audit.add_argument("--write-fresh-user-trend-report", action="store_true", help="Write a cross-report fresh-user trend report from backlog inputs.")
    audit.add_argument("--fresh-user-trend-report", help="Optional output path for the cross-report fresh-user trend report.")
    audit.add_argument("--write-release-readiness", action="store_true", help="Write a human-readable release-readiness dashboard for market-facing report QA.")
    audit.add_argument("--release-readiness-report", help="Optional output path for the release-readiness dashboard.")
    audit.add_argument("--write-release-history", action="store_true", help="Append the current release decision to a sanitized cross-run history.")
    audit.add_argument("--release-history-report", help="Optional output path for the release-readiness history Markdown file.")
    audit.add_argument("--market-sample-dir", action="append", default=[], help="Additional exported report directory to include in the cross-scenario market sample matrix. Repeat for single-paper, paper-set, and field/course samples.")

    return parser


def _add_unified_planner_args(parser: argparse.ArgumentParser, default_target_kind: str = "auto") -> None:
    parser.set_defaults(default_target_kind=default_target_kind)
    parser.add_argument("--preset", choices=sorted(PLANNER_PRESETS), help="Common planner preset such as paper-fastest, field-project, or course-complete.")
    parser.add_argument("--route-depth", choices=["fastest", "balanced", "complete"])
    parser.add_argument("--learning-style", choices=["practical", "theory", "video", "auto"])
    parser.add_argument("--target-kind", choices=["paper", "field", "course", "auto"])


def _planner_options(args: argparse.Namespace) -> dict[str, str]:
    options = {
        "route_depth": "balanced",
        "learning_style": "practical",
        "target_kind": getattr(args, "default_target_kind", "auto"),
    }
    preset = getattr(args, "preset", None)
    if preset:
        options.update(PLANNER_PRESETS[preset])
    if args.route_depth:
        options["route_depth"] = args.route_depth
    if args.learning_style:
        options["learning_style"] = args.learning_style
    if args.target_kind:
        options["target_kind"] = args.target_kind
    return options


def _roadmap(args: argparse.Namespace) -> int:
    if args.interactive:
        _interactive_update_args(args, "roadmap")
    if not args.goal:
        print("error: --goal is required unless --interactive supplies one", file=sys.stderr)
        return 2
    planner = _planner_options(args)
    profile = LearnerProfile(
        goal=args.goal,
        output_language=normalize_output_language(args.output_language),
        resource_language_preference=normalize_resource_language_preference(args.resource_language),
        known_topics=args.known_topic,
        levels=_parse_levels(args.level),
        weekly_hours=args.weekly_hours,
        target_date=args.target_date,
        target_kind=planner["target_kind"],
        route_depth=planner["route_depth"],
        learning_style=planner["learning_style"],
    )
    registry = SourceRegistry.default()
    live_diagnostics = {"enabled": False, "status": "not_requested"}
    resources = offline_resources_for_goal(args.goal)
    selected_sources = _parse_sources(args.sources)
    if not args.offline and not args.no_live_search:
        live_resources, live_diagnostics = _safe_live_search(args.goal, sorted(selected_sources) if selected_sources else None, args.resource_language)
        resources.extend(live_resources)
    if selected_sources:
        resources = _filter_resources_by_sources(resources, selected_sources, registry)
    if args.local_resource:
        resources.extend(analyze_local_resources(args.local_resource, args.goal))
    ranked = rank_resources(resources, profile)
    ranked, rag_index = apply_rag_to_resources(profile, ranked, mode=args.rag)
    rag_evidence = public_rag_evidence(rag_index, profile.goal)
    roadmap = build_roadmap(profile, ranked, live_search=live_diagnostics, rag_evidence=rag_evidence)
    if rag_evidence:
        roadmap["rag_evidence"] = rag_evidence
    manifest = None
    if args.resource_dir:
        manifest = bundle_study_resources(
            Path(args.resource_dir),
            ranked,
            roadmap,
            bundle_scope=args.bundle_scope,
            retries=max(0, args.download_retries),
            progress=None if args.quiet_downloads else _print_bundle_progress,
        )
        if args.rag != "off":
            write_bundle_rag_index(Path(args.resource_dir), manifest, query=profile.goal, mode=args.rag)
        roadmap = attach_study_bundle(roadmap, manifest, report_dir=Path(args.output_dir))
    roadmap = _apply_paper_lens_option(args, roadmap)
    roadmap = _apply_paper_map_option(args, roadmap)
    write_outputs(Path(args.output_dir), profile, ranked, roadmap, registry.snapshot())
    if manifest is not None:
        print((Path(args.resource_dir) / "study_bundle_manifest.json").resolve())
        print(f"resources: {manifest['summary']}")
    print(Path(args.output_dir).resolve())
    return 0


def _paper(args: argparse.Namespace) -> int:
    if args.interactive:
        _interactive_update_args(args, "paper")
    if not args.url:
        print("error: --url is required unless --interactive supplies one", file=sys.stderr)
        return 2
    target_resource = _paper_resource_from_url(args.url, live=not args.no_live_search)
    planner = _planner_options(args)
    profile = LearnerProfile(
        goal=_paper_profile_goal(args.goal, target_resource, args.url),
        output_language=normalize_output_language(args.output_language),
        resource_language_preference=normalize_resource_language_preference(args.resource_language),
        levels={"paper_reading": "beginner"},
        target_kind=planner["target_kind"],
        route_depth=planner["route_depth"],
        learning_style=planner["learning_style"],
    )
    registry = SourceRegistry.default()
    live_diagnostics = {"enabled": False, "status": "not_requested"}
    resources = [target_resource]
    query = _paper_support_query(args.goal, target_resource, args.url)
    resources.extend(offline_resources_for_goal(query))
    if not args.no_live_search:
        live_resources, live_diagnostics = _safe_live_search(_paper_live_search_query(args.goal, args.url), None, args.resource_language)
        resources.extend(live_resources)
    if args.local_resource:
        resources.extend(analyze_local_resources(args.local_resource, query))
    if not args.with_videos:
        resources = [resource for resource in resources if resource.type != "video"]
    ranked = rank_resources(resources, profile)
    ranked, rag_index = apply_rag_to_resources(profile, ranked, mode=args.rag)
    rag_evidence = public_rag_evidence(rag_index, profile.goal)
    roadmap = build_roadmap(profile, ranked, live_search=live_diagnostics, rag_evidence=rag_evidence)
    if rag_evidence:
        roadmap["rag_evidence"] = rag_evidence
    manifest = None
    if args.resource_dir:
        manifest = bundle_study_resources(
            Path(args.resource_dir),
            ranked,
            roadmap,
            bundle_scope=args.bundle_scope,
            retries=max(0, args.download_retries),
            progress=None if args.quiet_downloads else _print_bundle_progress,
        )
        if args.rag != "off":
            write_bundle_rag_index(Path(args.resource_dir), manifest, query=profile.goal, mode=args.rag)
        roadmap = attach_study_bundle(roadmap, manifest, report_dir=Path(args.output_dir))
    roadmap = _apply_paper_lens_option(args, roadmap)
    roadmap = _apply_paper_map_option(args, roadmap)
    write_outputs(Path(args.output_dir), profile, ranked, roadmap, registry.snapshot())
    if manifest is not None:
        print((Path(args.resource_dir) / "study_bundle_manifest.json").resolve())
        print(f"resources: {manifest['summary']}")
    print(Path(args.output_dir).resolve())
    return 0


def _interactive_update_args(args: argparse.Namespace, mode: str) -> None:
    print("fields-study-flow interactive setup / 交互式设置")
    print("Press Enter to keep the value shown in brackets. / 直接回车保留方括号中的默认值。")
    if mode == "paper":
        args.url = _prompt_text("Paper URL / DOI / local PDF path / 论文 URL、DOI 或本地 PDF 路径", args.url)
        args.goal = _prompt_text("Learning goal / 学习目标", args.goal)
        args.with_videos = _prompt_bool("Include video resources as links / 是否保留视频资源链接", args.with_videos)
    else:
        args.goal = _prompt_text("Learning goal / 学习目标", args.goal)
    args.output_language = _prompt_choice("Output language / 输出语言", args.output_language, ["zh-CN", "en", "bilingual"])
    args.resource_language = _prompt_choice("Resource language preference / 资料语言偏好", args.resource_language, ["zh-first", "en-first", "balanced", "zh-only", "en-only"])
    args.route_depth = _prompt_choice("Route depth / 路线深度", args.route_depth or "balanced", ["fastest", "balanced", "complete"])
    args.learning_style = _prompt_choice("Learning style / 学习风格", args.learning_style or "practical", ["practical", "theory", "video", "auto"])
    args.target_kind = _prompt_choice(
        "Target kind / 目标类型",
        args.target_kind or getattr(args, "default_target_kind", "auto"),
        ["paper", "field", "course", "auto"],
    )
    local_paths = _prompt_text("Local resource path(s), separated by ; / 本地资料路径，多个用 ; 分隔", ";".join(args.local_resource or []), required=False)
    args.local_resource = [path.strip() for path in local_paths.split(";") if path.strip()]
    args.output_dir = _prompt_text("Report output directory / 报告输出目录", args.output_dir)
    want_bundle = _prompt_bool("Copy/download the full study resource library to a private folder / 是否复制或下载学习资料包", bool(args.resource_dir))
    if want_bundle:
        default_resource_dir = args.resource_dir or str(Path(args.output_dir) / "study_resources")
        args.resource_dir = _prompt_text("Resource download/copy directory / 资料下载或复制目录", default_resource_dir)
        args.bundle_scope = _prompt_choice(
            "Bundle scope: all downloads every directly available candidate; selected only bundles the shortest route / 资料包范围：all 尽量下载全部可获取候选资料，selected 只打包最短路线资料",
            args.bundle_scope or "all",
            ["all", "selected"],
        )
    else:
        args.resource_dir = None
    if mode == "roadmap":
        args.offline = _prompt_bool("Use offline deterministic catalog only / 是否只使用离线内置资源目录", args.offline)
    if not getattr(args, "offline", False):
        args.no_live_search = not _prompt_bool("Enable live open-source discovery / 是否启用开放来源实时发现", not args.no_live_search)


def _apply_paper_lens_option(args: argparse.Namespace, roadmap: dict[str, object]) -> dict[str, object]:
    updated = dict(roadmap)
    if not getattr(args, "no_paper_lens", False):
        updated["paper_lens_options"] = {
            "language": getattr(args, "paper_lens_language", "auto"),
            "density": getattr(args, "paper_lens_density", "dense"),
            "granularity": getattr(args, "paper_lens_granularity", "paragraph"),
        }
        updated.pop("paper_lens", None)
        return updated
    updated["paper_lens_disabled"] = True
    updated.pop("paper_lens", None)
    outputs = updated.get("outputs")
    if isinstance(outputs, list):
        updated["outputs"] = [item for item in outputs if item != "paper_lens.html"]
    return updated


def _apply_paper_map_option(args: argparse.Namespace, roadmap: dict[str, object]) -> dict[str, object]:
    updated = dict(roadmap)
    if not getattr(args, "no_paper_map", False):
        updated["paper_map_options"] = {
            "language": getattr(args, "paper_map_language", "auto"),
            "depth": getattr(args, "paper_map_depth", "standard"),
            "layout": getattr(args, "paper_map_layout", "xmind-flow"),
            "provider": getattr(args, "paper_map_provider", "auto"),
        }
        updated.pop("paper_map", None)
        return updated
    updated["paper_map_disabled"] = True
    updated.pop("paper_map", None)
    outputs = updated.get("outputs")
    if isinstance(outputs, list):
        updated["outputs"] = [item for item in outputs if item != "paper_map.html"]
    return updated


def _prompt_text(label: str, current: str | None, *, required: bool = True) -> str:
    current = current or ""
    while True:
        value = input(f"{label} [{current}]: ").strip()
        output = value or current
        if output or not required:
            return output
        print("This value is required.")


def _prompt_choice(label: str, current: str | None, choices: list[str]) -> str:
    current = current if current in choices else choices[0]
    options = "/".join(choices)
    while True:
        value = input(f"{label} ({options}) [{current}]: ").strip()
        output = value or current
        if output in choices:
            return output
        print(f"Choose one of: {options}")


def _prompt_bool(label: str, current: bool) -> bool:
    default = "y" if current else "n"
    while True:
        value = input(f"{label} (y/n) [{default}]: ").strip().lower()
        value = value or default
        if value in {"y", "yes", "true", "1"}:
            return True
        if value in {"n", "no", "false", "0"}:
            return False
        print("Choose y or n.")


def _print_bundle_progress(event: dict[str, object]) -> None:
    kind = str(event.get("event", ""))
    index = event.get("index", "?")
    total = event.get("total", "?")
    title = event.get("title", "Resource")
    if kind == "start":
        print(f"[{index}/{total}] {title}")
    elif kind == "attempt":
        attempt = event.get("attempt", "?")
        max_attempts = event.get("max_attempts", "?")
        action = event.get("action", "download")
        print(f"  {action} attempt {attempt}/{max_attempts}: {event.get('url', '')}")
    elif kind == "finish":
        status = event.get("status", "unknown")
        target = event.get("file") or ("retryable" if event.get("retryable") else "link-only")
        print(f"  -> {status}: {target}")


def _paper_profile_goal(goal: str, target_resource: Resource, original_url: str) -> str:
    public_identifier = _public_paper_identifier(original_url)
    target_name = target_resource.title or public_identifier or "target paper"
    clean_goal = _collapse_repeated_goal_tail(goal)
    if _normalized_goal_contains(clean_goal, target_name):
        return clean_goal
    return f"{clean_goal}: {target_name}"


def _normalized_goal_contains(value: str, needle: str) -> bool:
    normalized_value = _normalize_goal_text(value)
    normalized_needle = _normalize_goal_text(needle)
    return bool(normalized_needle and normalized_needle in normalized_value)


def _normalize_goal_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _collapse_repeated_goal_tail(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    for _ in range(3):
        changed = False
        for size in range(len(text) // 2, 15, -1):
            tail = text[-size:].strip()
            prefix = text[:-size].strip()
            prefix_without_separator = re.sub(r"[:\uff1a,\uff0c;\uff1b-]+\s*$", "", prefix).strip()
            if tail and _normalize_goal_text(prefix_without_separator).endswith(_normalize_goal_text(tail)):
                text = prefix_without_separator
                changed = True
                break
        if not changed:
            break
    return text


def _safe_live_search(query: str, sources: list[str] | None, language_preference: str) -> tuple[list[Resource], dict[str, object]]:
    try:
        return search_live_resources(query, sources=sources, language_preference=language_preference)
    except Exception as exc:
        return [], {"enabled": True, "status": "fallback", "errors": [str(exc)], "manual_link_only_sources": [], "queried_sources": []}


def _paper_live_search_query(goal: str, url: str) -> str:
    parts = [goal, _paper_topic_hint(url), _public_paper_identifier(url)]
    return " ".join(part for part in parts if part).strip()


def _public_paper_identifier(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower().removeprefix("www.")
    path_parts = [part for part in parsed.path.split("/") if part]
    if host == "arxiv.org" and len(path_parts) >= 2 and path_parts[0] in {"abs", "pdf"}:
        paper_id = path_parts[1].removesuffix(".pdf")
        return paper_id
    if host in {"doi.org", "dx.doi.org"} and path_parts:
        return "doi " + "/".join(path_parts)
    return ""


def _ingest_url(args: argparse.Namespace) -> int:
    print(json.dumps(ingestUrl(args.url, args.source_hint), ensure_ascii=False, indent=2))
    return 0


def _analyze_local(args: argparse.Namespace) -> int:
    profile = LearnerProfile(goal=args.goal, resource_language_preference=normalize_resource_language_preference(args.resource_language))
    resources = rank_resources(analyze_local_resources(args.path, args.goal, max_files=args.max_files), profile)
    print(json.dumps([resource.to_dict() for resource in resources], ensure_ascii=False, indent=2))
    return 0


def _discover_sources(args: argparse.Namespace) -> int:
    registry = SourceRegistry.default()
    sources = registry.discover(language_preference=args.language, source_policy=args.source_policy)
    print(json.dumps([source.to_dict() for source in sources], ensure_ascii=False, indent=2))
    return 0


def _ask(args: argparse.Namespace) -> int:
    roadmap_path = Path(args.roadmap)
    resource_dir = Path(args.resource_dir) if args.resource_dir else _infer_resource_dir_from_roadmap(roadmap_path)
    if resource_dir is None:
        print("error: --resource-dir is required when the bundle directory cannot be inferred from --roadmap", file=sys.stderr)
        return 2
    result = answer_from_bundle(resource_dir, args.question, limit=max(1, args.limit))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _demo(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    if args.sample == "all-market":
        return _demo_market_suite(args, output_dir)
    if args.sample != "transformer-paper":
        profile, resources = _demo_sample(args.sample, normalize_output_language(args.output_language))
        _build_demo_report(output_dir, profile, resources)
        print((output_dir / "index.html").resolve())
        if getattr(args, "market_check", False):
            market_check = _run_demo_market_check(
                output_dir,
                fresh_user_minutes=getattr(args, "market_fresh_user_minutes", None),
                capture_screenshots=bool(getattr(args, "market_check_screenshots", False)),
                probe_interactions=bool(getattr(args, "market_check_interactions", False)),
            )
            market_check_path = output_dir / "demo_market_check.json"
            market_check_path.write_text(json.dumps(market_check, ensure_ascii=False, indent=2), encoding="utf-8")
            print(market_check_path.resolve())
        return 0
    profile = LearnerProfile(
        goal="快速理解并能够汇报 Attention Is All You Need",
        output_language=normalize_output_language(args.output_language),
        resource_language_preference=normalize_resource_language_preference("en-first"),
        levels={"paper_reading": "beginner"},
        target_kind="paper",
        route_depth="fastest",
        learning_style="practical",
    )
    resources = _demo_transformer_resources()
    _materialize_demo_resources(output_dir / "demo-source-materials", resources)
    ranked = rank_resources(resources, profile)
    ranked, rag_index = apply_rag_to_resources(profile, ranked, mode="light")
    roadmap = build_roadmap(
        profile,
        ranked,
        live_search={"enabled": False, "status": "demo_offline"},
        rag_evidence=public_rag_evidence(rag_index, profile.goal),
    )
    resource_dir = output_dir / "study-assets"
    manifest = bundle_study_resources(resource_dir, ranked, roadmap, bundle_scope="all", progress=None)
    write_bundle_rag_index(resource_dir, manifest, query=profile.goal, mode="light")
    roadmap = attach_study_bundle(roadmap, manifest, report_dir=output_dir)
    write_outputs(output_dir, profile, ranked, roadmap, SourceRegistry.default().snapshot())
    write_report_audit(output_dir, roadmap)
    print((output_dir / "index.html").resolve())
    if getattr(args, "market_check", False):
        market_check = _run_demo_market_check(
            output_dir,
            fresh_user_minutes=getattr(args, "market_fresh_user_minutes", None),
            capture_screenshots=bool(getattr(args, "market_check_screenshots", False)),
            probe_interactions=bool(getattr(args, "market_check_interactions", False)),
        )
        market_check_path = output_dir / "demo_market_check.json"
        market_check_path.write_text(json.dumps(market_check, ensure_ascii=False, indent=2), encoding="utf-8")
        print(market_check_path.resolve())
    return 0


def _demo_sample(sample: str, output_language: str) -> tuple[LearnerProfile, list[Resource]]:
    if sample == "diffusion-paper-set":
        return (
            LearnerProfile(
                goal="compare diffusion model papers: DDPM, score SDE, and classifier-free guidance",
                output_language=output_language,
                resource_language_preference=normalize_resource_language_preference("en-first"),
                levels={"paper_reading": "familiar", "generative_models": "beginner"},
                target_kind="field",
                route_depth="complete",
                learning_style="theory",
            ),
            _demo_diffusion_paper_set_resources(),
        )
    if sample == "diffusion-field-course":
        return (
            LearnerProfile(
                goal="learn diffusion models and build a small image generation project",
                output_language=output_language,
                resource_language_preference=normalize_resource_language_preference("en-first"),
                levels={"machine_learning": "familiar", "pytorch": "beginner"},
                target_kind="field",
                route_depth="complete",
                learning_style="practical",
            ),
            _demo_diffusion_field_course_resources(),
        )
    return (
        LearnerProfile(
            goal="quickly understand and present Attention Is All You Need",
            output_language=output_language,
            resource_language_preference=normalize_resource_language_preference("en-first"),
            levels={"paper_reading": "beginner"},
            target_kind="paper",
            route_depth="fastest",
            learning_style="practical",
        ),
        _demo_transformer_resources(),
    )


def _build_demo_report(output_dir: Path, profile: LearnerProfile, resources: list[Resource]) -> dict[str, object]:
    output_dir.mkdir(parents=True, exist_ok=True)
    _materialize_demo_resources(output_dir / "demo-source-materials", resources)
    ranked = rank_resources(resources, profile)
    ranked, rag_index = apply_rag_to_resources(profile, ranked, mode="light")
    roadmap = build_roadmap(
        profile,
        ranked,
        live_search={"enabled": False, "status": "demo_offline"},
        rag_evidence=public_rag_evidence(rag_index, profile.goal),
    )
    resource_dir = output_dir / "study-assets"
    manifest = bundle_study_resources(resource_dir, ranked, roadmap, bundle_scope="all", progress=None)
    write_bundle_rag_index(resource_dir, manifest, query=profile.goal, mode="light")
    roadmap = attach_study_bundle(roadmap, manifest, report_dir=output_dir)
    write_outputs(output_dir, profile, ranked, roadmap, SourceRegistry.default().snapshot())
    write_report_audit(output_dir, roadmap)
    return roadmap


def _demo_market_suite(args: argparse.Namespace, output_dir: Path) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    sample_names = ["transformer-paper", "diffusion-paper-set", "diffusion-field-course"]
    sample_dirs: list[Path] = []
    for sample in sample_names:
        sample_dir = output_dir / sample
        profile, resources = _demo_sample(sample, normalize_output_language(args.output_language))
        _build_demo_report(sample_dir, profile, resources)
        sample_dirs.append(sample_dir)
        if getattr(args, "market_check", False):
            market_check = _run_demo_market_check(
                sample_dir,
                fresh_user_minutes=getattr(args, "market_fresh_user_minutes", None),
                capture_screenshots=bool(getattr(args, "market_check_screenshots", False)),
                probe_interactions=bool(getattr(args, "market_check_interactions", False)),
            )
            (sample_dir / "demo_market_check.json").write_text(json.dumps(market_check, ensure_ascii=False, indent=2), encoding="utf-8")
    matrix = evaluate_market_sample_matrix(sample_dirs)
    matrix_path = output_dir / "market_sample_matrix.json"
    matrix_path.write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_demo_market_suite_index(output_dir, sample_dirs, matrix)
    print((output_dir / "index.html").resolve())
    print(matrix_path.resolve())
    return 0


def _write_demo_market_suite_index(output_dir: Path, sample_dirs: list[Path], matrix: dict[str, object]) -> None:
    summary = matrix.get("summary") if isinstance(matrix.get("summary"), dict) else {}
    covered = ", ".join(str(item) for item in summary.get("covered_scenarios", [])) or "-"
    missing = ", ".join(str(item) for item in summary.get("missing_scenarios", [])) or "-"
    cards = "\n".join(
        f'<a class="sample-card" href="{sample_dir.name}/index.html"><span>{sample_dir.name}</span><strong>Open report</strong></a>'
        for sample_dir in sample_dirs
    )
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>fields-study-flow market samples</title>
  <style>
    * {{ box-sizing:border-box; }}
    body {{ margin:0; background:#f6f4ef; color:#18201d; font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Noto Sans SC",Arial,sans-serif; line-height:1.65; }}
    main {{ width:min(1080px, calc(100vw - 28px)); margin:0 auto; padding:30px 0 46px; overflow-wrap:anywhere; }}
    .hero, .sample-card, .matrix-card {{ border:1px solid #d9e2d7; border-radius:18px; background:#fffdfa; box-shadow:0 14px 36px rgba(43,53,45,.08); }}
    .hero {{ padding:26px; }}
    h1 {{ margin:0 0 10px; font-size:clamp(2rem,5vw,4rem); line-height:1.05; letter-spacing:0; }}
    p {{ margin-top:0; color:#536258; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:12px; margin-top:16px; }}
    .sample-card, .matrix-card {{ display:block; padding:16px; color:inherit; text-decoration:none; }}
    .sample-card span, .matrix-card span {{ display:block; color:#657066; font-size:.9rem; }}
    .sample-card strong, .matrix-card strong {{ display:block; margin-top:6px; color:#2f6f73; font-size:1.1rem; }}
    @media (max-width:720px) {{ main {{ width:min(100vw - 18px, 720px); }} .hero, .sample-card, .matrix-card {{ border-radius:14px; }} }}
  </style>
</head>
<body>
  <main>
    <section class="hero">
      <p>Market sample matrix</p>
      <h1>fields-study-flow market samples</h1>
      <p>Use these three offline reports to review single-paper, paper-set, and field/course learning before claiming broad market readiness.</p>
      <div class="grid">
        <article class="matrix-card"><span>Matrix status</span><strong>{matrix.get("status", "unknown")}</strong></article>
        <article class="matrix-card"><span>Covered scenarios</span><strong>{covered}</strong></article>
        <article class="matrix-card"><span>Missing scenarios</span><strong>{missing}</strong></article>
        <a class="matrix-card" href="market_sample_matrix.json"><span>Audit data</span><strong>Open JSON</strong></a>
      </div>
    </section>
    <section class="grid" aria-label="sample reports">
      {cards}
    </section>
  </main>
</body>
</html>"""
    output_dir.joinpath("index.html").write_text(html, encoding="utf-8")


def _run_demo_market_check(
    output_dir: Path,
    *,
    fresh_user_minutes: float | None = None,
    capture_screenshots: bool = False,
    probe_interactions: bool = False,
) -> dict[str, object]:
    result = audit_report_directory(output_dir)
    roadmap_path = output_dir / "roadmap.json"
    try:
        roadmap = json.loads(roadmap_path.read_text(encoding="utf-8"))
        result["report_audit"] = write_report_audit(output_dir, roadmap)
    except (OSError, json.JSONDecodeError) as exc:
        result["report_audit"] = {
            "status": "warn",
            "summary": {"path": "report_audit.json", "error": str(exc)},
        }
    if capture_screenshots:
        result["browser_snapshot_capture"] = capture_browser_snapshots(output_dir)
    if probe_interactions:
        result["browser_interaction_probe"] = probe_browser_interactions(output_dir)
    if fresh_user_minutes is not None:
        result["fresh_user_timing"] = evaluate_fresh_user_timing(float(fresh_user_minutes))
    result["release_readiness_report"] = write_release_readiness_report(output_dir, result)
    result["generated_artifact_audit"] = audit_report_directory(output_dir)
    release_summary = result.get("release_readiness_report", {}).get("summary", {})
    next_actions = release_summary.get("next_actions", []) if isinstance(release_summary, dict) else []
    result["market_check_summary"] = {
        "decision": release_summary.get("decision", "needs_work") if isinstance(release_summary, dict) else "needs_work",
        "score": release_summary.get("score", 0) if isinstance(release_summary, dict) else 0,
        "next_actions": _demo_market_next_actions(next_actions),
        "report": "release_readiness.html",
    }
    return result


def _demo_market_next_actions(actions: object) -> list[str]:
    if not isinstance(actions, list):
        return []
    replacements = {
        "--fresh-user-minutes": "--market-fresh-user-minutes",
        "--capture-screenshots": "--market-check-screenshots",
        "--probe-interactions": "--market-check-interactions",
    }
    adapted: list[str] = []
    for action in actions:
        text = str(action)
        for original, replacement in replacements.items():
            text = text.replace(original, replacement)
        adapted.append(text)
    return adapted


def _audit_report(args: argparse.Namespace) -> int:
    report_dir = Path(args.report_dir)
    result = audit_report_directory(report_dir)
    roadmap_path = report_dir / "roadmap.json"
    if roadmap_path.exists():
        try:
            roadmap = json.loads(roadmap_path.read_text(encoding="utf-8"))
            result["report_audit"] = write_report_audit(report_dir, roadmap)
        except (OSError, json.JSONDecodeError) as exc:
            result["report_audit"] = {
                "status": "warn",
                "summary": {"path": "report_audit.json", "error": str(exc)},
            }
    snapshot_result = None
    if getattr(args, "capture_screenshots", False):
        snapshot_result = capture_browser_snapshots(
            Path(args.report_dir),
            output_dir=Path(args.screenshot_dir) if getattr(args, "screenshot_dir", None) else None,
        )
        result["browser_snapshot_capture"] = snapshot_result
    if getattr(args, "probe_interactions", False):
        result["browser_interaction_probe"] = probe_browser_interactions(Path(args.report_dir))
    if getattr(args, "snapshot_baseline", None):
        if snapshot_result is None:
            snapshot_result = _read_existing_snapshot_manifest(Path(args.report_dir), Path(args.screenshot_dir) if getattr(args, "screenshot_dir", None) else None)
        result["browser_snapshot_baseline"] = compare_browser_snapshot_baseline(snapshot_result, Path(args.snapshot_baseline))
    if getattr(args, "fresh_user_minutes", None) is not None:
        result["fresh_user_timing"] = evaluate_fresh_user_timing(
            float(args.fresh_user_minutes),
            target_minutes=float(getattr(args, "fresh_user_target_minutes", 10.0)),
        )
    if getattr(args, "write_fresh_user_worksheet", False):
        result["fresh_user_worksheet"] = write_fresh_user_worksheet(
            Path(args.report_dir),
            target_minutes=float(getattr(args, "fresh_user_target_minutes", 10.0)),
            output_path=Path(args.fresh_user_worksheet) if getattr(args, "fresh_user_worksheet", None) else None,
        )
    worksheet_inputs = [Path(item) for item in getattr(args, "fresh_user_worksheet_input", [])]
    if worksheet_inputs:
        if getattr(args, "write_fresh_user_backlog", False):
            result["fresh_user_backlog"] = write_fresh_user_backlog(
                worksheet_inputs,
                Path(args.report_dir),
                output_path=Path(args.fresh_user_backlog) if getattr(args, "fresh_user_backlog", None) else None,
            )
        else:
            result["fresh_user_backlog"] = summarize_fresh_user_worksheets(worksheet_inputs)
    backlog_inputs = [Path(item) for item in getattr(args, "fresh_user_backlog_input", [])]
    if backlog_inputs:
        if getattr(args, "write_fresh_user_trend_report", False):
            result["fresh_user_trend_report"] = write_fresh_user_trend_report(
                backlog_inputs,
                Path(args.report_dir),
                output_path=Path(args.fresh_user_trend_report) if getattr(args, "fresh_user_trend_report", None) else None,
            )
        else:
            result["fresh_user_trend_report"] = summarize_fresh_user_backlogs(backlog_inputs)
    market_sample_dirs = [Path(item) for item in getattr(args, "market_sample_dir", [])]
    if market_sample_dirs:
        result["market_sample_matrix"] = evaluate_market_sample_matrix(market_sample_dirs)
    if getattr(args, "write_release_readiness", False) or getattr(args, "write_release_history", False):
        result["release_readiness_report"] = write_release_readiness_report(
            Path(args.report_dir),
            result,
            output_path=Path(args.release_readiness_report) if getattr(args, "release_readiness_report", None) else None,
        )
    if getattr(args, "write_release_history", False):
        result["release_readiness_history"] = write_release_readiness_history(
            Path(args.report_dir),
            result["release_readiness_report"],
            output_path=Path(args.release_history_report) if getattr(args, "release_history_report", None) else None,
        )
    if result.get("release_readiness_report") or result.get("release_readiness_history"):
        result["generated_artifact_audit"] = audit_report_directory(Path(args.report_dir))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    screenshot_status = (result.get("browser_snapshot_capture") or {}).get("status", "pass")
    interaction_status = (result.get("browser_interaction_probe") or {}).get("status", "pass")
    baseline_status = (result.get("browser_snapshot_baseline") or {}).get("status", "pass")
    timing_status = (result.get("fresh_user_timing") or {}).get("status", "pass")
    worksheet_status = (result.get("fresh_user_worksheet") or {}).get("status", "pass")
    backlog_status = (result.get("fresh_user_backlog") or {}).get("status", "pass")
    trend_status = (result.get("fresh_user_trend_report") or {}).get("status", "pass")
    matrix_status = (result.get("market_sample_matrix") or {}).get("status", "pass")
    release_status = (result.get("release_readiness_report") or {}).get("status", "pass")
    history_status = (result.get("release_readiness_history") or {}).get("status", "pass")
    generated_status = (result.get("generated_artifact_audit") or {}).get("status", "pass")
    return 0 if result["status"] == "pass" and screenshot_status in {"pass", "skipped"} and interaction_status in {"pass", "skipped"} and baseline_status == "pass" and timing_status == "pass" and worksheet_status in {"pass", "warn"} and backlog_status in {"pass", "warn"} and trend_status in {"pass", "warn"} and matrix_status in {"pass", "warn"} and release_status in {"pass", "warn"} and history_status in {"pass", "warn"} and generated_status == "pass" else 1


def _read_existing_snapshot_manifest(report_dir: Path, screenshot_dir: Path | None = None) -> dict[str, object]:
    manifest = (screenshot_dir if screenshot_dir else report_dir / "visual-snapshots") / "manifest.json"
    try:
        return json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "missing",
            "summary": {
                "mode": "browser-backed",
                "reason": f"Snapshot manifest could not be read: {exc}",
            },
            "captures": [],
            "checks": [],
        }


def _demo_transformer_resources() -> list[Resource]:
    target_metadata = {
        "target_paper": True,
        "paper_metadata": {
            "title": "Attention Is All You Need",
            "abstract_snippet": (
                "The paper introduces the Transformer, a sequence transduction architecture based entirely on attention. "
                "It replaces recurrent and convolutional layers with self-attention, multi-head attention, and positional encodings."
            ),
            "authors": ["Ashish Vaswani", "Noam Shazeer", "Niki Parmar", "Jakob Uszkoreit"],
            "source_ids": {"arxiv": "1706.03762"},
            "concepts": ["Transformer", "self-attention", "multi-head attention", "positional encoding", "machine translation"],
            "sections": ["Abstract", "Introduction", "Model Architecture", "Experiments", "Conclusion"],
            "method_hints": [
                "Scaled dot-product attention computes compatibility between queries and keys, then mixes values.",
                "Multi-head attention lets the model attend to information from different representation subspaces.",
                "Positional encodings inject token order because the architecture has no recurrence.",
            ],
            "experiment_hints": [
                "The paper evaluates on WMT 2014 English-German and English-French translation.",
                "It compares BLEU score, training cost, and model variants through ablations.",
            ],
            "limitations_hints": [
                "Self-attention has quadratic cost in sequence length.",
                "The original experiments focus on translation, so transfer to other tasks needs separate validation.",
            ],
            "metadata_status": "demo",
            "warnings": ["This bundled demo uses public metadata-style hints plus local demo notes; it is not the full paper PDF."],
        },
    }
    return [
        Resource(
            title="Attention Is All You Need",
            url="https://arxiv.org/abs/1706.03762",
            source="arxiv",
            type="paper",
            language="en",
            difficulty="intermediate",
            concepts=["Transformer", "self-attention", "multi-head attention", "positional encoding"],
            learning_key_points=[
                "为什么去掉 RNN/CNN 后仍然能建模序列关系",
                "scaled dot-product attention 的输入、输出和复杂度",
                "multi-head attention 如何把不同关系分到多个子空间",
            ],
            focus_areas=["architecture logic", "attention formula", "ablation evidence"],
            estimated_minutes=120,
            trust_score=0.99,
            why_recommended="Demo target paper. It is the core object that Paper Map and Paper Lens explain.",
            license_or_access_note="Open arXiv abstract page.",
            critical_path_role="core-paper",
            metadata=target_metadata,
        ),
        Resource(
            title="The Annotated Transformer",
            url="https://nlp.seas.harvard.edu/annotated-transformer/",
            source="web",
            type="article",
            language="en",
            difficulty="intermediate",
            concepts=["Transformer", "PyTorch", "attention implementation", "training loop"],
            learning_key_points=[
                "把论文结构映射到可运行 PyTorch 代码",
                "观察 attention、encoder、decoder 和 loss 训练流程如何连接",
            ],
            focus_areas=["implementation", "reproduction"],
            estimated_minutes=90,
            trust_score=0.9,
            why_recommended="Turns the Transformer paper into readable implementation notes for the reproduce gate.",
            license_or_access_note="Public educational webpage.",
            critical_path_role="implementation-support",
        ),
        Resource(
            title="The Illustrated Transformer",
            url="https://jalammar.github.io/illustrated-transformer/",
            source="web",
            type="article",
            language="en",
            difficulty="beginner",
            concepts=["self-attention", "encoder-decoder", "visual intuition"],
            learning_key_points=[
                "用图像直观理解 Q/K/V 和注意力权重",
                "先建立结构直觉，再回到论文公式",
            ],
            focus_areas=["intuition", "explain"],
            estimated_minutes=45,
            trust_score=0.82,
            why_recommended="Shortens the path for a first-time reader who needs a visual explanation before formulas.",
            license_or_access_note="Public educational article.",
            critical_path_role="focused-support",
        ),
        Resource(
            title="PyTorch Transformer Tutorial",
            url="https://docs.pytorch.org/tutorials/beginner/transformer_tutorial.html",
            source="official-docs",
            type="documentation",
            language="en",
            difficulty="intermediate",
            concepts=["Transformer", "PyTorch", "language modeling", "implementation"],
            learning_key_points=[
                "用官方框架搭建最小 Transformer 训练任务",
                "把论文的模块拆成可以检查的工程步骤",
            ],
            focus_areas=["practice", "validation"],
            estimated_minutes=75,
            trust_score=0.86,
            why_recommended="Provides an official implementation-oriented path for a small validation project.",
            license_or_access_note="Official public PyTorch documentation.",
            critical_path_role="practice-validation",
        ),
    ]


def _demo_diffusion_paper_set_resources() -> list[Resource]:
    return [
        Resource(
            title="Diffusion Models Prerequisite Sprint",
            url="local://diffusion-prerequisite-sprint",
            source="generated",
            type="template",
            language="en",
            difficulty="beginner",
            concepts=["Gaussian noise", "Markov chains", "variational inference", "score matching"],
            learning_key_points=[
                "Review only the probability concepts that unlock DDPM and score-based diffusion papers.",
                "Map noise schedules, likelihood bounds, and score functions to the later paper comparison.",
            ],
            focus_areas=["prerequisites", "probability", "paper reading bridge"],
            estimated_minutes=75,
            trust_score=0.8,
            why_recommended="Adds a short foundation phase so the paper-set demo shows how learners enter the literature before comparing papers.",
            license_or_access_note="Generated local demo prerequisite sprint.",
            critical_path_role="prerequisite",
        ),
        Resource(
            title="Denoising Diffusion Probabilistic Models",
            url="https://arxiv.org/abs/2006.11239",
            source="arxiv",
            type="paper",
            language="en",
            difficulty="advanced",
            concepts=["diffusion models", "denoising", "variational inference", "sampling"],
            learning_key_points=[
                "Forward noising turns data into Gaussian noise through a Markov chain.",
                "Reverse denoising learns to reconstruct data step by step.",
                "The training objective connects variational bounds with a simple noise-prediction loss.",
            ],
            focus_areas=["methodology", "objective", "sampling"],
            estimated_minutes=180,
            trust_score=0.97,
            why_recommended="Core paper for understanding the discrete DDPM formulation before comparing later variants.",
            license_or_access_note="Open arXiv abstract page.",
            critical_path_role="core-paper",
            metadata={
                "paper_metadata": {
                    "title": "Denoising Diffusion Probabilistic Models",
                    "abstract_snippet": "A discrete-time denoising diffusion model that learns a reverse process from noise to data.",
                    "concepts": ["diffusion models", "denoising", "variational inference"],
                }
            },
        ),
        Resource(
            title="Score-Based Generative Modeling through Stochastic Differential Equations",
            url="https://arxiv.org/abs/2011.13456",
            source="arxiv",
            type="paper",
            language="en",
            difficulty="advanced",
            concepts=["diffusion models", "score matching", "stochastic differential equations", "sampling"],
            learning_key_points=[
                "Continuous-time SDEs generalize discrete diffusion processes.",
                "Score functions guide the reverse-time generative process.",
                "Predictor-corrector samplers connect theory with image generation practice.",
            ],
            focus_areas=["continuous-time formulation", "score estimation", "samplers"],
            estimated_minutes=210,
            trust_score=0.95,
            why_recommended="Shows how diffusion methods evolved from discrete Markov chains to continuous-time score-based models.",
            license_or_access_note="Open arXiv abstract page.",
            critical_path_role="focused-support",
            metadata={
                "paper_metadata": {
                    "title": "Score-Based Generative Modeling through Stochastic Differential Equations",
                    "abstract_snippet": "A continuous-time framework for score-based generative modeling with SDEs.",
                    "concepts": ["diffusion models", "score matching", "stochastic differential equations"],
                }
            },
        ),
        Resource(
            title="Classifier-Free Diffusion Guidance",
            url="https://arxiv.org/abs/2207.12598",
            source="arxiv",
            type="paper",
            language="en",
            difficulty="advanced",
            concepts=["diffusion models", "classifier-free guidance", "conditional generation", "evaluation"],
            learning_key_points=[
                "Classifier-free guidance mixes conditional and unconditional predictions.",
                "Guidance strength trades diversity for sample quality.",
                "The technique became a practical default for controllable diffusion generation.",
            ],
            focus_areas=["guidance", "conditioning", "evaluation"],
            estimated_minutes=150,
            trust_score=0.93,
            why_recommended="Adds the practical control mechanism that learners need to compare modern diffusion pipelines.",
            license_or_access_note="Open arXiv abstract page.",
            critical_path_role="support",
            metadata={
                "paper_metadata": {
                    "title": "Classifier-Free Diffusion Guidance",
                    "abstract_snippet": "A guidance method for conditional diffusion models that avoids a separate classifier.",
                    "concepts": ["diffusion models", "classifier-free guidance", "conditional generation"],
                }
            },
        ),
        Resource(
            title="Diffusion Paper Comparison Worksheet",
            url="local://diffusion-paper-comparison-worksheet",
            source="generated",
            type="template",
            language="en",
            difficulty="beginner",
            concepts=["paper comparison", "method evolution", "evaluation evidence"],
            learning_key_points=[
                "Compare each paper by problem, method, objective, sampler, experiment, contribution, and limitation.",
                "Use shared concepts to explain why the papers form one learning path.",
            ],
            focus_areas=["synthesis", "presentation", "critique"],
            estimated_minutes=60,
            trust_score=0.78,
            why_recommended="Turns the paper set into a measurable synthesis task rather than a loose bibliography.",
            license_or_access_note="Generated local demo worksheet.",
            critical_path_role="practice-validation",
        ),
    ]


def _demo_diffusion_field_course_resources() -> list[Resource]:
    return [
        Resource(
            title="Generative Modeling Prerequisite Sprint",
            url="local://generative-modeling-prerequisite-sprint",
            source="generated",
            type="template",
            language="en",
            difficulty="beginner",
            concepts=["probability", "PyTorch tensors", "training loop", "image generation"],
            learning_key_points=[
                "Refresh the minimum probability and PyTorch pieces needed before starting diffusion models.",
                "Connect data, noise, loss, and generated samples before reading full implementation notes.",
            ],
            focus_areas=["prerequisites", "implementation readiness", "mental model"],
            estimated_minutes=70,
            trust_score=0.8,
            why_recommended="Creates a clear foundation phase for the field/course demo instead of starting directly from implementation resources.",
            license_or_access_note="Generated local demo prerequisite sprint.",
            critical_path_role="prerequisite",
        ),
        Resource(
            title="Diffusion Models from Scratch Notes",
            url="local://diffusion-from-scratch-notes",
            source="local-library",
            type="course",
            language="en",
            difficulty="beginner",
            concepts=["diffusion models", "forward process", "reverse process", "noise prediction"],
            learning_key_points=[
                "Understand the forward noising process before reading model code.",
                "Map reverse denoising to a small neural network training loop.",
            ],
            focus_areas=["prerequisites", "intuition", "implementation"],
            estimated_minutes=90,
            trust_score=0.82,
            why_recommended="Gives a compact prerequisite path for learners who want a project, not only papers.",
            license_or_access_note="Generated local demo notes.",
            critical_path_role="core-concept",
        ),
        Resource(
            title="The Annotated Diffusion Model",
            url="https://huggingface.co/blog/annotated-diffusion",
            source="huggingface",
            type="article",
            language="en",
            difficulty="intermediate",
            concepts=["diffusion models", "PyTorch", "UNet", "training loop"],
            learning_key_points=[
                "Build the diffusion process and denoising model in readable code.",
                "Connect loss, sampler, schedule, and generated images.",
            ],
            focus_areas=["implementation", "project"],
            estimated_minutes=150,
            trust_score=0.88,
            why_recommended="Provides a practical implementation bridge for the field/course project path.",
            license_or_access_note="Public educational article.",
            critical_path_role="implementation-support",
        ),
        Resource(
            title="Diffusers Quicktour",
            url="https://huggingface.co/docs/diffusers/quicktour",
            source="official-docs",
            type="documentation",
            language="en",
            difficulty="beginner",
            concepts=["diffusers", "pipeline", "sampling", "image generation"],
            learning_key_points=[
                "Run a pretrained diffusion pipeline before implementing the toy version.",
                "Understand what a production pipeline abstracts away.",
            ],
            focus_areas=["tooling", "validation", "deployment"],
            estimated_minutes=60,
            trust_score=0.86,
            why_recommended="Gives a fast local validation route and shows the difference between toy and production workflows.",
            license_or_access_note="Official public Hugging Face documentation.",
            critical_path_role="practice-validation",
        ),
        Resource(
            title="Mini Diffusion Project Checklist",
            url="local://mini-diffusion-project-checklist",
            source="generated",
            type="template",
            language="en",
            difficulty="beginner",
            concepts=["project validation", "experiment log", "image samples", "critique"],
            learning_key_points=[
                "Train or run a minimal diffusion experiment and record evidence.",
                "Explain which parts came from theory, code, and tool documentation.",
            ],
            focus_areas=["artifact", "mastery evidence", "reproduction"],
            estimated_minutes=75,
            trust_score=0.8,
            why_recommended="Makes the field route finish with an inspectable project artifact instead of passive reading.",
            license_or_access_note="Generated local demo checklist.",
            critical_path_role="practice-validation",
        ),
    ]


def _materialize_demo_resources(source_dir: Path, resources: list[Resource]) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    for index, resource in enumerate(resources, start=1):
        target = source_dir / f"{index:02d}-{_demo_slug(resource.title)}.md"
        target.write_text(_render_demo_resource_note(resource), encoding="utf-8")
        resource.local_path = str(target)
        resource.license_or_access_note = (
            f"{resource.license_or_access_note} Demo export includes a local note file so the zero-setup report works offline."
        )


def _demo_slug(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()[:80] or "resource"


def _render_demo_resource_note(resource: Resource) -> str:
    lines = [
        f"# {resource.title}",
        "",
        "This is a local demo note generated by fields-study-flow so the sample report has an offline study bundle.",
        "",
        f"- Original link: {resource.url}",
        f"- Source: {resource.source}",
        f"- Type: {resource.type}",
        f"- Why it is in the demo: {resource.why_recommended}",
        "",
    ]
    for heading, values in (
        ("Concepts", resource.concepts),
        ("Learning key points", resource.learning_key_points),
        ("Focus areas", resource.focus_areas),
    ):
        if not values:
            continue
        lines.extend([f"## {heading}", ""])
        lines.extend(f"- {value}" for value in values)
        lines.append("")
    paper_metadata = resource.metadata.get("paper_metadata") if isinstance(resource.metadata, dict) else None
    if isinstance(paper_metadata, dict):
        abstract = paper_metadata.get("abstract_snippet")
        if abstract:
            lines.extend(["## Target Paper Abstract Snippet", "", str(abstract), ""])
        for heading, key in (
            ("Method hints", "method_hints"),
            ("Experiment hints", "experiment_hints"),
            ("Limitation hints", "limitations_hints"),
        ):
            values = [str(item) for item in paper_metadata.get(key, []) if str(item)]
            if not values:
                continue
            lines.extend([f"## {heading}", ""])
            lines.extend(f"- {value}" for value in values)
            lines.append("")
    lines.extend(
        [
            "## Suggested evidence to collect",
            "",
            "- Explain the resource in your own words.",
            "- Link it back to the Paper Map node it supports.",
            "- Record one note, equation, code pointer, or limitation you can verify later.",
            "",
        ]
    )
    return "\n".join(lines)


def _infer_resource_dir_from_roadmap(roadmap_path: Path) -> Path | None:
    if not roadmap_path.exists():
        return None
    parent = roadmap_path.parent
    candidates = [
        parent / "study_resources",
        parent / "study-assets",
        parent.parent / "study-assets" / parent.name,
    ]
    parts = list(parent.parts)
    if "study-reports" in parts:
        index = parts.index("study-reports")
        candidates.append(Path(*parts[:index], "study-assets", *parts[index + 1 :]))
    for candidate in candidates:
        if (candidate / ".rag_index" / "manifest.json").exists():
            return candidate
    return None


def _export(args: argparse.Namespace) -> int:
    source = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    data = json.loads(source.read_text(encoding="utf-8"))
    from fields_study_flow.roadmap import sanitize_roadmap_for_export

    data = sanitize_roadmap_for_export(data)
    targets: list[Path] = []
    if args.format == "json":
        target = output_dir / "roadmap.json"
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        targets.append(target)
    elif args.format in {"markdown", "svg", "html", "all"}:
        from fields_study_flow.artifact_templates import write_artifact_template
        from fields_study_flow.frontend_report import render_report_index
        from fields_study_flow.roadmap import render_html, render_markdown, render_svg

        if args.format in {"markdown", "all"}:
            target = output_dir / "roadmap.md"
            target.write_text(render_markdown(data), encoding="utf-8")
            targets.append(target)
        if args.format in {"svg", "all"}:
            target = output_dir / "roadmap.svg"
            target.write_text(render_svg(data), encoding="utf-8")
            targets.append(target)
        if args.format in {"html", "all"}:
            target = output_dir / "roadmap.html"
            target.write_text(render_html(data), encoding="utf-8")
            targets.append(target)
        if args.format == "all":
            target = output_dir / "index.html"
            target.write_text(render_report_index(data), encoding="utf-8")
            targets.append(target)
            target = output_dir / "roadmap.json"
            target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            targets.append(target)
        write_artifact_template(output_dir, data)
        if data.get("generated_artifacts"):
            targets.append(output_dir / "artifact_template")
    else:
        target = output_dir / "anki.csv"
        cards = ["front,back"]
        for phase in data.get("phases", []):
            for resource in phase.get("resources", []):
                cards.append(f"\"{resource['title']}\",\"{resource['why_recommended']}\"")
        target.write_text("\n".join(cards) + "\n", encoding="utf-8")
        targets.append(target)
    for target in targets:
        print(target.resolve())
    return 0


def _parse_sources(value: str) -> set[str]:
    if value == "auto":
        return set()
    aliases = {
        "pwc": "papers-with-code",
        "paperswithcode": "papers-with-code",
        "hf": "hugging-face",
        "huggingface": "hugging-face",
        "bili": "bilibili",
    }
    output: set[str] = set()
    for item in value.split(","):
        source = item.strip()
        if source:
            output.add(aliases.get(source.lower(), source))
    return output


def _parse_levels(values: list[str]) -> dict[str, str]:
    levels: dict[str, str] = {}
    for value in values:
        if "=" in value:
            key, level = value.split("=", 1)
            levels[key.strip()] = level.strip()
    return levels


def _filter_resources_by_sources(resources: list[Resource], selected_sources: set[str], registry: SourceRegistry) -> list[Resource]:
    allowed = set(selected_sources)
    for source_id in selected_sources:
        source = registry.sources.get(source_id)
        if not source:
            continue
        allowed.add(source.category)
        if source.category == "course" or source.category.startswith("course-"):
            allowed.add("course")
        if source.category == "video" or source.category.startswith("video-"):
            allowed.add("video")
        if source.category == "academic":
            allowed.add(source.id)
    return [resource for resource in resources if resource.source in allowed]


def _paper_resource_from_url(url: str, *, live: bool = True) -> Resource:
    metadata = resolve_paper_metadata(url, live=live)
    return paper_metadata_to_resource(metadata)


def _paper_support_query(goal: str, target_resource: Resource, url: str) -> str:
    metadata = target_resource.metadata.get("paper_metadata", {})
    public_terms = [
        goal,
        target_resource.title,
        " ".join(str(concept) for concept in target_resource.concepts if concept != "paper reading"),
        " ".join(str(section) for section in metadata.get("sections", [])[:4]),
        _public_paper_identifier(url),
    ]
    return " ".join(term for term in public_terms if term).strip()


def _paper_topic_hint(url: str) -> str:
    lowered = url.lower()
    if "1706.03762" in lowered or "attention" in lowered:
        return "transformer"
    if "diffusion" in lowered:
        return "diffusion"
    if "ppo" in lowered or "trpo" in lowered:
        return "ppo"
    return ""


if __name__ == "__main__":
    raise SystemExit(main())
