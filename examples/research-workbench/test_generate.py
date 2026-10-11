"""Run explicitly: python -m pytest -q examples/research-workbench/test_generate.py."""
import importlib.util
import json
import socket
from pathlib import Path

import pytest


HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("workbench_examples", HERE / "generate.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def test_source_records_are_versioned_and_do_not_redistribute_papers():
    records = generator.load_records()
    assert {r["scenario"] for r in records} == {
        "planning-paper", "transformer-paper-project", "diffusion-missing-materials",
    }
    for record in records:
        assert record["url"].endswith(record["version"])
        assert record["content_kind"] == "original_short_paraphrase"
        assert record["verbatim_quote_words"] == 0
        assert (HERE / record["note"]).is_file()
        assert "not" in record["coverage_boundary"].lower()


def test_generation_is_offline_and_preserves_evidence_boundaries(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Example generation attempted network access")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setenv("FIELDS_STUDY_FLOW_LLM_ENABLED", "true")
    monkeypatch.setenv("FIELDS_STUDY_FLOW_LLM_BASE_URL", "https://invalid.example/v1")
    monkeypatch.setenv("FIELDS_STUDY_FLOW_LLM_MODEL", "must-not-be-called")
    monkeypatch.setenv("FIELDS_STUDY_FLOW_LLM_API_KEY", "test-only")
    manifest = generator.generate(tmp_path, output_language="en")
    assert manifest["human_evaluation"] == "pending"
    assert manifest["screenshots"] == "pending"
    assert len(manifest["scenarios"]) == 3
    for item in manifest["scenarios"]:
        report = json.loads((tmp_path / item["id"] / "roadmap.json").read_text(encoding="utf-8"))
        context = report["research_context"]
        assert context["validation"]["valid"]
        assert context["explanations"]["mode"] == "local"
        assert context["anchors"]
        assert context["learning_steps"]
        assert report["paper_lens"]["segments"]
        assert any("Original paraphrase" in s["original_text"] for s in report["paper_lens"]["segments"])
        assert not any(r["review_status"] == "accepted" for r in context["relations"])
        assert report["example_provenance"]["paper_reproduction"] is False
        assert not (tmp_path / item["id"] / "index.html").exists()
        for source in context["sources"]:
            assert source.get("local_href"), source["title"]
            assert (tmp_path / item["id"] / source["local_href"]).is_file()
        assert len({m["name"] for m in item["materials"]}) == len(item["materials"])
        if item["id"] == "transformer-paper-project":
            assert {"paper", "code", "config", "result", "readme"} <= {s["kind"] for s in context["sources"]}
            records = json.loads((tmp_path / item["id"] / "source_records.json").read_text(encoding="utf-8"))
            assert records["toy_project"]["version"] == "own-demo-v1"
            assert "Hand-computed" in records["toy_project"]["result_provenance"] or "hand-computed" in records["toy_project"]["result_provenance"]
        if item["id"] == "diffusion-missing-materials":
            assert not any(s["kind"] in {"code", "config", "result"} for s in context["sources"])
            assert any(s["status"] == "needs_material" for s in context["learning_steps"])
    before = json.loads((tmp_path / "transformer-paper-project" / "roadmap.json").read_text(encoding="utf-8"))["research_context"]
    generator.generate(tmp_path, output_language="en")
    after = json.loads((tmp_path / "transformer-paper-project" / "roadmap.json").read_text(encoding="utf-8"))["research_context"]
    # Copy/reuse attempt metadata may change; source identity and context must not.
    assert after == before


def test_optional_html_uses_shared_exporter(tmp_path):
    generator.generate(tmp_path, output_language="en", export_html=True)
    for record in generator.load_records():
        directory = tmp_path / record["scenario"]
        assert all((directory / name).is_file() for name in (
            "index.html", "paper_map.html", "paper_lens.html", "roadmap.html",
        ))


def test_output_cannot_overwrite_example_sources():
    with pytest.raises(ValueError, match="output"):
        generator.generate(HERE)


def test_expected_trace_is_an_arithmetic_check_not_a_paper_result():
    demo_spec = importlib.util.spec_from_file_location("own_attention_demo", HERE / "toy-transformer/attention.py")
    demo = importlib.util.module_from_spec(demo_spec)
    demo_spec.loader.exec_module(demo)
    config = json.loads((HERE / "toy-transformer/config.json").read_text(encoding="utf-8"))
    expected = json.loads((HERE / "toy-transformer/expected_trace.json").read_text(encoding="utf-8"))
    actual = demo.scalar_attention(config["query"], config["keys"], config["values"], config["temperature"])
    assert actual["weights"] == expected["weights"]
    assert actual["output"] == expected["output"]
    assert expected["paper_reproduction"] is False
    assert "NOT measured" in expected["provenance"]
