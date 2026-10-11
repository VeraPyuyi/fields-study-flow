import copy
import json
import shutil
import socket

import httpx
import pytest

from fields_study_flow import frontend_report, mcp_tools, roadmap
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.paper_lens import build_paper_lens
from fields_study_flow.paper_map import build_paper_map


@pytest.fixture
def prepared_plan(monkeypatch):
    method = "Self-attention compares token queries and keys before weighting values."
    paragraphs = [
        ("abstract", "The demonstration studies token representations without recurrence. The source describes an attention-based model."),
        ("method", method),
        ("method", "Multi-head attention combines separately projected representations. The outputs are concatenated before another projection."),
        ("method", "Positional encodings provide information about token order by assigning each sequence position a representation that remains distinguishable from representations assigned to other positions, so comparisons can retain the order information supplied by the source. The model adds these representations to token embeddings before the attention blocks process the sequence, preserving both the token content and its position in the representation described by this demonstration."),
        ("method", "The feed-forward block transforms each token representation. The same transformation is applied at every position."),
        ("method", "Residual connections preserve an input path through each block. Normalization is applied around the resulting representations."),
        ("experiment", "Evaluation compares translation quality on held-out sequences. The source records the dataset and comparison conditions."),
        ("limitation", "The study evaluates only the supplied translation conditions. Generalization to other tasks remains untested."),
    ]
    text = "\n\n".join(f"{kind.title()}\n{paragraph}" for kind, paragraph in paragraphs)
    resource = Resource(
        title="Demonstration paper", url="https://example.org/paper", source="demonstration",
        type="paper", metadata={"target_paper": True, "paper_metadata": {
            "title": "Demonstration paper", "abstract_snippet": paragraphs[0][1],
            "method_hints": [method], "sections": ["Method"], "text_preview": text,
            "formula_candidates": ["weighted_values = attention_weights * values"],
        }},
    )
    plan = {
        "title": "Demonstration report",
        "profile": LearnerProfile(goal="Understand the demonstration paper", output_language="en").to_dict(),
        "phases": [{"name": "Read", "objective": "Understand", "estimated_time": "1h", "resources": [resource.to_dict()]}],
        "checkpoints": [], "safety_policy": [], "outputs": [],
        "paper_lens_options": {"language": "en", "density": "key", "granularity": "sentence"},
        "paper_map_options": {"language": "en", "depth": "quick", "layout": "xmind-flow", "provider": "local"},
    }
    plan["paper_lens"] = build_paper_lens(plan, paper_lens_language="en", paper_lens_density="key", paper_lens_granularity="sentence")
    plan["paper_map"] = build_paper_map(plan, paper_map_language="en", paper_map_depth="quick", paper_map_provider="local")
    reference = {"anchor_id": "anchor-method", "source_id": "paper-source", "locator": {"section": "Method"}, "snippet": method}
    plan["research_context"] = {
        "schema_version": 1, "bundle_id": "demo-bundle", "snapshot_id": "demo-snapshot",
        "primary_source_ids": ["paper-source"],
        "sources": [{"id": "paper-source", "kind": "paper", "title": resource.title,
                     "url": resource.url, "fingerprint": "demo-fingerprint"}],
        "anchors": [{"id": "anchor-method", "source_id": "paper-source",
                     "locator": reference["locator"], "snippet": method, "locator_status": "valid"}],
        "claims": [{"id": "claim-method", "kind": "methodology", "statement": method,
                    "anchor_ids": ["anchor-method"], "evidence_status": "located"}],
        "relations": [], "learning_steps": [],
        "explanations": {"mode": "llm", "language": "en", "status": "ready", "warnings": [], "items": [{
            "claim_id": "claim-method", "kind": "methodology", "anchor_ids": ["anchor-method"],
            "plain_meaning": "Saved model explanation of token comparisons.",
            "why_it_matters": "The excerpt identifies how token information is combined.",
            "method_note": "Read the stated query and key comparison before the value weighting.",
            "evidence_refs": [reference], "review_status": "unreviewed",
        }]},
    }
    from fields_study_flow.workbench import project_prepared_views

    plan = project_prepared_views(plan)
    assert any(item["plain_meaning"].startswith("Saved model explanation") for item in plan["paper_lens"]["inline_explanations"])
    monkeypatch.setattr("fields_study_flow.paper_lens._latex_engine", lambda: None)
    monkeypatch.setattr(frontend_report, "_dist_dir", lambda: None)
    return plan


@pytest.fixture
def forbid_export_network(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Export must not generate explanations or access the network")

    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)
    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    monkeypatch.setattr("fields_study_flow.explanations.prepare_explanations", forbidden)
    monkeypatch.setattr("fields_study_flow.explanation_provider.request_explanations", forbidden)
    for key, value in {"ENABLED": "true", "BASE_URL": "https://example.invalid/v1", "MODEL": "test-model", "API_KEY": "test-export-key"}.items():
        monkeypatch.setenv("FIELDS_STUDY_FLOW_LLM_" + key, value)


def read_plan(directory):
    return json.loads((directory / "roadmap.json").read_text(encoding="utf-8"))


def test_shared_export_reuses_snapshot_without_builders_or_network(tmp_path, prepared_plan, monkeypatch, forbid_export_network):
    from fields_study_flow.report_export import export_report

    def forbidden(*args, **kwargs):
        pytest.fail("Prepared export must not rebuild or use the network")

    monkeypatch.setattr(roadmap, "_ensure_paper_lens", forbidden)
    monkeypatch.setattr(roadmap, "_ensure_paper_map", forbidden)
    before = copy.deepcopy(prepared_plan)
    result = export_report(tmp_path, prepared_plan)
    public = read_plan(tmp_path)
    assert prepared_plan == before
    for key in ("paper_map", "paper_lens_options", "paper_map_options", "research_context"):
        assert public[key] == before[key]
    lens = public["paper_lens"]
    lens.pop("latex_export")
    assert lens == before["paper_lens"]
    assert result["paper_lens_tex"].endswith("paper_lens.tex")


def test_cli_and_mcp_export_same_snapshot_and_legacy_keys(tmp_path, prepared_plan):
    cli_dir, mcp_dir = tmp_path / "cli", tmp_path / "mcp"
    profile = LearnerProfile(**prepared_plan["profile"])
    roadmap.write_outputs(cli_dir, profile, [], prepared_plan, {"sources": []})
    result = mcp_tools.exportPlan(prepared_plan, str(mcp_dir))
    assert read_plan(cli_dir) == read_plan(mcp_dir)
    assert set(result) >= {
        "index_html", "report_audit_json", "roadmap_json", "roadmap_md", "roadmap_svg",
        "roadmap_html", "study_cards_md", "study_quiz_md", "mastery_worksheet_md",
        "quick_brief_md", "evidence_coverage_md", "evidence_coverage_html",
        "paper_map_html", "paper_lens_html", "paper_lens_tex",
    }
    for key in result:
        assert (cli_dir / result[key].replace("\\", "/").rsplit("/", 1)[-1]).read_bytes() == (mcp_dir / result[key].replace("\\", "/").rsplit("/", 1)[-1]).read_bytes()
    assert (cli_dir / "source_registry_snapshot.json").is_file()


def test_only_explicit_options_rebuild_actual_language_and_density(tmp_path, prepared_plan, forbid_export_network):
    before = copy.deepcopy(prepared_plan)
    mcp_tools.exportPlan(prepared_plan, str(tmp_path), paperMapLanguage="zh-CN", paperLensDensity="dense")
    public = read_plan(tmp_path)
    assert public["paper_map_options"] == {**prepared_plan["paper_map_options"], "language": "zh-CN"}
    assert public["paper_lens_options"] == {**prepared_plan["paper_lens_options"], "density": "dense"}
    assert public["paper_map"]["output_language"] == "zh-CN"
    assert public["paper_lens"]["output_language"] == "en"
    assert public["paper_lens"]["explanation_summary"]["density"] == "dense"
    assert len(public["paper_lens"]["segments"]) > len(before["paper_lens"]["segments"])
    assert all(segment["unit"] == "sentence" for segment in public["paper_lens"]["segments"])
    saved = before["research_context"]["explanations"]["items"][0]["plain_meaning"]
    method = next(node for node in public["paper_map"]["nodes"] if node["kind"] == "methodology")
    assert method["plain_explanation"] != saved
    assert any("\u4e00" <= char <= "\u9fff" for char in method["plain_explanation"])
    assert any(item["plain_meaning"] == saved for item in public["paper_lens"]["inline_explanations"])
    assert public["research_context"]["explanations"] == before["research_context"]["explanations"]
    assert prepared_plan == before


def test_explicit_granularity_and_depth_change_actual_segments_and_branches(tmp_path, prepared_plan, forbid_export_network):
    before = copy.deepcopy(prepared_plan)
    mcp_tools.exportPlan(prepared_plan, str(tmp_path), paperLensDensity="dense", paperLensGranularity="paragraph", paperMapDepth="complete")
    public = read_plan(tmp_path)
    segments = public["paper_lens"]["segments"]
    assert all(segment["unit"] == "paragraph" for segment in segments)
    assert any(segment["sentence_count"] > 1 for segment in segments)
    assert any("Positional encodings" in segment["original_text"] and "token embeddings" in segment["original_text"] for segment in segments)
    branches = lambda view: [node for node in view["nodes"] if node["role"] not in {"target", "core"}]
    assert len(branches(public["paper_map"])) > len(branches(before["paper_map"]))
    assert any(node["kind"] == "formula" for node in branches(public["paper_map"]))
    assert public["research_context"]["explanations"] == before["research_context"]["explanations"]


def test_explicit_lens_language_does_not_reuse_saved_answer_in_another_language(tmp_path, prepared_plan, forbid_export_network):
    saved = prepared_plan["research_context"]["explanations"]["items"][0]["plain_meaning"]
    mcp_tools.exportPlan(prepared_plan, str(tmp_path), paperLensLanguage="zh-CN")
    public = read_plan(tmp_path)
    assert public["paper_map"] == prepared_plan["paper_map"]
    assert all(item["plain_meaning"] != saved for item in public["paper_lens"]["inline_explanations"])
    assert all(any("\u4e00" <= char <= "\u9fff" for char in item["plain_meaning"]) for item in public["paper_lens"]["inline_explanations"])
    assert public["research_context"]["explanations"] == prepared_plan["research_context"]["explanations"]


@pytest.mark.parametrize("view", ["paper_map", "paper_lens"])
def test_disable_removes_prepared_and_stale_views(tmp_path, prepared_plan, view):
    prepared_plan[view + "_disabled"] = True
    stale = [view + ".html"] + (["paper_lens.tex", "paper_lens.pdf"] if view == "paper_lens" else [])
    for name in stale:
        (tmp_path / name).write_text("stale", encoding="utf-8")
    prepared_plan["outputs"] = stale[:]
    result = mcp_tools.exportPlan(prepared_plan, str(tmp_path), paperMapLanguage="en", paperLensLanguage="en")
    public = read_plan(tmp_path)
    assert not public.get(view)
    assert view + "_html" not in result
    for name in stale:
        assert name not in public["outputs"]
        assert not (tmp_path / name).exists()


def test_bundle_rebinds_context_and_both_prepared_views_and_survives_move(tmp_path, prepared_plan, forbid_export_network):
    prepared_plan["paper_map"]["target"]["local_href"] = "stale-assets/paper.pdf"
    prepared_plan["paper_lens"]["target_papers"][0]["local_href"] = "stale-assets/paper.pdf"
    saved = copy.deepcopy(prepared_plan["research_context"]["explanations"])
    prepared_plan["study_bundle"] = {"resources": [{
        "title": "Demonstration paper", "url": "https://example.org/paper",
        "status": "copied", "local_href": "study-assets/paper.md",
    }]}
    output = tmp_path / "original"
    (output / "study-assets").mkdir(parents=True)
    (output / "study-assets/paper.md").write_text("source", encoding="utf-8")
    mcp_tools.exportPlan(prepared_plan, str(output))
    public = read_plan(output)
    assert public["research_context"]["sources"][0]["local_href"] == "study-assets/paper.md"
    assert public["paper_map"]["target"]["local_href"] == "study-assets/paper.md"
    assert public["paper_lens"]["target_papers"][0]["local_href"] == "study-assets/paper.md"
    assert public["research_context"]["explanations"] == saved
    moved = tmp_path / "moved"
    shutil.move(str(output), str(moved))
    assert (moved / public["research_context"]["sources"][0]["local_href"]).read_text() == "source"


def test_existing_renderers_keep_malicious_script_and_private_paths_inert(tmp_path, prepared_plan):
    attack = '</script><script id="injected">alert(1)</script>'
    prepared_plan["title"] = attack
    prepared_plan["notes"] = "C:/Users/example/private/paper.pdf"
    mcp_tools.exportPlan(prepared_plan, str(tmp_path))
    for name in ("index.html", "roadmap.html", "paper_map.html", "paper_lens.html", "evidence_coverage.html"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        assert attack not in text
        assert '<script id="injected">' not in text
        assert "C:/Users/example/private" not in text


def test_legacy_missing_views_use_saved_options(tmp_path, prepared_plan, forbid_export_network):
    prepared_plan.pop("paper_lens")
    prepared_plan.pop("paper_map")
    mcp_tools.exportPlan(prepared_plan, str(tmp_path))
    public = read_plan(tmp_path)
    assert public["paper_lens"]["explanation_summary"]["density"] == "key"
    assert public["paper_lens"]["explanation_summary"]["granularity"] == "sentence"
    assert public["paper_map"]["depth"] == "quick"
    assert public["research_context"]["explanations"] == prepared_plan["research_context"]["explanations"]


def test_context_without_bundle_is_preserved_not_regenerated(tmp_path, prepared_plan, forbid_export_network):
    prepared_plan["research_context"]["sources"][0]["local_href"] = "../study-assets/saved-paper.md"
    prepared_plan["paper_map"]["target"]["local_href"] = "../study-assets/saved-paper.md"
    prepared_plan["paper_lens"]["target_papers"][0]["local_href"] = "../study-assets/saved-paper.md"
    context = copy.deepcopy(prepared_plan["research_context"])
    mcp_tools.exportPlan(prepared_plan, str(tmp_path))
    public = read_plan(tmp_path)
    assert public["research_context"] == context
    assert public["paper_map"]["target"]["local_href"] == "../study-assets/saved-paper.md"
    assert public["paper_lens"]["target_papers"][0]["local_href"] == "../study-assets/saved-paper.md"


def test_explicit_unchanged_options_preserve_saved_model_views(tmp_path, prepared_plan, forbid_export_network):
    mcp_tools.exportPlan(prepared_plan, str(tmp_path), paperLensLanguage="en", paperLensDensity="key",
                         paperLensGranularity="sentence", paperMapLanguage="en", paperMapDepth="quick")
    public = read_plan(tmp_path)
    lens = public["paper_lens"]
    lens.pop("latex_export")
    assert lens == prepared_plan["paper_lens"]
    assert public["paper_map"] == prepared_plan["paper_map"]
    assert public["research_context"] == prepared_plan["research_context"]


def test_export_does_not_bind_same_title_with_a_conflicting_url(tmp_path, prepared_plan, forbid_export_network):
    prepared_plan["study_bundle"] = {"resources": [{"title": "Demonstration paper",
        "url": "https://example.org/another-paper", "status": "copied", "local_href": "assets/wrong-paper.pdf"}]}
    mcp_tools.exportPlan(prepared_plan, str(tmp_path))
    public = read_plan(tmp_path)
    assert not public["paper_map"]["target"].get("local_href")
    assert not public["paper_lens"]["target_papers"][0].get("local_href")
    assert not public["research_context"]["sources"][0].get("local_href")


def test_none_only_overrides_preserve_snapshot_without_rebuild_or_reprojection(tmp_path, prepared_plan, forbid_export_network, monkeypatch):
    from fields_study_flow.report_export import export_report

    def forbidden(*args, **kwargs):
        pytest.fail("None-only overrides must not change a prepared view")

    monkeypatch.setattr(roadmap, "_ensure_paper_lens", forbidden)
    monkeypatch.setattr(roadmap, "_ensure_paper_map", forbidden)
    monkeypatch.setattr("fields_study_flow.workbench.project_prepared_views", forbidden)
    export_report(tmp_path, prepared_plan, paper_lens_options={"language": None, "density": None, "granularity": None},
                  paper_map_options={"language": None, "depth": None, "layout": None, "provider": None})
    public = read_plan(tmp_path)
    public["paper_lens"].pop("latex_export")
    for key in ("paper_lens", "paper_map", "paper_lens_options", "paper_map_options", "research_context"):
        assert public[key] == prepared_plan[key]


def test_export_redacts_absolute_private_paths_but_preserves_portable_parent_links(tmp_path, prepared_plan, forbid_export_network):
    prepared_plan["notes"] = {
        "unc": r"\\private-unc-host\private-share\research-paper.pdf",
        "mnt": "/mnt/private-mount/research-paper.pdf",
        "srv": "/srv/private-project/parameters.yaml",
        "generic_file": "/var/research/private-experiment.json",
        "windows": r"C:\private-drive\research-paper.pdf",
        "portable_parent": "../study-assets/portable-paper.md",
        "portable_child": "study-assets/portable-paper.md",
    }
    mcp_tools.exportPlan(prepared_plan, str(tmp_path))
    public = read_plan(tmp_path)
    assert public["notes"]["portable_parent"] == "../study-assets/portable-paper.md"
    assert public["notes"]["portable_child"] == "study-assets/portable-paper.md"
    for name in ("roadmap.json", "roadmap.html", "paper_map.html", "paper_lens.html"):
        text = (tmp_path / name).read_text(encoding="utf-8")
        for private_marker in ("private-unc-host", "private-share", "private-mount", "private-project", "private-experiment", "private-drive"):
            assert private_marker not in text


def test_frontend_payload_reuses_snapshot_and_escapes_script(tmp_path, prepared_plan, monkeypatch):
    dist = tmp_path / "frontend-fixture"
    dist.mkdir()
    (dist / "manifest.json").write_text(json.dumps({"index.html": {"file": "app.js"}}), encoding="utf-8")
    (dist / "app.js").write_text("throw new Error('demonstration script failure');", encoding="utf-8")
    monkeypatch.setattr(frontend_report, "_dist_dir", lambda: dist)
    attack = '</script><script id="injected">alert(1)</script>'
    prepared_plan["title"] = attack
    output = tmp_path / "report"
    mcp_tools.exportPlan(prepared_plan, str(output))
    for name in ("roadmap.html", "paper_map.html", "paper_lens.html"):
        text = (output / name).read_text(encoding="utf-8")
        assert attack not in text
        payload = text.split('<script type="application/json" id="fields-study-flow-data">', 1)[1].split("</script>", 1)[0]
        embedded = json.loads(payload)["roadmap"]
        if "page_language" in embedded:
            assert embedded.pop("page_language") == "en"
        assert embedded == read_plan(output)
        assert "<noscript>" in text
        assert "Saved model explanation" in payload
