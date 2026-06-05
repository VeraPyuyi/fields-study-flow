from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from git4study.language import normalize_output_language, normalize_resource_language_preference
from git4study.mcp_tools import ingestUrl
from git4study.models import LearnerProfile, Resource
from git4study.offline_catalog import offline_resources_for_goal
from git4study.ranking import rank_resources
from git4study.roadmap import build_roadmap, write_outputs
from git4study.sources import SourceRegistry


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "roadmap":
        return _roadmap(args)
    if args.command == "paper":
        return _paper(args)
    if args.command == "ingest-url":
        return _ingest_url(args)
    if args.command == "discover-sources":
        return _discover_sources(args)
    if args.command == "export":
        return _export(args)
    parser.print_help()
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="git4study", description="Generate AI/CS learning roadmaps from multi-source resources.")
    subparsers = parser.add_subparsers(dest="command")

    roadmap = subparsers.add_parser("roadmap", help="Generate a learning roadmap.")
    roadmap.add_argument("--goal", required=True)
    roadmap.add_argument("--sources", default="auto")
    roadmap.add_argument("--output-language", default="zh-CN")
    roadmap.add_argument("--resource-language", default="balanced")
    roadmap.add_argument("--known-topic", action="append", default=[])
    roadmap.add_argument("--level", action="append", default=[], help="Domain level as domain=beginner|familiar|advanced")
    roadmap.add_argument("--weekly-hours", type=int)
    roadmap.add_argument("--target-date")
    roadmap.add_argument("--output-dir", default="git4study-output")
    roadmap.add_argument("--offline", action="store_true", help="Use the bundled deterministic resource catalog. This is the MVP default.")

    paper = subparsers.add_parser("paper", help="Generate a paper deep-reading roadmap.")
    paper.add_argument("--url", required=True)
    paper.add_argument("--goal", default="fully understand, derive, and reproduce the paper")
    paper.add_argument("--with-videos", action="store_true")
    paper.add_argument("--output-language", default="zh-CN")
    paper.add_argument("--resource-language", default="balanced")
    paper.add_argument("--output-dir", default="git4study-paper-output")

    ingest = subparsers.add_parser("ingest-url", help="Parse a user-provided resource URL at metadata level.")
    ingest.add_argument("url")
    ingest.add_argument("--source-hint")

    discover = subparsers.add_parser("discover-sources", help="List source adapters for a goal and language policy.")
    discover.add_argument("--goal", required=True)
    discover.add_argument("--language", default="balanced")
    discover.add_argument("--source-policy", default="open", choices=["open", "all"])

    export = subparsers.add_parser("export", help="Export an existing roadmap JSON.")
    export.add_argument("--input", default="git4study-output/roadmap.json")
    export.add_argument("--format", choices=["markdown", "json", "anki"], default="json")
    export.add_argument("--output-dir", default="git4study-export")

    return parser


def _roadmap(args: argparse.Namespace) -> int:
    profile = LearnerProfile(
        goal=args.goal,
        output_language=normalize_output_language(args.output_language),
        resource_language_preference=normalize_resource_language_preference(args.resource_language),
        known_topics=args.known_topic,
        levels=_parse_levels(args.level),
        weekly_hours=args.weekly_hours,
        target_date=args.target_date,
    )
    registry = SourceRegistry.default()
    if not args.offline:
        print("Live API connectors are not enabled in this MVP; using the bundled deterministic catalog.", file=sys.stderr)
    resources = offline_resources_for_goal(args.goal)
    selected_sources = _parse_sources(args.sources)
    if selected_sources:
        resources = _filter_resources_by_sources(resources, selected_sources, registry)
    ranked = rank_resources(resources, profile)
    roadmap = build_roadmap(profile, ranked)
    write_outputs(Path(args.output_dir), profile, ranked, roadmap, registry.snapshot())
    print(Path(args.output_dir).resolve())
    return 0


def _paper(args: argparse.Namespace) -> int:
    profile = LearnerProfile(
        goal=f"{args.goal}: {args.url}",
        output_language=normalize_output_language(args.output_language),
        resource_language_preference=normalize_resource_language_preference(args.resource_language),
        levels={"paper_reading": "beginner"},
    )
    registry = SourceRegistry.default()
    resources = [_paper_resource_from_url(args.url)]
    resources.extend(offline_resources_for_goal(f"{args.goal} {args.url} {_paper_topic_hint(args.url)}"))
    if not args.with_videos:
        resources = [resource for resource in resources if resource.type != "video"]
    ranked = rank_resources(resources, profile)
    roadmap = build_roadmap(profile, ranked)
    write_outputs(Path(args.output_dir), profile, ranked, roadmap, registry.snapshot())
    print(Path(args.output_dir).resolve())
    return 0


def _ingest_url(args: argparse.Namespace) -> int:
    print(json.dumps(ingestUrl(args.url, args.source_hint), ensure_ascii=False, indent=2))
    return 0


def _discover_sources(args: argparse.Namespace) -> int:
    registry = SourceRegistry.default()
    sources = registry.discover(language_preference=args.language, source_policy=args.source_policy)
    print(json.dumps([source.to_dict() for source in sources], ensure_ascii=False, indent=2))
    return 0


def _export(args: argparse.Namespace) -> int:
    source = Path(args.input)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.format == "json":
        target = output_dir / "roadmap.json"
        target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    elif args.format == "markdown":
        data = json.loads(source.read_text(encoding="utf-8"))
        from git4study.roadmap import render_markdown

        target = output_dir / "roadmap.md"
        target.write_text(render_markdown(data), encoding="utf-8")
    else:
        data = json.loads(source.read_text(encoding="utf-8"))
        target = output_dir / "anki.csv"
        cards = ["front,back"]
        for phase in data.get("phases", []):
            for resource in phase.get("resources", []):
                cards.append(f"\"{resource['title']}\",\"{resource['why_recommended']}\"")
        target.write_text("\n".join(cards) + "\n", encoding="utf-8")
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


def _paper_resource_from_url(url: str) -> Resource:
    hint = _paper_topic_hint(url)
    title = "Target paper"
    concepts: list[str] = ["paper reading"]
    if "1706.03762" in url:
        title = "Attention Is All You Need"
        concepts.extend(["transformer", "self attention"])
    elif hint:
        concepts.append(hint)
    return Resource(
        title=title,
        url=url,
        source="arxiv" if "arxiv.org" in url else "user-paper",
        type="paper",
        language="en",
        difficulty="advanced",
        concepts=concepts,
        estimated_time="4-8h",
        trust_score=0.95 if "arxiv.org" in url else 0.7,
        why_recommended="Target paper for the deep-reading route.",
        license_or_access_note="User-provided paper URL. Link and summarize; do not copy long copyrighted passages.",
        metadata={"target_paper": True},
    )


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
