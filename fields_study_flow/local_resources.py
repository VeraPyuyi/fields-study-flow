from __future__ import annotations

import json
import os
import re
from hashlib import sha256
from pathlib import Path

from fields_study_flow.models import Resource


TEXT_EXTENSIONS = {".md", ".txt", ".rst", ".tex", ".py", ".ipynb", ".json", ".yaml", ".yml", ".csv"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".pptx", ".ppt"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | DOCUMENT_EXTENSIONS
SKIP_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "site-packages",
}

KEYWORD_CONCEPTS = {
    "transformer": "transformer",
    "attention": "attention",
    "self-attention": "self attention",
    "diffusion": "diffusion models",
    "score matching": "score matching",
    "yolo": "yolo",
    "cnn": "cnn",
    "ppo": "ppo",
    "trpo": "trpo",
    "reinforcement": "reinforcement learning",
    "llm": "large language model",
    "large language model": "large language model",
    "symbolic planning": "symbolic planning",
    "automated planning": "automated planning",
    "pddl": "pddl",
    "planning domain definition language": "pddl",
    "chain-of-thought": "chain-of-thought",
    "chain of thought": "chain-of-thought",
    "logical chain": "logical chain-of-thought",
    "planbench": "planbench",
    "val feedback": "val verifier",
    "plan validation": "plan validation",
    "state transition": "state transitions",
    "precondition": "action preconditions",
    "instruction tuning": "instruction tuning",
    "python": "python",
    "pytorch": "pytorch",
    "linear algebra": "linear algebra",
    "probability": "probability",
    "optimization": "optimization",
}


def analyze_local_resources(paths: list[str], goal: str, max_files: int = 30) -> list[Resource]:
    """Turn explicit local files or folders into rankable learning resources.

    The scanner only follows paths supplied by the user. It samples metadata and
    short text previews from supported learning files; it does not crawl the
    whole machine or attempt to bypass document restrictions.
    """

    candidates: list[Path] = []
    for value in paths:
        path = Path(value).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Local resource path does not exist: {value}")
        if path.is_dir():
            candidates.extend(_iter_supported_files(path, max_files=max_files - len(candidates)))
        elif _is_supported(path):
            candidates.append(path)
        if len(candidates) >= max_files:
            break

    resources = [_resource_from_path(path, goal) for path in candidates[:max_files]]
    return resources


def _iter_supported_files(root: Path, max_files: int) -> list[Path]:
    if max_files <= 0:
        return []
    root_resolved = root.resolve()
    files: list[Path] = []
    for current_root, dirs, names in os.walk(root, topdown=True, onerror=lambda _error: None):
        dirs[:] = sorted(
            dirname
            for dirname in dirs
            if not dirname.startswith(".")
            and dirname not in SKIP_DIRS
            and not _is_link_or_junction(Path(current_root) / dirname)
            and _is_within_directory((Path(current_root) / dirname).resolve(), root_resolved)
        )
        for name in sorted(names):
            path = Path(current_root) / name
            if path.is_file() and _is_supported(path) and not _is_link_or_junction(path) and _is_within_directory(path.resolve(), root_resolved):
                files.append(path)
                if len(files) >= max_files:
                    files.sort(key=_candidate_priority)
                    return files
    files.sort(key=_candidate_priority)
    return files


def _candidate_priority(path: Path) -> tuple[int, int, str]:
    name = path.name.lower()
    if name in {"readme.md", "readme.txt"}:
        return (0, len(path.parts), name)
    if path.suffix.lower() in {".pdf", ".ipynb", ".md"}:
        return (1, len(path.parts), name)
    if path.suffix.lower() in {".py", ".tex"}:
        return (2, len(path.parts), name)
    return (3, len(path.parts), name)


def _is_supported(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTENSIONS


def _is_link_or_junction(path: Path) -> bool:
    if path.is_symlink():
        return True
    is_junction = getattr(path, "is_junction", None)
    return bool(is_junction and is_junction())


def _is_within_directory(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _resource_from_path(path: Path, goal: str) -> Resource:
    resolved = path.resolve()
    resource_id = _local_resource_id(path)
    snippet = _read_preview(path)
    title = _title_from_path(path, snippet)
    resource_type = _resource_type(path)
    concepts = _extract_concepts(goal, path, snippet)
    goal_fit = _goal_fit(goal, title, concepts, snippet)
    estimated_minutes = _estimate_minutes(path, snippet, resource_type)
    key_points = _learning_key_points(concepts, resource_type)
    focus_areas = _focus_areas(concepts, resource_type)
    decision = "critical-path-candidate" if goal_fit >= 0.25 else "supplement-only"

    return Resource(
        title=title,
        url=f"local://{resource_id}",
        source="local-library",
        type=resource_type,
        language=_detect_language(title + "\n" + snippet),
        difficulty=_difficulty_from_path(path, snippet),
        prerequisites=_prerequisites_for(concepts),
        concepts=concepts,
        estimated_time=_format_minutes(estimated_minutes),
        estimated_minutes=estimated_minutes,
        learning_key_points=key_points,
        focus_areas=focus_areas,
        critical_path_role=_critical_path_role(resource_type, concepts),
        local_path=str(resolved),
        trust_score=0.62 + min(0.2, goal_fit * 0.2),
        why_recommended=_why_local_resource(decision, resource_type),
        license_or_access_note="Explicit user-provided local path. Use for personal study planning; do not publish private content or copy long excerpts.",
        metadata={
            "local_availability": True,
            "goal_fit": round(goal_fit, 3),
            "candidate_decision": decision,
            "local_resource_id": resource_id,
            "size_bytes": path.stat().st_size,
            "path_name": path.name,
        },
    )


def _local_resource_id(path: Path) -> str:
    stat = path.stat()
    stable = f"{path.name}:{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8", errors="ignore")
    return "local-" + sha256(stable).hexdigest()[:12]


def _read_preview(path: Path, limit: int = 60000) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return _read_pdf_preview(path, limit)
    if suffix not in TEXT_EXTENSIONS:
        return ""
    if suffix == ".ipynb":
        return _read_notebook_preview(path, limit)
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _read_notebook_preview(path: Path, limit: int) -> str:
    try:
        import nbformat

        notebook = nbformat.read(path, as_version=4)
        parts = []
        for cell in notebook.cells:
            parts.append(str(cell.get("source", "")))
            if sum(len(part) for part in parts) >= limit:
                break
        return "\n".join(parts)[:limit]
    except Exception:
        return _read_notebook_json_preview(path, limit)


def _read_notebook_json_preview(path: Path, limit: int) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    except (OSError, json.JSONDecodeError):
        return ""
    parts: list[str] = []
    for cell in data.get("cells", []):
        source = cell.get("source", [])
        if isinstance(source, list):
            parts.append("".join(source))
        elif isinstance(source, str):
            parts.append(source)
        if sum(len(part) for part in parts) >= limit:
            break
    return "\n".join(parts)[:limit]


def _read_pdf_preview(path: Path, limit: int) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages[:8]:
            parts.append(page.extract_text() or "")
            if sum(len(part) for part in parts) >= limit:
                break
        text = "\n".join(parts).strip()
        if text:
            return text[:limit]
    except Exception:
        return _read_raw_text_preview(path, limit)
    return _read_raw_text_preview(path, limit)


def _read_raw_text_preview(path: Path, limit: int) -> str:
    try:
        raw = path.read_bytes()[:limit]
    except OSError:
        return ""
    return raw.decode("utf-8", errors="ignore")


def _title_from_path(path: Path, snippet: str) -> str:
    for line in snippet.splitlines()[:12]:
        cleaned = line.strip().lstrip("#").strip()
        match = re.match(r"\\(?:section|subsection|chapter)\{(.+?)\}", cleaned)
        if match:
            cleaned = match.group(1).strip()
        if 4 <= len(cleaned) <= 90 and not cleaned.startswith("{"):
            return cleaned
    return path.stem.replace("_", " ").replace("-", " ").strip().title()


def _resource_type(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        return "paper"
    if suffix in {".ipynb", ".py"}:
        return "code"
    if suffix in {".ppt", ".pptx"}:
        return "slides"
    if suffix == ".docx":
        return "document"
    return "notes"


def _extract_concepts(goal: str, path: Path, snippet: str) -> list[str]:
    haystack = f"{path.name}\n{snippet[:12000]}".lower()
    concepts: list[str] = []
    for keyword, concept in KEYWORD_CONCEPTS.items():
        if keyword in haystack and concept not in concepts:
            concepts.append(concept)
    if not concepts:
        tokens = [token for token in re.split(r"[\s,_/.-]+", path.stem.lower()) if len(token) >= 4]
        concepts.extend(tokens[:3])
    return concepts[:8]


def _goal_fit(goal: str, title: str, concepts: list[str], snippet: str) -> float:
    goal_terms = _tokens(goal)
    if not goal_terms:
        return 0.3
    resource_terms = _tokens(title) | _tokens(" ".join(concepts)) | _tokens(snippet[:4000])
    overlap = len(goal_terms & resource_terms) / max(1, len(goal_terms))
    return min(1.0, 0.15 + overlap)


def _tokens(value: str) -> set[str]:
    normalized = value.lower().replace("self-attention", "self attention")
    tokens = {token.strip(".,:;()[]{}") for token in re.split(r"\s+|/|-|_", normalized) if token.strip()}
    for keyword in KEYWORD_CONCEPTS:
        if keyword in normalized:
            tokens.add(keyword)
    return tokens


def _estimate_minutes(path: Path, snippet: str, resource_type: str) -> int:
    if resource_type == "paper":
        size_kb = max(1, path.stat().st_size // 1024)
        return max(45, min(300, 45 + size_kb // 18))
    if resource_type == "code":
        line_count = snippet.count("\n") + 1 if snippet else 120
        return max(35, min(240, 30 + line_count // 8))
    if resource_type == "slides":
        return 45
    words = re.findall(r"\w+", snippet)
    if not words:
        return 30
    return max(20, min(180, 15 + len(words) // 160))


def _format_minutes(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes}min"
    hours = minutes / 60
    if minutes % 60 == 0:
        return f"{minutes // 60}h"
    return f"{hours:.1f}h"


def _detect_language(value: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", value):
        return "zh-CN"
    return "en"


def _difficulty_from_path(path: Path, snippet: str) -> str:
    text = f"{path.name}\n{snippet[:5000]}".lower()
    if any(term in text for term in ("proof", "derivation", "theorem", "推导", "证明", "paper", "论文")):
        return "advanced"
    if any(term in text for term in ("intro", "beginner", "primer", "入门", "基础")):
        return "beginner"
    return "intermediate"


def _prerequisites_for(concepts: list[str]) -> list[str]:
    prerequisites: list[str] = []
    if any(concept in concepts for concept in ("transformer", "attention", "diffusion models")):
        prerequisites.extend(["linear algebra", "probability", "python"])
    if any(concept in concepts for concept in ("yolo", "cnn")):
        prerequisites.extend(["python", "cnn basics"])
    if any(concept in concepts for concept in ("ppo", "trpo", "reinforcement learning")):
        prerequisites.extend(["probability", "policy gradient"])
    return list(dict.fromkeys(prerequisites))


def _learning_key_points(concepts: list[str], resource_type: str) -> list[str]:
    if resource_type == "code":
        return ["minimal runnable path", "model and data interfaces", "reproduction checkpoints"]
    if resource_type == "paper":
        return ["problem setting and assumptions", "core method or equations", "evidence, limits, and claims"]
    if "transformer" in concepts or "attention" in concepts:
        return ["self-attention mechanism", "positional information", "training and inference flow"]
    if "diffusion models" in concepts:
        return ["forward noising process", "denoising objective", "sampling procedure"]
    return ["definitions that unblock the goal", "worked examples", "open questions to resolve"]


def _focus_areas(concepts: list[str], resource_type: str) -> list[str]:
    focus = [concept for concept in concepts[:4]]
    if resource_type == "code":
        focus.append("run only the minimal reproduction path")
    elif resource_type == "paper":
        focus.append("read only sections needed for the target claim first")
    else:
        focus.append("skip material not needed for the target paper")
    return list(dict.fromkeys(focus))[:5]


def _critical_path_role(resource_type: str, concepts: list[str]) -> str:
    if resource_type == "paper":
        return "core-paper"
    if resource_type == "code":
        return "practice-validation"
    if any(concept in concepts for concept in ("linear algebra", "probability", "python")):
        return "prerequisite"
    return "focused-support"


def _why_local_resource(decision: str, resource_type: str) -> str:
    if decision == "critical-path-candidate":
        return f"Local {resource_type} appears goal-aligned and may shorten the mastery path."
    return f"Local {resource_type} is available as backup material, but should enter the route only if it removes a blocker."
