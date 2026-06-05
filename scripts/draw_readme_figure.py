from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


OUT = Path("docs/assets")
OUT.mkdir(parents=True, exist_ok=True)

mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 9,
        "axes.spines.right": False,
        "axes.spines.top": False,
        "legend.frameon": False,
    }
)

COLORS = {
    "ink": "#1F2937",
    "muted": "#6B7280",
    "line": "#CBD5E1",
    "panel": "#F8FAFC",
    "profile": "#F4D06F",
    "source": "#8EC5D6",
    "tools": "#A7D8B8",
    "rank": "#F2A7A0",
    "output": "#B8D8A7",
    "safety": "#D66A6A",
    "accent": "#3B82F6",
}


def rounded_box(ax, x, y, w, h, title, lines, color, title_color="#111827"):
    box = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.025",
        linewidth=1.0,
        edgecolor="#D1D5DB",
        facecolor=color,
        zorder=2,
    )
    ax.add_patch(box)
    ax.text(x + 0.025 * w, y + h - 0.18 * h, title, ha="left", va="top", color=title_color, weight="bold", fontsize=10.5)
    for i, line in enumerate(lines):
        ax.text(x + 0.025 * w, y + h - (0.4 + 0.18 * i) * h, line, ha="left", va="top", color=COLORS["ink"], fontsize=8.3)


def chip(ax, x, y, text, color="#FFFFFF", edge="#CBD5E1", width=0.08):
    patch = FancyBboxPatch(
        (x, y),
        width,
        0.035,
        boxstyle="round,pad=0.008,rounding_size=0.018",
        linewidth=0.8,
        edgecolor=edge,
        facecolor=color,
        zorder=3,
    )
    ax.add_patch(patch)
    ax.text(x + width / 2, y + 0.0175, text, ha="center", va="center", fontsize=7.2, color=COLORS["ink"])


def arrow(ax, x1, y1, x2, y2, rad=0.0):
    patch = FancyArrowPatch(
        (x1, y1),
        (x2, y2),
        arrowstyle="-|>",
        mutation_scale=12,
        linewidth=1.2,
        color="#64748B",
        connectionstyle=f"arc3,rad={rad}",
        zorder=1,
    )
    ax.add_patch(patch)


def main():
    fig, ax = plt.subplots(figsize=(13.6, 7.2), dpi=180)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")

    ax.text(0.035, 0.955, "Git-4-Study Flow", fontsize=19, weight="bold", color=COLORS["ink"], ha="left", va="top")
    ax.text(
        0.035,
        0.905,
        "From learner intent to ranked multi-source resources and agent-ready roadmap artifacts",
        fontsize=10.5,
        color=COLORS["muted"],
        ha="left",
        va="top",
    )

    y = 0.53
    h = 0.22
    w = 0.16
    xs = [0.035, 0.245, 0.455, 0.665, 0.84]

    rounded_box(
        ax,
        xs[0],
        y,
        w,
        h,
        "1. Goal + Profile",
        ["paper / skill / project", "known topics + levels", "time budget", "route + resource language"],
        COLORS["profile"],
    )
    rounded_box(
        ax,
        xs[1],
        y,
        w,
        h,
        "2. Source Registry",
        ["declared access modes", "language coverage", "quality signals", "open / link-only policy"],
        COLORS["source"],
    )
    rounded_box(
        ax,
        xs[2],
        y,
        w,
        h,
        "3. MCP Toolchain",
        ["assessKnowledge", "discover + search", "rankResources", "buildRoadmap"],
        COLORS["tools"],
    )
    rounded_box(
        ax,
        xs[3],
        y,
        w,
        h,
        "4. Rank + Guard",
        ["difficulty fit", "trust score", "URL de-duplication", "piracy / bypass checks"],
        COLORS["rank"],
    )
    rounded_box(
        ax,
        xs[4],
        y,
        0.13,
        h,
        "5. Outputs",
        ["roadmap.md", "roadmap.json", "profile + index", "agent continuation"],
        COLORS["output"],
    )

    for i in range(4):
        arrow(ax, xs[i] + (w if i < 4 else 0.13), y + h / 2, xs[i + 1] - 0.012, y + h / 2)

    ax.text(0.245, 0.45, "Multi-source learning graph", ha="left", va="center", fontsize=10.5, weight="bold", color=COLORS["ink"])
    source_chips = [
        ("GitHub", 0.245, 0.392, 0.075),
        ("arXiv", 0.327, 0.392, 0.062),
        ("OpenAlex", 0.396, 0.392, 0.078),
        ("Papers w/ Code", 0.481, 0.392, 0.105),
        ("YouTube", 0.593, 0.392, 0.078),
        ("Bilibili", 0.678, 0.392, 0.07),
        ("Zhihu", 0.755, 0.392, 0.06),
        ("Hugging Face", 0.822, 0.392, 0.102),
        ("Kaggle", 0.245, 0.342, 0.07),
        ("MIT OCW", 0.322, 0.342, 0.078),
        ("fast.ai", 0.407, 0.342, 0.066),
        ("Google MLCC", 0.48, 0.342, 0.102),
        ("MOOC", 0.589, 0.342, 0.064),
    ]
    for text, x, yy, ww in source_chips:
        chip(ax, x, yy, text, width=ww)

    rounded_box(
        ax,
        0.035,
        0.155,
        0.29,
        0.18,
        "Language policy",
        ["output language: zh-CN / en / bilingual", "resource language: zh-first / en-first / balanced", "hard filters: zh-only / en-only"],
        "#EEF2FF",
    )
    rounded_box(
        ax,
        0.355,
        0.155,
        0.29,
        0.18,
        "Safety boundary",
        ["official APIs or user-provided URLs", "no pirate mirrors or login bypass", "no video downloads or long copyrighted copies"],
        "#FFF1F2",
    )
    rounded_box(
        ax,
        0.675,
        0.155,
        0.29,
        0.18,
        "Agent integrations",
        ["Codex / Claude Code skills", "Cursor + VS Code MCP configs", "CLI and JSON-lines tool server"],
        "#F0FDF4",
    )

    arrow(ax, 0.18, 0.335, 0.18, y - 0.015, rad=-0.15)
    arrow(ax, 0.5, 0.335, 0.745, y - 0.015, rad=0.15)
    arrow(ax, 0.82, 0.335, 0.905, y - 0.015, rad=-0.12)

    ax.text(
        0.5,
        0.065,
        "Figure logic: profile-aware source discovery -> language-sensitive ranking -> safe, traceable roadmap outputs.",
        ha="center",
        va="center",
        fontsize=9.2,
        color=COLORS["muted"],
    )

    svg_path = OUT / "git4study-flow-architecture.svg"
    fig.savefig(svg_path, bbox_inches="tight")
    plt.close(fig)
    print(svg_path)


if __name__ == "__main__":
    main()
