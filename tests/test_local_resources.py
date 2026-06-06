import json
import os
import subprocess
import sys
import pytest

from fields_study_flow.local_resources import analyze_local_resources


def test_analyze_local_resources_extracts_shortest_path_fields(tmp_path):
    note = tmp_path / "transformer-derivation.md"
    note.write_text(
        """# Transformer Derivation Notes

Self-attention, positional encoding, and the training objective needed to read Attention Is All You Need.
Skip broad NLP history unless it blocks the paper.
""",
        encoding="utf-8",
    )

    resources = analyze_local_resources([str(note)], "fully master Transformer paper")

    assert len(resources) == 1
    resource = resources[0]
    assert resource.source == "local-library"
    assert resource.local_path == str(note.resolve())
    assert resource.estimated_minutes is not None
    assert resource.learning_key_points
    assert resource.focus_areas
    assert resource.metadata["candidate_decision"] == "critical-path-candidate"


def test_analyze_local_resources_does_not_inherit_goal_keywords(tmp_path):
    note = tmp_path / "grocery-list.md"
    note.write_text("# Grocery List\nmilk\neggs\nrice", encoding="utf-8")

    resources = analyze_local_resources([str(note)], "fully master Transformer paper")

    assert len(resources) == 1
    resource = resources[0]
    assert "transformer" not in resource.concepts
    assert resource.metadata["candidate_decision"] == "supplement-only"


def test_cli_analyze_local_outputs_rankable_resources(tmp_path):
    note = tmp_path / "ppo-notes.md"
    note.write_text("# PPO Notes\npolicy gradient and clipped objective", encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "fields_study_flow.cli",
            "analyze-local",
            "--goal",
            "master PPO paper",
            "--path",
            str(note),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    resources = json.loads(result.stdout)
    assert resources[0]["source"] == "local-library"
    assert resources[0]["estimated_minutes"] is not None
    assert resources[0]["local_path"] is None
    assert resources[0]["url"].startswith("local://")


def test_analyze_local_resources_reads_tex_notebook_and_pdf_previews(tmp_path):
    tex = tmp_path / "attention-proof.tex"
    tex.write_text("\\section{Attention} Transformer self-attention derivation and proof notes.", encoding="utf-8")
    notebook = tmp_path / "minimal-transformer.ipynb"
    notebook.write_text(
        json.dumps(
            {
                "cells": [
                    {"cell_type": "markdown", "source": ["# Transformer notebook\n", "self-attention implementation"]},
                    {"cell_type": "code", "source": ["class Attention: pass\n"]},
                ]
            }
        ),
        encoding="utf-8",
    )
    pdf = tmp_path / "attention-paper.pdf"
    pdf.write_bytes(b"%PDF-1.4\nTransformer self-attention positional encoding paper\n%%EOF")

    resources = analyze_local_resources([str(tex), str(notebook), str(pdf)], "master Transformer paper", max_files=5)
    by_suffix = {resource.metadata["path_name"].split(".")[-1]: resource for resource in resources}

    assert by_suffix["tex"].type == "notes"
    assert by_suffix["ipynb"].type == "code"
    assert by_suffix["pdf"].type == "paper"
    assert "attention" in by_suffix["pdf"].concepts


def test_analyze_local_resources_does_not_follow_symlinked_files_outside_explicit_directory(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    inside = root / "inside.md"
    inside.write_text("# Transformer Notes\nself-attention", encoding="utf-8")
    outside = tmp_path / "outside-secret.md"
    outside.write_text("# Secret Outside\nprivate token transformer", encoding="utf-8")
    link = root / "linked-secret.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("Symlinks are not available in this environment.")

    resources = analyze_local_resources([str(root)], "master Transformer paper", max_files=10)

    assert [resource.metadata["path_name"] for resource in resources] == ["inside.md"]
    assert all(os.path.realpath(resource.local_path).startswith(os.path.realpath(root)) for resource in resources)
