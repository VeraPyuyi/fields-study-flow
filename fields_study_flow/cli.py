from __future__ import annotations

import argparse
import json
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


PLANNER_PRESETS: dict[str, dict[str, str]] = {
    "fastest": {"route_depth": "fastest", "learning_style": "practical"},
    "balanced": {"route_depth": "balanced", "learning_style": "practical"},
    "complete": {"route_depth": "complete", "learning_style": "theory"},
    "paper-fastest": {"target_kind": "paper", "route_depth": "fastest", "learning_style": "practical"},
    "paper-deep": {"target_kind": "paper", "route_depth": "complete", "learning_style": "theory"},
    "field-project": {"target_kind": "field", "route_depth": "balanced", "learning_style": "practical"},
    "course-complete": {"target_kind": "course", "route_depth": "complete", "learning_style": "theory"},
}


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
    if not getattr(args, "no_paper_lens", False):
        return roadmap
    updated = dict(roadmap)
    updated["paper_lens_disabled"] = True
    updated.pop("paper_lens", None)
    outputs = updated.get("outputs")
    if isinstance(outputs, list):
        updated["outputs"] = [item for item in outputs if item != "paper_lens.html"]
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
    return f"{goal}: {target_name}"


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
