"""Refresh an existing offline report while preserving its downloaded bundle."""
from __future__ import annotations

import argparse
import json
from dataclasses import fields
from pathlib import Path

from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.paper_metadata import resolve_paper_metadata, paper_metadata_to_resource
from fields_study_flow.rag import apply_rag_to_resources, public_rag_evidence
from fields_study_flow.resource_bundle import attach_study_bundle
from fields_study_flow.roadmap import build_roadmap, write_outputs


def refresh(report_dir: Path, paper: Path, assets: Path) -> None:
    def read(name: str) -> dict | list:
        return json.loads((report_dir / name).read_text(encoding="utf-8"))

    profile_data = read("learner_profile.json")
    profile_data["learning_outcome"] = "present"
    profile = LearnerProfile(**profile_data)
    old = read("roadmap.json")
    manifest = json.loads((assets / "study_bundle_manifest.json").read_text(encoding="utf-8"))
    manifest["resource_dir"] = str(assets.resolve())
    entries = {(e.get("title"), e.get("url")): e for e in manifest.get("resources", [])}
    accepted = {f.name for f in fields(Resource)}
    resources = []
    for data in read("resource_index.json"):
        resource = Resource(**{k: v for k, v in data.items() if k in accepted})
        entry = entries.get((resource.title, resource.url), {})
        file = assets / str(entry.get("file") or "missing")
        if entry.get("status") in {"downloaded", "copied", "snapshotted", "generated"} and file.is_file() and file.resolve().is_relative_to(assets.resolve()):
            resource.local_path = str(file.resolve())
        resource.metadata.pop("target_paper", None)
        resources.append(resource)
    target = paper_metadata_to_resource(resolve_paper_metadata(str(paper), live=False))
    previous_target = old.get("paper_map", {}).get("target") or old.get("paper_lens", {}).get("target") or {}
    # Preserve the existing public identity for its previously copied local PDF.
    target.title = previous_target.get("title") or target.title
    target.url = previous_target.get("url") or target.url
    target.local_path = str(paper.resolve())
    resources = [target] + [r for r in resources if (r.title, r.url) != (target.title, target.url)]
    resources, index = apply_rag_to_resources(profile, resources, mode="light")
    plan = build_roadmap(profile, resources, offline=True, explanation_provider="local",
        rag_evidence=public_rag_evidence(index, profile.goal),
        live_search={"enabled": False, "status": "saved_materials_offline"},
        paper_lens_options={"language": "zh-CN", "density": "dense", "granularity": "paragraph"},
        paper_map_options={"language": "zh-CN", "depth": "standard", "provider": "local"})
    plan = attach_study_bundle(plan, manifest, report_dir=report_dir)
    registry_file = report_dir / "source_registry_snapshot.json"
    registry = read(registry_file.name) if registry_file.exists() else None
    write_outputs(report_dir, profile, resources, plan, registry)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    parser.add_argument("--assets", type=Path, required=True)
    args = parser.parse_args()
    refresh(args.report_dir, args.paper, args.assets)
    print("Offline workbench refreshed; existing bundle and user notes preserved.")
