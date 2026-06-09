from __future__ import annotations

import json
import math
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from fields_study_flow.models import LearnerProfile, Resource


RAG_INDEX_DIR = ".rag_index"
RAG_INDEX_FILE = "manifest.json"
SUPPORTED_RAG_EXTENSIONS = {".md", ".txt", ".rst", ".tex", ".py", ".json", ".yaml", ".yml", ".csv", ".html", ".htm", ".ipynb", ".pdf"}
STOPWORDS = {
    "about",
    "after",
    "and",
    "are",
    "can",
    "does",
    "for",
    "from",
    "how",
    "into",
    "learn",
    "master",
    "paper",
    "study",
    "that",
    "the",
    "this",
    "what",
    "when",
    "with",
}


def normalize_rag_mode(mode: str | None) -> str:
    normalized = (mode or "auto").strip().lower()
    if normalized in {"off", "none", "false", "0"}:
        return "off"
    if normalized in {"light", "lite", "bm25", "keyword"}:
        return "light"
    if normalized in {"embedding", "embeddings", "vector"}:
        return "embedding"
    return "auto"


def build_rag_index(
    resources: list[Resource] | None = None,
    *,
    query: str = "",
    mode: str = "auto",
    resource_dir: Path | None = None,
    manifest: dict[str, Any] | None = None,
    max_chunks_per_resource: int = 12,
) -> dict[str, Any]:
    rag_mode = normalize_rag_mode(mode)
    if rag_mode == "off":
        return _empty_index(rag_mode)
    chunks: list[dict[str, Any]] = []
    for resource in resources or []:
        chunks.extend(_chunks_from_resource(resource, max_chunks=max_chunks_per_resource))
    if resource_dir is not None and manifest is not None:
        chunks.extend(_chunks_from_bundle(resource_dir, manifest, max_chunks=max_chunks_per_resource))
    chunks = _dedupe_chunks(chunks)
    embedding_enabled, embedding_error = _embedding_status(rag_mode)
    if rag_mode == "embedding" and embedding_enabled:
        embedding_error = _add_embeddings(chunks)
        embedding_enabled = not embedding_error
    return {
        "mode": "embedding" if rag_mode == "embedding" and embedding_enabled else "light",
        "requested_mode": rag_mode,
        "embedding_enabled": embedding_enabled,
        "embedding_error": embedding_error,
        "query": query,
        "summary": {
            "chunks": len(chunks),
            "resources": len({chunk["resource_id"] for chunk in chunks}),
        },
        "chunks": chunks,
    }


def apply_rag_to_resources(profile: LearnerProfile, resources: list[Resource], *, mode: str = "auto") -> tuple[list[Resource], dict[str, Any]]:
    rag_mode = normalize_rag_mode(mode)
    if rag_mode == "off":
        return resources, _empty_index(rag_mode)
    index = build_rag_index(resources, query=profile.goal, mode=rag_mode)
    evidence_by_resource: dict[str, list[dict[str, Any]]] = {}
    for evidence in retrieve_evidence(profile.goal, index=index, limit=max(8, len(resources) * 2)):
        evidence_by_resource.setdefault(str(evidence.get("resource_id", "")), []).append(evidence)
    for resource in resources:
        resource_id = _resource_id(resource)
        top_chunks = evidence_by_resource.get(resource_id, [])[:3]
        evidence_score = round(sum(float(chunk.get("score", 0.0)) for chunk in top_chunks), 4)
        if top_chunks:
            resource.metadata["rag"] = {
                "mode": index["mode"],
                "evidence_score": evidence_score,
                "top_chunks": [_public_evidence_chunk(chunk) for chunk in top_chunks],
            }
            resource.score = round((resource.score or 0.0) + min(1.0, evidence_score / 3.0), 4)
            resource.why_recommended = resource.why_recommended or "Selected because retrieved evidence matches the learning goal."
    return sorted(resources, key=lambda item: (float(item.metadata.get("rag", {}).get("evidence_score", 0.0)), item.score), reverse=True), index


def public_rag_evidence(index: dict[str, Any], query: str, *, limit: int = 5) -> dict[str, Any]:
    if not index or normalize_rag_mode(str(index.get("requested_mode", index.get("mode", "auto")))) == "off":
        return {}
    return {
        "mode": index.get("mode", "light"),
        "requested_mode": index.get("requested_mode", "auto"),
        "embedding_enabled": bool(index.get("embedding_enabled")),
        "summary": dict(index.get("summary", {})),
        "top_chunks": [_public_evidence_chunk(chunk) for chunk in retrieve_evidence(query, index=index, limit=limit)],
    }


def retrieve_evidence(query: str, *, index: dict[str, Any] | None = None, chunks: list[dict[str, Any]] | None = None, limit: int = 5) -> list[dict[str, Any]]:
    corpus = chunks if chunks is not None else list((index or {}).get("chunks", []))
    if not corpus:
        return []
    if (index or {}).get("mode") == "embedding":
        embedded = _retrieve_embedding_evidence(query, corpus, limit)
        if embedded:
            return embedded
    query_terms = _tokenize(query)
    if not query_terms:
        return []
    idf = _idf(corpus)
    scored: list[dict[str, Any]] = []
    for chunk in corpus:
        terms = _tokenize(str(chunk.get("text") or chunk.get("snippet") or ""))
        if not terms:
            continue
        overlap = query_terms & terms
        phrase_bonus = _phrase_bonus(query, str(chunk.get("text") or chunk.get("snippet") or ""))
        score = sum(idf.get(term, 1.0) for term in overlap) + phrase_bonus
        if score <= 0:
            continue
        scored.append({**chunk, "score": round(score, 4)})
    scored.sort(key=lambda item: (float(item.get("score", 0.0)), len(str(item.get("snippet", "")))), reverse=True)
    return [_public_evidence_chunk(item) for item in scored[:limit]]


def write_bundle_rag_index(resource_dir: Path, manifest: dict[str, Any], *, query: str = "", mode: str = "auto") -> dict[str, Any]:
    index = build_rag_index([], query=query, mode=mode, resource_dir=resource_dir, manifest=manifest)
    target_dir = resource_dir / RAG_INDEX_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    (target_dir / RAG_INDEX_FILE).write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
    return index


def load_bundle_rag_index(resource_dir: Path) -> dict[str, Any]:
    target = resource_dir / RAG_INDEX_DIR / RAG_INDEX_FILE
    if not target.exists():
        return _empty_index("auto")
    return json.loads(target.read_text(encoding="utf-8"))


def answer_from_bundle(resource_dir: Path, question: str, *, limit: int = 5) -> dict[str, Any]:
    index = load_bundle_rag_index(resource_dir)
    evidence = retrieve_evidence(question, index=index, limit=limit)
    if not evidence:
        return {
            "status": "no-evidence",
            "question": question,
            "answer": "Evidence not found in the study bundle.",
            "sources": [],
        }
    snippets = [str(item.get("snippet", "")).strip() for item in evidence if str(item.get("snippet", "")).strip()]
    return {
        "status": "ok",
        "question": question,
        "answer": "Based on the study bundle: " + " ".join(snippets[:3]),
        "sources": evidence,
    }


def _chunks_from_resource(resource: Resource, *, max_chunks: int) -> list[dict[str, Any]]:
    resource_id = _resource_id(resource)
    file_name = ""
    private = bool(resource.local_path)
    text_parts = [
        resource.title,
        " ".join(resource.concepts),
        " ".join(resource.learning_key_points),
        " ".join(resource.focus_areas),
        resource.why_recommended,
    ]
    metadata = resource.metadata or {}
    paper_metadata = metadata.get("paper_metadata") if isinstance(metadata.get("paper_metadata"), dict) else {}
    if paper_metadata:
        for key in ("abstract_snippet", "sections", "method_hints", "experiment_hints", "limitations_hints", "formula_candidates", "keywords"):
            value = paper_metadata.get(key)
            text_parts.append(" ".join(str(item) for item in value) if isinstance(value, list) else str(value or ""))
    if resource.local_path:
        path = Path(resource.local_path)
        file_name = path.name
        text_parts.append(_read_supported_file(path))
    text = _clean_text("\n".join(part for part in text_parts if part))
    return _chunk_text(
        text,
        resource_id=resource_id,
        resource_title=resource.title,
        source=resource.source,
        resource_type=resource.type,
        file_name=file_name,
        private=private,
        max_chunks=max_chunks,
    )


def _chunks_from_bundle(resource_dir: Path, manifest: dict[str, Any], *, max_chunks: int) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    for entry in manifest.get("resources", []):
        if not isinstance(entry, dict) or not entry.get("file"):
            continue
        path = resource_dir / str(entry["file"])
        if not path.exists() or path.suffix.lower() not in SUPPORTED_RAG_EXTENSIONS:
            continue
        text = _read_supported_file(path)
        if not text:
            continue
        resource = Resource(
            title=str(entry.get("title") or path.stem),
            url=str(entry.get("url") or f"local://bundle/{path.name}"),
            source=str(entry.get("source") or "bundle"),
            type=str(entry.get("type") or "resource"),
        )
        chunks.extend(
            _chunk_text(
                text,
                resource_id=_resource_id(resource),
                resource_title=resource.title,
                source=resource.source,
                resource_type=resource.type,
                file_name=path.name,
                private=False,
                max_chunks=max_chunks,
            )
        )
    return chunks


def _chunk_text(
    text: str,
    *,
    resource_id: str,
    resource_title: str,
    source: str,
    resource_type: str,
    file_name: str,
    private: bool,
    max_chunks: int,
    chunk_chars: int = 900,
    overlap: int = 120,
) -> list[dict[str, Any]]:
    if not text:
        return []
    pieces: list[str] = []
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
    buffer = ""
    for paragraph in paragraphs or [text]:
        if len(buffer) + len(paragraph) <= chunk_chars:
            buffer = f"{buffer}\n{paragraph}".strip()
            continue
        if buffer:
            pieces.append(buffer)
        buffer = paragraph[-chunk_chars:]
    if buffer:
        pieces.append(buffer)
    output: list[dict[str, Any]] = []
    for index, piece in enumerate(pieces[: max_chunks or len(pieces)], start=1):
        if index > 1 and overlap:
            piece = (pieces[index - 2][-overlap:] + " " + piece).strip()
        snippet = _clip(piece, 420)
        chunk_id = sha256(f"{resource_id}:{index}:{snippet}".encode("utf-8", errors="ignore")).hexdigest()[:16]
        output.append(
            {
                "chunk_id": chunk_id,
                "resource_id": resource_id,
                "resource_title": resource_title,
                "source": source,
                "type": resource_type,
                "file_name": file_name,
                "chunk_index": index,
                "snippet": snippet,
                "text": piece,
                "private": private,
            }
        )
    return output


def _read_supported_file(path: Path, limit: int = 160000) -> str:
    suffix = path.suffix.lower()
    try:
        if suffix == ".pdf":
            return _read_pdf(path, limit)
        if suffix == ".ipynb":
            return _read_notebook(path, limit)
        if suffix in {".html", ".htm"}:
            return _read_html(path, limit)
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except OSError:
        return ""


def _read_pdf(path: Path, limit: int) -> str:
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        parts = []
        for page_number, page in enumerate(reader.pages[:16], start=1):
            parts.append(f"[page {page_number}]\n{page.extract_text() or ''}")
            if sum(len(part) for part in parts) >= limit:
                break
        return "\n".join(parts)[:limit]
    except Exception:
        return path.read_bytes()[:limit].decode("utf-8", errors="ignore")


def _read_notebook(path: Path, limit: int) -> str:
    try:
        import nbformat

        notebook = nbformat.read(path, as_version=4)
        parts = [str(cell.get("source", "")) for cell in notebook.cells]
        return "\n\n".join(parts)[:limit]
    except Exception:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]


def _read_html(path: Path, limit: int) -> str:
    raw = path.read_text(encoding="utf-8", errors="ignore")[:limit]
    try:
        from bs4 import BeautifulSoup

        return BeautifulSoup(raw, "html.parser").get_text("\n")[:limit]
    except Exception:
        return re.sub(r"<[^>]+>", " ", raw)[:limit]


def _resource_id(resource: Resource) -> str:
    public = resource.to_dict()
    seed = f"{public.get('title', '')}|{public.get('url', '')}|{resource.local_path or ''}"
    return sha256(seed.encode("utf-8", errors="ignore")).hexdigest()[:16]


def _dedupe_chunks(chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for chunk in chunks:
        key = str(chunk.get("chunk_id") or chunk.get("snippet", ""))
        if key in seen:
            continue
        seen.add(key)
        output.append(chunk)
    return output


def _public_evidence_chunk(chunk: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "chunk_id",
        "resource_id",
        "resource_title",
        "source",
        "type",
        "file_name",
        "chunk_index",
        "snippet",
        "score",
        "private",
    }
    return {key: chunk[key] for key in allowed if key in chunk and chunk[key] not in {None, ""}}


def _idf(chunks: list[dict[str, Any]]) -> dict[str, float]:
    documents = [_tokenize(str(chunk.get("text") or chunk.get("snippet") or "")) for chunk in chunks]
    total = max(1, len(documents))
    terms = sorted(set().union(*documents) if documents else set())
    return {term: math.log((total + 1) / (1 + sum(1 for doc in documents if term in doc))) + 1.0 for term in terms}


def _tokenize(value: str) -> set[str]:
    normalized = value.lower().replace("-", " ").replace("/", " ")
    tokens = {token.strip(".,:;()[]{}<>\"'`") for token in re.split(r"\s+", normalized) if len(token.strip(".,:;()[]{}<>\"'`")) >= 3}
    terms = {token for token in tokens if token not in STOPWORDS}
    for phrase in (
        "chain of thought",
        "chain-of-thought",
        "large language model",
        "symbolic planning",
        "automated planning",
        "state transition",
        "action preconditions",
        "plan validation",
        "pddl",
        "val",
    ):
        if phrase in normalized:
            terms.add(phrase.replace("-", " "))
    return terms


def _phrase_bonus(query: str, text: str) -> float:
    query_norm = " ".join(sorted(_tokenize(query)))
    text_norm = text.lower().replace("-", " ")
    bonus = 0.0
    for phrase in _tokenize(query):
        if " " in phrase and phrase in text_norm:
            bonus += 1.5
    if query_norm and query_norm in text_norm:
        bonus += 1.0
    return bonus


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _clip(value: str, limit: int) -> str:
    value = _clean_text(value)
    if len(value) <= limit:
        return value
    return value[: limit - 1].rstrip() + "..."


def _embedding_status(mode: str) -> tuple[bool, str]:
    if mode != "embedding":
        return False, ""
    try:
        import fastembed  # noqa: F401
        import numpy  # noqa: F401

        return True, ""
    except Exception as exc:
        return False, f"embedding_unavailable: {exc}"


def _add_embeddings(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return ""
    try:
        vectors = _embed_texts([str(chunk.get("text") or chunk.get("snippet") or "")[:4000] for chunk in chunks])
    except Exception as exc:
        return f"embedding_failed: {exc}"
    if len(vectors) != len(chunks):
        return "embedding_failed: vector_count_mismatch"
    for chunk, vector in zip(chunks, vectors):
        chunk["embedding"] = [round(float(value), 6) for value in vector]
    return ""


def _retrieve_embedding_evidence(query: str, corpus: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    embedded_chunks = [chunk for chunk in corpus if isinstance(chunk.get("embedding"), list)]
    if not embedded_chunks:
        return []
    try:
        query_vector = _embed_texts([query])[0]
    except Exception:
        return []
    scored: list[dict[str, Any]] = []
    for chunk in embedded_chunks:
        score = _cosine_similarity(query_vector, chunk["embedding"])
        if score <= 0:
            continue
        scored.append({**chunk, "score": round(score, 4)})
    scored.sort(key=lambda item: float(item.get("score", 0.0)), reverse=True)
    return [_public_evidence_chunk(item) for item in scored[:limit]]


def _embed_texts(texts: list[str]) -> list[Any]:
    import numpy as np
    from fastembed import TextEmbedding

    model = TextEmbedding()
    return [np.asarray(vector, dtype=float) for vector in model.embed(texts)]


def _cosine_similarity(left: Any, right: Any) -> float:
    import numpy as np

    left_vector = np.asarray(left, dtype=float)
    right_vector = np.asarray(right, dtype=float)
    denominator = float(np.linalg.norm(left_vector) * np.linalg.norm(right_vector))
    if denominator == 0:
        return 0.0
    return float(np.dot(left_vector, right_vector) / denominator)


def _empty_index(mode: str) -> dict[str, Any]:
    return {
        "mode": "off" if normalize_rag_mode(mode) == "off" else "light",
        "requested_mode": normalize_rag_mode(mode),
        "embedding_enabled": False,
        "embedding_error": "",
        "query": "",
        "summary": {"chunks": 0, "resources": 0},
        "chunks": [],
    }
