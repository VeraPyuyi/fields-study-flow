from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
from hashlib import sha1
from html import escape
from pathlib import Path
from typing import Any


PRIVATE_PATH_RE = re.compile(r"(?:file://[^\s)\]}\"'<]+|(?<![A-Za-z0-9])[A-Za-z]:[\\/][^)\]}\"'<\r\n]+|/(?:Users|home)/[^)\]}\"'<\r\n]+)")

SECTION_SPECS = [
    {
        "kind": "abstract",
        "title_en": "Paper in one pass",
        "title_zh": "一遍读懂论文",
        "metadata_key": "abstract_snippet",
        "annotation_type": "supporting",
        "terms": {"abstract", "problem", "contribution", "overview", "goal", "planning", "paper"},
    },
    {
        "kind": "background",
        "title_en": "Background bridge",
        "title_zh": "背景与前置知识",
        "metadata_key": "concepts",
        "annotation_type": "prerequisite",
        "terms": {"background", "prerequisite", "concept", "pddl", "planning", "chain", "thought", "cot"},
    },
    {
        "kind": "method",
        "title_en": "Method and mechanism",
        "title_zh": "方法与机制",
        "metadata_key": "method_hints",
        "annotation_type": "supporting",
        "terms": {"method", "approach", "model", "algorithm", "framework", "trace", "pddl", "planning", "action", "precondition"},
    },
    {
        "kind": "formula",
        "title_en": "Formula or derivation",
        "title_zh": "公式与推导",
        "metadata_key": "formula_candidates",
        "annotation_type": "derivation",
        "terms": {"formula", "derive", "derivation", "equation", "objective", "loss", "planner", "symbolic"},
    },
    {
        "kind": "experiment",
        "title_en": "Experiment and reproduction",
        "title_zh": "实验与复现",
        "metadata_key": "experiment_hints",
        "annotation_type": "implementation",
        "terms": {"experiment", "evaluation", "benchmark", "result", "reproduce", "code", "validity", "dataset"},
    },
    {
        "kind": "limitation",
        "title_en": "Limitations and critique",
        "title_zh": "局限与批判",
        "metadata_key": "limitations_hints",
        "annotation_type": "critique",
        "terms": {"limitation", "failure", "future", "cost", "boundary", "critique", "coverage", "risk"},
    },
    {
        "kind": "related_work",
        "title_en": "Related work map",
        "title_zh": "相关工作地图",
        "metadata_key": "keywords",
        "annotation_type": "compare",
        "terms": {"related", "paper", "survey", "citation", "compare", "planning", "cot", "benchmark"},
    },
]

ANNOTATION_TYPE_LABELS = {
    "prerequisite": ("Prerequisite", "前置知识"),
    "supporting": ("Supporting evidence", "支撑资料"),
    "derivation": ("Derivation help", "推导辅助"),
    "implementation": ("Implementation resource", "实现/实验"),
    "critique": ("Critique lens", "批判视角"),
    "compare": ("Comparison", "对比资料"),
}

PAPER_LENS_DENSITY_LIMITS = {
    "key": 8,
    "section": 48,
    "dense": 120,
}

SECTION_KIND_TERMS = {
    "abstract": {"abstract", "overview", "contribution", "problem", "summary"},
    "background": {"introduction", "background", "preliminaries", "related", "motivation"},
    "method": {"method", "approach", "framework", "algorithm", "pddl-instruct", "trace", "instruction"},
    "formula": {"formula", "equation", "objective"},
    "experiment": {"experiment", "evaluation", "benchmark", "planbench", "result", "validity", "validation"},
    "limitation": {"limitation", "future", "failure", "cost", "coverage", "broader impact"},
    "related_work": {"related work", "citation", "compare", "prior"},
}

EXPLANATION_PROVIDER = {"mode": "local", "llm_extension_ready": True}


def has_target_paper(roadmap: dict[str, Any]) -> bool:
    return bool(_target_resource(roadmap))


def build_paper_lens(
    roadmap: dict[str, Any],
    *,
    paper_lens_language: str = "auto",
    paper_lens_density: str = "dense",
) -> dict[str, Any]:
    private_roadmap = copy.deepcopy(roadmap)
    private_target = _target_resource(private_roadmap)
    safe_roadmap = _sanitize(copy.deepcopy(roadmap))
    target = _target_resource(safe_roadmap)
    if not target:
        return {}
    language = _resolve_lens_language(paper_lens_language, safe_roadmap)
    density = _normalize_density(paper_lens_density)
    paper_metadata = _paper_metadata(target)
    private_metadata = _paper_metadata(private_target)
    bundle_lookup = _bundle_lookup(safe_roadmap.get("study_bundle", {}))
    resource_lookup = _resource_lookup(safe_roadmap)
    task_lookup = _task_lookup(safe_roadmap.get("study_tasks", []))
    evidence_chunks = _evidence_chunks(safe_roadmap)
    target_bundle = _bundle_for_resource(target, bundle_lookup)
    target_paper = _target_paper_summary(target, paper_metadata, target_bundle)
    sections: list[dict[str, Any]] = []
    for index, spec in enumerate(SECTION_SPECS, start=1):
        summary = _section_summary(spec, paper_metadata, language)
        key_points = _section_key_points(spec, paper_metadata)
        section = {
            "id": f"section-{spec['kind']}",
            "kind": spec["kind"],
            "title": _section_title(spec, language),
            "source_label": spec["title_en"],
            "summary": summary,
            "key_points": key_points,
            "annotations": _section_annotations(
                spec,
                summary,
                key_points,
                evidence_chunks,
                resource_lookup,
                bundle_lookup,
                task_lookup,
                target_title=target_paper["title"],
            ),
        }
        if not section["annotations"]:
            section["no_evidence_note"] = _label(language, "no_evidence")
        sections.append(section)
    reading_recommendations = _reading_recommendations(sections, language)
    segments = _paper_segments(private_target or target, private_metadata or paper_metadata, sections, language, density)
    inline_explanations = _inline_explanations(segments, sections, language)
    annotation_count = sum(len(section["annotations"]) for section in sections)
    local_link_count = sum(1 for section in sections for item in section["annotations"] if item.get("local_href"))
    if target_paper.get("local_href"):
        local_link_count += 1
    return _sanitize(
        {
            "version": 1,
            "mode": "single-target",
            "future_modes": ["multi-target-compare"],
            "output_language": language,
            "title": _lens_title(target_paper["title"], language),
            "target_papers": [target_paper],
            "sections": sections,
            "reading_recommendations": reading_recommendations,
            "segments": segments,
            "inline_explanations": inline_explanations,
            "explanation_provider": dict(EXPLANATION_PROVIDER),
            "explanation_summary": {
                "language": language,
                "density": density,
                "segments": len(segments),
                "inline_explanations": len(inline_explanations),
                "fallback": not bool(_paper_source_text(private_target or target, private_metadata or paper_metadata)),
            },
            "summary": {
                "sections": len(sections),
                "annotations": annotation_count,
                "local_links": local_link_count,
                "evidence_backed_sections": sum(1 for section in sections if section["annotations"]),
            },
        }
    )


def render_paper_lens_html(roadmap: dict[str, Any]) -> str:
    safe_roadmap = _sanitize(copy.deepcopy(roadmap))
    lens = safe_roadmap.get("paper_lens") if isinstance(safe_roadmap.get("paper_lens"), dict) else {}
    if not lens:
        lens = build_paper_lens(safe_roadmap)
    if not lens:
        language = str(safe_roadmap.get("profile", {}).get("output_language", "zh-CN"))
        return _empty_html(language)
    language = str(lens.get("output_language") or safe_roadmap.get("profile", {}).get("output_language", "zh-CN"))
    target = (lens.get("target_papers") or [{}])[0]
    title = str(lens.get("title") or _label(language, "reader_title"))
    sections = [section for section in lens.get("sections", []) if isinstance(section, dict)]
    segments = [segment for segment in lens.get("segments", []) if isinstance(segment, dict)]
    explanations = [item for item in lens.get("inline_explanations", []) if isinstance(item, dict)]
    recommendations = [item for item in lens.get("reading_recommendations", []) if isinstance(item, dict)]
    section_nav = "".join(_section_nav_button(section, index) for index, section in enumerate(sections))
    quick_overview = _quick_overview_panel(sections, language)
    quick_segment_reader = _segment_reader(_key_segments(segments, limit=8), explanations, language, compact=True)
    segment_reader = _segment_reader(segments, explanations, language)
    section_cards = "".join(_section_card(section, language) for section in sections)
    recommendation_panel = _recommendations_panel(recommendations, language)
    annotation_cards = "".join(
        _annotation_card(annotation, section, language)
        for section in sections
        for annotation in section.get("annotations", [])
        if isinstance(annotation, dict)
    )
    explanation_cards = "".join(_side_explanation_card(item, language, active=index == 0) for index, item in enumerate(explanations))
    detail_cards = "".join(_detail_explanation_card(item, segments, language) for item in explanations)
    filter_types = _annotation_filter_types(sections)
    filter_buttons = "".join(
        f'<button type="button" class="lens-filter-chip" data-lens-filter="{escape(kind)}">{escape(_annotation_type_label(language, kind))}</button>'
        for kind in filter_types
    )
    target_actions = _target_actions(target, language) + _latex_export_actions(lens, language)
    lens_json = json.dumps(
        {
            "storageKey": f"fields-study-flow-paper-lens:{_slug(str(target.get('title') or 'target-paper'))}",
            "sections": [section.get("id") for section in sections],
            "segments": [segment.get("id") for segment in segments],
        },
        ensure_ascii=False,
    )
    return _sanitize(
        f"""<!doctype html>
<html lang="{escape(_html_lang(language))}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{ --ink:#1b2733; --muted:#627386; --line:#dbe5ef; --paper:#fbfcfe; --blue:#245f9e; --green:#2f7d59; --gold:#a96f10; --rose:#a64253; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:#eef4f8; font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Noto Sans SC","Source Han Sans SC",Arial,sans-serif; line-height:1.62; }}
    a {{ color:var(--blue); text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .paper-lens-app {{ min-height:100vh; padding:22px; }}
    .lens-shell {{ max-width:1420px; margin:0 auto; display:grid; gap:16px; }}
    .lens-hero {{ border:1px solid var(--line); background:#fff; border-radius:10px; padding:18px; display:grid; grid-template-columns:minmax(0,1fr) auto; gap:14px; align-items:start; }}
    .lens-hero h1 {{ margin:0 0 8px; font-size:clamp(22px,3vw,34px); line-height:1.22; overflow-wrap:anywhere; }}
    .lens-meta {{ color:var(--muted); font-size:14px; overflow-wrap:anywhere; }}
    .lens-actions {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:flex-end; }}
    .lens-action, .lens-filter-chip, .section-nav-button, .view-mode-button {{ border:1px solid #c9d8e8; background:#fff; border-radius:999px; padding:8px 11px; color:var(--blue); cursor:pointer; font:inherit; font-size:13px; }}
    .lens-action.primary, .lens-filter-chip.active, .section-nav-button.active, .view-mode-button.active {{ background:var(--blue); color:#fff; border-color:var(--blue); }}
    .view-mode-switch {{ display:flex; flex-wrap:wrap; gap:8px; padding:4px; border:1px solid #d7e4ef; border-radius:999px; background:#f7fbff; }}
    .view-mode-status {{ align-self:center; border:1px solid #d7e4ef; background:#f7fbff; color:#46627f; border-radius:999px; padding:7px 10px; font-size:13px; line-height:1.25; }}
    .view-mode-status.is-deep {{ border-color:#9ec9e8; background:#edf7ff; color:var(--blue); font-weight:700; }}
    .paper-lens-app[data-mode="quick"] .deep-only {{ display:none !important; }}
    .paper-lens-app[data-mode="deep"] .quick-only {{ display:none !important; }}
    .lens-layout {{ display:grid; grid-template-columns:minmax(0,1.35fr) minmax(340px,.65fr); gap:16px; align-items:start; }}
    .lens-reading, .lens-context-panel {{ min-width:0; display:grid; gap:12px; }}
    .section-nav {{ position:sticky; top:0; z-index:2; display:flex; flex-wrap:wrap; gap:8px; padding:10px; border:1px solid var(--line); background:rgba(255,255,255,.94); border-radius:10px; backdrop-filter:blur(6px); }}
    .lens-section-card, .lens-context-card, .lens-side-card {{ min-width:0; border:1px solid var(--line); background:#fff; border-radius:10px; padding:15px; box-shadow:0 12px 26px rgba(38,68,96,.06); overflow:hidden; }}
    .lens-section-card.active {{ border-color:#8fc7ef; box-shadow:0 0 0 3px rgba(143,199,239,.22); }}
    .lens-section-card h2, .lens-context-card h3, .lens-side-card h2 {{ margin:0 0 8px; line-height:1.32; overflow-wrap:anywhere; }}
    .lens-section-card p, .lens-section-card li, .lens-context-card p, .lens-context-card li {{ overflow-wrap:anywhere; word-break:break-word; }}
    .lens-tag-row {{ display:flex; flex-wrap:wrap; gap:7px; margin:10px 0; }}
    .lens-tag {{ border:1px solid #d7e3ee; border-radius:999px; padding:3px 8px; color:#46627f; background:#f7fbff; font-size:12px; }}
    .lens-empty {{ color:var(--muted); background:#f7fafc; border:1px dashed #cbd9e6; border-radius:8px; padding:10px; }}
    .lens-context-panel {{ position:sticky; top:14px; max-height:calc(100vh - 28px); overflow:auto; }}
    .lens-filter-row {{ display:flex; flex-wrap:wrap; gap:8px; }}
    .annotation-list {{ display:grid; gap:10px; }}
    .quick-overview {{ display:grid; gap:12px; border:1px solid var(--line); background:#fff; border-radius:10px; padding:16px; box-shadow:0 12px 26px rgba(38,68,96,.06); }}
    .quick-overview h2 {{ margin:0; line-height:1.28; overflow-wrap:anywhere; }}
    .quick-overview-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }}
    .quick-overview-item {{ border:1px solid #dde8f2; background:#fbfdff; border-radius:10px; padding:12px; min-width:0; }}
    .quick-overview-item h3 {{ margin:0 0 6px; font-size:15px; line-height:1.32; overflow-wrap:anywhere; }}
    .quick-overview-item p {{ margin:0; overflow-wrap:anywhere; word-break:break-word; }}
    .quick-keywords {{ display:flex; flex-wrap:wrap; gap:7px; }}
    .segment-reader {{ display:grid; gap:10px; }}
    .segment-reader-head {{ border:1px solid var(--line); background:#fff; border-radius:10px; padding:14px; }}
    .segment-reader-head h2 {{ margin:0 0 6px; line-height:1.28; overflow-wrap:anywhere; }}
    .paper-segment-card {{ position:relative; border:1px solid #dfebf4; background:#fff; border-radius:10px; padding:10px; overflow:visible; }}
    .paper-segment-card.compact {{ padding:7px; }}
    .paper-segment-card.active {{ border-color:#7bb8e6; box-shadow:0 0 0 3px rgba(123,184,230,.2); }}
    .paper-segment-button {{ width:100%; border:0; background:#fbfdff; color:var(--ink); text-align:left; border-radius:8px; padding:12px; font:inherit; line-height:1.68; cursor:pointer; overflow-wrap:anywhere; word-break:break-word; }}
    .paper-segment-card.compact .paper-segment-button {{ padding:10px; line-height:1.52; }}
    .paper-segment-button:hover, .paper-segment-button:focus {{ outline:2px solid #9ed0f4; background:#f2f9ff; }}
    .segment-meta-row {{ display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }}
    .paper-segment-card.compact .segment-meta-row {{ display:none; }}
    .segment-popover {{ display:none; position:absolute; left:18px; right:18px; top:calc(100% - 4px); z-index:5; border:1px solid #c8dced; background:#fff; border-radius:10px; padding:12px; box-shadow:0 18px 36px rgba(24,52,78,.18); overflow-wrap:anywhere; }}
    .paper-segment-card:hover .segment-popover, .paper-segment-button:focus + .segment-popover, .segment-popover.pinned {{ display:block; }}
    .segment-popover p, .active-explanation-card p, .detail-explanation-card p {{ margin:7px 0; overflow-wrap:anywhere; word-break:break-word; }}
    .active-explanation-card[hidden] {{ display:none; }}
    .explanation-detail-grid {{ display:grid; gap:12px; }}
    .detail-explanation-card {{ min-width:0; border:1px solid var(--line); background:#fff; border-radius:10px; padding:15px; box-shadow:0 12px 26px rgba(38,68,96,.06); }}
    .detail-explanation-card:target {{ border-color:#8fc7ef; box-shadow:0 0 0 4px rgba(143,199,239,.24); }}
    .recommendation-list {{ display:grid; gap:10px; }}
    .recommendation-section {{ border:1px solid #dde8f2; background:#fbfdff; border-radius:10px; padding:12px; }}
    .recommendation-section h3 {{ margin:0 0 8px; font-size:15px; line-height:1.32; overflow-wrap:anywhere; }}
    .recommendation-links {{ display:flex; flex-wrap:wrap; gap:7px; }}
    .recommendation-link {{ display:inline-flex; align-items:center; max-width:100%; border:1px solid #cfddea; background:#fff; border-radius:999px; padding:6px 9px; font-size:13px; line-height:1.25; overflow-wrap:anywhere; word-break:break-word; }}
    .recommendation-more summary {{ cursor:pointer; color:var(--blue); font-size:13px; margin-top:8px; }}
    .lens-context-card {{ border-left:4px solid var(--blue); }}
    .lens-context-card.prerequisite {{ border-left-color:var(--green); }}
    .lens-context-card.derivation {{ border-left-color:var(--gold); }}
    .lens-context-card.implementation {{ border-left-color:#6b62c7; }}
    .lens-context-card.critique {{ border-left-color:var(--rose); }}
    .lens-context-card.compare {{ border-left-color:#5b7895; }}
    .context-head {{ display:flex; justify-content:space-between; gap:10px; align-items:start; }}
    .context-head strong {{ overflow-wrap:anywhere; }}
    .context-type {{ flex:0 0 auto; border-radius:999px; background:#eef5fb; color:#385775; padding:3px 7px; font-size:12px; }}
    .evidence-snippet {{ background:#f7fafc; border:1px solid #e0e9f2; border-radius:8px; padding:10px; margin:9px 0; color:#35495c; }}
    .context-links {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:8px; }}
    .context-links a {{ border:1px solid #cbd9e6; border-radius:8px; padding:5px 8px; background:#fbfdff; font-size:13px; }}
    .progress-row {{ display:flex; gap:8px; align-items:flex-start; margin-top:8px; color:var(--muted); font-size:13px; }}
    .progress-row input {{ width:17px; height:17px; margin-top:4px; accent-color:var(--blue); }}
    .storage-warning {{ display:none; color:#805b00; background:#fff8dc; border:1px solid #f0dd98; border-radius:8px; padding:8px; }}
    .storage-warning.show {{ display:block; }}
    @media (max-width: 980px) {{
      .paper-lens-app {{ padding:12px; }}
      .lens-hero, .lens-layout {{ grid-template-columns:1fr; }}
      .quick-overview-grid {{ grid-template-columns:1fr; }}
      .lens-actions {{ justify-content:flex-start; }}
      .lens-context-panel, .section-nav {{ position:static; max-height:none; overflow:visible; }}
      .segment-popover {{ position:static; margin-top:8px; display:none; }}
      .paper-segment-card.active .segment-popover {{ display:block; }}
    }}
  </style>
</head>
<body>
<main class="paper-lens-app" data-paper-lens-app data-mode="quick">
  <div class="lens-shell">
    <header class="lens-hero">
      <div>
        <p class="lens-meta">{escape(_label(language, "reader_eyebrow"))}</p>
        <h1>{escape(title)}</h1>
        <p class="lens-meta">{escape(str(target.get("title") or ""))}</p>
        <p class="lens-meta">{escape(_join(target.get("authors", []), _label(language, "unknown")))}</p>
      </div>
      <nav class="lens-actions">
        <div class="view-mode-switch" aria-label="{escape(_label(language, "view_mode_switch"))}">
          <button type="button" class="view-mode-button active" data-view-mode="quick" aria-pressed="true">{escape(_label(language, "quick_mode"))}</button>
          <button type="button" class="view-mode-button" data-view-mode="deep" aria-pressed="false">{escape(_label(language, "deep_mode"))}</button>
        </div>
        <span class="view-mode-status" data-view-mode-status>{escape(_label(language, "current_quick_mode"))}</span>
        {target_actions}
      </nav>
    </header>
    <section class="storage-warning" data-storage-warning>{escape(_label(language, "storage_warning"))}</section>
    <div class="lens-layout">
      <section class="lens-reading" aria-label="{escape(_label(language, "reading_flow"))}">
        <div class="quick-only">
          {quick_overview}
          {quick_segment_reader}
        </div>
        <div class="deep-only" data-deep-start>
          <nav class="section-nav" aria-label="{escape(_label(language, "section_navigation"))}">{section_nav}</nav>
          {segment_reader}
          {section_cards}
        </div>
        <section class="lens-side-card explanation-details deep-only">
          <h2>{escape(_label(language, "detail_explanations"))}</h2>
          <p class="lens-meta">{escape(_label(language, "detail_explanations_note"))}</p>
          <div class="explanation-detail-grid">{detail_cards or f'<p class="lens-empty">{escape(_label(language, "no_segments"))}</p>'}</div>
        </section>
      </section>
      <aside class="lens-context-panel" aria-label="{escape(_label(language, "context_panel"))}">
        {recommendation_panel}
        <section class="lens-side-card" data-active-explanation-panel>
          <h2>{escape(_label(language, "inline_explanation"))}</h2>
          <p class="lens-meta">{escape(_label(language, "inline_explanation_note"))}</p>
          {explanation_cards or f'<p class="lens-empty">{escape(_label(language, "no_segments"))}</p>'}
        </section>
        <section class="lens-side-card deep-only">
          <h2>{escape(_label(language, "context_panel"))}</h2>
          <p class="lens-meta" data-active-section-label>{escape(_label(language, "all_sections"))}</p>
          <div class="lens-filter-row">
            <button type="button" class="lens-filter-chip active" data-lens-filter="all">{escape(_label(language, "all_annotations"))}</button>
            {filter_buttons}
          </div>
        </section>
        <section class="annotation-list deep-only" data-annotation-list>{annotation_cards or f'<p class="lens-empty">{escape(_label(language, "no_evidence"))}</p>'}</section>
      </aside>
    </div>
  </div>
</main>
<script type="application/json" id="paper-lens-data">{_script_json_payload(lens_json)}</script>
<script>
(function () {{
  const config = JSON.parse(document.getElementById('paper-lens-data').textContent || '{{}}');
  const app = document.querySelector('[data-paper-lens-app]');
  const sectionButtons = Array.from(document.querySelectorAll('[data-section-jump]'));
  const sections = Array.from(document.querySelectorAll('[data-lens-section]'));
  const annotations = Array.from(document.querySelectorAll('[data-lens-annotation]'));
  const filters = Array.from(document.querySelectorAll('[data-lens-filter]'));
  const segmentCards = Array.from(document.querySelectorAll('[data-paper-segment-card]'));
  const segmentButtons = Array.from(document.querySelectorAll('[data-paper-segment]'));
  const explanationCards = Array.from(document.querySelectorAll('[data-explanation-card]'));
  const modeButtons = Array.from(document.querySelectorAll('[data-view-mode]'));
  const detailLinks = Array.from(document.querySelectorAll('[data-detail-link]'));
  const modeStatus = document.querySelector('[data-view-mode-status]');
  const activeLabel = document.querySelector('[data-active-section-label]');
  const modeStatusText = {{
    quick: {json.dumps(_label(language, "current_quick_mode"), ensure_ascii=False)},
    deep: {json.dumps(_label(language, "current_deep_mode"), ensure_ascii=False)}
  }};
  let activeSection = 'all';
  let activeFilter = 'all';
  let activeSegment = segmentButtons[0]?.dataset.paperSegment || '';
  let viewMode = 'quick';
  let storage = null;
  try {{
    storage = window.localStorage;
    const probe = config.storageKey + ':probe';
    storage.setItem(probe, '1');
    storage.removeItem(probe);
    viewMode = storage.getItem(config.storageKey + ':view-mode') || 'quick';
  }} catch (error) {{
    document.querySelector('[data-storage-warning]')?.classList.add('show');
    storage = null;
  }}
  function cssEscape(value) {{
    const text = String(value || '');
    if (window.CSS && typeof window.CSS.escape === 'function') return window.CSS.escape(text);
    return text.replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"');
  }}
  function setViewMode(nextMode, shouldScroll = false) {{
    viewMode = nextMode === 'deep' ? 'deep' : 'quick';
    if (app) app.setAttribute('data-mode', viewMode);
    modeButtons.forEach((button) => {{
      const isActive = button.getAttribute('data-view-mode') === viewMode;
      button.classList.toggle('active', isActive);
      button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
    }});
    if (modeStatus) {{
      modeStatus.textContent = modeStatusText[viewMode] || viewMode;
      modeStatus.classList.toggle('is-deep', viewMode === 'deep');
    }}
    if (storage) {{
      try {{ storage.setItem(config.storageKey + ':view-mode', viewMode); }} catch (error) {{}}
    }}
    if (shouldScroll && viewMode === 'deep') {{
      const deepStart = document.querySelector('[data-deep-start]') || document.querySelector('.deep-only');
      window.setTimeout(() => deepStart?.scrollIntoView({{behavior:'smooth', block:'start'}}), 20);
    }}
  }}
  function applyMode() {{
    setViewMode(viewMode, false);
  }}
  function revealHashTarget(hash, shouldScroll = true) {{
    if (!hash || hash.charAt(0) !== '#') return false;
    const id = decodeURIComponent(hash.slice(1));
    if (!id) return false;
    const target = document.getElementById(id);
    if (!target) return false;
    if (target.closest('.deep-only')) {{
      setViewMode('deep', false);
    }}
    if (shouldScroll) {{
      window.setTimeout(() => {{
        target.scrollIntoView({{behavior:'smooth', block:'start'}});
        if (typeof target.focus === 'function') target.focus({{preventScroll:true}});
      }}, 30);
    }}
    return true;
  }}
  function applyFilters() {{
    sections.forEach((section) => section.classList.toggle('active', activeSection !== 'all' && section.dataset.lensSection === activeSection));
    sectionButtons.forEach((button) => button.classList.toggle('active', button.dataset.sectionJump === activeSection));
    filters.forEach((button) => button.classList.toggle('active', button.dataset.lensFilter === activeFilter));
    segmentCards.forEach((card) => {{
      const sectionMatch = activeSection === 'all' || card.dataset.sectionRef === activeSection || card.dataset.sectionKind === activeSection.replace('section-', '');
      card.hidden = !sectionMatch;
      card.classList.toggle('active', card.dataset.segmentId === activeSegment);
    }});
    segmentButtons.forEach((button) => button.classList.toggle('active', button.dataset.paperSegment === activeSegment));
    explanationCards.forEach((card) => {{
      const isActive = card.dataset.explanationCard === activeSegment;
      card.hidden = !isActive;
    }});
    annotations.forEach((card) => {{
      const sectionMatch = activeSection === 'all' || card.dataset.sectionRef === activeSection;
      const typeMatch = activeFilter === 'all' || card.dataset.annotationType === activeFilter;
      card.hidden = !(sectionMatch && typeMatch);
    }});
    const active = sections.find((section) => section.dataset.lensSection === activeSection);
    if (activeLabel) activeLabel.textContent = active ? active.dataset.sectionTitle : {json.dumps(_label(language, "all_sections"), ensure_ascii=False)};
  }}
  sectionButtons.forEach((button) => button.addEventListener('click', () => {{
    activeSection = button.getAttribute('data-section-jump') || 'all';
    const target = document.querySelector('[data-lens-section="' + cssEscape(activeSection) + '"]');
    target?.scrollIntoView({{behavior:'smooth', block:'start'}});
    applyFilters();
  }}));
  sections.forEach((section) => section.addEventListener('click', () => {{
    activeSection = section.dataset.lensSection || 'all';
    applyFilters();
  }}));
  filters.forEach((button) => button.addEventListener('click', () => {{
    activeFilter = button.dataset.lensFilter || 'all';
    applyFilters();
  }}));
  document.addEventListener('click', (event) => {{
    const button = event.target.closest('[data-view-mode]');
    if (!button) return;
    event.preventDefault();
    setViewMode(button.getAttribute('data-view-mode') || 'quick', true);
    applyFilters();
  }});
  detailLinks.forEach((link) => link.addEventListener('click', () => {{
    window.setTimeout(() => revealHashTarget(link.hash || link.getAttribute('href') || '', true), 0);
  }}));
  window.addEventListener('hashchange', () => revealHashTarget(window.location.hash, true));
  segmentButtons.forEach((button) => button.addEventListener('click', () => {{
    activeSegment = button.dataset.paperSegment || activeSegment;
    activeSection = button.dataset.sectionRef || activeSection;
    applyFilters();
  }}));
  document.querySelectorAll('[data-progress-id]').forEach((box) => {{
    const key = config.storageKey + ':' + box.dataset.progressId;
    if (storage) box.checked = storage.getItem(key) === 'done';
    box.addEventListener('change', () => {{
      if (storage) storage.setItem(key, box.checked ? 'done' : '');
    }});
  }});
  if (!revealHashTarget(window.location.hash, true)) applyMode();
  applyFilters();
}})();
</script>
</body>
</html>"""
    )


def write_paper_lens_latex(output_dir: Path, roadmap: dict[str, Any], *, compile_pdf: bool = True) -> dict[str, Any]:
    safe_roadmap = _sanitize(copy.deepcopy(roadmap))
    lens = safe_roadmap.get("paper_lens") if isinstance(safe_roadmap.get("paper_lens"), dict) else {}
    if not lens:
        lens = build_paper_lens(safe_roadmap)
    if not lens:
        return {}
    output_dir.mkdir(parents=True, exist_ok=True)
    tex_path = output_dir / "paper_lens.tex"
    pdf_path = output_dir / "paper_lens.pdf"
    tex_path.write_text(render_paper_lens_latex({**safe_roadmap, "paper_lens": lens}), encoding="utf-8")
    metadata: dict[str, Any] = {
        "tex_file": tex_path.name,
        "pdf_file": pdf_path.name if pdf_path.exists() else "",
        "compile_status": "skipped",
        "engine": "",
    }
    if not compile_pdf:
        return metadata
    engine = _latex_engine()
    if not engine:
        metadata["compile_status"] = "missing_engine"
        metadata["warning"] = "No xelatex, lualatex, pdflatex, or tectonic executable was found."
        return metadata
    metadata["engine"] = Path(engine).name
    result = _compile_latex(tex_path, engine)
    metadata.update(result)
    if pdf_path.exists() and result.get("compile_status") == "compiled":
        metadata["pdf_file"] = pdf_path.name
    return _sanitize(metadata)


def render_paper_lens_latex(roadmap: dict[str, Any]) -> str:
    safe_roadmap = _sanitize(copy.deepcopy(roadmap))
    lens = safe_roadmap.get("paper_lens") if isinstance(safe_roadmap.get("paper_lens"), dict) else {}
    if not lens:
        lens = build_paper_lens(safe_roadmap)
    language = str(lens.get("output_language") or safe_roadmap.get("profile", {}).get("output_language") or "zh-CN")
    target = (lens.get("target_papers") or [{}])[0]
    title = str(lens.get("title") or _label(language, "reader_title"))
    sections = [section for section in lens.get("sections", []) if isinstance(section, dict)]
    segments = _key_segments([segment for segment in lens.get("segments", []) if isinstance(segment, dict)], limit=10)
    explanations = [item for item in lens.get("inline_explanations", []) if isinstance(item, dict)]
    recommendations = [item for item in lens.get("reading_recommendations", []) if isinstance(item, dict)]
    explanation_lookup = {str(item.get("segment_id")): item for item in explanations}
    overview = _latex_quick_overview(sections, language)
    key_segments = _latex_key_segments(segments, explanation_lookup, language)
    reading = _latex_recommendations(recommendations, language)
    return "\n".join(
        [
            r"\documentclass[11pt]{ctexart}",
            r"\usepackage[a4paper,margin=2cm]{geometry}",
            r"\usepackage{hyperref}",
            r"\usepackage{xcolor}",
            r"\usepackage{enumitem}",
            r"\setlist{nosep,leftmargin=1.6em}",
            r"\hypersetup{colorlinks=true,linkcolor=blue,urlcolor=blue}",
            r"\pagestyle{plain}",
            r"\begin{document}",
            rf"\title{{{_latex_escape(title)}}}",
            rf"\author{{{_latex_escape(_join(target.get('authors', []), _label(language, 'unknown')))}}}",
            r"\date{}",
            r"\maketitle",
            rf"\noindent\textbf{{{_latex_escape(_label(language, 'target_paper'))}}} {_latex_escape(str(target.get('title') or ''))}",
            "",
            overview,
            key_segments,
            reading,
            r"\end{document}",
            "",
        ]
    )


def _latex_quick_overview(sections: list[dict[str, Any]], language: str) -> str:
    section_lookup = {str(section.get("kind")): section for section in sections}
    items = [
        ("quick_problem", section_lookup.get("abstract", {})),
        ("quick_method", section_lookup.get("method", {})),
        ("quick_evidence", section_lookup.get("experiment", {})),
        ("quick_boundary", section_lookup.get("limitation", {})),
    ]
    lines = [rf"\section*{{{_latex_escape(_label(language, 'quick_overview'))}}}", r"\begin{description}"]
    for label_key, section in items:
        summary = _clip(str(section.get("summary") or _label(language, "not_available")), 420)
        lines.append(rf"\item[{_latex_escape(_label(language, label_key))}] {_latex_escape(summary)}")
    keywords = _quick_keywords(sections)
    if keywords:
        lines.append(rf"\item[{_latex_escape(_label(language, 'quick_keywords'))}] {_latex_escape(' / '.join(keywords))}")
    lines.append(r"\end{description}")
    return "\n".join(lines)


def _latex_key_segments(segments: list[dict[str, Any]], explanation_lookup: dict[str, dict[str, Any]], language: str) -> str:
    lines = [rf"\section*{{{_latex_escape(_label(language, 'key_sentence_flow'))}}}", r"\begin{enumerate}"]
    for segment in segments:
        explanation = explanation_lookup.get(str(segment.get("id")), {})
        original = _clip(str(segment.get("original_text") or ""), 360)
        plain = _clip(str(explanation.get("plain_meaning") or ""), 360)
        method = _clip(str(explanation.get("method_note") or ""), 300)
        lines.extend(
            [
                rf"\item {_latex_escape(original)}",
                rf"\begin{{itemize}}",
                rf"\item \textbf{{{_latex_escape(_label(language, 'plain_meaning'))}}} {_latex_escape(plain)}",
                rf"\item \textbf{{{_latex_escape(_label(language, 'method_note'))}}} {_latex_escape(method)}",
                rf"\end{{itemize}}",
            ]
        )
    lines.append(r"\end{enumerate}")
    return "\n".join(lines)


def _latex_recommendations(recommendations: list[dict[str, Any]], language: str) -> str:
    lines = [rf"\section*{{{_latex_escape(_label(language, 'reading_recommendations'))}}}"]
    for recommendation in recommendations[:5]:
        lines.append(rf"\subsection*{{{_latex_escape(str(recommendation.get('section_title') or ''))}}}")
        summary = str(recommendation.get("summary") or "")
        if summary:
            lines.append(_latex_escape(summary))
        lines.append(r"\begin{itemize}")
        for resource in [item for item in recommendation.get("resources", []) if isinstance(item, dict)][:3]:
            title = _latex_escape(str(resource.get("title") or _label(language, "recommended_resource")))
            href = str(resource.get("local_href") or resource.get("url") or "")
            if href and not href.startswith("local://"):
                lines.append(rf"\item \href{{{_latex_url_arg(href)}}}{{{title}}}")
            else:
                lines.append(rf"\item {title}")
        lines.append(r"\end{itemize}")
    return "\n".join(lines)


def _latex_engine() -> str:
    for candidate in ("xelatex", "lualatex", "pdflatex", "tectonic"):
        path = shutil.which(candidate)
        if path:
            return path
    return ""


def _compile_latex(tex_path: Path, engine: str) -> dict[str, Any]:
    command = [engine, "-interaction=nonstopmode", "-halt-on-error", tex_path.name]
    if Path(engine).name.lower().startswith("tectonic"):
        command = [engine, tex_path.name]
    try:
        completed = subprocess.run(
            command,
            cwd=tex_path.parent,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            timeout=90,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log_path = tex_path.with_name("paper_lens_compile.log")
        log_path.write_text(_sanitize(str(exc)), encoding="utf-8")
        return {"compile_status": "failed", "log_file": log_path.name, "warning": _sanitize(str(exc))}
    _cleanup_latex_aux(tex_path)
    if completed.returncode == 0 and tex_path.with_suffix(".pdf").exists():
        return {"compile_status": "compiled"}
    log_path = tex_path.with_name("paper_lens_compile.log")
    log_text = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    log_path.write_text(_sanitize(_clip(log_text, 12000)), encoding="utf-8")
    return {"compile_status": "failed", "log_file": log_path.name, "warning": f"LaTeX exited with code {completed.returncode}."}


def _cleanup_latex_aux(tex_path: Path) -> None:
    for suffix in (".aux", ".log", ".out", ".toc"):
        try:
            tex_path.with_suffix(suffix).unlink(missing_ok=True)
        except OSError:
            pass


def _latex_escape(value: str) -> str:
    text = str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def _latex_url_arg(value: str) -> str:
    return value.replace("\\", "/").replace("%", r"\%").replace("#", r"\#").replace(" ", "%20")


def _empty_html(language: str) -> str:
    return f"<!doctype html><html lang=\"{escape(_html_lang(language))}\"><meta charset=\"utf-8\"><title>{escape(_label(language, 'reader_title'))}</title><body>{escape(_label(language, 'no_target_paper'))}</body></html>"


def _target_resource(roadmap: dict[str, Any]) -> dict[str, Any]:
    for phase in roadmap.get("phases", []):
        for resource in phase.get("resources", []):
            if isinstance(resource, dict) and _is_target_resource(resource):
                return resource
    for resource in roadmap.get("resource_library", []):
        if isinstance(resource, dict) and _is_target_resource(resource):
            return resource
    return {}


def _is_target_resource(resource: dict[str, Any]) -> bool:
    metadata = resource.get("metadata", {})
    return bool(isinstance(metadata, dict) and metadata.get("target_paper"))


def _paper_metadata(resource: dict[str, Any]) -> dict[str, Any]:
    metadata = resource.get("metadata", {})
    if isinstance(metadata, dict) and isinstance(metadata.get("paper_metadata"), dict):
        return dict(metadata["paper_metadata"])
    return {}


def _target_paper_summary(resource: dict[str, Any], metadata: dict[str, Any], bundle_item: dict[str, Any]) -> dict[str, Any]:
    local_href = str(bundle_item.get("local_href") or resource.get("local_href") or "")
    return {
        "id": "target-1",
        "title": str(metadata.get("title") or resource.get("title") or "Target paper"),
        "authors": [str(item) for item in metadata.get("authors", []) if item],
        "abstract_snippet": str(metadata.get("abstract_snippet") or ""),
        "concepts": [str(item) for item in metadata.get("concepts", []) if item],
        "metadata_status": str(metadata.get("metadata_status") or resource.get("metadata", {}).get("metadata_status") or "partial"),
        "url": str(resource.get("url") or metadata.get("url") or ""),
        "local_href": local_href,
        "source": str(resource.get("source") or metadata.get("source") or "paper"),
    }


def _resolve_lens_language(option: str, roadmap: dict[str, Any]) -> str:
    value = str(option or "auto")
    if value in {"zh-CN", "en", "bilingual"}:
        return value
    profile = roadmap.get("profile", {}) if isinstance(roadmap.get("profile"), dict) else {}
    output_language = str(profile.get("output_language") or "")
    if output_language in {"zh-CN", "en", "bilingual"}:
        return output_language
    goal = str(profile.get("goal") or roadmap.get("title") or "")
    if re.search(r"[\u4e00-\u9fff]", goal):
        return "zh-CN"
    return "zh-CN"


def _normalize_density(value: str) -> str:
    density = str(value or "dense").strip().lower()
    return density if density in PAPER_LENS_DENSITY_LIMITS else "dense"


def _paper_segments(
    target: dict[str, Any],
    metadata: dict[str, Any],
    sections: list[dict[str, Any]],
    language: str,
    density: str,
) -> list[dict[str, Any]]:
    text = _paper_source_text(target, metadata)
    if not text:
        text = _metadata_fallback_text(metadata, language)
    raw_segments = _split_paper_segments(text)
    if not raw_segments:
        raw_segments = _split_paper_segments(_metadata_fallback_text(metadata, language))
    section_titles = {str(section.get("kind")): str(section.get("title") or "") for section in sections}
    segments: list[dict[str, Any]] = []
    for order, item in enumerate(raw_segments, start=1):
        original_text = _clip(str(item.get("text") or ""), 900)
        if not original_text:
            continue
        section_kind = str(item.get("section_kind") or _section_kind_for_text(original_text))
        segment = {
            "id": _segment_id(order, section_kind, original_text),
            "section_kind": section_kind,
            "section_title": section_titles.get(section_kind, section_kind),
            "order": order,
            "original_text": original_text,
            "source_language": _detect_text_language(original_text),
            "importance_score": _segment_importance(original_text, section_kind),
        }
        if item.get("page"):
            segment["page"] = item["page"]
        segments.append(segment)
    return _limit_segments(segments, density)


def _paper_source_text(target: dict[str, Any], metadata: dict[str, Any]) -> str:
    for key in ("text_preview", "extracted_text", "full_text_preview", "pdf_text", "raw_text"):
        value = metadata.get(key)
        if isinstance(value, list):
            text = "\n\n".join(str(item) for item in value if item)
        else:
            text = str(value or "")
        if text.strip():
            return text
    local_path = str(target.get("local_path") or metadata.get("local_path") or "")
    if local_path and not local_path.startswith("[private"):
        text = _read_lens_supported_file(local_path)
        if text:
            return text
    return ""


def _read_lens_supported_file(local_path: str, limit: int = 220000) -> str:
    try:
        path = Path(local_path)
        if local_path.startswith("file://"):
            path = Path(local_path.replace("file:///", "").replace("file://", ""))
        if not path.exists() or not path.is_file():
            return ""
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader

                reader = PdfReader(str(path))
                parts: list[str] = []
                for page_number, page in enumerate(reader.pages[:24], start=1):
                    parts.append(f"[page {page_number}]\n{page.extract_text() or ''}")
                    if sum(len(part) for part in parts) >= limit:
                        break
                return "\n".join(parts)[:limit]
            except Exception:
                return path.read_bytes()[:limit].decode("utf-8", errors="ignore")
        if suffix in {".html", ".htm"}:
            raw = path.read_text(encoding="utf-8", errors="ignore")[:limit]
            return re.sub(r"<[^>]+>", " ", raw)
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _metadata_fallback_text(metadata: dict[str, Any], language: str) -> str:
    parts: list[str] = []
    key_pairs = [
        ("abstract", "abstract_snippet"),
        ("background", "concepts"),
        ("method", "method_hints"),
        ("formula", "formula_candidates"),
        ("experiment", "experiment_hints"),
        ("limitation", "limitations_hints"),
        ("related_work", "keywords"),
    ]
    for heading, key in key_pairs:
        value = metadata.get(key)
        if isinstance(value, list):
            text = "\n".join(str(item) for item in value if item)
        else:
            text = str(value or "")
        if text.strip():
            parts.append(f"{heading}\n{text}")
    if not parts:
        parts.append(_label(language, "based_on_available_fragments"))
    return "\n\n".join(parts)


def _split_paper_segments(text: str) -> list[dict[str, Any]]:
    current_kind = "abstract"
    current_page: int | None = None
    output: list[dict[str, Any]] = []
    for raw_block in re.split(r"\n{1,}", text):
        block = _clean_segment_text(raw_block)
        if not block:
            continue
        page_match = re.match(r"^\[page\s+(\d+)\]$", block, flags=re.I)
        if page_match:
            current_page = int(page_match.group(1))
            continue
        heading_kind = _section_kind_from_heading(block)
        if heading_kind:
            current_kind = heading_kind
            continue
        for sentence in _split_sentence_units(block):
            cleaned = _clean_segment_text(sentence)
            if not _looks_like_readable_segment(cleaned):
                continue
            kind = current_kind if current_kind else _section_kind_for_text(cleaned)
            if _looks_like_formula_segment(cleaned):
                kind = "formula"
            item: dict[str, Any] = {"section_kind": kind, "text": cleaned}
            if current_page:
                item["page"] = current_page
            output.append(item)
    return output


def _split_sentence_units(block: str) -> list[str]:
    if len(block) <= 360 or _looks_like_formula_segment(block):
        return [block]
    pieces = re.split(r"(?<=[.!?。！？])\s+", block)
    merged: list[str] = []
    buffer = ""
    for piece in pieces:
        piece = piece.strip()
        if not piece:
            continue
        if len(buffer) + len(piece) < 120:
            buffer = f"{buffer} {piece}".strip()
            continue
        if buffer:
            merged.append(buffer)
        buffer = piece
    if buffer:
        merged.append(buffer)
    return merged or [block]


def _clean_segment_text(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip(" \t\r\n%")
    text = re.sub(r"(?<=\w)-\s+(?=\w)", "", text)
    return text


def _looks_like_readable_segment(text: str) -> bool:
    if not text or len(text) < 28 or len(text) > 1400:
        return False
    lowered = text.lower()
    if lowered in {"abstract", "references", "introduction"}:
        return False
    if re.match(r"^\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z ]{2,80}$", text):
        return False
    word_count = len(re.findall(r"[A-Za-z0-9_\u4e00-\u9fff]+", text))
    return word_count >= 5 or _looks_like_formula_segment(text)


def _looks_like_formula_segment(text: str) -> bool:
    return bool(any(signal in text for signal in ("=", "\\sum", "\\frac", "_{", "preconditions(", "effects(", "s_{")))


def _section_kind_from_heading(text: str) -> str:
    normalized = re.sub(r"^\d+(?:\.\d+)*\.?\s+", "", text).strip().lower()
    if len(normalized.split()) > 8:
        return ""
    if normalized in {"abstract"}:
        return "abstract"
    if any(term in normalized for term in ("related work", "literature")):
        return "related_work"
    for kind, terms in SECTION_KIND_TERMS.items():
        if any(term in normalized for term in terms):
            return kind
    return ""


def _section_kind_for_text(text: str, default: str = "background") -> str:
    lowered = text.lower()
    if _looks_like_formula_segment(text):
        return "formula"
    best_kind = default
    best_score = 0
    for kind, terms in SECTION_KIND_TERMS.items():
        score = sum(1 for term in terms if term in lowered)
        if score > best_score:
            best_kind = kind
            best_score = score
    return best_kind


def _segment_importance(text: str, section_kind: str) -> int:
    lowered = text.lower()
    base = {
        "abstract": 7,
        "method": 9,
        "formula": 9,
        "experiment": 8,
        "limitation": 8,
        "background": 6,
        "related_work": 5,
    }.get(section_kind, 5)
    signals = (
        "we propose",
        "we construct",
        "we evaluate",
        "large language model",
        "symbolic planning",
        "pddl",
        "planbench",
        "val",
        "precondition",
        "effect",
        "state transition",
        "limitation",
        "future work",
        "chain-of-thought",
    )
    score = base + sum(1 for signal in signals if signal in lowered)
    if _looks_like_formula_segment(text):
        score += 2
    return min(score, 20)


def _limit_segments(segments: list[dict[str, Any]], density: str) -> list[dict[str, Any]]:
    limit = PAPER_LENS_DENSITY_LIMITS[_normalize_density(density)]
    if len(segments) <= limit:
        return segments
    selected = sorted(segments, key=lambda item: (int(item.get("importance_score", 0)), -int(item.get("order", 0))), reverse=True)[:limit]
    selected_ids = {str(item.get("id")) for item in selected}
    return [segment for segment in segments if str(segment.get("id")) in selected_ids]


def _detect_text_language(text: str) -> str:
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_words = len(re.findall(r"[A-Za-z]{2,}", text))
    if chinese_chars > latin_words:
        return "zh-CN"
    return "en"


def _segment_id(order: int, section_kind: str, text: str) -> str:
    digest = sha1(f"{order}\n{section_kind}\n{text}".encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"seg-{order:03d}-{_slug(section_kind)}-{digest}"


def _inline_explanations(segments: list[dict[str, Any]], sections: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    section_lookup = {str(section.get("kind")): section for section in sections}
    explanations: list[dict[str, Any]] = []
    for segment in segments:
        section = section_lookup.get(str(segment.get("section_kind")), {})
        annotations = [item for item in section.get("annotations", []) if isinstance(item, dict)]
        evidence_refs = [_annotation_evidence_ref(item) for item in annotations[:3]]
        evidence_refs = [item for item in evidence_refs if item]
        explanations.append(
            _sanitize(
                {
                    "id": f"exp-{segment.get('id')}",
                    "segment_id": segment.get("id"),
                    "section_kind": segment.get("section_kind"),
                    "plain_meaning": _plain_meaning(segment, language),
                    "why_it_matters": _why_it_matters(segment, language),
                    "method_note": _method_note(segment, language),
                    "related_resources": [_related_resources_note(annotations, language)],
                    "evidence_refs": evidence_refs,
                    "detail_anchor": f"detail-{segment.get('id')}",
                    "confidence": _explanation_confidence(segment, evidence_refs),
                    "provider_payload": {
                        "mode": "local",
                        "llm_extension_ready": True,
                        "segment_id": segment.get("id"),
                        "section_kind": segment.get("section_kind"),
                    },
                }
            )
        )
    return _differentiate_inline_explanations(explanations, segments, language)


def _differentiate_inline_explanations(
    explanations: list[dict[str, Any]], segments: list[dict[str, Any]], language: str
) -> list[dict[str, Any]]:
    segment_lookup = {str(segment.get("id")): str(segment.get("original_text") or "") for segment in segments}
    for field in ("plain_meaning", "why_it_matters", "method_note"):
        seen: dict[str, int] = {}
        for explanation in explanations:
            value = str(explanation.get(field) or "")
            if not value:
                continue
            count = seen.get(value, 0)
            if count:
                cue = _segment_specific_cue(segment_lookup.get(str(explanation.get("segment_id")), ""), language)
                explanation[field] = _append_explanation_note(value, cue)
            seen[value] = count + 1
    return explanations


def _annotation_evidence_ref(annotation: dict[str, Any]) -> dict[str, Any]:
    ref = {
        "resource_title": annotation.get("resource_title") or annotation.get("title"),
        "file_name": annotation.get("file_name"),
        "snippet": annotation.get("snippet"),
        "local_href": annotation.get("local_href"),
        "url": annotation.get("url"),
    }
    return {key: value for key, value in ref.items() if value}


def _reading_recommendations(sections: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    recommendations: list[dict[str, Any]] = []
    for section in sections:
        resources: list[dict[str, Any]] = []
        seen: set[str] = set()
        for annotation in section.get("annotations", []):
            if not isinstance(annotation, dict):
                continue
            title = str(annotation.get("resource_title") or annotation.get("title") or "").strip()
            if not title:
                continue
            key = _title_key(title)
            if key in seen:
                continue
            seen.add(key)
            resources.append(
                {
                    "title": _clip(title, 120),
                    "annotation_type": annotation.get("annotation_type"),
                    "source": annotation.get("source"),
                    "resource_type": annotation.get("resource_type"),
                    "file_name": annotation.get("file_name"),
                    "local_href": annotation.get("local_href"),
                    "url": annotation.get("url"),
                    "reason": annotation.get("reason"),
                }
            )
            if len(resources) >= 4:
                break
        if not resources:
            continue
        recommendations.append(
            _sanitize(
                {
                    "section_id": section.get("id"),
                    "section_kind": section.get("kind"),
                    "section_title": section.get("title"),
                    "summary": _recommendation_summary(str(section.get("kind") or ""), language),
                    "resources": resources,
                }
            )
        )
    return recommendations


def _recommendation_summary(section_kind: str, language: str) -> str:
    summaries = {
        "abstract": (
            "Use these after the overview to anchor the paper's problem, contribution, and evaluation.",
            "读完上面的总览后，用这些资料固定论文的问题、贡献和验证方式。",
        ),
        "background": (
            "Use these only to unblock the prerequisite concepts needed by the target paper.",
            "这些资料只用来补齐会卡住目标论文阅读的前置概念。",
        ),
        "method": (
            "Use these to understand the method pipeline, assumptions, and implementation hooks.",
            "这些资料用来读通方法流程、关键假设和可实现的接口。",
        ),
        "formula": (
            "Use these to connect notation to derivation and symbolic checks.",
            "这些资料用来把符号、推导和可检查规则连起来。",
        ),
        "experiment": (
            "Use these to verify the benchmark, validation method, and reproduction evidence.",
            "这些资料用来核对基准、验证方法和复现实验证据。",
        ),
        "limitation": (
            "Use these to understand boundaries, failure modes, and what should not be over-claimed.",
            "这些资料用来理解边界、失败模式，以及哪些结论不能说过头。",
        ),
        "related_work": (
            "Use these to place the target paper among nearby work.",
            "这些资料用来把目标论文放回相关工作的脉络里。",
        ),
    }
    en, zh = summaries.get(section_kind, ("Use these resources to support the section above.", "这些资料用来支撑上面这一节的理解。"))
    if language == "en":
        return en
    if language == "bilingual":
        return f"{en} / {zh}"
    return zh


def _plain_meaning(segment: dict[str, Any], language: str) -> str:
    text = str(segment.get("original_text") or "")
    kind = str(segment.get("section_kind") or "")
    if language == "en":
        return _append_explanation_note(_english_plain_note(text, kind), _english_focus_note(text, kind))
    if language == "bilingual":
        en_note = _append_explanation_note(_english_plain_note(text, kind), _english_focus_note(text, kind))
        zh_note = _append_explanation_note(_chinese_plain_note(text, kind), _chinese_focus_note(text, kind))
        return f"{en_note} / {zh_note}"
    return _append_explanation_note(_chinese_plain_note(text, kind), _chinese_focus_note(text, kind))


def _why_it_matters(segment: dict[str, Any], language: str) -> str:
    text = str(segment.get("original_text") or "")
    kind = str(segment.get("section_kind") or "")
    if language == "en":
        return _append_explanation_note(_english_importance_note(kind), _english_importance_focus(text, kind))
    if language == "bilingual":
        en_note = _append_explanation_note(_english_importance_note(kind), _english_importance_focus(text, kind))
        zh_note = _append_explanation_note(_chinese_importance_note(kind), _chinese_importance_focus(text, kind))
        return f"{en_note} / {zh_note}"
    return _append_explanation_note(_chinese_importance_note(kind), _chinese_importance_focus(text, kind))


def _method_note(segment: dict[str, Any], language: str) -> str:
    text = str(segment.get("original_text") or "")
    if language == "en":
        return _append_explanation_note(_english_method_note(text), _english_method_focus(text))
    if language == "bilingual":
        en_note = _append_explanation_note(_english_method_note(text), _english_method_focus(text))
        zh_note = _append_explanation_note(_chinese_method_note(text), _chinese_method_focus(text))
        return f"{en_note} / {zh_note}"
    return _append_explanation_note(_chinese_method_note(text), _chinese_method_focus(text))


def _related_resources_note(annotations: list[dict[str, Any]], language: str) -> str:
    titles = _dedupe([str(item.get("resource_title") or item.get("title") or "") for item in annotations if item], limit=3)
    if language == "en":
        return ", ".join(titles) if titles else "Use the centralized recommendation panel and evidence panel first."
    if language == "bilingual":
        target = ", ".join(titles) if titles else "Use the centralized recommendation panel and evidence panel first."
        zh_target = "、".join(titles) if titles else "先看当前句段解释，再回到集中推荐和证据面板补资料。"
        return f"{target} / {zh_target}"
    return "、".join(titles) if titles else "先看当前句段解释，再回到集中推荐和证据面板补资料。"


def _append_explanation_note(base: str, extra: str) -> str:
    base = _compact_inline_text(base)
    extra = _compact_inline_text(extra)
    if not extra or extra in base:
        return base
    separator = "" if _starts_with_cjk(extra) else " "
    return f"{base.rstrip()}{separator}{extra.lstrip()}"


def _starts_with_cjk(value: str) -> bool:
    for char in value.strip():
        return "\u4e00" <= char <= "\u9fff"
    return False


def _segment_specific_cue(text: str, language: str) -> str:
    cue = _clip(_compact_inline_text(text), 72)
    if not cue:
        return ""
    if language == "en":
        return f"Specific cue: \"{cue}\"."
    if language == "bilingual":
        return f"Specific cue: \"{cue}\". / 本句具体落在：“{cue}”。"
    return f"本句具体落在：“{cue}”。"


def _chinese_focus_note(text: str, kind: str) -> str:
    lowered = text.lower()
    if "large language models struggle" in lowered or ("valid plans" in lowered and "precondition" in lowered):
        return "抓住这里：难点是让模型写出的计划能被规则验证，而不只是看起来像计划。"
    if "logical chain-of-thought" in lowered or ("trace" in lowered and "state transition" in lowered):
        return "抓住这里：推理链要把每一步状态怎么变公开写出来。"
    if "open-ended text generation" in lowered:
        return "抓住这里：规划题不像自由写作，答案空间会被动作规则和世界状态锁住。"
    if "current state contains" in lowered or "facts required" in lowered:
        return "抓住这里：下一步能不能走，取决于当前状态里有没有必需事实。"
    if "pddl-instruct" in lowered:
        return "抓住这里：数据样例把自然语言任务、PDDL 领域和逻辑推理轨迹绑在一起。"
    if "worked example" in lowered:
        return "抓住这里：trace 像老师板书，把检查前提和应用效果的过程拆给模型看。"
    if "instruction tuned" in lowered or "instruction tuning" in lowered:
        return "抓住这里：训练目标是让模型模仿这种规整的推理格式。"
    if "state transition" in lowered or "s_{t+1}" in lowered or "apply(a_t" in lowered:
        return "抓住这里：状态像棋盘一样，被合法动作一步步改写。"
    if "planbench" in lowered:
        return "抓住这里：PlanBench 是考试卷，用来测计划是否真的可执行。"
    if "val-style" in lowered or "validation checks" in lowered:
        return "抓住这里：验证器像裁判，逐步检查动作序列是否真的到达目标。"
    if "results show" in lowered or "logical traces help" in lowered:
        return "抓住这里：实验结论把“写推理轨迹”连接到“更守符号约束”。"
    if "quality and coverage" in lowered:
        return "抓住这里：训练轨迹质量不够时，方法的上限也会被拉低。"
    if "unseen" in lowered or "long-horizon" in lowered:
        return "抓住这里：新领域和长链依赖是规划模型最容易失手的地方。"
    if "self-verification" in lowered or "broaden" in lowered:
        return "抓住这里：下一步研究要让模型更会自查，也要覆盖更多 PDDL 领域。"
    if kind == "formula":
        return "抓住这里：公式在描述“动作合法才更新状态”的最小规则。"
    if kind == "limitation":
        return "抓住这里：作者在给结论划边界，提醒不要把效果外推太远。"
    focus = _clip(_compact_inline_text(text), 54)
    return f"抓住这里：这句围绕“{focus}”展开。"


def _compact_inline_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _chinese_importance_focus(text: str, kind: str) -> str:
    lowered = text.lower()
    if "open-ended text generation" in lowered:
        return "它帮你区分普通文本生成和符号规划：后者必须受规则约束。"
    if "current state contains" in lowered or "facts required" in lowered:
        return "这是逐步验证计划合法性的入口，也是很多错误最早出现的位置。"
    if "precondition" in lowered or "effect" in lowered:
        return "如果不懂前提和效果，就很难判断模型生成的计划到底错在哪里。"
    if "trace" in lowered or "chain-of-thought" in lowered:
        return "这决定论文的核心主张：可检查的推理过程本身就是训练信号。"
    if "pddl-instruct" in lowered:
        return "这是方法落地的关键数据桥梁，后面的复现也要围绕它展开。"
    if "instruction tuned" in lowered or "instruction tuning" in lowered:
        return "它说明改进来自训练目标和数据格式，而不只是提示词写得更长。"
    if "state transition" in lowered or "s_{t+1}" in lowered:
        return "它是把规划过程写成可执行更新规则的关键一步。"
    if "results show" in lowered or "logical traces help" in lowered:
        return "这是论文从方法叙述走向实验证据的地方。"
    if "planbench" in lowered or "val" in lowered or "validation" in lowered:
        return "它把“看起来合理”变成“按规则可验收”，直接关系到实验可信度。"
    if "quality and coverage" in lowered or "unseen" in lowered or "long-horizon" in lowered:
        return "这些边界决定你汇报时哪些结论能说，哪些必须谨慎说。"
    if kind == "formula":
        return "它让你能把方法从口头理解推进到可推导、可实现的层面。"
    return ""


def _chinese_method_focus(text: str) -> str:
    lowered = text.lower()
    if "precondition" in lowered and "effect" in lowered:
        return "实操时可以把每个动作拆成两列：执行前必须满足什么，执行后会新增或删除什么。"
    if "current state contains" in lowered:
        return "读的时候把 current state 当成一张事实清单，逐项勾选下一步动作需要的条件。"
    if "pddl-instruct" in lowered:
        return "复现时先准备任务描述和 PDDL domain，再生成或标注每一步逻辑 trace。"
    if "worked example" in lowered:
        return "把它当成给模型看的标准解题过程，而不是给人看的随笔式解释。"
    if "instruction tuned" in lowered:
        return "训练数据的格式要稳定，否则模型学到的可能只是文字风格而不是检查流程。"
    if "planbench" in lowered or "val" in lowered:
        return "复现实验时要保留可执行性检查日志，不能只记录文本相似度。"
    if "long-horizon" in lowered:
        return "长步数任务要额外看错误是早期条件没满足，还是后面状态滚动出了偏差。"
    return ""


def _english_focus_note(text: str, kind: str) -> str:
    lowered = text.lower()
    if "large language models struggle" in lowered or ("valid plans" in lowered and "precondition" in lowered):
        return "Focus: the difficulty is not fluent text, but rule-valid plans."
    if "logical chain-of-thought" in lowered or ("trace" in lowered and "state transition" in lowered):
        return "Focus: the trace exposes how each state changes."
    if "open-ended text generation" in lowered:
        return "Focus: planning is constrained by world states and action rules."
    if "current state contains" in lowered:
        return "Focus: an action is allowed only when the current facts support it."
    if "pddl-instruct" in lowered:
        return "Focus: the dataset binds natural language tasks, PDDL domains, and logical traces."
    if "worked example" in lowered:
        return "Focus: the trace is a worked solution, not just a final answer."
    if "instruction tuned" in lowered:
        return "Focus: tuning teaches a stable reasoning format."
    if "state transition" in lowered or "s_{t+1}" in lowered:
        return "Focus: legal actions update the state step by step."
    if "planbench" in lowered:
        return "Focus: PlanBench tests whether plans are actually executable."
    if "val-style" in lowered or "validation checks" in lowered:
        return "Focus: the validator plays referee for the action sequence."
    if "quality and coverage" in lowered or "unseen" in lowered or "long-horizon" in lowered:
        return "Focus: the result should not be over-generalized beyond covered domains."
    if kind == "formula":
        return "Focus: the formula states the minimal rule for updating state."
    return ""


def _english_importance_focus(text: str, kind: str) -> str:
    lowered = text.lower()
    if "open-ended text generation" in lowered:
        return "It separates free-form generation from rule-bound planning."
    if "current state contains" in lowered or "facts required" in lowered:
        return "It is the entry point for checking whether each step is legal."
    if "precondition" in lowered or "effect" in lowered:
        return "Without this, plan errors cannot be diagnosed."
    if "trace" in lowered or "chain-of-thought" in lowered:
        return "It is the paper's main training signal."
    if "pddl-instruct" in lowered:
        return "It is the data bridge needed for reproduction."
    if "instruction tuned" in lowered or "instruction tuning" in lowered:
        return "It ties the gain to training data and objectives, not just prompting."
    if "state transition" in lowered or "s_{t+1}" in lowered:
        return "It makes planning implementable as a checked state update."
    if "results show" in lowered or "logical traces help" in lowered:
        return "It connects the method claim to empirical evidence."
    if "planbench" in lowered or "val" in lowered or "validation" in lowered:
        return "It turns plausibility into checkable evidence."
    if "quality and coverage" in lowered or "unseen" in lowered or "long-horizon" in lowered:
        return "It marks where claims need caution."
    if kind == "formula":
        return "It moves the method from intuition to implementation."
    return ""


def _english_method_focus(text: str) -> str:
    lowered = text.lower()
    if "precondition" in lowered and "effect" in lowered:
        return "For implementation, split every action into required facts and resulting facts."
    if "current state contains" in lowered:
        return "Read the current state as a fact checklist for the next action."
    if "pddl-instruct" in lowered:
        return "To reproduce it, pair task text with a PDDL domain and stepwise traces."
    if "worked example" in lowered:
        return "Treat the trace as a standard solution process for the model."
    if "planbench" in lowered or "val" in lowered:
        return "Keep executable validation logs, not only text scores."
    return ""


def _chinese_plain_note(text: str, kind: str) -> str:
    lowered = text.lower()
    if "precondition" in lowered or "effect" in lowered or "pddl" in lowered:
        return "它把规划问题说成一张严格的清单：每一步动作不是想写就写，必须先满足前提条件，执行后还会改变世界状态。"
    if "chain-of-thought" in lowered or "trace" in lowered:
        return "它强调的不是只给最终答案，而是把中间推理过程写成可检查的草稿，让模型学会为什么这一步能走。"
    if "planbench" in lowered or "val" in lowered or "validation" in lowered:
        return "它在说评测不能只看答案像不像计划，还要像裁判一样检查这串动作能不能真的从起点走到目标。"
    if kind == "limitation":
        return "它在提醒这个方法的边界：资料、领域或长步骤一变复杂，模型仍可能掉链子。"
    if kind == "formula":
        return "它把方法压缩成符号关系：当前状态经过某个动作，会变成下一个状态。"
    return "它是在交代论文主线中的一个关键环节：作者想让模型从“会生成文字”进一步变成“会按规则推演”。"


def _chinese_importance_note(kind: str) -> str:
    notes = {
        "abstract": "摘要句决定你先抓住论文的问题、贡献和结论，后面读方法才不会迷路。",
        "background": "这是读懂论文的地基；如果这里没通，后面的方法会像直接看答案一样跳步。",
        "method": "方法句是论文的发动机，说明作者到底怎样把想法变成可训练、可验证的流程。",
        "formula": "公式句是把直觉变成规则的地方，能推出来才算真正理解。",
        "experiment": "实验句告诉你作者如何证明方法有效，也决定你复现时要收集什么证据。",
        "limitation": "局限句帮助你判断方法什么时候可靠，什么时候只是看起来有效。",
        "related_work": "相关工作句帮你把这篇论文放回领域地图里，看清它和前人差在哪里。",
    }
    return notes.get(kind, "它是理解论文论证链的一块拼图，需要和前后句一起看。")


def _chinese_method_note(text: str) -> str:
    lowered = text.lower()
    if "state" in lowered and ("transition" in lowered or "apply" in lowered):
        return "可以把它想成棋盘走子：先看当前局面，确认这步合法，再把棋盘更新成新局面。"
    if "instruction tuned" in lowered or "instruction tuning" in lowered:
        return "可以把训练理解成给模型看大量“标准解题草稿”，让它模仿这种按规则检查的思路。"
    if "pddl" in lowered:
        return "PDDL 像机器可读的任务说明书，里面写清动作、前提和效果，模型生成的计划要接受这份说明书检查。"
    return "读这一句时要问三个问题：输入是什么、规则是什么、输出怎样被验证。"


def _english_plain_note(text: str, kind: str) -> str:
    lowered = text.lower()
    if "pddl" in lowered or "precondition" in lowered or "effect" in lowered:
        return "planning is treated as a rule-checked sequence where every action must be legal before it changes the state."
    if "chain-of-thought" in lowered or "trace" in lowered:
        return "the paper teaches the model with inspectable reasoning traces, not just final answers."
    if kind == "limitation":
        return "the method has boundaries and may fail when coverage or horizon length changes."
    return "this sentence is one link in the paper's argument about making language models reason under planning rules."


def _english_importance_note(kind: str) -> str:
    notes = {
        "method": "it explains the mechanism that turns the idea into a trainable workflow.",
        "formula": "it turns intuition into a rule that can be derived and checked.",
        "experiment": "it defines what evidence would make the claim credible.",
        "limitation": "it marks where the method should not be over-claimed.",
    }
    return notes.get(kind, "it helps anchor the paper's claim in a specific part of the argument.")


def _english_method_note(text: str) -> str:
    if "pddl" in text.lower():
        return "read it as a machine-checkable task contract: actions, preconditions, effects, and goals."
    return "ask what the input is, what rule is applied, and how the output is validated."


def _explanation_confidence(segment: dict[str, Any], evidence_refs: list[dict[str, Any]]) -> float:
    score = float(segment.get("importance_score") or 0)
    value = 0.45 + min(score, 12) / 30 + min(len(evidence_refs), 3) * 0.06
    return round(min(value, 0.95), 2)


def _section_summary(spec: dict[str, Any], metadata: dict[str, Any], language: str) -> str:
    value = metadata.get(spec["metadata_key"])
    if isinstance(value, list):
        value = " ".join(str(item) for item in value[:3] if item)
    text = str(value or "").strip()
    if text:
        return _localized_section_summary(spec, metadata, language, text)
    if spec["kind"] == "background":
        concepts = _join(metadata.get("concepts", []), "")
        if concepts:
            return _localized_section_summary(spec, metadata, language, concepts)
    return _label(language, f"fallback_{spec['kind']}")


def _localized_section_summary(spec: dict[str, Any], metadata: dict[str, Any], language: str, source_text: str) -> str:
    source = _clip(source_text, 720)
    if language == "en" or _detect_text_language(source) == "zh-CN":
        return source
    zh_summary = _chinese_section_summary(spec, metadata, source)
    if language == "bilingual":
        return _clip(f"{source} / {zh_summary}", 920)
    return zh_summary


def _chinese_section_summary(spec: dict[str, Any], metadata: dict[str, Any], source_text: str) -> str:
    kind = str(spec.get("kind") or "")
    if kind == "abstract":
        return _clip(
            f"先抓住论文主线：{_zh_problem_phrase(metadata, source_text)}；核心方法是{_zh_method_phrase(metadata, source_text)}；"
            f"{_zh_evaluation_phrase(metadata, source_text)}读完这一遍要能用自己的话说清它解决什么、怎样做、凭什么说有效。",
            720,
        )
    if kind == "background":
        return _clip(
            f"这一节只补直接卡住阅读的前置知识：{_zh_concept_phrase(metadata, source_text)}。"
            "目标不是把领域从头学一遍，而是让后面的方法、公式和实验能马上读通。",
            720,
        )
    if kind == "method":
        return _clip(
            f"这一节按流程读：输入是什么、规则怎样约束、模型怎样产生推理轨迹或计划、输出怎样被验证。"
            f"{_zh_method_phrase(metadata, source_text)}。",
            720,
        )
    if kind == "formula":
        return _clip(
            "这一节把直觉压成符号关系：先认清状态、动作、约束和更新规则，再手推一遍关键步骤。"
            f"{_zh_formula_phrase(metadata, source_text)}",
            720,
        )
    if kind == "experiment":
        return _clip(
            f"这一节重点看证据链：用什么任务评测、指标怎样定义、失败案例说明什么。{_zh_evaluation_phrase(metadata, source_text)}"
            "如果要复现，优先保存可执行性检查、输入输出样例和错误分析。",
            720,
        )
    if kind == "limitation":
        return _clip(
            f"这一节给结论划边界：{_zh_limitation_phrase(metadata, source_text)}。"
            "汇报时要把这些限制讲清楚，避免把论文结果外推到没有验证过的场景。",
            720,
        )
    if kind == "related_work":
        return _clip(
            f"这一节用来定位论文在领域里的位置：它和{_zh_concept_phrase(metadata, source_text)}相关，"
            "只优先读那些能帮助你更快理解目标论文差异、前提或复现路径的资料。",
            720,
        )
    return _clip(f"这一节围绕{_zh_concept_phrase(metadata, source_text)}展开，阅读时抓住问题、方法、证据和边界四条线。", 720)


def _zh_concept_phrase(metadata: dict[str, Any], source_text: str) -> str:
    concepts = _dedupe([str(item) for item in metadata.get("concepts", []) if item], limit=4) if isinstance(metadata.get("concepts"), list) else []
    if concepts:
        return "、".join(concepts)
    tokens = _dedupe([token for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{3,}", source_text) if token.lower() not in {"this", "that", "with", "from", "into"}], limit=4)
    return "、".join(tokens) if tokens else "目标论文的核心概念"


def _zh_problem_phrase(metadata: dict[str, Any], source_text: str) -> str:
    lowered = source_text.lower()
    if "language model" in lowered and "planning" in lowered:
        return "它要解决的是让大语言模型在规划任务中不只会写顺口的答案，还要遵守动作前提、效果和状态变化"
    if "symbolic planning" in lowered:
        return "它围绕符号规划中的合法动作、状态变化和目标达成展开"
    return f"它围绕{_zh_concept_phrase(metadata, source_text)}提出一个需要被解释和验证的问题"


def _zh_method_phrase(metadata: dict[str, Any], source_text: str) -> str:
    lowered = " ".join(
        [source_text]
        + [str(item) for item in metadata.get("method_hints", []) if item]
        + [str(item) for item in metadata.get("concepts", []) if item]
    ).lower()
    if "pddl" in lowered and ("chain-of-thought" in lowered or "trace" in lowered or "logical" in lowered):
        return "用 PDDL 任务和逻辑 CoT 轨迹做指令微调，让模型把每一步计划为什么合法写出来"
    if "instruction tuning" in lowered or "instruction tuned" in lowered:
        return "用结构化的指令微调样例教模型按固定推理流程解题"
    if "trace" in lowered:
        return "把中间推理轨迹显式写出来，让计划生成过程可检查"
    return f"围绕{_zh_concept_phrase(metadata, source_text)}组织方法流程"


def _zh_evaluation_phrase(metadata: dict[str, Any], source_text: str) -> str:
    lowered = " ".join(
        [source_text]
        + [str(item) for item in metadata.get("experiment_hints", []) if item]
        + [str(item) for item in metadata.get("keywords", []) if item]
    ).lower()
    if "planbench" in lowered or "val" in lowered or "validation" in lowered:
        return "验收时重点看 PlanBench、VAL 或 PDDL 风格检查是否证明计划真的可执行。"
    if "experiment" in lowered or "evaluation" in lowered:
        return "验收时重点看实验任务、评价指标和复现证据是否支撑结论。"
    return "验收时重点看论文给出的证据是否能支撑核心主张。"


def _zh_formula_phrase(metadata: dict[str, Any], source_text: str) -> str:
    lowered = " ".join([source_text] + [str(item) for item in metadata.get("formula_candidates", []) if item]).lower()
    if "state" in lowered or "s_t" in lowered or "s_{" in lowered:
        return "可以把它想成“当前状态经过合法动作后更新成下一个状态”。"
    return "关键是把每个符号对应回论文里的对象，而不是只记公式外形。"


def _zh_limitation_phrase(metadata: dict[str, Any], source_text: str) -> str:
    lowered = " ".join([source_text] + [str(item) for item in metadata.get("limitations_hints", []) if item]).lower()
    if "coverage" in lowered or "quality" in lowered:
        return "方法依赖训练轨迹的质量和覆盖范围"
    if "unseen" in lowered or "long-horizon" in lowered or "complex" in lowered:
        return "新领域、长步骤依赖和复杂任务仍可能让模型出错"
    return "注意论文适用的任务范围、数据条件和失败模式"


def _section_key_points(spec: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    output: list[str] = []
    for key in ("concepts", "keywords"):
        value = metadata.get(key)
        if isinstance(value, list):
            output.extend(str(item) for item in value[:4] if item)
    if spec["metadata_key"] in {"method_hints", "experiment_hints", "limitations_hints", "formula_candidates"}:
        value = metadata.get(spec["metadata_key"])
        if isinstance(value, list):
            output.extend(str(item) for item in value[:2] if item)
    return _dedupe([_clip(item, 120) for item in output], limit=6)


def _section_annotations(
    spec: dict[str, Any],
    summary: str,
    key_points: list[str],
    evidence_chunks: list[dict[str, Any]],
    resource_lookup: dict[str, dict[str, Any]],
    bundle_lookup: dict[str, dict[str, dict[str, Any]]],
    task_lookup: dict[str, list[str]],
    *,
    target_title: str,
) -> list[dict[str, Any]]:
    section_terms = set(spec["terms"]) | _tokens(summary) | _tokens(" ".join(key_points))
    annotations: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for chunk in evidence_chunks:
        resource_title = str(chunk.get("resource_title") or "")
        if resource_title and resource_title == target_title:
            continue
        if not _matches_terms(section_terms, chunk):
            continue
        annotation = _annotation_from_chunk(spec, chunk, resource_lookup, bundle_lookup, task_lookup)
        key = (annotation.get("resource_title", ""), annotation.get("snippet", ""), spec["kind"])
        if key not in seen:
            seen.add(key)
            annotations.append(annotation)
    if len(annotations) < 3:
        for resource in resource_lookup.values():
            if resource.get("title") == target_title or _is_target_resource(resource):
                continue
            if not _resource_matches(section_terms, resource):
                continue
            annotation = _annotation_from_resource(spec, resource, bundle_lookup, task_lookup)
            key = (annotation.get("resource_title", ""), annotation.get("snippet", ""), spec["kind"])
            if key not in seen:
                seen.add(key)
                annotations.append(annotation)
            if len(annotations) >= 4:
                break
    annotations.sort(key=lambda item: (_score_value(item.get("score")), 1 if item.get("local_href") else 0), reverse=True)
    return annotations[:6]


def _annotation_from_chunk(
    spec: dict[str, Any],
    chunk: dict[str, Any],
    resource_lookup: dict[str, dict[str, Any]],
    bundle_lookup: dict[str, dict[str, dict[str, Any]]],
    task_lookup: dict[str, list[str]],
) -> dict[str, Any]:
    resource_title = str(chunk.get("resource_title") or "")
    resource = resource_lookup.get(_title_key(resource_title), {})
    bundle = _bundle_for_resource(resource or {"title": resource_title, "url": chunk.get("url", "")}, bundle_lookup)
    return _sanitize(
        {
            "id": _annotation_id(spec["kind"], resource_title, str(chunk.get("chunk_id") or chunk.get("snippet") or "")),
            "annotation_type": spec["annotation_type"],
            "title": _clip(resource_title or str(chunk.get("file_name") or "Evidence"), 140),
            "resource_title": resource_title,
            "source": str(chunk.get("source") or resource.get("source") or ""),
            "resource_type": str(chunk.get("type") or resource.get("type") or ""),
            "file_name": str(chunk.get("file_name") or ""),
            "snippet": _clip(str(chunk.get("snippet") or ""), 520),
            "score": chunk.get("score"),
            "local_href": str(bundle.get("local_href") or resource.get("local_href") or ""),
            "url": str(resource.get("url") or bundle.get("url") or chunk.get("url") or ""),
            "task_ids": task_lookup.get(_title_key(resource_title), []),
            "reason": _annotation_reason(spec["kind"]),
        }
    )


def _annotation_from_resource(
    spec: dict[str, Any],
    resource: dict[str, Any],
    bundle_lookup: dict[str, dict[str, dict[str, Any]]],
    task_lookup: dict[str, list[str]],
) -> dict[str, Any]:
    title = str(resource.get("title") or "Resource")
    bundle = _bundle_for_resource(resource, bundle_lookup)
    snippet = " ".join(str(item) for item in resource.get("learning_key_points", [])[:2] if item)
    if not snippet:
        snippet = str(resource.get("why_recommended") or resource.get("focus_areas") or "")
    return _sanitize(
        {
            "id": _annotation_id(spec["kind"], title, snippet),
            "annotation_type": spec["annotation_type"],
            "title": _clip(title, 140),
            "resource_title": title,
            "source": str(resource.get("source") or ""),
            "resource_type": str(resource.get("type") or ""),
            "file_name": str(bundle.get("file") or ""),
            "snippet": _clip(snippet or title, 520),
            "score": resource.get("score"),
            "local_href": str(bundle.get("local_href") or resource.get("local_href") or ""),
            "url": str(resource.get("url") or bundle.get("url") or ""),
            "task_ids": task_lookup.get(_title_key(title), []),
            "reason": _annotation_reason(spec["kind"]),
        }
    )


def _evidence_chunks(roadmap: dict[str, Any]) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    rag = roadmap.get("rag_evidence", {})
    if isinstance(rag, dict):
        chunks.extend(item for item in rag.get("top_chunks", []) if isinstance(item, dict))
    for task in roadmap.get("study_tasks", []):
        if not isinstance(task, dict):
            continue
        for chunk in task.get("evidence_chunks", []):
            if isinstance(chunk, dict):
                chunks.append({**chunk, "task_id": task.get("id"), "task_type": task.get("type")})
    for resource in list(roadmap.get("resource_library", [])) + [item for phase in roadmap.get("phases", []) for item in phase.get("resources", [])]:
        if not isinstance(resource, dict):
            continue
        rag_meta = resource.get("metadata", {}).get("rag", {}) if isinstance(resource.get("metadata"), dict) else {}
        for chunk in rag_meta.get("top_chunks", []) if isinstance(rag_meta, dict) else []:
            if isinstance(chunk, dict):
                chunks.append({**chunk, "resource_title": chunk.get("resource_title") or resource.get("title")})
    return _dedupe_chunks(chunks)


def _resource_lookup(roadmap: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for resource in roadmap.get("resource_library", []):
        if isinstance(resource, dict) and resource.get("title"):
            lookup[_title_key(str(resource["title"]))] = resource
    for phase in roadmap.get("phases", []):
        for resource in phase.get("resources", []):
            if isinstance(resource, dict) and resource.get("title"):
                lookup.setdefault(_title_key(str(resource["title"])), resource)
    return lookup


def _task_lookup(study_tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = {}
    for task in study_tasks:
        if not isinstance(task, dict):
            continue
        task_id = str(task.get("id") or "")
        if not task_id:
            continue
        for title in task.get("resource_titles", []) or []:
            lookup.setdefault(_title_key(str(title)), [])
            if task_id not in lookup[_title_key(str(title))]:
                lookup[_title_key(str(title))].append(task_id)
        for chunk in task.get("evidence_chunks", []) or []:
            if isinstance(chunk, dict) and chunk.get("resource_title"):
                key = _title_key(str(chunk["resource_title"]))
                lookup.setdefault(key, [])
                if task_id not in lookup[key]:
                    lookup[key].append(task_id)
    return lookup


def _bundle_lookup(study_bundle: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    exact: dict[str, dict[str, Any]] = {}
    by_title: dict[str, dict[str, Any]] = {}
    for entry in study_bundle.get("resources", []) if isinstance(study_bundle, dict) else []:
        if not isinstance(entry, dict) or not entry.get("title"):
            continue
        title = _title_key(str(entry.get("title", "")))
        url = str(entry.get("url") or "")
        exact[f"{title}\n{url}"] = entry
        by_title.setdefault(title, entry)
    return {"exact": exact, "title": by_title}


def _bundle_for_resource(resource: dict[str, Any], bundle_lookup: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    if not resource:
        return {}
    title = _title_key(str(resource.get("title", "")))
    url = str(resource.get("url") or "")
    return bundle_lookup.get("exact", {}).get(f"{title}\n{url}") or bundle_lookup.get("title", {}).get(title, {})


def _section_nav_button(section: dict[str, Any], index: int) -> str:
    section_id = str(section.get("id") or "")
    active = " active" if index == 0 else ""
    return f'<button type="button" class="section-nav-button{active}" data-section-jump="{escape(section_id)}">{escape(str(section.get("title") or section_id))}</button>'


def _section_card(section: dict[str, Any], language: str) -> str:
    section_id = str(section.get("id") or "")
    tags = "".join(f'<span class="lens-tag">{escape(str(item))}</span>' for item in section.get("key_points", [])[:6])
    note = ""
    if section.get("no_evidence_note"):
        note = f'<p class="lens-empty">{escape(str(section["no_evidence_note"]))}</p>'
    return f"""
    <article class="lens-section-card" data-lens-section="{escape(section_id)}" data-section-title="{escape(str(section.get('title') or section_id))}">
      <h2>{escape(str(section.get('title') or section_id))}</h2>
      <p>{escape(str(section.get('summary') or _label(language, 'not_available')))}</p>
      <div class="lens-tag-row">{tags}</div>
      {note}
    </article>
    """


def _quick_overview_panel(sections: list[dict[str, Any]], language: str) -> str:
    section_lookup = {str(section.get("kind")): section for section in sections}
    abstract = section_lookup.get("abstract", {})
    method = section_lookup.get("method", {})
    experiment = section_lookup.get("experiment", {})
    limitation = section_lookup.get("limitation", {})
    keywords = _quick_keywords(sections)
    keyword_html = "".join(f'<span class="lens-tag">{escape(item)}</span>' for item in keywords)
    items = [
        ("quick_problem", str(abstract.get("summary") or _label(language, "not_available"))),
        ("quick_method", str(method.get("summary") or _label(language, "not_available"))),
        ("quick_evidence", str(experiment.get("summary") or _label(language, "not_available"))),
        ("quick_boundary", str(limitation.get("summary") or _label(language, "not_available"))),
    ]
    cards = "".join(
        f"""
        <article class="quick-overview-item">
          <h3>{escape(_label(language, label_key))}</h3>
          <p>{escape(_clip(text, 260))}</p>
        </article>
        """
        for label_key, text in items
    )
    return f"""
    <section class="quick-overview" data-quick-overview>
      <div>
        <h2>{escape(_label(language, "quick_overview"))}</h2>
        <p class="lens-meta">{escape(_label(language, "quick_overview_note"))}</p>
      </div>
      <div class="quick-overview-grid">{cards}</div>
      <div class="quick-keywords" aria-label="{escape(_label(language, "quick_keywords"))}">{keyword_html}</div>
    </section>
    """


def _quick_keywords(sections: list[dict[str, Any]]) -> list[str]:
    values: list[str] = []
    for section in sections:
        for item in (section.get("key_points", []) if isinstance(section, dict) else []):
            values.append(str(item))
    return _dedupe([_clip(item, 40) for item in values if item], limit=5)


def _key_segments(segments: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    if len(segments) <= limit:
        return segments
    selected = sorted(
        segments,
        key=lambda item: (float(item.get("importance_score") or 0), -int(item.get("order") or 0)),
        reverse=True,
    )[:limit]
    selected_ids = {str(item.get("id")) for item in selected}
    return [segment for segment in segments if str(segment.get("id")) in selected_ids]


def _recommendations_panel(recommendations: list[dict[str, Any]], language: str) -> str:
    items = "".join(_recommendation_section_html(item, language) for item in recommendations)
    if not items:
        items = f'<p class="lens-empty">{escape(_label(language, "no_reading_recommendations"))}</p>'
    return f"""
    <section class="lens-side-card reading-recommendations" data-reading-recommendations>
      <h2>{escape(_label(language, "reading_recommendations"))}</h2>
      <p class="lens-meta">{escape(_label(language, "reading_recommendations_note"))}</p>
      <div class="recommendation-list">{items}</div>
    </section>
    """


def _recommendation_section_html(recommendation: dict[str, Any], language: str) -> str:
    section_title = str(recommendation.get("section_title") or recommendation.get("section_kind") or "")
    summary = str(recommendation.get("summary") or "")
    resources = [item for item in recommendation.get("resources", []) if isinstance(item, dict)]
    links = "".join(_recommendation_resource_link(item, language) for item in resources[:2])
    more_links = "".join(_recommendation_resource_link(item, language) for item in resources[2:])
    more = (
        f"""
        <details class="recommendation-more">
          <summary>{escape(_label(language, "more_resources"))}</summary>
          <div class="recommendation-links">{more_links}</div>
        </details>
        """
        if more_links
        else ""
    )
    if not links:
        links = f'<p class="lens-empty">{escape(_label(language, "no_reading_recommendations"))}</p>'
    return f"""
    <article class="recommendation-section" data-recommendation-section="{escape(str(recommendation.get('section_id') or ''))}">
      <h3>{escape(section_title)}</h3>
      <p class="lens-meta">{escape(summary)}</p>
      <div class="recommendation-links">{links}</div>
      {more}
    </article>
    """


def _recommendation_resource_link(resource: dict[str, Any], language: str) -> str:
    title = str(resource.get("title") or _label(language, "recommended_resource"))
    local_href = str(resource.get("local_href") or "")
    url = str(resource.get("url") or "")
    href = local_href or (url if not url.startswith("local://") else "")
    type_label = _annotation_type_label(language, str(resource.get("annotation_type") or "supporting"))
    label = f"{title} · {type_label}"
    if href:
        return f'<a class="recommendation-link" href="{escape(href)}">{escape(label)}</a>'
    return f'<span class="recommendation-link">{escape(label)}</span>'


def _segment_reader(segments: list[dict[str, Any]], explanations: list[dict[str, Any]], language: str, *, compact: bool = False) -> str:
    explanation_lookup = {str(item.get("segment_id")): item for item in explanations}
    cards = "".join(_segment_card(segment, explanation_lookup.get(str(segment.get("id")), {}), language, compact=compact) for segment in segments)
    if not cards:
        cards = f'<p class="lens-empty">{escape(_label(language, "no_segments"))}</p>'
    title_key = "key_sentence_flow" if compact else "source_reading_flow"
    note_key = "key_sentence_note" if compact else "source_reading_note"
    class_name = "segment-reader compact" if compact else "segment-reader"
    return f"""
    <section class="{class_name}" aria-label="{escape(_label(language, title_key))}">
      <div class="segment-reader-head">
        <h2>{escape(_label(language, title_key))}</h2>
        <p class="lens-meta">{escape(_label(language, note_key))}</p>
      </div>
      {cards}
    </section>
    """


def _segment_card(segment: dict[str, Any], explanation: dict[str, Any], language: str, *, compact: bool = False) -> str:
    segment_id = str(segment.get("id") or "")
    section_kind = str(segment.get("section_kind") or "")
    section_ref = f"section-{section_kind}"
    page = segment.get("page")
    page_badge = f'<span class="lens-tag">p.{escape(str(page))}</span>' if page else ""
    score = segment.get("importance_score")
    score_badge = f'<span class="lens-tag">{escape(_label(language, "importance"))}: {escape(str(score))}</span>' if score is not None else ""
    popover = _popover_explanation(explanation, language) if explanation else ""
    class_name = "paper-segment-card compact" if compact else "paper-segment-card"
    return f"""
    <article class="{class_name}" data-paper-segment-card data-segment-id="{escape(segment_id)}" data-section-ref="{escape(section_ref)}" data-section-kind="{escape(section_kind)}">
      <button type="button" class="paper-segment-button" data-paper-segment="{escape(segment_id)}" data-section-ref="{escape(section_ref)}">
        {escape(str(segment.get("original_text") or ""))}
      </button>
      {popover}
      <div class="segment-meta-row">
        <span class="lens-tag">{escape(str(segment.get("section_title") or section_kind))}</span>
        <span class="lens-tag">{escape(str(segment.get("source_language") or ""))}</span>
        {page_badge}
        {score_badge}
      </div>
    </article>
    """


def _popover_explanation(explanation: dict[str, Any], language: str) -> str:
    segment_id = str(explanation.get("segment_id") or "")
    return f"""
    <div class="segment-popover" data-explanation-card="{escape(segment_id)}">
      <p><strong>{escape(_label(language, "plain_meaning"))}</strong></p>
      <p>{escape(str(explanation.get("plain_meaning") or ""))}</p>
      <p>{escape(str(explanation.get("why_it_matters") or ""))}</p>
      <a class="lens-action" data-detail-link href="#{escape(str(explanation.get('detail_anchor') or ''))}">{escape(_label(language, "expand_detail"))}</a>
    </div>
    """


def _side_explanation_card(explanation: dict[str, Any], language: str, *, active: bool = False) -> str:
    segment_id = str(explanation.get("segment_id") or "")
    refs = "".join(_evidence_ref_html(item, language) for item in explanation.get("evidence_refs", []) if isinstance(item, dict))
    hidden = "" if active else " hidden"
    return f"""
    <article class="active-explanation-card" data-explanation-card="{escape(segment_id)}"{hidden}>
      <p><strong>{escape(_label(language, "plain_meaning"))}</strong></p>
      <p>{escape(str(explanation.get("plain_meaning") or ""))}</p>
      <p><strong>{escape(_label(language, "why_it_matters"))}</strong></p>
      <p>{escape(str(explanation.get("why_it_matters") or ""))}</p>
      <p><strong>{escape(_label(language, "method_note"))}</strong></p>
      <p>{escape(str(explanation.get("method_note") or ""))}</p>
      <div>{refs}</div>
      <a class="lens-action primary" data-detail-link href="#{escape(str(explanation.get('detail_anchor') or ''))}">{escape(_label(language, "expand_detail"))}</a>
    </article>
    """


def _detail_explanation_card(explanation: dict[str, Any], segments: list[dict[str, Any]], language: str) -> str:
    segment = next((item for item in segments if str(item.get("id")) == str(explanation.get("segment_id"))), {})
    refs = "".join(_evidence_ref_html(item, language) for item in explanation.get("evidence_refs", []) if isinstance(item, dict))
    return f"""
    <article id="{escape(str(explanation.get('detail_anchor') or ''))}" class="detail-explanation-card" data-detail-anchor="{escape(str(explanation.get('detail_anchor') or ''))}" tabindex="-1">
      <h3>{escape(str(segment.get("section_title") or _label(language, "inline_explanation")))}</h3>
      <p class="evidence-snippet">{escape(str(segment.get("original_text") or ""))}</p>
      <p><strong>{escape(_label(language, "plain_meaning"))}</strong> {escape(str(explanation.get("plain_meaning") or ""))}</p>
      <p><strong>{escape(_label(language, "why_it_matters"))}</strong> {escape(str(explanation.get("why_it_matters") or ""))}</p>
      <p><strong>{escape(_label(language, "method_note"))}</strong> {escape(str(explanation.get("method_note") or ""))}</p>
      {refs}
    </article>
    """


def _evidence_ref_html(ref: dict[str, Any], language: str) -> str:
    local_href = str(ref.get("local_href") or "")
    url = str(ref.get("url") or "")
    links: list[str] = []
    if local_href:
        links.append(f'<a href="{escape(local_href)}">{escape(_label(language, "open_local_resource"))}</a>')
    if url and url != local_href and not url.startswith("local://"):
        links.append(f'<a href="{escape(url)}">{escape(_label(language, "original_link"))}</a>')
    return f"""
    <details class="evidence-snippet">
      <summary>{escape(str(ref.get("resource_title") or _label(language, "original_evidence")))}</summary>
      <p>{escape(str(ref.get("snippet") or ""))}</p>
      <div class="context-links">{''.join(links)}</div>
    </details>
    """


def _annotation_card(annotation: dict[str, Any], section: dict[str, Any], language: str) -> str:
    annotation_type = str(annotation.get("annotation_type") or "supporting")
    section_id = str(section.get("id") or "")
    local_href = str(annotation.get("local_href") or "")
    url = str(annotation.get("url") or "")
    links: list[str] = []
    if local_href:
        links.append(f'<a href="{escape(local_href)}">{escape(_label(language, "open_local_resource"))}</a>')
    if url and url != local_href and not url.startswith("local://"):
        links.append(f'<a href="{escape(url)}">{escape(_label(language, "original_link"))}</a>')
    task_ids = annotation.get("task_ids") or []
    task_text = f"{_label(language, 'related_tasks')}: {', '.join(str(item) for item in task_ids)}" if task_ids else _label(language, "no_related_tasks")
    return f"""
    <article class="lens-context-card {escape(annotation_type)}" data-lens-annotation data-section-ref="{escape(section_id)}" data-annotation-type="{escape(annotation_type)}">
      <div class="context-head">
        <strong>{escape(str(annotation.get('title') or annotation.get('resource_title') or 'Resource'))}</strong>
        <span class="context-type">{escape(_annotation_type_label(language, annotation_type))}</span>
      </div>
      <p class="lens-meta">{escape(str(annotation.get('source') or ''))} / {escape(str(annotation.get('resource_type') or ''))} {escape(str(annotation.get('file_name') or ''))}</p>
      <details open>
        <summary>{escape(_label(language, "original_evidence"))}</summary>
        <p class="evidence-snippet">{escape(str(annotation.get('snippet') or _label(language, 'not_available')))}</p>
      </details>
      <p class="lens-meta">{escape(str(annotation.get('reason') or ''))}</p>
      <p class="lens-meta">{escape(task_text)}</p>
      <div class="context-links">{''.join(links)}</div>
      <label class="progress-row"><input type="checkbox" data-progress-id="{escape(str(annotation.get('id') or 'annotation'))}"><span>{escape(_label(language, 'mark_read'))}</span></label>
    </article>
    """


def _target_actions(target: dict[str, Any], language: str) -> str:
    local_href = str(target.get("local_href") or "")
    url = str(target.get("url") or "")
    actions: list[str] = []
    if local_href:
        actions.append(f'<a class="lens-action primary" href="{escape(local_href)}">{escape(_label(language, "open_local_paper"))}</a>')
    if url and url != local_href and not url.startswith("local://"):
        actions.append(f'<a class="lens-action" href="{escape(url)}">{escape(_label(language, "original_link"))}</a>')
    if not actions:
        actions.append(f'<span class="lens-meta">{escape(_label(language, "no_local_paper"))}</span>')
    return "".join(actions)


def _latex_export_actions(lens: dict[str, Any], language: str) -> str:
    export = lens.get("latex_export", {}) if isinstance(lens.get("latex_export"), dict) else {}
    actions: list[str] = []
    pdf_file = str(export.get("pdf_file") or "")
    tex_file = str(export.get("tex_file") or "")
    if pdf_file and export.get("compile_status") == "compiled":
        actions.append(f'<a class="lens-action primary" href="{escape(pdf_file)}">{escape(_label(language, "open_latex_pdf"))}</a>')
    if tex_file:
        actions.append(f'<a class="lens-action" href="{escape(tex_file)}">{escape(_label(language, "open_latex_source"))}</a>')
    return "".join(actions)


def _annotation_filter_types(sections: list[dict[str, Any]]) -> list[str]:
    seen: list[str] = []
    for section in sections:
        for annotation in section.get("annotations", []):
            kind = str(annotation.get("annotation_type") or "")
            if kind and kind not in seen:
                seen.append(kind)
    return seen


def _matches_terms(section_terms: set[str], chunk: dict[str, Any]) -> bool:
    text_terms = _tokens(" ".join(str(chunk.get(key) or "") for key in ("snippet", "resource_title", "file_name", "type", "source")))
    return bool(section_terms & text_terms)


def _score_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _resource_matches(section_terms: set[str], resource: dict[str, Any]) -> bool:
    values = [
        resource.get("title", ""),
        resource.get("type", ""),
        resource.get("source", ""),
        " ".join(str(item) for item in resource.get("concepts", []) if item),
        " ".join(str(item) for item in resource.get("learning_key_points", []) if item),
        " ".join(str(item) for item in resource.get("focus_areas", []) if item),
    ]
    return bool(section_terms & _tokens(" ".join(values)))


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text)}


def _dedupe(values: list[str], *, limit: int) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        output.append(normalized)
        if len(output) >= limit:
            break
    return output


def _dedupe_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for chunk in chunks:
        key = (
            str(chunk.get("resource_title") or ""),
            str(chunk.get("file_name") or ""),
            str(chunk.get("snippet") or "")[:160],
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(chunk)
    return output


def _annotation_id(section_kind: str, title: str, content: str) -> str:
    digest = sha1(f"{section_kind}\n{title}\n{content}".encode("utf-8", errors="ignore")).hexdigest()[:10]
    return f"ann-{_slug(section_kind)}-{_slug(title)[:40]}-{digest}"


def _section_title(spec: dict[str, Any], language: str) -> str:
    if language == "en":
        return str(spec["title_en"])
    if language == "bilingual":
        return f"{spec['title_en']} / {spec['title_zh']}"
    return str(spec["title_zh"])


def _annotation_type_label(language: str, kind: str) -> str:
    en, zh = ANNOTATION_TYPE_LABELS.get(kind, (kind.replace("_", " ").title(), kind))
    if language == "en":
        return en
    if language == "bilingual":
        return f"{en} / {zh}"
    return zh


def _annotation_reason(section_kind: str) -> str:
    reasons = {
        "abstract": "用于快速定位论文问题、贡献和主线。",
        "background": "用于补齐读懂该段所需的前置知识。",
        "method": "用于解释方法机制、算法步骤或关键假设。",
        "formula": "用于辅助推导公式、目标函数或符号定义。",
        "experiment": "用于连接实验设置、复现资源和验证证据。",
        "limitation": "用于识别适用边界、失败模式和批判角度。",
        "related_work": "用于对比相关工作、基准或后续资料。",
    }
    return reasons.get(section_kind, "用于支撑目标论文阅读。")


def _lens_title(target_title: str, language: str) -> str:
    compact = _compact_title(target_title)
    if language == "en":
        return f"{compact} Paper Lens"
    if language == "bilingual":
        return f"{compact} Paper Lens / 目标论文增强阅读器"
    return f"{compact} 目标论文增强阅读器"


def _compact_title(title: str) -> str:
    text = re.sub(r"\s+", " ", title).strip()
    if ":" in text:
        prefix = text.split(":", 1)[0].strip()
        if 6 <= len(prefix) <= 52:
            return prefix
    return _clip(text or "Target paper", 64)


def _label(language: str, key: str) -> str:
    labels = {
        "reader_title": ("Paper Lens", "目标论文增强阅读器"),
        "reader_eyebrow": ("Evidence-grounded paper reader", "证据驱动的目标论文阅读器"),
        "view_mode_switch": ("View mode", "阅读模式"),
        "quick_mode": ("Quick understanding", "快速理解"),
        "deep_mode": ("Deep reading", "精读模式"),
        "current_quick_mode": ("Current: quick understanding", "当前：快速理解"),
        "current_deep_mode": ("Current: deep reading", "当前：精读模式"),
        "quick_overview": ("Understand in three minutes", "三分钟读懂"),
        "quick_overview_note": (
            "Start here: read the paper's problem, method, evidence, and boundary before opening the heavier evidence layers.",
            "先看这里：用最少信息抓住问题、方法、证据和边界，再按需打开更重的证据层。",
        ),
        "quick_problem": ("Problem", "解决什么问题"),
        "quick_method": ("Core method", "核心方法"),
        "quick_evidence": ("Why it works", "为什么有效"),
        "quick_boundary": ("Boundary", "适用边界"),
        "quick_keywords": ("Keywords to remember", "需要记住的关键词"),
        "reading_flow": ("Paper reading flow", "论文阅读流"),
        "section_navigation": ("Section navigation", "章节导航"),
        "context_panel": ("Context, evidence, and resources", "上下文资料、证据与任务"),
        "key_sentence_flow": ("Key sentence quick read", "关键句速读"),
        "key_sentence_note": (
            "Only the highest-value sentences are shown here. Click one sentence to pin its explanation on the right.",
            "这里只显示最值得先看的关键句。点击句段后，右侧会固定对应解释。",
        ),
        "source_reading_flow": ("Source sentence reading flow", "原文句段精读流"),
        "source_reading_note": (
            "Hover or click a highlighted sentence to see what it means, why it matters, and how to understand the method.",
            "悬浮或点击句段，查看它在说什么、为什么重要，以及方法怎么理解。",
        ),
        "reading_recommendations": ("Recommended reading for the sections above", "以上内容推荐阅读"),
        "reading_recommendations_note": (
            "Read these resources after a group of sentences instead of interrupting every sentence with a separate reading prompt.",
            "读完一组句段后，再集中查看这些资料；不在每句话下面反复打断阅读。",
        ),
        "more_resources": ("More resources", "展开更多资料"),
        "no_reading_recommendations": ("No grouped reading recommendation is available yet.", "暂未生成集中推荐阅读。"),
        "recommended_resource": ("Recommended resource", "推荐资料"),
        "inline_explanation": ("Inline explanation", "句段解释卡"),
        "inline_explanation_note": (
            "Click a sentence on the left to pin its explanation here.",
            "点击左侧句段后，这里会固定显示对应解释。",
        ),
        "detail_explanations": ("Detailed explanations", "句段详解区"),
        "detail_explanations_note": (
            "Detailed cards keep the original sentence, plain explanation, method note, and supporting evidence together.",
            "详解卡会把原句、直白解释、方法说明和支撑证据放在一起。",
        ),
        "plain_meaning": ("What this says", "这句话在说什么"),
        "why_it_matters": ("Why it matters", "为什么重要"),
        "method_note": ("How to understand the method", "方法怎么理解"),
        "expand_detail": ("Expand details", "展开详解"),
        "importance": ("importance", "重要度"),
        "no_segments": ("No readable paper segments were found.", "暂未找到可用于句段精读的论文片段。"),
        "based_on_available_fragments": (
            "This reader is based on available metadata and evidence fragments.",
            "当前阅读器基于可用的论文元数据和证据片段生成。",
        ),
        "all_sections": ("All sections", "全部章节"),
        "all_annotations": ("All annotations", "全部注释"),
        "open_local_paper": ("Open local paper", "打开本地论文"),
        "open_latex_pdf": ("Open compiled PDF", "打开 PDF 精简版"),
        "open_latex_source": ("Open LaTeX source", "打开 LaTeX 源文件"),
        "open_local_resource": ("Open local resource", "打开本地资料"),
        "original_link": ("Original link", "原始链接"),
        "original_evidence": ("Original evidence", "原文证据"),
        "related_tasks": ("Related tasks", "关联任务"),
        "no_related_tasks": ("No related task", "暂无关联任务"),
        "mark_read": ("Mark as read", "标记为已读"),
        "storage_warning": ("Local progress storage is unavailable, so checks are temporary.", "当前浏览器无法使用本地进度存储，勾选状态仅临时保留。"),
        "no_evidence": ("No direct evidence was found in the current bundle.", "当前资料包中未找到直接证据。"),
        "no_target_paper": ("No target paper was found.", "未找到目标论文。"),
        "target_paper": ("Target paper:", "目标论文："),
        "no_local_paper": ("No local paper file in bundle", "资料包中暂无本地论文文件"),
        "not_available": ("Not available", "暂无"),
        "unknown": ("Unknown", "未知"),
        "fallback_abstract": ("Read the abstract and contribution first, then connect it to the method and experiments.", "先抓住论文问题、贡献和主线，再连接方法与实验。"),
        "fallback_background": ("Review only prerequisites that directly unblock the target paper.", "只补齐会直接卡住目标论文阅读的前置知识。"),
        "fallback_method": ("Locate the method pipeline, assumptions, inputs, outputs, and key mechanisms.", "定位方法流程、假设、输入输出和关键机制。"),
        "fallback_formula": ("Extract one formula, objective, or symbolic step that must be derived.", "抽取一个必须能推导的公式、目标函数或符号步骤。"),
        "fallback_experiment": ("Map evaluation settings to reproducible checks and evidence.", "把实验设置映射到可复现检查与证据。"),
        "fallback_limitation": ("List boundary conditions, failure modes, and when not to use the method.", "列出适用边界、失败模式和不适用场景。"),
        "fallback_related_work": ("Use related resources only when they clarify this paper faster.", "只使用能更快解释目标论文的相关资料。"),
    }
    en, zh = labels.get(key, (key.replace("_", " ").title(), key))
    if language == "en":
        return en
    if language == "bilingual":
        return f"{en} / {zh}"
    return zh


def _join(values: Any, fallback: str) -> str:
    if isinstance(values, str):
        return values
    if isinstance(values, list):
        text = ", ".join(str(item) for item in values if item)
        return text or fallback
    return fallback


def _title_key(title: str) -> str:
    return re.sub(r"\s+", " ", title).strip().lower()


def _slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()
    return slug or "item"


def _clip(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, child in value.items():
            if key == "local_path":
                sanitized[key] = None
            else:
                sanitized[key] = _sanitize(child)
        return sanitized
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return PRIVATE_PATH_RE.sub("[private local path]", value)
    return value


def _script_json_payload(value: str) -> str:
    return (
        value.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _html_lang(language: str) -> str:
    if language == "en":
        return "en"
    if language == "bilingual":
        return "zh-CN"
    return "zh-CN"
