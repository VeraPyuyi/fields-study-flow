from __future__ import annotations

import copy
import json
import re
import shutil
from html import escape
from pathlib import Path
from typing import Any


FRONTEND_DIST_DIR = Path(__file__).with_name("frontend_dist")
FRONTEND_ASSET_DIR = "assets/study-flow-app"
PRIVATE_PATH_RE = re.compile(r"(?:file://[^\s)\]}\"'<]+|(?<![A-Za-z0-9])[A-Za-z]:[\\/][^)\]}\"'<\r\n]+|/(?:Users|home)/[^)\]}\"'<\r\n]+)")


def frontend_assets_available() -> bool:
    return _manifest_file(FRONTEND_DIST_DIR).exists()


def copy_frontend_assets(output_dir: Path) -> str | None:
    dist_dir = _dist_dir()
    if not dist_dir or not _manifest_file(dist_dir).exists():
        return None
    target = output_dir / FRONTEND_ASSET_DIR
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(dist_dir, target, dirs_exist_ok=True)
    return FRONTEND_ASSET_DIR


def render_frontend_report(report_kind: str, roadmap: dict[str, Any], *, asset_base: str | None = None) -> str:
    dist_dir = _dist_dir()
    if not dist_dir:
        raise FileNotFoundError("frontend build assets are not available")
    manifest = _load_manifest(dist_dir)
    entry = manifest.get("index.html") or next(iter(manifest.values()), {})
    script_file = str(entry.get("file") or "")
    css_files = [str(item) for item in entry.get("css", []) if item]
    if not script_file:
        raise FileNotFoundError("frontend manifest does not contain an entry script")
    asset_prefix = (asset_base or FRONTEND_ASSET_DIR).strip("/")
    safe_roadmap = _sanitize_private_values(copy.deepcopy(roadmap))
    payload = {
        "reportKind": report_kind,
        "roadmap": safe_roadmap,
    }
    json_payload = _script_json(json.dumps(payload, ensure_ascii=False))
    css_tags = "\n".join(f"  <style>{_style_text(_asset_text(dist_dir, css_file))}</style>" for css_file in css_files)
    fallback_style = _frontend_static_fallback_style()
    script_text = _inline_script_text(_asset_text(dist_dir, script_file))
    title = _report_title(report_kind, safe_roadmap)
    lang = _html_lang(safe_roadmap)
    fallback_html = _frontend_static_fallback_html(report_kind, safe_roadmap, lang)
    noscript_note = (
        "浏览器禁用了 JavaScript；上方静态入口仍可用于打开资料和辅助报告。"
        if lang != "en"
        else "JavaScript is disabled; the static entry above still links to the companion reports."
    )
    return f"""<!doctype html>
<html lang="{escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
{css_tags}
  <style>{fallback_style}</style>
</head>
<body>
  <div id="root" data-report-kind="{escape(report_kind)}">{fallback_html}</div>
  <noscript><p class="static-report-noscript">{escape(noscript_note)}</p></noscript>
  <script type="application/json" id="fields-study-flow-data">{json_payload}</script>
  <script>{script_text}</script>
</body>
</html>"""


def render_report_index(roadmap: dict[str, Any]) -> str:
    safe_roadmap = _sanitize_private_values(copy.deepcopy(roadmap))
    lang = _html_lang(safe_roadmap)
    is_zh = lang != "en"
    title = _display_report_base_title(safe_roadmap)
    path_strategy = safe_roadmap.get("path_strategy", {}) if isinstance(safe_roadmap.get("path_strategy"), dict) else {}
    profile = safe_roadmap.get("profile", {}) if isinstance(safe_roadmap.get("profile"), dict) else {}
    estimated_time = str(path_strategy.get("estimated_total_time") or ("待估计" if is_zh else "not estimated"))
    route_depth = str(path_strategy.get("mode") or profile.get("route_depth") or "balanced")
    selected_resources = str(path_strategy.get("selected_resources") or "-")
    goal = str(profile.get("goal") or safe_roadmap.get("title") or title)
    cards = _index_cards(safe_roadmap, is_zh)
    cards_html = "\n".join(_index_card_html(card) for card in cards)
    health_html = _report_health_panel_html(safe_roadmap, is_zh)
    scenario_html = _scenario_panel_html(is_zh)
    intent_router_html = _intent_router_panel_html(safe_roadmap, is_zh)
    market_value_html = _market_value_panel_html(safe_roadmap, is_zh)
    recommended_action_html = _recommended_action_panel_html(safe_roadmap, is_zh)
    first_session_html = _first_session_plan_panel_html(safe_roadmap, is_zh)
    outcome_contract_html = _learning_outcome_contract_panel_html(safe_roadmap, is_zh)
    learning_guide_html = _learning_guide_panel_html(safe_roadmap, is_zh)
    active_recall_html = _active_recall_panel_html(safe_roadmap, is_zh)
    heading = "从这里开始" if is_zh else "Start Here"
    subtitle = (
        "先看论文逻辑图，再做段落精读，最后按学习路线完成验收。"
        if is_zh
        else "Open the paper map first, then read focused paragraphs, then finish the mastery checklist."
    )
    goal_label = "学习目标" if is_zh else "Goal"
    time_label = "预计耗时" if is_zh else "Estimated Time"
    mode_label = "路线模式" if is_zh else "Route Mode"
    resource_label = "核心资料" if is_zh else "Core Resources"
    quickstart_html = _quickstart_panel_html(is_zh, bool(safe_roadmap.get("paper_map")), bool(safe_roadmap.get("paper_lens")))
    next_panel_html = _next_paper_panel_html(is_zh)
    secondary_guidance_html = _secondary_guidance_panel_html(
        is_zh,
        "\n".join(
            [
                market_value_html,
                outcome_contract_html,
                learning_guide_html,
                quickstart_html,
                intent_router_html,
                health_html,
                scenario_html,
                next_panel_html,
            ]
        ),
    )
    technical_label = "辅助文件" if is_zh else "Support Files"
    technical_note = (
        "JSON、Markdown 和 SVG 是给复查、分享或二次处理用的；普通学习优先打开上面的入口。"
        if is_zh
        else "JSON, Markdown, and SVG are support artifacts; learners should start with the cards above."
    )
    technical_summary = "需要原始数据或导出文件时再展开" if is_zh else "Open only when you need data or export files"
    return f"""<!doctype html>
<html lang="{escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - {escape(heading)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f3ed;
      --ink: #21201d;
      --muted: #6f6a61;
      --line: rgba(52, 47, 40, 0.14);
      --panel: rgba(255, 255, 255, 0.86);
      --accent: #2f6f73;
      --accent-2: #9b5a39;
      --shadow: 0 20px 60px rgba(47, 42, 35, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      font-family: "Microsoft YaHei UI", "Microsoft YaHei", "PingFang SC", "Noto Sans SC", "Source Han Sans SC", Arial, sans-serif;
      color: var(--ink);
      background:
        linear-gradient(135deg, rgba(47, 111, 115, 0.10), transparent 34%),
        linear-gradient(315deg, rgba(155, 90, 57, 0.10), transparent 34%),
        var(--bg);
      line-height: 1.65;
    }}
    main {{
      width: min(1120px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 48px 0;
    }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr);
      gap: 20px;
      align-items: stretch;
      margin-bottom: 22px;
    }}
    .hero-copy, .metric-panel, .start-card, .next-paper-panel, .scenario-panel, .support-panel, .secondary-guidance-panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }}
    .hero-copy {{
      border-radius: 28px;
      padding: clamp(24px, 4vw, 42px);
    }}
    .eyebrow {{
      margin: 0 0 10px;
      color: var(--accent);
      font-size: 0.82rem;
      font-weight: 800;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 0;
      max-width: 880px;
      font-size: clamp(2rem, 6vw, 4rem);
      line-height: 1.05;
      letter-spacing: 0;
      overflow-wrap: anywhere;
    }}
    .subtitle {{
      margin: 18px 0 0;
      max-width: 760px;
      color: var(--muted);
      font-size: clamp(1rem, 2vw, 1.18rem);
      overflow-wrap: anywhere;
    }}
    .metric-panel {{
      border-radius: 24px;
      padding: 22px;
      display: grid;
      gap: 12px;
    }}
    .metric {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 14px 16px;
      background: rgba(255, 255, 255, 0.55);
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 0.84rem;
    }}
    .metric strong {{
      display: block;
      margin-top: 4px;
      font-size: 1.05rem;
      overflow-wrap: anywhere;
    }}
    .start-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 16px;
      margin-top: 18px;
    }}
    .quickstart-panel {{
      margin: 0 0 18px;
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 18px;
      background: rgba(255, 255, 255, 0.76);
      box-shadow: 0 16px 46px rgba(47, 42, 35, 0.10);
    }}
    .learning-guide-panel {{
      margin: 0 0 18px;
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 18px;
      background: rgba(255, 255, 255, 0.78);
      box-shadow: 0 16px 46px rgba(47, 42, 35, 0.10);
    }}
    .active-recall-panel {{
      margin: 0 0 18px;
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 18px;
      background: rgba(255, 255, 255, 0.78);
      box-shadow: 0 16px 46px rgba(47, 42, 35, 0.10);
    }}
    .session-plan-panel {{
      margin: 0 0 18px;
      border: 1px solid rgba(47, 111, 115, 0.18);
      border-radius: 24px;
      padding: 18px;
      background:
        linear-gradient(135deg, rgba(47, 111, 115, 0.09), transparent 42%),
        rgba(255, 255, 255, 0.80);
      box-shadow: 0 16px 46px rgba(47, 42, 35, 0.10);
    }}
    .intent-router-panel {{
      margin: 0 0 18px;
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 18px;
      background: rgba(255, 255, 255, 0.76);
      box-shadow: 0 16px 46px rgba(47, 42, 35, 0.10);
    }}
    .quickstart-panel header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      margin-bottom: 14px;
    }}
    .intent-router-panel header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      margin-bottom: 14px;
    }}
    .learning-guide-panel header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      margin-bottom: 14px;
    }}
    .active-recall-panel header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      margin-bottom: 14px;
    }}
    .session-plan-panel header {{
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: start;
      margin-bottom: 14px;
    }}
    .quickstart-panel h2 {{
      margin: 0;
      font-size: clamp(1.15rem, 2vw, 1.55rem);
      line-height: 1.22;
      overflow-wrap: anywhere;
    }}
    .intent-router-panel h2 {{
      margin: 0;
      font-size: clamp(1.15rem, 2vw, 1.55rem);
      line-height: 1.22;
      overflow-wrap: anywhere;
    }}
    .learning-guide-panel h2 {{
      margin: 0;
      font-size: clamp(1.15rem, 2vw, 1.55rem);
      line-height: 1.22;
      overflow-wrap: anywhere;
    }}
    .active-recall-panel h2 {{
      margin: 0;
      font-size: clamp(1.15rem, 2vw, 1.55rem);
      line-height: 1.22;
      overflow-wrap: anywhere;
    }}
    .session-plan-panel h2 {{
      margin: 0;
      font-size: clamp(1.15rem, 2vw, 1.55rem);
      line-height: 1.22;
      overflow-wrap: anywhere;
    }}
    .quickstart-panel p {{
      margin: 4px 0 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .intent-router-panel p {{
      margin: 4px 0 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .learning-guide-panel p {{
      margin: 4px 0 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .active-recall-panel p {{
      margin: 4px 0 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .session-plan-panel p {{
      margin: 4px 0 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .quickstart-badge {{
      flex: 0 0 auto;
      border: 1px solid rgba(47, 111, 115, 0.22);
      border-radius: 999px;
      padding: 7px 11px;
      color: var(--accent);
      background: rgba(47, 111, 115, 0.08);
      font-size: 0.84rem;
      font-weight: 800;
      white-space: nowrap;
    }}
    .quickstart-steps {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .intent-router-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .learning-guide-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .active-recall-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
    }}
    .active-recall-actions a {{
      display: inline-flex;
      align-items: center;
      min-height: 36px;
      padding: 7px 11px;
      border: 1px solid rgba(47, 111, 115, 0.22);
      border-radius: 999px;
      color: var(--accent);
      background: rgba(255, 255, 255, 0.72);
      text-decoration: none;
      font-size: 0.88rem;
      font-weight: 750;
      overflow-wrap: anywhere;
    }}
    .active-recall-actions a:hover, .active-recall-actions a:focus-visible {{
      border-color: rgba(47, 111, 115, 0.5);
      box-shadow: 0 10px 22px rgba(47, 42, 35, 0.10);
      outline: none;
    }}
    .active-recall-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }}
    .session-plan-list {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }}
    .session-step {{
      display: flex;
      flex-direction: column;
      min-height: 168px;
      border: 1px solid rgba(47, 111, 115, 0.16);
      border-radius: 18px;
      padding: 14px;
      color: var(--ink);
      background: rgba(255, 255, 255, 0.68);
      text-decoration: none;
      transition: transform 0.16s ease, border-color 0.16s ease, box-shadow 0.16s ease;
    }}
    .session-step:hover, .session-step:focus-visible {{
      transform: translateY(-2px);
      border-color: rgba(47, 111, 115, 0.42);
      box-shadow: 0 14px 32px rgba(47, 42, 35, 0.10);
      outline: none;
    }}
    .session-step time {{
      width: fit-content;
      border: 1px solid rgba(47, 111, 115, 0.18);
      border-radius: 999px;
      padding: 4px 9px;
      color: var(--accent);
      background: rgba(47, 111, 115, 0.08);
      font-size: 0.78rem;
      font-weight: 900;
      white-space: nowrap;
    }}
    .session-step strong {{
      margin-top: 10px;
      font-size: 1rem;
      line-height: 1.3;
      overflow-wrap: anywhere;
    }}
    .session-step span {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 0.9rem;
      line-height: 1.55;
      overflow-wrap: anywhere;
    }}
    .session-step em {{
      margin-top: auto;
      color: var(--accent-2);
      font-size: 0.82rem;
      font-style: normal;
      font-weight: 800;
      overflow-wrap: anywhere;
    }}
    .quickstart-steps a, .quickstart-steps span {{
      display: block;
      min-height: 92px;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      color: inherit;
      background: rgba(255, 255, 255, 0.62);
      text-decoration: none;
      overflow-wrap: anywhere;
    }}
    .intent-card {{
      display: grid;
      gap: 7px;
      min-height: 132px;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      color: inherit;
      background: rgba(255, 255, 255, 0.62);
      text-decoration: none;
      overflow-wrap: anywhere;
      transition: transform 160ms ease, border-color 160ms ease, background 160ms ease;
    }}
    .learning-question-card {{
      display: grid;
      gap: 7px;
      min-height: 150px;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.64);
      overflow-wrap: anywhere;
    }}
    .recall-card {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 0;
      background: rgba(255, 255, 255, 0.64);
      overflow: hidden;
    }}
    .recall-card summary {{
      display: grid;
      gap: 6px;
      padding: 12px;
      cursor: pointer;
      list-style: none;
      overflow-wrap: anywhere;
    }}
    .recall-card summary::-webkit-details-marker {{ display: none; }}
    .recall-card summary::after {{
      content: "＋";
      justify-self: start;
      color: var(--accent);
      font-weight: 900;
    }}
    .recall-card[open] summary::after {{ content: "－"; }}
    .recall-card small {{
      color: var(--accent-2);
      font-weight: 900;
    }}
    .recall-card strong {{
      display: block;
      font-size: 0.98rem;
      line-height: 1.32;
      overflow-wrap: anywhere;
    }}
    .recall-card p {{
      padding: 0 12px 8px;
      margin: 0;
      color: var(--muted);
      font-size: 0.92rem;
    }}
    .recall-card a {{
      display: inline-block;
      margin: 0 12px 12px;
      color: var(--accent);
      font-weight: 800;
      text-decoration: none;
    }}
    .quickstart-steps a:hover, .quickstart-steps a:focus-visible {{
      border-color: rgba(47, 111, 115, 0.42);
      outline: none;
    }}
    .intent-card:hover, .intent-card:focus-visible {{
      transform: translateY(-2px);
      border-color: rgba(47, 111, 115, 0.42);
      background: rgba(255, 255, 255, 0.86);
      outline: none;
    }}
    .learning-question-card a {{
      color: var(--accent);
      font-weight: 800;
      text-decoration: none;
    }}
    .quickstart-steps small {{
      display: block;
      color: var(--accent-2);
      font-weight: 800;
    }}
    .intent-card small {{
      color: var(--accent);
      font-weight: 900;
    }}
    .learning-question-card small {{
      color: var(--accent-2);
      font-weight: 900;
    }}
    .quickstart-steps strong {{
      display: block;
      margin-top: 4px;
      font-size: 1rem;
    }}
    .intent-card strong {{
      display: block;
      font-size: 1rem;
      line-height: 1.28;
    }}
    .learning-question-card strong {{
      display: block;
      font-size: 1rem;
      line-height: 1.3;
      overflow-wrap: anywhere;
    }}
    .learning-question-card code {{
      display: block;
      border: 1px solid rgba(47, 111, 115, 0.16);
      border-radius: 12px;
      padding: 8px;
      color: #2d4f52;
      background: rgba(47, 111, 115, 0.07);
      white-space: normal;
      overflow-wrap: anywhere;
      font-size: 0.82rem;
      line-height: 1.45;
    }}
    .intent-card em {{
      align-self: end;
      color: var(--accent-2);
      font-size: 0.82rem;
      font-style: normal;
      font-weight: 800;
    }}
    .market-value-panel {{
      margin: 0 0 18px;
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 20px;
      background: rgba(255, 255, 255, 0.78);
      box-shadow: 0 16px 46px rgba(47, 42, 35, 0.10);
    }}
    .market-value-panel header {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: start;
      margin-bottom: 14px;
    }}
    .market-value-panel h2 {{
      margin: 0;
      font-size: clamp(1.15rem, 2vw, 1.55rem);
      line-height: 1.22;
      overflow-wrap: anywhere;
    }}
    .market-value-panel p {{
      margin: 4px 0 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .market-value-badge {{
      flex: 0 0 auto;
      border: 1px solid rgba(47, 111, 115, 0.22);
      border-radius: 999px;
      padding: 7px 11px;
      color: var(--accent);
      background: rgba(47, 111, 115, 0.08);
      font-size: 0.84rem;
      font-weight: 800;
      white-space: nowrap;
    }}
    .market-value-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }}
    .market-value-card {{
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.62);
      overflow-wrap: anywhere;
    }}
    .market-value-card span {{
      display: block;
      color: var(--accent-2);
      font-size: 0.78rem;
      font-weight: 900;
    }}
    .market-value-card strong {{
      display: block;
      margin-top: 5px;
      font-size: 1rem;
      line-height: 1.25;
    }}
    .market-value-card p {{
      margin-top: 7px;
      font-size: 0.92rem;
      line-height: 1.52;
    }}
    .recommended-action-panel {{
      margin: 0 0 18px;
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 20px;
      background: rgba(255, 255, 255, 0.80);
      box-shadow: 0 16px 46px rgba(47, 42, 35, 0.10);
    }}
    .recommended-action-panel header {{
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 14px;
    }}
    .recommended-action-panel h2 {{
      margin: 0;
      font-size: clamp(1.15rem, 2vw, 1.55rem);
      line-height: 1.22;
      overflow-wrap: anywhere;
    }}
    .recommended-action-panel p {{
      margin: 4px 0 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .recommended-action-badge {{
      flex: 0 0 auto;
      border: 1px solid rgba(155, 90, 57, 0.22);
      border-radius: 999px;
      padding: 7px 11px;
      color: var(--accent-2);
      background: rgba(155, 90, 57, 0.08);
      font-size: 0.84rem;
      font-weight: 800;
      white-space: nowrap;
    }}
    .recommended-action-grid {{
      display: grid;
      grid-template-columns: minmax(0, 1.15fr) minmax(280px, 0.85fr);
      gap: 12px;
      align-items: stretch;
    }}
    .recommended-action-primary {{
      display: grid;
      gap: 10px;
      border: 1px solid rgba(47, 111, 115, 0.22);
      border-radius: 18px;
      padding: 16px;
      color: inherit;
      text-decoration: none;
      background: linear-gradient(135deg, rgba(47, 111, 115, 0.10), rgba(255, 255, 255, 0.72));
      overflow-wrap: anywhere;
    }}
    .recommended-action-primary:hover, .recommended-action-primary:focus-visible {{
      transform: translateY(-1px);
      border-color: rgba(47, 111, 115, 0.45);
      outline: none;
    }}
    .recommended-action-primary small, .recommended-action-side small {{
      color: var(--accent);
      font-weight: 900;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}
    .recommended-action-primary strong {{
      font-size: 1.25rem;
      line-height: 1.22;
    }}
    .recommended-action-primary em {{
      color: var(--accent-2);
      font-style: normal;
      font-weight: 800;
    }}
    .recommended-action-side {{
      display: grid;
      gap: 9px;
    }}
    .recommended-action-side a {{
      display: grid;
      gap: 3px;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 11px 12px;
      color: inherit;
      background: rgba(255, 255, 255, 0.62);
      text-decoration: none;
      overflow-wrap: anywhere;
    }}
    .recommended-action-side strong {{
      line-height: 1.25;
    }}
    .recommended-action-side span {{
      color: var(--muted);
      font-size: 0.9rem;
    }}
    .outcome-contract-panel {{
      margin: 0 0 18px;
      border: 1px solid var(--line);
      border-radius: 24px;
      padding: 20px;
      background: rgba(255, 255, 255, 0.80);
      box-shadow: 0 16px 46px rgba(47, 42, 35, 0.10);
    }}
    .outcome-contract-panel header {{
      display: flex;
      align-items: start;
      justify-content: space-between;
      gap: 14px;
      margin-bottom: 14px;
    }}
    .outcome-contract-panel h2 {{
      margin: 0;
      font-size: clamp(1.15rem, 2vw, 1.55rem);
      line-height: 1.22;
      overflow-wrap: anywhere;
    }}
    .outcome-contract-panel p {{
      margin: 4px 0 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .outcome-contract-badge {{
      flex: 0 0 auto;
      border: 1px solid rgba(47, 111, 115, 0.22);
      border-radius: 999px;
      padding: 7px 11px;
      color: var(--accent);
      background: rgba(47, 111, 115, 0.08);
      font-size: 0.84rem;
      font-weight: 800;
      white-space: nowrap;
    }}
    .outcome-contract-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }}
    .outcome-card {{
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.62);
      overflow-wrap: anywhere;
    }}
    .outcome-card span {{
      display: block;
      color: var(--accent-2);
      font-size: 0.78rem;
      font-weight: 900;
    }}
    .outcome-card strong {{
      display: block;
      margin-top: 5px;
      font-size: 1rem;
      line-height: 1.25;
    }}
    .outcome-card p {{
      margin-top: 7px;
      font-size: 0.92rem;
      line-height: 1.52;
    }}
    .outcome-proof-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 14px;
    }}
    .outcome-proof-row a, .outcome-proof-row span {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 7px 10px;
      color: inherit;
      background: rgba(255, 255, 255, 0.68);
      text-decoration: none;
      font-size: 0.9rem;
      font-weight: 800;
      overflow-wrap: anywhere;
    }}
    .report-health-panel, .start-card {{
      display: flex;
      flex-direction: column;
      min-height: 230px;
      border-radius: 22px;
      padding: 22px;
      color: inherit;
      text-decoration: none;
      transition: transform 160ms ease, border-color 160ms ease, box-shadow 160ms ease;
    }}
    .start-card:hover, .start-card:focus-visible {{
      transform: translateY(-3px);
      border-color: rgba(47, 111, 115, 0.42);
      box-shadow: 0 24px 70px rgba(47, 42, 35, 0.16);
      outline: none;
    }}
    .start-card small {{
      color: var(--accent-2);
      font-weight: 800;
    }}
    .start-card h2 {{
      margin: 16px 0 8px;
      font-size: 1.35rem;
      line-height: 1.22;
      overflow-wrap: anywhere;
    }}
    .start-card p {{
      margin: 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .start-card strong {{
      margin-top: auto;
      padding-top: 18px;
      color: var(--accent);
    }}
    .report-health-panel {{
      margin: 0 0 18px;
      min-height: auto;
      background: rgba(255, 255, 255, 0.80);
      border: 1px solid var(--line);
      box-shadow: 0 16px 46px rgba(47, 42, 35, 0.10);
    }}
    .report-health-panel header {{
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: start;
      margin-bottom: 14px;
    }}
    .report-health-panel h2 {{
      margin: 0;
      font-size: clamp(1.15rem, 2vw, 1.55rem);
      line-height: 1.22;
      overflow-wrap: anywhere;
    }}
    .report-health-panel p {{
      margin: 4px 0 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .report-health-link {{
      flex: 0 0 auto;
      border: 1px solid rgba(47, 111, 115, 0.22);
      border-radius: 999px;
      padding: 7px 11px;
      color: var(--accent);
      background: rgba(47, 111, 115, 0.08);
      font-size: 0.84rem;
      font-weight: 800;
      text-decoration: none;
      white-space: nowrap;
    }}
    .report-health-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
    }}
    .report-health-card {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.62);
      overflow-wrap: anywhere;
    }}
    .report-health-card span {{
      display: block;
      color: var(--accent-2);
      font-size: 0.82rem;
      font-weight: 800;
    }}
    .report-health-card strong {{
      display: block;
      margin-top: 4px;
      color: var(--ink);
      font-size: 1.1rem;
    }}
    .report-health-card small {{
      display: block;
      margin-top: 6px;
      color: var(--muted);
      line-height: 1.45;
    }}
    .scenario-panel {{
      margin: 0 0 18px;
      border-radius: 24px;
      padding: 20px 22px;
    }}
    .scenario-panel h2 {{
      margin: 0;
      font-size: clamp(1.15rem, 2vw, 1.55rem);
      line-height: 1.22;
      overflow-wrap: anywhere;
    }}
    .scenario-panel > p {{
      margin: 6px 0 14px;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .scenario-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }}
    .scenario-card {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.62);
      overflow-wrap: anywhere;
    }}
    .scenario-card span {{
      display: block;
      color: var(--accent-2);
      font-size: 0.82rem;
      font-weight: 800;
    }}
    .scenario-card strong {{
      display: block;
      margin-top: 5px;
      font-size: 1.02rem;
    }}
    .scenario-card p {{
      margin: 7px 0 10px;
      color: var(--muted);
      font-size: 0.93rem;
    }}
    .scenario-card code {{
      display: block;
      border-radius: 12px;
      padding: 9px;
      background: rgba(33, 32, 29, 0.06);
      color: var(--ink);
      font-family: Consolas, "SFMono-Regular", "Liberation Mono", monospace;
      font-size: 0.82rem;
      line-height: 1.45;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }}
    .next-paper-panel {{
      margin-top: 16px;
      border-radius: 24px;
      padding: 22px;
      display: grid;
      grid-template-columns: minmax(0, 0.9fr) minmax(280px, 1.1fr);
      gap: 18px;
      align-items: start;
    }}
    .next-paper-panel h2 {{
      margin: 0 0 8px;
      font-size: clamp(1.4rem, 3vw, 2rem);
      line-height: 1.18;
      overflow-wrap: anywhere;
    }}
    .next-paper-panel p {{
      margin: 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .command-grid {{
      display: grid;
      gap: 10px;
    }}
    .command-grid article {{
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.58);
    }}
    .command-grid span {{
      display: block;
      margin-bottom: 6px;
      color: var(--accent-2);
      font-size: 0.82rem;
      font-weight: 800;
    }}
    .command-grid code {{
      display: block;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
      color: var(--ink);
      font-family: Consolas, "SFMono-Regular", "Liberation Mono", monospace;
      font-size: 0.9rem;
      line-height: 1.5;
    }}
    .next-paper-note {{
      grid-column: 1 / -1;
      padding-top: 2px;
      font-size: 0.92rem;
    }}
    .secondary-guidance-panel {{
      margin-top: 16px;
      border-radius: 22px;
      padding: 20px 22px;
    }}
    .secondary-guidance-panel summary {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      cursor: pointer;
      list-style: none;
      overflow-wrap: anywhere;
    }}
    .secondary-guidance-panel summary::-webkit-details-marker {{
      display: none;
    }}
    .secondary-guidance-panel summary::after {{
      content: "+";
      flex: 0 0 auto;
      width: 28px;
      height: 28px;
      border: 1px solid var(--line);
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: var(--accent);
      background: rgba(255, 255, 255, 0.62);
      font-weight: 900;
    }}
    .secondary-guidance-panel[open] summary::after {{
      content: "-";
    }}
    .secondary-guidance-panel summary span {{
      display: block;
    }}
    .secondary-guidance-panel summary strong {{
      display: block;
      margin-top: 3px;
      font-size: 1rem;
      line-height: 1.35;
    }}
    .secondary-guidance-note {{
      margin: 12px 0 0;
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .secondary-guidance-content {{
      margin-top: 16px;
    }}
    .support-panel {{
      margin-top: 16px;
      border-radius: 22px;
      padding: 20px 22px;
    }}
    .support-panel summary {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 14px;
      cursor: pointer;
      list-style: none;
      overflow-wrap: anywhere;
    }}
    .support-panel summary::-webkit-details-marker {{
      display: none;
    }}
    .support-panel summary::after {{
      content: "+";
      flex: 0 0 auto;
      width: 28px;
      height: 28px;
      border: 1px solid var(--line);
      border-radius: 999px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      color: var(--accent);
      background: rgba(255, 255, 255, 0.62);
      font-weight: 900;
    }}
    .support-panel[open] summary::after {{
      content: "-";
    }}
    .support-panel summary span {{
      display: block;
    }}
    .support-panel summary strong {{
      display: block;
      margin-top: 3px;
      font-size: 1rem;
      line-height: 1.35;
    }}
    .support-panel p {{
      margin: 12px 0;
      color: var(--muted);
    }}
    .support-links {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .support-links a {{
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 8px 12px;
      color: var(--ink);
      background: rgba(255, 255, 255, 0.62);
      text-decoration: none;
    }}
    .support-links a:hover, .support-links a:focus-visible {{
      border-color: rgba(47, 111, 115, 0.42);
      color: var(--accent);
      outline: none;
    }}
    @media (max-width: 820px) {{
      main {{ width: min(100vw - 22px, 720px); padding: 24px 0; }}
      .hero, .start-grid, .intent-router-grid, .learning-guide-grid, .active-recall-grid, .session-plan-list, .quickstart-steps, .next-paper-panel, .report-health-grid, .scenario-grid, .market-value-grid, .recommended-action-grid, .outcome-contract-grid {{ grid-template-columns: 1fr; }}
      .hero-copy {{ border-radius: 22px; }}
      .start-card {{ min-height: auto; }}
      .intent-router-panel header {{ display: block; }}
      .learning-guide-panel header {{ display: block; }}
      .active-recall-panel header {{ display: block; }}
      .session-plan-panel header {{ display: block; }}
      .quickstart-panel header {{ display: block; }}
      .market-value-panel header {{ display: block; }}
      .recommended-action-panel header {{ display: block; }}
      .outcome-contract-panel header {{ display: block; }}
      .report-health-panel header {{ display: block; }}
      .quickstart-badge {{ display: inline-block; margin-top: 10px; }}
      .market-value-badge {{ display: inline-block; margin-top: 10px; }}
      .recommended-action-badge {{ display: inline-block; margin-top: 10px; }}
      .outcome-contract-badge {{ display: inline-block; margin-top: 10px; }}
      .report-health-link {{ display: inline-block; margin-top: 10px; }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero" aria-labelledby="start-title">
      <div class="hero-copy">
        <p class="eyebrow">fields-study-flow</p>
        <h1 id="start-title">{escape(heading)}</h1>
        <p class="subtitle">{escape(subtitle)}</p>
        <p class="subtitle"><strong>{escape(goal_label)}：</strong>{escape(_truncate(goal, 260))}</p>
      </div>
      <aside class="metric-panel" aria-label="{escape('报告概览' if is_zh else 'Report overview')}">
        <div class="metric"><span>{escape(time_label)}</span><strong>{escape(estimated_time)}</strong></div>
        <div class="metric"><span>{escape(mode_label)}</span><strong>{escape(route_depth)}</strong></div>
        <div class="metric"><span>{escape(resource_label)}</span><strong>{escape(selected_resources)}</strong></div>
      </aside>
    </section>
    {recommended_action_html}
    {first_session_html}
    {active_recall_html}
    <section class="start-grid" aria-label="{escape('推荐入口' if is_zh else 'Recommended entries')}">
      {cards_html}
    </section>
    {secondary_guidance_html}
    <details class="support-panel" data-support-files-panel="collapsed">
      <summary id="support-files">
        <span>
          <span class="eyebrow">{escape(technical_label)}</span>
          <strong>{escape(technical_summary)}</strong>
        </span>
      </summary>
      <p>{escape(technical_note)}</p>
      <div class="support-links">
        <a href="roadmap.json">roadmap.json</a>
        <a href="roadmap.md">roadmap.md</a>
        <a href="roadmap.svg">roadmap.svg</a>
        <a href="study_cards.md">study_cards.md</a>
        <a href="study_quiz.md">study_quiz.md</a>
        <a href="mastery_worksheet.md">mastery_worksheet.md</a>
        <a href="quick_brief.md">quick_brief.md</a>
        <a href="evidence_coverage.md">evidence_coverage.md</a>
        <a href="evidence_coverage.html">evidence_coverage.html</a>
      </div>
    </details>
  </main>
</body>
</html>"""


def _secondary_guidance_panel_html(is_zh: bool, content_html: str) -> str:
    label = "更多说明与检查" if is_zh else "More guidance and checks"
    summary = (
        "已收起：产品价值、学习结果、问答向导、10 分钟入门、审计状态、场景说明和换论文命令"
        if is_zh
        else "Collapsed: value, outcomes, starter questions, 10-minute quickstart, audit status, scenarios, and bring-your-own-paper commands"
    )
    note = (
        "先按上面的第一轮学习会话开始；需要解释项目为什么这样设计、检查报告健康状态或换成自己的论文时，再展开这里。"
        if is_zh
        else "Start with the first study session above. Open this when you need product rationale, report health, alternate entry paths, or commands for your own paper."
    )
    return f"""<details class="secondary-guidance-panel" data-secondary-guidance-panel="collapsed">
      <summary id="secondary-guidance">
        <span>
          <span class="eyebrow">{escape(label)}</span>
          <strong>{escape(summary)}</strong>
        </span>
      </summary>
      <p class="secondary-guidance-note">{escape(note)}</p>
      <div class="secondary-guidance-content">
        {content_html}
      </div>
    </details>"""


def _index_cards(roadmap: dict[str, Any], is_zh: bool) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    if roadmap.get("paper_map"):
        cards.append(
            {
                "step": "01",
                "href": "paper_map.html",
                "title": "先看论文逻辑图" if is_zh else "Open the Paper Map",
                "body": "用 XMind 式主链抓住背景、动机、问题、方法、实验、贡献和局限。" if is_zh else "Use the causal map to understand background, motivation, method, experiments, contributions, and limits.",
                "cta": "进入论文逻辑图" if is_zh else "Open Paper Map",
            }
        )
    if roadmap.get("paper_lens"):
        cards.append(
            {
                "step": f"{len(cards) + 1:02d}",
                "href": "paper_lens.html",
                "title": "再做段落精读" if is_zh else "Read Key Paragraphs",
                "body": "把原文段落、直白解释、证据和资料放在一起，减少来回查资料。" if is_zh else "Read source paragraphs with plain explanations, evidence, and supporting materials together.",
                "cta": "进入段落精读" if is_zh else "Open Paper Lens",
            }
        )
    cards.append(
        {
            "step": f"{len(cards) + 1:02d}",
            "href": "roadmap.html",
            "title": "最后按路线验收" if is_zh else "Finish the Roadmap",
            "body": "按阶段完成资料、任务和掌握证据，确认自己真的能解释、推导、复现和批判。" if is_zh else "Complete phases, tasks, and mastery evidence for explain, derive, reproduce, and critique.",
            "cta": "进入学习路线" if is_zh else "Open Roadmap",
        }
    )
    return cards


def _index_card_html(card: dict[str, str]) -> str:
    return f"""<a class="start-card" href="{escape(card['href'])}">
        <small>{escape(card['step'])}</small>
        <h2>{escape(card['title'])}</h2>
        <p>{escape(card['body'])}</p>
        <strong>{escape(card['cta'])}</strong>
      </a>"""


def _market_value_panel_html(roadmap: dict[str, Any], is_zh: bool) -> str:
    has_paper_map = bool(roadmap.get("paper_map"))
    has_paper_lens = bool(roadmap.get("paper_lens"))
    title = "为什么它不只是 PDF 总结器" if is_zh else "Why this is more than a PDF summarizer"
    body = (
        "它把论文或领域目标变成可点击的学习结构、证据、资料包和验收任务，减少“看过但讲不清、资料散落、无法复现”的学习摩擦。"
        if is_zh
        else "It turns a paper or field goal into a clickable learning structure, evidence, a local bundle, and checkable mastery tasks."
    )
    badge = "差异化价值" if is_zh else "Differentiated value"
    map_title = "先看目标逻辑图" if is_zh else "Start with the target logic"
    map_body = (
        "像 roadmap.sh 和 React Flow 一样可视化，但节点来自你的论文或学习目标。"
        if is_zh
        else "Visual like roadmap.sh and React Flow, but generated from your paper or learning goal."
    )
    if has_paper_map:
        map_title = "先看论文逻辑图" if is_zh else "Start with the Paper Map"
        map_body = (
            "把背景、动机、问题、方法、实验、贡献和局限串成一条可点击主链。"
            if is_zh
            else "Connect background, motivation, problem, method, experiments, contributions, and limits in one clickable chain."
        )
    evidence_title = "再读证据精读层" if is_zh else "Read with evidence nearby"
    evidence_body = (
        "吸收 Explainpaper 和 PaperQA2 的优点：解释要直白，结论要能回到证据。"
        if is_zh
        else "Borrow the best of Explainpaper and PaperQA2: plain explanations with traceable evidence."
    )
    if not has_paper_lens:
        evidence_body = (
            "把关键概念、资源和任务绑定到证据，避免只给一堆泛泛链接。"
            if is_zh
            else "Tie concepts, resources, and tasks to evidence instead of leaving learners with a loose link list."
        )
    items = [
        {
            "reference": "roadmap.sh / React Flow",
            "title": map_title,
            "body": map_body,
        },
        {
            "reference": "Explainpaper / PaperQA2",
            "title": evidence_title,
            "body": evidence_body,
        },
        {
            "reference": "NotebookLM / Elicit",
            "title": "带走本地资料包" if is_zh else "Keep a local study bundle",
            "body": (
                "能下载、复制、快照或生成的资料优先落地到本地，减少反复找链接。"
                if is_zh
                else "Download, copy, snapshot, or generate usable resources locally so learners stop hunting links."
            ),
        },
        {
            "reference": "Get It",
            "title": "最后留下验收证据" if is_zh else "End with mastery proof",
            "body": (
                "不是读完就结束，而是产出解释、推导、复现和批判这些可检查结果。"
                if is_zh
                else "Do not stop at reading; produce explain, derive, reproduce, and critique evidence."
            ),
        },
    ]
    cards = "\n".join(
        f"""<article class="market-value-card">
          <span>{escape(item["reference"])}</span>
          <strong>{escape(item["title"])}</strong>
          <p>{escape(item["body"])}</p>
        </article>"""
        for item in items
    )
    return f"""<section class="market-value-panel" data-market-value-panel="true" aria-labelledby="market-value-title">
      <header>
        <div>
          <h2 id="market-value-title">{escape(title)}</h2>
          <p>{escape(body)}</p>
        </div>
        <span class="market-value-badge">{escape(badge)}</span>
      </header>
      <div class="market-value-grid">{cards}</div>
    </section>"""


def _recommended_action_panel_html(roadmap: dict[str, Any], is_zh: bool) -> str:
    has_paper_map = bool(roadmap.get("paper_map"))
    has_paper_lens = bool(roadmap.get("paper_lens"))
    if has_paper_map:
        href = "paper_map.html"
        title = "第一步：打开论文逻辑图" if is_zh else "First step: open the Paper Map"
        reason = (
            "先用一张图看清背景、动机、问题、方法、实验、贡献和局限，再决定要不要精读。"
            if is_zh
            else "Use one map to see background, motivation, problem, method, experiments, contributions, and limits before deep reading."
        )
        payoff = "最快建立论文主线" if is_zh else "Fastest way to build the paper logic"
    elif has_paper_lens:
        href = "paper_lens.html"
        title = "第一步：读关键段落" if is_zh else "First step: read the key paragraphs"
        reason = (
            "从原文段落和直白解释开始，先把论文讲清楚，再进入任务验收。"
            if is_zh
            else "Start from source paragraphs plus plain explanations, then move into validation tasks."
        )
        payoff = "最快进入理解状态" if is_zh else "Fastest way to start understanding"
    else:
        href = "roadmap.html"
        title = "第一步：打开学习路线" if is_zh else "First step: open the roadmap"
        reason = (
            "先看阶段、资料和验收任务，按最短路径补齐核心知识。"
            if is_zh
            else "Start with phases, resources, and validation tasks to fill the core knowledge path."
        )
        payoff = "最快开始执行" if is_zh else "Fastest way to start doing"
    heading = "推荐第一步" if is_zh else "Recommended first action"
    body = (
        "如果你只想马上开始，不需要先研究报告结构，直接点下面这个入口。"
        if is_zh
        else "If you want to start immediately, use this entry before learning the report structure."
    )
    badge = "新用户优先" if is_zh else "Fresh-user priority"
    alternatives = [
        {
            "href": "paper_lens.html" if has_paper_lens else "roadmap.html",
            "label": "如果要汇报" if is_zh else "For presentation",
            "title": "看段落解释和证据" if is_zh else "Use paragraph explanations",
            "body": "把原文、解释、证据连起来。" if is_zh else "Connect source text, explanation, and evidence.",
        },
        {
            "href": "roadmap.html",
            "label": "如果要掌握" if is_zh else "For mastery",
            "title": "做验收任务" if is_zh else "Do validation tasks",
            "body": "留下解释、推导、复现和批判证据。" if is_zh else "Leave explain, derive, reproduce, and critique evidence.",
        },
        {
            "href": "#next-paper-title",
            "label": "如果要换论文" if is_zh else "For your own paper",
            "title": "复制生成命令" if is_zh else "Copy the generation command",
            "body": "把示例 URL 或 PDF 路径换成自己的。" if is_zh else "Replace the example URL or PDF path with yours.",
        },
    ]
    alternative_html = "\n".join(
        f"""<a href="{escape(item["href"])}">
            <small>{escape(item["label"])}</small>
            <strong>{escape(item["title"])}</strong>
            <span>{escape(item["body"])}</span>
          </a>"""
        for item in alternatives
    )
    return f"""<section class="recommended-action-panel" data-recommended-action-panel="true" aria-labelledby="recommended-action-title">
      <header>
        <div>
          <p class="eyebrow">{escape('下一步' if is_zh else 'Next click')}</p>
          <h2 id="recommended-action-title">{escape(heading)}</h2>
          <p>{escape(body)}</p>
        </div>
        <span class="recommended-action-badge">{escape(badge)}</span>
      </header>
      <div class="recommended-action-grid">
        <a class="recommended-action-primary" data-recommended-first-action="true" href="{escape(href)}">
          <small>{escape(payoff)}</small>
          <strong>{escape(title)}</strong>
          <p>{escape(reason)}</p>
          <em>{escape('立即进入' if is_zh else 'Open now')}</em>
        </a>
        <div class="recommended-action-side">
          {alternative_html}
        </div>
      </div>
    </section>"""


def _learning_outcome_contract_panel_html(roadmap: dict[str, Any], is_zh: bool) -> str:
    task_types = {
        str(item.get("type") or item.get("task_type") or "").lower()
        for item in roadmap.get("study_tasks", [])
        if isinstance(item, dict)
    }
    required = {"explain", "derive", "reproduce", "critique"}
    covered = len(task_types & required)
    title = "学完后你应该能交付什么" if is_zh else "What you should be able to deliver"
    body = (
        "把“看懂了”拆成可检查的结果：能讲清、能推导、能复现、能批判。缺哪一项，就按学习路线补哪一项。"
        if is_zh
        else "Turn 'I understood it' into checkable outputs: explain, derive, reproduce, and critique. If one is missing, use the roadmap to fill it."
    )
    badge = (f"{covered}/4 项已覆盖" if is_zh else f"{covered}/4 covered") if task_types else ("等待任务生成" if is_zh else "tasks pending")
    outcomes = [
        {
            "key": "explain",
            "label": "Explain" if not is_zh else "讲清楚",
            "title": "3 分钟讲明白论文主线" if is_zh else "Explain the paper in 3 minutes",
            "body": "能说出背景、动机、问题、方法、实验、贡献和局限。" if is_zh else "State the background, motivation, problem, method, experiments, contributions, and limits.",
        },
        {
            "key": "derive",
            "label": "Derive" if not is_zh else "推出来",
            "title": "推导一个关键机制" if is_zh else "Derive one key mechanism",
            "body": "把核心公式、状态转移、损失函数或算法步骤拆成自己的话。" if is_zh else "Break down the core formula, state transition, objective, or algorithm step in your own words.",
        },
        {
            "key": "reproduce",
            "label": "Reproduce" if not is_zh else "做出来",
            "title": "留下最小复现实验记录" if is_zh else "Leave a minimal reproduction log",
            "body": "运行或设计一个最小实验，记录输入、输出、失败点和验证证据。" if is_zh else "Run or design a small experiment and record inputs, outputs, failures, and validation evidence.",
        },
        {
            "key": "critique",
            "label": "Critique" if not is_zh else "能批判",
            "title": "说明适用边界和不足" if is_zh else "Explain boundaries and limitations",
            "body": "指出方法在哪些数据、假设、任务或评价方式下可能失效。" if is_zh else "Identify where the method may fail across data, assumptions, tasks, or evaluation choices.",
        },
    ]
    cards = "\n".join(
        f"""<article class="outcome-card" data-outcome="{escape(item["key"])}">
          <span>{escape(item["label"])}</span>
          <strong>{escape(item["title"])}</strong>
          <p>{escape(item["body"])}</p>
        </article>"""
        for item in outcomes
    )
    proof_links: list[tuple[str, str]] = []
    if roadmap.get("paper_map"):
        proof_links.append(("paper_map.html", "论文逻辑图" if is_zh else "Paper Map"))
    if roadmap.get("paper_lens"):
        proof_links.append(("paper_lens.html", "段落精读" if is_zh else "Paper Lens"))
    proof_links.append(("roadmap.html", "验收清单" if is_zh else "Mastery checklist"))
    proof_html = "\n".join(f'<a href="{escape(href)}">{escape(label)}</a>' for href, label in proof_links)
    return f"""<section class="outcome-contract-panel" data-learning-outcome-contract="true" aria-labelledby="outcome-contract-title">
      <header>
        <div>
          <p class="eyebrow">{escape('学习结果契约' if is_zh else 'Outcome contract')}</p>
          <h2 id="outcome-contract-title">{escape(title)}</h2>
          <p>{escape(body)}</p>
        </div>
        <span class="outcome-contract-badge">{escape(badge)}</span>
      </header>
      <div class="outcome-contract-grid">
        {cards}
      </div>
      <div class="outcome-proof-row" aria-label="{escape('相关验收入口' if is_zh else 'Related validation entries')}">
        {proof_html}
      </div>
    </section>"""


def _learning_guide_panel_html(roadmap: dict[str, Any], is_zh: bool) -> str:
    title = "三问上手" if is_zh else "3 starter questions"
    body = (
        "不想先研究界面时，直接按这三个问题读。每个问题都指向一个页面，也给出本地资料包问答命令。"
        if is_zh
        else "If you do not want to learn the interface first, start with these questions. Each one points to a page and a local-bundle Q&A command."
    )
    badge = "像导师一样开场" if is_zh else "guided start"
    questions = _starter_questions(roadmap, is_zh)
    cards = "\n".join(_starter_question_card_html(item, is_zh) for item in questions)
    return f"""<section class="learning-guide-panel" data-learning-guide-panel="starter-questions" aria-labelledby="learning-guide-title">
      <header>
        <div>
          <p class="eyebrow">{escape('学习向导' if is_zh else 'Learning guide')}</p>
          <h2 id="learning-guide-title">{escape(title)}</h2>
          <p>{escape(body)}</p>
        </div>
        <span class="quickstart-badge">{escape(badge)}</span>
      </header>
      <div class="learning-guide-grid">
        {cards}
      </div>
    </section>"""


def _first_session_plan_panel_html(roadmap: dict[str, Any], is_zh: bool) -> str:
    steps = _first_session_steps(roadmap, is_zh)
    total_minutes = sum(int(step["minutes"]) for step in steps)
    title = "第一轮学习会话" if is_zh else "First study session"
    body = (
        "如果只想立刻开始，按这条时间盒走一遍：先抓主线，再读证据，再闭卷回忆，最后留下一个可验收结果。"
        if is_zh
        else "If you want to start immediately, follow this timebox: map the logic, read evidence, recall from memory, then leave one checkable result."
    )
    badge = f"约 {total_minutes} 分钟" if is_zh else f"about {total_minutes} min"
    step_html = "\n".join(_session_step_card_html(step, is_zh) for step in steps)
    return f"""<section class="session-plan-panel" data-first-session-plan="true" aria-labelledby="first-session-title">
      <header>
        <div>
          <p class="eyebrow">{escape('今日开始' if is_zh else 'Start today')}</p>
          <h2 id="first-session-title">{escape(title)}</h2>
          <p>{escape(body)}</p>
        </div>
        <span class="quickstart-badge">{escape(badge)}</span>
      </header>
      <div class="session-plan-list">
        {step_html}
      </div>
    </section>"""


def _first_session_steps(roadmap: dict[str, Any], is_zh: bool) -> list[dict[str, str | int]]:
    has_map = bool(roadmap.get("paper_map"))
    has_lens = bool(roadmap.get("paper_lens"))
    profile = roadmap.get("profile", {}) if isinstance(roadmap.get("profile"), dict) else {}
    target_kind = str(profile.get("target_kind") or roadmap.get("target_kind") or "").lower()
    is_field_route = target_kind in {"field", "course"}
    is_paper = bool(has_map or has_lens) and not is_field_route
    if is_paper:
        map_href = "paper_map.html" if has_map else "roadmap.html"
        lens_href = "paper_lens.html" if has_lens else map_href
        return [
            {
                "id": "session-paper-map",
                "minutes": 6,
                "href": map_href,
                "title": "先看论文主链" if is_zh else "Map the paper chain",
                "body": "只看背景、动机、问题、方法、实验、贡献、局限怎么连。"
                if is_zh
                else "Read only how background, motivation, problem, method, experiments, contributions, and limits connect.",
                "cta": "打开逻辑图" if is_zh else "Open map",
            },
            {
                "id": "session-paper-evidence",
                "minutes": 14,
                "href": lens_href,
                "title": "读一段关键证据" if is_zh else "Read one evidence paragraph",
                "body": "挑一个方法或实验段落，确认解释不是凭感觉。"
                if is_zh
                else "Pick one method or experiment paragraph and ground the explanation in evidence.",
                "cta": "进入精读" if is_zh else "Read lens",
            },
            {
                "id": "session-recall",
                "minutes": 8,
                "href": "#active-recall-title",
                "title": "闭卷主动回忆" if is_zh else "Recall without notes",
                "body": "先回答小卡片，再回页面找证据修正答案。"
                if is_zh
                else "Answer the recall cards first, then reopen evidence to correct your answer.",
                "cta": "做小测" if is_zh else "Try recall",
            },
            {
                "id": "session-mastery-task",
                "minutes": 22,
                "href": "roadmap.html",
                "title": "完成一个验收任务" if is_zh else "Finish one mastery task",
                "body": "留下解释、推导、复现或批判中的一个可检查证据。"
                if is_zh
                else "Leave one checkable explain, derive, reproduce, or critique artifact.",
                "cta": "打开任务" if is_zh else "Open tasks",
            },
        ]
    return [
        {
            "id": "session-prereq-scan",
            "minutes": 10,
            "href": "roadmap.html",
            "title": "扫一遍前置知识" if is_zh else "Scan prerequisites",
            "body": "只补会缩短路线的前置知识，不重学整门课。"
            if is_zh
            else "Fill only prerequisites that shorten the route, not a whole course.",
            "cta": "看路线" if is_zh else "Open route",
        },
        {
            "id": "session-core-resource",
            "minutes": 20,
            "href": "roadmap.html",
            "title": "读第一份核心资料" if is_zh else "Read the first core resource",
            "body": "优先选择证据强、覆盖目标概念、能本地打开的资料。"
            if is_zh
            else "Start with the resource that is evidence-backed, target-covering, and locally available.",
            "cta": "看资料" if is_zh else "Open resources",
        },
        {
            "id": "session-route-recall",
            "minutes": 10,
            "href": "#active-recall-title",
            "title": "闭卷说出结构" if is_zh else "Recall the structure",
            "body": "说清概念、资料、任务和验收之间的关系。"
            if is_zh
            else "Explain how concepts, resources, tasks, and assessments connect.",
            "cta": "做小测" if is_zh else "Try recall",
        },
        {
            "id": "session-route-artifact",
            "minutes": 20,
            "href": "roadmap.html",
            "title": "定义今天的产出" if is_zh else "Define today's artifact",
            "body": "把学习落到项目、综述、复现日志或验收清单上。"
            if is_zh
            else "Turn learning into a project, survey, reproduction log, or checklist.",
            "cta": "看验收" if is_zh else "Open validation",
        },
    ]


def _session_step_card_html(step: dict[str, str | int], is_zh: bool) -> str:
    minutes = int(step["minutes"])
    time_text = f"{minutes} 分钟" if is_zh else f"{minutes} min"
    return f"""<a class="session-step" data-session-step="{escape(str(step["id"]))}" href="{escape(str(step["href"]))}">
          <time>{escape(time_text)}</time>
          <strong>{escape(str(step["title"]))}</strong>
          <span>{escape(str(step["body"]))}</span>
          <em>{escape(str(step["cta"]))}</em>
        </a>"""


def _starter_questions(roadmap: dict[str, Any], is_zh: bool) -> list[dict[str, str]]:
    has_map = bool(roadmap.get("paper_map"))
    has_lens = bool(roadmap.get("paper_lens"))
    is_paper = bool(has_map or has_lens)
    if is_paper:
        main_href = "paper_map.html" if has_map else "roadmap.html"
        evidence_href = "paper_lens.html" if has_lens else main_href
        return [
            {
                "id": "paper-main-chain",
                "label": "01",
                "href": main_href,
                "question": "这篇论文的主线到底是什么？" if is_zh else "What is the paper's main logic chain?",
                "hint": "先看背景、动机、问题、方法、实验、贡献和局限如何连起来。" if is_zh else "Start with how background, motivation, problem, method, experiments, contributions, and limits connect.",
                "ask": "这篇论文在解决什么问题？请用一句话说明主线。" if is_zh else "What problem does this paper solve? Explain the main chain in one sentence.",
            },
            {
                "id": "paper-core-evidence",
                "label": "02",
                "href": evidence_href,
                "question": "核心方法为什么可能有效？证据在哪里？" if is_zh else "Why might the core method work, and where is the evidence?",
                "hint": "用段落精读和证据片段确认关键方法不是凭感觉理解。" if is_zh else "Use paragraph reading and evidence snippets so the method is not understood by intuition alone.",
                "ask": "哪些原文证据支撑这篇论文的核心方法？" if is_zh else "Which source evidence supports the paper's core method?",
            },
            {
                "id": "paper-mastery-proof",
                "label": "03",
                "href": "roadmap.html",
                "question": "我怎样证明自己真的掌握了？" if is_zh else "How do I prove I actually mastered it?",
                "hint": "最后用 explain、derive、reproduce、critique 留下可检查结果。" if is_zh else "Finish with checkable explain, derive, reproduce, and critique evidence.",
                "ask": "我需要交付哪些证据才能算掌握这篇论文？" if is_zh else "What evidence should I produce to prove mastery of this paper?",
            },
        ]
    return [
        {
            "id": "route-prerequisites",
            "label": "01",
            "href": "roadmap.html",
            "question": "我应该先补哪几个前置知识？" if is_zh else "Which prerequisites should I learn first?",
            "hint": "先补会缩短路线的知识，不把整门课重学一遍。" if is_zh else "Fill only the prerequisites that shorten the route instead of retaking a whole course.",
            "ask": "这条学习路线最先需要补哪些前置知识？" if is_zh else "Which prerequisites matter first for this route?",
        },
        {
            "id": "route-resource-priority",
            "label": "02",
            "href": "roadmap.html",
            "question": "哪些资料是核心，哪些只是补充？" if is_zh else "Which resources are core, and which are optional support?",
            "hint": "按证据强度、覆盖范围和本地可打开状态筛资源。" if is_zh else "Use evidence strength, coverage, and local availability to choose resources.",
            "ask": "哪些资料最值得先读，为什么？" if is_zh else "Which resources should I read first, and why?",
        },
        {
            "id": "route-final-artifact",
            "label": "03",
            "href": "roadmap.html",
            "question": "学完以后我要交付什么？" if is_zh else "What should I deliver after learning?",
            "hint": "用项目、复现日志、综述笔记或验收清单证明学习结果。" if is_zh else "Use a project, reproduction log, survey note, or checklist to prove the result.",
            "ask": "这条路线最终应该交付什么成果？" if is_zh else "What final artifact should this route produce?",
        },
    ]


def _starter_question_card_html(item: dict[str, str], is_zh: bool) -> str:
    command = f'fields-study-flow ask --roadmap roadmap.json --question "{item["ask"]}"'
    return f"""<article class="learning-question-card" data-starter-question="{escape(item["id"])}">
          <small>{escape(item["label"])}</small>
          <strong>{escape(item["question"])}</strong>
          <p>{escape(item["hint"])}</p>
          <a href="{escape(item["href"])}">{escape('打开对应页面' if is_zh else 'Open page')}</a>
          <code>{escape(command)}</code>
        </article>"""


def _active_recall_panel_html(roadmap: dict[str, Any], is_zh: bool) -> str:
    title = "5 分钟主动回忆小测" if is_zh else "5-minute active recall"
    body = (
        "先别急着继续读。用这几张小卡闭卷回答，答不出来再打开对应页面找证据。"
        if is_zh
        else "Pause before reading more. Answer these cards from memory, then open the linked page to find evidence."
    )
    card_label = "下载练习卡" if is_zh else "Download cards"
    quiz_label = "下载小测" if is_zh else "Download quiz"
    cards = "\n".join(_recall_card_html(card, is_zh) for card in _recall_cards(roadmap, is_zh))
    return f"""<section class="active-recall-panel" data-active-recall-panel="five-minute-check" aria-labelledby="active-recall-title">
      <header>
        <div>
          <p class="eyebrow">{escape('主动回忆' if is_zh else 'Active recall')}</p>
          <h2 id="active-recall-title">{escape(title)}</h2>
          <p>{escape(body)}</p>
        </div>
        <div class="active-recall-actions" data-active-recall-downloads>
          <a href="study_cards.md">{escape(card_label)}</a>
          <a href="study_quiz.md">{escape(quiz_label)}</a>
        </div>
      </header>
      <div class="active-recall-grid">
        {cards}
      </div>
    </section>"""


def _recall_cards(roadmap: dict[str, Any], is_zh: bool) -> list[dict[str, str]]:
    has_map = bool(roadmap.get("paper_map"))
    has_lens = bool(roadmap.get("paper_lens"))
    is_paper = bool(has_map or has_lens)
    if is_paper:
        map_href = "paper_map.html" if has_map else "roadmap.html"
        lens_href = "paper_lens.html" if has_lens else map_href
        return [
            {
                "id": "recall-main-chain",
                "label": "Q1",
                "href": map_href,
                "prompt": "不看报告，你能用一句话讲清论文主线吗？" if is_zh else "Without the report, can you explain the paper's main chain in one sentence?",
                "check": "检查是否包含背景、动机、问题、方法和贡献。" if is_zh else "Check whether your answer includes background, motivation, problem, method, and contribution.",
            },
            {
                "id": "recall-method",
                "label": "Q2",
                "href": lens_href,
                "prompt": "核心方法为什么可能有效？" if is_zh else "Why might the core method work?",
                "check": "找一段原文证据支撑你的解释，而不是只凭直觉。" if is_zh else "Find one source passage that supports your explanation, not just intuition.",
            },
            {
                "id": "recall-experiment",
                "label": "Q3",
                "href": "roadmap.html",
                "prompt": "如果要最小复现，你会先做哪一步？" if is_zh else "If you had to reproduce the minimum result, what would you do first?",
                "check": "把答案落到一个命令、一个 notebook 单元或一条实验记录。" if is_zh else "Turn the answer into a command, notebook cell, or experiment log entry.",
            },
            {
                "id": "recall-limits",
                "label": "Q4",
                "href": map_href,
                "prompt": "这篇论文最可能在哪里失效？" if is_zh else "Where is this paper most likely to fail?",
                "check": "至少说出一个数据、假设、任务或评价方式上的边界。" if is_zh else "Name at least one boundary in data, assumptions, task setting, or evaluation.",
            },
        ]
    return [
        {
            "id": "recall-prereq",
            "label": "Q1",
            "href": "roadmap.html",
            "prompt": "你能说出最先要补的两个前置知识吗？" if is_zh else "Can you name the first two prerequisites to fill?",
            "check": "只保留会缩短当前路线的前置知识。" if is_zh else "Keep only prerequisites that shorten the current route.",
        },
        {
            "id": "recall-core-concept",
            "label": "Q2",
            "href": "roadmap.html",
            "prompt": "这个领域的核心概念之间怎么连？" if is_zh else "How do the core concepts in this field connect?",
            "check": "用概念、资料、任务和验收之间的关系解释。" if is_zh else "Explain through concept, resource, task, and assessment links.",
        },
        {
            "id": "recall-resource",
            "label": "Q3",
            "href": "roadmap.html",
            "prompt": "哪份资料最值得先读？为什么？" if is_zh else "Which resource should you read first, and why?",
            "check": "优先引用证据强度、覆盖范围和本地可打开状态。" if is_zh else "Use evidence strength, coverage, and local availability as the reason.",
        },
        {
            "id": "recall-artifact",
            "label": "Q4",
            "href": "roadmap.html",
            "prompt": "学完以后你要留下什么成果？" if is_zh else "What artifact should remain after learning?",
            "check": "把答案落到项目、综述、复现日志或验收清单。" if is_zh else "Turn it into a project, survey, reproduction log, or checklist.",
        },
    ]


def _recall_card_html(card: dict[str, str], is_zh: bool) -> str:
    return f"""<details class="recall-card" data-recall-card="{escape(card["id"])}">
          <summary>
            <small>{escape(card["label"])}</small>
            <strong>{escape(card["prompt"])}</strong>
          </summary>
          <p>{escape(card["check"])}</p>
          <a href="{escape(card["href"])}">{escape('去找证据' if is_zh else 'Find evidence')}</a>
        </details>"""


def render_study_cards_markdown(roadmap: dict[str, Any]) -> str:
    """Render a portable active-recall card set from the same cards used by index.html."""
    is_zh = _html_lang(roadmap) != "en"
    cards = _recall_cards(roadmap, is_zh)
    title = "主动回忆练习卡" if is_zh else "Active Recall Study Cards"
    subtitle = (
        "先遮住答案自己回答，再打开对应页面找证据修正。"
        if is_zh
        else "Answer from memory first, then open the linked page to verify with evidence."
    )
    evidence_label = "去找证据" if is_zh else "Find evidence"
    check_label = "检查标准" if is_zh else "Check"
    output: list[str] = [
        f"# {title}",
        "",
        subtitle,
        "",
        "| # | Prompt | Check | Evidence Link |",
        "|---|---|---|---|",
    ]
    for card in cards:
        output.append(
            "| {label} | {prompt} | {check} | [{evidence_label}]({href}) |".format(
                label=_markdown_cell(card.get("label", "")),
                prompt=_markdown_cell(card.get("prompt", "")),
                check=_markdown_cell(f"{check_label}: {card.get('check', '')}"),
                evidence_label=_markdown_cell(evidence_label),
                href=_safe_markdown_href(card.get("href", "roadmap.html")),
            )
        )
    output.extend(
        [
            "",
            ("## 使用方法" if is_zh else "## How to Use"),
            "",
            (
                "1. 先不要打开证据链接，闭卷回答每张卡。"
                if is_zh
                else "1. Do not open the evidence link yet; answer each card closed-book."
            ),
            (
                "2. 回答后打开证据链接，把原文依据补到自己的笔记里。"
                if is_zh
                else "2. After answering, open the evidence link and add the source basis to your notes."
            ),
            (
                "3. 答不出来的卡片，回到 Paper Map、Paper Lens 或 roadmap 补读。"
                if is_zh
                else "3. For cards you cannot answer, return to Paper Map, Paper Lens, or the roadmap."
            ),
            "",
        ]
    )
    return "\n".join(output)


def render_study_quiz_markdown(roadmap: dict[str, Any]) -> str:
    """Render a portable quiz with an evidence-linked answer key."""
    is_zh = _html_lang(roadmap) != "en"
    cards = _recall_cards(roadmap, is_zh)
    title = "证据链接学习小测" if is_zh else "Evidence-Linked Study Quiz"
    subtitle = (
        "把它当成 5-10 分钟闭卷小测：先写答案，再按证据链接核对。"
        if is_zh
        else "Use this as a 5-10 minute closed-book check: write first, then verify through the evidence links."
    )
    score_title = "自评分规则" if is_zh else "Self-Scoring Rubric"
    score_items = (
        [
            "0 分：答不出来，或只复述标题。",
            "1 分：有大概方向，但没有论文逻辑或证据。",
            "2 分：能说清核心观点，并能指向一个证据页面。",
            "3 分：能用自己的话解释，并补上原文证据或复现动作。",
        ]
        if is_zh
        else [
            "0 points: no answer, or only repeats the title.",
            "1 point: rough direction, but no paper logic or evidence.",
            "2 points: clear core claim and one evidence page.",
            "3 points: explains in your own words and adds source evidence or a reproduction action.",
        ]
    )
    question_heading = "题目" if is_zh else "Questions"
    key_heading = "自查答案钥匙" if is_zh else "Answer Key"
    evidence_label = "证据入口" if is_zh else "Evidence"
    answer_slot = "我的答案：" if is_zh else "My answer:"
    output: list[str] = [
        f"# {title}",
        "",
        subtitle,
        "",
        f"## {score_title}",
        "",
    ]
    output.extend(f"- {item}" for item in score_items)
    output.extend(["", f"## {question_heading}", ""])
    for index, card in enumerate(cards, start=1):
        prompt = _markdown_text(card.get("prompt", ""))
        href = _safe_markdown_href(card.get("href", "roadmap.html"))
        output.extend(
            [
                f"{index}. **{prompt}**",
                f"   - {answer_slot} ________________________________",
                f"   - [{evidence_label}]({href})",
                "",
            ]
        )
    output.extend([f"## {key_heading}", ""])
    for index, card in enumerate(cards, start=1):
        check = _markdown_text(card.get("check", ""))
        href = _safe_markdown_href(card.get("href", "roadmap.html"))
        output.extend(
            [
                f"{index}. {check}",
                f"   - [{evidence_label}]({href})",
                "",
            ]
        )
    return "\n".join(output)


def render_mastery_worksheet_markdown(roadmap: dict[str, Any]) -> str:
    """Render a fillable mastery-evidence worksheet from roadmap tasks."""
    is_zh = _html_lang(roadmap) != "en"
    title = _markdown_text(roadmap.get("title") or _display_report_base_title(roadmap))
    profile = roadmap.get("profile") if isinstance(roadmap.get("profile"), dict) else {}
    goal = _markdown_text(profile.get("goal") or title)
    mastery = roadmap.get("mastery_evidence") if isinstance(roadmap.get("mastery_evidence"), dict) else {}
    final_artifact = _markdown_text(mastery.get("final_artifact") or _dict_at(roadmap, "final_artifact").get("type") or "")
    tasks = _mastery_worksheet_items(roadmap)
    resource_links = _resource_links_by_title(roadmap)
    heading = "掌握证据工作表" if is_zh else "Mastery Evidence Worksheet"
    output: list[str] = [
        f"# {title} - {heading}",
        "",
        f"- {'学习目标' if is_zh else 'Learning goal'}: {goal}",
        f"- {'最终产物' if is_zh else 'Final artifact'}: {final_artifact or ('未指定' if is_zh else 'not specified')}",
        f"- {'完成进度' if is_zh else 'Progress'}: 0/{len(tasks)}",
        "",
        (
            "使用方法：每完成一项任务，就把自己的解释、推导、复现结果或批判结论写进“我的证据”，并补上来源链接或本地文件。"
            if is_zh
            else "How to use: for each task, fill in your explanation, derivation, reproduction result, or critique under My Evidence, then add the source link or local file."
        ),
        "",
        f"## {'快速入口' if is_zh else 'Quick Links'}",
        "",
        "- [Paper Map](paper_map.html)",
        "- [Paper Lens](paper_lens.html)",
        "- [Roadmap / Mastery Checklist](roadmap.html#mastery-checklist-title)",
        "",
    ]
    if not tasks:
        output.extend(
            [
                f"## {'暂无验收任务' if is_zh else 'No Mastery Tasks Yet'}",
                "",
                (
                    "当前路线还没有可填写的掌握任务。请补充目标论文、资料包或重新生成路线。"
                    if is_zh
                    else "This route does not have fillable mastery tasks yet. Add the target paper, study bundle, or regenerate the route."
                ),
                "",
            ]
        )
        return "\n".join(output)
    output.extend([f"## {'证据槽' if is_zh else 'Evidence Slots'}", ""])
    for index, item in enumerate(tasks, start=1):
        task_type = _worksheet_task_type_label(item.get("task_type") or item.get("type"), is_zh)
        task_title = _markdown_text(item.get("title") or f"{'任务' if is_zh else 'Task'} {index}")
        evidence = _markdown_text(item.get("evidence") or "")
        pass_criteria = _markdown_text(item.get("pass_criteria") or item.get("acceptance") or "")
        minutes = item.get("estimated_minutes")
        output.extend(
            [
                f"### {index}. {task_title}",
                "",
                f"- {'类型' if is_zh else 'Type'}: {task_type}",
                f"- {'建议入口' if is_zh else 'Suggested entry'}: {_worksheet_entry_link(str(item.get('task_type') or item.get('type') or ''), is_zh)}",
                f"- {'预计耗时' if is_zh else 'Estimated time'}: {minutes if minutes else ('未估计' if is_zh else 'not estimated')}",
                f"- {'要交付的证据' if is_zh else 'Evidence to produce'}: {evidence or ('填写可复查证据。' if is_zh else 'Fill reviewable evidence.')}",
                f"- {'通过标准' if is_zh else 'Pass criteria'}: {pass_criteria or ('能回到来源说明为什么成立。' if is_zh else 'Can trace the claim back to the source.')}",
                "",
                f"**{'建议资料' if is_zh else 'Suggested resources'}**",
            ]
        )
        resources = [str(value) for value in item.get("resources") or item.get("resource_titles") or [] if str(value).strip()]
        if resources:
            for resource in resources[:4]:
                output.append(f"- {_resource_markdown_link(resource, resource_links)}")
        else:
            output.append(f"- {'回到路线资料库选择最短路径资料。' if is_zh else 'Return to the roadmap resource library and choose the shortest-path resource.'}")
        chunk_lines = _worksheet_evidence_chunk_lines(item.get("evidence_chunks") or [], is_zh)
        if chunk_lines:
            output.extend(["", f"**{'可回看的原文证据' if is_zh else 'Source evidence to revisit'}**"])
            output.extend(chunk_lines)
        output.extend(
            [
                "",
                f"**{'我的证据' if is_zh else 'My Evidence'}**",
                "",
                "- ",
                "",
                f"**{'来源 / 文件 / 页码' if is_zh else 'Source / File / Page'}**",
                "",
                "- ",
                "",
                f"**{'复核结果' if is_zh else 'Review Result'}**: {'通过 / 需要修改 / 证据不足' if is_zh else 'pass / revise / insufficient evidence'}",
                "",
            ]
        )
    return "\n".join(output)


def render_evidence_coverage_markdown(roadmap: dict[str, Any]) -> str:
    """Render a portable evidence-coverage matrix for trust and study planning."""
    is_zh = _html_lang(roadmap) != "en"
    title = _markdown_text(roadmap.get("title") or _display_report_base_title(roadmap))
    profile = roadmap.get("profile") if isinstance(roadmap.get("profile"), dict) else {}
    goal = _markdown_text(profile.get("goal") or title)
    map_rows = _coverage_mark_surface(_coverage_paper_map_rows(roadmap, is_zh), "Paper Map", 10)
    lens_rows = _coverage_mark_surface(_coverage_paper_lens_rows(roadmap, is_zh), "Paper Lens", 20)
    task_rows = _coverage_mark_surface(_coverage_task_rows(roadmap, is_zh), "Mastery Tasks", 30)
    resource_rows = _coverage_mark_surface(_coverage_resource_rows(roadmap, is_zh), "Resource Library", 40)
    all_rows = map_rows + lens_rows + task_rows + resource_rows
    covered = sum(1 for item in all_rows if item.get("status") == "covered")
    total = len(all_rows)
    coverage_percent = _coverage_percent(covered, total)
    section_scores = _coverage_section_scores(
        [
            ("Paper Map", map_rows, "paper_map.html"),
            ("Paper Lens", lens_rows, "paper_lens.html"),
            ("Mastery Tasks", task_rows, "roadmap.html#mastery-checklist-title"),
            ("Resource Library", resource_rows, "roadmap.html#resource-library"),
        ],
        roadmap,
    )
    priority_gaps = _coverage_priority_gaps(all_rows)
    source_diagnostics = _coverage_source_diagnostics(roadmap, map_rows, lens_rows, task_rows, resource_rows)
    heading = "证据覆盖矩阵" if is_zh else "Evidence Coverage Matrix"
    output: list[str] = [
        f"# {title} - {heading}",
        "",
        f"- {'学习目标' if is_zh else 'Learning goal'}: {goal}",
        f"- {'覆盖进度' if is_zh else 'Coverage'}: {covered}/{total}",
        f"- {'覆盖分数' if is_zh else 'Coverage score'}: {coverage_percent}%",
        f"- {'优先缺口' if is_zh else 'Priority gaps'}: {len(priority_gaps)}",
        f"- {'用途' if is_zh else 'Use'}: "
        + (
            "先看哪里有证据，再决定是否继续读、补资料或重新生成路线。"
            if is_zh
            else "See what is evidence-backed before deciding whether to read, add sources, or regenerate the route."
        ),
        "",
        f"## {'覆盖总览' if is_zh else 'Coverage Summary'}",
        "",
        "| {surface} | {covered_label} | {total_label} | {entry} |".format(
            surface="学习面" if is_zh else "Surface",
            covered_label="已覆盖" if is_zh else "Covered",
            total_label="总数" if is_zh else "Total",
            entry="优先入口" if is_zh else "First entry",
        ),
        "| --- | ---: | ---: | --- |",
    ]
    summary_items: list[tuple[str, list[dict[str, Any]], str]] = []
    if map_rows or roadmap.get("paper_map"):
        summary_items.append(("论文逻辑图" if is_zh else "Paper Map", map_rows, "paper_map.html"))
    if lens_rows or roadmap.get("paper_lens"):
        summary_items.append(("段落精读" if is_zh else "Paper Lens", lens_rows, "paper_lens.html"))
    summary_items.extend(
        [
            ("掌握任务" if is_zh else "Mastery Tasks", task_rows, "roadmap.html#mastery-checklist-title"),
            ("资料库" if is_zh else "Resource Library", resource_rows, "roadmap.html#resource-library"),
        ]
    )
    for label, rows, entry in summary_items:
        output.append(f"| {label} | {sum(1 for item in rows if item.get('status') == 'covered')} | {len(rows)} | [{_markdown_text(entry)}]({_safe_markdown_href(entry)}) |")
    output.append("")
    _append_evidence_source_diagnostics(output, source_diagnostics, is_zh)
    _append_measured_coverage_score(output, section_scores, is_zh)
    _append_priority_evidence_queue(output, priority_gaps, is_zh)
    _append_coverage_table(output, "论文逻辑覆盖" if is_zh else "Paper Logic Coverage", map_rows, is_zh)
    _append_coverage_table(output, "精读段落覆盖" if is_zh else "Reading Paragraph Coverage", lens_rows, is_zh)
    _append_coverage_table(output, "验收任务覆盖" if is_zh else "Mastery Task Coverage", task_rows, is_zh)
    _append_coverage_table(output, "资料证据覆盖" if is_zh else "Resource Evidence Coverage", resource_rows, is_zh)
    gaps = _coverage_gap_lines(all_rows, is_zh)
    output.extend([f"## {'下一步补证据' if is_zh else 'Evidence Gaps to Fix'}", ""])
    output.extend(gaps or [("- 当前核心路径都有可追溯证据。" if is_zh else "- The current core path has traceable evidence.")])
    output.append("")
    return "\n".join(output)


def render_evidence_coverage_html(roadmap: dict[str, Any]) -> str:
    """Render the evidence coverage matrix as a readable offline dashboard."""
    markdown = render_evidence_coverage_markdown(roadmap)
    is_zh = _html_lang(roadmap) != "en"
    title = _markdown_text(roadmap.get("title") or _display_report_base_title(roadmap))
    body = _simple_markdown_to_html(markdown)
    return f"""<!doctype html>
<html lang="{escape('zh-CN' if is_zh else 'en')}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - {escape('证据覆盖仪表盘' if is_zh else 'Evidence Coverage Dashboard')}</title>
  <style>
    :root {{
      --ink:#15212f;
      --muted:#5d6f82;
      --line:#d9e4ee;
      --paper:#fbfcfd;
      --accent:#2f6f73;
      --accent-2:#375c9f;
      --warn:#9a6324;
      --soft:#f2f7f8;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0;
      color:var(--ink);
      background:linear-gradient(180deg,#eef5f6 0,#f8fbfc 46%,#eef3f7 100%);
      font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Noto Sans SC","Source Han Sans SC",Arial,sans-serif;
      line-height:1.62;
    }}
    main {{ width:min(1180px, calc(100vw - 28px)); max-width:100%; margin:0 auto; padding:28px 0 44px; }}
    .hero {{
      border:1px solid rgba(47,111,115,.18);
      background:rgba(255,255,255,.92);
      border-radius:18px;
      padding:22px;
      box-shadow:0 18px 55px rgba(32,64,82,.11);
    }}
    .eyebrow {{ margin:0 0 6px; color:var(--accent); font-size:.78rem; font-weight:800; letter-spacing:.08em; text-transform:uppercase; }}
    h1 {{ margin:0; font-size:clamp(24px,4vw,42px); line-height:1.16; overflow-wrap:anywhere; }}
    .hero p:last-child {{ margin-bottom:0; color:var(--muted); }}
    .dashboard {{
      margin-top:18px;
      display:grid;
      gap:16px;
      grid-template-columns:minmax(0,1fr);
    }}
    section {{
      border:1px solid var(--line);
      background:rgba(255,255,255,.94);
      border-radius:14px;
      padding:18px;
      overflow:hidden;
    }}
    h2 {{ margin:0 0 12px; font-size:1.22rem; line-height:1.25; }}
    ul {{ margin:0; padding-left:1.2rem; }}
    li {{ margin:6px 0; overflow-wrap:anywhere; }}
    table {{ width:100%; border-collapse:collapse; font-size:.94rem; }}
    th, td {{ border-bottom:1px solid var(--line); padding:10px 9px; text-align:left; vertical-align:top; overflow-wrap:anywhere; }}
    th {{ color:#31475b; background:var(--soft); font-weight:800; }}
    tr:last-child td {{ border-bottom:0; }}
    a {{ color:var(--accent-2); text-decoration:none; font-weight:700; }}
    a:hover, a:focus-visible {{ text-decoration:underline; outline:none; }}
    code {{ background:#edf3f5; border-radius:6px; padding:2px 5px; }}
    .metric-list {{
      display:grid;
      gap:10px;
      grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
      padding:0;
      list-style:none;
    }}
    .metric-list li {{
      border:1px solid var(--line);
      border-radius:12px;
      padding:12px;
      background:#fbfdfe;
    }}
    .metric-list strong {{ display:block; margin-bottom:4px; color:var(--accent); }}
    @media (max-width:760px) {{
      main {{ width:min(100vw - 20px, 680px); padding-top:18px; }}
      section {{ padding:14px; }}
      table {{ display:block; overflow-x:auto; white-space:normal; }}
      th, td {{ min-width:130px; }}
    }}
  </style>
</head>
<body>
  <main>
    <header class="hero">
      <p class="eyebrow">fields-study-flow</p>
      <h1>{escape('证据覆盖仪表盘' if is_zh else 'Evidence Coverage Dashboard')}</h1>
      <p>{escape(title)}</p>
    </header>
    <article class="dashboard">
      {body}
    </article>
  </main>
</body>
</html>"""


def render_quick_brief_markdown(roadmap: dict[str, Any]) -> str:
    """Render a one-page quick brief for first-read comprehension."""
    is_zh = _html_lang(roadmap) != "en"
    title = _markdown_text(roadmap.get("title") or _display_report_base_title(roadmap))
    profile = roadmap.get("profile") if isinstance(roadmap.get("profile"), dict) else {}
    goal = _markdown_text(profile.get("goal") or title)
    paper_map = roadmap.get("paper_map") if isinstance(roadmap.get("paper_map"), dict) else {}
    core_nodes = _quick_brief_core_nodes(paper_map)
    resource_links = _resource_links_by_title(roadmap)
    heading = "5 分钟速读 Brief" if is_zh else "5-Minute Research Brief"
    one_sentence = _quick_brief_one_sentence(core_nodes, roadmap, is_zh)
    start_label, start_chain = _quick_brief_start_here(roadmap, is_zh)
    output: list[str] = [
        f"# {title} - {heading}",
        "",
        f"- {'目标' if is_zh else 'Goal'}: {goal}",
        f"- {start_label}: {start_chain}",
        "",
        f"## {'一句话理解' if is_zh else 'One-Sentence Takeaway'}",
        "",
        one_sentence,
        "",
    ]
    if core_nodes:
        output.extend([f"## {'论文逻辑主链' if is_zh else 'Paper Logic Chain'}", ""])
        labels = _quick_brief_chain_labels(is_zh)
        for kind in ("background", "motivation", "problem", "methodology", "experiment", "contribution", "limitation"):
            node = next((item for item in core_nodes if str(item.get("kind")) == kind), {})
            if not node:
                continue
            text = _quick_brief_node_text(node)
            output.append(f"- **{labels.get(kind, kind)}**: {text}")
        output.append("")
        talking_points = [_markdown_text(node.get("talking_point") or node.get("plain_explanation") or "") for node in core_nodes]
        talking_points = [item for item in talking_points if item][:3]
        if talking_points:
            output.extend([f"## {'汇报时可以这样说' if is_zh else 'Presentation Wording'}", ""])
            output.extend(f"- {item}" for item in talking_points)
            output.append("")
        evidence_lines = _quick_brief_evidence_lines(core_nodes, is_zh)
        if evidence_lines:
            output.extend([f"## {'最该打开的证据' if is_zh else 'Evidence to Open First'}", ""])
            output.extend(evidence_lines)
            output.append("")
    else:
        output.extend(_quick_brief_route_sections(roadmap, is_zh))
    next_actions = [item for item in roadmap.get("next_actions", []) if isinstance(item, dict)]
    if next_actions:
        output.extend([f"## {'下一步动作' if is_zh else 'Next Actions'}", ""])
        for action in next_actions[:3]:
            title_text = _markdown_text(action.get("title") or action.get("task_id") or "")
            minutes = action.get("estimated_minutes")
            evidence = _markdown_text(action.get("evidence") or "")
            suffix = f" ({minutes} {'分钟' if is_zh else 'min'})" if minutes else ""
            output.append(f"- {title_text}{suffix}: {evidence}")
        output.append("")
    resources = _quick_brief_resource_lines(roadmap, resource_links, is_zh)
    if resources:
        output.extend([f"## {'先打开这些资料' if is_zh else 'Open These Resources First'}", ""])
        output.extend(resources)
        output.append("")
    output.extend(
        [
            f"## {'掌握检查' if is_zh else 'Mastery Check'}",
            "",
            (
                "- 读完这页后，去 `study_quiz.md` 闭卷做一遍，再把证据写进 `mastery_worksheet.md`。"
                if is_zh
                else "- After this page, take `study_quiz.md` closed-book, then fill evidence into `mastery_worksheet.md`."
            ),
            "",
        ]
    )
    return "\n".join(output)


def _markdown_cell(value: object) -> str:
    return _markdown_text(value).replace("|", "\\|").replace("\n", "<br>")


def _markdown_text(value: object) -> str:
    text = str(value or "")
    text = PRIVATE_PATH_RE.sub("[private path]", text)
    return text.replace("\r", " ").replace("\n", " ").strip()


def _simple_markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("# "):
            output.append(f"<section><h2>{_inline_markdown_to_html(line[2:].strip())}</h2>")
            index += 1
            while index < len(lines) and lines[index].startswith("- "):
                items: list[str] = []
                while index < len(lines) and lines[index].startswith("- "):
                    items.append(f"<li>{_inline_markdown_to_html(lines[index][2:].strip())}</li>")
                    index += 1
                output.append(f"<ul class=\"metric-list\">{''.join(items)}</ul>")
            output.append("</section>")
            continue
        if line.startswith("## "):
            heading = _inline_markdown_to_html(line[3:].strip())
            index += 1
            block_lines: list[str] = []
            while index < len(lines) and not lines[index].startswith("## "):
                block_lines.append(lines[index])
                index += 1
            output.append(f"<section><h2>{heading}</h2>{_markdown_block_to_html(block_lines)}</section>")
            continue
        output.append(f"<section><p>{_inline_markdown_to_html(line.strip())}</p></section>")
        index += 1
    return "\n".join(output)


def _markdown_block_to_html(lines: list[str]) -> str:
    output: list[str] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        if line.startswith("|"):
            table_lines: list[str] = []
            while index < len(lines) and lines[index].startswith("|"):
                table_lines.append(lines[index])
                index += 1
            output.append(_markdown_table_to_html(table_lines))
            continue
        if line.startswith("- "):
            items: list[str] = []
            while index < len(lines) and lines[index].startswith("- "):
                items.append(f"<li>{_inline_markdown_to_html(lines[index][2:].strip())}</li>")
                index += 1
            output.append(f"<ul>{''.join(items)}</ul>")
            continue
        output.append(f"<p>{_inline_markdown_to_html(line.strip())}</p>")
        index += 1
    return "\n".join(output)


def _markdown_table_to_html(lines: list[str]) -> str:
    rows = [_split_markdown_table_row(line) for line in lines if line.strip()]
    if not rows:
        return ""
    header = rows[0]
    body_rows = rows[2:] if len(rows) > 1 and all(set(cell) <= {"-", ":"} for cell in rows[1]) else rows[1:]
    head_html = "".join(f"<th>{_inline_markdown_to_html(cell)}</th>" for cell in header)
    body_html = "".join(
        "<tr>" + "".join(f"<td>{_inline_markdown_to_html(cell)}</td>" for cell in row) + "</tr>"
        for row in body_rows
    )
    return f"<table><thead><tr>{head_html}</tr></thead><tbody>{body_html}</tbody></table>"


def _split_markdown_table_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    cells: list[str] = []
    current: list[str] = []
    escaped = False
    for char in stripped:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    cells.append("".join(current).strip())
    return cells


def _inline_markdown_to_html(text: str) -> str:
    parts: list[str] = []
    last_index = 0
    for match in re.finditer(r"\[([^\]]+)\]\(([^)]+)\)", text):
        parts.append(_inline_markdown_fragment_to_html(text[last_index : match.start()]))
        label = _inline_markdown_fragment_to_html(match.group(1))
        href = escape(match.group(2), quote=True)
        parts.append(f'<a href="{href}">{label}</a>')
        last_index = match.end()
    parts.append(_inline_markdown_fragment_to_html(text[last_index:]))
    return "".join(parts)


def _inline_markdown_fragment_to_html(text: str) -> str:
    safe = escape(text)
    safe = re.sub(r"`([^`]+)`", r"<code>\1</code>", safe)
    safe = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", safe)
    return safe


def _safe_markdown_href(value: object) -> str:
    href = str(value or "roadmap.html").strip()
    if PRIVATE_PATH_RE.search(href) or not href:
        return "roadmap.html"
    return href.replace(" ", "%20")


def _mastery_worksheet_items(roadmap: dict[str, Any]) -> list[dict[str, Any]]:
    mastery = roadmap.get("mastery_evidence") if isinstance(roadmap.get("mastery_evidence"), dict) else {}
    required = mastery.get("required_evidence") if isinstance(mastery.get("required_evidence"), list) else []
    if required:
        return [item for item in required if isinstance(item, dict)]
    tasks = roadmap.get("study_tasks") if isinstance(roadmap.get("study_tasks"), list) else []
    items: list[dict[str, Any]] = []
    for task in tasks:
        if not isinstance(task, dict):
            continue
        items.append(
            {
                "task_id": task.get("id"),
                "task_type": task.get("type"),
                "title": task.get("title"),
                "evidence": task.get("evidence"),
                "pass_criteria": task.get("acceptance"),
                "resources": task.get("resource_titles", []),
                "estimated_minutes": task.get("estimated_minutes"),
                "evidence_chunks": task.get("evidence_chunks", []),
            }
        )
    return items


def _resource_links_by_title(roadmap: dict[str, Any]) -> dict[str, str]:
    links: dict[str, str] = {}
    for resource in _report_all_resource_entries(roadmap):
        title = str(resource.get("title") or resource.get("resource_title") or "").strip()
        if not title:
            continue
        href = str(resource.get("local_href") or resource.get("href") or resource.get("url") or "").strip()
        if href and not href.startswith("local://") and not PRIVATE_PATH_RE.search(href):
            links[title.casefold()] = _safe_markdown_href(href)
    return links


def _resource_markdown_link(title: str, links: dict[str, str]) -> str:
    clean_title = _markdown_text(title)
    href = links.get(clean_title.casefold())
    if not href:
        return clean_title
    return f"[{clean_title}]({href})"


def _worksheet_task_type_label(value: object, is_zh: bool) -> str:
    task_type = str(value or "task")
    labels = {
        "explain": ("Explain", "解释"),
        "derive": ("Derive", "推导"),
        "reproduce": ("Reproduce", "复现"),
        "critique": ("Critique", "批判"),
        "synthesize": ("Synthesize", "综合"),
    }
    en, zh = labels.get(task_type, (task_type, task_type))
    return zh if is_zh else en


def _worksheet_entry_link(task_type: str, is_zh: bool) -> str:
    entries = {
        "explain": ("Paper Map", "paper_map.html"),
        "derive": ("Paper Lens", "paper_lens.html"),
        "reproduce": ("Roadmap", "roadmap.html#mastery-checklist-title"),
        "critique": ("Paper Map", "paper_map.html"),
        "synthesize": ("Roadmap", "roadmap.html#mastery-checklist-title"),
    }
    label, href = entries.get(task_type, ("Roadmap", "roadmap.html#mastery-checklist-title"))
    if is_zh:
        label = {"Paper Map": "论文逻辑图", "Paper Lens": "段落精读", "Roadmap": "学习路线"}.get(label, label)
    return f"[{label}]({href})"


def _worksheet_evidence_chunk_lines(chunks: object, is_zh: bool) -> list[str]:
    if not isinstance(chunks, list):
        return []
    lines: list[str] = []
    for chunk in chunks[:2]:
        if not isinstance(chunk, dict):
            continue
        label = _markdown_text(chunk.get("resource_title") or chunk.get("file_name") or chunk.get("title") or ("证据片段" if is_zh else "Evidence snippet"))
        snippet = _truncate_markdown(_markdown_text(chunk.get("snippet") or chunk.get("quote") or ""), 180)
        href = str(chunk.get("detail_anchor") or chunk.get("local_href") or chunk.get("href") or chunk.get("url") or "").strip()
        if href and not PRIVATE_PATH_RE.search(href):
            label = f"[{label}]({_safe_markdown_href(href)})"
        if snippet:
            lines.append(f"- {label}: {snippet}")
        else:
            lines.append(f"- {label}")
    return lines


def _truncate_markdown(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()


def _quick_brief_core_nodes(paper_map: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = paper_map.get("nodes") if isinstance(paper_map.get("nodes"), list) else []
    core = [node for node in nodes if isinstance(node, dict) and node.get("role") == "core"]
    order = {"background": 0, "motivation": 1, "problem": 2, "methodology": 3, "experiment": 4, "contribution": 5, "limitation": 6}
    return sorted(core, key=lambda node: order.get(str(node.get("kind")), 99))


def _quick_brief_chain_labels(is_zh: bool) -> dict[str, str]:
    if is_zh:
        return {
            "background": "背景",
            "motivation": "动机 / 缺口",
            "problem": "问题",
            "methodology": "方法",
            "experiment": "实验",
            "contribution": "贡献",
            "limitation": "局限",
        }
    return {
        "background": "Background",
        "motivation": "Motivation / Gap",
        "problem": "Problem",
        "methodology": "Methodology",
        "experiment": "Experiments",
        "contribution": "Contributions",
        "limitation": "Limitations",
    }


def _quick_brief_start_here(roadmap: dict[str, Any], is_zh: bool) -> tuple[str, str]:
    has_map = bool(roadmap.get("paper_map"))
    has_lens = bool(roadmap.get("paper_lens"))
    label = "建议先读" if is_zh else "Start here"
    links: list[str] = []
    if has_map:
        links.append("[论文逻辑图](paper_map.html)" if is_zh else "[Paper Map](paper_map.html)")
    if has_lens:
        links.append("[段落精读](paper_lens.html)" if is_zh else "[Paper Lens](paper_lens.html)")
    if not links:
        links.append("[学习路线](roadmap.html)" if is_zh else "[Roadmap](roadmap.html)")
    links.append("[学习小测](study_quiz.md)" if is_zh else "[Study Quiz](study_quiz.md)")
    links.append("[掌握验收表](mastery_worksheet.md)" if is_zh else "[Mastery Worksheet](mastery_worksheet.md)")
    return label, " -> ".join(links)


def _quick_brief_node_text(node: dict[str, Any]) -> str:
    text = _markdown_text(node.get("plain_explanation") or node.get("summary") or node.get("label") or "")
    return _truncate_markdown(text, 240)


def _quick_brief_one_sentence(core_nodes: list[dict[str, Any]], roadmap: dict[str, Any], is_zh: bool) -> str:
    if core_nodes:
        problem = next((node for node in core_nodes if str(node.get("kind")) == "problem"), {})
        method = next((node for node in core_nodes if str(node.get("kind")) == "methodology"), {})
        contribution = next((node for node in core_nodes if str(node.get("kind")) == "contribution"), {})
        parts = [_quick_brief_node_text(item) for item in (problem, method, contribution) if item]
        if parts:
            connector = "；" if is_zh else "; "
            return connector.join(parts[:3])
    goal = _markdown_text(_dict_at(roadmap, "profile").get("goal") or roadmap.get("title") or "")
    return (
        f"这份路线要用最短路径帮你掌握：{goal}。"
        if is_zh
        else f"This route is the shortest useful path to master: {goal}."
    )


def _quick_brief_evidence_lines(core_nodes: list[dict[str, Any]], is_zh: bool) -> list[str]:
    lines: list[str] = []
    for node in core_nodes:
        for item in node.get("evidence") or []:
            if not isinstance(item, dict):
                continue
            label = _markdown_text(item.get("source_title") or item.get("file_name") or item.get("title") or ("证据" if is_zh else "Evidence"))
            snippet = _truncate_markdown(_markdown_text(item.get("snippet") or item.get("note") or ""), 180)
            href = str(item.get("local_href") or item.get("detail_anchor") or item.get("href") or item.get("url") or "").strip()
            if href and not PRIVATE_PATH_RE.search(href):
                label = f"[{label}]({_safe_markdown_href(href)})"
            if snippet:
                lines.append(f"- {label}: {snippet}")
            else:
                lines.append(f"- {label}")
            if len(lines) >= 5:
                return lines
    return lines


def _quick_brief_route_sections(roadmap: dict[str, Any], is_zh: bool) -> list[str]:
    phases = [item for item in roadmap.get("phases", []) if isinstance(item, dict)]
    lines: list[str] = [f"## {'路线速览' if is_zh else 'Route at a Glance'}", ""]
    if phases:
        for phase in phases[:5]:
            name = _markdown_text(phase.get("name") or ("阶段" if is_zh else "Phase"))
            objective = _truncate_markdown(_markdown_text(phase.get("objective") or ""), 220)
            lines.append(f"- **{name}**: {objective}")
    else:
        lines.append("- " + ("当前报告还没有阶段路线，请补充资料后重新生成。" if is_zh else "No phases yet; add resources and regenerate the report."))
    lines.append("")
    return lines


def _quick_brief_resource_lines(roadmap: dict[str, Any], resource_links: dict[str, str], is_zh: bool) -> list[str]:
    resources = _report_all_resource_entries(roadmap)
    selected = [item for item in resources if item.get("selected") or str(item.get("route_status") or "") == "selected"]
    if not selected:
        selected = resources[:4]
    lines: list[str] = []
    for resource in selected[:4]:
        title = _markdown_text(resource.get("title") or resource.get("label") or ("资料" if is_zh else "Resource"))
        link = _resource_markdown_link(title, resource_links)
        reason = _truncate_markdown(_markdown_text(resource.get("why_recommended") or resource.get("reason") or resource.get("critical_path_role") or ""), 160)
        lines.append(f"- {link}" + (f": {reason}" if reason else ""))
    return lines


def _coverage_mark_surface(rows: list[dict[str, Any]], surface: str, base_priority: int) -> list[dict[str, Any]]:
    marked: list[dict[str, Any]] = []
    for index, row in enumerate(rows):
        item = dict(row)
        item["surface"] = surface
        item["priority"] = base_priority + index
        marked.append(item)
    return marked


def _coverage_percent(covered: int, total: int) -> int:
    if total <= 0:
        return 0
    return int(round((max(0, covered) / total) * 100))


def _coverage_section_scores(
    sections: list[tuple[str, list[dict[str, Any]], str]],
    roadmap: dict[str, Any],
) -> list[dict[str, Any]]:
    scores: list[dict[str, Any]] = []
    for label, rows, entry in sections:
        if label == "Paper Map" and not rows and not roadmap.get("paper_map"):
            continue
        if label == "Paper Lens" and not rows and not roadmap.get("paper_lens"):
            continue
        covered = sum(1 for item in rows if item.get("status") == "covered")
        total = len(rows)
        gaps = max(0, total - covered)
        scores.append(
            {
                "label": label,
                "covered": covered,
                "total": total,
                "score": _coverage_percent(covered, total),
                "gaps": gaps,
                "href": entry,
                "action": _coverage_section_action(label, gaps),
            }
        )
    return scores


def _coverage_section_action(label: str, gaps: int) -> str:
    if gaps <= 0:
        return "Keep as release evidence."
    if label == "Paper Map":
        return "Add source snippets for uncovered claims."
    if label == "Paper Lens":
        return "Bind uncovered paragraphs to local evidence or resources."
    if label == "Mastery Tasks":
        return "Attach each task to resources and checkable evidence."
    if label == "Resource Library":
        return "Download/snapshot resources or attach evidence chunks."
    return "Add traceable evidence."


def _coverage_priority_gaps(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    gaps = [row for row in rows if row.get("status") != "covered"]
    return sorted(gaps, key=lambda row: (_coerce_nonnegative_int(row.get("priority")), str(row.get("label") or "")))[:10]


def _coverage_first_gap_href(rows: list[dict[str, Any]], fallback: str) -> str:
    for row in rows:
        if row.get("status") != "covered":
            return _safe_markdown_href(row.get("href") or fallback)
    for row in rows:
        if row.get("href"):
            return _safe_markdown_href(row.get("href"))
    return _safe_markdown_href(fallback)


def _coverage_first_resource_href(resources: list[dict[str, Any]], fallback: str) -> str:
    for resource in resources:
        href = str(resource.get("local_href") or resource.get("href") or resource.get("url") or "").strip()
        if href and not PRIVATE_PATH_RE.search(href):
            return _safe_markdown_href(href)
    return _safe_markdown_href(fallback)


def _coverage_first_public_ref(refs: list[Any]) -> str:
    for ref in refs:
        if isinstance(ref, str):
            href = ref.strip()
        elif isinstance(ref, dict):
            href = str(ref.get("detail_anchor") or ref.get("local_href") or ref.get("href") or ref.get("url") or "").strip()
        else:
            href = ""
        if href and not PRIVATE_PATH_RE.search(href):
            return _safe_markdown_href(href)
    return ""


def _coverage_source_diagnostics(
    roadmap: dict[str, Any],
    map_rows: list[dict[str, Any]],
    lens_rows: list[dict[str, Any]],
    task_rows: list[dict[str, Any]],
    resource_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    resources = _report_all_resource_entries(roadmap)
    resource_chunk_count = sum(len(_resource_evidence_chunks(item)) for item in resources if isinstance(item, dict))
    local_resource_count = sum(1 for item in resources if isinstance(item, dict) and _resource_is_materialized(item))
    local_note_resources = [item for item in resources if isinstance(item, dict) and _resource_is_local_note_like(item)]
    local_note_chunks = sum(len(_resource_evidence_chunks(item)) for item in local_note_resources)
    task_chunk_rows = [row for row in task_rows if _coerce_nonnegative_int(row.get("evidence_count")) > 0]
    diagnostics: list[dict[str, Any]] = []
    if map_rows or roadmap.get("paper_map"):
        diagnostics.append(
            {
                "label": "Target-paper logic claims",
                "covered": sum(1 for row in map_rows if row.get("status") == "covered"),
                "total": len(map_rows),
                "next": "Add source snippets to uncovered Paper Map nodes.",
                "href": _coverage_first_gap_href(map_rows, "paper_map.html"),
            }
        )
    if lens_rows or roadmap.get("paper_lens"):
        diagnostics.append(
            {
                "label": "Reading paragraphs",
                "covered": sum(1 for row in lens_rows if row.get("status") == "covered"),
                "total": len(lens_rows),
                "next": "Bind unsupported Paper Lens paragraphs to evidence references.",
                "href": _coverage_first_gap_href(lens_rows, "paper_lens.html"),
            }
        )
    if resource_rows or resource_chunk_count:
        diagnostics.append(
            {
                "label": "RAG/resource chunks",
                "covered": resource_chunk_count,
                "total": max(resource_chunk_count, len(resource_rows)),
                "next": "Index downloaded files or attach retrieved snippets to recommended resources.",
                "href": _coverage_first_gap_href(resource_rows, "roadmap.html#resource-library"),
            }
        )
    if resources:
        diagnostics.append(
            {
                "label": "Local/openable resources",
                "covered": local_resource_count,
                "total": len(resources),
                "next": "Download, copy, snapshot, or generate local files for link-only resources.",
                "href": _coverage_first_gap_href(resource_rows, "roadmap.html#resource-library"),
            }
        )
    if task_rows:
        diagnostics.append(
            {
                "label": "Mastery task evidence",
                "covered": len(task_chunk_rows),
                "total": len(task_rows),
                "next": "Attach each task to resource titles, chunks, or acceptance artifacts.",
                "href": _coverage_first_gap_href(task_rows, "roadmap.html#mastery-checklist-title"),
            }
        )
    if local_note_resources or local_note_chunks:
        diagnostics.append(
            {
                "label": "Local notes and notebooks",
                "covered": local_note_chunks,
                "total": max(local_note_chunks, len(local_note_resources)),
                "next": "Add Markdown, notebook, or local-note chunks when the learner brings private material.",
                "href": _coverage_first_resource_href(local_note_resources, "roadmap.html#resource-library"),
            }
        )
    return diagnostics


def _append_evidence_source_diagnostics(output: list[str], diagnostics: list[dict[str, Any]], is_zh: bool) -> None:
    output.extend([f"## {'证据来源诊断' if is_zh else 'Evidence Source Diagnostics'}", ""])
    output.extend(
        [
            "| {source} | {score} | {covered} | {total} | {next_step} |".format(
                source="来源" if is_zh else "Source",
                score="覆盖率" if is_zh else "Coverage",
                covered="已支撑" if is_zh else "Backed",
                total="应检查" if is_zh else "Expected",
                next_step="下一步" if is_zh else "Next diagnostic step",
            ),
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for item in diagnostics:
        label = _markdown_cell(_coverage_localized_diagnostic_label(str(item.get("label") or ""), is_zh))
        href = _safe_markdown_href(item.get("href") or "roadmap.html")
        covered = _coerce_nonnegative_int(item.get("covered"))
        total = _coerce_nonnegative_int(item.get("total"))
        score = _coverage_percent(covered, total)
        next_step = _markdown_cell(_coverage_localized_diagnostic_next(str(item.get("next") or ""), is_zh))
        output.append(f"| [{label}]({href}) | {score}% | {covered} | {total} | {next_step} |")
    output.append("")


def _append_measured_coverage_score(output: list[str], scores: list[dict[str, Any]], is_zh: bool) -> None:
    output.extend([f"## {'可量化覆盖分数' if is_zh else 'Measured Coverage Score'}", ""])
    if not scores:
        output.extend([("- 暂无可计分学习面。" if is_zh else "- No measurable learning surfaces yet."), ""])
        return
    output.extend(
        [
            "| {surface} | {score} | {covered} | {total} | {action} |".format(
                surface="学习面" if is_zh else "Surface",
                score="分数" if is_zh else "Score",
                covered="已覆盖" if is_zh else "Covered",
                total="总数" if is_zh else "Total",
                action="下一步" if is_zh else "Next action",
            ),
            "| --- | ---: | ---: | ---: | --- |",
        ]
    )
    for item in scores:
        label = _markdown_cell(item.get("label") or "")
        href = _safe_markdown_href(item.get("href") or "roadmap.html")
        action = _markdown_cell(_coverage_localized_action(str(item.get("action") or ""), is_zh))
        output.append(
            "| [{label}]({href}) | {score}% | {covered} | {total} | {action} |".format(
                label=label,
                href=href,
                score=_coerce_nonnegative_int(item.get("score")),
                covered=_coerce_nonnegative_int(item.get("covered")),
                total=_coerce_nonnegative_int(item.get("total")),
                action=action,
            )
        )
    output.append("")


def _append_priority_evidence_queue(output: list[str], gaps: list[dict[str, Any]], is_zh: bool) -> None:
    output.extend([f"## {'优先补证据队列' if is_zh else 'Priority Evidence Queue'}", ""])
    if not gaps:
        output.extend([("- 暂无高优先级证据缺口。" if is_zh else "- No high-priority evidence gaps remain."), ""])
        return
    output.extend(
        [
            "| {rank} | {surface} | {item} | {reason} | {action} |".format(
                rank="优先级" if is_zh else "Priority",
                surface="学习面" if is_zh else "Surface",
                item="项目" if is_zh else "Item",
                reason="缺口原因" if is_zh else "Gap reason",
                action="建议动作" if is_zh else "Suggested fix",
            ),
            "| ---: | --- | --- | --- | --- |",
        ]
    )
    for rank, row in enumerate(gaps[:8], start=1):
        label = _markdown_cell(row.get("label") or "")
        href = _safe_markdown_href(row.get("href") or "roadmap.html")
        surface = _markdown_cell(row.get("surface") or "")
        reason = _markdown_cell(_truncate_markdown(_markdown_text(row.get("detail") or ""), 120))
        action = _markdown_cell(_coverage_gap_action(str(row.get("surface") or ""), is_zh))
        output.append(f"| {rank} | {surface} | [{label}]({href}) | {reason} | {action} |")
    output.append("")


def _coverage_localized_action(action: str, is_zh: bool) -> str:
    if not is_zh:
        return action
    translations = {
        "Keep as release evidence.": "保留为发布证据。",
        "Add source snippets for uncovered claims.": "给未覆盖论断补原文片段。",
        "Bind uncovered paragraphs to local evidence or resources.": "给未覆盖段落绑定本地证据或资料。",
        "Attach each task to resources and checkable evidence.": "把任务绑定到资料和可检查证据。",
        "Download/snapshot resources or attach evidence chunks.": "下载/快照资料，或补证据片段。",
        "Add traceable evidence.": "补可追溯证据。",
    }
    return translations.get(action, action)


def _coverage_localized_diagnostic_label(label: str, is_zh: bool) -> str:
    if not is_zh:
        return label
    translations = {
        "Target-paper logic claims": "目标论文逻辑论断",
        "Reading paragraphs": "精读段落",
        "RAG/resource chunks": "RAG/资料片段",
        "Local/openable resources": "本地可打开资料",
        "Mastery task evidence": "掌握任务证据",
        "Local notes and notebooks": "本地笔记与 Notebook",
    }
    return translations.get(label, label)


def _coverage_localized_diagnostic_next(next_step: str, is_zh: bool) -> str:
    if not is_zh:
        return next_step
    translations = {
        "Add source snippets to uncovered Paper Map nodes.": "给未覆盖的 Paper Map 节点补原文片段。",
        "Bind unsupported Paper Lens paragraphs to evidence references.": "把未支撑的 Paper Lens 段落绑定到证据引用。",
        "Index downloaded files or attach retrieved snippets to recommended resources.": "索引已下载文件，或给推荐资料补检索片段。",
        "Download, copy, snapshot, or generate local files for link-only resources.": "给仅链接资料下载、复制、快照或生成本地文件。",
        "Attach each task to resource titles, chunks, or acceptance artifacts.": "把每个任务绑定到资料标题、证据片段或验收产物。",
        "Add Markdown, notebook, or local-note chunks when the learner brings private material.": "当用户带入私有材料时，补 Markdown、Notebook 或本地笔记片段。",
    }
    return translations.get(next_step, next_step)


def _coverage_gap_action(surface: str, is_zh: bool) -> str:
    if surface == "Paper Map":
        return "回到目标论文，给这个逻辑节点补一条原文证据。" if is_zh else "Add one source snippet to this logic node."
    if surface == "Paper Lens":
        return "给这段精读解释绑定原文片段、资料或本地文件。" if is_zh else "Bind this paragraph explanation to a source snippet, resource, or local file."
    if surface == "Mastery Tasks":
        return "给任务补资料标题、证据片段或验收产物。" if is_zh else "Attach resources, evidence chunks, or an acceptance artifact to the task."
    if surface == "Resource Library":
        return "优先下载/快照资料，或给推荐理由补证据片段。" if is_zh else "Download/snapshot the resource or attach evidence for why it matters."
    return "补一条可追溯证据。" if is_zh else "Add one traceable evidence item."


def _resource_is_local_note_like(resource: dict[str, Any]) -> bool:
    values = " ".join(
        str(resource.get(key) or "")
        for key in ("source", "type", "title", "label", "local_href", "file_name", "path")
    ).casefold()
    return any(marker in values for marker in ("local", "note", "notebook", ".ipynb", ".md", "markdown", "tex"))


def _coverage_paper_map_rows(roadmap: dict[str, Any], is_zh: bool) -> list[dict[str, Any]]:
    paper_map = roadmap.get("paper_map") if isinstance(roadmap.get("paper_map"), dict) else {}
    nodes = paper_map.get("nodes") if isinstance(paper_map.get("nodes"), list) else []
    rows: list[dict[str, Any]] = []
    for node in nodes:
        if not isinstance(node, dict) or node.get("role") != "core":
            continue
        evidence = [item for item in node.get("evidence") or [] if isinstance(item, dict)]
        href = _coverage_first_href(evidence) or f"paper_map.html#{_safe_anchor(node.get('id') or node.get('kind') or 'node')}"
        label = _markdown_text(node.get("label") or node.get("kind") or ("节点" if is_zh else "Node"))
        detail = _truncate_markdown(_markdown_text(node.get("plain_explanation") or node.get("summary") or ""), 140)
        rows.append(
            {
                "label": label,
                "status": "covered" if evidence else "gap",
                "evidence_count": len(evidence),
                "detail": detail or ("需要补充证据片段" if is_zh else "Needs evidence snippets"),
                "href": href,
            }
        )
    return rows


def _coverage_paper_lens_rows(roadmap: dict[str, Any], is_zh: bool) -> list[dict[str, Any]]:
    lens = roadmap.get("paper_lens") if isinstance(roadmap.get("paper_lens"), dict) else {}
    segments = lens.get("segments") if isinstance(lens.get("segments"), list) else []
    explanations = lens.get("inline_explanations") if isinstance(lens.get("inline_explanations"), list) else []
    explanations_by_segment = {
        str(item.get("segment_id") or item.get("id") or ""): item
        for item in explanations
        if isinstance(item, dict)
    }
    rows: list[dict[str, Any]] = []
    for index, segment in enumerate(segments[:12], start=1):
        if not isinstance(segment, dict):
            continue
        segment_id = str(segment.get("id") or "")
        explanation = explanations_by_segment.get(segment_id, {})
        refs = explanation.get("evidence_refs") if isinstance(explanation.get("evidence_refs"), list) else []
        resources = explanation.get("related_resources") if isinstance(explanation.get("related_resources"), list) else []
        evidence_count = len([item for item in refs if item]) + len([item for item in resources if item])
        evidence_href = _coverage_first_public_ref(refs)
        href = str(explanation.get("detail_anchor") or segment.get("detail_anchor") or evidence_href or f"paper_lens.html#detail-{_safe_anchor(segment_id or str(index))}")
        label = _markdown_text(segment.get("section_kind") or segment.get("heading") or f"{'段落' if is_zh else 'Paragraph'} {index}")
        detail = _truncate_markdown(_markdown_text(explanation.get("plain_meaning") or segment.get("original_text") or ""), 140)
        rows.append(
            {
                "label": label,
                "status": "covered" if evidence_count else "gap",
                "evidence_count": evidence_count,
                "detail": detail or ("未找到段落解释证据" if is_zh else "No paragraph evidence found"),
                "href": href,
            }
        )
    return rows


def _coverage_task_rows(roadmap: dict[str, Any], is_zh: bool) -> list[dict[str, Any]]:
    tasks = [item for item in roadmap.get("study_tasks", []) if isinstance(item, dict)]
    rows: list[dict[str, Any]] = []
    for index, task in enumerate(tasks, start=1):
        resources = task.get("resource_titles") if isinstance(task.get("resource_titles"), list) else []
        chunks = task.get("evidence_chunks") if isinstance(task.get("evidence_chunks"), list) else []
        evidence_count = len([item for item in resources if item]) + len([item for item in chunks if _is_traceable_evidence_chunk(item)])
        task_type = str(task.get("type") or "")
        href = _coverage_task_href(task_type, roadmap)
        label = _markdown_text(task.get("title") or f"{'任务' if is_zh else 'Task'} {index}")
        detail = _truncate_markdown(_markdown_text(task.get("evidence") or task.get("acceptance") or ""), 140)
        rows.append(
            {
                "label": label,
                "status": "covered" if evidence_count else "gap",
                "evidence_count": evidence_count,
                "detail": detail or ("需要绑定资料或证据片段" if is_zh else "Needs linked resources or evidence snippets"),
                "href": href,
            }
        )
    return rows


def _coverage_resource_rows(roadmap: dict[str, Any], is_zh: bool) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for resource in _report_all_resource_entries(roadmap)[:12]:
        chunks = _resource_evidence_chunks(resource)
        href = str(resource.get("local_href") or resource.get("href") or resource.get("url") or "roadmap.html#resource-library")
        if PRIVATE_PATH_RE.search(href):
            href = "roadmap.html#resource-library"
        status = "covered" if chunks or _resource_is_materialized(resource) else "gap"
        title = _markdown_text(resource.get("title") or resource.get("label") or ("资料" if is_zh else "Resource"))
        detail = _truncate_markdown(
            _markdown_text(resource.get("why_recommended") or resource.get("reason") or resource.get("critical_path_role") or resource.get("status") or ""),
            140,
        )
        rows.append(
            {
                "label": title,
                "status": status,
                "evidence_count": len(chunks),
                "detail": detail or ("已落地本地资料" if status == "covered" and is_zh else "Local/openable resource" if status == "covered" else "Needs local file or evidence snippet"),
                "href": href,
            }
        )
    return rows


def _append_coverage_table(output: list[str], heading: str, rows: list[dict[str, Any]], is_zh: bool) -> None:
    output.extend([f"## {heading}", ""])
    if not rows:
        output.extend([("- 暂无可检查项目。" if is_zh else "- No checkable items yet."), ""])
        return
    status_label = "状态" if is_zh else "Status"
    item_label = "项目" if is_zh else "Item"
    evidence_label = "证据数" if is_zh else "Evidence"
    detail_label = "说明" if is_zh else "Why it matters"
    output.extend(
        [
            f"| {item_label} | {status_label} | {evidence_label} | {detail_label} |",
            "| --- | --- | ---: | --- |",
        ]
    )
    for row in rows:
        label = _markdown_text(row.get("label") or "")
        href = _safe_markdown_href(row.get("href") or "roadmap.html")
        status = _coverage_status_label(str(row.get("status") or ""), is_zh)
        evidence_count = _coerce_nonnegative_int(row.get("evidence_count"))
        detail = _truncate_markdown(_markdown_text(row.get("detail") or ""), 180)
        output.append(f"| [{_markdown_cell(label)}]({href}) | {status} | {evidence_count} | {_markdown_cell(detail)} |")
    output.append("")


def _coverage_gap_lines(rows: list[dict[str, Any]], is_zh: bool) -> list[str]:
    gaps = [row for row in rows if row.get("status") != "covered"]
    if not gaps:
        return []
    lines: list[str] = []
    for row in gaps[:8]:
        label = _markdown_text(row.get("label") or "")
        href = _safe_markdown_href(row.get("href") or "roadmap.html")
        detail = _truncate_markdown(_markdown_text(row.get("detail") or ""), 160)
        if is_zh:
            lines.append(f"- 补强 [{label}]({href})：{detail or '加入来源片段、资料链接或验收证据。'}")
        else:
            lines.append(f"- Strengthen [{label}]({href}): {detail or 'Add source snippets, resource links, or task evidence.'}")
    return lines


def _coverage_first_href(evidence: list[dict[str, Any]]) -> str:
    for item in evidence:
        href = str(item.get("detail_anchor") or item.get("local_href") or item.get("href") or item.get("url") or "").strip()
        if href and not PRIVATE_PATH_RE.search(href):
            return _safe_markdown_href(href)
    return ""


def _coverage_task_href(task_type: str, roadmap: dict[str, Any]) -> str:
    has_map = bool(roadmap.get("paper_map"))
    has_lens = bool(roadmap.get("paper_lens"))
    if task_type in {"explain", "critique"} and has_map:
        return "paper_map.html"
    if task_type == "derive" and has_lens:
        return "paper_lens.html"
    return "roadmap.html#mastery-checklist-title"


def _coverage_status_label(status: str, is_zh: bool) -> str:
    if status == "covered":
        return "已覆盖" if is_zh else "covered"
    return "需补证据" if is_zh else "needs evidence"


def _safe_anchor(value: object) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip()).strip("-").lower()
    return text or "item"


def _intent_router_panel_html(roadmap: dict[str, Any], is_zh: bool) -> str:
    has_map = bool(roadmap.get("paper_map"))
    has_lens = bool(roadmap.get("paper_lens"))
    title = "按你的目的选择入口" if is_zh else "Choose by what you need now"
    body = (
        "不知道先点哪里时，直接按当前学习目的进入；每个入口都会保留本地资料和验收证据。"
        if is_zh
        else "If you are not sure where to click first, choose by your current goal; every path keeps local resources and mastery evidence nearby."
    )
    items = [
        {
            "intent": "quick-understand",
            "href": "paper_map.html" if has_map else "roadmap.html",
            "label": "最快理解" if is_zh else "Fastest understanding",
            "title": "我只想先看懂这篇" if is_zh else "I just need the paper to make sense",
            "body": "先看背景、动机、问题、方法、实验、贡献和局限的主链。" if is_zh else "Start with the main chain: background, motivation, problem, method, experiments, contributions, and limits.",
            "time": "3-10 分钟" if is_zh else "3-10 min",
        },
        {
            "intent": "presentation-ready",
            "href": "paper_lens.html" if has_lens else ("paper_map.html" if has_map else "roadmap.html"),
            "label": "汇报准备" if is_zh else "Presentation-ready",
            "title": "我要能讲给别人听" if is_zh else "I need to explain it to someone",
            "body": "把关键段落、直白解释、证据和汇报话术连起来。" if is_zh else "Connect key paragraphs, plain explanations, evidence, and presentation wording.",
            "time": "20-40 分钟" if is_zh else "20-40 min",
        },
        {
            "intent": "mastery-proof",
            "href": "roadmap.html",
            "label": "验收/复现" if is_zh else "Validation / reproduction",
            "title": "我要留下可检查结果" if is_zh else "I need checkable output",
            "body": "进入任务、资料库、进度勾选和 explain/derive/reproduce/critique 验收。" if is_zh else "Use tasks, the resource library, progress checks, and explain/derive/reproduce/critique validation.",
            "time": "按路线完成" if is_zh else "follow the route",
        },
    ]
    item_html = "\n".join(_intent_router_card_html(item) for item in items)
    return f"""<section class="intent-router-panel" data-intent-router="learning-goal" aria-labelledby="intent-router-title">
      <header>
        <div>
          <p class="eyebrow">{escape('学习意图' if is_zh else 'Learning intent')}</p>
          <h2 id="intent-router-title">{escape(title)}</h2>
          <p>{escape(body)}</p>
        </div>
      </header>
      <div class="intent-router-grid">
        {item_html}
      </div>
    </section>"""


def _intent_router_card_html(item: dict[str, str]) -> str:
    return f"""<a class="intent-card" data-intent="{escape(item['intent'])}" href="{escape(item['href'])}">
          <small>{escape(item["label"])}</small>
          <strong>{escape(item["title"])}</strong>
          <p>{escape(item["body"])}</p>
          <em>{escape(item["time"])}</em>
        </a>"""


def _report_health_panel_html(roadmap: dict[str, Any], is_zh: bool) -> str:
    resources = _report_resources(roadmap)
    total = len(resources)
    local_count = sum(1 for item in resources if _resource_is_materialized(item))
    failed_count = sum(1 for item in resources if str(item.get("status") or "") == "failed")
    evidence = _report_evidence_health(roadmap, is_zh)
    local_value = f"{local_count}/{total}" if total else ("待补齐" if is_zh else "pending")
    failed_value = str(failed_count) if failed_count else ("无失败" if is_zh else "none")
    title = "报告健康状态" if is_zh else "Report Health"
    body = (
        "打开前先确认这份报告是否可用：资料是否落地、隐私是否脱敏、排版是否安全，以及完整审计文件在哪里。"
        if is_zh
        else "Before learning, check whether the report is usable: local assets, privacy redaction, layout safety, and the full audit file."
    )
    audit_label = "查看完整审计" if is_zh else "Open full audit"
    cards = [
        {
            "label": "本地资料" if is_zh else "Local assets",
            "value": local_value,
            "detail": "已下载、复制、快照或生成的资料会优先本地打开。" if is_zh else "Downloaded, copied, snapshotted, or generated resources open locally first.",
        },
        {
            "label": "下载失败" if is_zh else "Download failures",
            "value": failed_value,
            "detail": "失败项会保留重试或原始链接，不会假装已经完成。" if is_zh else "Failures keep retry or source links instead of pretending they are complete.",
        },
        {
            "label": "证据覆盖" if is_zh else "Evidence coverage",
            "value": evidence["value"],
            "detail": evidence["detail"],
        },
        {
            "label": "隐私已脱敏" if is_zh else "Privacy redacted",
            "value": "已启用" if is_zh else "enabled",
            "detail": "共享型 HTML/JSON/MD 不写入本地绝对路径。" if is_zh else "Shareable HTML/JSON/MD avoid absolute local paths.",
        },
        {
            "label": "排版安全" if is_zh else "Layout safe",
            "value": "已检查" if is_zh else "checked",
            "detail": "长中文、英文标题和命令文本都有换行与宽度约束。" if is_zh else "Long Chinese, English titles, and commands have wrapping and width constraints.",
        },
    ]
    card_html = "\n".join(_report_health_card_html(card) for card in cards)
    return f"""<section class="report-health-panel" aria-labelledby="report-health-title">
      <header>
        <div>
          <p class="eyebrow">{escape('质量自检' if is_zh else 'Quality check')}</p>
          <h2 id="report-health-title">{escape(title)}</h2>
          <p>{escape(body)}</p>
        </div>
        <a class="report-health-link" href="report_audit.json">{escape(audit_label)}</a>
      </header>
      <div class="report-health-grid">
        {card_html}
      </div>
    </section>"""


def _report_health_card_html(card: dict[str, str]) -> str:
    return f"""<article class="report-health-card">
          <span>{escape(card["label"])}</span>
          <strong>{escape(card["value"])}</strong>
          <small>{escape(card["detail"])}</small>
        </article>"""


def _scenario_panel_html(is_zh: bool) -> str:
    title = "支持三种学习场景" if is_zh else "Three Learning Scenarios"
    body = (
        "当前报告只是其中一种入口。换目标时，不需要换工具：同一套规划、资料包和验收机制可以覆盖单篇论文、多篇论文和领域/课程路线。"
        if is_zh
        else "This report is one entry point. The same planner, bundle, and mastery checks cover one paper, paper sets, and field/course routes."
    )
    scenarios = [
        {
            "label": "01",
            "title": "单篇论文" if is_zh else "Single paper",
            "body": "用 Paper Map 抓主线，再用段落精读和验收任务确认真正掌握。" if is_zh else "Use Paper Map for the logic chain, then Paper Lens and mastery tasks.",
            "command": "fields-study-flow paper --url ./paper.pdf --output-dir ./report",
        },
        {
            "label": "02",
            "title": "多篇论文 / 文献组" if is_zh else "Paper set",
            "body": "把多篇论文作为本地资源加入，比较背景、方法、实验和贡献差异。" if is_zh else "Add multiple papers as local resources and compare background, methods, experiments, and contributions.",
            "command": "fields-study-flow roadmap --goal \"compare papers on LLM planning\" --local-resource ./papers",
        },
        {
            "label": "03",
            "title": "领域 / 课程路线" if is_zh else "Field / course route",
            "body": "从前置知识、核心概念、关键论文、项目和综合验收构建最短掌握路径。" if is_zh else "Build the shortest path across prerequisites, core concepts, key papers, projects, and synthesis.",
            "command": "fields-study-flow roadmap --goal \"learn diffusion models\" --target-kind field",
        },
    ]
    cards = "\n".join(_scenario_card_html(item) for item in scenarios)
    return f"""<section class="scenario-panel" aria-labelledby="scenario-title">
      <p class="eyebrow">{escape('产品覆盖' if is_zh else 'Coverage')}</p>
      <h2 id="scenario-title">{escape(title)}</h2>
      <p>{escape(body)}</p>
      <div class="scenario-grid">
        {cards}
      </div>
    </section>"""


def _scenario_card_html(card: dict[str, str]) -> str:
    return f"""<article class="scenario-card">
          <span>{escape(card["label"])}</span>
          <strong>{escape(card["title"])}</strong>
          <p>{escape(card["body"])}</p>
          <code>{escape(card["command"])}</code>
        </article>"""


def _report_resources(roadmap: dict[str, Any]) -> list[dict[str, Any]]:
    bundle = roadmap.get("study_bundle") if isinstance(roadmap.get("study_bundle"), dict) else {}
    resources = bundle.get("resources") if isinstance(bundle, dict) else []
    if not resources:
        resources = roadmap.get("resource_library") if isinstance(roadmap.get("resource_library"), list) else []
    return [item for item in resources if isinstance(item, dict)]


def _report_all_resource_entries(roadmap: dict[str, Any]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    bundle = roadmap.get("study_bundle") if isinstance(roadmap.get("study_bundle"), dict) else {}
    sources = [
        bundle.get("resources") if isinstance(bundle, dict) else [],
        roadmap.get("resource_library") if isinstance(roadmap.get("resource_library"), list) else [],
    ]
    for source in sources:
        if not isinstance(source, list):
            continue
        for item in source:
            if not isinstance(item, dict):
                continue
            key = (
                str(item.get("id") or item.get("title") or ""),
                str(item.get("url") or item.get("href") or ""),
                str(item.get("local_href") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            entries.append(item)
    return entries


def _resource_is_materialized(resource: dict[str, Any]) -> bool:
    return bool(resource.get("local_href")) or str(resource.get("status") or "") in {"downloaded", "copied", "snapshotted", "generated"}


def _report_evidence_health(roadmap: dict[str, Any], is_zh: bool) -> dict[str, str]:
    kg_summary = _dict_at(roadmap, "knowledge_graph", "summary")
    evidence_edges = _coerce_nonnegative_int(kg_summary.get("evidence_backed_edges"))
    resource_chunks = sum(len(_resource_evidence_chunks(item)) for item in _report_all_resource_entries(roadmap))
    lens_refs = _paper_lens_evidence_ref_count(roadmap)

    if evidence_edges:
        return {
            "value": f"{evidence_edges} 条边" if is_zh else f"{evidence_edges} edges",
            "detail": (
                f"知识图谱已有 {evidence_edges} 条证据化关系，资源片段 {resource_chunks} 条，精读引用 {lens_refs} 条。"
                if is_zh
                else f"Knowledge graph has {evidence_edges} evidence-backed edges, plus {resource_chunks} resource snippets and {lens_refs} reading references."
            ),
        }
    if resource_chunks or lens_refs:
        total_refs = resource_chunks + lens_refs
        return {
            "value": f"{total_refs} 条片段" if is_zh else f"{total_refs} snippets",
            "detail": (
                "资源库或精读页已有可追溯片段；核心结论仍建议继续补足 KG 证据边。"
                if is_zh
                else "The resource library or Paper Lens has traceable snippets; add KG evidence edges for stronger claims."
            ),
        }
    return {
        "value": "待补齐" if is_zh else "pending",
        "detail": (
            "未发现可追溯证据片段，建议补充目标论文 PDF、资料包或 RAG 索引。"
            if is_zh
            else "No traceable evidence snippets were found; add the target PDF, resource bundle, or RAG index."
        ),
    }


def _dict_at(root: dict[str, Any], *keys: str) -> dict[str, Any]:
    current: Any = root
    for key in keys:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _coerce_nonnegative_int(value: Any) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _resource_evidence_chunks(resource: dict[str, Any]) -> list[Any]:
    metadata = resource.get("metadata") if isinstance(resource.get("metadata"), dict) else {}
    rag = metadata.get("rag") if isinstance(metadata.get("rag"), dict) else {}
    chunks: list[Any] = []
    for key in ("evidence_chunks", "top_chunks", "chunks"):
        value = rag.get(key) or metadata.get(key)
        if isinstance(value, list):
            chunks.extend(chunk for chunk in value if _is_traceable_evidence_chunk(chunk))
    return chunks


def _is_traceable_evidence_chunk(chunk: Any) -> bool:
    if isinstance(chunk, str):
        return bool(chunk.strip())
    if not isinstance(chunk, dict):
        return False
    snippet = str(chunk.get("snippet") or chunk.get("text") or chunk.get("quote") or "").strip()
    locator = any(chunk.get(key) for key in ("detail_anchor", "local_href", "href", "url", "file_name", "resource_title"))
    return bool(snippet or locator)


def _paper_lens_evidence_ref_count(roadmap: dict[str, Any]) -> int:
    lens = roadmap.get("paper_lens") if isinstance(roadmap.get("paper_lens"), dict) else {}
    explanations = lens.get("inline_explanations") if isinstance(lens.get("inline_explanations"), list) else []
    total = 0
    for item in explanations:
        if not isinstance(item, dict):
            continue
        refs = item.get("evidence_refs")
        if isinstance(refs, list):
            total += len([ref for ref in refs if ref])
        elif refs:
            total += 1
    return total


def _quickstart_panel_html(is_zh: bool, has_paper_map: bool, has_paper_lens: bool) -> str:
    title = "10 分钟入门" if is_zh else "10-minute quickstart"
    badge = "适合单篇论文" if is_zh else "Best for one paper"
    body = (
        "不用先读完整报告。按下面三步走，先建立论文主线，再进入精读和验收。"
        if is_zh
        else "Do not read the whole report first. Follow these three steps to build the paper logic, then read and validate."
    )
    steps = [
        {
            "href": "paper_map.html" if has_paper_map else "roadmap.html",
            "label": "01",
            "title": "先看主图" if is_zh else "Start with the map",
            "body": "用背景、动机、问题、方法、实验、贡献、局限抓住主线。" if is_zh else "Capture the background, motivation, problem, method, experiments, contributions, and limits.",
            "enabled": has_paper_map,
        },
        {
            "href": "paper_lens.html" if has_paper_lens else "roadmap.html",
            "label": "02",
            "title": "再读关键段落" if is_zh else "Read key paragraphs",
            "body": "只读最关键原文段落和直白解释，避免一开始被资料淹没。" if is_zh else "Read the highest-value source paragraphs and plain explanations without drowning in resources.",
            "enabled": has_paper_lens,
        },
        {
            "href": "roadmap.html",
            "label": "03",
            "title": "最后做验收" if is_zh else "Finish with evidence",
            "body": "按解释、推导、复现、批判留下可检查的掌握证据。" if is_zh else "Leave checkable evidence for explain, derive, reproduce, and critique.",
            "enabled": True,
        },
    ]
    step_html = "\n".join(_quickstart_step_html(step) for step in steps)
    return f"""<section class="quickstart-panel fresh-user-flow-panel" data-fresh-user-flow="first-10-minutes" aria-labelledby="quickstart-title">
      <header>
        <div>
          <h2 id="quickstart-title">{escape(title)}</h2>
          <p>{escape(body)}</p>
        </div>
        <span class="quickstart-badge">{escape(badge)}</span>
      </header>
      <div class="quickstart-steps">
        {step_html}
      </div>
    </section>"""


def _quickstart_step_html(step: dict[str, Any]) -> str:
    tag = "a" if step.get("enabled") else "span"
    href = f' href="{escape(str(step["href"]))}"' if tag == "a" else ""
    return f"""<{tag}{href}>
          <small>{escape(str(step["label"]))}</small>
          <strong>{escape(str(step["title"]))}</strong>
          <p>{escape(str(step["body"]))}</p>
        </{tag}>"""


def _next_paper_panel_html(is_zh: bool) -> str:
    heading = "换成自己的论文" if is_zh else "Bring Your Own Paper"
    body = (
        "看完 demo 后，直接把下面命令里的 URL 或 PDF 路径换成自己的论文。报告仍会从 index.html 开始，并优先生成论文逻辑图和段落精读。"
        if is_zh
        else "After the demo, replace the URL or PDF path below with your own paper. The report still starts from index.html and prioritizes Paper Map plus Paper Lens."
    )
    url_label = "公开论文 URL / DOI" if is_zh else "Public paper URL / DOI"
    local_label = "本地 PDF" if is_zh else "Local PDF"
    note = (
        "需要下载资料包时再加 `--resource-dir ./study-assets/my-paper`；共享报告不会暴露本地绝对路径。"
        if is_zh
        else "Add `--resource-dir ./study-assets/my-paper` when you want a local bundle; shareable reports redact absolute local paths."
    )
    return f"""<section class="next-paper-panel" aria-labelledby="next-paper-title">
      <div>
        <p class="eyebrow">{escape('下一步' if is_zh else 'Next Step')}</p>
        <h2 id="next-paper-title">{escape(heading)}</h2>
        <p>{escape(body)}</p>
      </div>
      <div class="command-grid">
        <article>
          <span>{escape(url_label)}</span>
          <code>fields-study-flow paper --url https://arxiv.org/abs/1706.03762 --output-dir ./my-paper-report</code>
        </article>
        <article>
          <span>{escape(local_label)}</span>
          <code>fields-study-flow paper --url ./my-paper.pdf --output-dir ./my-paper-report</code>
        </article>
      </div>
      <p class="next-paper-note">{escape(note)}</p>
    </section>"""


def _dist_dir() -> Path | None:
    if _manifest_file(FRONTEND_DIST_DIR).exists():
        return FRONTEND_DIST_DIR
    repo_dist = Path(__file__).resolve().parent.parent / "frontend" / "dist"
    if _manifest_file(repo_dist).exists():
        return repo_dist
    return None


def _manifest_file(dist_dir: Path) -> Path:
    root_manifest = dist_dir / "manifest.json"
    if root_manifest.exists():
        return root_manifest
    return dist_dir / ".vite" / "manifest.json"


def _load_manifest(dist_dir: Path) -> dict[str, Any]:
    try:
        data = json.loads(_manifest_file(dist_dir).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _asset_href(asset_prefix: str, file_name: str) -> str:
    return "/".join(part.strip("/") for part in (asset_prefix, file_name) if part)


def _asset_text(dist_dir: Path, file_name: str) -> str:
    asset_path = dist_dir / file_name
    try:
        return asset_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FileNotFoundError(f"frontend asset is missing: {asset_path}") from exc


def _script_json(value: str) -> str:
    return value.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


def _inline_script_text(value: str) -> str:
    return value.replace("</script", "<\\/script")


def _style_text(value: str) -> str:
    return value.replace("</style", "<\\/style")


def _frontend_static_fallback_html(report_kind: str, roadmap: dict[str, Any], lang: str) -> str:
    is_zh = lang != "en"
    title = _display_report_base_title(roadmap)
    report_labels = {
        "paper_map": "论文逻辑图" if is_zh else "Paper Map",
        "paper_lens": "段落精读" if is_zh else "Paper Lens",
        "roadmap": "学习路线" if is_zh else "Roadmap",
    }
    heading = (
        f"{report_labels.get(report_kind, '报告')}正在启动"
        if is_zh
        else f"{report_labels.get(report_kind, 'Report')} is loading"
    )
    body = (
        "如果页面没有正常启动，可以先用下面的静态入口继续学习；重新生成报告或打开 index.html 也能恢复完整交互体验。"
        if is_zh
        else "If the interactive app does not start, use these static links to keep learning. Re-open index.html or regenerate the report to restore the full experience."
    )
    actions = _frontend_static_actions(report_kind, roadmap, is_zh)
    links = "\n".join(
        f'<a href="{escape(href)}">{escape(label)}</a>'
        for href, label in actions
    )
    return f"""<section class="static-report-fallback" data-report-static-fallback="{escape(report_kind)}" aria-label="{escape(report_labels.get(report_kind, 'report'))}">
    <div class="static-report-card">
      <p class="static-report-eyebrow">{escape('离线报告' if is_zh else 'Offline report')}</p>
      <h1>{escape(title)}</h1>
      <h2>{escape(heading)}</h2>
      <p>{escape(body)}</p>
      <nav class="static-report-actions" aria-label="{escape('备用入口' if is_zh else 'Fallback links')}">
        {links}
      </nav>
    </div>
  </section>"""


def _frontend_static_actions(report_kind: str, roadmap: dict[str, Any], is_zh: bool) -> list[tuple[str, str]]:
    actions: list[tuple[str, str]] = [("index.html", "返回入口页" if is_zh else "Back to Start")]
    if report_kind != "paper_map" and roadmap.get("paper_map"):
        actions.append(("paper_map.html", "进入论文逻辑图" if is_zh else "Open Paper Map"))
    if report_kind != "paper_lens" and roadmap.get("paper_lens"):
        actions.append(("paper_lens.html", "进入段落精读" if is_zh else "Open Paper Lens"))
    if report_kind != "roadmap":
        actions.append(("roadmap.html", "查看学习路线" if is_zh else "Open Roadmap"))
    if len(actions) == 1 and report_kind != "roadmap":
        actions.append(("roadmap.html", "查看学习路线" if is_zh else "Open Roadmap"))
    return actions


def _frontend_static_fallback_style() -> str:
    return """:root{color-scheme:light}.static-report-fallback{min-height:100vh;display:grid;place-items:center;padding:32px;background:#f6f3ed;color:#20201d;font-family:"Microsoft YaHei UI","Microsoft YaHei","PingFang SC","Noto Sans SC","Source Han Sans SC",Arial,sans-serif;line-height:1.65}.static-report-card{width:min(720px,100%);border:1px solid rgba(52,47,40,.14);border-radius:24px;padding:28px;background:rgba(255,255,255,.9);box-shadow:0 20px 60px rgba(47,42,35,.12);overflow-wrap:anywhere}.static-report-eyebrow{margin:0 0 8px;color:#2f6f73;font-size:.82rem;font-weight:800;letter-spacing:.08em}.static-report-card h1{margin:0 0 12px;font-size:clamp(1.55rem,5vw,2.8rem);line-height:1.12;letter-spacing:0}.static-report-card h2{margin:0 0 10px;font-size:1.05rem}.static-report-card p{margin:0 0 18px;color:#625d54}.static-report-actions{display:flex;flex-wrap:wrap;gap:10px}.static-report-actions a{display:inline-flex;align-items:center;min-height:40px;border:1px solid rgba(47,111,115,.28);border-radius:999px;padding:8px 14px;color:#245f63;background:rgba(47,111,115,.08);font-weight:800;text-decoration:none}.static-report-noscript{margin:0;padding:12px 16px;background:#fff8dd;color:#4f3b08;font-family:"Microsoft YaHei UI","Microsoft YaHei",Arial,sans-serif;overflow-wrap:anywhere}"""


def _sanitize_private_values(value: Any) -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, child in value.items():
            if key == "local_path":
                output[key] = None
            else:
                output[key] = _sanitize_private_values(child)
        return output
    if isinstance(value, list):
        return [_sanitize_private_values(item) for item in value]
    if isinstance(value, str):
        return PRIVATE_PATH_RE.sub("[private local path]", value)
    return value


def _report_title(report_kind: str, roadmap: dict[str, Any]) -> str:
    title = _display_report_base_title(roadmap)
    if report_kind == "paper_map":
        suffix = "论文逻辑图"
    elif report_kind == "paper_lens":
        suffix = "论文精读"
    else:
        suffix = "学习路线"
    return f"{title} - {suffix}"


def _display_report_base_title(roadmap: dict[str, Any]) -> str:
    title = _target_paper_title(roadmap) or str(roadmap.get("title") or "fields-study-flow")
    title = _strip_roadmap_prefix(_collapse_repeated_tail(title))
    if ":" in title:
        prefix = title.split(":", 1)[0].strip()
        if 6 <= len(prefix) <= 52:
            return prefix
    return _truncate(title or "fields-study-flow", 72)


def _target_paper_title(roadmap: dict[str, Any]) -> str:
    paper_lens = roadmap.get("paper_lens") if isinstance(roadmap.get("paper_lens"), dict) else {}
    target_papers = paper_lens.get("target_papers") if isinstance(paper_lens, dict) else []
    if isinstance(target_papers, list) and target_papers and isinstance(target_papers[0], dict):
        title = str(target_papers[0].get("title") or "").strip()
        if title:
            return title
    target = paper_lens.get("target") if isinstance(paper_lens, dict) else {}
    if isinstance(target, dict) and target.get("title"):
        return str(target["title"])
    paper_map = roadmap.get("paper_map") if isinstance(roadmap.get("paper_map"), dict) else {}
    map_target = paper_map.get("target") if isinstance(paper_map, dict) else {}
    if isinstance(map_target, dict) and map_target.get("title"):
        return str(map_target["title"])
    return ""


def _strip_roadmap_prefix(value: str) -> str:
    return re.sub(r"^(Learning Roadmap(?:\s*/\s*学习路线)?|学习路线)\s*[:：]\s*", "", value).strip()


def _collapse_repeated_tail(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    for _ in range(3):
        changed = False
        for size in range(len(text) // 2, 15, -1):
            tail = text[-size:].strip()
            prefix = text[:-size].strip()
            prefix_without_separator = re.sub(r"[\s:：,，;；-]+$", "", prefix).strip()
            if tail and _normalize_title_text(prefix_without_separator).endswith(_normalize_title_text(tail)):
                text = prefix_without_separator
                changed = True
                break
        if not changed:
            break
    return text


def _normalize_title_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _truncate(value: str, limit: int) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: max(1, limit)].rstrip()


def _html_lang(roadmap: dict[str, Any]) -> str:
    profile = roadmap.get("profile", {}) if isinstance(roadmap.get("profile"), dict) else {}
    language = str(profile.get("output_language") or roadmap.get("output_language") or "zh-CN")
    return "en" if language == "en" else "zh-CN"
