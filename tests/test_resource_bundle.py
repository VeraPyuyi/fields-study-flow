from __future__ import annotations

import json

from fields_study_flow.models import Resource
from fields_study_flow.resource_bundle import bundle_study_resources


class FakeStream:
    def __init__(self, content: bytes, content_type: str = "application/pdf") -> None:
        self.content = content
        self.headers = {"content-type": content_type}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self) -> None:
        return None

    def iter_bytes(self):
        yield self.content


class FakeClient:
    def __init__(self) -> None:
        self.urls: list[str] = []

    def stream(self, method: str, url: str, timeout: float | None = None):
        self.urls.append(url)
        return FakeStream(b"%PDF-1.4\nopen paper\n%%EOF")


class FakeHtmlClient(FakeClient):
    def stream(self, method: str, url: str, timeout: float | None = None):
        self.urls.append(url)
        return FakeStream(b"<!doctype html><title>open docs</title>", "text/html")


def test_bundle_copies_explicit_local_resources(tmp_path):
    paper = tmp_path / "private-paper.pdf"
    paper.write_bytes(b"%PDF-1.4\nprivate paper\n%%EOF")
    resource = Resource(
        title="Private Planning Paper",
        url="local://private-planning-paper",
        source="local-library",
        type="paper",
        local_path=str(paper),
    )
    roadmap = {"phases": [{"resources": [resource.to_dict()]}]}
    resource_dir = tmp_path / "bundle"

    manifest = bundle_study_resources(resource_dir, [resource], roadmap)

    copied = resource_dir / manifest["resources"][0]["file"]
    assert copied.exists()
    assert copied.read_bytes() == paper.read_bytes()
    assert manifest["summary"]["copied"] == 1
    assert (resource_dir / "study_bundle_manifest.json").exists()
    assert (resource_dir / "links.md").exists()


def test_bundle_downloads_arxiv_pdf_and_keeps_video_as_link(tmp_path):
    paper = Resource(
        title="Attention Is All You Need",
        url="https://arxiv.org/abs/1706.03762",
        source="arxiv",
        type="paper",
    )
    video = Resource(
        title="Lecture video",
        url="https://www.youtube.com/watch?v=example",
        source="youtube",
        type="video",
    )
    roadmap = {"phases": [{"resources": [paper.to_dict(), video.to_dict()]}]}
    client = FakeClient()

    manifest = bundle_study_resources(tmp_path / "bundle", [paper, video], roadmap, client=client)

    assert client.urls == ["https://arxiv.org/pdf/1706.03762.pdf"]
    assert manifest["summary"]["downloaded"] == 1
    assert manifest["summary"]["link-only"] == 1
    assert any(item.get("reason") == "video_resources_are_not_downloaded" for item in manifest["resources"])
    dumped = json.dumps(manifest, ensure_ascii=False)
    assert "Attention Is All You Need" in dumped


def test_bundle_downloads_github_repository_archive(tmp_path):
    repository = Resource(
        title="VAL: The Automatic Validation Tool for PDDL Planning",
        url="https://github.com/KCL-Planning/VAL",
        source="github",
        type="repository",
    )
    client = FakeClient()

    manifest = bundle_study_resources(tmp_path / "bundle", [repository], {"phases": []}, client=client)

    assert client.urls == ["https://codeload.github.com/KCL-Planning/VAL/zip/refs/heads/main"]
    assert manifest["summary"]["downloaded"] == 1
    assert manifest["resources"][0]["file"].endswith(".zip")


def test_bundle_snapshots_public_web_pages(tmp_path):
    docs = Resource(
        title="PDDL Reference",
        url="https://planning.wiki/ref/pddl",
        source="documentation",
        type="documentation",
    )
    client = FakeHtmlClient()

    manifest = bundle_study_resources(tmp_path / "bundle", [docs], {"phases": []}, client=client)

    assert client.urls == ["https://planning.wiki/ref/pddl"]
    assert manifest["summary"]["snapshotted"] == 1
    snapshot = tmp_path / "bundle" / manifest["resources"][0]["file"]
    assert snapshot.suffix == ".html"
    assert "open docs" in snapshot.read_text(encoding="utf-8")


def test_bundle_keeps_omitted_resources_in_full_library(tmp_path):
    selected = Resource(
        title="Target planning paper",
        url="https://arxiv.org/abs/2509.13351",
        source="arxiv",
        type="paper",
    )
    omitted_book = Resource(
        title="Automated Planning: Theory and Practice",
        url="https://www.automatedplanning.info/",
        source="book",
        type="book",
    )
    roadmap = {
        "phases": [{"resources": [selected.to_dict()]}],
        "resource_library": [
            {**selected.to_dict(), "route_status": "selected", "selected": True, "route_reason": "included-in-shortest-path"},
            {**omitted_book.to_dict(), "route_status": "omitted", "selected": False, "route_reason": "broad-detour"},
            {
                "title": "Focused prerequisite sprint",
                "url": "local://fields-study-flow-prerequisite-sprint",
                "source": "fields-study-flow",
                "type": "checklist",
                "route_status": "generated",
                "selected": True,
                "route_reason": "included-in-shortest-path",
            },
        ],
    }
    client = FakeClient()

    manifest = bundle_study_resources(tmp_path / "bundle", [selected, omitted_book], roadmap, client=client)

    assert manifest["summary"]["total"] == 3
    assert [item["title"] for item in manifest["resources"]] == [
        "Target planning paper",
        "Automated Planning: Theory and Practice",
        "Focused prerequisite sprint",
    ]
    assert manifest["resources"][1]["status"] == "link-only"
    assert manifest["resources"][1]["route_status"] == "omitted"
    assert manifest["resources"][2]["route_status"] == "generated"
    assert manifest["resources"][2]["reason"] == "generated_or_report_only_resource"
    assert "Automated Planning: Theory and Practice" in (tmp_path / "bundle" / "links.md").read_text(encoding="utf-8")
