import json
from pathlib import Path

import pytest

from fields_study_flow.models import Resource
from fields_study_flow.project_evidence import extract_project_evidence


FIXTURE = Path(__file__).parent / "fixtures" / "research_workbench" / "toy_project"


def resource(path, **metadata):
    return Resource(title=path.name, url="", source="local-library", type="code",
                    local_path=str(path), metadata=metadata)


def test_toy_project_locators_and_demonstration_coverage():
    result = extract_project_evidence([resource(FIXTURE)])
    assert {s["kind"] for s in result["sources"]} == {"readme", "code", "config", "result", "notebook"}
    locators = [a["locator"] for a in result["anchors"]]
    assert any(l.get("symbol") == "ToyPlanner.transition" and l["line_start"] == 12 for l in locators)
    assert any(l.get("cell_id") == "toy-transition" for l in locators)
    assert any(l.get("json_pointer") == "/experiment/seed" for l in locators)
    assert any(l.get("json_pointer") == "/metrics/toy_valid_actions" for l in locators)
    assert any(l.get("row") == 2 and l.get("column") == "toy_valid_actions" for l in locators)
    assert all(len(a["snippet"]) <= 300 for a in result["anchors"])
    assert result["coverage"]["processed_files"] == 6
    assert "demonstration" in json.dumps(result)


def test_only_explicit_file_not_neighbor_and_never_execute(tmp_path):
    selected = tmp_path / "selected.py"
    selected.write_text("raise RuntimeError('must never run')\ndef selected():\n    pass\n")
    (tmp_path / "neighbor.py").write_text("def private_neighbor(): pass")
    result = extract_project_evidence([resource(selected)])
    assert len(result["sources"]) == 1
    assert result["anchors"][0]["locator"]["symbol"] == "selected"


def test_root_escape_and_symlink_parent_are_not_read(tmp_path):
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("def forbidden(): pass")
    result = extract_project_evidence([resource(outside, project_root=str(root))])
    assert not result["anchors"]
    assert result["coverage"]["skipped"][0]["reason"] == "outside_root"
    link = root / "linked"
    try:
        link.symlink_to(tmp_path, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks is unavailable on this host")
    result = extract_project_evidence([resource(link / "outside.py")])
    assert not result["anchors"]
    assert result["coverage"]["skipped"][0]["reason"] == "symlink"


def test_bad_file_does_not_block_other_material(tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{bad")
    good = tmp_path / "okay.py"
    good.write_text("def okay(): pass")
    result = extract_project_evidence([resource(bad), resource(good)])
    assert any(a["locator"].get("symbol") == "okay" for a in result["anchors"])
    assert any(s["reason"] == "parse_error" for s in result["coverage"]["skipped"])


def test_limits_and_unsupported_recorded_without_secret_leak(tmp_path):
    big = tmp_path / "big.py"
    big.write_bytes(b" " * (1024 * 1024 + 1))
    unknown = tmp_path / "binary.bin"
    unknown.write_bytes(b"\x00")
    config = tmp_path / "config.json"
    config.write_text(json.dumps({"api_key": "VERY_PRIVATE_TEST_TOKEN", "path": str(tmp_path / "secret"), "seed": 2}))
    result = extract_project_evidence([resource(big), resource(unknown), resource(config)])
    reasons = {s["reason"] for s in result["coverage"]["skipped"]}
    assert {"size_limit", "unsupported"} <= reasons
    public = json.dumps(result)
    assert "VERY_PRIVATE_TEST_TOKEN" not in public
    assert str(tmp_path).replace("\\", "\\\\") not in public
    many = extract_project_evidence([resource(config, source_id=f"item-{i}") for i in range(70)])
    assert many["coverage"]["truncated"]
    assert len(many["sources"]) <= 64


def test_duplicate_title_identity_and_fingerprint_change(tmp_path):
    a, b = tmp_path / "a.py", tmp_path / "b.py"
    a.write_text("def one(): pass")
    b.write_text("def two(): pass")
    resources = [resource(a), resource(b)]
    for r in resources:
        r.title = "Same title"
    before = extract_project_evidence(resources)
    assert len({s["id"] for s in before["sources"]}) == 2
    a.write_text("def changed(): pass")
    after = extract_project_evidence(resources)
    assert before["sources"][0]["id"] == after["sources"][0]["id"]
    assert before["sources"][0]["fingerprint"] != after["sources"][0]["fingerprint"]
    assert before["sources"][1] == after["sources"][1]


def test_invalid_pdf_metadata_remains_unverified(tmp_path):
    pdf = tmp_path / "paper.pdf"
    pdf.write_bytes(b"not a valid PDF; metadata was already extracted")
    r = resource(pdf, segments=[{"page": 3, "section": "Method", "text": "Extracted method."}],
                 rag={"top_chunks": [{"chunk_id": "rag-only", "snippet": "Unlocated RAG preview"}]})
    result = extract_project_evidence([r])
    assert any(a["locator"].get("page") == 3 and a["locator_status"] == "missing" for a in result["anchors"])
    assert any(a["locator_status"] == "missing" for a in result["anchors"])
    assert any(s["reason"] == "metadata_locator_unverified" for s in result["coverage"]["skipped"])


def write_real_pdf(path, pages):
    from pypdf import PdfWriter
    from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject

    writer = PdfWriter()
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"),
                             NameObject("/Subtype"): NameObject("/Type1"),
                             NameObject("/BaseFont"): NameObject("/Helvetica")})
    for text in pages:
        page = writer.add_blank_page(width=612, height=792)
        page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"):
            DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
        stream = DecodedStreamObject()
        commands = [b"BT /F1 12 Tf 40 740 Td"]
        for line in text.splitlines():
            literal = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            commands.append(f"({literal}) Tj 0 -16 Td".encode("ascii"))
        stream.set_data(b"\n".join([*commands, b"ET"]))
        page[NameObject("/Contents")] = writer._add_object(stream)
    writer.write(path)


def test_real_pdf_has_valid_page_and_paragraph_anchors(tmp_path):
    path = tmp_path / "actual.pdf"
    write_real_pdf(path, ["Background\n" + "Introductory material. " * 20 +
                         "\nMethod\nWe evaluate the model on 80 samples.", "Results\nAccuracy is 75 percent."])
    result = extract_project_evidence([resource(path)])
    assert result["sources"][0]["availability"] == "available"
    assert {a["locator"]["page"] for a in result["anchors"]} == {1, 2}
    assert all(a["locator_status"] == "valid" for a in result["anchors"])
    assert any("We evaluate the model on 80 samples." in a["snippet"] for a in result["anchors"])
    assert result["coverage"]["bytes_read"] == path.stat().st_size


def test_pdf_categories_and_balanced_page_coverage(tmp_path):
    from fields_study_flow.research_context import build_research_context
    path = tmp_path / "actual.pdf"
    write_real_pdf(path, [
        "Background\n" + "The prior literature considers sequential decision making.\n" * 160,
        "Methodology\nOur approach trains a model using logical intermediate states.\n",
        "Experiments\nWe evaluate the model on held-out planning instances.\n",
        "Contributions\nOur contributions include a structured instruction dataset.\n",
        "Limitations\nThis method is limited to the observed planning domains.\n",
    ])
    context = build_research_context({}, [resource(path, target_paper=True)])
    categories = {c["kind"] for c in context["claims"]}
    assert {"methodology", "experiment", "contribution", "limitation"} <= categories
    assert any(a["locator"].get("page") == 5 and a.get("hint_kind") == "limitation" for a in context["anchors"])
    preview_ids = {a["id"] for a in context["anchors"] if a.get("scope") == "page_preview"}
    assert not any(preview_ids.intersection(c["anchor_ids"]) for c in context["claims"])


def test_real_pdf_supplied_snippets_verified_on_actual_page_before_clipping(tmp_path):
    path = tmp_path / "actual.pdf"
    prefix = "Actual observation. " * 20
    write_real_pdf(path, ["Method\n" + prefix + "\nWe use 80 samples.", "Results\nAccuracy is 75 percent."])
    segments = [
        {"page": 1, "section": "Method", "text": "We use 80 samples."},
        {"page": 2, "text": "We use 80 samples."},
        {"page": 99999, "text": "We use 80 samples."},
        {"page": 1, "text": "We use 8"},
        {"page": 1, "text": prefix + "Fabricated 999."},
        {"page": 1, "symbol": "invented", "text": "We use 80 samples."},
        {"page": 1, "section": "Invented", "text": "We use 80 samples."},
    ]
    result = extract_project_evidence([resource(path, segments=segments)])
    assert [a["locator_status"] for a in result["anchors"][-len(segments):]] == ["valid", *["missing"] * 6]


def test_real_pdf_first_twelve_pages_only_and_no_large_pdf_parser(tmp_path, monkeypatch):
    from pypdf import PdfReader

    path = tmp_path / "pages.pdf"
    write_real_pdf(path, [f"Actual page {n}." for n in range(1, 14)])
    result = extract_project_evidence([resource(path, segments=[{"page": 13, "text": "Actual page 13."}])])
    assert {a["locator"]["page"] for a in result["anchors"] if a["locator_status"] == "valid"} == set(range(1, 13))
    assert result["anchors"][-1]["locator_status"] == "missing"
    assert any(s["reason"] == "pdf_page_limit" for s in result["coverage"]["skipped"])
    large = tmp_path / "large.pdf"
    large.write_bytes(b"x" * (1024 * 1024 + 1))
    def never_parse(*args, **kwargs):
        pytest.fail("Oversized PDF reached PdfReader")
    monkeypatch.setattr(PdfReader, "__init__", never_parse)
    bounded = extract_project_evidence([resource(large, segments=[{"page": 2, "text": "Existing hint"}])])
    assert bounded["coverage"]["bytes_read"] == 0
    assert bounded["anchors"][0]["locator_status"] == "missing"


def test_real_pdf_page_text_limit_preserves_truthful_supplied_status(tmp_path, monkeypatch):
    import fields_study_flow.project_evidence as module

    monkeypatch.setattr(module, "MAX_PDF_PAGE_CHARS", 100, raising=False)
    path = tmp_path / "text.pdf"
    write_real_pdf(path, ["Actual text. " * 20 + "Tail must not be verified."])
    result = extract_project_evidence([resource(path, segments=[{"page": 1, "text": "Tail must not be verified."}])])
    assert result["anchors"][-1]["locator_status"] == "missing"
    assert any(s["reason"] == "pdf_text_limit" for s in result["coverage"]["skipped"])


def test_large_pdf_reuses_metadata_without_exceeding_read_limit(tmp_path):
    path = tmp_path / "large.pdf"
    path.write_bytes(b"x" * (1024 * 1024 + 1))
    evidence = extract_project_evidence([resource(path, segments=[{"page": 2, "text": "Already extracted text"}])])
    assert evidence["anchors"][0]["locator"]["page"] == 2
    assert evidence["coverage"]["bytes_read"] == 0
    assert evidence["sources"][0]["fingerprint_scope"] == "metadata_and_stat"
    assert evidence["coverage"]["truncated"]


def test_analyzed_resource_shape_and_relocated_root_stable_ids(tmp_path):
    from fields_study_flow.local_resources import analyze_local_resources
    first, second = tmp_path / "first", tmp_path / "second"
    for root in (first, second):
        root.mkdir()
        (root / "code.py").write_text("def entry(): pass")
    left = analyze_local_resources([str(first / "code.py")], "study")
    right = analyze_local_resources([str(second / "code.py")], "study")
    left[0].metadata["project_root"] = str(first)
    right[0].metadata["project_root"] = str(second)
    a, b = extract_project_evidence(left), extract_project_evidence(right)
    assert a["sources"][0]["id"] == b["sources"][0]["id"]
    assert a["sources"][0]["fingerprint"] == b["sources"][0]["fingerprint"]
    assert a["sources"][0]["resource_id"] == left[0].metadata["local_resource_id"]


def test_yaml_aliases_and_generic_token_are_bounded_and_private(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text("loop: &loop\n  self: *loop\ntoken: NEVER_PUBLISH_THIS_TOKEN\nseed: 1\n")
    result = extract_project_evidence([resource(config)])
    assert "NEVER_PUBLISH_THIS_TOKEN" not in json.dumps(result)
    assert len(result["anchors"]) < 128


def test_unidentified_same_title_resources_not_collapsed():
    resources = [Resource(title="Same", url="", source="supplied", type="paper", metadata={"segments": [{"section": "Method", "text": text}]}) for text in ("One method", "A different method")]
    evidence = extract_project_evidence(resources)
    assert len(evidence["sources"]) == 2
    assert len({s["id"] for s in evidence["sources"]}) == 2
    assert any(i["reason"] == "identity_unavailable" for i in evidence["coverage"]["skipped"])


@pytest.mark.parametrize("text", [
    '{"api_key": "DUMMY_PRIVATE_VALUE"}',
    "{'access_token': 'DUMMY_PRIVATE_VALUE'}",
    '{"password" : "DUMMY_PRIVATE_VALUE"}',
    r'{\"api_key\": \"DUMMY_PRIVATE_VALUE\"}',
    'authorization = "Bearer DUMMY_PRIVATE_VALUE"',
])
def test_quoted_secret_fields_redacted_in_notebook_and_metadata(tmp_path, text):
    path = tmp_path / "notes.ipynb"
    path.write_text(json.dumps({"cells": [{"id": "cell", "source": text}]}), encoding="utf-8")
    r = resource(path, segments=[{"cell_id": "cell", "text": text}])
    result = extract_project_evidence([r])
    assert "DUMMY_PRIVATE_VALUE" not in json.dumps(result)
    assert "[redacted]" in json.dumps(result)


@pytest.mark.parametrize("private_path", [r"\\FAKEHOST\private\paper.pdf", "/opt/research/private.log",
    "/custom/private/paper.pdf", r"D:\research\private\notes.md"])
def test_private_paths_redacted_without_breaking_public_urls(private_path):
    text = f"Read {private_path}; compare https://example.org/papers/method.pdf and assets/method.pdf"
    r = Resource(title=text, url="https://example.org/paper", source="supplied", type="paper",
                 metadata={"segments": [{"page": 1, "section": text, "text": text}]})
    result = extract_project_evidence([r])
    serialized = json.dumps(result)
    assert private_path not in result["sources"][0]["title"]
    assert all(private_path not in a["snippet"] and private_path not in a["locator"].get("section", "") for a in result["anchors"])
    assert "https://example.org/papers/method.pdf" in serialized
    assert "assets/method.pdf" in serialized


def test_json_pointer_keys_cannot_publish_paths_or_secret_values(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({r"C:\FAKE_PRIVATE\config.json": "private-key-value", "token": "PRIVATE_TOKEN", "seed": 2}), encoding="utf-8")
    r = resource(path, segments=[{"json_pointer": "/token", "text": '"PRIVATE_TOKEN"'}])
    result = extract_project_evidence([r])
    serialized = json.dumps(result)
    assert "FAKE_PRIVATE" not in serialized and "PRIVATE_TOKEN" not in serialized
    assert "private-key-value" not in serialized
    assert any(a["locator"].get("json_pointer") == "/seed" for a in result["anchors"])


def test_local_python_metadata_verifies_symbol_range_and_actual_text(tmp_path):
    path = tmp_path / "code.py"
    text = "def actual():\n    return 8\n\ndef other():\n    return 9\n"
    path.write_text(text, encoding="utf-8")
    segments = [
        {"id": "correct", "symbol": "actual", "line_start": 1, "line_end": 2, "text": "return 8"},
        {"id": "symbol", "symbol": "NONEXISTENT_SYMBOL", "text": "return 8"},
        {"id": "line", "line_start": 99999, "line_end": 99999, "text": "return 8"},
        {"id": "wrong-text", "symbol": "actual", "text": "return 9"},
        {"id": "wrong-combination", "symbol": "actual", "line_start": 4, "line_end": 5, "text": "return 9"},
        {"id": "wrong-kind", "page": 1, "text": "return 8"},
    ]
    result = extract_project_evidence([resource(path, segments=segments)])
    supplied = result["anchors"][-len(segments):]
    assert [a["locator_status"] for a in supplied] == ["valid", "missing", "missing", "missing", "missing", "missing"]
    assert any(s["reason"] == "metadata_locator_unverified" for s in result["coverage"]["skipped"])


@pytest.mark.parametrize("suffix,contents,good,bad", [
    (".md", "# Method\nActual observation.\n# Result\nDifferent value.\n",
     {"section": "Method", "text": "Actual observation."}, {"section": "Missing", "text": "Actual observation."}),
    (".json", '{"metrics": {"score": 8}}',
     {"json_pointer": "/metrics/score", "text": "8"}, {"json_pointer": "/metrics/score", "text": "99"}),
    (".yaml", "metrics:\n  score: 8\n",
     {"json_pointer": "/metrics/score", "text": "8"}, {"json_pointer": "/missing", "text": "8"}),
    (".csv", "score,name\n8,actual\n",
     {"row": 2, "column": "score", "text": "8"}, {"row": 99999, "column": "score", "text": "8"}),
    (".ipynb", '{"cells":[{"id":"actual-cell","source":["value = 8"]}]}',
     {"cell_id": "actual-cell", "json_pointer": "/cells/0", "text": "value = 8"},
     {"cell_id": "actual-cell", "json_pointer": "/cells/99", "text": "value = 8"}),
])
def test_local_metadata_locators_checked_against_format(tmp_path, suffix, contents, good, bad):
    path = tmp_path / ("material" + suffix)
    path.write_text(contents, encoding="utf-8")
    result = extract_project_evidence([resource(path, segments=[good, bad])])
    assert [a["locator_status"] for a in result["anchors"][-2:]] == ["valid", "missing"]


def test_long_fabrication_after_snippet_clip_is_not_verified(tmp_path):
    path = tmp_path / "readme.md"
    prefix = "Actual observation. " * 30
    path.write_text("# Method\n" + prefix, encoding="utf-8")
    result = extract_project_evidence([resource(path, segments=[{"section": "Method", "text": prefix + "Fabricated 999."}])])
    assert result["anchors"][-1]["locator_status"] == "missing"


def test_metadata_capped_before_hash_serialization_and_resource_copy(monkeypatch):
    import fields_study_flow.project_evidence as module
    huge = "x" * (9 * 1024 * 1024)
    r = Resource(title="Large metadata", url="https://example.org/large", source="supplied", type="paper",
        metadata={"segments": [{"page": 1, "text": huge}, {"page": 2, "text": "Small retained excerpt."}]})
    original_digest = module._digest
    def bounded_digest(value):
        assert huge not in repr(value), "raw oversized metadata reached hashing"
        return original_digest(value)
    monkeypatch.setattr(module, "_digest", bounded_digest)
    original_to_dict = Resource.to_dict
    def bounded_copy(self, *args, **kwargs):
        assert self is not r, "Resource.to_dict recursively copied original oversized metadata"
        return original_to_dict(self, *args, **kwargs)
    monkeypatch.setattr(Resource, "to_dict", bounded_copy)
    result = extract_project_evidence([r])
    assert result["coverage"]["truncated"]
    assert result["coverage"]["metadata_bytes_retained"] <= result["coverage"]["limits"]["total_metadata_bytes"]
    assert any(s["reason"] == "metadata_limit" for s in result["coverage"]["skipped"])
    assert result["sources"][0]["metadata_truncated"]
    assert any(a["snippet"] == "Small retained excerpt." for a in result["anchors"])
    assert all(a["snippet"] != "x" * 300 for a in result["anchors"])
    assert r.metadata["segments"][0]["text"] is huge


def test_metadata_cycles_entries_and_total_budget_are_bounded(monkeypatch):
    import fields_study_flow.project_evidence as module
    monkeypatch.setattr(module, "MAX_METADATA_BYTES", 2048, raising=False)
    monkeypatch.setattr(module, "MAX_TOTAL_METADATA_BYTES", 3000, raising=False)
    cyclic = {"page": 1, "text": "Safe excerpt."}
    cyclic["cycle"] = cyclic
    resources = [Resource(title=f"Material {i}", url=f"https://example.org/{i}", source="supplied", type="paper",
                 metadata={"segments": [cyclic, *[{"page": n + 2, "text": "retained text " * 20} for n in range(2000)]]}) for i in range(3)]
    result = extract_project_evidence(resources)
    assert len(result["sources"]) == 3
    assert result["coverage"]["truncated"]
    assert result["coverage"]["metadata_bytes_retained"] <= 3000
    assert all(s.get("metadata_truncated") for s in result["sources"])
    assert any(a["snippet"] == "Safe excerpt." for a in result["anchors"])


def test_private_json_pointer_is_not_rewritten_into_fake_valid_location(tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"data": {"score": 8}}', encoding="utf-8")
    result = extract_project_evidence([resource(path, segments=[{"json_pointer": "/data/score", "text": "8"}])])
    assert result["anchors"][-1]["locator"] == {"json_pointer": "/data/score"}
    assert result["anchors"][-1]["locator_status"] == "valid"


@pytest.mark.parametrize("suffix,contents,segment", [
    (".json", '{"score": 18}', {"json_pointer": "/score", "text": "8"}),
    (".csv", "score\n18\n", {"row": 2, "column": "score", "text": "8"}),
    (".py", "def actual():\n    return 80\n", {"symbol": "actual", "text": "return 8"}),
])
def test_numeric_substring_is_not_an_actual_excerpt(tmp_path, suffix, contents, segment):
    path = tmp_path / ("material" + suffix)
    path.write_text(contents, encoding="utf-8")
    assert extract_project_evidence([resource(path, segments=[segment])])["anchors"][-1]["locator_status"] == "missing"


def test_private_local_url_not_published():
    r = Resource(title="Private file", url="local://C:/FAKE_PRIVATE/paper.pdf", source="local-library", type="paper")
    assert "FAKE_PRIVATE" not in json.dumps(extract_project_evidence([r]))


def test_private_locator_labels_omitted_instead_of_rewritten(tmp_path):
    md = tmp_path / "notes.md"
    md.write_text("# Location C:/FAKE_PRIVATE/paper.pdf\nPublic paragraph.\n", encoding="utf-8")
    csv = tmp_path / "result.csv"
    csv.write_text('"C:/FAKE_PRIVATE/data.csv",score\nPRIVATE_CELL_VALUE,8\n', encoding="utf-8")
    result = extract_project_evidence([resource(md), resource(csv)])
    serialized = json.dumps(result)
    assert "FAKE_PRIVATE" not in serialized and "PRIVATE_CELL_VALUE" not in serialized
    md_anchor = next(a for a in result["anchors"] if a["snippet"] == "Public paragraph.")
    assert md_anchor["locator"] == {"line_start": 1, "line_end": 2}
    assert any(a["locator"].get("column") == "score" for a in result["anchors"])


def test_oversized_identity_metadata_disclosed_without_hashing_value():
    r = Resource(title="Identity", url="", source="supplied", type="paper",
                 metadata={"source_id": "x" * 10000, "segments": [{"page": 1, "text": "Safe fragment."}]})
    result = extract_project_evidence([r])
    assert result["sources"][0]["metadata_truncated"]
    assert result["sources"][0]["identity_status"] == "input_order_fallback"


def test_unicode_metadata_budget_is_utf8_serializable_and_bounded(monkeypatch):
    import fields_study_flow.project_evidence as module
    monkeypatch.setattr(module, "MAX_METADATA_BYTES", 500)
    r = Resource(title="Unicode", url="https://example.org/unicode", source="supplied", type="paper",
                 metadata={"segments": [{"page": 1, "text": "测试" * 300}, {"page": 2, "text": "Bad \ud800 text"}]})
    result = extract_project_evidence([r])
    assert result["coverage"]["metadata_bytes_retained"] <= 500
    assert "\ud800" not in json.dumps(result, ensure_ascii=False)
