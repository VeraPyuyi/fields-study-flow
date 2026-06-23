from __future__ import annotations

import copy
import json
import re
from hashlib import sha1
from html import escape
from typing import Any, Protocol


PRIVATE_PATH_RE = re.compile(r"(?:file://[^\s)\]}\"'<]+|(?<![A-Za-z0-9])[A-Za-z]:[\\/][^)\]}\"'<\r\n]+|/(?:Users|home)/[^)\]}\"'<\r\n]+)")
PAPER_MAP_FILE = "paper_map.html"
PAPER_LENS_FILE = "paper_lens.html"
CORE_CHAIN = [
    "background",
    "motivation",
    "problem",
    "methodology",
    "experiment",
    "contribution",
    "limitation",
]
EDGE_CHAIN = [
    ("background", "motivation", "requires_background"),
    ("motivation", "problem", "motivates"),
    ("problem", "methodology", "addresses"),
    ("methodology", "experiment", "evaluated_by"),
    ("methodology", "contribution", "implements"),
    ("experiment", "contribution", "supports"),
    ("contribution", "limitation", "bounded_by"),
]
PROVIDER = {"mode": "local", "llm_extension_ready": True}


class PaperMapProvider(Protocol):
    def enrich(self, paper_map: dict[str, Any], roadmap: dict[str, Any]) -> dict[str, Any]:
        """Optional extension point for LLM-enhanced paper logic extraction."""


def build_paper_map(
    roadmap: dict[str, Any],
    *,
    paper_map_language: str = "auto",
    paper_map_depth: str = "standard",
    paper_map_layout: str = "xmind-flow",
    paper_map_provider: str = "auto",
    provider: PaperMapProvider | None = None,
) -> dict[str, Any]:
    private_roadmap = copy.deepcopy(roadmap)
    safe_roadmap = _sanitize(copy.deepcopy(roadmap))
    target = _target_resource(safe_roadmap)
    private_target = _target_resource(private_roadmap)
    if not target:
        return {}
    language = _resolve_language(paper_map_language, safe_roadmap)
    depth = _normalize_depth(paper_map_depth)
    metadata = _paper_metadata(target)
    private_metadata = _paper_metadata(private_target)
    text = _paper_source_text(private_target or target, private_metadata or metadata)
    bundle_lookup = _bundle_lookup(safe_roadmap.get("study_bundle", {}))
    target_bundle = _bundle_for_resource(target, bundle_lookup)
    evidence = _evidence_chunks(safe_roadmap)
    resources = _resource_links(safe_roadmap, bundle_lookup)
    tasks = _task_links(safe_roadmap)
    target_summary = _target_summary(target, metadata, target_bundle)
    nodes = [_target_node(target_summary, language)]
    core_nodes = [_core_node(kind, metadata, text, evidence, language) for kind in CORE_CHAIN]
    nodes.extend(core_nodes)
    edges = _core_edges(core_nodes, language)
    if depth in {"standard", "complete"}:
        branch_nodes, branch_edges = _branch_nodes_and_edges(metadata, resources, tasks, evidence, language, depth)
        nodes.extend(branch_nodes)
        edges.extend(branch_edges)
    layout = _apply_xmind_flow_layout(nodes, edges, paper_map_layout)
    source_links = _source_links(target_summary, resources)
    paper_map = _sanitize(
        {
            "version": 1,
            "mode": "single-paper",
            "future_modes": ["multi-paper", "field"],
            "output_language": language,
            "depth": depth,
            "provider": _provider_summary(paper_map_provider, provider),
            "layout": layout,
            "target": target_summary,
            "nodes": nodes,
            "edges": edges,
            "source_links": source_links,
            "summary": {
                "core_nodes": len(core_nodes),
                "edges": len(edges),
                "evidence_backed_nodes": sum(1 for node in nodes if node.get("evidence")),
                "primary_chain": "Background -> Motivation -> Problem -> Methodology -> Experiments -> Contributions -> Limitations",
            },
        }
    )
    if provider is not None:
        paper_map = provider.enrich(paper_map, safe_roadmap)
    return _sanitize(paper_map)


def render_paper_map_html(roadmap: dict[str, Any]) -> str:
    safe_roadmap = _sanitize(copy.deepcopy(roadmap))
    paper_map = safe_roadmap.get("paper_map") if isinstance(safe_roadmap.get("paper_map"), dict) else {}
    if not paper_map:
        options = safe_roadmap.get("paper_map_options", {}) if isinstance(safe_roadmap.get("paper_map_options"), dict) else {}
        paper_map = build_paper_map(
            safe_roadmap,
            paper_map_language=str(options.get("language") or "auto"),
            paper_map_depth=str(options.get("depth") or "standard"),
            paper_map_layout=str(options.get("layout") or "xmind-flow"),
            paper_map_provider=str(options.get("provider") or "auto"),
        )
    if not paper_map:
        return _empty_html("zh-CN")
    return _render_paper_map_graph_html(paper_map)
    language = str(paper_map.get("output_language") or "zh-CN")
    target = paper_map.get("target", {}) if isinstance(paper_map.get("target"), dict) else {}
    nodes = [node for node in paper_map.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in paper_map.get("edges", []) if isinstance(edge, dict)]
    core_nodes = [node for node in nodes if node.get("role") == "core"]
    branch_nodes = [node for node in nodes if node.get("role") not in {"core", "target"}]
    first_node = core_nodes[0] if core_nodes else (nodes[0] if nodes else {})
    html_nodes = "".join(_node_card(node, language, active=node.get("id") == first_node.get("id")) for node in core_nodes)
    html_edges = "".join(_edge_chip(edge) for edge in edges if edge.get("from") in {node.get("id") for node in core_nodes})
    branch_cards = "".join(_branch_card(node) for node in branch_nodes) or f'<p class="paper-map-empty">{escape(_label(language, "no_branch"))}</p>'
    source_links = "".join(_source_link(item, language) for item in paper_map.get("source_links", []) if isinstance(item, dict))
    data_json = json.dumps({"nodes": nodes, "edges": edges, "target": target}, ensure_ascii=False)
    title = _label(language, "paper_map_title")
    target_title = str(target.get("title") or "Target paper")
    return _sanitize(
        f"""<!doctype html>
<html lang="{escape(_html_lang(language))}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(_compact_title(target_title))} {escape(title)}</title>
  <style>
    :root {{ --ink:#162331; --muted:#647588; --line:#d8e4ee; --blue:#23639b; --green:#25745d; --gold:#a56b10; --rose:#a54257; --paper:#f6f9fc; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; color:var(--ink); background:#eef4f8; font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Noto Sans SC","Source Han Sans SC",Arial,sans-serif; line-height:1.62; }}
    a {{ color:var(--blue); text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    .paper-map-app {{ min-height:100vh; padding:22px; }}
    .paper-map-shell {{ max-width:1480px; margin:0 auto; display:grid; gap:16px; }}
    .paper-map-hero, .paper-map-panel {{ min-width:0; border:1px solid var(--line); background:#fff; border-radius:10px; padding:16px; box-shadow:0 12px 28px rgba(35,75,110,.06); }}
    .paper-map-hero {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:14px; align-items:start; }}
    .paper-map-hero h1 {{ margin:0 0 6px; font-size:clamp(24px,3vw,36px); line-height:1.2; overflow-wrap:anywhere; }}
    .paper-map-meta {{ color:var(--muted); font-size:14px; overflow-wrap:anywhere; }}
    .paper-map-actions {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:flex-end; }}
    .paper-map-action {{ border:1px solid #c9d8e8; background:#f8fbfe; border-radius:999px; padding:8px 11px; font-size:13px; color:var(--blue); }}
    .paper-map-action.primary {{ background:var(--blue); color:#fff; border-color:var(--blue); }}
    .paper-map-main {{ display:grid; grid-template-columns:minmax(0,1.25fr) minmax(340px,.75fr); gap:16px; align-items:start; }}
    .paper-map-chain-wrap {{ overflow:auto; padding-bottom:8px; }}
    .paper-map-chain {{ min-width:1080px; display:grid; grid-template-columns:repeat(7,minmax(140px,1fr)); gap:10px; align-items:stretch; }}
    .paper-map-node {{ width:100%; min-height:164px; display:flex; flex-direction:column; gap:8px; border:1px solid #d6e4ef; background:#fbfdff; border-radius:10px; padding:12px; text-align:left; color:var(--ink); cursor:pointer; font:inherit; overflow:hidden; }}
    .paper-map-node strong {{ color:var(--blue); line-height:1.28; overflow-wrap:anywhere; }}
    .paper-map-node span, .paper-map-node p {{ margin:0; overflow-wrap:anywhere; word-break:break-word; }}
    .paper-map-node.active {{ border-color:#7cb9e6; box-shadow:0 0 0 3px rgba(124,185,230,.22); background:#f2f9ff; }}
    .paper-map-edge-row {{ display:flex; flex-wrap:wrap; gap:8px; margin-top:12px; }}
    .paper-map-edge {{ border:1px solid #d8e5ef; border-radius:999px; background:#f7fbff; color:#405e7b; padding:5px 8px; font-size:12px; overflow-wrap:anywhere; }}
    .paper-map-detail-panel {{ position:sticky; top:14px; max-height:calc(100vh - 28px); overflow:auto; }}
    .paper-map-detail-panel h2, .paper-map-panel h2 {{ margin:0 0 8px; line-height:1.3; overflow-wrap:anywhere; }}
    .paper-map-detail-section {{ border-top:1px solid #e1ebf3; padding-top:10px; margin-top:10px; }}
    .paper-map-evidence {{ border:1px solid #e0e9f2; background:#f8fafc; border-radius:8px; padding:9px; margin:8px 0; overflow-wrap:anywhere; word-break:break-word; }}
    .paper-map-branches {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; }}
    .paper-map-branch {{ min-width:0; border:1px solid #dce8f2; background:#fbfdff; border-radius:10px; padding:11px; overflow:hidden; }}
    .paper-map-branch h3 {{ margin:0 0 6px; font-size:15px; overflow-wrap:anywhere; }}
    .paper-map-source-links {{ display:flex; flex-wrap:wrap; gap:8px; }}
    .paper-map-source-links a {{ border:1px solid #cfddea; background:#fbfdff; border-radius:999px; padding:6px 9px; font-size:13px; }}
    .paper-map-empty {{ color:var(--muted); border:1px dashed #cbd9e6; border-radius:8px; background:#f7fafc; padding:10px; }}
    @media (max-width: 980px) {{
      .paper-map-app {{ padding:12px; }}
      .paper-map-hero, .paper-map-main {{ grid-template-columns:1fr; }}
      .paper-map-actions {{ justify-content:flex-start; }}
      .paper-map-detail-panel {{ position:static; max-height:none; }}
      .paper-map-chain {{ min-width:0; grid-template-columns:1fr; }}
    }}
  </style>
</head>
<body>
<main class="paper-map-app" data-paper-map-app>
  <div class="paper-map-shell">
    <header class="paper-map-hero">
      <div>
        <p class="paper-map-meta">{escape(_label(language, "eyebrow"))}</p>
        <h1>{escape(title)}</h1>
        <p class="paper-map-meta">{escape(target_title)}</p>
      </div>
      <nav class="paper-map-actions">
        <a class="paper-map-action primary" href="{escape(PAPER_LENS_FILE)}">{escape(_label(language, "open_lens"))}</a>
        {_target_link(target, language)}
      </nav>
    </header>
    <section class="paper-map-main">
      <div class="paper-map-panel">
        <h2>{escape(_label(language, "causal_chain"))}</h2>
        <p class="paper-map-meta">{escape(_label(language, "causal_note"))}</p>
        <div class="paper-map-chain-wrap">
          <div class="paper-map-chain">{html_nodes}</div>
        </div>
        <div class="paper-map-edge-row">{html_edges}</div>
      </div>
      <aside class="paper-map-panel paper-map-detail-panel" data-paper-map-detail-panel>
        {_detail_html(first_node, language)}
      </aside>
    </section>
    <section class="paper-map-panel">
      <h2>{escape(_label(language, "branches"))}</h2>
      <div class="paper-map-branches">{branch_cards}</div>
    </section>
    <section class="paper-map-panel">
      <h2>{escape(_label(language, "source_links"))}</h2>
      <div class="paper-map-source-links">{source_links}</div>
    </section>
  </div>
</main>
<script type="application/json" id="paper-map-data">{_script_json_payload(data_json)}</script>
<script>
(() => {{
  const data = JSON.parse(document.getElementById('paper-map-data').textContent || '{{}}');
  const panel = document.querySelector('[data-paper-map-detail-panel]');
  const buttons = Array.from(document.querySelectorAll('[data-paper-map-node]'));
  const nodeById = new Map((data.nodes || []).map((node) => [node.id, node]));
  function escapeHtml(value) {{
    return String(value || '').replace(/[&<>"']/g, (char) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char]));
  }}
  function linkHtml(item) {{
    const href = item.local_href || item.url || item.href || '';
    if (!href) return '';
    return '<a class="paper-map-action" href="' + escapeHtml(href) + '">' + escapeHtml(item.label || item.title || '{escape(_label(language, "open_resource"))}') + '</a>';
  }}
  const confidenceLabel = {json.dumps(_label(language, "confidence"), ensure_ascii=False)};
  function renderNode(node) {{
    const evidence = (node.evidence || []).map((item) => '<div class="paper-map-evidence"><strong>' + escapeHtml(item.source_title || item.file_name || '{escape(_label(language, "evidence"))}') + '</strong><p>' + escapeHtml(item.snippet || item.note || '') + '</p>' + linkHtml(item) + '</div>').join('') || '<p class="paper-map-empty">{escape(_label(language, "evidence_missing"))}</p>';
    const resources = (node.related_resources || []).map(linkHtml).join(' ');
    panel.innerHTML = '<h2>' + escapeHtml(node.label) + '</h2>'
      + '<p class="paper-map-meta">' + escapeHtml(node.kind_label || node.kind || '') + ' · ' + escapeHtml(confidenceLabel) + ' ' + escapeHtml(node.confidence || '') + '</p>'
      + '<div class="paper-map-detail-section"><strong>{escape(_label(language, "plain"))}</strong><p>' + escapeHtml(node.plain_explanation || '') + '</p></div>'
      + '<div class="paper-map-detail-section"><strong>{escape(_label(language, "why"))}</strong><p>' + escapeHtml(node.why_it_matters || '') + '</p></div>'
      + '<div class="paper-map-detail-section"><strong>{escape(_label(language, "connection"))}</strong><p>' + escapeHtml(node.connection || '') + '</p></div>'
      + '<div class="paper-map-detail-section"><strong>{escape(_label(language, "talking_point"))}</strong><p>' + escapeHtml(node.talking_point || '') + '</p></div>'
      + '<div class="paper-map-detail-section"><strong>{escape(_label(language, "evidence"))}</strong>' + evidence + '</div>'
      + '<div class="paper-map-detail-section"><strong>{escape(_label(language, "resources"))}</strong><p>' + (resources || '{escape(_label(language, "no_resource"))}') + '</p></div>';
  }}
  document.addEventListener('click', (event) => {{
    const button = event.target.closest('[data-paper-map-node]');
    if (!button) return;
    event.preventDefault();
    const node = nodeById.get(button.getAttribute('data-paper-map-node'));
    if (!node || !panel) return;
    buttons.forEach((item) => item.classList.toggle('active', item === button));
    renderNode(node);
  }});
}})();
</script>
</body>
</html>"""
    )


def _render_paper_map_graph_html(paper_map: dict[str, Any]) -> str:
    paper_map = _sanitize(copy.deepcopy(paper_map))
    language = str(paper_map.get("output_language") or "zh-CN")
    target = paper_map.get("target", {}) if isinstance(paper_map.get("target"), dict) else {}
    nodes = [node for node in paper_map.get("nodes", []) if isinstance(node, dict)]
    edges = [edge for edge in paper_map.get("edges", []) if isinstance(edge, dict)]
    layout = paper_map.get("layout", {}) if isinstance(paper_map.get("layout"), dict) else {}
    if layout.get("kind") != "xmind-flow":
        layout = _apply_xmind_flow_layout(nodes, edges, "xmind-flow")
    canvas = layout.get("canvas", {}) if isinstance(layout.get("canvas"), dict) else {"width": 1840, "height": 980}
    canvas_width = int(canvas.get("width") or 1840)
    canvas_height = int(canvas.get("height") or 980)
    first_node = next((node for node in nodes if node.get("role") == "target"), nodes[0] if nodes else {})
    node_lookup = {str(node.get("id")): node for node in nodes}
    html_nodes = "".join(_graph_node_card(node, language, active=node.get("id") == first_node.get("id")) for node in nodes)
    html_edges = "".join(_svg_edge_path(edge, node_lookup) for edge in edges)
    source_links = "".join(_source_link(item, language) for item in paper_map.get("source_links", []) if isinstance(item, dict))
    data_json = json.dumps({"nodes": nodes, "edges": edges, "target": target, "layout": layout}, ensure_ascii=False)
    ui_json = json.dumps(
        {
            "confidence": _label(language, "confidence"),
            "plain": _label(language, "plain"),
            "why": _label(language, "why"),
            "connection": _label(language, "connection"),
            "talkingPoint": _label(language, "talking_point"),
            "evidence": _label(language, "evidence"),
            "resources": _label(language, "resources"),
            "noResource": _label(language, "no_resource"),
            "missingEvidence": _label(language, "evidence_missing"),
            "openResource": _label(language, "open_resource"),
            "collapseBranches": _label(language, "collapse_branches"),
            "expandBranches": _label(language, "expand_branches"),
            "showAllBranches": _label(language, "show_all_branches"),
            "storageUnavailable": _label(language, "storage_unavailable"),
            "showSources": _label(language, "show_sources"),
            "hideSources": _label(language, "hide_sources"),
        },
        ensure_ascii=False,
    )
    title = _label(language, "paper_map_title")
    target_title = str(target.get("title") or "Target paper")
    return _sanitize(
        f"""<!doctype html>
<html lang="{escape(_html_lang(language))}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(_compact_title(target_title))} {escape(title)}</title>
  <style>
    :root {{ --ink:#162331; --muted:#647588; --line:#d8e4ee; --blue:#23639b; --green:#25745d; --gold:#a56b10; --rose:#a54257; --canvas:#f8fbfd; }}
    * {{ box-sizing:border-box; }}
    html, body {{ min-height:100%; }}
    body {{ margin:0; color:var(--ink); background:#eaf1f7; font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Noto Sans SC","Source Han Sans SC",Arial,sans-serif; line-height:1.58; overflow:hidden; }}
    a {{ color:var(--blue); text-decoration:none; }}
    a:hover {{ text-decoration:underline; }}
    button {{ font:inherit; }}
    .paper-map-app {{ height:100vh; padding:14px; display:flex; flex-direction:column; gap:12px; }}
    .paper-map-hero {{ flex:0 0 auto; min-width:0; border:1px solid var(--line); background:rgba(255,255,255,.96); border-radius:14px; padding:12px 14px; box-shadow:0 14px 34px rgba(35,75,110,.08); display:grid; grid-template-columns:minmax(0,1fr) auto; gap:14px; align-items:center; }}
    .paper-map-hero h1 {{ margin:0 0 4px; font-size:clamp(22px,2.2vw,32px); line-height:1.2; overflow-wrap:anywhere; }}
    .paper-map-meta {{ color:var(--muted); font-size:14px; overflow-wrap:anywhere; }}
    .paper-map-actions {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:flex-end; }}
    .paper-map-action {{ border:1px solid #c9d8e8; background:#f8fbfe; border-radius:999px; padding:7px 10px; font-size:13px; color:var(--blue); white-space:nowrap; }}
    .paper-map-action.primary {{ background:var(--blue); color:#fff; border-color:var(--blue); }}
    .paper-map-workspace {{ flex:1 1 auto; min-height:0; display:grid; grid-template-columns:minmax(0,1fr) minmax(330px,390px); gap:12px; }}
    .paper-map-canvas-shell {{ min-width:0; min-height:0; border:1px solid var(--line); background:linear-gradient(90deg,rgba(126,159,190,.08) 1px,transparent 1px),linear-gradient(rgba(126,159,190,.08) 1px,transparent 1px),var(--canvas); background-size:36px 36px; border-radius:16px; overflow:hidden; position:relative; box-shadow:0 18px 40px rgba(35,75,110,.09); }}
    .paper-map-toolbar {{ position:absolute; z-index:7; top:12px; left:12px; right:12px; display:flex; justify-content:space-between; gap:10px; pointer-events:none; }}
    .paper-map-toolbar-group {{ display:flex; flex-wrap:wrap; gap:7px; pointer-events:auto; }}
    .paper-map-zoom-control {{ border:1px solid #c7d7e6; background:rgba(255,255,255,.94); color:#2b5c86; border-radius:999px; padding:7px 10px; cursor:pointer; box-shadow:0 8px 18px rgba(35,75,110,.08); }}
    .paper-map-storage-note {{ display:none; border:1px solid #f0d5a8; background:#fff8ea; color:#7a551d; border-radius:999px; padding:7px 10px; font-size:13px; }}
    .paper-map-storage-note.visible {{ display:inline-flex; }}
    .paper-map-canvas {{ width:100%; height:100%; min-height:680px; position:relative; overflow:hidden; touch-action:none; cursor:grab; }}
    .paper-map-canvas.dragging {{ cursor:grabbing; }}
    .paper-map-viewport {{ position:absolute; left:0; top:0; width:{canvas_width}px; height:{canvas_height}px; transform-origin:0 0; }}
    .paper-map-svg {{ position:absolute; inset:0; width:100%; height:100%; overflow:visible; pointer-events:none; }}
    .paper-map-svg-edge, .paper-map-edge {{ stroke:#8aa2b6; stroke-width:3; fill:none; opacity:.78; transition:opacity .16s, stroke .16s, stroke-width .16s; }}
    .paper-map-svg-edge.paper-map-edge-active {{ stroke:#23639b; stroke-width:4; opacity:1; }}
    .paper-map-svg-edge.hidden {{ display:none; }}
    .paper-map-node {{ position:absolute; border:1px solid #d6e4ef; background:rgba(255,255,255,.97); border-radius:14px; box-shadow:0 12px 26px rgba(35,75,110,.11); overflow:hidden; cursor:grab; transition:box-shadow .16s, border-color .16s, opacity .16s, transform .16s; }}
    .paper-map-node.dragging {{ cursor:grabbing; box-shadow:0 20px 42px rgba(35,75,110,.18); }}
    .paper-map-node.hidden {{ display:none; }}
    .paper-map-node.active {{ border-color:#65a9de; box-shadow:0 0 0 4px rgba(101,169,222,.22),0 16px 32px rgba(35,75,110,.13); }}
    .paper-map-node.neighbor {{ border-color:#9bc8e7; }}
    .paper-map-node-main {{ width:100%; height:100%; display:flex; flex-direction:column; gap:6px; padding:12px; text-align:left; color:var(--ink); background:transparent; border:0; cursor:pointer; }}
    .paper-map-target-node {{ background:#eaf5ff; border-color:#83bde8; }}
    .paper-map-core-node {{ background:#fbfdff; }}
    .paper-map-branch-node {{ background:#fffefa; border-style:dashed; }}
    .paper-map-methodology-node, .paper-map-experiment-node {{ background:#f2fbf6; border-color:#97cfaa; }}
    .paper-map-contribution-node {{ background:#fff3f5; border-color:#e4a0ae; }}
    .paper-map-node strong {{ color:var(--blue); line-height:1.25; overflow-wrap:anywhere; }}
    .paper-map-node span, .paper-map-node p {{ margin:0; overflow-wrap:anywhere; word-break:break-word; }}
    .paper-map-node p {{ color:#405467; font-size:13px; }}
    .paper-map-node-toggle {{ position:absolute; right:8px; bottom:8px; border:1px solid #cbdbea; background:#fff; color:#386a93; border-radius:999px; padding:4px 8px; font-size:12px; cursor:pointer; }}
    .paper-map-detail-panel {{ min-width:0; min-height:0; overflow:auto; border:1px solid var(--line); background:rgba(255,255,255,.97); border-radius:16px; padding:14px; box-shadow:0 18px 40px rgba(35,75,110,.09); }}
    .paper-map-detail-panel.collapsed {{ display:none; }}
    .paper-map-detail-panel h2 {{ margin:0 0 8px; line-height:1.3; overflow-wrap:anywhere; }}
    .paper-map-detail-section {{ border-top:1px solid #e1ebf3; padding-top:10px; margin-top:10px; }}
    .paper-map-evidence {{ border:1px solid #e0e9f2; background:#f8fafc; border-radius:8px; padding:9px; margin:8px 0; overflow-wrap:anywhere; word-break:break-word; }}
    .paper-map-source-dock {{ position:absolute; left:12px; right:12px; bottom:12px; z-index:6; display:flex; align-items:flex-start; gap:8px; max-height:138px; padding:8px; overflow:auto; border:1px solid #d4e1ed; background:rgba(255,255,255,.94); border-radius:14px; box-shadow:0 12px 26px rgba(35,75,110,.10); pointer-events:auto; transition:max-height .18s ease,right .18s ease,background .18s ease,border-color .18s ease,box-shadow .18s ease; }}
    .paper-map-source-dock.collapsed {{ right:auto; max-height:42px; padding:0; overflow:visible; border-color:transparent; background:transparent; box-shadow:none; }}
    .paper-map-source-toggle {{ flex:0 0 auto; border:1px solid #c7d7e6; background:rgba(255,255,255,.96); color:#2b5c86; border-radius:999px; padding:7px 10px; cursor:pointer; box-shadow:0 8px 18px rgba(35,75,110,.08); }}
    .paper-map-source-list {{ min-width:0; display:flex; flex-wrap:wrap; gap:7px; }}
    .paper-map-source-dock.collapsed .paper-map-source-list {{ display:none; }}
    .paper-map-source-dock a {{ border:1px solid #cfddea; background:rgba(255,255,255,.93); border-radius:999px; padding:6px 9px; font-size:13px; box-shadow:0 8px 18px rgba(35,75,110,.06); max-width:260px; overflow-wrap:anywhere; white-space:normal; }}
    .paper-map-empty {{ color:var(--muted); border:1px dashed #cbd9e6; border-radius:8px; background:#f7fafc; padding:10px; }}
    @media (max-width: 980px) {{
      body {{ overflow:auto; }}
      .paper-map-app {{ height:auto; min-height:100vh; padding:12px; }}
      .paper-map-hero, .paper-map-workspace {{ grid-template-columns:1fr; }}
      .paper-map-actions {{ justify-content:flex-start; }}
      .paper-map-canvas {{ min-height:560px; }}
      .paper-map-detail-panel.collapsed {{ display:block; }}
    }}
  </style>
</head>
<body>
<main class="paper-map-app" data-paper-map-app>
  <header class="paper-map-hero">
    <div>
      <p class="paper-map-meta">{escape(_label(language, "eyebrow"))}</p>
      <h1>{escape(title)}</h1>
      <p class="paper-map-meta">{escape(target_title)}</p>
    </div>
    <nav class="paper-map-actions">
      <a class="paper-map-action primary" href="{escape(PAPER_LENS_FILE)}">{escape(_label(language, "open_lens"))}</a>
      {_target_link(target, language)}
    </nav>
  </header>
  <section class="paper-map-workspace">
    <div class="paper-map-canvas-shell">
      <div class="paper-map-toolbar">
        <div class="paper-map-toolbar-group">
          <button type="button" class="paper-map-zoom-control" data-paper-map-zoom-in>{escape(_label(language, "zoom_in"))}</button>
          <button type="button" class="paper-map-zoom-control" data-paper-map-zoom-out>{escape(_label(language, "zoom_out"))}</button>
          <button type="button" class="paper-map-zoom-control" data-paper-map-fit>{escape(_label(language, "fit_view"))}</button>
          <button type="button" class="paper-map-zoom-control" data-paper-map-reset>{escape(_label(language, "reset_layout"))}</button>
          <button type="button" class="paper-map-zoom-control" data-paper-map-show-all>{escape(_label(language, "show_all_branches"))}</button>
        </div>
        <div class="paper-map-toolbar-group">
          <span class="paper-map-storage-note" data-paper-map-storage-note>{escape(_label(language, "storage_unavailable"))}</span>
          <button type="button" class="paper-map-zoom-control" data-paper-map-collapse-detail>{escape(_label(language, "toggle_detail"))}</button>
        </div>
      </div>
      <div class="paper-map-canvas" data-paper-map-canvas>
        <div class="paper-map-viewport" data-paper-map-viewport>
          <svg class="paper-map-svg" viewBox="0 0 {canvas_width} {canvas_height}" aria-hidden="true">
            <defs>
              <marker id="paper-map-arrow" markerWidth="12" markerHeight="10" refX="10" refY="5" orient="auto">
                <path d="M0,0 L12,5 L0,10 Z" fill="#8aa2b6"></path>
              </marker>
            </defs>
            {html_edges}
          </svg>
          {html_nodes}
        </div>
      </div>
      <div class="paper-map-source-dock collapsed" data-paper-map-source-dock>
        <button type="button" class="paper-map-source-toggle" data-paper-map-source-toggle>{escape(_label(language, "show_sources"))}</button>
        <div class="paper-map-source-list">{source_links}</div>
      </div>
    </div>
    <aside class="paper-map-detail-panel" data-paper-map-detail-panel>
      {_graph_detail_html(first_node, language)}
    </aside>
  </section>
</main>
<script type="application/json" id="paper-map-data">{_script_json_payload(data_json)}</script>
<script type="application/json" id="paper-map-ui">{_script_json_payload(ui_json)}</script>
<script>
(() => {{
  const data = JSON.parse(document.getElementById('paper-map-data').textContent || '{{}}');
  const ui = JSON.parse(document.getElementById('paper-map-ui').textContent || '{{}}');
  const panel = document.querySelector('[data-paper-map-detail-panel]');
  const canvas = document.querySelector('[data-paper-map-canvas]');
  const viewport = document.querySelector('[data-paper-map-viewport]');
  const storageNote = document.querySelector('[data-paper-map-storage-note]');
  const sourceDock = document.querySelector('[data-paper-map-source-dock]');
  const sourceToggle = document.querySelector('[data-paper-map-source-toggle]');
  const cards = Array.from(document.querySelectorAll('[data-paper-map-node-card]'));
  const edgeEls = Array.from(document.querySelectorAll('[data-paper-map-edge]'));
  const nodeById = new Map((data.nodes || []).map((node) => [node.id, node]));
  const cardById = new Map(cards.map((card) => [card.getAttribute('data-node-id'), card]));
  const storageKey = 'fields-study-flow:paper-map:' + (data.target?.title || 'target');
  let state = {{ panX: 0, panY: 0, scale: 0.78, selected: (data.nodes || [])[0]?.id || '', collapsed: {{}}, positions: {{}}, sourceDockCollapsed: true }};
  let storageAvailable = true;
  function escapeHtml(value) {{
    return String(value || '').replace(/[&<>"']/g, (char) => ({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[char]));
  }}
  function loadState() {{
    try {{
      const raw = localStorage.getItem(storageKey);
      if (raw) state = Object.assign(state, JSON.parse(raw));
    }} catch (error) {{
      storageAvailable = false;
      storageNote?.classList.add('visible');
    }}
  }}
  function saveState() {{
    if (!storageAvailable) return;
    try {{ localStorage.setItem(storageKey, JSON.stringify(state)); }}
    catch (error) {{ storageAvailable = false; storageNote?.classList.add('visible'); }}
  }}
  function linkHtml(item) {{
    const href = item.local_href || item.url || item.href || '';
    if (!href) return '';
    return '<a class="paper-map-action" href="' + escapeHtml(href) + '">' + escapeHtml(item.label || item.title || ui.openResource || '') + '</a>';
  }}
  function nodeLayout(node) {{
    node.layout = Object.assign({{ x: 0, y: 0, width: 210, height: 120, branch_group: '' }}, node.layout || {{}}, state.positions[node.id] || {{}});
    return node.layout;
  }}
  function centerOf(node) {{
    const layout = nodeLayout(node);
    return {{ x: Number(layout.x || 0) + Number(layout.width || 0) / 2, y: Number(layout.y || 0) + Number(layout.height || 0) / 2 }};
  }}
  function isNodeHidden(node) {{
    const layout = node.layout || {{}};
    return node.role !== 'target' && node.role !== 'core' && node.role !== 'resource' && state.collapsed[layout.branch_group];
  }}
  function applyTransform() {{
    viewport.style.transform = 'translate(' + state.panX + 'px,' + state.panY + 'px) scale(' + state.scale + ')';
  }}
  function updateNodePositions() {{
    for (const node of data.nodes || []) {{
      const card = cardById.get(node.id);
      if (!card) continue;
      const layout = nodeLayout(node);
      card.style.left = Number(layout.x || 0) + 'px';
      card.style.top = Number(layout.y || 0) + 'px';
      card.style.width = Number(layout.width || 210) + 'px';
      card.style.minHeight = Number(layout.height || 110) + 'px';
      card.classList.toggle('hidden', isNodeHidden(node));
    }}
  }}
  function updateEdges() {{
    for (const edgeEl of edgeEls) {{
      const edge = (data.edges || []).find((item) => item.id === edgeEl.getAttribute('data-paper-map-edge'));
      const source = edge ? nodeById.get(edge.from) : null;
      const target = edge ? nodeById.get(edge.to) : null;
      if (!source || !target || isNodeHidden(source) || isNodeHidden(target)) {{
        edgeEl.classList.add('hidden');
        edgeEl.setAttribute('d', '');
        continue;
      }}
      edgeEl.classList.remove('hidden');
      const a = centerOf(source);
      const b = centerOf(target);
      const dx = Math.max(90, Math.abs(b.x - a.x) * 0.42);
      edgeEl.setAttribute('d', 'M ' + a.x + ' ' + a.y + ' C ' + (a.x + dx) + ' ' + a.y + ', ' + (b.x - dx) + ' ' + b.y + ', ' + b.x + ' ' + b.y);
    }}
  }}
  function updateToggles() {{
    document.querySelectorAll('[data-paper-map-expand-toggle]').forEach((button) => {{
      const group = button.getAttribute('data-paper-map-expand-toggle');
      button.textContent = state.collapsed[group] ? (ui.expandBranches || 'Expand') : (ui.collapseBranches || 'Collapse');
    }});
  }}
  function updateSourceDock() {{
    if (!sourceDock || !sourceToggle) return;
    sourceDock.classList.toggle('collapsed', Boolean(state.sourceDockCollapsed));
    sourceToggle.textContent = state.sourceDockCollapsed ? (ui.showSources || 'Show sources') : (ui.hideSources || 'Hide sources');
  }}
  function highlight(nodeId) {{
    cards.forEach((card) => card.classList.remove('active', 'neighbor'));
    edgeEls.forEach((edge) => edge.classList.remove('paper-map-edge-active'));
    const neighbors = new Set();
    for (const edge of data.edges || []) {{
      if (edge.from === nodeId || edge.to === nodeId) {{
        neighbors.add(edge.from);
        neighbors.add(edge.to);
        const edgeEl = edgeEls.find((item) => item.getAttribute('data-paper-map-edge') === edge.id);
        edgeEl?.classList.add('paper-map-edge-active');
      }}
    }}
    cardById.get(nodeId)?.classList.add('active');
    neighbors.forEach((id) => {{ if (id !== nodeId) cardById.get(id)?.classList.add('neighbor'); }});
  }}
  function renderNode(node) {{
    const evidence = (node.evidence || []).map((item) => '<div class="paper-map-evidence"><strong>' + escapeHtml(item.source_title || item.file_name || ui.evidence || '') + '</strong><p>' + escapeHtml(item.snippet || item.note || '') + '</p>' + linkHtml(item) + '</div>').join('') || '<p class="paper-map-empty">' + escapeHtml(ui.missingEvidence || '') + '</p>';
    const resources = (node.related_resources || []).map(linkHtml).join(' ');
    panel.innerHTML = '<h2>' + escapeHtml(node.label) + '</h2>'
      + '<p class="paper-map-meta">' + escapeHtml(node.kind_label || node.kind || '') + ' · ' + escapeHtml(ui.confidence || '') + ' ' + escapeHtml(node.confidence || '') + '</p>'
      + '<div class="paper-map-detail-section"><strong>' + escapeHtml(ui.plain || '') + '</strong><p>' + escapeHtml(node.plain_explanation || '') + '</p></div>'
      + '<div class="paper-map-detail-section"><strong>' + escapeHtml(ui.why || '') + '</strong><p>' + escapeHtml(node.why_it_matters || '') + '</p></div>'
      + '<div class="paper-map-detail-section"><strong>' + escapeHtml(ui.connection || '') + '</strong><p>' + escapeHtml(node.connection || '') + '</p></div>'
      + '<div class="paper-map-detail-section"><strong>' + escapeHtml(ui.talkingPoint || '') + '</strong><p>' + escapeHtml(node.talking_point || '') + '</p></div>'
      + '<div class="paper-map-detail-section"><strong>' + escapeHtml(ui.evidence || '') + '</strong>' + evidence + '</div>'
      + '<div class="paper-map-detail-section"><strong>' + escapeHtml(ui.resources || '') + '</strong><p>' + (resources || escapeHtml(ui.noResource || '')) + '</p></div>';
  }}
  function selectNode(nodeId) {{
    const node = nodeById.get(nodeId);
    if (!node || !panel) return;
    state.selected = nodeId;
    renderNode(node);
    highlight(nodeId);
    saveState();
  }}
  function visibleNodeBounds() {{
    const visible = (data.nodes || []).filter((node) => !isNodeHidden(node));
    if (!visible.length) return {{ x: 0, y: 0, width: Number(data.layout?.canvas?.width || 1840), height: Number(data.layout?.canvas?.height || 980) }};
    let minX = Infinity;
    let minY = Infinity;
    let maxX = -Infinity;
    let maxY = -Infinity;
    for (const node of visible) {{
      const layout = nodeLayout(node);
      const x = Number(layout.x || 0);
      const y = Number(layout.y || 0);
      const width = Number(layout.width || 210);
      const height = Number(layout.height || 110);
      minX = Math.min(minX, x);
      minY = Math.min(minY, y);
      maxX = Math.max(maxX, x + width);
      maxY = Math.max(maxY, y + height);
    }}
    return {{ x: minX, y: minY, width: Math.max(1, maxX - minX), height: Math.max(1, maxY - minY) }};
  }}
  function sourceDockReserve() {{
    if (!sourceDock || state.sourceDockCollapsed) return 34;
    return Math.min(154, Math.max(72, sourceDock.getBoundingClientRect().height || 110));
  }}
  function fitView() {{
    const box = canvas.getBoundingClientRect();
    const bounds = visibleNodeBounds();
    const availableWidth = Math.max(320, box.width - 72);
    const availableHeight = Math.max(260, box.height - 70 - sourceDockReserve());
    state.scale = Math.max(0.45, Math.min(1.28, Math.min(availableWidth / bounds.width, availableHeight / bounds.height)));
    state.panX = Math.round((box.width - bounds.width * state.scale) / 2 - bounds.x * state.scale);
    state.panY = Math.round((availableHeight - bounds.height * state.scale) / 2 - bounds.y * state.scale + 44);
    applyTransform();
    saveState();
  }}
  function resetLayout() {{
    state.positions = {{}};
    state.collapsed = {{}};
    state.sourceDockCollapsed = true;
    state.scale = Number(data.layout?.default_view?.scale || 0.78);
    state.panX = Number(data.layout?.default_view?.x || 0);
    state.panY = Number(data.layout?.default_view?.y || 0);
    updateNodePositions();
    updateEdges();
    updateToggles();
    updateSourceDock();
    fitView();
  }}
  function showAllBranches() {{
    state.collapsed = {{}};
    updateNodePositions();
    updateEdges();
    updateToggles();
    requestAnimationFrame(fitView);
    saveState();
  }}
  document.addEventListener('click', (event) => {{
    if (event.target.closest('[data-paper-map-source-toggle]')) {{
      state.sourceDockCollapsed = !state.sourceDockCollapsed;
      updateSourceDock();
      requestAnimationFrame(fitView);
      saveState();
      return;
    }}
    const toggle = event.target.closest('[data-paper-map-expand-toggle]');
    if (toggle) {{
      event.preventDefault();
      const group = toggle.getAttribute('data-paper-map-expand-toggle');
      state.collapsed[group] = !state.collapsed[group];
      updateNodePositions();
      updateEdges();
      updateToggles();
      requestAnimationFrame(fitView);
      saveState();
      return;
    }}
    if (event.target.closest('[data-paper-map-zoom-in]')) {{ state.scale = Math.min(1.8, state.scale + 0.12); applyTransform(); saveState(); return; }}
    if (event.target.closest('[data-paper-map-zoom-out]')) {{ state.scale = Math.max(0.32, state.scale - 0.12); applyTransform(); saveState(); return; }}
    if (event.target.closest('[data-paper-map-fit]')) {{ fitView(); return; }}
    if (event.target.closest('[data-paper-map-reset]')) {{ resetLayout(); return; }}
    if (event.target.closest('[data-paper-map-show-all]')) {{ showAllBranches(); return; }}
    if (event.target.closest('[data-paper-map-collapse-detail]')) {{ panel?.classList.toggle('collapsed'); return; }}
    const button = event.target.closest('[data-paper-map-node]');
    if (button) {{
      event.preventDefault();
      selectNode(button.getAttribute('data-paper-map-node'));
    }}
  }});
  canvas.addEventListener('wheel', (event) => {{
    event.preventDefault();
    const delta = event.deltaY > 0 ? -0.08 : 0.08;
    state.scale = Math.max(0.32, Math.min(1.8, state.scale + delta));
    applyTransform();
    saveState();
  }}, {{ passive: false }});
  let drag = null;
  canvas.addEventListener('pointerdown', (event) => {{
    const card = event.target.closest('[data-paper-map-node-card]');
    drag = {{ type: card ? 'node' : 'pan', id: card?.getAttribute('data-node-id'), startX: event.clientX, startY: event.clientY, panX: state.panX, panY: state.panY }};
    if (card) {{
      const node = nodeById.get(drag.id);
      const layout = nodeLayout(node);
      drag.nodeX = Number(layout.x || 0);
      drag.nodeY = Number(layout.y || 0);
      card.classList.add('dragging');
    }} else {{
      canvas.classList.add('dragging');
    }}
    canvas.setPointerCapture(event.pointerId);
  }});
  canvas.addEventListener('pointermove', (event) => {{
    if (!drag) return;
    const dx = (event.clientX - drag.startX) / state.scale;
    const dy = (event.clientY - drag.startY) / state.scale;
    if (drag.type === 'node') {{
      state.positions[drag.id] = Object.assign({{}}, state.positions[drag.id] || {{}}, {{ x: Math.round(drag.nodeX + dx), y: Math.round(drag.nodeY + dy) }});
      updateNodePositions();
      updateEdges();
    }} else {{
      state.panX = Math.round(drag.panX + event.clientX - drag.startX);
      state.panY = Math.round(drag.panY + event.clientY - drag.startY);
      applyTransform();
    }}
  }});
  canvas.addEventListener('pointerup', (event) => {{
    if (!drag) return;
    cardById.get(drag.id)?.classList.remove('dragging');
    canvas.classList.remove('dragging');
    drag = null;
    saveState();
    try {{ canvas.releasePointerCapture(event.pointerId); }} catch (error) {{}}
  }});
  loadState();
  updateNodePositions();
  applyTransform();
  updateEdges();
  updateToggles();
  updateSourceDock();
  if (state.selected) selectNode(state.selected);
  else if ((data.nodes || [])[0]) selectNode(data.nodes[0].id);
  requestAnimationFrame(fitView);
}})();
</script>
</body>
</html>"""
    )


def _target_resource(roadmap: dict[str, Any]) -> dict[str, Any]:
    for key in ("selected_resources", "resource_library"):
        for resource in roadmap.get(key, []):
            if isinstance(resource, dict) and _is_target_resource(resource):
                return resource
    for phase in roadmap.get("phases", []):
        if not isinstance(phase, dict):
            continue
        for resource in phase.get("resources", []):
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


def _target_summary(resource: dict[str, Any], metadata: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "target-paper",
        "title": str(metadata.get("title") or resource.get("title") or "Target paper"),
        "authors": [str(item) for item in metadata.get("authors", []) if item],
        "abstract_snippet": str(metadata.get("abstract_snippet") or ""),
        "concepts": [str(item) for item in metadata.get("concepts", []) if item],
        "url": str(resource.get("url") or metadata.get("url") or ""),
        "local_href": str(bundle.get("local_href") or resource.get("local_href") or ""),
        "source": str(resource.get("source") or metadata.get("source") or "paper"),
    }


def _target_node(target: dict[str, Any], language: str) -> dict[str, Any]:
    return {
        "id": "target-paper",
        "kind": "target",
        "role": "target",
        "label": _compact_title(str(target.get("title") or "Target paper")),
        "kind_label": _label(language, "target"),
        "plain_explanation": str(target.get("abstract_snippet") or _label(language, "target_plain")),
        "why_it_matters": _label(language, "target_why"),
        "connection": _label(language, "target_connection"),
        "talking_point": _label(language, "target_talk"),
        "evidence": [],
        "confidence": 0.75,
        "related_resources": [_link_item(target, _label(language, "open_local_or_source"))],
    }


def _core_node(kind: str, metadata: dict[str, Any], text: str, evidence: list[dict[str, Any]], language: str) -> dict[str, Any]:
    source = _source_for_kind(kind, metadata, text)
    node_evidence = _evidence_for_kind(kind, source, evidence)
    confidence = 0.55 + min(len(node_evidence), 2) * 0.12 + (0.12 if source else 0)
    label = _node_label(kind, metadata, source, language)
    return _sanitize(
        {
            "id": f"core-{kind}",
            "kind": kind,
            "role": "core",
            "label": label,
            "kind_label": _kind_label(kind, language),
            "plain_explanation": _plain_explanation(kind, source, metadata, language),
            "why_it_matters": _why_it_matters(kind, source, language),
            "connection": _connection_text(kind, language),
            "talking_point": _talking_point(kind, label, language),
            "evidence": node_evidence or [_missing_evidence(language)],
            "confidence": round(min(confidence, 0.95), 2),
            "related_resources": [],
            "paper_lens_href": PAPER_LENS_FILE,
        }
    )


def _core_edges(core_nodes: list[dict[str, Any]], language: str) -> list[dict[str, Any]]:
    ids = {str(node.get("kind")): str(node.get("id")) for node in core_nodes}
    edges: list[dict[str, Any]] = []
    for source_kind, target_kind, label in EDGE_CHAIN:
        if source_kind in ids and target_kind in ids:
            edges.append(
                {
                    "id": f"edge-{source_kind}-{target_kind}-{label}",
                    "from": ids[source_kind],
                    "to": ids[target_kind],
                    "label": label,
                    "localized_label": _edge_label(label, language),
                }
            )
    if "contribution" in ids:
        edges.append(
            {
                "id": "edge-contribution-target-claims",
                "from": ids["contribution"],
                "to": "target-paper",
                "label": "claims",
                "localized_label": _edge_label("claims", language),
            }
        )
    return edges


def _branch_nodes_and_edges(
    metadata: dict[str, Any],
    resources: list[dict[str, Any]],
    tasks: list[dict[str, Any]],
    evidence: list[dict[str, Any]],
    language: str,
    depth: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    formulas = [str(item) for item in metadata.get("formula_candidates", []) if item]
    for index, formula in enumerate(formulas[:2], start=1):
        node_id = f"formula-{index}"
        nodes.append(_branch_node(node_id, "formula", _clip(formula, 90), _label(language, "formula_plain"), language))
        edges.append(_branch_edge("core-methodology", node_id, "supports", language))
    for index, item in enumerate(resources[: 4 if depth == "standard" else 8], start=1):
        node_id = f"resource-{index}"
        node = _branch_node(node_id, "resource", str(item.get("title") or "Resource"), _label(language, "resource_plain"), language)
        node["related_resources"] = [_link_item(item, _label(language, "open_resource"))]
        nodes.append(node)
        edges.append(_branch_edge("core-methodology", node_id, "supports", language))
    for index, task in enumerate(tasks[: 3 if depth == "standard" else 6], start=1):
        node_id = f"task-{index}"
        nodes.append(_branch_node(node_id, "task", str(task.get("title") or task.get("name") or "Task"), _label(language, "task_plain"), language))
        edges.append(_branch_edge(node_id, "core-contribution", "supports", language))
    for index, item in enumerate(evidence[: 2 if depth == "standard" else 5], start=1):
        node_id = f"evidence-{index}"
        nodes.append(_branch_node(node_id, "evidence", str(item.get("resource_title") or item.get("file_name") or "Evidence"), _clip(str(item.get("snippet") or ""), 180), language))
        edges.append(_branch_edge(node_id, "core-experiment", "supports", language))
    return nodes, edges


def _branch_node(node_id: str, kind: str, label: str, explanation: str, language: str) -> dict[str, Any]:
    return {
        "id": node_id,
        "kind": kind,
        "role": kind,
        "label": _clip(label, 120),
        "kind_label": _kind_label(kind, language),
        "plain_explanation": explanation,
        "why_it_matters": _label(language, "branch_why"),
        "connection": _label(language, "branch_connection"),
        "talking_point": _label(language, "branch_talk"),
        "evidence": [],
        "confidence": 0.62,
        "related_resources": [],
    }


def _branch_edge(source: str, target: str, label: str, language: str) -> dict[str, Any]:
    return {"id": f"edge-{source}-{target}-{label}", "from": source, "to": target, "label": label, "localized_label": _edge_label(label, language)}


def _provider_summary(paper_map_provider: str, provider: PaperMapProvider | None) -> dict[str, Any]:
    requested = str(paper_map_provider or "auto").strip().lower()
    if requested not in {"local", "auto", "llm"}:
        requested = "auto"
    summary = dict(PROVIDER)
    if requested in {"local", "auto"} and provider is None:
        return summary
    summary["requested"] = requested
    summary["status"] = "external_provider_supplied" if provider is not None else "not_configured"
    return summary


def _normalize_layout_kind(value: str) -> str:
    value = str(value or "xmind-flow").strip().lower()
    return value if value == "xmind-flow" else "xmind-flow"


def _apply_xmind_flow_layout(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], layout_kind: str) -> dict[str, Any]:
    kind = _normalize_layout_kind(layout_kind)
    canvas = {"width": 1840, "height": 980}
    node_by_id = {str(node.get("id")): node for node in nodes}
    core_nodes = [node for node in nodes if node.get("role") == "core"]
    core_order = {kind_name: index for index, kind_name in enumerate(CORE_CHAIN)}
    core_nodes.sort(key=lambda node: core_order.get(str(node.get("kind")), 99))
    if "target-paper" in node_by_id:
        node_by_id["target-paper"]["layout"] = {
            "x": 760,
            "y": 54,
            "width": 320,
            "height": 116,
            "layer": 0,
            "branch_group": "target",
            "collapsed": False,
        }
    start_x = 76
    spacing = 244
    for index, node in enumerate(core_nodes):
        kind_name = str(node.get("kind") or f"core-{index}")
        node["layout"] = {
            "x": start_x + index * spacing,
            "y": 360,
            "width": 202,
            "height": 142,
            "layer": 1,
            "branch_group": kind_name,
            "collapsed": False,
        }
    parent_lookup = _branch_parent_lookup(edges)
    branch_counts: dict[str, int] = {}
    branch_nodes = [node for node in nodes if node.get("role") not in {"target", "core"}]
    for node in branch_nodes:
        node_id = str(node.get("id") or "")
        parent_id = parent_lookup.get(node_id) or "core-methodology"
        parent = node_by_id.get(parent_id) or (core_nodes[0] if core_nodes else {})
        parent_layout = parent.get("layout", {}) if isinstance(parent.get("layout"), dict) else {}
        group = str(parent.get("kind") or parent_id.replace("core-", "") or "methodology")
        count = branch_counts.get(parent_id, 0)
        branch_counts[parent_id] = count + 1
        direction = -1 if count % 2 == 0 else 1
        row = count // 2
        parent_x = int(parent_layout.get("x", 760))
        parent_y = int(parent_layout.get("y", 360))
        node["layout"] = {
            "x": max(24, min(canvas["width"] - 230, parent_x + (row * 30) - 8)),
            "y": max(210, min(canvas["height"] - 120, parent_y + direction * (190 + row * 54))),
            "width": 218,
            "height": 96,
            "layer": 2 + row,
            "branch_group": group,
            "parent": parent_id,
            "collapsed": False,
        }
    return {
        "kind": kind,
        "coordinate_system": "absolute",
        "canvas": canvas,
        "default_view": {"x": 0, "y": 0, "scale": 0.78},
        "node_size": {"core": {"width": 202, "height": 142}, "branch": {"width": 218, "height": 96}, "target": {"width": 320, "height": 116}},
    }


def _branch_parent_lookup(edges: list[dict[str, Any]]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for edge in edges:
        source = str(edge.get("from") or "")
        target = str(edge.get("to") or "")
        if source.startswith("core-") and target:
            lookup[target] = source
        if target.startswith("core-") and source:
            lookup[source] = target
    return lookup


def _paper_source_text(target: dict[str, Any], metadata: dict[str, Any]) -> str:
    for key in ("text_preview", "extracted_text", "full_text_preview", "pdf_text", "raw_text", "abstract_snippet"):
        value = metadata.get(key)
        if isinstance(value, list):
            text = "\n\n".join(str(item) for item in value if item)
        else:
            text = str(value or "")
        if text.strip():
            return text
    return str(target.get("description") or target.get("why_recommended") or "")


def _source_for_kind(kind: str, metadata: dict[str, Any], text: str) -> str:
    key_map = {
        "background": ("concepts", "keywords"),
        "motivation": ("abstract_snippet", "limitations_hints"),
        "problem": ("abstract_snippet",),
        "methodology": ("method_hints",),
        "experiment": ("experiment_hints",),
        "contribution": ("abstract_snippet", "method_hints"),
        "limitation": ("limitations_hints",),
    }
    for key in key_map.get(kind, ()):
        value = metadata.get(key)
        if isinstance(value, list) and value:
            return " ".join(str(item) for item in value[:3] if item)
        if isinstance(value, str) and value.strip():
            return value
    sentences = _sentences(text)
    terms = {
        "background": ("background", "symbolic", "pddl", "planning"),
        "motivation": ("motivation", "gap", "struggle", "violate", "need"),
        "problem": ("problem", "struggle", "valid", "precondition"),
        "methodology": ("method", "construct", "trace", "pddl-instruct", "chain-of-thought"),
        "experiment": ("experiment", "planbench", "val", "evaluation", "validation"),
        "contribution": ("result", "show", "contribution", "help"),
        "limitation": ("limitation", "fail", "coverage", "unseen"),
    }.get(kind, ())
    for sentence in sentences:
        lower = sentence.lower()
        if any(term in lower for term in terms):
            return sentence
    return sentences[0] if sentences else ""


def _evidence_for_kind(kind: str, source: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    terms = set(_tokens(source)) | {
        "methodology": {"pddl", "trace", "cot", "logical"},
        "experiment": {"planbench", "val", "validation"},
        "limitation": {"coverage", "unseen", "quality"},
    }.get(kind, set())
    output: list[dict[str, Any]] = []
    for item in evidence:
        snippet = str(item.get("snippet") or "")
        if not snippet:
            continue
        if terms and not (_tokens(snippet) & terms):
            continue
        output.append(
            _sanitize(
                {
                    "source_title": item.get("resource_title") or item.get("title"),
                    "file_name": item.get("file_name"),
                    "snippet": _clip(snippet, 360),
                    "score": item.get("score"),
                    "local_href": item.get("local_href"),
                    "url": item.get("url"),
                }
            )
        )
        if len(output) >= 2:
            break
    if not output and source:
        output.append({"source_title": "Target paper", "snippet": _clip(source, 360), "score": 0.6})
    return output


def _evidence_chunks(roadmap: dict[str, Any]) -> list[dict[str, Any]]:
    evidence = roadmap.get("rag_evidence", [])
    if isinstance(evidence, dict):
        evidence = evidence.get("evidence", [])
    return [item for item in evidence if isinstance(item, dict)]


def _resource_links(roadmap: dict[str, Any], bundle_lookup: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    resources = list(roadmap.get("resource_library", []))
    if not resources:
        for phase in roadmap.get("phases", []):
            if isinstance(phase, dict):
                resources.extend(item for item in phase.get("resources", []) if isinstance(item, dict))
    for resource in resources:
        if not isinstance(resource, dict) or _is_target_resource(resource):
            continue
        bundle = _bundle_for_resource(resource, bundle_lookup)
        item = {
            "title": resource.get("title"),
            "url": resource.get("url"),
            "local_href": bundle.get("local_href") or resource.get("local_href"),
            "source": resource.get("source"),
            "type": resource.get("type"),
        }
        output.append(_sanitize(item))
    return output


def _task_links(roadmap: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in roadmap.get("study_tasks", []) if isinstance(item, dict)]


def _source_links(target: dict[str, Any], resources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = [_link_item(target, "Target paper")]
    output.extend(_link_item(item, str(item.get("title") or "Resource")) for item in resources[:8])
    return [item for item in output if item.get("href") or item.get("local_href") or item.get("url")]


def _bundle_lookup(study_bundle: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    lookup: dict[tuple[str, str], dict[str, Any]] = {}
    for item in study_bundle.get("resources", []) if isinstance(study_bundle, dict) else []:
        if not isinstance(item, dict):
            continue
        for key in ((str(item.get("title") or "").lower(), str(item.get("url") or "")), (str(item.get("title") or "").lower(), "")):
            lookup[key] = item
    return lookup


def _bundle_for_resource(resource: dict[str, Any], lookup: dict[tuple[str, str], dict[str, Any]]) -> dict[str, Any]:
    title = str(resource.get("title") or "").lower()
    url = str(resource.get("url") or "")
    return lookup.get((title, url)) or lookup.get((title, "")) or {}


def _link_item(item: dict[str, Any], label: str) -> dict[str, Any]:
    return {"label": label, "title": item.get("title"), "href": item.get("local_href") or item.get("url"), "local_href": item.get("local_href"), "url": item.get("url")}


def _node_label(kind: str, metadata: dict[str, Any], source: str, language: str) -> str:
    concepts = [str(item) for item in metadata.get("concepts", []) if item] if isinstance(metadata.get("concepts"), list) else []
    if kind == "background":
        return _clip(" / ".join(concepts[:3]) or _kind_label(kind, language), 90)
    if kind == "motivation":
        return _label(language, "motivation_label")
    if kind == "problem":
        return _label(language, "problem_label")
    if kind == "methodology":
        if "pddl" in source.lower():
            return "PDDL-Instruct + Logical CoT"
        return _clip(source or _kind_label(kind, language), 90)
    if kind == "experiment":
        if re.search(r"planbench|val", source, flags=re.I):
            return "PlanBench / VAL"
        return _clip(source or _kind_label(kind, language), 90)
    if kind == "contribution":
        return _label(language, "contribution_label")
    if kind == "limitation":
        return _label(language, "limitation_label")
    return _kind_label(kind, language)


def _plain_explanation(kind: str, source: str, metadata: dict[str, Any], language: str) -> str:
    if language == "en":
        return _english_plain(kind, source)
    if kind == "background":
        return f"这篇论文站在这些背景上：{_concept_phrase(metadata, source)}。先知道这些，后面的动机和方法才不会悬空。"
    if kind == "motivation":
        return "它的出发点是：大模型生成的计划看起来可能顺，但不一定真的满足动作前提、效果和状态变化约束。"
    if kind == "problem":
        return "它要解决的具体问题是：让模型不仅给出计划，还能说明每一步为什么在符号规划规则下合法。"
    if kind == "methodology":
        return f"方法可以直白理解为：把规划任务做成带逻辑推理过程的教学样例，让模型学习按状态、前提、效果一步步推。{_clip(source, 180)}"
    if kind == "experiment":
        return f"实验部分负责回答：这种训练到底有没有让计划更可执行。关键看 PlanBench、VAL 或 PDDL 风格验证。{_clip(source, 180)}"
    if kind == "contribution":
        return "贡献不是只说用了 CoT，而是把 CoT 变成可检查的规划逻辑轨迹，并用执行性验证证明它有帮助。"
    if kind == "limitation":
        return f"边界在于：轨迹质量、领域覆盖和长步规划都会影响效果，不能把结果无限外推。{_clip(source, 160)}"
    return _clip(source, 240)


def _english_plain(kind: str, source: str) -> str:
    templates = {
        "background": "This part names the field assumptions the paper relies on before the method makes sense.",
        "motivation": "This part explains the gap: fluent language output is not the same as a valid symbolic plan.",
        "problem": "This part turns the gap into a concrete question the method must solve.",
        "methodology": "This part describes the mechanism used to teach the model the planning process.",
        "experiment": "This part checks whether the method improves executable planning behavior.",
        "contribution": "This part states what the paper adds beyond prior work.",
        "limitation": "This part defines when the claim may not hold.",
    }
    return _clip(f"{templates.get(kind, '')} {source}", 260)


def _why_it_matters(kind: str, source: str, language: str) -> str:
    if language == "en":
        return "It is a load-bearing node in the paper's argument: removing it would make the next step less justified."
    zh = {
        "background": "它决定读者需要补哪些前置知识，避免被术语卡住。",
        "motivation": "它回答“为什么要写这篇论文”，是整篇文章的发动机。",
        "problem": "它把宽泛动机压成可验证的问题，后面的方法和实验都围绕它展开。",
        "methodology": "它是论文真正的技术核心，贡献是否成立主要看这里。",
        "experiment": "它把方法从想法变成证据，支撑论文的有效性主张。",
        "contribution": "它是用户汇报时必须讲清的“这篇论文到底新在哪里”。",
        "limitation": "它防止过度理解论文，帮助用户讲清适用边界。",
    }
    return zh.get(kind, _clip(source, 180))


def _connection_text(kind: str, language: str) -> str:
    if language == "en":
        return "Read this node together with its incoming and outgoing arrows."
    zh = {
        "background": "背景给动机提供前提：如果不了解符号规划约束，就看不出为什么普通文本生成不够。",
        "motivation": "动机把背景中的困难变成论文要补的空缺。",
        "problem": "问题定义约束了方法：方法必须让计划步骤可解释、可检查。",
        "methodology": "方法承接问题，并交给实验去验证是否真的有效。",
        "experiment": "实验把方法的效果转化成可报告的证据。",
        "contribution": "贡献由方法和实验共同支撑，同时受到局限节点约束。",
        "limitation": "局限反过来限定贡献能被相信到什么范围。",
    }
    return zh.get(kind, "")


def _talking_point(kind: str, label: str, language: str) -> str:
    if language == "en":
        return f"In a presentation, explain this as the paper's {kind}: {label}."
    zh = {
        "background": f"汇报时可以说：这篇论文建立在 {label} 这些背景上。",
        "motivation": "汇报时可以说：作者真正担心的是“会说”不等于“会做合法规划”。",
        "problem": "汇报时可以说：目标是让每一步计划都能对上规则，而不是只输出最终答案。",
        "methodology": f"汇报时可以说：核心方法是 {label}，用带逻辑轨迹的样例训练模型。",
        "experiment": f"汇报时可以说：实验用 {label} 这类验证来检查计划是否真能执行。",
        "contribution": "汇报时可以说：贡献是把逻辑 CoT 和符号规划执行性连接起来，并给出验证证据。",
        "limitation": "汇报时可以说：这套方法依赖轨迹质量和领域覆盖，长程/未见领域仍有风险。",
    }
    return zh.get(kind, f"汇报时围绕 {label} 讲清这一节点。")


def _concept_phrase(metadata: dict[str, Any], source: str) -> str:
    concepts = [str(item) for item in metadata.get("concepts", []) if item] if isinstance(metadata.get("concepts"), list) else []
    if concepts:
        return "、".join(concepts[:4])
    return _clip(source or "目标论文的核心术语", 120)


def _kind_label(kind: str, language: str) -> str:
    labels = {
        "background": ("Background", "背景"),
        "motivation": ("Motivation / Gap", "动机 / 缺口"),
        "problem": ("Problem", "问题"),
        "methodology": ("Methodology", "方法"),
        "experiment": ("Experiments", "实验"),
        "result": ("Results", "结果"),
        "contribution": ("Contributions", "贡献"),
        "limitation": ("Limitations", "局限"),
        "formula": ("Formula", "公式"),
        "resource": ("Resource", "资料"),
        "task": ("Task", "任务"),
        "evidence": ("Evidence", "证据"),
        "target": ("Target paper", "目标论文"),
    }
    en, zh = labels.get(kind, (kind, kind))
    return en if language == "en" else f"{en} / {zh}" if language == "bilingual" else zh


def _edge_label(label: str, language: str) -> str:
    labels = {
        "requires_background": ("requires background", "依赖背景"),
        "motivates": ("motivates", "引发动机"),
        "addresses": ("addresses", "回应问题"),
        "implements": ("implements", "形成贡献"),
        "evaluated_by": ("evaluated by", "由实验验证"),
        "supports": ("supports", "支撑"),
        "claims": ("claims", "主张"),
        "bounded_by": ("bounded by", "受局限约束"),
    }
    en, zh = labels.get(label, (label, label))
    return en if language == "en" else f"{en} / {zh}" if language == "bilingual" else zh


def _label(language: str, key: str) -> str:
    labels = {
        "paper_map_title": ("Paper Logic Map", "论文逻辑图"),
        "eyebrow": ("Xmind-style single-paper understanding map", "Xmind 式单篇论文理解图"),
        "open_lens": ("Open Paper Lens", "进入精读阅读器"),
        "open_paper": ("Open paper", "打开论文"),
        "open_resource": ("Open resource", "打开资料"),
        "open_local_or_source": ("Open local/source paper", "打开本地或原始论文"),
        "causal_chain": ("Causal chain", "论文因果主链"),
        "causal_note": ("Read left to right: background creates the gap, the method answers it, experiments support the contribution.", "从左到右读：背景引出缺口，方法回应问题，实验支撑贡献。"),
        "branches": ("Attached formulas, resources, and tasks", "挂接的公式、资料和任务"),
        "source_links": ("Source links", "资料入口"),
        "no_branch": ("No branch nodes yet.", "暂未生成支线节点。"),
        "plain": ("What this part says", "这部分在说什么"),
        "why": ("Why it matters", "为什么重要"),
        "connection": ("How it connects", "和前后节点怎么连"),
        "talking_point": ("Presentation wording", "汇报话术"),
        "evidence": ("Original evidence", "原文证据"),
        "confidence": ("Confidence", "置信度"),
        "evidence_count": ("Evidence", "证据"),
        "resources": ("Recommended resources", "推荐资料"),
        "no_resource": ("No direct resource", "暂无直接资料"),
        "evidence_missing": ("Evidence is insufficient; treat this node as a local heuristic.", "证据不足：这一节点来自本地规则推断，需要读原文复核。"),
        "target": ("Target paper", "目标论文"),
        "target_plain": ("Target paper for this map.", "这张图围绕目标论文生成。"),
        "target_why": ("The whole map exists to make this paper easier to explain and remember.", "整张图都是为了更快讲清并记住这篇论文。"),
        "target_connection": ("Core nodes explain how the paper's argument is assembled.", "核心节点解释论文论证是怎么拼起来的。"),
        "target_talk": ("Start with the map, then open Paper Lens for details.", "先讲逻辑图，再进入精读阅读器补细节。"),
        "motivation_label": ("Fluent text is not valid planning", "会说不等于会合法规划"),
        "problem_label": ("Make each planning step checkable", "让每一步规划可检查"),
        "contribution_label": ("Logical CoT improves planning validity", "逻辑 CoT 提升规划有效性"),
        "limitation_label": ("Trace quality and coverage limits", "轨迹质量与覆盖限制"),
        "formula_plain": ("This formula branch helps pin the method to a derivation or symbolic relation.", "公式支线用于把方法落到可推导的符号关系上。"),
        "resource_plain": ("This resource helps explain or verify the selected logic node.", "这份资料用于解释或验证图中的关键节点。"),
        "task_plain": ("This task turns understanding into checkable learning evidence.", "这个任务把理解转成可验收的学习证据。"),
        "branch_why": ("It shortens the path from seeing the map to checking the claim.", "它能缩短从看懂图到验证主张的路径。"),
        "branch_connection": ("It hangs off the nearest core node as supporting material.", "它作为支撑材料挂在最相关的核心节点上。"),
        "branch_talk": ("Use it when the audience asks for evidence or detail.", "听众追问证据或细节时再展开。"),
        "zoom_in": ("Zoom in", "放大"),
        "zoom_out": ("Zoom out", "缩小"),
        "fit_view": ("Fit view", "适应窗口"),
        "reset_layout": ("Reset layout", "重置布局"),
        "toggle_detail": ("Toggle detail", "收起/展开详情"),
        "collapse_branches": ("Collapse branches", "收起分支"),
        "expand_branches": ("Expand branches", "展开分支"),
        "show_all_branches": ("Show all nodes", "恢复全部节点"),
        "show_sources": ("Show source tags", "展开资料标签"),
        "hide_sources": ("Hide source tags", "收起资料标签"),
        "storage_unavailable": ("Local progress storage is unavailable; interactions still work temporarily.", "本地状态保存不可用；仍可临时交互查看。"),
    }
    en, zh = labels.get(key, (key.replace("_", " ").title(), key))
    return en if language == "en" else f"{en} / {zh}" if language == "bilingual" else zh


def _node_card(node: dict[str, Any], language: str, *, active: bool) -> str:
    classes = "paper-map-node active" if active else "paper-map-node"
    evidence_count = len([item for item in node.get("evidence", []) if isinstance(item, dict) and item.get("snippet")])
    return f"""
    <button type="button" class="{classes}" data-paper-map-node="{escape(str(node.get('id')))}">
      <strong>{escape(str(node.get('kind_label') or node.get('kind')))}</strong>
      <span>{escape(str(node.get('label') or ''))}</span>
      <p>{escape(_clip(str(node.get('plain_explanation') or ''), 120))}</p>
      <span class="paper-map-meta">{escape(_label(language, "confidence"))} {escape(str(node.get('confidence', '')))} · {escape(_label(language, "evidence_count"))} {evidence_count}</span>
    </button>
    """


def _edge_chip(edge: dict[str, Any]) -> str:
    return f'<span class="paper-map-edge" data-paper-map-edge="{escape(str(edge.get("id")))}">{escape(str(edge.get("localized_label") or edge.get("label")))}</span>'


def _graph_node_card(node: dict[str, Any], language: str, *, active: bool) -> str:
    layout = node.get("layout", {}) if isinstance(node.get("layout"), dict) else {}
    role = str(node.get("role") or node.get("kind") or "")
    kind = str(node.get("kind") or "")
    branch_group = str(layout.get("branch_group") or kind)
    classes = [
        "paper-map-node",
        f"paper-map-{role}-node",
        f"paper-map-{kind}-node",
    ]
    if role not in {"target", "core"}:
        classes.append("paper-map-branch-node")
    if active:
        classes.append("active")
    style = (
        f"left:{int(layout.get('x', 0))}px;"
        f"top:{int(layout.get('y', 0))}px;"
        f"width:{int(layout.get('width', 210))}px;"
        f"min-height:{int(layout.get('height', 110))}px;"
    )
    evidence_count = len([item for item in node.get("evidence", []) if isinstance(item, dict) and item.get("snippet")])
    toggle = ""
    if role == "core":
        toggle = f'<button type="button" class="paper-map-node-toggle" data-paper-map-expand-toggle="{escape(branch_group)}">{escape(_label(language, "collapse_branches"))}</button>'
    return f"""
    <article class="{' '.join(classes)}" style="{style}" data-paper-map-node-card data-node-id="{escape(str(node.get('id') or ''))}" data-branch-group="{escape(branch_group)}">
      <button type="button" class="paper-map-node-main" data-paper-map-node="{escape(str(node.get('id') or ''))}">
        <strong>{escape(str(node.get('kind_label') or node.get('kind') or ''))}</strong>
        <span>{escape(str(node.get('label') or ''))}</span>
        <p>{escape(_clip(str(node.get('plain_explanation') or ''), 118))}</p>
        <span class="paper-map-meta">{escape(_label(language, "confidence"))} {escape(str(node.get('confidence', '')))} · {escape(_label(language, "evidence_count"))} {evidence_count}</span>
      </button>
      {toggle}
    </article>
    """


def _svg_edge_path(edge: dict[str, Any], node_lookup: dict[str, dict[str, Any]]) -> str:
    source = node_lookup.get(str(edge.get("from") or ""))
    target = node_lookup.get(str(edge.get("to") or ""))
    path = _edge_path(source, target) if source and target else ""
    label = str(edge.get("localized_label") or edge.get("label") or "")
    return (
        f'<path class="paper-map-svg-edge paper-map-edge" data-paper-map-edge="{escape(str(edge.get("id") or ""))}" '
        f'data-edge-from="{escape(str(edge.get("from") or ""))}" data-edge-to="{escape(str(edge.get("to") or ""))}" '
        f'aria-label="{escape(label)}" marker-end="url(#paper-map-arrow)" d="{escape(path)}"></path>'
    )


def _edge_path(source: dict[str, Any] | None, target: dict[str, Any] | None) -> str:
    if not source or not target:
        return ""
    source_layout = source.get("layout", {}) if isinstance(source.get("layout"), dict) else {}
    target_layout = target.get("layout", {}) if isinstance(target.get("layout"), dict) else {}
    sx = int(source_layout.get("x", 0)) + int(source_layout.get("width", 210)) // 2
    sy = int(source_layout.get("y", 0)) + int(source_layout.get("height", 110)) // 2
    tx = int(target_layout.get("x", 0)) + int(target_layout.get("width", 210)) // 2
    ty = int(target_layout.get("y", 0)) + int(target_layout.get("height", 110)) // 2
    dx = max(90, int(abs(tx - sx) * 0.42))
    return f"M {sx} {sy} C {sx + dx} {sy}, {tx - dx} {ty}, {tx} {ty}"


def _graph_detail_html(node: dict[str, Any], language: str) -> str:
    evidence = "".join(
        f'<div class="paper-map-evidence"><strong>{escape(str(item.get("source_title") or item.get("file_name") or _label(language, "evidence")))}</strong><p>{escape(str(item.get("snippet") or item.get("note") or ""))}</p>{_detail_resource_link(item, language)}</div>'
        for item in node.get("evidence", [])
        if isinstance(item, dict)
    ) or f'<p class="paper-map-empty">{escape(_label(language, "evidence_missing"))}</p>'
    resources = " ".join(_detail_resource_link(item, language) for item in node.get("related_resources", []) if isinstance(item, dict))
    return f"""
      <h2>{escape(str(node.get('label') or ''))}</h2>
      <p class="paper-map-meta">{escape(str(node.get('kind_label') or node.get('kind') or ''))} · {escape(_label(language, "confidence"))} {escape(str(node.get('confidence') or ''))}</p>
      <div class="paper-map-detail-section"><strong>{escape(_label(language, "plain"))}</strong><p>{escape(str(node.get('plain_explanation') or ''))}</p></div>
      <div class="paper-map-detail-section"><strong>{escape(_label(language, "why"))}</strong><p>{escape(str(node.get('why_it_matters') or ''))}</p></div>
      <div class="paper-map-detail-section"><strong>{escape(_label(language, "connection"))}</strong><p>{escape(str(node.get('connection') or ''))}</p></div>
      <div class="paper-map-detail-section"><strong>{escape(_label(language, "talking_point"))}</strong><p>{escape(str(node.get('talking_point') or ''))}</p></div>
      <div class="paper-map-detail-section"><strong>{escape(_label(language, "evidence"))}</strong>{evidence}</div>
      <div class="paper-map-detail-section"><strong>{escape(_label(language, "resources"))}</strong><p>{resources or escape(_label(language, "no_resource"))}</p></div>
    """


def _detail_resource_link(item: dict[str, Any], language: str) -> str:
    href = str(item.get("local_href") or item.get("url") or item.get("href") or "")
    if not href:
        return ""
    label = str(item.get("label") or item.get("title") or _label(language, "open_resource"))
    return f'<a class="paper-map-action" href="{escape(href)}">{escape(_clip(label, 80))}</a>'


def _branch_card(node: dict[str, Any]) -> str:
    return f"""
    <article class="paper-map-branch">
      <h3>{escape(str(node.get('label') or ''))}</h3>
      <p class="paper-map-meta">{escape(str(node.get('kind_label') or node.get('kind')))}</p>
      <p>{escape(_clip(str(node.get('plain_explanation') or ''), 180))}</p>
    </article>
    """


def _source_link(item: dict[str, Any], language: str) -> str:
    href = str(item.get("href") or item.get("local_href") or item.get("url") or "")
    if not href:
        return ""
    label = str(item.get("label") or item.get("title") or _label(language, "open_resource"))
    return f'<a href="{escape(href)}">{escape(_clip(label, 80))}</a>'


def _target_link(target: dict[str, Any], language: str) -> str:
    href = str(target.get("local_href") or target.get("url") or "")
    if not href:
        return ""
    return f'<a class="paper-map-action" href="{escape(href)}">{escape(_label(language, "open_paper"))}</a>'


def _detail_html(node: dict[str, Any], language: str) -> str:
    evidence = "".join(
        f'<div class="paper-map-evidence"><strong>{escape(str(item.get("source_title") or item.get("file_name") or _label(language, "evidence")))}</strong><p>{escape(str(item.get("snippet") or item.get("note") or ""))}</p></div>'
        for item in node.get("evidence", [])
        if isinstance(item, dict)
    ) or f'<p class="paper-map-empty">{escape(_label(language, "evidence_missing"))}</p>'
    return f"""
      <h2>{escape(str(node.get('label') or ''))}</h2>
      <p class="paper-map-meta">{escape(str(node.get('kind_label') or node.get('kind') or ''))} · confidence {escape(str(node.get('confidence') or ''))}</p>
      <div class="paper-map-detail-section"><strong>{escape(_label(language, "plain"))}</strong><p>{escape(str(node.get('plain_explanation') or ''))}</p></div>
      <div class="paper-map-detail-section"><strong>{escape(_label(language, "why"))}</strong><p>{escape(str(node.get('why_it_matters') or ''))}</p></div>
      <div class="paper-map-detail-section"><strong>{escape(_label(language, "connection"))}</strong><p>{escape(str(node.get('connection') or ''))}</p></div>
      <div class="paper-map-detail-section"><strong>{escape(_label(language, "talking_point"))}</strong><p>{escape(str(node.get('talking_point') or ''))}</p></div>
      <div class="paper-map-detail-section"><strong>{escape(_label(language, "evidence"))}</strong>{evidence}</div>
    """


def _missing_evidence(language: str) -> dict[str, Any]:
    return {"source_title": _label(language, "evidence"), "snippet": _label(language, "evidence_missing"), "score": 0}


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text)).strip()
    return [_clip(item.strip(), 420) for item in re.split(r"(?<=[.!?。！？])\s+", normalized) if len(item.strip()) > 24]


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", str(text))}


def _resolve_language(option: str, roadmap: dict[str, Any]) -> str:
    if option in {"zh-CN", "en", "bilingual"}:
        return option
    profile = roadmap.get("profile", {}) if isinstance(roadmap.get("profile"), dict) else {}
    value = str(profile.get("output_language") or "zh-CN")
    return value if value in {"zh-CN", "en", "bilingual"} else "zh-CN"


def _normalize_depth(value: str) -> str:
    value = str(value or "standard").strip().lower()
    return value if value in {"quick", "standard", "complete"} else "standard"


def _compact_title(title: str) -> str:
    text = re.sub(r"\s+", " ", title).strip()
    if ":" in text:
        prefix = text.split(":", 1)[0].strip()
        if 6 <= len(prefix) <= 56:
            return prefix
    return _clip(text or "Target paper", 72)


def _clip(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", str(value)).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit)].rstrip()


def _sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: (None if key == "local_path" else _sanitize(child)) for key, child in value.items()}
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    if isinstance(value, str):
        return PRIVATE_PATH_RE.sub("[private local path]", value)
    return value


def _script_json_payload(value: str) -> str:
    return value.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")


def _html_lang(language: str) -> str:
    return "en" if language == "en" else "zh-CN"


def _empty_html(language: str) -> str:
    return f"<!doctype html><html lang=\"{escape(_html_lang(language))}\"><meta charset=\"utf-8\"><body>{escape(_label(language, 'paper_map_title'))}</body></html>"
