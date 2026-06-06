import json
import importlib
import subprocess
import sys
from pathlib import Path

from fields_study_flow.cli import _paper_live_search_query, _paper_resource_from_url, _parse_sources
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.roadmap import build_roadmap, write_outputs


def test_cli_roadmap_generates_expected_artifacts(tmp_path):
    output_dir = tmp_path / "out"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "roadmap",
            "--goal",
            "从 Python 到掌握 Transformer",
            "--output-language",
            "zh-CN",
            "--resource-language",
            "en-first",
            "--output-dir",
            str(output_dir),
            "--offline",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (output_dir / "learner_profile.json").exists()
    assert (output_dir / "resource_index.json").exists()
    assert (output_dir / "local_resource_analysis.json").exists()
    assert (output_dir / "source_registry_snapshot.json").exists()
    assert (output_dir / "roadmap.md").exists()
    assert (output_dir / "roadmap.json").exists()
    assert (output_dir / "roadmap.svg").exists()
    assert (output_dir / "roadmap.html").exists()

    roadmap = json.loads((output_dir / "roadmap.json").read_text(encoding="utf-8"))
    assert roadmap["profile"]["resource_language_preference"] == "en-first"
    assert roadmap["path_strategy"]["mode"] == "balanced"
    assert roadmap["path_strategy"]["route_depth"] == "balanced"
    assert "Transformer" in (output_dir / "roadmap.md").read_text(encoding="utf-8")
    assert "模式" in (output_dir / "roadmap.svg").read_text(encoding="utf-8")
    assert "roadmap-grid" in (output_dir / "roadmap.html").read_text(encoding="utf-8")


def test_cli_discover_sources_outputs_language_filtered_sources():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "discover-sources",
            "--goal",
            "理解 Transformer",
            "--language",
            "zh-only",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "bilibili" in result.stdout
    assert "zhihu" in result.stdout


def test_cli_source_aliases_match_documented_short_names():
    assert _parse_sources("pwc,hf,youtube") == {"papers-with-code", "hugging-face", "youtube"}


def test_legacy_git4study_cli_wrapper_still_works():
    result = subprocess.run(
        [sys.executable, "-m", "git4study.cli", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "fields-study-flow" in result.stdout


def test_legacy_git4study_submodule_is_available_as_package_attribute():
    import git4study

    importlib.import_module("git4study.language")

    assert git4study.language.ResourceLanguagePreference.BALANCED == "balanced"


def test_cli_paper_includes_target_url_in_resource_index(tmp_path):
    output_dir = tmp_path / "paper"
    paper_url = "https://arxiv.org/abs/1706.03762"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "paper",
            "--url",
            paper_url,
            "--no-live-search",
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    resources = json.loads((output_dir / "resource_index.json").read_text(encoding="utf-8"))
    assert any(resource["url"] == paper_url for resource in resources)


def test_cli_paper_uses_local_pdf_title_instead_of_private_path(tmp_path):
    pdf = tmp_path / "private-solver-paper.pdf"
    pdf.write_bytes(
        b"""%PDF-1.4
Learning Sparse Matrix Solvers
Abstract
We study sparse matrix solvers.
1 Method
The method optimizes a residual.
%%EOF"""
    )
    output_dir = tmp_path / "out"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "paper",
            "--url",
            str(pdf),
            "--output-language",
            "en",
            "--resource-language",
            "en-first",
            "--no-live-search",
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    roadmap = json.loads((output_dir / "roadmap.json").read_text(encoding="utf-8"))
    dumped = json.dumps(roadmap, ensure_ascii=False)

    assert "Learning Sparse Matrix Solvers" in roadmap["title"]
    assert "Learning Sparse Matrix Solvers" in roadmap["profile"]["goal"]
    assert str(pdf) not in dumped
    assert "[private local path]" not in roadmap["title"]


def test_cli_paper_resource_uses_resolved_metadata(monkeypatch):
    def fake_resolve(url: str, *, live: bool = True):
        return {
            "title": "Metadata Driven Paper",
            "url": url,
            "source": "semantic-scholar",
            "abstract_snippet": "A metadata-rich paper about verifiable study routes.",
            "authors": ["Ada Example"],
            "source_ids": {"doi": "10.5555/example"},
            "concepts": ["verification", "study routes"],
            "sections": ["Introduction", "Method"],
            "method_hints": ["Method turns metadata into a route."],
            "experiment_hints": [],
            "limitations_hints": [],
            "metadata_status": "ok",
            "warnings": [],
            "local_path": None,
        }

    monkeypatch.setattr("fields_study_flow.cli.resolve_paper_metadata", fake_resolve, raising=False)

    resource = _paper_resource_from_url("https://doi.org/10.5555/example", live=True)

    assert resource.title == "Metadata Driven Paper"
    assert resource.source == "semantic-scholar"
    assert resource.metadata["paper_metadata"]["source_ids"]["doi"] == "10.5555/example"


def test_cli_registry_course_source_id_keeps_course_catalog_resources(tmp_path):
    output_dir = tmp_path / "course"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "roadmap",
            "--goal",
            "从 Python 到掌握 Transformer",
            "--sources",
            "mit-ocw",
            "--no-live-search",
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    resources = json.loads((output_dir / "resource_index.json").read_text(encoding="utf-8"))
    assert resources
    assert any(resource["source"] == "course" for resource in resources)


def test_cli_paper_with_videos_flag_controls_video_resources(tmp_path):
    no_video_dir = tmp_path / "paper-no-video"
    with_video_dir = tmp_path / "paper-with-video"
    paper_url = "https://example.com/diffusion-paper"

    no_video = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "paper",
            "--url",
            paper_url,
            "--no-live-search",
            "--output-dir",
            str(no_video_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    with_video = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "paper",
            "--url",
            paper_url,
            "--with-videos",
            "--no-live-search",
            "--output-dir",
            str(with_video_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert no_video.returncode == 0, no_video.stderr
    assert with_video.returncode == 0, with_video.stderr
    no_video_resources = json.loads((no_video_dir / "resource_index.json").read_text(encoding="utf-8"))
    with_video_resources = json.loads((with_video_dir / "resource_index.json").read_text(encoding="utf-8"))
    assert all(resource["type"] != "video" for resource in no_video_resources)
    assert any(resource["type"] == "video" for resource in with_video_resources)


def test_cli_roadmap_can_include_explicit_local_resource(tmp_path):
    note = tmp_path / "transformer-notes.md"
    note.write_text("# Transformer Notes\nself-attention and positional encoding", encoding="utf-8")
    output_dir = tmp_path / "with-local"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "roadmap",
            "--goal",
            "master Transformer paper",
            "--local-resource",
            str(note),
            "--output-dir",
            str(output_dir),
            "--offline",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    local_analysis = json.loads((output_dir / "local_resource_analysis.json").read_text(encoding="utf-8"))
    assert local_analysis
    assert local_analysis[0]["source"] == "local-library"
    assert local_analysis[0]["local_path"] is None
    assert local_analysis[0]["url"].startswith("local://")
    assert str(note.resolve()) not in (output_dir / "roadmap.json").read_text(encoding="utf-8")
    assert str(note.resolve()) not in (output_dir / "roadmap.md").read_text(encoding="utf-8")
    assert str(note.resolve()) not in (output_dir / "roadmap.html").read_text(encoding="utf-8")
    assert "LOCAL" in (output_dir / "roadmap.svg").read_text(encoding="utf-8")


def test_cli_paper_accepts_unified_planner_options_and_local_resources(tmp_path):
    note = tmp_path / "attention.tex"
    note.write_text("\\section{Attention} Scaled dot-product attention and residual connection.", encoding="utf-8")
    output_dir = tmp_path / "paper-unified"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "paper",
            "--url",
            "https://arxiv.org/abs/1706.03762",
            "--route-depth",
            "fastest",
            "--learning-style",
            "practical",
            "--target-kind",
            "paper",
            "--local-resource",
            str(note),
            "--no-live-search",
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    roadmap = json.loads((output_dir / "roadmap.json").read_text(encoding="utf-8"))
    assert roadmap["profile"]["route_depth"] == "fastest"
    assert roadmap["profile"]["learning_style"] == "practical"
    assert roadmap["profile"]["target_kind"] == "paper"
    assert roadmap["path_strategy"]["mode"] == "fastest"
    assert (output_dir / "roadmap.html").exists()


def test_cli_presets_configure_common_learning_modes(tmp_path):
    roadmap_dir = tmp_path / "preset-field"
    paper_dir = tmp_path / "preset-paper"

    roadmap_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "roadmap",
            "--goal",
            "learn diffusion models",
            "--preset",
            "field-project",
            "--offline",
            "--output-dir",
            str(roadmap_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    paper_result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "paper",
            "--url",
            "https://arxiv.org/abs/1706.03762",
            "--preset",
            "paper-fastest",
            "--no-live-search",
            "--output-dir",
            str(paper_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert roadmap_result.returncode == 0, roadmap_result.stderr
    assert paper_result.returncode == 0, paper_result.stderr

    roadmap = json.loads((roadmap_dir / "roadmap.json").read_text(encoding="utf-8"))
    paper = json.loads((paper_dir / "roadmap.json").read_text(encoding="utf-8"))

    assert roadmap["profile"]["target_kind"] == "field"
    assert roadmap["profile"]["route_depth"] == "balanced"
    assert roadmap["profile"]["learning_style"] == "practical"
    assert paper["profile"]["target_kind"] == "paper"
    assert paper["profile"]["route_depth"] == "fastest"
    assert paper["profile"]["learning_style"] == "practical"


def test_cli_paper_live_search_query_does_not_include_private_url():
    private_url = "https://institution.example/private/paper.pdf?token=secret"

    query = _paper_live_search_query("fully understand, derive, and reproduce the paper", private_url)

    assert private_url not in query
    assert "token=secret" not in query
    assert "institution.example" not in query
    assert "fully understand" in query


def test_cli_export_writes_svg_and_html(tmp_path):
    profile = LearnerProfile(goal="master Transformer", output_language="en")
    resource = Resource(
        title="Transformer Notes",
        url="local://local-notes",
        source="local-library",
        type="notes",
        language="en",
        concepts=["transformer"],
        estimated_minutes=30,
        metadata={"local_availability": True, "candidate_decision": "critical-path-candidate"},
        critical_path_role="focused-support",
    )
    roadmap = build_roadmap(profile, [resource])
    source_dir = tmp_path / "source"
    write_outputs(source_dir, profile, [resource], roadmap, {"sources": []})
    export_dir = tmp_path / "export"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "export",
            "--input",
            str(source_dir / "roadmap.json"),
            "--format",
            "all",
            "--output-dir",
            str(export_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (export_dir / "roadmap.json").exists()
    assert (export_dir / "roadmap.md").exists()
    assert (export_dir / "roadmap.svg").exists()
    assert (export_dir / "roadmap.html").exists()


def test_cli_export_all_sanitizes_private_paths_and_lists_outputs(tmp_path):
    source = tmp_path / "private-roadmap.json"
    source.write_text(
        json.dumps(
            {
                "title": "Private Roadmap",
                "profile": {"goal": "master private paper", "output_language": "en", "resource_language_preference": "balanced"},
                "path_strategy": {"mode": "fastest", "estimated_total_time": "1h", "selected_resources": 1, "candidate_resources": 1},
                "generated_artifacts": [],
                "phases": [
                    {
                        "name": "Phase 1",
                        "objective": "Read local paper",
                        "estimated_time": "1h",
                        "resources": [
                            {
                                "title": "Private Paper",
                                "url": "file:///C:/Users/example/private/paper.pdf",
                                "source": "local-library",
                                "type": "paper",
                                "language": "en",
                                "difficulty": "advanced",
                                "estimated_time": "1h",
                                "trust_score": 0.8,
                                "critical_path_role": "core-paper",
                                "concepts": ["attention"],
                                "learning_key_points": ["read"],
                                "focus_areas": ["method"],
                                "why_recommended": "Uses C:/Users/example/private/paper.pdf",
                                "license_or_access_note": "Explicit local file.",
                                "translation_note": "No translation needed.",
                                "local_path": "C:/Users/example/private/paper.pdf",
                                "metadata": {
                                    "target_paper": True,
                                    "paper_metadata": {
                                        "title": "Private Paper",
                                        "url": "file:///C:/Users/example/private/paper.pdf",
                                        "local_path": "C:/Users/example/private/paper.pdf",
                                    },
                                },
                            }
                        ],
                    }
                ],
                "checkpoints": ["Explain it."],
                "safety_policy": ["Do not expose private paths."],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    export_dir = tmp_path / "export"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "export",
            "--input",
            str(source),
            "--format",
            "all",
            "--output-dir",
            str(export_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "roadmap.json" in result.stdout
    assert "roadmap.md" in result.stdout
    assert "roadmap.svg" in result.stdout
    assert "roadmap.html" in result.stdout
    for target in ("roadmap.json", "roadmap.md", "roadmap.svg", "roadmap.html"):
        exported = (export_dir / target).read_text(encoding="utf-8")
        assert "C:/Users/example/private" not in exported
        assert "file:///C:/Users/example/private" not in exported


def test_write_outputs_sanitizes_private_urls_in_resource_indices(tmp_path):
    profile = LearnerProfile(goal="master C:/Users/example/private folder/paper.pdf", output_language="en", target_kind="paper")
    resource = Resource(
        title="Private Paper",
        url="file:///C:/Users/example/private%20folder/paper.pdf",
        source="local-library",
        type="paper",
        language="en",
        concepts=["attention"],
        estimated_minutes=120,
        local_path="C:/Users/example/private folder/paper.pdf",
        why_recommended="Read C:/Users/example/private folder/paper.pdf first.",
        metadata={
            "target_paper": True,
            "paper_metadata": {
                "title": "Private Paper",
                "url": "file:///C:/Users/example/private%20folder/paper.pdf",
                "local_path": "C:/Users/example/private folder/paper.pdf",
            },
        },
        critical_path_role="core-paper",
    )
    roadmap = build_roadmap(profile, [resource])

    write_outputs(tmp_path, profile, [resource], roadmap, {"sources": []})

    for target in ("resource_index.json", "local_resource_analysis.json", "roadmap.json"):
        exported = (tmp_path / target).read_text(encoding="utf-8")
        assert "C:/Users/example/private" not in exported
        assert "private folder" not in exported
        assert "file:///C:/Users/example/private" not in exported
        assert "local://private-paper" in exported


def test_write_outputs_exports_generated_artifact_template(tmp_path):
    profile = LearnerProfile(goal="build a diffusion model project", output_language="en", target_kind="field")
    resource = Resource(
        title="Diffusion paper",
        url="https://arxiv.org/abs/2105.05233",
        source="arxiv",
        type="paper",
        language="en",
        concepts=["diffusion models"],
        estimated_minutes=300,
        trust_score=0.9,
        critical_path_role="core-paper",
    )
    roadmap = build_roadmap(profile, [resource])

    write_outputs(tmp_path, profile, [resource], roadmap, {"sources": []})

    assert (tmp_path / "artifact_template" / "README.md").exists()
    assert (tmp_path / "artifact_template" / "task_checklist.md").exists()
    assert (tmp_path / "artifact_template" / "reproduction_log.md").exists()
    assert (tmp_path / "artifact_template" / "notebook_skeleton.ipynb").exists()
    assert (tmp_path / "artifact_template" / "src" / "main.py").exists()


def test_artifact_template_includes_paper_derived_acceptance_targets(tmp_path):
    profile = LearnerProfile(goal="fully understand and reproduce a diffusion paper", output_language="en", target_kind="paper")
    paper = Resource(
        title="Diffusion paper",
        url="local://paper-diffusion",
        source="local-library",
        type="paper",
        language="en",
        concepts=["diffusion models"],
        estimated_minutes=300,
        trust_score=0.9,
        metadata={
            "target_paper": True,
            "paper_metadata": {
                "title": "Diffusion paper",
                "sections": ["Method", "Experiments"],
                "method_hints": ["The method predicts epsilon with classifier-free guidance."],
                "experiment_hints": ["Experiments compare FID and sampling speed."],
                "limitations_hints": ["Limitations include slow sampling."],
                "formula_candidates": ["L_simple = E[||epsilon - epsilon_theta(x_t,t)||^2]"],
                "code_links": ["https://github.com/example/diffusion-sampler"],
                "local_path": None,
            },
        },
        critical_path_role="core-paper",
    )
    roadmap = build_roadmap(profile, [paper])

    write_outputs(tmp_path, profile, [paper], roadmap, {"sources": []})

    checklist = (tmp_path / "artifact_template" / "task_checklist.md").read_text(encoding="utf-8")
    log = (tmp_path / "artifact_template" / "reproduction_log.md").read_text(encoding="utf-8")
    readme = (tmp_path / "artifact_template" / "README.md").read_text(encoding="utf-8")

    assert "epsilon_theta" in checklist
    assert "https://github.com/example/diffusion-sampler" in checklist
    assert "The method predicts epsilon" in readme
    assert "Experiments compare FID" in log
    assert "Limitations include slow sampling" in log


def test_artifact_template_follows_chinese_output_language(tmp_path):
    profile = LearnerProfile(goal="复现 diffusion paper", output_language="zh-CN", target_kind="paper")
    paper = Resource(
        title="Diffusion paper",
        url="local://paper-diffusion",
        source="local-library",
        type="paper",
        language="en",
        concepts=["diffusion models"],
        estimated_minutes=300,
        trust_score=0.9,
        metadata={"target_paper": True, "paper_metadata": {"formula_candidates": ["L_simple = E[||epsilon||^2]"], "local_path": None}},
        critical_path_role="core-paper",
    )
    roadmap = build_roadmap(profile, [paper])

    write_outputs(tmp_path, profile, [paper], roadmap, {"sources": []})

    readme = (tmp_path / "artifact_template" / "README.md").read_text(encoding="utf-8")
    checklist = (tmp_path / "artifact_template" / "task_checklist.md").read_text(encoding="utf-8")
    log = (tmp_path / "artifact_template" / "reproduction_log.md").read_text(encoding="utf-8")

    assert "# fields-study-flow 产物模板" in readme
    assert "# 产物验收清单" in checklist
    assert "推导或追踪这个公式候选" in checklist
    assert "# 复现记录" in log


def test_write_outputs_removes_stale_artifact_template_when_not_required(tmp_path):
    first_profile = LearnerProfile(goal="build a diffusion model project", output_language="en", target_kind="field")
    paper = Resource(
        title="Diffusion paper",
        url="https://arxiv.org/abs/2105.05233",
        source="arxiv",
        type="paper",
        language="en",
        concepts=["diffusion models"],
        estimated_minutes=300,
        trust_score=0.9,
        critical_path_role="core-paper",
    )
    first_roadmap = build_roadmap(first_profile, [paper])
    write_outputs(tmp_path, first_profile, [paper], first_roadmap, {"sources": []})
    assert (tmp_path / "artifact_template" / "README.md").exists()

    second_profile = LearnerProfile(goal="build a diffusion model project", output_language="en", target_kind="field")
    repo = Resource(
        title="Diffusion implementation",
        url="https://github.com/example/diffusion",
        source="github",
        type="repository",
        language="en",
        concepts=["diffusion models", "python"],
        estimated_minutes=300,
        trust_score=0.8,
        critical_path_role="practice-validation",
    )
    second_roadmap = build_roadmap(second_profile, [repo])
    write_outputs(tmp_path, second_profile, [repo], second_roadmap, {"sources": []})

    assert second_roadmap["generated_artifacts"] == []
    assert not (tmp_path / "artifact_template").exists()
