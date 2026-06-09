from __future__ import annotations

import copy
import json
import re
from hashlib import sha1
from html import escape
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


def has_target_paper(roadmap: dict[str, Any]) -> bool:
    return bool(_target_resource(roadmap))


def build_paper_lens(roadmap: dict[str, Any]) -> dict[str, Any]:
    safe_roadmap = _sanitize(copy.deepcopy(roadmap))
    target = _target_resource(safe_roadmap)
    if not target:
        return {}
    language = str(safe_roadmap.get("profile", {}).get("output_language", "zh-CN"))
    paper_metadata = _paper_metadata(target)
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
    section_nav = "".join(_section_nav_button(section, index) for index, section in enumerate(sections))
    section_cards = "".join(_section_card(section, language) for section in sections)
    annotation_cards = "".join(
        _annotation_card(annotation, section, language)
        for section in sections
        for annotation in section.get("annotations", [])
        if isinstance(annotation, dict)
    )
    filter_types = _annotation_filter_types(sections)
    filter_buttons = "".join(
        f'<button type="button" class="lens-filter-chip" data-lens-filter="{escape(kind)}">{escape(_annotation_type_label(language, kind))}</button>'
        for kind in filter_types
    )
    target_actions = _target_actions(target, language)
    lens_json = json.dumps(
        {
            "storageKey": f"fields-study-flow-paper-lens:{_slug(str(target.get('title') or 'target-paper'))}",
            "sections": [section.get("id") for section in sections],
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
    .lens-action, .lens-filter-chip, .section-nav-button {{ border:1px solid #c9d8e8; background:#fff; border-radius:999px; padding:8px 11px; color:var(--blue); cursor:pointer; font:inherit; font-size:13px; }}
    .lens-action.primary, .lens-filter-chip.active, .section-nav-button.active {{ background:var(--blue); color:#fff; border-color:var(--blue); }}
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
      .lens-actions {{ justify-content:flex-start; }}
      .lens-context-panel, .section-nav {{ position:static; max-height:none; overflow:visible; }}
    }}
  </style>
</head>
<body>
<main class="paper-lens-app" data-paper-lens-app>
  <div class="lens-shell">
    <header class="lens-hero">
      <div>
        <p class="lens-meta">{escape(_label(language, "reader_eyebrow"))}</p>
        <h1>{escape(title)}</h1>
        <p class="lens-meta">{escape(str(target.get("title") or ""))}</p>
        <p class="lens-meta">{escape(_join(target.get("authors", []), _label(language, "unknown")))}</p>
      </div>
      <nav class="lens-actions">{target_actions}</nav>
    </header>
    <section class="storage-warning" data-storage-warning>{escape(_label(language, "storage_warning"))}</section>
    <div class="lens-layout">
      <section class="lens-reading" aria-label="{escape(_label(language, "reading_flow"))}">
        <nav class="section-nav" aria-label="{escape(_label(language, "section_navigation"))}">{section_nav}</nav>
        {section_cards}
      </section>
      <aside class="lens-context-panel" aria-label="{escape(_label(language, "context_panel"))}">
        <section class="lens-side-card">
          <h2>{escape(_label(language, "context_panel"))}</h2>
          <p class="lens-meta" data-active-section-label>{escape(_label(language, "all_sections"))}</p>
          <div class="lens-filter-row">
            <button type="button" class="lens-filter-chip active" data-lens-filter="all">{escape(_label(language, "all_annotations"))}</button>
            {filter_buttons}
          </div>
        </section>
        <section class="annotation-list" data-annotation-list>{annotation_cards or f'<p class="lens-empty">{escape(_label(language, "no_evidence"))}</p>'}</section>
      </aside>
    </div>
  </div>
</main>
<script type="application/json" id="paper-lens-data">{escape(lens_json)}</script>
<script>
(function () {{
  const config = JSON.parse(document.getElementById('paper-lens-data').textContent || '{{}}');
  const app = document.querySelector('[data-paper-lens-app]');
  const sectionButtons = Array.from(document.querySelectorAll('[data-section-jump]'));
  const sections = Array.from(document.querySelectorAll('[data-lens-section]'));
  const annotations = Array.from(document.querySelectorAll('[data-lens-annotation]'));
  const filters = Array.from(document.querySelectorAll('[data-lens-filter]'));
  const activeLabel = document.querySelector('[data-active-section-label]');
  let activeSection = 'all';
  let activeFilter = 'all';
  let storage = null;
  try {{
    storage = window.localStorage;
    const probe = config.storageKey + ':probe';
    storage.setItem(probe, '1');
    storage.removeItem(probe);
  }} catch (error) {{
    document.querySelector('[data-storage-warning]')?.classList.add('show');
    storage = null;
  }}
  function applyFilters() {{
    sections.forEach((section) => section.classList.toggle('active', activeSection !== 'all' && section.dataset.lensSection === activeSection));
    sectionButtons.forEach((button) => button.classList.toggle('active', button.dataset.sectionJump === activeSection));
    filters.forEach((button) => button.classList.toggle('active', button.dataset.lensFilter === activeFilter));
    annotations.forEach((card) => {{
      const sectionMatch = activeSection === 'all' || card.dataset.sectionRef === activeSection;
      const typeMatch = activeFilter === 'all' || card.dataset.annotationType === activeFilter;
      card.hidden = !(sectionMatch && typeMatch);
    }});
    const active = sections.find((section) => section.dataset.lensSection === activeSection);
    if (activeLabel) activeLabel.textContent = active ? active.dataset.sectionTitle : {json.dumps(_label(language, "all_sections"), ensure_ascii=False)};
  }}
  sectionButtons.forEach((button) => button.addEventListener('click', () => {{
    activeSection = button.dataset.sectionJump || 'all';
    const target = document.querySelector('[data-lens-section="' + CSS.escape(activeSection) + '"]');
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
  document.querySelectorAll('[data-progress-id]').forEach((box) => {{
    const key = config.storageKey + ':' + box.dataset.progressId;
    if (storage) box.checked = storage.getItem(key) === 'done';
    box.addEventListener('change', () => {{
      if (storage) storage.setItem(key, box.checked ? 'done' : '');
    }});
  }});
  applyFilters();
}})();
</script>
</body>
</html>"""
    )


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


def _section_summary(spec: dict[str, Any], metadata: dict[str, Any], language: str) -> str:
    value = metadata.get(spec["metadata_key"])
    if isinstance(value, list):
        value = " ".join(str(item) for item in value[:3] if item)
    text = str(value or "").strip()
    if text:
        return _clip(text, 720)
    if spec["kind"] == "background":
        concepts = _join(metadata.get("concepts", []), "")
        if concepts:
            return _clip(concepts, 720)
    return _label(language, f"fallback_{spec['kind']}")


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
        "reading_flow": ("Paper reading flow", "论文阅读流"),
        "section_navigation": ("Section navigation", "章节导航"),
        "context_panel": ("Context, evidence, and resources", "上下文资料、证据与任务"),
        "all_sections": ("All sections", "全部章节"),
        "all_annotations": ("All annotations", "全部注释"),
        "open_local_paper": ("Open local paper", "打开本地论文"),
        "open_local_resource": ("Open local resource", "打开本地资料"),
        "original_link": ("Original link", "原始链接"),
        "original_evidence": ("Original evidence", "原文证据"),
        "related_tasks": ("Related tasks", "关联任务"),
        "no_related_tasks": ("No related task", "暂无关联任务"),
        "mark_read": ("Mark as read", "标记为已读"),
        "storage_warning": ("Local progress storage is unavailable, so checks are temporary.", "当前浏览器无法使用本地进度存储，勾选状态仅临时保留。"),
        "no_evidence": ("No direct evidence was found in the current bundle.", "当前资料包中未找到直接证据。"),
        "no_target_paper": ("No target paper was found.", "未找到目标论文。"),
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


def _html_lang(language: str) -> str:
    if language == "en":
        return "en"
    if language == "bilingual":
        return "zh-CN"
    return "zh-CN"
