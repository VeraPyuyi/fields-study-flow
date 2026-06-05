from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch, Polygon, Rectangle


OUT = Path("docs/assets")
OUT.mkdir(parents=True, exist_ok=True)

TEXT_BOUNDS = []

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": [
            "Microsoft YaHei",
            "SimHei",
            "Noto Sans CJK SC",
            "Arial",
            "Helvetica",
            "DejaVu Sans",
            "sans-serif",
        ],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 8,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "legend.frameon": False,
    }
)

PALETTE = {
    "ink": "#172033",
    "muted": "#687287",
    "line": "#D4DEE9",
    "paper": "#FBFCFE",
    "blue": "#62A9D9",
    "blue_soft": "#EAF5FF",
    "teal": "#75C7B9",
    "teal_soft": "#E9F8F5",
    "green": "#85C996",
    "green_soft": "#ECF8EF",
    "gold": "#F3C85E",
    "gold_soft": "#FFF7DE",
    "coral": "#F28F82",
    "coral_soft": "#FFF0EE",
    "violet": "#9F8FE8",
    "violet_soft": "#F2EFFF",
    "rose": "#D97783",
    "rose_soft": "#FFF0F4",
}

COPY = {
    "en": {
        "subtitle": "Profile-aware AI/CS study routes from goal interview to ranked resources and agent-ready outputs",
        "claim": "diagnose -> discover -> rank -> deliver",
        "stages": ["Learner Diagnosis", "Multi-source Discovery + Ranking", "Roadmap Artifacts + Agent Loop"],
        "goal": ("Goal intake", ["paper deep read", "skill / project", "outcome + deadline"]),
        "knowledge_title": "Knowledge map",
        "knowledge": [("Math", 0.58), ("Code", 0.72), ("ML", 0.46), ("Systems", 0.38), ("Papers", 0.52)],
        "contract": ("Learning contract", ["time budget", "route language", "resource language"]),
        "note1": "Start from what the learner already knows.",
        "source_title": "Source registry",
        "source_nodes": ["Papers", "GitHub", "Video", "Courses", "Practice", "CN web"],
        "source_examples": ["arXiv", "OpenAlex", "PWC", "YouTube", "Bilibili", "HF", "Kaggle", "Zhihu"],
        "query": ("Queries", ["Transformer proof", "Transformer 推导", "preference weight"]),
        "rank_title": "Rank engine",
        "rank_signals": ["difficulty", "trust", "coverage", "license", "recency"],
        "safety": ("Safety gate", ["official APIs / open URLs"]),
        "note2": "High-quality cross-language resources\nstay visible.",
        "outputs": ("Generated outputs", ["roadmap.md", "roadmap.json", "learner profile", "resource index / anki.csv"]),
        "agents": ("Agent handoff", ["Codex", "Claude Code", "Cursor", "VS Code"]),
        "loop": ("Validate + iterate", ["source checks", "learner feedback", "next learning sprint"]),
        "note3": "Every resource includes why, prerequisites,\naccess notes, and next actions.",
        "footer": "Evidence logic: interview -> source registry -> scored resources -> traceable roadmap artifacts",
        "filename": "fields-study-flow-architecture-en.svg",
        "preview": "fields-study-flow-architecture-en.preview.png",
    },
    "zh": {
        "subtitle": "从目标访谈到多源资源排序，再到可被 agent 继续执行的个性化 AI/CS 学习路线",
        "claim": "诊断 -> 发现 -> 排序 -> 交付",
        "stages": ["学习者诊断", "多源发现 + 资源排序", "路线产物 + Agent 循环"],
        "goal": ("目标访谈", ["论文深读", "技能 / 项目 / 面试", "目标结果 + 截止时间"]),
        "knowledge_title": "知识地图",
        "knowledge": [("数学", 0.58), ("编程", 0.72), ("ML", 0.46), ("系统", 0.38), ("论文", 0.52)],
        "contract": ("学习契约", ["时间预算", "路线语言", "资料语言偏好"]),
        "note1": "从用户已经掌握的知识出发。",
        "source_title": "来源注册表",
        "source_nodes": ["论文", "GitHub", "视频", "课程", "实践", "中文社区"],
        "source_examples": ["arXiv", "OpenAlex", "PWC", "YouTube", "Bilibili", "HF", "Kaggle", "知乎"],
        "query": ("中英查询", ["Transformer derivation", "Transformer 推导", "按资料语言偏好加权"]),
        "rank_title": "排序引擎",
        "rank_signals": ["难度", "可信度", "覆盖", "许可", "时效"],
        "safety": ("安全防线", ["官方 API / 开放链接"]),
        "note2": "高质量跨语言资料\n不会被隐藏。",
        "outputs": ("生成产物", ["roadmap.md", "roadmap.json", "学习者画像", "资源索引 / anki.csv"]),
        "agents": ("Agent 交接", ["Codex", "Claude Code", "Cursor", "VS Code"]),
        "loop": ("校验 + 迭代", ["来源校验", "学习反馈", "下一轮学习冲刺"]),
        "note3": "每个资源说明推荐理由、前置知识、\n访问边界和下一步行动。",
        "footer": "证据链：访谈 -> 来源注册表 -> 资源评分 -> 可追踪路线产物",
        "filename": "fields-study-flow-architecture-zh.svg",
        "preview": "fields-study-flow-architecture-zh.preview.png",
    },
}


def rounded_rect(ax, x, y, w, h, fc, ec="#D5DEE8", lw=1.0, radius=0.018, alpha=1.0, z=2):
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle=f"round,pad=0.008,rounding_size={radius}",
        linewidth=lw,
        edgecolor=ec,
        facecolor=fc,
        alpha=alpha,
        zorder=z,
    )
    ax.add_patch(patch)
    return patch


def bounded_text(ax, bounds, name, *args, **kwargs):
    text = ax.text(*args, **kwargs)
    TEXT_BOUNDS.append((text, bounds, name))
    return text


def verify_text_bounds(fig, ax, locale: str):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    failures = []
    for text, bounds, name in TEXT_BOUNDS:
        bbox = text.get_window_extent(renderer=renderer)
        x, y, w, h = bounds
        x0, y0 = ax.transData.transform((x, y))
        x1, y1 = ax.transData.transform((x + w, y + h))
        left, right = sorted((x0, x1))
        bottom, top = sorted((y0, y1))
        tolerance = 3.0
        if bbox.x0 < left - tolerance or bbox.x1 > right + tolerance or bbox.y0 < bottom - tolerance or bbox.y1 > top + tolerance:
            failures.append(f"{locale}:{name}:{text.get_text()!r}")
    if failures:
        joined = "\n".join(failures)
        raise RuntimeError(f"Text exceeds its layout bounds:\n{joined}")


def draw_background(ax):
    ax.add_patch(Rectangle((0, 0), 1, 1, facecolor="#F7FAFD", edgecolor="none", zorder=0))
    for x in np.linspace(0.06, 0.94, 14):
        ax.add_patch(Circle((x, 0.07 + 0.012 * np.sin(16 * x)), 0.0032, color="#DDE7F1", alpha=0.6, zorder=0.5))
    for x, y, w, h, color in [
        (0.045, 0.855, 0.12, 0.02, "#DFF2FC"),
        (0.78, 0.875, 0.12, 0.02, "#E5F6EC"),
        (0.43, 0.055, 0.13, 0.018, "#F2EFFF"),
    ]:
        rounded_rect(ax, x, y, w, h, color, ec=color, lw=0, radius=0.012, alpha=0.65, z=0.6)


def arrow(ax, start, end, color="#8292AA", rad=0.0, lw=1.25, alpha=0.95, z=5):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=12,
            linewidth=lw,
            color=color,
            alpha=alpha,
            connectionstyle=f"arc3,rad={rad}",
            zorder=z,
        )
    )


def icon_target(ax, cx, cy, color):
    for radius, lw in [(0.019, 1.4), (0.012, 1.1), (0.0055, 1.0)]:
        ax.add_patch(Circle((cx, cy), radius, fill=False, edgecolor=color, linewidth=lw, zorder=6))
    ax.plot([cx + 0.015, cx + 0.032], [cy + 0.015, cy + 0.032], color=color, linewidth=1.4, zorder=6)
    ax.add_patch(Polygon([[cx + 0.032, cy + 0.032], [cx + 0.026, cy + 0.031], [cx + 0.031, cy + 0.026]], color=color, zorder=6))


def icon_network(ax, cx, cy, color):
    points = [(cx - 0.025, cy + 0.016), (cx, cy + 0.029), (cx + 0.025, cy + 0.016), (cx - 0.016, cy - 0.021), (cx + 0.018, cy - 0.022)]
    for a, b in [(0, 1), (1, 2), (0, 3), (2, 4), (3, 4), (1, 4)]:
        ax.plot([points[a][0], points[b][0]], [points[a][1], points[b][1]], color=color, linewidth=1.0, alpha=0.8, zorder=6)
    for px, py in points:
        ax.add_patch(Circle((px, py), 0.007, facecolor="#FFFFFF", edgecolor=color, linewidth=1.2, zorder=7))


def icon_doc(ax, cx, cy, color):
    ax.add_patch(Rectangle((cx - 0.022, cy - 0.03), 0.044, 0.058, fill=False, edgecolor=color, linewidth=1.4, zorder=6))
    ax.add_patch(Polygon([[cx + 0.006, cy + 0.028], [cx + 0.022, cy + 0.012], [cx + 0.006, cy + 0.012]], fill=False, edgecolor=color, linewidth=1.1, zorder=6))
    for yy in [cy + 0.004, cy - 0.009, cy - 0.021]:
        ax.plot([cx - 0.013, cx + 0.012], [yy, yy], color=color, linewidth=1.0, zorder=6)


def icon_shield(ax, cx, cy, color):
    pts = np.array(
        [
            [cx, cy + 0.031],
            [cx + 0.026, cy + 0.018],
            [cx + 0.021, cy - 0.021],
            [cx, cy - 0.033],
            [cx - 0.021, cy - 0.021],
            [cx - 0.026, cy + 0.018],
        ]
    )
    ax.add_patch(Polygon(pts, fill=False, edgecolor=color, linewidth=1.5, joinstyle="round", zorder=6))
    ax.plot([cx - 0.011, cx - 0.001, cx + 0.017], [cy, cy - 0.011, cy + 0.012], color=color, linewidth=1.6, zorder=6)


def stage_panel(ax, x, y, w, h, step, title, color, soft):
    rounded_rect(ax, x + 0.004, y - 0.006, w, h, "#D9E2ED", ec="#D9E2ED", lw=0, radius=0.018, alpha=0.28, z=1)
    rounded_rect(ax, x, y, w, h, "#FFFFFF", ec=color, lw=1.1, radius=0.018, alpha=1.0, z=2)
    rounded_rect(ax, x, y + h - 0.062, w, 0.062, soft, ec=color, lw=0.9, radius=0.018, alpha=1.0, z=3)
    ax.add_patch(Circle((x + 0.028, y + h - 0.031), 0.017, facecolor=color, edgecolor="#FFFFFF", linewidth=0.9, zorder=6))
    bounded_text(ax, (x + 0.017, y + h - 0.044, 0.022, 0.026), f"stage-number-{step}", x + 0.028, y + h - 0.031, str(step), ha="center", va="center", fontsize=8.3, weight="bold", color="#FFFFFF", zorder=7)
    bounded_text(ax, (x + 0.052, y + h - 0.052, w - 0.065, 0.04), f"stage-title-{step}", x + 0.052, y + h - 0.031, title, ha="left", va="center", fontsize=10.2, weight="bold", color=PALETTE["ink"], zorder=7)


def mini_card(ax, x, y, w, h, title, lines, color, icon=None):
    rounded_rect(ax, x, y, w, h, "#FFFFFF", ec="#D6E0EC", lw=0.85, radius=0.014, alpha=1.0, z=4)
    text_x = x + 0.058 if icon else x + 0.022
    text_w = w - (text_x - x) - 0.022
    if icon:
        ax.add_patch(Circle((x + 0.031, y + h - 0.034), 0.019, facecolor=color, edgecolor="none", alpha=0.22, zorder=5))
        if icon == "target":
            icon_target(ax, x + 0.031, y + h - 0.034, color)
        elif icon == "network":
            icon_network(ax, x + 0.031, y + h - 0.034, color)
        elif icon == "doc":
            icon_doc(ax, x + 0.031, y + h - 0.034, color)
        elif icon == "shield":
            icon_shield(ax, x + 0.031, y + h - 0.034, color)
    bounded_text(ax, (text_x - 0.006, y + h - 0.064, text_w + 0.012, 0.052), f"{title}-title", text_x, y + h - 0.026, title, ha="left", va="top", fontsize=7.5, weight="bold", color=PALETTE["ink"], zorder=6)
    for i, line in enumerate(lines):
        bounded_text(ax, (text_x - 0.006, y - 0.002, text_w + 0.012, h - 0.044), f"{title}-line-{i}", text_x, y + h - 0.054 - 0.017 * i, line, ha="left", va="top", fontsize=5.6, color=PALETTE["muted"], zorder=6)


def note_strip(ax, x, y, w, h, text, color, name):
    rounded_rect(ax, x, y, w, h, color, ec="#D7E0EA", lw=0.8, radius=0.014, alpha=0.92, z=4)
    bounded_text(ax, (x + 0.015, y + 0.006, w - 0.03, h - 0.012), name, x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=6.6, color=PALETTE["ink"], linespacing=1.14, zorder=6)


def chip(ax, x, y, w, label, color, name):
    rounded_rect(ax, x, y, w, 0.031, "#FFFFFF", ec="#D4DEE9", lw=0.75, radius=0.014, alpha=1.0, z=5)
    ax.add_patch(Circle((x + 0.014, y + 0.0155), 0.005, facecolor=color, edgecolor="none", zorder=6))
    bounded_text(ax, (x + 0.022, y + 0.006, w - 0.028, 0.019), name, x + 0.025, y + 0.0155, label, ha="left", va="center", fontsize=6.2, color=PALETTE["ink"], zorder=6)


def draw_knowledge_map(ax, x, y, w, h, title, rows, color):
    rounded_rect(ax, x, y, w, h, "#FFFFFF", ec="#D6E0EC", lw=0.85, radius=0.014, z=4)
    bounded_text(ax, (x + 0.018, y + h - 0.042, w - 0.036, 0.03), "knowledge-title", x + 0.018, y + h - 0.022, title, ha="left", va="top", fontsize=8.4, weight="bold", color=PALETTE["ink"], zorder=6)
    y0 = y + h - 0.068
    for i, (label, value) in enumerate(rows):
        yy = y0 - 0.022 * i
        bounded_text(ax, (x + 0.018, yy - 0.01, 0.055, 0.02), f"knowledge-label-{i}", x + 0.018, yy, label, ha="left", va="center", fontsize=6.5, color=PALETTE["muted"], zorder=6)
        ax.add_patch(Rectangle((x + 0.085, yy - 0.006), w - 0.12, 0.012, facecolor="#EDF2F7", edgecolor="none", zorder=5))
        ax.add_patch(Rectangle((x + 0.085, yy - 0.006), (w - 0.12) * value, 0.012, facecolor=color, edgecolor="none", alpha=0.75, zorder=6))


def draw_source_graph(ax, x, y, w, h, cfg):
    rounded_rect(ax, x, y, w, h, "#FFFFFF", ec="#D6E0EC", lw=0.85, radius=0.014, z=4)
    bounded_text(ax, (x + 0.016, y + h - 0.052, w - 0.032, 0.044), "source-registry-title", x + 0.018, y + h - 0.023, cfg["source_title"], ha="left", va="top", fontsize=8.2, weight="bold", color=PALETTE["ink"], zorder=6)
    cx, cy = x + w / 2, y + h / 2 - 0.006
    ax.add_patch(Circle((cx, cy), 0.033, facecolor=PALETTE["teal_soft"], edgecolor=PALETTE["teal"], linewidth=1.0, zorder=5))
    icon_network(ax, cx, cy, PALETTE["teal"])
    node_positions = [
        (x + 0.055, y + h - 0.075),
        (x + w - 0.055, y + h - 0.075),
        (x + 0.045, y + 0.056),
        (x + w - 0.045, y + 0.056),
        (x + w / 2 - 0.06, y + 0.035),
        (x + w / 2 + 0.06, y + 0.035),
    ]
    colors = [PALETTE["blue"], PALETTE["violet"], PALETTE["coral"], PALETTE["green"], PALETTE["gold"], PALETTE["rose"]]
    for i, ((px, py), label) in enumerate(zip(node_positions, cfg["source_nodes"])):
        arrow(ax, (px, py), (cx, cy), color="#B7C4D3", lw=0.9, alpha=0.7, z=4)
        ax.add_patch(Circle((px, py), 0.018, facecolor="#FFFFFF", edgecolor=colors[i], linewidth=1.2, zorder=6))
        bounded_text(ax, (px - 0.04, py - 0.039, 0.08, 0.026), f"source-node-{i}", px, py - 0.029, label, ha="center", va="center", fontsize=5.8, color=PALETTE["ink"], zorder=6)


def draw_rank_engine(ax, x, y, w, h, cfg):
    rounded_rect(ax, x, y, w, h, "#FFFFFF", ec="#D6E0EC", lw=0.85, radius=0.014, z=4)
    bounded_text(ax, (x + 0.016, y + h - 0.052, w - 0.032, 0.044), "rank-title", x + 0.018, y + h - 0.023, cfg["rank_title"], ha="left", va="top", fontsize=8.2, weight="bold", color=PALETTE["ink"], zorder=6)
    matrix_x, matrix_y = x + 0.02, y + 0.03
    cell = 0.016
    matrix = np.array(
        [
            [0.35, 0.62, 0.70, 0.48],
            [0.55, 0.88, 0.72, 0.60],
            [0.46, 0.66, 0.92, 0.72],
            [0.30, 0.48, 0.63, 0.82],
        ]
    )
    for r in range(4):
        for c in range(4):
            alpha = 0.25 + 0.55 * matrix[r, c]
            ax.add_patch(Rectangle((matrix_x + c * cell, matrix_y + (3 - r) * cell), cell - 0.002, cell - 0.002, facecolor=PALETTE["violet"], edgecolor="none", alpha=alpha, zorder=5))
    bounded_text(ax, (matrix_x, matrix_y - 0.022, 0.07, 0.02), "rank-matrix-caption", matrix_x + 0.032, matrix_y - 0.011, "fit x trust", ha="center", va="center", fontsize=5.6, color=PALETTE["muted"], zorder=6)
    chip_x = x + 0.108
    for i, signal in enumerate(cfg["rank_signals"]):
        row = i // 2
        col = i % 2
        chip(ax, chip_x + col * 0.086, y + h - 0.073 - row * 0.038, 0.078, signal, [PALETTE["blue"], PALETTE["teal"], PALETTE["gold"], PALETTE["rose"], PALETTE["green"]][i], f"rank-signal-{i}")


def draw_outputs(ax, x, y, w, h, title, lines, color):
    rounded_rect(ax, x, y, w, h, "#FFFFFF", ec="#D6E0EC", lw=0.85, radius=0.014, z=4)
    icon_doc(ax, x + 0.036, y + h - 0.047, color)
    bounded_text(ax, (x + 0.072, y + h - 0.064, w - 0.088, 0.042), "outputs-title", x + 0.072, y + h - 0.028, title, ha="left", va="top", fontsize=8.6, weight="bold", color=PALETTE["ink"], zorder=6)
    for i, line in enumerate(lines):
        yy = y + h - 0.076 - i * 0.027
        rounded_rect(ax, x + 0.082, yy - 0.018, w - 0.108, 0.022, "#F7FAFD", ec="#E2EAF3", lw=0.55, radius=0.01, z=5)
        bounded_text(ax, (x + 0.092, yy - 0.018, w - 0.128, 0.022), f"output-line-{i}", x + 0.096, yy - 0.007, line, ha="left", va="center", fontsize=6.4, color=PALETTE["muted"], zorder=6)


def draw_agent_handoff(ax, x, y, w, h, title, agents):
    rounded_rect(ax, x, y, w, h, "#FFFFFF", ec="#D6E0EC", lw=0.85, radius=0.014, z=4)
    bounded_text(ax, (x + 0.018, y + h - 0.052, w - 0.036, 0.042), "agent-title", x + 0.02, y + h - 0.022, title, ha="left", va="top", fontsize=8.1, weight="bold", color=PALETTE["ink"], zorder=6)
    colors = [PALETTE["blue"], PALETTE["violet"], PALETTE["green"], PALETTE["gold"]]
    for i, agent in enumerate(agents):
        col = i % 2
        row = i // 2
        chip(ax, x + 0.026 + col * ((w - 0.068) / 2 + 0.016), y + 0.052 - row * 0.039, (w - 0.068) / 2, agent, colors[i], f"agent-{agent}")


def draw_figure(locale: str):
    TEXT_BOUNDS.clear()
    cfg = COPY[locale]
    fig, ax = plt.subplots(figsize=(14.0, 7.4), dpi=190)
    fig.patch.set_facecolor("white")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    draw_background(ax)

    bounded_text(ax, (0.03, 0.895, 0.65, 0.075), "main-title", 0.035, 0.948, "fields-study-flow Framework", ha="left", va="top", fontsize=18.8, weight="bold", color=PALETTE["ink"], zorder=7)
    bounded_text(ax, (0.035, 0.872, 0.62, 0.04), "main-subtitle", 0.035, 0.89, cfg["subtitle"], ha="left", va="center", fontsize=9.4, color=PALETTE["muted"], zorder=7)
    rounded_rect(ax, 0.72, 0.882, 0.245, 0.052, "#FFFFFF", ec="#D4DEE9", lw=0.8, radius=0.018, z=3)
    bounded_text(ax, (0.735, 0.894, 0.215, 0.027), "claim", 0.842, 0.908, cfg["claim"], ha="center", va="center", fontsize=8.1, weight="bold", color=PALETTE["blue"], zorder=7)
    ax.plot([0.035, 0.965], [0.858, 0.858], color="#D8E1EC", linewidth=1.1, zorder=2)

    py, ph = 0.105, 0.725
    x1, w1 = 0.035, 0.285
    x2, w2 = 0.345, 0.31
    x3, w3 = 0.68, 0.285

    stage_panel(ax, x1, py, w1, ph, 1, cfg["stages"][0], PALETTE["blue"], PALETTE["blue_soft"])
    stage_panel(ax, x2, py, w2, ph, 2, cfg["stages"][1], PALETTE["green"], PALETTE["green_soft"])
    stage_panel(ax, x3, py, w3, ph, 3, cfg["stages"][2], PALETTE["violet"], PALETTE["violet_soft"])
    arrow(ax, (x1 + w1 + 0.006, py + ph * 0.56), (x2 - 0.011, py + ph * 0.56), color="#8594AA", lw=1.5)
    arrow(ax, (x2 + w2 + 0.006, py + ph * 0.56), (x3 - 0.011, py + ph * 0.56), color="#8594AA", lw=1.5)

    mini_card(ax, x1 + 0.02, 0.66, w1 - 0.04, 0.112, cfg["goal"][0], cfg["goal"][1], PALETTE["blue"], icon="target")
    draw_knowledge_map(ax, x1 + 0.02, 0.465, w1 - 0.04, 0.16, cfg["knowledge_title"], cfg["knowledge"], PALETTE["blue"])
    mini_card(ax, x1 + 0.02, 0.305, w1 - 0.04, 0.117, cfg["contract"][0], cfg["contract"][1], PALETTE["gold"], icon="doc")
    note_strip(ax, x1 + 0.02, 0.13, w1 - 0.04, 0.075, cfg["note1"], PALETTE["blue_soft"], "note-1")

    draw_source_graph(ax, x2 + 0.02, 0.60, w2 - 0.04, 0.172, cfg)
    mini_card(ax, x2 + 0.02, 0.445, (w2 - 0.054) / 2, 0.112, cfg["query"][0], cfg["query"][1], PALETTE["teal"])
    mini_card(ax, x2 + 0.027 + (w2 - 0.054) / 2, 0.445, (w2 - 0.054) / 2, 0.112, "Open policy" if locale == "en" else "开放策略", ["arXiv / OA", "PWC", "YT / Bili"] if locale == "en" else ["arXiv / OA", "PWC", "YT / B站"], PALETTE["green"])
    draw_rank_engine(ax, x2 + 0.02, 0.255, w2 - 0.04, 0.148, cfg)
    mini_card(ax, x2 + 0.02, 0.175, w2 - 0.04, 0.081, cfg["safety"][0], cfg["safety"][1], PALETTE["rose"])
    note_strip(ax, x2 + 0.02, 0.115, w2 - 0.04, 0.049, cfg["note2"], PALETTE["green_soft"], "note-2")

    draw_outputs(ax, x3 + 0.02, 0.602, w3 - 0.04, 0.17, cfg["outputs"][0], cfg["outputs"][1], PALETTE["green"])
    draw_agent_handoff(ax, x3 + 0.02, 0.425, w3 - 0.04, 0.13, cfg["agents"][0], cfg["agents"][1])
    mini_card(ax, x3 + 0.02, 0.265, w3 - 0.04, 0.118, cfg["loop"][0], cfg["loop"][1], PALETTE["violet"], icon="network")
    note_strip(ax, x3 + 0.02, 0.13, w3 - 0.04, 0.075, cfg["note3"], PALETTE["violet_soft"], "note-3")

    bounded_text(ax, (0.18, 0.045, 0.64, 0.035), "footer", 0.5, 0.061, cfg["footer"], ha="center", va="center", fontsize=7.8, color=PALETTE["muted"], zorder=7)

    verify_text_bounds(fig, ax, locale)
    fig.savefig(OUT / cfg["filename"], bbox_inches="tight")
    fig.savefig(OUT / cfg["preview"], dpi=220, bbox_inches="tight")
    plt.close(fig)
    print(OUT / cfg["filename"])
    print(OUT / cfg["preview"])


def main():
    draw_figure("en")
    draw_figure("zh")


if __name__ == "__main__":
    main()
