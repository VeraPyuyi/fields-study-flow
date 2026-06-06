from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from defusedxml import ElementTree as ET

from fields_study_flow.models import Resource
from fields_study_flow.offline_catalog import offline_resources_for_goal


ARXIV_API_URL = "https://export.arxiv.org/api/query"
SEMANTIC_SCHOLAR_PAPER_URL = "https://api.semanticscholar.org/graph/v1/paper"
OPENALEX_WORKS_URL = "https://api.openalex.org/works"

TEXT_PREVIEW_LIMIT = 80000


def resolve_paper_metadata(
    target: str,
    *,
    live: bool = True,
    client: Any | None = None,
    timeout: float = 6.0,
) -> dict[str, Any]:
    """Resolve public paper metadata or local PDF structure into a safe dict."""

    warnings: list[str] = []
    file_uri_path = _local_pdf_path_from_file_uri(target)
    if file_uri_path is not None and file_uri_path.exists() and file_uri_path.is_file() and file_uri_path.suffix.lower() == ".pdf":
        return _metadata_from_local_pdf(file_uri_path)
    if file_uri_path is not None:
        title = _safe_title_from_target(target)
        return _fallback_metadata(
            title=title,
            url=f"local://paper-{_safe_slug(title)}",
            source="local-library",
            source_ids={},
            warnings=warnings + ["local_file_unavailable"],
        )

    path = Path(target)
    if path.exists() and path.is_file() and path.suffix.lower() == ".pdf":
        return _metadata_from_local_pdf(path)

    arxiv_id = _extract_arxiv_id(target)
    doi = _extract_doi(target)
    close_client = False
    if live and client is None:
        try:
            import httpx

            client = httpx.Client(timeout=timeout, follow_redirects=True)
            close_client = True
        except Exception as exc:
            warnings.append(f"http_client_unavailable: {exc}")
            live = False

    try:
        if live and arxiv_id and client is not None:
            try:
                return _metadata_from_arxiv(arxiv_id, client, timeout)
            except Exception as exc:
                warnings.append(f"arxiv_unavailable: {exc}")
        if live and doi and client is not None:
            return _metadata_from_doi(doi, target, client, timeout)
    finally:
        if close_client and client is not None:
            client.close()

    if arxiv_id:
        offline = _offline_catalog_metadata(arxiv_id=arxiv_id)
        if offline:
            offline["warnings"] = warnings + ["offline_catalog_fallback", *offline.get("warnings", [])]
            return offline
        return _fallback_metadata(
            title=f"arXiv:{arxiv_id}",
            url=_arxiv_abs_url(arxiv_id),
            source="arxiv",
            source_ids={"arxiv": arxiv_id},
            warnings=warnings + ["metadata_unavailable"],
        )
    if doi:
        offline = _offline_catalog_metadata(doi=doi)
        if offline:
            offline["warnings"] = warnings + ["offline_catalog_fallback", *offline.get("warnings", [])]
            return offline
        return _fallback_metadata(
            title=f"DOI:{doi}",
            url=f"https://doi.org/{doi}",
            source="doi",
            source_ids={"doi": doi},
            warnings=warnings + ["metadata_unavailable"],
        )
    return _fallback_metadata(
        title=_safe_title_from_target(target),
        url=target,
        source=_source_from_target(target),
        source_ids={},
        warnings=warnings + ["metadata_unavailable"],
    )


def paper_metadata_to_resource(metadata: dict[str, Any]) -> Resource:
    paper_metadata = _public_metadata(metadata)
    title = paper_metadata.get("title") or "Target paper"
    source = metadata.get("source") or paper_metadata.get("source") or "user-paper"
    url = metadata.get("url") or paper_metadata.get("url") or ""
    concepts = list(dict.fromkeys(["paper reading", *paper_metadata.get("concepts", [])]))
    learning_key_points = [
        "problem, contribution, and assumptions",
        "key method or derivation",
        "minimal reproduction target",
        "limitations and boundary conditions",
    ]
    if paper_metadata.get("method_hints"):
        learning_key_points[1] = str(paper_metadata["method_hints"][0])[:120]
    if paper_metadata.get("formula_candidates"):
        learning_key_points.append(f"derive formula candidate: {str(paper_metadata['formula_candidates'][0])[:100]}")
    focus_areas = [*concepts[:4]]
    if paper_metadata.get("sections"):
        focus_areas.extend(str(section) for section in paper_metadata["sections"][:3])
    if paper_metadata.get("code_links"):
        focus_areas.append("code or repository link available")
    return Resource(
        title=title,
        url=url,
        source=source,
        type="paper",
        language="en",
        difficulty="advanced",
        concepts=concepts,
        estimated_time="4-8h",
        estimated_minutes=360,
        learning_key_points=learning_key_points,
        focus_areas=list(dict.fromkeys(focus_areas))[:6],
        critical_path_role="core-paper",
        trust_score=0.95 if source in {"arxiv", "semantic-scholar", "openalex"} else 0.72,
        why_recommended="Target paper for the deep-reading route, with extracted metadata guiding the shortest mastery path.",
        license_or_access_note="Paper metadata and links only. Link and summarize; do not copy long copyrighted passages.",
        metadata={
            "target_paper": True,
            "paper_metadata": paper_metadata,
            "metadata_status": paper_metadata.get("metadata_status", "partial"),
        },
    )


def _metadata_from_arxiv(arxiv_id: str, client: Any, timeout: float) -> dict[str, Any]:
    response = client.get(ARXIV_API_URL, params={"id_list": arxiv_id, "start": 0, "max_results": 1}, timeout=timeout)
    response.raise_for_status()
    root = ET.fromstring(response.text)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entry = root.find("atom:entry", ns)
    if entry is None:
        return _fallback_metadata(
            title=f"arXiv:{arxiv_id}",
            url=_arxiv_abs_url(arxiv_id),
            source="arxiv",
            source_ids={"arxiv": arxiv_id},
            warnings=["arxiv_entry_not_found"],
        )
    title = _clean_text(entry.findtext("atom:title", default="", namespaces=ns)) or f"arXiv:{arxiv_id}"
    abstract = _clean_text(entry.findtext("atom:summary", default="", namespaces=ns))
    authors = [
        _clean_text(author.findtext("atom:name", default="", namespaces=ns))
        for author in entry.findall("atom:author", ns)
        if _clean_text(author.findtext("atom:name", default="", namespaces=ns))
    ]
    categories = [node.attrib.get("term", "") for node in entry.findall("atom:category", ns) if node.attrib.get("term")]
    versionless_id = re.sub(r"v\d+$", "", arxiv_id)
    return _metadata(
        title=title,
        url=_arxiv_abs_url(versionless_id),
        source="arxiv",
        abstract=abstract,
        authors=authors,
        source_ids={"arxiv": versionless_id},
        categories=categories,
        concepts=_concepts_from_text(f"{title} {abstract} {' '.join(categories)}"),
        sections=[],
        metadata_status="ok",
        warnings=[],
        extra={
            "published": _clean_text(entry.findtext("atom:published", default="", namespaces=ns)),
            "updated": _clean_text(entry.findtext("atom:updated", default="", namespaces=ns)),
            "pdf_url": f"https://arxiv.org/pdf/{versionless_id}",
        },
    )


def _metadata_from_doi(doi: str, original_target: str, client: Any, timeout: float) -> dict[str, Any]:
    warnings: list[str] = []
    semantic_url = f"{SEMANTIC_SCHOLAR_PAPER_URL}/DOI:{doi}"
    try:
        response = client.get(
            semantic_url,
            params={"fields": "title,url,abstract,authors,fieldsOfStudy,citationCount,year,isOpenAccess,openAccessPdf"},
            timeout=timeout,
        )
        response.raise_for_status()
        payload = response.json()
        title = payload.get("title") or f"DOI:{doi}"
        abstract = payload.get("abstract") or ""
        authors = [item.get("name", "") for item in payload.get("authors", []) if item.get("name")]
        fields = [str(item) for item in payload.get("fieldsOfStudy", []) if item]
        return _metadata(
            title=title,
            url=payload.get("url") or f"https://doi.org/{doi}",
            source="semantic-scholar",
            abstract=abstract,
            authors=authors,
            source_ids={"doi": doi},
            categories=fields,
            concepts=_concepts_from_text(f"{title} {abstract} {' '.join(fields)}"),
            sections=[],
            metadata_status="ok",
            warnings=warnings,
            extra={
                "year": payload.get("year"),
                "citations": payload.get("citationCount") or 0,
                "open_access_pdf": payload.get("openAccessPdf") or {},
            },
        )
    except Exception as exc:
        warnings.append(f"semantic_scholar_unavailable: {exc}")

    openalex_url = f"{OPENALEX_WORKS_URL}/doi:{doi}"
    try:
        response = client.get(openalex_url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        title = payload.get("display_name") or f"DOI:{doi}"
        abstract = _abstract_from_inverted_index(payload.get("abstract_inverted_index") or {})
        authors = [
            item.get("author", {}).get("display_name", "")
            for item in payload.get("authorships", [])
            if item.get("author", {}).get("display_name")
        ]
        concepts = [item.get("display_name", "") for item in payload.get("concepts", []) if item.get("display_name")]
        return _metadata(
            title=title,
            url=payload.get("doi") or f"https://doi.org/{doi}",
            source="openalex",
            abstract=abstract,
            authors=authors,
            source_ids={"doi": doi},
            categories=[],
            concepts=_concepts_from_text(f"{title} {abstract} {' '.join(concepts)}"),
            sections=[],
            metadata_status="ok",
            warnings=warnings,
            extra={"openalex_id": payload.get("id")},
        )
    except Exception as exc:
        warnings.append(f"openalex_unavailable: {exc}")

    return _fallback_metadata(
        title=f"DOI:{doi}",
        url=f"https://doi.org/{doi}" if original_target else "",
        source="doi",
        source_ids={"doi": doi},
        warnings=warnings + ["metadata_unavailable"],
    )


def _metadata_from_local_pdf(path: Path) -> dict[str, Any]:
    text = _read_pdf_text(path)
    title = _title_from_pdf_text(path, text)
    abstract = _abstract_from_text(text)
    sections = _sections_from_text(text)
    concepts = _concepts_from_text(f"{title} {abstract} {text[:12000]}")
    return _metadata(
        title=title,
        url=f"local://paper-{_safe_slug(path.stem)}",
        source="local-library",
        abstract=abstract,
        authors=[],
        source_ids={"local_resource": _safe_slug(path.stem)},
        categories=[],
        concepts=concepts,
        sections=sections,
        metadata_status="ok" if text else "partial",
        warnings=[] if text else ["pdf_text_unavailable"],
        extra={
            "method_hints": _hints_for_terms(text, ("method", "approach", "model", "objective", "algorithm", "方法")),
            "experiment_hints": _hints_for_terms(text, ("experiment", "evaluation", "dataset", "result", "实验", "评估")),
            "limitations_hints": _hints_for_terms(text, ("limitation", "failure", "future work", "cost", "局限")),
            "keywords": _keywords_from_text(text),
            "formula_candidates": _formula_candidates_from_text(text),
            "code_links": _code_links_from_text(text),
            "local_path": None,
            "path_name": path.name,
        },
    )


def _metadata(
    *,
    title: str,
    url: str,
    source: str,
    abstract: str,
    authors: list[str],
    source_ids: dict[str, str],
    categories: list[str],
    concepts: list[str],
    sections: list[str],
    metadata_status: str,
    warnings: list[str],
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": title,
        "url": url,
        "source": source,
        "abstract_snippet": _clip(_clean_text(abstract), 700),
        "authors": authors[:12],
        "source_ids": source_ids,
        "categories": categories[:8],
        "concepts": concepts[:10],
        "sections": sections[:16],
        "method_hints": [],
        "experiment_hints": [],
        "limitations_hints": [],
        "keywords": [],
        "formula_candidates": [],
        "code_links": [],
        "metadata_status": metadata_status,
        "warnings": warnings,
        "local_path": None,
    }
    if extra:
        data.update(extra)
    data["method_hints"] = [_clip(_clean_text(item), 220) for item in data.get("method_hints", []) if _clean_text(item)][:4]
    data["experiment_hints"] = [_clip(_clean_text(item), 220) for item in data.get("experiment_hints", []) if _clean_text(item)][:4]
    data["limitations_hints"] = [_clip(_clean_text(item), 220) for item in data.get("limitations_hints", []) if _clean_text(item)][:4]
    data["keywords"] = _clean_unique_list(data.get("keywords", []), 12, 80)
    data["formula_candidates"] = _clean_unique_list(data.get("formula_candidates", []), 8, 180)
    data["code_links"] = _clean_unique_list(data.get("code_links", []), 8, 240)
    return data


def _fallback_metadata(title: str, url: str, source: str, source_ids: dict[str, str], warnings: list[str]) -> dict[str, Any]:
    return _metadata(
        title=title,
        url=url,
        source=source,
        abstract="",
        authors=[],
        source_ids=source_ids,
        categories=[],
        concepts=_concepts_from_text(title),
        sections=[],
        metadata_status="partial",
        warnings=warnings,
        extra=None,
    )


def _offline_catalog_metadata(arxiv_id: str = "", doi: str = "") -> dict[str, Any] | None:
    for resource in _offline_catalog_papers():
        normalized_url = resource.url.lower()
        source_ids: dict[str, str] = {}
        if arxiv_id and arxiv_id.lower() in normalized_url:
            source_ids["arxiv"] = re.sub(r"v\d+$", "", arxiv_id)
        elif doi and doi.lower() in normalized_url:
            source_ids["doi"] = doi
        else:
            continue
        return _metadata(
            title=resource.title,
            url=resource.url,
            source=resource.source,
            abstract="",
            authors=[],
            source_ids=source_ids,
            categories=[],
            concepts=resource.concepts,
            sections=[],
            metadata_status="partial",
            warnings=[],
            extra={"offline_catalog": True},
        )
    return None


def _offline_catalog_papers() -> list[Resource]:
    seeds = "transformer diffusion yolo ppo trpo reinforcement learning"
    resources = offline_resources_for_goal(seeds)
    return [resource for resource in resources if resource.type == "paper"]


def _public_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    data = dict(metadata)
    data["local_path"] = None
    if isinstance(data.get("paper_metadata"), dict):
        data["paper_metadata"] = _public_metadata(data["paper_metadata"])
    return data


def _extract_arxiv_id(target: str) -> str:
    parsed = urlparse(target)
    host = parsed.netloc.lower().removeprefix("www.")
    if host == "arxiv.org":
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) >= 2 and parts[0] in {"abs", "pdf"}:
            return parts[1].removesuffix(".pdf")
    match = re.search(r"(?<!\d)(\d{4}\.\d{4,5})(?:v\d+)?(?!\d)", target)
    return match.group(0) if match else ""


def _extract_doi(target: str) -> str:
    parsed = urlparse(target)
    host = parsed.netloc.lower().removeprefix("www.")
    if host in {"doi.org", "dx.doi.org"}:
        return unquote(parsed.path.lstrip("/")).strip()
    match = re.search(r"\b10\.\d{4,9}/[^\s?#]+", target, flags=re.I)
    return match.group(0).rstrip(".,);") if match else ""


def _read_pdf_text(path: Path) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts: list[str] = []
        for page in reader.pages[:12]:
            parts.append(page.extract_text() or "")
            if sum(len(part) for part in parts) >= TEXT_PREVIEW_LIMIT:
                break
        text = "\n".join(parts).strip()
        if text:
            return text[:TEXT_PREVIEW_LIMIT]
    except Exception:
        return _read_raw_pdf_text(path)
    return _read_raw_pdf_text(path)


def _read_raw_pdf_text(path: Path) -> str:
    try:
        return path.read_bytes()[:TEXT_PREVIEW_LIMIT].decode("utf-8", errors="ignore")
    except OSError:
        return ""


def _title_from_pdf_text(path: Path, text: str) -> str:
    for raw_line in text.splitlines()[:30]:
        line = _clean_text(raw_line).lstrip("\ufeff").strip("% ")
        lowered = line.lower()
        if not line or lowered.startswith("pdf-") or lowered.startswith("%pdf-") or lowered in {"abstract", "introduction"}:
            continue
        if re.match(r"^\d+(\.\d+)?\s+", line):
            continue
        if 6 <= len(line) <= 120:
            return line
    return path.stem.replace("_", " ").replace("-", " ").strip().title()


def _abstract_from_text(text: str) -> str:
    match = re.search(r"\babstract\b\s*(.*?)(?:\n\s*(?:\d+\.?\s+)?(?:introduction|1\s+introduction|keywords)\b)", text, flags=re.I | re.S)
    if match:
        return _clean_text(match.group(1))
    return _clean_text(text[:900])


def _sections_from_text(text: str) -> list[str]:
    sections: list[str] = []
    pattern = re.compile(r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?([A-Z][A-Za-z][A-Za-z \-/]{2,60})\s*$")
    for line in text.splitlines()[:500]:
        cleaned = _clean_text(line).strip("% ")
        if not cleaned or cleaned.lower() in {"abstract", "references"}:
            continue
        match = pattern.match(cleaned)
        if not match:
            continue
        heading = match.group(1).strip()
        if len(heading.split()) > 8:
            continue
        normalized = heading.title()
        if normalized not in sections:
            sections.append(normalized)
        if len(sections) >= 16:
            break
    return sections


def _hints_for_terms(text: str, terms: tuple[str, ...]) -> list[str]:
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?。！？])\s+|\n+", text)
    hints: list[str] = []
    for sentence in sentences:
        cleaned = _clean_text(sentence).strip("% ")
        if len(cleaned) < 24:
            continue
        lowered = cleaned.lower()
        if any(term.lower() in lowered for term in terms):
            hints.append(cleaned)
        if len(hints) >= 4:
            break
    return hints


def _keywords_from_text(text: str) -> list[str]:
    match = re.search(r"^\s*(?:keywords?|key words)\s*[:：]\s*(.+)$", text, flags=re.I | re.M)
    if not match:
        return []
    raw = re.split(r"\n\s*(?:\d+\.?\s+)?[A-Z][A-Za-z ]{2,40}\b", match.group(1), maxsplit=1)[0]
    keywords = re.split(r"[,;；、]", raw)
    return _clean_unique_list(keywords, 12, 80)


def _formula_candidates_from_text(text: str) -> list[str]:
    candidates: list[str] = []
    for raw_line in text.splitlines()[:700]:
        line = _clean_text(raw_line).strip("% ")
        if not _looks_like_formula(line):
            continue
        candidates.append(line)
        if len(candidates) >= 8:
            break
    return _clean_unique_list(candidates, 8, 180)


def _looks_like_formula(line: str) -> bool:
    if not (12 <= len(line) <= 220):
        return False
    lowered = line.lower()
    if "http://" in lowered or "https://" in lowered:
        return False
    has_math_signal = any(signal in line for signal in ("=", "≤", ">=", "<=", "||", "_", "^", "\\sum", "\\frac", "E[", "E_", "argmin"))
    if not has_math_signal:
        return False
    mathy_tokens = sum(1 for token in ("theta", "epsilon", "alpha", "beta", "sigma", "loss", "objective", "log", "q(", "p(", "x_", "L_") if token in line)
    return "=" in line or mathy_tokens >= 2


def _code_links_from_text(text: str) -> list[str]:
    links = re.findall(r"https?://(?:github\.com|huggingface\.co|gitlab\.com|bitbucket\.org|paperswithcode\.com)/[^\s)\]}\"'<]+", text, flags=re.I)
    return _clean_unique_list([link.rstrip(".,;:") for link in links], 8, 240)


def _clean_unique_list(values: Any, limit: int, clip_limit: int) -> list[str]:
    output: list[str] = []
    for value in values or []:
        cleaned = _clip(_clean_text(str(value)).strip(" .,:;"), clip_limit)
        if not cleaned or cleaned.lower() in {item.lower() for item in output}:
            continue
        output.append(cleaned)
        if len(output) >= limit:
            break
    return output


def _concepts_from_text(value: str) -> list[str]:
    normalized = value.lower()
    concepts: list[str] = []
    keyword_map = {
        "transformer": "transformer",
        "attention": "attention",
        "self-attention": "self attention",
        "diffusion": "diffusion models",
        "denoising": "denoising",
        "score": "score matching",
        "sampler": "sampling",
        "sampling": "sampling",
        "language model": "language model",
        "reproduc": "reproducibility",
        "verification": "verification",
        "python": "python",
        "pytorch": "pytorch",
        "reinforcement": "reinforcement learning",
        "ppo": "ppo",
    }
    for keyword, concept in keyword_map.items():
        if keyword in normalized and concept not in concepts:
            concepts.append(concept)
    return concepts


def _abstract_from_inverted_index(index: dict[str, list[int]]) -> str:
    positions: list[tuple[int, str]] = []
    for word, word_positions in index.items():
        for position in word_positions:
            positions.append((int(position), word))
    return " ".join(word for _, word in sorted(positions))


def _safe_title_from_target(target: str) -> str:
    parsed = urlparse(target)
    if parsed.path:
        return unquote(parsed.path.rstrip("/").split("/")[-1]) or target
    return target


def _source_from_target(target: str) -> str:
    lowered = target.lower()
    if "arxiv.org" in lowered:
        return "arxiv"
    if "doi.org" in lowered:
        return "doi"
    return "user-paper"


def _local_pdf_path_from_file_uri(target: str) -> Path | None:
    parsed = urlparse(target)
    if parsed.scheme.lower() != "file":
        return None
    raw_path = unquote(parsed.path)
    if parsed.netloc:
        raw_path = f"//{parsed.netloc}{raw_path}"
    try:
        return Path(url2pathname(raw_path))
    except Exception:
        return None


def _arxiv_abs_url(arxiv_id: str) -> str:
    return f"https://arxiv.org/abs/{arxiv_id}"


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return slug or "paper"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _clip(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "…"
