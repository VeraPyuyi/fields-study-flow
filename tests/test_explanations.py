import copy
import json

import pytest

from fields_study_flow.explanations import explain_segment, prepare_explanations


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    for name in ("ENABLED", "BASE_URL", "MODEL", "API_KEY"):
        monkeypatch.delenv("FIELDS_STUDY_FLOW_LLM_" + name, raising=False)


@pytest.fixture
def context():
    return {
        "schema_version": 1, "bundle_id": "bundle", "snapshot_id": "snapshot",
        "sources": [{"id": "paper", "kind": "paper", "title": "Attention",
                     "fingerprint": "v1", "local_path": "C:/private/paper.pdf"}],
        "anchors": [
            {"id": "a1", "source_id": "paper", "locator": {"page": 2},
             "snippet": "Self-attention uses 8 heads to compare tokens.", "locator_status": "valid"},
            {"id": "a2", "source_id": "paper", "locator": {"page": 3},
             "snippet": "Diffusion removes noise over 50 steps.", "locator_status": "valid"},
        ],
        "claims": [
            {"id": "c1", "kind": "methodology", "statement": "Attention method",
             "anchor_ids": ["a1"], "evidence_status": "located"},
            {"id": "c2", "kind": "methodology", "statement": "Diffusion method",
             "anchor_ids": ["a2"], "evidence_status": "located"},
        ],
    }


@pytest.fixture
def enabled(monkeypatch):
    for key, value in {"ENABLED": "true", "BASE_URL": "https://example.invalid/v1",
                       "MODEL": "user-model", "API_KEY": "private-test-key"}.items():
        monkeypatch.setenv("FIELDS_STUDY_FLOW_LLM_" + key, value)


def response(context):
    return {"items": [
        {"claim_id": claim["id"], "plain_meaning": anchor["snippet"],
         "why_it_matters": "Read this excerpt before interpreting the method.",
         "method_note": None, "anchor_ids": [anchor["id"]]}
        for claim, anchor in zip(context["claims"], context["anchors"])
    ]}


def test_local_is_excerpt_specific_honest_and_never_calls_provider(context, enabled):
    def forbidden(_payload):
        pytest.fail("local must not invoke a provider")
    before = copy.deepcopy(context)
    result = prepare_explanations(context, provider_mode="local", provider=forbidden)
    assert result["mode"] == "local" and result["status"] == "ready"
    first, second = result["items"]
    assert "Self-attention" in first["plain_meaning"]
    assert "Diffusion" in second["plain_meaning"]
    assert first["why_it_matters"] != second["why_it_matters"]
    assert "自注意力" in first["method_note"]
    assert "扩散" not in first["method_note"]
    assert "全文翻译" in first["plain_meaning"]
    assert all(item["review_status"] == "unreviewed" for item in result["items"])
    assert all("PDDL" not in item["plain_meaning"] for item in result["items"])
    assert "C:/private" not in json.dumps(result)
    assert context == before


def test_english_local_retains_actual_snippet(context):
    item = prepare_explanations(context, language="en")["items"][0]
    assert context["anchors"][0]["snippet"] in item["plain_meaning"]
    assert "translation" in item["plain_meaning"]
    assert item["evidence_refs"][0] == {
        "anchor_id": "a1", "source_id": "paper", "locator": {"page": 2},
        "snippet": context["anchors"][0]["snippet"],
    }


def test_configured_provider_receives_only_allowed_input_chunks(context, enabled):
    seen = []
    def provider(payload):
        seen.append(payload)
        return response(context)
    result = prepare_explanations(context, provider=provider)
    assert result["mode"] == "llm" and result["status"] == "ready"
    assert result["items"][0]["review_status"] == "unreviewed"
    assert seen[0]["language"] == "zh-CN"
    assert {a["id"] for a in seen[0]["anchors"]} == {"a1", "a2"}
    assert "private-test-key" not in json.dumps(seen)
    assert "C:/private" not in json.dumps(seen)
    assert "title" not in json.dumps(seen)


@pytest.mark.parametrize("mutation", ["unknown_anchor", "cross_claim_anchor", "number", "percent",
    "reference_snippet", "reference_locator", "reference_source", "empty_anchors", "missing_claim",
    "duplicate_claim", "unknown_field", "script", "path", "secret", "unmarked_example"])
def test_rejects_unsafe_or_ungrounded_responses(context, enabled, mutation):
    data = response(context)
    item = data["items"][0]
    if mutation == "unknown_anchor":
        item["anchor_ids"] = ["made-up"]
    elif mutation == "cross_claim_anchor":
        item["anchor_ids"] = ["a2"]
    elif mutation == "number":
        item["plain_meaning"] = "There are 9 heads."
    elif mutation == "percent":
        item["plain_meaning"] = "Accuracy is 8%."
    elif mutation.startswith("reference_"):
        ref = {"anchor_id": "a1", "source_id": "paper", "locator": {"page": 2},
               "snippet": context["anchors"][0]["snippet"]}
        ref[{"reference_snippet": "snippet", "reference_locator": "locator",
             "reference_source": "source_id"}[mutation]] = "invented"
        item["evidence_refs"] = [ref]
    elif mutation == "empty_anchors":
        item["anchor_ids"] = []
    elif mutation == "missing_claim":
        data["items"].pop()
    elif mutation == "duplicate_claim":
        data["items"].append(copy.deepcopy(item))
    elif mutation == "unknown_field":
        item["verified"] = True
    elif mutation == "script":
        item["plain_meaning"] = "<script>alert('bad')</script>"
    elif mutation == "path":
        item["method_note"] = "Read C:\\private\\results.json"
    elif mutation == "secret":
        item["plain_meaning"] = "private-test-key"
    else:
        item["example"] = {"text": "Imagine 99 tokens."}
    result = prepare_explanations(context, provider=lambda _p: data)
    assert result["mode"] == "local" and result["status"] == "fallback"
    assert result["warnings"] == ["provider_response_rejected"]
    assert "private-test-key" not in json.dumps(result)


def test_numbers_are_grounded_in_cited_snippets_not_statement_or_other_claim(context, enabled):
    context["claims"][0]["statement"] = "99 heads"
    for number in ("50", "99", "8.0", "+8", "8e0"):
        data = response(context)
        data["items"][0]["plain_meaning"] = f"The result was {number}."
        assert prepare_explanations(context, provider=lambda _p: data)["status"] == "fallback"


def test_marked_educational_example_may_have_new_numbers(context, enabled):
    data = response(context)
    data["items"][0]["example"] = {"kind": "educational", "text": "Imagine 99 tokens, not a paper result."}
    result = prepare_explanations(context, provider=lambda _p: data)
    assert result["mode"] == "llm"
    assert result["items"][0]["example"]["kind"] == "educational"


@pytest.mark.parametrize("damage", ["stale", "missing", "locator", "source"])
def test_invalid_source_locators_are_not_sent_or_cited(context, enabled, damage):
    if damage in {"stale", "missing"}:
        context["anchors"][0]["locator_status"] = damage
    elif damage == "locator":
        context["anchors"][0]["locator"] = {"page": -1}
    else:
        context["anchors"][0]["source_id"] = "absent"
    def provider(payload):
        assert "a1" not in {a["id"] for a in payload["anchors"]}
        assert "c1" not in {c["id"] for c in payload["claims"]}
        return {"items": response(context)["items"][1:]}
    result = prepare_explanations(context, provider=provider)
    assert result["items"][0]["anchor_ids"] == []
    assert result["items"][0]["evidence_refs"] == []
    assert "evidence_unavailable" in result["warnings"]


def test_segment_projection_matches_exact_text_and_never_reuses_whole_claim(context, enabled):
    segment = {"id": "seg", "original_text": context["anchors"][1]["snippet"]}
    result = explain_segment(segment, context, "en")
    assert result["segment_id"] == "seg" and result["anchor_ids"] == ["a2"]
    assert "Self-attention" not in result["plain_meaning"]
    llm = prepare_explanations(context, language="en", provider=lambda _p: response(context))
    projected = explain_segment(segment, context, "en", items=llm)
    assert projected["plain_meaning"] == llm["items"][1]["plain_meaning"]
    unknown = explain_segment({"id": "unknown", "original_text": "Unrelated new paragraph."}, context, "en", items=llm)
    assert unknown["anchor_ids"] == [] and unknown["evidence_refs"] == []
    assert "Unrelated new paragraph." in unknown["plain_meaning"]
    assert "Diffusion" not in unknown["plain_meaning"]


def test_segment_explicit_wrong_anchor_and_malformed_supplied_items_cannot_bypass_validation(context):
    segment = {"id": "seg", "original_text": context["anchors"][1]["snippet"], "anchor_ids": ["a1"]}
    assert explain_segment(segment, context, "en")["anchor_ids"] == []
    bad = response(context)
    bad["items"][1]["plain_meaning"] = "Fabricated 99 steps."
    segment["anchor_ids"] = ["a2"]
    assert "99" not in explain_segment(segment, context, "en", items=bad)["plain_meaning"]


@pytest.mark.parametrize("damage", ["duplicate_anchor", "duplicate_claim", "wrong_schema"])
def test_malformed_context_raises_value_error(context, damage):
    if damage == "duplicate_anchor":
        context["anchors"].append(copy.deepcopy(context["anchors"][0]))
    elif damage == "duplicate_claim":
        context["claims"].append(copy.deepcopy(context["claims"][0]))
    else:
        context["schema_version"] = 999
    with pytest.raises(ValueError):
        prepare_explanations(context)


def test_provider_payload_is_bounded_and_never_reads_source_files(context, enabled):
    context["anchors"][0]["snippet"] = "private input " * 10000
    seen = []
    def provider(payload):
        seen.append(payload)
        return {"items": response(context)["items"][1:]}
    result = prepare_explanations(context, provider=provider)
    assert len(json.dumps(seen)) < 50000
    assert "provider_input_limited" in result["warnings"]
    assert result["items"][0]["anchor_ids"] == ["a1"]


def test_exact_reference_check_rejects_float_locator(context, enabled):
    data = response(context)
    data["items"][0]["evidence_refs"] = [{"anchor_id": "a1", "source_id": "paper",
        "snippet": context["anchors"][0]["snippet"], "locator": {"page": 2.0}}]
    assert prepare_explanations(context, provider=lambda _p: data)["status"] == "fallback"


def test_unhashable_source_id_is_treated_as_unavailable(context):
    context["anchors"][0]["source_id"] = []
    assert prepare_explanations(context)["items"][0]["anchor_ids"] == []


def test_malformed_cached_segment_anchor_ids_cannot_crash_projection(context):
    segment = {"id": "seg", "original_text": context["anchors"][0]["snippet"]}
    data = response(context)
    data["items"][0]["anchor_ids"] = [{}]
    assert explain_segment(segment, context, "en", items=data)["anchor_ids"] == ["a1"]


def test_segment_source_and_locator_disambiguate_identical_excerpts(context):
    context["anchors"][1]["snippet"] = context["anchors"][0]["snippet"]
    segment = {"id": "seg", "original_text": context["anchors"][0]["snippet"],
               "source_id": "paper", "page": 3}
    assert explain_segment(segment, context, "en")["anchor_ids"] == ["a2"]


def test_segment_supplied_claim_item_must_match_complete_paragraph(context):
    context["anchors"][0]["snippet"] = "Self-attention compares tokens. A second sentence gives its context."
    segment = {"id": "seg", "original_text": "Self-attention compares tokens."}
    result = explain_segment(segment, context, "en", items=response(context))
    assert "second sentence" not in result["plain_meaning"]
    assert result["anchor_ids"] == []


def test_segment_accepts_claim_keyed_lookup_and_remains_unreviewed(context):
    row = response(context)["items"][0]
    row["review_status"] = "accepted"
    segment = {"id": "seg", "original_text": context["anchors"][0]["snippet"]}
    result = explain_segment(segment, context, "en", items={"c1": row})
    assert result["plain_meaning"] == row["plain_meaning"]
    assert result["review_status"] == "unreviewed"


def test_no_terms_when_source_has_no_technical_terms(context):
    context["anchors"][0]["snippet"] = "Participants completed the task after reading the instructions."
    result = prepare_explanations(context)["items"][0]
    assert result["method_note"] is None
    assert "attention" not in result["plain_meaning"].lower()


def test_payload_file_and_chunk_budgets(context, enabled):
    context["sources"] = [{"id": f"s{i}"} for i in range(70)]
    context["anchors"] = [{"id": f"a{i}", "source_id": f"s{i}", "locator": {"page": 1},
        "snippet": "A short excerpt.", "locator_status": "valid"} for i in range(70)]
    context["claims"] = [{"id": f"c{i}", "kind": "background", "anchor_ids": [f"a{i}"]} for i in range(70)]
    seen = []
    def provider(payload):
        seen.append(payload)
        return {"items": [{"claim_id": c["id"], "plain_meaning": "A short excerpt.",
                          "why_it_matters": "Read its context.", "anchor_ids": c["anchor_ids"]} for c in payload["claims"]]}
    result = prepare_explanations(context, provider=provider)
    assert len({a["source_id"] for a in seen[0]["anchors"]}) <= 16
    assert len(seen[0]["anchors"]) <= 64
    assert len(result["items"]) == 70
    assert result["warnings"] == ["provider_input_limited"]


@pytest.mark.parametrize("locator", [{"line_start": 2, "line_end": 4}, {"cell_id": "cell-1"},
    {"json_pointer": "/settings/heads"}, {"row": 3, "column": "value"}, {"section": "Method"}])
def test_supported_locator_forms_preserve_exact_references(context, locator):
    context["anchors"][0]["locator"] = locator
    assert prepare_explanations(context)["items"][0]["evidence_refs"][0]["locator"] == locator


def test_local_secret_and_absolute_path_snippets_not_exported(context, enabled):
    for text in ("private-test-key", "Open C:/private/paper.pdf", "Read /home/private/results.json"):
        context["anchors"][0]["snippet"] = text
        result = prepare_explanations(context, provider_mode="local")
        assert result["items"][0]["anchor_ids"] == []
        assert text not in json.dumps(result)


def test_bilingual_local_has_explicit_english_secondary(context, enabled):
    result = prepare_explanations(context, language="bilingual", offline=True,
                                  provider=lambda _p: pytest.fail("offline bilingual network"))
    first = result["items"][0]
    assert result["language"] == "bilingual" and result["mode"] == "local"
    assert first["language"] == "zh-CN"
    assert "摘录导读" in first["plain_meaning"]
    english = first["translations"]["en"]
    assert english["language"] == "en" and "Excerpt orientation" in english["plain_meaning"]
    assert english["anchor_ids"] == first["anchor_ids"]
    assert english["review_status"] == "unreviewed"


def test_bilingual_generation_and_cache_are_per_language(context, enabled, tmp_path):
    calls = []
    def provider(payload):
        calls.append(payload["language"])
        data = response(context)
        if payload["language"] == "zh-CN":
            for item in data["items"]:
                item["plain_meaning"] = "这段摘录说明方法的具体条件。"
                item["why_it_matters"] = "需要结合原文理解其适用范围。"
        return data
    result = prepare_explanations(context, language="bilingual", provider=provider, cache_dir=tmp_path)
    assert calls == ["zh-CN", "en"]
    assert result["language_modes"] == {"zh-CN": "llm", "en": "llm"}
    assert prepare_explanations(context, language="bilingual", provider=provider, cache_dir=tmp_path) == result
    assert calls == ["zh-CN", "en"]
    segment = {"id": "seg", "original_text": context["anchors"][0]["snippet"]}
    projected = explain_segment(segment, context, "bilingual", items=result)
    assert projected["plain_meaning"] == result["items"][0]["plain_meaning"]
    assert projected["translations"]["en"]["plain_meaning"] == result["items"][0]["translations"]["en"]["plain_meaning"]
    assert calls == ["zh-CN", "en"]
    english_only = explain_segment(segment, context, "en", items=result)
    assert english_only["plain_meaning"] == result["items"][0]["translations"]["en"]["plain_meaning"]


def test_bilingual_partial_provider_failure_does_not_mislabel_secondary(context, enabled):
    def provider(payload):
        if payload["language"] == "en":
            raise RuntimeError("private-test-key")
        return response(context)
    result = prepare_explanations(context, language="bilingual", provider=provider)
    assert result["status"] == "fallback" and result["mode"] == "mixed"
    assert result["language_modes"] == {"zh-CN": "llm", "en": "local"}
    assert "Excerpt orientation" in result["items"][0]["translations"]["en"]["plain_meaning"]
    assert "private-test-key" not in json.dumps(result)


def test_english_projection_does_not_reuse_zh_primary_without_secondary(context):
    row = response(context)["items"][0]
    row.update(language="zh-CN", plain_meaning="此段描述了自注意力。")
    segment = {"id": "seg", "original_text": context["anchors"][0]["snippet"]}
    result = explain_segment(segment, context, "en", items={"c1": row})
    assert "Excerpt orientation" in result["plain_meaning"]


def test_numeric_formatting_cannot_sneak_in_percent_or_thousands(context, enabled):
    for number in ("8 %", "8％", "1,008", "−8"):
        data = response(context)
        data["items"][0]["plain_meaning"] = f"Reported accuracy is {number}."
        assert prepare_explanations(context, provider=lambda _p: data)["status"] == "fallback"


def test_response_with_unpaired_surrogate_rejected(context, enabled, tmp_path):
    data = response(context)
    data["items"][0]["plain_meaning"] = "Bad \ud800 text"
    assert prepare_explanations(context, provider=lambda _p: data, cache_dir=tmp_path)["status"] == "fallback"


def test_missing_source_availability_cannot_be_cited(context):
    context["sources"][0]["availability"] = "missing"
    result = prepare_explanations(context)
    assert all(not item["anchor_ids"] for item in result["items"])


def test_recognizable_secret_fields_not_sent_or_exported(context, enabled):
    context["anchors"][0].update(locator={"json_pointer": "/token"}, snippet='"DO_NOT_PUBLISH"')
    context["anchors"][1]["snippet"] = 'api_key = "ANOTHER_PRIVATE_VALUE"'
    result = prepare_explanations(context, provider=lambda _p: pytest.fail("no safe input remains"))
    serialized = json.dumps(result)
    assert "DO_NOT_PUBLISH" not in serialized
    assert "ANOTHER_PRIVATE_VALUE" not in serialized
    assert all(not item["anchor_ids"] for item in result["items"])


def test_segment_text_secret_not_exported_even_without_source(context):
    result = explain_segment({"id": "segment", "original_text": "Authorization: Bearer PRIVATE_VALUE"}, context, "en")
    assert "PRIVATE_VALUE" not in json.dumps(result)
