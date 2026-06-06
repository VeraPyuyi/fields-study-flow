from __future__ import annotations

from html import escape
from pathlib import Path


OUT = Path("docs/assets")
OUT.mkdir(parents=True, exist_ok=True)

PALETTE = {
    "ink": "#172033",
    "muted": "#657085",
    "line": "#D8E2EE",
    "paper": "#F7FAFD",
    "blue": "#62A9D9",
    "blue_soft": "#EAF5FF",
    "green": "#85C996",
    "green_soft": "#ECF8EF",
    "violet": "#9F8FE8",
    "violet_soft": "#F2EFFF",
    "gold": "#F3C85E",
    "gold_soft": "#FFF7DE",
}


COPY = {
    "en": {
        "filename": "fields-study-flow-architecture-en.svg",
        "title": "fields-study-flow",
        "subtitle": "Unified mastery paths for papers, fields, courses, local resources, and live discovery",
        "panels": [
            ("1", "Goal + Profile", "paper / field / course", ["route depth: fastest, balanced, complete", "learning style: practical, theory, video", "language and time preferences"]),
            ("2", "Resource Discovery", "open APIs + explicit local paths", ["arXiv, OpenAlex, Semantic Scholar, GitHub, Hugging Face", "PDF, TeX, notebooks, notes, code", "credentialed sources stay manual-link-only"]),
            ("3", "Mastery Path", "explain, derive, reproduce, critique", ["route audit and quality gates", "study tasks, next actions, final artifact", "Markdown, JSON, SVG, HTML report"]),
        ],
        "footer": "Default path is balanced; switch to fastest for shortest viable mastery or complete for broader coverage.",
    },
    "zh": {
        "filename": "fields-study-flow-architecture-zh.svg",
        "title": "fields-study-flow",
        "subtitle": "\u7edf\u4e00\u751f\u6210\u8bba\u6587\u3001\u9886\u57df\u3001\u8bfe\u7a0b\u3001\u672c\u5730\u8d44\u6e90\u548c\u5b9e\u65f6\u641c\u7d22\u7684\u638c\u63e1\u8def\u5f84",
        "panels": [
            (
                "1",
                "\u76ee\u6807\u4e0e\u753b\u50cf",
                "\u8bba\u6587 / \u9886\u57df / \u8bfe\u7a0b",
                [
                    "\u8def\u7ebf\u6df1\u5ea6\uff1a\u6700\u5feb\u3001\u5e73\u8861\u3001\u6700\u5b8c\u6574",
                    "\u5b66\u4e60\u98ce\u683c\uff1a\u5b9e\u6218\u3001\u7406\u8bba\u3001\u89c6\u9891",
                    "\u8bed\u8a00\u504f\u597d\u4e0e\u65f6\u95f4\u9884\u7b97",
                ],
            ),
            (
                "2",
                "\u8d44\u6e90\u53d1\u73b0",
                "\u5f00\u653e API + \u663e\u5f0f\u672c\u5730\u8def\u5f84",
                [
                    "arXiv\u3001OpenAlex\u3001Semantic Scholar\u3001GitHub\u3001Hugging Face",
                    "PDF\u3001TeX\u3001Notebook\u3001\u7b14\u8bb0\u3001\u4ee3\u7801",
                    "\u9700\u51ed\u8bc1\u6765\u6e90\u53ea\u4f5c\u4e3a\u624b\u52a8\u94fe\u63a5\u5165\u53e3",
                ],
            ),
            (
                "3",
                "\u638c\u63e1\u8def\u5f84",
                "\u89e3\u91ca\u3001\u63a8\u5bfc\u3001\u590d\u73b0\u3001\u6279\u5224",
                [
                    "\u8def\u7ebf\u5ba1\u8ba1\u4e0e\u8d28\u91cf\u95e8",
                    "\u5b66\u4e60\u4efb\u52a1\u3001\u4e0b\u4e00\u6b65\u884c\u52a8\u4e0e\u6700\u7ec8\u4ea7\u51fa",
                    "Markdown\u3001JSON\u3001SVG\u3001HTML \u62a5\u544a",
                ],
            ),
        ],
        "footer": "\u9ed8\u8ba4\u4f7f\u7528\u5e73\u8861\u8def\u7ebf\uff1b\u9700\u8981\u6700\u77ed\u8def\u5f84\u7528 fastest\uff0c\u9700\u8981\u5b8c\u6574\u8986\u76d6\u7528 complete\u3002",
    },
}


def wrap_text(value: str, limit: int) -> list[str]:
    if len(value) <= limit:
        return [value]
    words = value.split()
    if len(words) == 1:
        return [value[i : i + limit] for i in range(0, len(value), limit)]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > limit and current:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def text(x: int, y: int, value: str, size: int = 16, weight: str = "400", fill: str = "ink", anchor: str = "start") -> str:
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{PALETTE[fill]}" text-anchor="{anchor}">{escape(value)}</text>'


def wrapped_text(x: int, y: int, value: str, limit: int, size: int = 15, fill: str = "muted", line_height: int = 21) -> str:
    parts = [f'<text x="{x}" y="{y}" font-size="{size}" fill="{PALETTE[fill]}">']
    for index, line in enumerate(wrap_text(value, limit)):
        dy = 0 if index == 0 else line_height
        parts.append(f'<tspan x="{x}" dy="{dy}">{escape(line)}</tspan>')
    parts.append("</text>")
    return "".join(parts)


def panel(x: int, y: int, w: int, h: int, number: str, title_value: str, subtitle: str, bullets: list[str], color: str, soft: str) -> str:
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="18" fill="#FFFFFF" stroke="{PALETTE[color]}" stroke-width="2"/>',
        f'<rect x="{x}" y="{y}" width="{w}" height="58" rx="18" fill="{PALETTE[soft]}" stroke="{PALETTE[color]}" stroke-width="2"/>',
        f'<circle cx="{x + 34}" cy="{y + 29}" r="18" fill="{PALETTE[color]}"/>',
        text(x + 34, y + 35, number, 17, "700", "paper", "middle"),
        text(x + 66, y + 36, title_value, 22, "700", "ink"),
        wrapped_text(x + 30, y + 92, subtitle, 34, 16, "ink", 22),
    ]
    bullet_y = y + 138
    for item in bullets:
        parts.append(f'<circle cx="{x + 40}" cy="{bullet_y - 5}" r="5" fill="{PALETTE[color]}"/>')
        parts.append(wrapped_text(x + 56, bullet_y, item, 38, 14, "muted", 19))
        bullet_y += 52
    return "\n".join(parts)


def render(locale: str) -> str:
    copy = COPY[locale]
    width, height = 1240, 650
    panel_w, panel_h = 360, 390
    xs = [44, 440, 836]
    colors = [("blue", "blue_soft"), ("green", "green_soft"), ("violet", "violet_soft")]
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        "<style>text{font-family:Arial,'Microsoft YaHei',sans-serif;letter-spacing:0}</style>",
        f'<rect width="{width}" height="{height}" rx="26" fill="{PALETTE["paper"]}"/>',
        text(44, 60, copy["title"], 34, "800", "ink"),
        wrapped_text(44, 95, copy["subtitle"], 104, 17, "muted", 22),
        f'<line x1="44" y1="122" x2="1196" y2="122" stroke="{PALETTE["line"]}" stroke-width="2"/>',
    ]
    for index, panel_copy in enumerate(copy["panels"]):
        number, title_value, subtitle, bullets = panel_copy
        parts.append(panel(xs[index], 154, panel_w, panel_h, number, title_value, subtitle, bullets, *colors[index]))
        if index < 2:
            start = xs[index] + panel_w + 12
            end = xs[index + 1] - 12
            parts.append(f'<path d="M {start} 348 C {start + 18} 348, {end - 18} 348, {end} 348" fill="none" stroke="{PALETTE["line"]}" stroke-width="3" marker-end="url(#arrow)"/>')
    parts.extend(
        [
            "<defs>",
            f'<marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto" markerUnits="strokeWidth"><path d="M0,0 L0,6 L8,3 z" fill="{PALETTE["line"]}"/></marker>',
            "</defs>",
            f'<rect x="44" y="574" width="1152" height="44" rx="14" fill="{PALETTE["gold_soft"]}" stroke="{PALETTE["gold"]}"/>',
            wrapped_text(68, 601, copy["footer"], 112, 15, "ink", 20),
            "</svg>",
        ]
    )
    return "\n".join(parts)


def main() -> None:
    for locale in COPY:
        (OUT / COPY[locale]["filename"]).write_text(render(locale), encoding="utf-8")


if __name__ == "__main__":
    main()
