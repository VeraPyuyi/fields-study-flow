import copy
import json

import httpx
import pytest

from fields_study_flow.cli import _planner_options, build_parser
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.mcp_tools import buildRoadmap
from fields_study_flow.roadmap import build_roadmap
from fields_study_flow.resource_bundle import attach_study_bundle, bundle_study_resources
from fields_study_flow.workbench import project_prepared_views


def target():
    return Resource(title="Attention Is All You Need", url="https://arxiv.org/abs/1706.03762", source="arxiv", type="paper",
                    concepts=["attention"], critical_path_role="target-paper", metadata={"target_paper": True, "paper_metadata": {
                        "title": "Attention Is All You Need", "abstract_snippet": "The Transformer uses attention without recurrence.",
                        "method_hints": ["Multi-head attention compares token representations."],
                        "experiment_hints": ["The evaluation compares translation quality."],
                        "limitations_hints": [], "concepts": ["attention"]}})


def test_paper_parser_supports_context_and_explicit_outcome_wins():
    args = build_parser().parse_args(["paper", "--url", "1706.03762", "--offline", "--known-topic", "attention",
                                    "--level", "linear-algebra=familiar", "--preset", "fast-presentation",
                                    "--learning-outcome", "extend", "--paper-map-provider", "llm", "--explanation-provider", "local"])
    assert _planner_options(args)["learning_outcome"] == "extend"
    assert args.known_topic == ["attention"] and args.offline
    assert args.explanation_provider == "local"


def test_generation_context_and_export_link_binding_do_not_reexplain(tmp_path, monkeypatch):
    from fields_study_flow.research_context import validate_research_context

    plan = build_roadmap(LearnerProfile(goal="understand attention", target_kind="paper"), [target()], offline=True)
    context = plan["research_context"]
    assert validate_research_context(context)["valid"]
    assert context["explanations"]["mode"] == "local"
    assert context["learning_steps"]
    monkeypatch.setattr("fields_study_flow.explanations.prepare_explanations", lambda *a, **kw: (_ for _ in ()).throw(AssertionError("re-explained")))
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "paper.pdf").write_bytes(b"demo")
    manifest = {"resource_dir": str(assets), "resources": [{"title": target().title, "url": target().url,
                  "status": "copied", "file": "paper.pdf"}], "summary": {"copied": 1}}
    bound = attach_study_bundle(plan, manifest, report_dir=tmp_path / "reports")
    assert bound["paper_map"]["target"]["local_href"] == "../assets/paper.pdf"
    assert bound["paper_lens"]["target_papers"][0]["local_href"] == "../assets/paper.pdf"
    paper_source = next(source for source in bound["research_context"]["sources"] if source.get("url") == target().url)
    assert paper_source["local_href"] == "../assets/paper.pdf"
    assert bound["research_context"]["explanations"] == context["explanations"]
    assert bound["research_context"]["snapshot_id"] == context["snapshot_id"]
    assert str(tmp_path) not in json.dumps(bound)


def test_offline_bundle_never_constructs_or_uses_network_client(tmp_path, monkeypatch):
    monkeypatch.setattr("httpx.Client", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network client created")))
    resource = target()
    local = tmp_path / "notes.md"
    local.write_text("Local attention notes")
    local_resource = Resource(title="Notes", url="local://notes", source="local-library", type="notes", local_path=str(local))
    manifest = bundle_study_resources(tmp_path / "assets", [resource, local_resource], {}, offline=True)
    remote, copied = manifest["resources"]
    assert remote["status"] == "link-only" and remote["reason"] == "offline_network_disabled"
    assert copied["status"] == "copied"


@pytest.fixture
def prepared_projection():
    text = "Self-attention compares token representations before combining their values."
    locator = {"page": 2, "section": "Method"}
    reference = {"anchor_id": "paper-anchor", "source_id": "paper-source", "locator": locator, "snippet": text}
    return {
        "profile": {"output_language": "en"},
        "paper_map": {"output_language": "en", "target": {"title": target().title, "url": target().url},
                      "nodes": [{"id": "core-methodology", "role": "core", "kind": "methodology",
                                 "plain_explanation": "Local map orientation."}]},
        "paper_lens": {"output_language": "en", "target_papers": [{"title": target().title, "url": target().url}],
                       "segments": [{"id": "segment-method", "original_text": text, "section_kind": "method", "page": 2}],
                       "inline_explanations": [{"segment_id": "segment-method", "plain_meaning": "Local lens orientation."}]},
        "research_context": {
            "schema_version": 1, "bundle_id": "bundle", "snapshot_id": "snapshot",
            "primary_source_ids": ["paper-source"],
            "sources": [
                {"id": "paper-source", "kind": "paper", "title": target().title, "url": target().url, "fingerprint": "paper-version"},
                {"id": "support-source", "kind": "paper", "title": "Supporting paper", "url": "https://example.org/support", "fingerprint": "support-version"},
            ],
            "anchors": [
                {"id": "support-anchor", "source_id": "support-source", "locator": {"page": 9}, "snippet": text, "locator_status": "valid"},
                {"id": "paper-anchor", "source_id": "paper-source", "locator": locator, "snippet": text, "locator_status": "valid"},
            ],
            "claims": [
                {"id": "support-claim", "kind": "methodology", "statement": text, "anchor_ids": ["support-anchor"], "evidence_status": "located"},
                {"id": "paper-claim", "kind": "methodology", "statement": text, "anchor_ids": ["paper-anchor"], "evidence_status": "located"},
            ],
            "relations": [], "learning_steps": [],
            "explanations": {"mode": "llm", "language": "en", "status": "ready", "warnings": [], "items": [
                {"claim_id": "support-claim", "kind": "methodology", "plain_meaning": "Unrelated supporting paper interpretation.",
                 "why_it_matters": "Supporting source only.", "method_note": None, "anchor_ids": ["support-anchor"],
                 "evidence_refs": [{"anchor_id": "support-anchor", "source_id": "support-source", "locator": {"page": 9}, "snippet": text}], "review_status": "unreviewed"},
                {"claim_id": "paper-claim", "kind": "methodology", "plain_meaning": "Saved model interpretation of self-attention.",
                 "why_it_matters": "The supplied excerpt specifies token interactions.", "method_note": "Compare the stated token representations.",
                 "anchor_ids": ["paper-anchor"], "evidence_refs": [reference], "review_status": "unreviewed"},
            ]},
        },
    }


def test_primary_source_wins_over_same_text_in_supporting_paper(prepared_projection):
    before = copy.deepcopy(prepared_projection)
    projected = project_prepared_views(prepared_projection)
    node = projected["paper_map"]["nodes"][0]
    segment = projected["paper_lens"]["segments"][0]
    explanation = projected["paper_lens"]["inline_explanations"][0]
    assert node["claim_id"] == "paper-claim"
    assert node["claim_ids"] == ["paper-claim"]
    assert node["anchor_ids"] == segment["anchor_ids"] == explanation["anchor_ids"] == ["paper-anchor"]
    assert segment["evidence_status"] == "located"
    assert "Unrelated supporting" not in json.dumps(projected["paper_map"])
    assert prepared_projection == before


@pytest.mark.parametrize("mutation", ["negation", "reordered_tokens", "stale", "unrelated"])
def test_similar_words_or_foreign_exact_text_are_not_located_paper_evidence(prepared_projection, mutation):
    from fields_study_flow.workbench import _bind_segment_anchors

    anchor = prepared_projection["research_context"]["anchors"][1]
    if mutation == "negation":
        anchor["snippet"] = "Self-attention never compares token representations before combining their values."
    elif mutation == "reordered_tokens":
        anchor["snippet"] = "Before combining values their representations token compares self-attention."
    elif mutation == "stale":
        anchor["locator_status"] = "stale"
    else:
        anchor["snippet"] = "The experiment measures image quality under a different condition."
    _bind_segment_anchors(prepared_projection)
    segment = prepared_projection["paper_lens"]["segments"][0]
    assert segment["anchor_ids"] == []
    assert segment["evidence_status"] == "missing"
    assert prepared_projection["paper_lens"]["inline_explanations"][0]["anchor_ids"] == []


@pytest.mark.parametrize("extra_text", ["", " A second mechanism uses positional encodings to represent sequence order."])
def test_saved_model_projection_is_excerpt_aware_and_never_calls_provider(prepared_projection, extra_text, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Projection must reuse prepared content without provider or network calls")

    monkeypatch.setattr("fields_study_flow.explanations.prepare_explanations", forbidden)
    monkeypatch.setattr("fields_study_flow.explanation_provider.request_explanations", forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)
    prepared_projection["paper_lens"]["segments"][0]["original_text"] += extra_text
    saved = copy.deepcopy(prepared_projection["research_context"]["explanations"])
    projected = project_prepared_views(prepared_projection)
    explanation = projected["paper_lens"]["inline_explanations"][0]
    item = saved["items"][1]
    assert projected["paper_map"]["nodes"][0]["plain_explanation"] == item["plain_meaning"]
    assert explanation["plain_meaning"].startswith(item["plain_meaning"])
    assert explanation["why_it_matters"] == item["why_it_matters"]
    assert explanation["method_note"] == item["method_note"]
    assert explanation["evidence_refs"] == item["evidence_refs"]
    assert explanation["interpretation_scope"] == ("excerpt" if extra_text else "paragraph")
    if extra_text:
        assert "only the located excerpt" in explanation["plain_meaning"]
    assert projected["research_context"]["explanations"] == saved


def test_other_language_lens_does_not_relabel_saved_model_interpretation(prepared_projection):
    prepared_projection["paper_lens"]["output_language"] = "zh-CN"
    original = prepared_projection["paper_lens"]["inline_explanations"][0]["plain_meaning"]
    projected = project_prepared_views(prepared_projection)
    assert projected["paper_lens"]["inline_explanations"][0]["plain_meaning"] == original
    assert projected["research_context"]["explanations"]["language"] == "en"


@pytest.mark.parametrize("entrypoint", ["python", "mcp"])
@pytest.mark.parametrize("mutation", ["schema", "unknown_source", "unknown_anchor", "duplicate_source"])
def test_invalid_supplied_context_is_rejected_before_explanations(prepared_projection, entrypoint, mutation, monkeypatch):
    context = copy.deepcopy(prepared_projection["research_context"])
    if mutation == "schema":
        context["schema_version"] = 999
    elif mutation == "unknown_source":
        context["anchors"][0]["source_id"] = "absent-source"
    elif mutation == "unknown_anchor":
        context["claims"][0]["anchor_ids"] = ["absent-anchor"]
    else:
        context["sources"].append(copy.deepcopy(context["sources"][0]))
    def forbidden(*args, **kwargs):
        pytest.fail("Invalid context must be rejected before explaining")

    monkeypatch.setattr("fields_study_flow.explanations.prepare_explanations", forbidden)
    profile = LearnerProfile(goal="understand attention", target_kind="paper", output_language="en")
    with pytest.raises(ValueError, match="researchContext|context|schema|references"):
        if entrypoint == "python":
            build_roadmap(profile, [target()], offline=True, research_context=context)
        else:
            buildRoadmap(profile.goal, profile.to_dict(), [target().to_dict()], ragMode="off",
                         targetKind="paper", outputLanguage="en", offline=True, researchContext=context)


def test_bundle_binding_never_replaces_explicit_url_with_same_title_resource(prepared_projection):
    from fields_study_flow.workbench import bind_workbench_links

    prepared_projection["study_bundle"] = {"resources": [{"title": target().title,
        "url": "https://example.org/wrong-paper", "status": "copied", "local_href": "assets/wrong.pdf"}]}
    bound = bind_workbench_links(prepared_projection)
    assert not bound["paper_map"]["target"].get("local_href")
    assert not bound["paper_lens"]["target_papers"][0].get("local_href")
    assert all(not source.get("local_href") for source in bound["research_context"]["sources"])


@pytest.mark.parametrize("href", [
    "C:/private/paper.pdf", r"\\private-server\share\paper.pdf", "/mnt/private/paper.pdf",
    "https://example.org/paper.pdf", "//example.org/paper.pdf", "javascript:alert(1)", "file:///C:/private/paper.pdf",
])
def test_bundle_binding_rejects_nonportable_or_active_hrefs(prepared_projection, href):
    from fields_study_flow.workbench import bind_workbench_links

    prepared_projection["study_bundle"] = {"resources": [{"title": target().title,
        "url": target().url, "status": "copied", "local_href": href}]}
    bound = bind_workbench_links(prepared_projection)
    assert not bound["paper_map"]["target"].get("local_href")
    assert not bound["paper_lens"]["target_papers"][0].get("local_href")
    assert not bound["research_context"]["sources"][0].get("local_href")


@pytest.mark.parametrize("status", ["failed", "link-only", "queued", "unknown"])
def test_bundle_binding_rejects_unsuccessful_status_even_with_relative_href(prepared_projection, status):
    from fields_study_flow.workbench import bind_workbench_links

    prepared_projection["study_bundle"] = {"resources": [{"title": target().title,
        "url": target().url, "status": status, "local_href": "assets/paper.pdf"}]}
    bound = bind_workbench_links(prepared_projection)
    assert not bound["paper_map"]["target"].get("local_href")
    assert not bound["paper_lens"]["target_papers"][0].get("local_href")
    assert not bound["research_context"]["sources"][0].get("local_href")


@pytest.mark.parametrize("status", ["copied", "downloaded", "snapshotted", "generated"])
@pytest.mark.parametrize("href", ["assets/paper.pdf", "../study-assets/paper.pdf"])
def test_successful_bundle_binds_the_same_portable_href_across_all_views(prepared_projection, status, href):
    from fields_study_flow.workbench import bind_workbench_links

    prepared_projection["study_bundle"] = {"resources": [{"title": target().title,
        "url": target().url, "status": status, "file": "paper.pdf", "local_href": href}]}
    saved = copy.deepcopy(prepared_projection["research_context"]["explanations"])
    bound = bind_workbench_links(prepared_projection)
    assert bound["paper_map"]["target"]["local_href"] == href
    assert bound["paper_lens"]["target_papers"][0]["local_href"] == href
    assert bound["research_context"]["sources"][0]["local_href"] == href
    assert bound["research_context"]["explanations"] == saved


def test_href_only_legacy_bundle_is_bound_or_rejected_consistently_across_views(prepared_projection):
    from fields_study_flow.workbench import bind_workbench_links

    prepared_projection["study_bundle"] = {"resources": [{"title": target().title,
        "url": target().url, "status": "copied", "local_href": "../study-assets/paper.pdf"}]}
    bound = bind_workbench_links(prepared_projection)
    hrefs = [bound["paper_map"]["target"].get("local_href"),
             bound["paper_lens"]["target_papers"][0].get("local_href"),
             bound["research_context"]["sources"][0].get("local_href")]
    assert len(set(hrefs)) == 1, "An incomplete legacy manifest may be rejected, but page links and source links must agree"


def test_missing_bundle_preserves_saved_hrefs_and_model_snapshot(prepared_projection):
    from fields_study_flow.workbench import bind_workbench_links

    href = "../study-assets/saved-paper.pdf"
    prepared_projection["paper_map"]["target"]["local_href"] = href
    prepared_projection["paper_lens"]["target_papers"][0]["local_href"] = href
    prepared_projection["research_context"]["sources"][0]["local_href"] = href
    before = copy.deepcopy(prepared_projection)
    assert bind_workbench_links(prepared_projection) == before
    assert prepared_projection == before
