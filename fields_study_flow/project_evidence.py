"""Bounded, read-only locators for explicitly supplied research materials.

No imports of project code, notebook execution, network requests, or OCR occur
here. Small local PDFs have bounded text extraction from their first 12 pages.
A valid locator establishes location, not correctness.
"""
from __future__ import annotations

import ast
import csv
import io
import json
import math
import os
import re
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit

import yaml

from fields_study_flow.local_resources import SKIP_DIRS
from fields_study_flow.models import Resource
from fields_study_flow.privacy import PRIVATE_PATH_RE
from fields_study_flow.rag import _resource_id

MAX_FILES = 64
MAX_FILE_BYTES = 1024 * 1024
MAX_TOTAL_BYTES = 8 * MAX_FILE_BYTES
MAX_ENTRIES = 2048
MAX_ANCHORS_PER_SOURCE = 128
MAX_ANCHORS = 2048
MAX_METADATA_BYTES = 256 * 1024
MAX_TOTAL_METADATA_BYTES = 1024 * 1024
MAX_METADATA_STRING_CHARS = 4096
MAX_METADATA_DEPTH = 12
MAX_PDF_PAGES = 12
MAX_PDF_PAGE_CHARS = 16384
SOURCE_KINDS = {"paper", "readme", "code", "config", "result", "notebook"}
LOCATOR_KEYS = {"page", "section", "symbol", "line_start", "line_end", "cell_id", "json_pointer", "row", "column"}
_SECRET_KEY = re.compile(r"(?:api[_-]?key|token|auth(?:orization)?|password|passwd|secret|credential|private[_-]?key)", re.I)
_PATH = re.compile(PRIVATE_PATH_RE.pattern + r"|(?<![\w:/.])/(?:[^\s/\"'<>]+/)+[^\s\"'<>]*")
_SECRET = re.compile(
    r"(?:\\?[\"'])?(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|passwd|secret|authorization|private[_-]?key)"
    r"(?:\\?[\"'])?\s*[=:]\s*(?:\\[\"'][^\r\n]*?\\[\"']|\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'|[^\s,;}\]]+)"
    r"|\bBearer\s+\S+|\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]+", re.I)
_FINGERPRINT_KEYS = ("segments", "paper_segments", "paper_metadata", "rag", "claims")
_EVIDENCE_KEYS = _FINGERPRINT_KEYS + ("source_id", "research_source_id", "resource_id", "local_resource_id", "doi", "kind")


def _digest(value: Any) -> str:
    return sha256(json.dumps(value, ensure_ascii=True, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def _id(prefix: str, value: Any) -> str:
    return f"{prefix}-{_digest(value)[:24]}"


def _public_text(value: Any, limit: int = 300) -> str:
    text = str(value or "")
    text = _SECRET.sub("[redacted]", text)
    # Keep URL paths separate from filesystem roots and greedy Windows paths.
    parts = re.split(r"(https?://[^\s\"'<>]+)", text)
    text = "".join(_safe_url(part) if part.startswith(("https://", "http://"))
                   else _PATH.sub("[private path] ", part) for part in parts)
    return text[:limit]


def _bounded_metadata(metadata: dict, byte_limit: int) -> tuple[dict, int, int]:
    """Drop oversized/cyclic values before any serialization or recursive copy."""
    omitted = 0
    visited = 0
    reserved = 0
    missing = object()

    def reserve(size: int) -> bool:
        nonlocal reserved
        if reserved + size > byte_limit:
            return False
        reserved += size
        return True

    def visit(value: Any, depth: int, ancestry: frozenset[int]):
        nonlocal visited, omitted
        visited += 1
        if visited > MAX_ENTRIES or depth > MAX_METADATA_DEPTH:
            omitted += 1
            return missing
        if isinstance(value, str):
            if len(value) > MAX_METADATA_STRING_CHARS or not reserve(len(value) * 6 + 2):
                omitted += 1
                return missing
            try:
                value.encode("utf-8")
            except UnicodeError:
                omitted += 1
                return missing
            return value
        if value is None or isinstance(value, bool):
            cost = 5
        elif isinstance(value, int) and value.bit_length() <= 1024:
            cost = len(str(value))
        elif isinstance(value, float) and math.isfinite(value):
            cost = len(repr(value))
        elif isinstance(value, (dict, list)):
            if id(value) in ancestry or not reserve(2):
                omitted += 1
                return missing
            ancestry = ancestry | {id(value)}
            output = {} if isinstance(value, dict) else []
            children = value.items() if isinstance(value, dict) else enumerate(value)
            for index, (key, child) in enumerate(children):
                if visited >= MAX_ENTRIES or reserved >= byte_limit:
                    omitted += len(value) - index
                    break
                if isinstance(value, dict):
                    if not isinstance(key, str) or len(key) > MAX_METADATA_STRING_CHARS or not reserve(len(key) * 6 + 4):
                        omitted += 1
                        continue
                elif not reserve(1):
                    omitted += len(value) - index
                    break
                kept = visit(child, depth + 1, ancestry)
                if kept is not missing:
                    if isinstance(output, dict):
                        output[key] = kept
                    else:
                        output.append(kept)
            return output
        else:
            omitted += 1
            return missing
        if not reserve(cost):
            omitted += 1
            return missing
        return value

    payload = {key: metadata[key] for key in _EVIDENCE_KEYS if key in metadata}
    bounded = visit(payload, 0, frozenset())
    bounded = bounded if isinstance(bounded, dict) else {}
    size = len(json.dumps(bounded, ensure_ascii=True, separators=(",", ":")).encode()) if bounded else 0
    return bounded, size, omitted


def _identity_text(value: Any) -> str:
    return value if isinstance(value, str) and len(value) <= MAX_METADATA_STRING_CHARS else ""


def _compact_resource_id(resource: Resource) -> str:
    metadata = _mapping(resource.metadata)
    compact = Resource(title=_identity_text(resource.title), url=_identity_text(resource.url),
                       source=_identity_text(resource.source), type=_identity_text(resource.type), local_path=resource.local_path,
                       metadata={"local_resource_id": _identity_text(metadata.get("local_resource_id"))})
    return _resource_id(compact)


def _safe_url(value: Any) -> str:
    if not isinstance(value, str) or len(value) > 4096:
        return ""
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http", "local"}:
            return ""
        if parsed.scheme == "local" and (parsed.path or PRIVATE_PATH_RE.search(value)):
            return ""
        host = parsed.netloc.rsplit("@", 1)[-1]
        if not host or "\\" in value or any(ord(c) < 32 for c in value):
            return ""
        path = _SECRET.sub("[redacted]", parsed.path)
        return urlunsplit((parsed.scheme, host, path, "", ""))
    except ValueError:
        return ""


def _safe_relative(value: Any) -> str:
    if not isinstance(value, str) or not value or len(value) > 1024:
        return ""
    decoded = unquote(unquote(value)).replace("\\", "/")
    path = PurePosixPath(decoded)
    if path.is_absolute() or any(p in {"..", ""} for p in decoded.split("/")):
        return ""
    if any(c in decoded for c in ":?#\x00") or any(ord(c) < 32 for c in decoded):
        return ""
    if _SECRET_KEY.search(decoded) or _SECRET.search(decoded):
        return ""
    return path.as_posix()


def _portable_href(value: Any) -> str:
    """Allow leading parent segments for a portable cross-directory bundle."""
    if not isinstance(value, str):
        return ""
    decoded = unquote(unquote(value)).replace("\\", "/")
    parts = decoded.split("/")
    parents = 0
    while parts and parts[0] == "..":
        parents += 1
        parts.pop(0)
    tail = _safe_relative("/".join(parts))
    return "../" * parents + tail if tail and parents <= 8 else ""


def _mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list:
    return value if isinstance(value, list) else []


def _locator(value: Any) -> dict:
    output = {}
    for key, item in _mapping(value).items():
        if key not in LOCATOR_KEYS:
            continue
        if key in {"page", "line_start", "line_end", "row"}:
            if isinstance(item, int) and not isinstance(item, bool) and item > 0:
                output[key] = item
        elif isinstance(item, str) and (item or key == "json_pointer"):
            # JSON pointers are locators, not filesystem paths.
            cleaned = _SECRET.sub("[redacted]", item)[:300] if key == "json_pointer" else _public_text(item)
            if cleaned == item:
                output[key] = cleaned
    if output.get("line_end", 0) < output.get("line_start", 0):
        output.pop("line_end", None)
    return output


def _private_locator(location: dict) -> bool:
    column = location.get("column")
    if isinstance(column, str) and (_SECRET_KEY.search(column) or PRIVATE_PATH_RE.search(column)):
        return True
    pointer = location.get("json_pointer")
    if isinstance(pointer, str):
        keys = [part.replace("~1", "/").replace("~0", "~") for part in pointer.split("/")]
        return any(_SECRET_KEY.search(key) or PRIVATE_PATH_RE.search(key) for key in keys)
    return False


def _anchor(source_id: str, locator: dict, snippet: Any, *, status: str | None = None, identity: Any = None) -> dict:
    locator = _locator(locator)
    return {"id": _id("anchor", [source_id, locator, identity]), "source_id": source_id,
            "locator": locator, "snippet": _public_text(snippet),
            "locator_status": status or ("valid" if locator else "missing")}


def _has_link(path: Path) -> bool:
    for part in (path, *path.parents):
        try:
            if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
                return True
            if getattr(part.lstat(), "st_file_attributes", 0) & 0x400:
                return True
        except OSError:
            continue
    return False


def _source_identity(resource: Resource, path: Path | None = None, root: Path | None = None, ordinal: int = 0) -> str:
    metadata = _mapping(resource.metadata)
    explicit_id = _identity_text(metadata.get("research_source_id")) or _identity_text(metadata.get("source_id"))
    if explicit_id:
        return _id("source", ["supplied", explicit_id, str(path.relative_to(root)) if path and root else ""])
    if path is not None:
        identity = str(path.relative_to(root)) if root else str(path.absolute())
        return _id("source", ["file", identity])
    identifier = (_identity_text(resource.url) or _identity_text(metadata.get("doi"))
                  or _identity_text(_mapping(metadata.get("paper_metadata")).get("doi")) or _identity_text(metadata.get("local_resource_id")))
    return _id("source", ["resource", _identity_text(resource.source), _identity_text(resource.type), identifier]) if identifier else _id("source", ["unidentified", _identity_text(resource.source), _identity_text(resource.type), ordinal])


def _kind(resource: Resource, path: Path | None) -> str:
    suffix = path.suffix.lower() if path else ""
    declared = _mapping(resource.metadata).get("kind") or resource.type
    declared = declared if isinstance(declared, str) else "code"
    if suffix == ".pdf" or (declared == "paper" and suffix in {"", ".md"}):
        return "paper"
    if suffix == ".ipynb":
        return "notebook"
    if suffix == ".py":
        return "code"
    if suffix in {".md", ".txt", ".rst"}:
        return "readme"
    if suffix == ".csv" or declared == "result" or (path and re.search(r"result|metrics|evaluation", path.stem, re.I)):
        return "result"
    if suffix in {".json", ".yaml", ".yml"}:
        return "config"
    return declared if declared in SOURCE_KINDS else "code"


def _metadata_anchors(source_id: str, metadata: dict, verify=None) -> list[dict]:
    paper = _mapping(metadata.get("paper_metadata"))
    segments = (_items(metadata.get("segments")) + _items(metadata.get("paper_segments")) + _items(paper.get("segments")))
    segments += _items(_mapping(metadata.get("rag")).get("top_chunks"))
    anchors = []
    for index, segment in enumerate(segments[:MAX_ANCHORS_PER_SOURCE]):
        if not isinstance(segment, dict):
            continue
        location = {k: segment[k] for k in LOCATOR_KEYS if k in segment}
        location.update(_mapping(segment.get("locator")))
        if "page" not in location and segment.get("page_number"):
            location["page"] = segment["page_number"]
        # section_kind is an inferred reading category, not an original locator.
        snippet = segment.get("original_text") or segment.get("text") or segment.get("snippet")
        if snippet:
            private = _private_locator(location)
            status = ("valid" if verify(location, snippet) else "missing") if verify is not None else None
            anchor = _anchor(source_id, {} if private else location, "[redacted]" if private else snippet,
                             status="missing" if private else status,
                             identity=segment.get("id") or segment.get("chunk_id") or index)
            if segment.get("section_kind"):
                anchor["hint_kind"] = _public_text(segment["section_kind"])
            anchors.append(anchor)
    for key in ("abstract_snippet", "method_hints", "experiment_hints", "limitations_hints", "formula_candidates"):
        values = paper.get(key)
        for index, text in enumerate(values if isinstance(values, list) else [values] if values else []):
            if len(anchors) >= MAX_ANCHORS_PER_SOURCE:
                break
            if text:
                anchor = _anchor(source_id, {}, text, identity=[key, index])
                anchor["hint_kind"] = {"method_hints": "methodology", "experiment_hints": "experiment", "limitations_hints": "limitation", "formula_candidates": "methodology"}.get(key, "background")
                anchors.append(anchor)
    return anchors


def _local_verifier(path: Path, text: str, parsed: list[dict], pdf_pages: dict[int, str] | None = None):
    """Verify every supplied locator component and the full retained excerpt."""
    lines = text.splitlines()
    suffix = path.suffix.lower()
    data = None
    if suffix in {".json", ".ipynb"}:
        data = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    table = {}
    if suffix == ".csv":
        for row, fields in enumerate(csv.DictReader(io.StringIO(text)), start=2):
            if row > MAX_ENTRIES:
                break
            table[row] = fields

    def pointer_value(pointer: str):
        value = data
        if pointer and (not pointer.startswith("/") or re.search(r"~(?![01])", pointer)):
            raise ValueError()
        for part in pointer.split("/")[1:] if pointer else []:
            key = part.replace("~1", "/").replace("~0", "~")
            if isinstance(value, dict):
                value = value[key]
            elif isinstance(value, list) and re.fullmatch(r"0|[1-9][0-9]*", key):
                value = value[int(key)]
            else:
                raise ValueError()
        return value

    def verify(location: dict, snippet: Any) -> bool:
        if (not isinstance(snippet, str) or not snippet.strip() or not location
                or _private_locator(location) or _locator(location) != location):
            return False
        try:
            candidates = []
            if suffix == ".pdf":
                if "page" not in location or set(location) - {"page", "section"}:
                    return False
                page = (pdf_pages or {}).get(location["page"], "")
                if "section" in location and not any(line.strip() == location["section"] for line in page.splitlines()):
                    return False
                candidates = [" ".join(page.split())]
                snippet = " ".join(snippet.split())
            elif suffix in {".json", ".yaml", ".yml"}:
                if set(location) != {"json_pointer"}:
                    return False
                value = pointer_value(location["json_pointer"])
                if isinstance(value, (dict, list)):
                    return False
                candidates = [json.dumps(value, ensure_ascii=True)]
            elif suffix == ".csv":
                if set(location) != {"row", "column"}:
                    return False
                candidates = [table[location["row"]][location["column"]]]
            elif suffix == ".ipynb":
                if set(location) - {"cell_id", "json_pointer"}:
                    return False
                cells = _items(_mapping(data).get("cells"))
                for index, cell in enumerate(cells[:MAX_ENTRIES]):
                    if not isinstance(cell, dict):
                        continue
                    actual = {"cell_id": str(cell.get("id") or f"cell-{index}"), "json_pointer": f"/cells/{index}"}
                    if all(actual.get(k) == v for k, v in location.items()):
                        source = cell.get("source", "")
                        candidates.append("".join(source) if isinstance(source, list) else source)
            elif suffix in {".py", ".md", ".txt", ".rst"}:
                allowed = {"line_start", "line_end", "symbol"} if suffix == ".py" else {"line_start", "line_end", "section"}
                if set(location) - allowed or "line_end" in location and "line_start" not in location:
                    return False
                ranges = [(1, len(lines))]
                name = "symbol" if suffix == ".py" else "section"
                if name in location:
                    ranges = [(a["locator"]["line_start"], a["locator"]["line_end"])
                              for a in parsed if a["locator"].get(name) == location[name]]
                for begin, end in ranges:
                    start = location.get("line_start", begin)
                    stop = location.get("line_end", start if "line_start" in location else end)
                    if begin <= start <= stop <= end:
                        candidates.append("\n".join(lines[start - 1:stop]))
            if suffix in {".json", ".yaml", ".yml", ".csv"}:
                return any(isinstance(candidate, str) and snippet.strip() == candidate.strip() for candidate in candidates)
            excerpt = snippet.strip()
            pattern = (r"(?<!\w)" if excerpt[0].isalnum() else "") + re.escape(excerpt) + (r"(?!\w)" if excerpt[-1].isalnum() else "")
            return any(isinstance(candidate, str) and re.search(pattern, candidate) for candidate in candidates)
        except (ValueError, KeyError, IndexError, TypeError, OverflowError):
            return False
    return verify


_PAPER_CUES = (
    (r"\b(?:our contributions?|we contribute|contributions? (?:are|include|of)|this work (?:introduces|presents|provides))\b", "contribution"),
    (r"\b(?:limitations?|limited to|cannot generalize|future work|remains? an? (?:open )?challenge)\b", "limitation"),
    (r"\b(?:however|critical gap|existing (?:methods|approaches)|struggle|fail to|motivated by)\b", "motivation"),
    (r"\b(?:problem formulation|our (?:goal|objective)|we (?:aim|seek)|task is to|research question)\b", "problem"),
    (r"\b(?:results? (?:show|indicate|demonstrate)|outperform|accuracy of|improvement over)\b", "result"),
    (r"\b(?:we evaluate|experimental|experiments?|benchmark|evaluation protocol|empirical evaluation)\b", "experiment"),
    (r"\b(?:we (?:propose|present|introduce)|our (?:approach|method|framework)|training methodology|instruction tuning)\b", "methodology"),
)


def _paper_hint(text: str, fallback: str = "background") -> str:
    return next((kind for pattern, kind in _PAPER_CUES if re.search(pattern, text, re.I)), fallback)


def _pdf_paragraphs(text: str, previous_kind: str) -> tuple[list[tuple[str, str]], str]:
    """Merge wrapped physical lines; inferred categories are not section locators."""
    output: list[tuple[str, str]] = []
    pending: list[str] = []
    kind = previous_kind

    def flush() -> None:
        if pending:
            value = " ".join(pending)
            pending.clear()
            if len(value) >= 35:
                output.append((value, kind))

    for raw in text.splitlines():
        line = raw.strip()
        heading = re.fullmatch(r"(?:\d+(?:\.\d+)*\s+)?(Abstract|Introduction|Related Work|Background|Preliminaries|Problem Formulation|.*Methodology.*|.*Experiments?.*|.*Evaluation.*|Results(?: and Discussion)?|Discussion|Contributions?|Limitations?|Conclusion|References|Broader Impacts)", line, re.I) if len(line) <= 100 else None
        if heading:
            flush()
            name = heading[1].lower()
            if name == "references":
                kind = "references"
            elif "method" in name:
                kind = "methodology"
            elif "evaluation" in name or "experiment" in name:
                kind = "experiment"
            elif "result" in name:
                kind = "result"
            elif "problem" in name:
                kind = "problem"
            elif "limitation" in name:
                kind = "limitation"
            elif "contribution" in name:
                kind = "contribution"
            else:
                kind = "background"
            continue
        if not line:
            flush()
            continue
        if kind == "references" or re.fullmatch(r"\d+", line):
            continue
        pending.append(line)
        # A sentence boundary is a safe fallback when PDF blank lines are lost.
        if len(" ".join(pending)) >= 240 and re.search(r"[.!?。]\s*$", line):
            flush()
        elif len(" ".join(pending)) >= 1400:
            flush()
    flush()
    return output, kind


def _parse_pdf(source_id: str, data: bytes) -> tuple[list[dict], dict[int, str], set[str]]:
    """Extract only bounded pages; retain no OCR or inferred section locators."""
    from pypdf import PdfReader

    pages: dict[int, str] = {}
    reasons: set[str] = set()
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        if len(reader.pages) > MAX_PDF_PAGES:
            reasons.add("pdf_page_limit")
        for index in range(min(len(reader.pages), MAX_PDF_PAGES)):
            try:
                text = reader.pages[index].extract_text() or ""
                if len(text) > MAX_PDF_PAGE_CHARS:
                    reasons.add("pdf_text_limit")
                pages[index + 1] = text[:MAX_PDF_PAGE_CHARS]
            except Exception:
                # Parser errors are coverage data, never exception text or paths.
                reasons.add("parse_error")
    except Exception:
        reasons.add("parse_error")
    anchors = []
    candidates: dict[int, list[dict]] = {}
    section_kind = "background"
    for number, text in pages.items():
        if not text.strip():
            continue
        preview = _anchor(source_id, {"page": number}, text, identity=["pdf-page", number])
        preview["scope"] = "page_preview"
        anchors.append(preview)
        paragraphs, section_kind = _pdf_paragraphs(text, section_kind)
        candidates[number] = []
        for paragraph_index, (paragraph, fallback) in enumerate(paragraphs):
            # Separate long paragraphs at sentence boundaries to retain later claims.
            sentences = re.split(r"(?<=[.!?。])\s+(?=[A-Z\u4e00-\u9fff])", paragraph)
            blocks: list[str] = []
            for sentence in sentences:
                if blocks and len(blocks[-1]) + len(sentence) < 650:
                    blocks[-1] += " " + sentence
                else:
                    blocks.append(sentence)
            for offset, block in enumerate(blocks):
                snippet = block[:300]
                item = _anchor(source_id, {"page": number}, snippet,
                               identity=["pdf-paragraph", number, paragraph_index, offset])
                item["hint_kind"] = _paper_hint(block, fallback)
                item["classification_origin"] = "rule"
                candidates[number].append(item)
    # Round-robin keeps methods/results on later pages when the source cap is hit.
    while any(candidates.values()) and len(anchors) < MAX_ANCHORS_PER_SOURCE:
        for items in candidates.values():
            if items and len(anchors) < MAX_ANCHORS_PER_SOURCE:
                anchors.append(items.pop(0))
    if any(candidates.values()):
        reasons.add("anchor_limit")
    return anchors, pages, reasons


def _parse_text(source_id: str, path: Path, text: str) -> list[dict]:
    suffix = path.suffix.lower()
    lines = text.splitlines()
    if suffix in {".md", ".txt", ".rst"}:
        headings = [(i, re.sub(r"^#+\s*", "", line).strip()) for i, line in enumerate(lines) if re.match(r"^#{1,6}\s+", line)]
        if not headings:
            return [_anchor(source_id, {"line_start": 1, "line_end": max(1, len(lines))}, text)] if text.strip() else []
        output = []
        for index, (start, heading) in enumerate(headings[:MAX_ANCHORS_PER_SOURCE]):
            end = headings[index + 1][0] if index + 1 < len(headings) else len(lines)
            snippet = "\n".join(lines[start + 1:end]).strip() or heading
            output.append(_anchor(source_id, {"section": heading, "line_start": start + 1, "line_end": max(start + 1, end)}, snippet))
        return output
    if suffix == ".py":
        tree = ast.parse(text)
        output = []

        def visit(node: ast.AST, parents: tuple[str, ...] = ()) -> None:
            for child in ast.iter_child_nodes(node):
                prefix = parents
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    prefix = (*parents, child.name)
                    if len(output) >= MAX_ANCHORS_PER_SOURCE:
                        return
                    output.append(_anchor(source_id, {"symbol": ".".join(prefix), "line_start": child.lineno, "line_end": child.end_lineno or child.lineno}, "\n".join(lines[child.lineno - 1:child.end_lineno])))
                visit(child, prefix)

        visit(tree)
        return output
    if suffix == ".ipynb":
        notebook = json.loads(text)
        output = []
        for index, cell in enumerate(_items(_mapping(notebook).get("cells"))[:MAX_ANCHORS_PER_SOURCE]):
            if not isinstance(cell, dict):
                continue
            value = cell.get("source", "")
            snippet = "".join(str(part) for part in value) if isinstance(value, list) else str(value)
            output.append(_anchor(source_id, {"cell_id": str(cell.get("id") or f"cell-{index}"), "json_pointer": f"/cells/{index}"}, snippet))
        return output
    if suffix in {".json", ".yaml", ".yml"}:
        data = json.loads(text) if suffix == ".json" else yaml.safe_load(text)
        output = []
        visited = 0

        def visit(value: Any, pointer: str, depth: int, ancestry: frozenset[int]) -> None:
            nonlocal visited
            visited += 1
            if visited > MAX_ENTRIES or depth > 24 or len(output) >= MAX_ANCHORS_PER_SOURCE:
                return
            if isinstance(value, (dict, list)):
                if id(value) in ancestry:
                    return
                ancestry = ancestry | {id(value)}
                children = value.items() if isinstance(value, dict) else enumerate(value)
                for key, child in children:
                    if len(output) >= MAX_ANCHORS_PER_SOURCE or visited > MAX_ENTRIES:
                        break
                    if _SECRET_KEY.search(str(key)) or PRIVATE_PATH_RE.search(str(key)):
                        continue
                    escaped = str(key).replace("~", "~0").replace("/", "~1")
                    visit(child, f"{pointer}/{escaped}", depth + 1, ancestry)
            else:
                output.append(_anchor(source_id, {"json_pointer": pointer}, json.dumps(value, ensure_ascii=True, default=str)))

        visit(data, "", 0, frozenset())
        return output
    if suffix == ".csv":
        output = []
        reader = csv.DictReader(io.StringIO(text))
        for row_index, row in enumerate(reader, start=2):
            for column, value in row.items():
                if column is not None and not _SECRET_KEY.search(column) and not PRIVATE_PATH_RE.search(column):
                    output.append(_anchor(source_id, {"row": row_index, "column": column}, value))
                    if len(output) >= MAX_ANCHORS_PER_SOURCE:
                        return output
        return output
    return []


def extract_project_evidence(resources: list[Resource]) -> dict:
    """Return sources, anchors, and explicit bounded coverage for input resources.

    A directory Resource authorizes only that directory; a file Resource never
    authorizes siblings. Optional metadata.project_root/explicit_root further
    constrains reads and supplies relocation-stable relative source identities.
    PDFs within the file/total-byte limits yield page and paragraph-span anchors
    from at most 12 pages, retaining at most 16384 text characters per page.
    Supplied PDF snippets are checked against those actual pages. Larger PDFs
    retain bounded metadata/stat fingerprints only, with unverified locators.
    """
    sources, anchors = [], []
    coverage = {"processed_files": 0, "processed_resources": 0, "skipped": [], "truncated": False,
                "metadata_bytes_retained": 0, "metadata_omitted_values": 0,
                "limits": {"files": MAX_FILES, "file_bytes": MAX_FILE_BYTES, "total_bytes": MAX_TOTAL_BYTES,
                           "metadata_bytes": MAX_METADATA_BYTES, "total_metadata_bytes": MAX_TOTAL_METADATA_BYTES,
                           "metadata_string_chars": MAX_METADATA_STRING_CHARS, "metadata_depth": MAX_METADATA_DEPTH,
                           "pdf_pages": MAX_PDF_PAGES, "pdf_page_chars": MAX_PDF_PAGE_CHARS,
                           "anchors_per_source": MAX_ANCHORS_PER_SOURCE, "anchors": MAX_ANCHORS, "entries": MAX_ENTRIES}}
    seen = set()
    total_bytes = 0
    entries = 0

    def skip(reason: str, sid: str = "", path: Path | None = None) -> None:
        if sid and reason in {"missing", "symlink", "outside_root", "unsupported", "parse_error", "size_limit", "total_size_limit", "no_extracted_text"}:
            for source in sources:
                if source["id"] == sid:
                    source["availability"] = "missing" if reason == "missing" else "unavailable"
        if len(coverage["skipped"]) < MAX_ENTRIES:
            item = {"reason": reason}
            if sid:
                item["source_id"] = sid
            if path and (name := _safe_relative(path.name)):
                item["relative_path"] = name
            coverage["skipped"].append(item)
        if reason.endswith("limit"):
            coverage["truncated"] = True

    def process(resource: Resource, path: Path | None, root: Path | None, ordinal: int = 0) -> None:
        nonlocal total_bytes
        metadata = _mapping(resource.metadata)
        sid = _source_identity(resource, path, root, ordinal)
        if sid in seen:
            return
        if len(sources) >= MAX_FILES:
            skip("file_limit", sid, path)
            return
        seen.add(sid)
        title = _public_text(path.name if root and path else resource.title) or (path.name if path else "Untitled material")
        source = {"id": sid, "kind": _kind(resource, path), "title": title, "fingerprint": "", "availability": "unavailable"}
        rid = _identity_text(metadata.get("resource_id")) or _identity_text(metadata.get("local_resource_id")) or _compact_resource_id(resource)
        source["resource_id"] = str(rid) if re.fullmatch(r"[A-Za-z0-9_-]{1,128}", str(rid)) else _id("resource", rid)
        if path:
            relative = _safe_relative(path.relative_to(root).as_posix() if root else path.name)
            if relative:
                source["relative_path"] = relative
        if url := _safe_url(resource.url):
            source["url"] = url
        sources.append(source)
        if path is None and not any(_identity_text(value) for value in (resource.url, metadata.get("doi"),
            _mapping(metadata.get("paper_metadata")).get("doi"), metadata.get("local_resource_id"), metadata.get("source_id"), metadata.get("research_source_id"))):
            source["identity_status"] = "input_order_fallback"
            skip("identity_unavailable", sid)
        extracted = []
        payload, retained_bytes, omitted = _bounded_metadata(metadata, min(MAX_METADATA_BYTES,
            max(0, MAX_TOTAL_METADATA_BYTES - coverage["metadata_bytes_retained"])))
        coverage["metadata_bytes_retained"] += retained_bytes
        coverage["metadata_omitted_values"] += omitted
        if omitted:
            source["metadata_truncated"] = True
            source["fingerprint_scope"] = "bounded_metadata"
            skip("metadata_limit", sid, path)
        # Path-derived resource IDs must not change relocated content fingerprints.
        content_metadata = {key: payload[key] for key in _FINGERPRINT_KEYS if key in payload}
        fingerprint_payload = [content_metadata, {"omitted_values": omitted}] if omitted else content_metadata
        source["fingerprint"] = _digest([_identity_text(resource.title), fingerprint_payload])

        def supplied(verify=None) -> list[dict]:
            values = _metadata_anchors(sid, payload, verify)
            if verify is not None and any(a["locator_status"] != "valid" for a in values):
                skip("metadata_locator_unverified", sid, path)
            return values

        if path is None:
            extracted = supplied()
            if extracted:
                source["availability"] = "available"
        else:
            try:
                if _has_link(path):
                    skip("symlink", sid, path)
                    return
                if root and not path.resolve().is_relative_to(root.resolve()):
                    skip("outside_root", sid, path)
                    return
                if not path.is_file():
                    skip("missing", sid, path)
                    return
                if path.suffix.lower() not in {".md", ".txt", ".rst", ".py", ".ipynb", ".json", ".yaml", ".yml", ".csv", ".pdf"}:
                    skip("unsupported", sid, path)
                    return
                size = path.stat().st_size
                limited = size > MAX_FILE_BYTES or total_bytes + size > MAX_TOTAL_BYTES
                if limited and path.suffix.lower() == ".pdf":
                    skip("size_limit" if size > MAX_FILE_BYTES else "total_size_limit", sid, path)
                    extracted = supplied(lambda _location, _snippet: False)
                    source["fingerprint"] = _digest([size, path.stat().st_mtime_ns, fingerprint_payload])
                    source["fingerprint_scope"] = "metadata_and_stat"
                    if extracted:
                        source["availability"] = "available"
                else:
                    if limited:
                        skip("size_limit" if size > MAX_FILE_BYTES else "total_size_limit", sid, path)
                        return
                    with path.open("rb") as stream:
                        data = stream.read(MAX_FILE_BYTES + 1)
                    if len(data) > MAX_FILE_BYTES:
                        skip("size_limit", sid, path)
                        return
                    total_bytes += len(data)
                    source["fingerprint"] = _digest([sha256(data).hexdigest(), fingerprint_payload])
                    source["fingerprint_scope"] = "content_and_metadata"
                    if path.suffix.lower() != ".pdf":
                        text = data.decode("utf-8-sig")
                        extracted = _parse_text(sid, path, text)
                        verify = _local_verifier(path, text, extracted)
                    else:
                        extracted, pdf_pages, pdf_reasons = _parse_pdf(sid, data)
                        for reason in sorted(pdf_reasons):
                            skip(reason, sid, path)
                        verify = _local_verifier(path, "", extracted, pdf_pages)
                    extracted += supplied(verify)
                    coverage["processed_files"] += 1
                    source["availability"] = "available"
            except (OSError, ValueError, SyntaxError, UnicodeError, yaml.YAMLError, RecursionError, csv.Error):
                skip("parse_error", sid, path)
        if omitted:
            source["fingerprint_scope"] = {"content_and_metadata": "content_and_bounded_metadata",
                "metadata_and_stat": "bounded_metadata_and_stat"}.get(source.get("fingerprint_scope"), "bounded_metadata")
        unique = {a["id"]: a for a in extracted}
        if len(unique) >= MAX_ANCHORS_PER_SOURCE:
            skip("anchor_limit", sid, path)
        room = min(MAX_ANCHORS_PER_SOURCE, MAX_ANCHORS - len(anchors))
        if len(unique) > room:
            skip("anchor_limit", sid, path)
        anchors.extend(list(unique.values())[:room])
        coverage["processed_resources"] += 1
        if not extracted and source["kind"] == "paper":
            skip("no_extracted_text", sid, path)

    def walk(root: Path):
        nonlocal entries
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            retained = []
            for name in dirs:
                entries += 1
                child = Path(directory) / name
                if _has_link(child):
                    skip("symlink", path=child)
                else:
                    retained.append(name)
            dirs[:] = retained
            for name in sorted(names):
                entries += 1
                if entries > MAX_ENTRIES or len(sources) >= MAX_FILES:
                    skip("entry_limit" if entries > MAX_ENTRIES else "file_limit")
                    return
                yield Path(directory) / name
            if entries > MAX_ENTRIES:
                skip("entry_limit")
                return

    for ordinal, resource in enumerate(resources[:MAX_ENTRIES]):
        if not isinstance(resource, Resource):
            skip("invalid_resource")
            continue
        metadata = _mapping(resource.metadata)
        path = Path(resource.local_path).expanduser().absolute() if resource.local_path else None
        root_value = metadata.get("project_root") or metadata.get("explicit_root")
        root = Path(root_value).expanduser().absolute() if isinstance(root_value, (str, os.PathLike)) else None
        if path and root and not path.is_relative_to(root):
            skip("outside_root", path=path)
            continue
        if path and _has_link(path):
            skip("symlink", path=path)
            continue
        if path and path.is_dir():
            for file in walk(path):
                process(resource, file, root or path, ordinal)
        else:
            process(resource, path, root, ordinal)
        if len(sources) >= MAX_FILES:
            skip("file_limit")
            break
    if len(resources) > MAX_ENTRIES:
        skip("entry_limit")
    coverage["bytes_read"] = total_bytes
    return {"schema_version": 1, "sources": sources, "anchors": anchors, "coverage": coverage}
