import json
import importlib
import subprocess
import sys
from pathlib import Path

from fields_study_flow.cli import _parse_sources


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
    assert (output_dir / "source_registry_snapshot.json").exists()
    assert (output_dir / "roadmap.md").exists()
    assert (output_dir / "roadmap.json").exists()

    roadmap = json.loads((output_dir / "roadmap.json").read_text(encoding="utf-8"))
    assert roadmap["profile"]["resource_language_preference"] == "en-first"
    assert "Transformer" in (output_dir / "roadmap.md").read_text(encoding="utf-8")


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
