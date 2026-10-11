"""Prepare local research-workbench examples; HTML export is an explicit step."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


HERE = Path(__file__).resolve().parent


def load_records() -> list[dict]:
    return json.loads((HERE / "source_records.json").read_text(encoding="utf-8"))["papers"]


def _write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate(output_dir: Path, *, output_language: str = "zh-CN", export_html: bool = False) -> dict:
    output_dir = Path(output_dir).resolve()
    if output_dir == HERE or output_dir in HERE.parents:
        raise ValueError("Choose an output directory that cannot overwrite example sources")
    if output_dir.is_relative_to(HERE) and output_dir.relative_to(HERE).parts[0] != "generated":
        raise ValueError("Inside the example folder, output must be under generated/")

    # Use the application pipeline, with both explanation and network policies explicit.
    from fields_study_flow.models import LearnerProfile, Resource
    from fields_study_flow.roadmap import build_roadmap
    from fields_study_flow.resource_bundle import attach_study_bundle, bundle_study_resources

    manifest = {"schema_version": 1, "network": "disabled", "explanation_provider": "local",
                "human_evaluation": "pending", "screenshots": "pending", "scenarios": []}
    for record in load_records():
        directory = output_dir / record["scenario"]
        directory.mkdir(parents=True, exist_ok=True)
        note = HERE / record["note"]
        text = note.read_text(encoding="utf-8")
        profile = LearnerProfile(
            goal=f"{record['learning_outcome']}: {record['title']} ({record['scenario']})",
            target_kind="paper", learning_outcome=record["learning_outcome"],
            output_language=output_language, known_topics=["linear algebra"],
            levels={"programming": "familiar"},
        )
        resources = [Resource(
            title=record["title"] + " - short paraphrase note, not full paper",
            url=record["url"], source="local-library", type="paper", local_path=str(note),
            concepts=record["concepts"], critical_path_role="primary", trust_score=0.7,
            license_or_access_note="Original short paraphrase under example MIT license; paper rights remain with authors.",
            metadata={"target_paper": True, "resource_id": record["scenario"] + "-note",
                      "project_root": str(HERE), "text_preview": text,
                      "paper_metadata": {"title": record["title"], "text_preview": text,
                                         "metadata_status": "authored_paraphrase",
                                         "source_ids": {"arxiv": record["version"]},
                                         "warnings": [record["coverage_boundary"]]}},
        )]
        if record["scenario"] == "transformer-paper-project":
            for path in sorted((HERE / "toy-transformer").iterdir()):
                if path.suffix not in {".md", ".py", ".json", ".csv"}:
                    continue
                resources.append(Resource(
                    title="Own attention demonstration / " + path.name,
                    url="", source="local-library", type="code" if path.suffix == ".py" else "document",
                    local_path=str(path), concepts=["attention"],
                    license_or_access_note="Original MIT demonstration; not a paper implementation or reproduction.",
                    metadata={"resource_id": "toy-" + path.name.replace(".", "-"),
                              "kind": "result" if path.stem == "expected_trace" else "code" if path.suffix == ".py" else "config",
                              "project_root": str(HERE)},
                ))
        roadmap = build_roadmap(profile, resources, offline=True, explanation_provider="local",
                                live_search={"enabled": False, "status": "example_offline"})
        bundle = bundle_study_resources(directory / "study-assets", resources, roadmap, offline=True)
        # Fixed fixture titles/URLs are unique; carry IDs into copied bundle records.
        identities = {(r.title, r.url): r.metadata["resource_id"] for r in resources}
        for entry in bundle["resources"]:
            rid = identities.get((entry.get("title"), entry.get("url", "")))
            if rid:
                entry.setdefault("metadata", {})["resource_id"] = rid
        roadmap = attach_study_bundle(roadmap, bundle, report_dir=directory)
        roadmap["example_provenance"] = {
            "scenario": record["scenario"], "source_record": record,
            "paper_reproduction": False, "human_evaluation": "pending",
            "toy_materials": "own demonstration only" if len(resources) > 1 else "not supplied",
            "missing_materials": record["missing_materials"],
        }
        _write_json(directory / "roadmap.json", roadmap)
        _write_json(directory / "source_record.json", record)
        source_records = {"schema_version": 1, "papers": [record],
                          "bundled_materials": [{"resource_id": e.get("metadata", {}).get("resource_id"),
                                                 "local_href": e.get("local_href"), "status": e.get("status")}
                                                for e in roadmap["study_bundle"]["resources"]]}
        if record["scenario"] == "transformer-paper-project":
            source_records["toy_project"] = json.loads((HERE / "source_records.json").read_text(encoding="utf-8"))["toy_project"]
        _write_json(directory / "source_records.json", source_records)
        shutil.copyfile(HERE / "LICENSE", directory / "LICENSE")
        if export_html:
            from fields_study_flow.report_export import export_report

            export_report(directory, roadmap, profile=profile, ranked_resources=resources)
        manifest["scenarios"].append({
            "id": record["scenario"], "snapshot": record["scenario"] + "/roadmap.json",
            "html": "exported_unverified" if export_html else "pending",
            "note_sha256": hashlib.sha256(note.read_bytes()).hexdigest(),
            "materials": [{"name": r.metadata["resource_id"],
                           "sha256": hashlib.sha256(Path(r.local_path).read_bytes()).hexdigest()} for r in resources],
        })
    _write_json(output_dir / "example_manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=HERE / "generated")
    parser.add_argument("--output-language", choices=["zh-CN", "en", "bilingual"], default="zh-CN")
    parser.add_argument("--export-html", action="store_true", help="Use the shared exporter; no screenshots or human scores.")
    args = parser.parse_args()
    try:
        manifest = generate(args.output_dir, output_language=args.output_language, export_html=args.export_html)
    except ModuleNotFoundError as exc:
        parser.exit(2, f"Example generation blocked: required module {exc.name} is not available; finish module integration first.\n")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
