import json

from fields_study_flow.mcp_tools import analyzeLocalResources, buildRoadmap, exportPlan, ingestUrl, searchResources, validateSources


def test_search_resources_applies_hard_language_filter_at_tool_boundary():
    result = searchResources("diffusion", languagePreference="zh-only")

    assert result["resources"]
    assert all(resource["language"] == "zh-CN" for resource in result["resources"])


def test_validate_sources_rejects_piracy_bypass_and_download_instructions():
    plan = {
        "phases": [
            {
                "resources": [
                    {
                        "title": "pirate",
                        "url": "https://sci-hub.example/paper",
                        "license_or_access_note": "mirror",
                    },
                    {
                        "title": "download video",
                        "url": "https://youtube.com/watch?v=abc",
                        "license_or_access_note": "download video with a helper tool",
                    },
                    {
                        "title": "bypass",
                        "url": "https://example.com/course",
                        "license_or_access_note": "bypass login and copy full text",
                    },
                ]
            }
        ]
    }

    result = validateSources(plan)

    assert result["valid"] is False
    assert any("Disallowed source" in issue for issue in result["issues"])
    assert any("download video" in issue for issue in result["issues"])
    assert any("bypass login" in issue for issue in result["issues"])


def test_analyze_local_resources_tool_returns_shortest_path_candidates(tmp_path):
    note = tmp_path / "attention-notes.md"
    note.write_text("# Attention Notes\nself-attention transformer paper derivation", encoding="utf-8")

    result = analyzeLocalResources(paths=[str(note)], goal="master Transformer paper", languagePreference="en-first")

    assert result["resources"]
    assert result["resources"][0]["source"] == "local-library"
    assert result["shortest_path_policy"].startswith("Include local material only")


def test_analyze_local_resources_tool_does_not_echo_absolute_paths(tmp_path):
    note = tmp_path / "attention-notes.md"
    note.write_text("# Attention Notes\nself-attention transformer paper derivation", encoding="utf-8")

    result = analyzeLocalResources(paths=[str(note.resolve())], goal="master Transformer paper", languagePreference="en-first")

    serialized = str(result)
    assert str(note.resolve()) not in serialized
    assert result["paths"][0]["path_name"] == "attention-notes.md"
    assert result["paths"][0]["local_path"] is None


def test_ingest_url_returns_paper_metadata_for_public_paper(monkeypatch):
    def fake_resolve(url: str):
        return {
            "title": "Metadata Driven Paper",
            "url": url,
            "source": "semantic-scholar",
            "abstract_snippet": "A metadata-rich paper about verifiable study routes.",
            "authors": ["Ada Example"],
            "source_ids": {"doi": "10.5555/example"},
            "concepts": ["verification"],
            "sections": ["Method"],
            "method_hints": ["Method turns metadata into a route."],
            "experiment_hints": [],
            "limitations_hints": [],
            "metadata_status": "ok",
            "warnings": [],
            "local_path": None,
        }

    monkeypatch.setattr("fields_study_flow.mcp_tools.resolve_paper_metadata", fake_resolve, raising=False)

    result = ingestUrl("https://doi.org/10.5555/example")

    assert result["title"] == "Metadata Driven Paper"
    assert result["metadata"]["paper_metadata"]["title"] == "Metadata Driven Paper"
    assert result["metadata"]["metadata_status"] == "ok"


def test_validate_sources_accepts_explicit_local_library_file_urls():
    plan = {
        "phases": [
            {
                "resources": [
                    {
                        "title": "local notes",
                        "url": "file:///tmp/notes.md",
                        "source": "local-library",
                        "license_or_access_note": "Explicit user-provided local path.",
                    }
                ]
            }
        ]
    }

    result = validateSources(plan)

    assert result["valid"] is True


def test_export_plan_writes_markdown_svg_and_html(tmp_path):
    plan = {
        "title": "Learning Roadmap: Transformer",
        "profile": {"goal": "Transformer", "output_language": "en", "resource_language_preference": "balanced"},
        "path_strategy": {
            "mode": "shortest_mastery_path",
            "estimated_total_time": "30min",
            "selected_resources": 1,
            "candidate_resources": 1,
        },
        "phases": [
            {
                "name": "Phase 1: Core Understanding",
                "objective": "Study the core concept.",
                "estimated_time": "30min",
                "resources": [
                    {
                        "title": "Transformer Notes",
                        "url": "local://local-notes",
                        "source": "local-library",
                        "type": "notes",
                        "language": "en",
                        "difficulty": "intermediate",
                        "estimated_time": "30min",
                        "trust_score": 0.7,
                        "critical_path_role": "focused-support",
                        "concepts": ["transformer"],
                        "learning_key_points": ["self-attention"],
                        "focus_areas": ["attention"],
                        "why_recommended": "Local shortcut.",
                        "license_or_access_note": "Explicit user-provided local path.",
                        "translation_note": "No translation needed.",
                    }
                ],
            }
        ],
        "checkpoints": ["Explain the core idea."],
        "safety_policy": ["Use explicit local paths only."],
    }

    result = exportPlan(plan, str(tmp_path))

    assert (tmp_path / "roadmap.json").exists()
    assert (tmp_path / "roadmap.md").exists()
    assert (tmp_path / "roadmap.svg").exists()
    assert (tmp_path / "roadmap.html").exists()
    assert result["roadmap_svg"].endswith("roadmap.svg")
    assert result["roadmap_html"].endswith("roadmap.html")


def test_export_plan_writes_generated_artifact_template(tmp_path):
    plan = {
        "title": "Learning Roadmap: Diffusion Project",
        "profile": {"goal": "build a diffusion model project", "output_language": "en", "resource_language_preference": "balanced"},
        "path_strategy": {
            "mode": "balanced",
            "estimated_total_time": "5h",
            "selected_resources": 2,
            "candidate_resources": 1,
        },
        "artifact_requirements": {"requires_runnable": True, "policy": "auto-generated-template"},
        "artifact_gaps": [],
        "generated_artifacts": [
            "artifact_template/README.md",
            "artifact_template/task_checklist.md",
            "artifact_template/reproduction_log.md",
            "artifact_template/notebook_skeleton.ipynb",
            "artifact_template/src/main.py",
        ],
        "phases": [],
        "checkpoints": ["Run the minimal template and record evidence."],
        "safety_policy": ["Use explicit local paths only."],
    }

    result = exportPlan(plan, str(tmp_path))

    assert (tmp_path / "artifact_template" / "README.md").exists()
    assert (tmp_path / "artifact_template" / "src" / "main.py").exists()
    assert result["artifact_template"].endswith("artifact_template")


def test_export_plan_sanitizes_private_paths_in_existing_plan(tmp_path):
    plan = {
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
    }

    exportPlan(plan, str(tmp_path))

    for target in ("roadmap.json", "roadmap.md", "roadmap.svg", "roadmap.html"):
        exported = (tmp_path / target).read_text(encoding="utf-8")
        assert "C:/Users/example/private" not in exported
        assert "file:///C:/Users/example/private" not in exported


def test_build_roadmap_tool_accepts_unified_planning_options():
    plan = buildRoadmap(
        goal="build a diffusion model project",
        profile={"output_language": "en"},
        rankedResources=[
            {
                "title": "Diffusion implementation",
                "url": "https://github.com/example/diffusion",
                "source": "github",
                "type": "repository",
                "language": "en",
                "concepts": ["diffusion models", "python"],
                "estimated_minutes": 300,
                "trust_score": 0.8,
            }
        ],
        outputLanguage="en",
        routeDepth="complete",
        learningStyle="practical",
        targetKind="field",
    )

    assert plan["profile"]["route_depth"] == "complete"
    assert plan["profile"]["learning_style"] == "practical"
    assert plan["profile"]["target_kind"] == "field"
    assert plan["final_artifact"]["type"] == "project"


def test_build_roadmap_tool_sanitizes_private_resource_urls():
    plan = buildRoadmap(
        goal="master C:/Users/example/private folder/paper.pdf",
        profile={"output_language": "en"},
        rankedResources=[
            {
                "title": "Private Paper",
                "url": "file:///C:/Users/example/private%20folder/paper.pdf",
                "source": "local-library",
                "type": "paper",
                "language": "en",
                "concepts": ["attention"],
                "estimated_minutes": 120,
                "local_path": "C:/Users/example/private folder/paper.pdf",
                "why_recommended": "Read C:/Users/example/private folder/paper.pdf first.",
                "metadata": {
                    "target_paper": True,
                    "paper_metadata": {
                        "title": "Private Paper",
                        "url": "file:///C:/Users/example/private%20folder/paper.pdf",
                        "local_path": "C:/Users/example/private folder/paper.pdf",
                    },
                },
            }
        ],
        outputLanguage="en",
        targetKind="paper",
    )

    serialized = json.dumps(plan, ensure_ascii=False)
    assert "C:/Users/example/private" not in serialized
    assert "private folder" not in serialized
    assert "file:///C:/Users/example/private" not in serialized
    assert "local://private-paper" in serialized


def test_search_resources_defaults_to_live_search_but_falls_back(monkeypatch):
    def fail_live_search(*_args, **_kwargs):
        raise RuntimeError("network unavailable")

    monkeypatch.setattr("fields_study_flow.mcp_tools.search_live_resources", fail_live_search)

    result = searchResources("Transformer", languagePreference="en-first")

    assert result["resources"]
    assert result["live_search"]["enabled"] is True
    assert result["live_search"]["status"] == "fallback"
