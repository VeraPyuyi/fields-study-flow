from pathlib import Path

from git4study.sources import SourceRegistry


def test_source_registry_loads_declared_platforms():
    registry = SourceRegistry.from_yaml(Path("source-registry.yaml"))

    assert "github" in registry.sources
    assert "youtube" in registry.sources
    assert "bilibili" in registry.sources
    assert registry.sources["github"].access_mode == "official-api"


def test_source_registry_filters_by_language_and_policy():
    registry = SourceRegistry.from_yaml(Path("source-registry.yaml"))

    zh_sources = registry.discover(language_preference="zh-only", source_policy="open")
    source_ids = {source.id for source in zh_sources}

    assert "bilibili" in source_ids
    assert "zhihu" in source_ids
    assert "youtube" in source_ids
    assert "arxiv" not in source_ids
    assert all("zh-CN" in source.languages for source in zh_sources)


def test_restricted_sources_are_excluded_for_open_policy():
    registry = SourceRegistry.from_yaml(Path("source-registry.yaml"))

    open_sources = {source.id for source in registry.discover(language_preference="balanced", source_policy="open")}

    assert "coursera" not in open_sources
    assert "deep-learning-ai" in open_sources


def test_source_registry_accepts_standard_yaml_syntax(tmp_path):
    registry_file = tmp_path / "registry.yaml"
    registry_file.write_text(
        """
sources:
  - id: custom-course
    name: Custom Course
    category: course
    languages:
      - en
    access_mode: link-only
    auth_required: false
    allowed_use: Recommend public course pages by link.
    quality_signals:
      - syllabus
    restricted: false
""".strip(),
        encoding="utf-8",
    )

    registry = SourceRegistry.from_yaml(registry_file)

    assert registry.sources["custom-course"].name == "Custom Course"


def test_source_registry_rejects_unknown_source_policy():
    registry = SourceRegistry.from_yaml(Path("source-registry.yaml"))

    try:
        registry.discover(language_preference="balanced", source_policy="opne")
    except ValueError as exc:
        assert "Unsupported source policy" in str(exc)
    else:
        raise AssertionError("Expected invalid source policy to raise")
