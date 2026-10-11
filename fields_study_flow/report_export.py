"""Offline report writing shared by CLI and MCP entry points."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from fields_study_flow import frontend_report
from fields_study_flow.artifact_templates import write_artifact_template
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.paper_lens import render_paper_lens_html
from fields_study_flow.paper_map import render_paper_map_html
from fields_study_flow.visual_audit import write_report_audit


REPORT_FILES = {
    "index_html": "index.html",
    "report_audit_json": "report_audit.json",
    "roadmap_json": "roadmap.json",
    "roadmap_md": "roadmap.md",
    "study_cards_md": "study_cards.md",
    "study_quiz_md": "study_quiz.md",
    "mastery_worksheet_md": "mastery_worksheet.md",
    "quick_brief_md": "quick_brief.md",
    "evidence_coverage_md": "evidence_coverage.md",
    "evidence_coverage_html": "evidence_coverage.html",
    "roadmap_svg": "roadmap.svg",
    "roadmap_html": "roadmap.html",
}


def export_report(
    output_dir: Path | str,
    roadmap: dict[str, Any],
    *,
    profile: LearnerProfile | None = None,
    ranked_resources: list[Resource] | None = None,
    source_registry_snapshot: dict[str, Any] | None = None,
    paper_lens_options: dict[str, Any] | None = None,
    paper_map_options: dict[str, Any] | None = None,
) -> dict[str, str]:
    """Write an existing snapshot without fetching sources or explaining again.

    Option dictionaries contain only explicitly requested overrides. Prepared
    views retain their content and model answers; legacy missing views may be
    filled by the local builders.
    """
    # Imported here because roadmap.write_outputs delegates back to this module.
    from fields_study_flow import roadmap as reports

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    working = copy.deepcopy(roadmap)
    _apply_options(working, "paper_lens", paper_lens_options)
    _apply_options(working, "paper_map", paper_map_options)
    for view, ensure in (("paper_lens", reports._ensure_paper_lens), ("paper_map", reports._ensure_paper_map)):
        if working.get(view + "_disabled"):
            working.pop(view, None)
        elif not working.get(view):
            working = ensure(working)
    from fields_study_flow.workbench import bind_workbench_links, project_prepared_views

    if any(value is not None for options in (paper_lens_options, paper_map_options) for value in (options or {}).values()):
        working = project_prepared_views(working)
    working = bind_workbench_links(working)
    public = reports.sanitize_roadmap_for_export(working)
    outputs = list(public.get("outputs", []))
    if "index.html" not in outputs:
        outputs.insert(0, "index.html")
    if "report_audit.json" not in outputs:
        outputs.insert(outputs.index("index.html") + 1, "report_audit.json")
    for name in REPORT_FILES.values():
        if name not in outputs:
            outputs.append(name)
    for view in ("paper_map", "paper_lens"):
        name = view + ".html"
        if public.get(view) and name not in outputs:
            outputs.append(name)
    public["outputs"] = outputs
    reports._remove_obsolete_html_reports(output)
    if public.get("paper_lens"):
        public = reports._write_paper_lens_latex_export(output, public)
    public = reports._remove_stale_paper_reports(output, public)
    asset_base = frontend_report.copy_frontend_assets(output)

    def write_json(name: str, data: Any) -> None:
        (output / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    if profile is not None:
        write_json("learner_profile.json", reports._sanitize_private_values(profile.to_dict()))
    if ranked_resources is not None:
        write_json("resource_index.json", reports._sanitize_private_values([resource.to_dict() for resource in ranked_resources]))
        write_json("local_resource_analysis.json", reports._sanitize_private_values([
            resource.to_dict() for resource in ranked_resources if resource.source == "local-library" or resource.local_path
        ]))
    if source_registry_snapshot is not None:
        write_json("source_registry_snapshot.json", reports._sanitize_private_values(source_registry_snapshot))
    write_json("roadmap.json", public)
    renderers = {
        "roadmap.md": reports.render_markdown,
        "roadmap.svg": reports.render_svg,
        "index.html": frontend_report.render_report_index,
        "study_cards.md": frontend_report.render_study_cards_markdown,
        "study_quiz.md": frontend_report.render_study_quiz_markdown,
        "mastery_worksheet.md": frontend_report.render_mastery_worksheet_markdown,
        "quick_brief.md": frontend_report.render_quick_brief_markdown,
        "evidence_coverage.md": frontend_report.render_evidence_coverage_markdown,
        "evidence_coverage.html": frontend_report.render_evidence_coverage_html,
    }
    for name, render in renderers.items():
        (output / name).write_text(render(public), encoding="utf-8")
    for kind, fallback in (("roadmap", reports.render_html), ("paper_map", render_paper_map_html), ("paper_lens", render_paper_lens_html)):
        if kind != "roadmap" and not public.get(kind):
            continue
        html = frontend_report.render_frontend_report(kind, public, asset_base=asset_base) if asset_base else fallback(public)
        (output / (kind + ".html")).write_text(html, encoding="utf-8")
    write_artifact_template(output, public)
    write_report_audit(output, public)
    result = {key: str(output / name) for key, name in REPORT_FILES.items()}
    for view in ("paper_map", "paper_lens"):
        if public.get(view):
            result[view + "_html"] = str(output / (view + ".html"))
    if public.get("paper_lens"):
        latex = public["paper_lens"].get("latex_export", {})
        for suffix in ("tex", "pdf"):
            if latex.get(suffix + "_file"):
                result["paper_lens_" + suffix] = str(output / latex[suffix + "_file"])
    if public.get("generated_artifacts"):
        result["artifact_template"] = str(output / "artifact_template")
    return result


def _apply_options(roadmap: dict[str, Any], view: str, overrides: dict[str, Any] | None) -> None:
    explicit = {key: value for key, value in (overrides or {}).items() if value is not None}
    if not explicit:
        return
    options = roadmap.get(view + "_options")
    changed = any(value != (options if isinstance(options, dict) else {}).get(key) for key, value in explicit.items())
    roadmap[view + "_options"] = {**(options if isinstance(options, dict) else {}), **explicit}
    snapshot = roadmap.get(view)
    if not isinstance(snapshot, dict) or roadmap.get(view + "_disabled"):
        return
    if changed:
        roadmap.pop(view, None)
