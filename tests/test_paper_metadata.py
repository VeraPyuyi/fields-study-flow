from __future__ import annotations

import json

import pytest

from fields_study_flow.paper_metadata import paper_metadata_to_resource, resolve_paper_metadata


class FakeResponse:
    def __init__(self, *, text: str = "", payload: dict | None = None, content: bytes = b"", status_code: int = 200) -> None:
        self.text = text
        self._payload = payload or {}
        self.content = content or text.encode("utf-8")
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeClient:
    def __init__(self, routes: dict[str, FakeResponse | Exception]) -> None:
        self.routes = routes
        self.requests: list[tuple[str, dict]] = []

    def get(self, url: str, params: dict | None = None, timeout: float | None = None) -> FakeResponse:
        self.requests.append((url, params or {}))
        key = url
        if key not in self.routes:
            raise AssertionError(f"unexpected request: {url} {params}")
        result = self.routes[key]
        if isinstance(result, Exception):
            raise result
        return result


def test_resolve_arxiv_metadata_extracts_public_paper_fields() -> None:
    atom = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/1706.03762v7</id>
        <title>Attention Is All You Need</title>
        <summary>The dominant sequence transduction models are based on complex recurrent or convolutional neural networks. We propose a new simple network architecture, the Transformer, based solely on attention mechanisms.</summary>
        <published>2017-06-12T17:57:34Z</published>
        <updated>2023-08-02T00:00:00Z</updated>
        <author><name>Ashish Vaswani</name></author>
        <author><name>Noam Shazeer</name></author>
        <category term="cs.CL" />
      </entry>
    </feed>
    """
    client = FakeClient({"https://export.arxiv.org/api/query": FakeResponse(text=atom)})

    metadata = resolve_paper_metadata("https://arxiv.org/abs/1706.03762", client=client)

    assert metadata["metadata_status"] == "ok"
    assert metadata["title"] == "Attention Is All You Need"
    assert metadata["authors"][:2] == ["Ashish Vaswani", "Noam Shazeer"]
    assert metadata["source_ids"]["arxiv"] == "1706.03762"
    assert "transformer" in metadata["concepts"]
    assert "attention" in metadata["concepts"]
    assert "pdf_url" in metadata


def test_resolve_arxiv_metadata_enriches_public_fields_from_pdf_preview() -> None:
    atom = """<?xml version="1.0"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>http://arxiv.org/abs/2509.13351v1</id>
        <title>Teaching LLMs to Plan: Logical Chain-of-Thought Instruction Tuning for Symbolic Planning</title>
        <summary>We present PDDL-INSTRUCT for symbolic planning.</summary>
        <author><name>Pulkit Verma</name></author>
        <category term="cs.AI" />
      </entry>
    </feed>
    """
    pdf_preview = b"""%PDF-1.4
Teaching LLMs to Plan: Logical Chain-of-Thought
Instruction Tuning for Symbolic Planning
Pulkit Verma
MIT CSAIL
Ngoc La
MIT CSAIL
Abstract
Large language models struggle with structured symbolic planning in PDDL. We present PDDL-INSTRUCT, a framework that teaches logical chain-of-thought reasoning with VAL feedback.
1 Introduction
LLMs struggle with action applicability and state transitions.
5 PDDL-INSTRUCT Methodology
Our approach uses structured instruction tuning and verifier feedback.
6 Empirical Evaluation
Experiments evaluate PlanBench domains and plan accuracy.
8 Conclusion
Limitations and Future Work include satisficing rather than optimal planning.
%%EOF"""
    client = FakeClient(
        {
            "https://export.arxiv.org/api/query": FakeResponse(text=atom),
            "https://arxiv.org/pdf/2509.13351.pdf": FakeResponse(content=pdf_preview),
        }
    )

    metadata = resolve_paper_metadata("https://arxiv.org/abs/2509.13351", client=client)

    assert metadata["metadata_status"] == "ok"
    assert metadata["title"] == "Teaching LLMs to Plan: Logical Chain-of-Thought Instruction Tuning for Symbolic Planning"
    assert {"Introduction", "PDDL-INSTRUCT Methodology", "Empirical Evaluation", "Conclusion"} <= set(metadata["sections"])
    assert metadata["method_hints"]
    assert metadata["experiment_hints"]
    assert metadata["limitations_hints"]
    assert "pddl" in metadata["concepts"]
    assert "val verifier" in metadata["concepts"]


def test_resolve_arxiv_metadata_falls_back_to_pdf_when_api_fails() -> None:
    pdf_preview = b"""%PDF-1.4
Teaching LLMs to Plan: Logical Chain-of-Thought
Instruction Tuning for Symbolic Planning
Pulkit Verma
MIT CSAIL
Ngoc La
MIT CSAIL
Anthony Favier
MIT CSAIL
Abstract
Large language models struggle with formal symbolic planning. PDDL-INSTRUCT teaches action applicability, state transitions, plan validity, and logical chain-of-thought reasoning using VAL feedback.
1 Introduction
LLMs struggle with structured symbolic planning.
5 PDDL-INSTRUCT Methodology
The method uses CoT instruction tuning and verifier feedback.
6 Empirical Evaluation
Experiments on PlanBench compare binary and detailed feedback.
8 Conclusion
Limitations and Future Work discuss optimal planning and broader PDDL coverage.
%%EOF"""
    client = FakeClient(
        {
            "https://export.arxiv.org/api/query": RuntimeError("rate limited"),
            "https://arxiv.org/pdf/2509.13351.pdf": FakeResponse(content=pdf_preview),
        }
    )

    metadata = resolve_paper_metadata("https://arxiv.org/abs/2509.13351", client=client)

    assert metadata["metadata_status"] == "ok"
    assert metadata["title"] == "Teaching LLMs to Plan: Logical Chain-of-Thought Instruction Tuning for Symbolic Planning"
    assert metadata["authors"][:2] == ["Pulkit Verma", "Ngoc La"]
    assert metadata["source"] == "arxiv"
    assert metadata["source_ids"]["arxiv"] == "2509.13351"
    assert metadata["abstract_snippet"]
    assert metadata["sections"]
    assert any("arxiv_unavailable" in warning for warning in metadata["warnings"])
    assert any("arxiv_pdf_fallback" in warning for warning in metadata["warnings"])


def test_resolve_arxiv_metadata_falls_back_when_api_is_unavailable() -> None:
    client = FakeClient({"https://export.arxiv.org/api/query": RuntimeError("rate limited")})

    metadata = resolve_paper_metadata("https://arxiv.org/abs/1706.03762", client=client)

    assert metadata["metadata_status"] == "partial"
    assert metadata["title"] == "Attention Is All You Need"
    assert metadata["source_ids"]["arxiv"] == "1706.03762"
    assert "transformer" in metadata["concepts"]
    assert any("arxiv_unavailable" in warning for warning in metadata["warnings"])
    assert any("offline_catalog_fallback" in warning for warning in metadata["warnings"])


def test_resolve_arxiv_metadata_uses_offline_catalog_when_live_disabled() -> None:
    metadata = resolve_paper_metadata("https://arxiv.org/abs/1706.03762", live=False)

    assert metadata["metadata_status"] == "partial"
    assert metadata["title"] == "Attention Is All You Need"
    assert metadata["source_ids"]["arxiv"] == "1706.03762"
    assert {"transformer", "self attention"} <= set(metadata["concepts"])


def test_resolve_arxiv_doi_prefers_arxiv_fallback_when_live_api_fails() -> None:
    client = FakeClient({"https://export.arxiv.org/api/query": RuntimeError("rate limited")})

    metadata = resolve_paper_metadata("https://doi.org/10.48550/arXiv.1706.03762", client=client)

    assert metadata["title"] == "Attention Is All You Need"
    assert metadata["source"] == "arxiv"
    assert metadata["source_ids"]["arxiv"] == "1706.03762"
    assert "offline_catalog_fallback" in metadata["warnings"]
    assert not any("semanticscholar" in url for url, _params in client.requests)


def test_resolve_doi_metadata_uses_open_source_fallback_when_semantic_scholar_fails() -> None:
    client = FakeClient(
        {
            "https://api.semanticscholar.org/graph/v1/paper/DOI:10.5555/example": RuntimeError("rate limited"),
            "https://api.openalex.org/works/doi:10.5555/example": FakeResponse(
                payload={
                    "display_name": "Denoising Diffusion Probabilistic Models",
                    "authorships": [{"author": {"display_name": "Jonathan Ho"}}],
                    "abstract_inverted_index": {
                        "Diffusion": [0],
                        "models": [1],
                        "learn": [2],
                        "denoising": [3],
                        "objectives": [4],
                    },
                    "concepts": [{"display_name": "Diffusion model"}, {"display_name": "Machine learning"}],
                    "doi": "https://doi.org/10.5555/example",
                }
            ),
        }
    )

    metadata = resolve_paper_metadata("https://doi.org/10.5555/example", client=client)

    assert metadata["metadata_status"] == "ok"
    assert metadata["title"] == "Denoising Diffusion Probabilistic Models"
    assert metadata["source_ids"]["doi"] == "10.5555/example"
    assert "Jonathan Ho" in metadata["authors"]
    assert "diffusion models" in metadata["concepts"]
    assert any("semantic_scholar" in warning for warning in metadata["warnings"])


def test_resolve_local_pdf_extracts_structure_without_exposing_private_path(tmp_path) -> None:
    pdf = tmp_path / "private-paper.pdf"
    pdf.write_bytes(
        b"""\xef\xbb\xbf%PDF-1.4
Learning Stable Diffusion Samplers
Abstract
We study diffusion models, denoising objectives, and fast sampling.
Keywords: diffusion models, denoising, fast sampling
1 Introduction
Diffusion models generate images through iterative denoising.
2 Method
The method predicts noise epsilon and uses classifier-free guidance.
The objective is L_simple = E[||epsilon - epsilon_theta(x_t, t)||^2].
Code is available at https://github.com/example/diffusion-sampler.
3 Experiments
Experiments compare FID and sampling speed on image datasets.
4 Limitations
Limitations include slow sampling and high compute cost.
%%EOF"""
    )

    metadata = resolve_paper_metadata(str(pdf), live=False)

    assert metadata["metadata_status"] in {"ok", "partial"}
    assert metadata["title"] == "Learning Stable Diffusion Samplers"
    assert metadata["local_path"] is None
    assert "diffusion models" in metadata["concepts"]
    assert "Method" in metadata["sections"]
    assert metadata["method_hints"]
    assert metadata["experiment_hints"]
    assert metadata["limitations_hints"]
    assert "diffusion models" in metadata["keywords"]
    assert any("epsilon_theta" in formula for formula in metadata["formula_candidates"])
    assert metadata["code_links"] == ["https://github.com/example/diffusion-sampler"]


def test_file_uri_pdf_is_treated_as_private_local_paper(tmp_path) -> None:
    pdf = tmp_path / "private-paper.pdf"
    pdf.write_bytes(
        b"""%PDF-1.4
Private Paper Title
Abstract
We study transformer attention.
1 Method
The method uses scaled dot product attention.
%%EOF"""
    )

    metadata = resolve_paper_metadata(pdf.as_uri(), live=False)
    resource = paper_metadata_to_resource(metadata)
    public = json.dumps(resource.to_dict(), ensure_ascii=False)

    assert metadata["local_path"] is None
    assert metadata["url"].startswith("local://")
    assert "file:" not in metadata["url"]
    assert str(pdf) not in public
    assert pdf.as_uri() not in public


def test_missing_file_uri_does_not_leak_private_path(tmp_path) -> None:
    missing_pdf = tmp_path / "missing-private-paper.pdf"

    metadata = resolve_paper_metadata(missing_pdf.as_uri(), live=False)
    resource = paper_metadata_to_resource(metadata)
    public = json.dumps(resource.to_dict(), ensure_ascii=False)

    assert metadata["source"] == "local-library"
    assert metadata["url"].startswith("local://")
    assert "file:" not in public
    assert str(missing_pdf) not in public
    assert any("local_file_unavailable" in warning for warning in metadata["warnings"])


def test_paper_metadata_to_resource_anchors_ranking_without_private_metadata() -> None:
    metadata = {
        "title": "Useful New Paper",
        "url": "https://example.org/paper",
        "source": "user-paper",
        "abstract_snippet": "A paper about verification and reproducible learning.",
        "authors": ["Ada Example"],
        "source_ids": {},
        "concepts": ["verification", "reproducibility"],
        "sections": ["Introduction", "Method"],
        "method_hints": ["Method explains the verification pipeline."],
        "experiment_hints": [],
        "limitations_hints": [],
        "metadata_status": "partial",
        "warnings": ["metadata_unavailable"],
        "local_path": None,
    }

    resource = paper_metadata_to_resource(metadata)
    public = resource.to_dict()

    assert resource.title == "Useful New Paper"
    assert resource.metadata["target_paper"] is True
    assert resource.metadata["paper_metadata"]["title"] == "Useful New Paper"
    assert resource.critical_path_role == "core-paper"
    assert "verification" in resource.concepts
    assert json.dumps(public, ensure_ascii=False).find("C:/") == -1
