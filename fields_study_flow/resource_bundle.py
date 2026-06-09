from __future__ import annotations

import copy
import json
import os
import re
import mimetypes
import shutil
from pathlib import Path
from typing import Any, Callable
from urllib.parse import unquote, urlparse

from fields_study_flow.models import Resource


DOWNLOADABLE_EXTENSIONS = {
    ".csv",
    ".htm",
    ".html",
    ".ipynb",
    ".json",
    ".md",
    ".pdf",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
    ".zip",
}
SKIP_DOWNLOAD_TYPES = {"video"}
DISALLOWED_HOST_TERMS = ("z-lib", "zlibrary", "sci-hub", "scihub", "libgen", "annas-archive", "annasarchive")
COMMON_REUSABLE_EXTENSIONS = (".pdf", ".zip", ".ipynb", ".html", ".htm", ".md", ".txt", ".json", ".py")
ProgressCallback = Callable[[dict[str, Any]], None]


def bundle_study_resources(
    resource_dir: Path,
    resources: list[Resource],
    roadmap: dict[str, Any],
    *,
    bundle_scope: str = "all",
    timeout: float = 20.0,
    max_bytes: int = 80 * 1024 * 1024,
    client: Any | None = None,
    retries: int = 2,
    progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Copy or download the full study resource library into a private bundle.

    Shareable roadmap exports intentionally redact private local paths. This
    bundle is the companion local-only workspace: explicit local files are
    copied, direct open files are downloaded, public GitHub repositories are
    saved as archives, ordinary public pages are snapshotted when possible, and
    non-downloadable links are preserved in a manifest and links file.
    """

    resource_dir.mkdir(parents=True, exist_ok=True)
    bundle_scope = "selected" if str(bundle_scope).strip().lower() == "selected" else "all"
    bundled_resources = _bundle_resources(resources)
    bundle_total = len(bundled_resources)
    library_meta = _library_metadata_by_key(roadmap)
    entries: list[dict[str, Any]] = []
    used_names: set[str] = set()
    close_client = False
    http_client = client
    if http_client is None:
        try:
            import httpx

            http_client = httpx.Client(timeout=timeout, follow_redirects=True)
            close_client = True
        except Exception as exc:
            http_client = None
            entries.append(
                {
                    "title": "HTTP client unavailable",
                    "status": "failed",
                    "reason": f"http_client_unavailable: {exc}",
                }
            )

    try:
        for index, resource in enumerate(bundled_resources, start=1):
            _emit_progress(progress, {"event": "start", "index": index, "total": bundle_total, "title": resource.title})
            route_meta = library_meta.get(_resource_key(resource), {})
            if bundle_scope == "selected" and _is_omitted_route_resource(route_meta):
                entry = _link_only_route_entry(index, resource, route_meta)
            else:
                entry = _bundle_one_resource(
                    resource_dir,
                    index,
                    bundle_total,
                    resource,
                    http_client,
                    timeout,
                    max_bytes,
                    used_names,
                    max(0, retries),
                    progress,
                )
            entry.update(route_meta)
            if entry.get("status") == "link-only":
                entry["link_only_reason"] = entry.get("reason", "")
            entries.append(entry)
            _emit_progress(
                progress,
                {
                    "event": "finish",
                    "index": index,
                    "total": bundle_total,
                    "title": resource.title,
                    "status": entry.get("status", "unknown"),
                    "file": entry.get("file"),
                    "retryable": entry.get("retryable", False),
                    "attempts": entry.get("attempts", 0),
                },
            )
        bundled_keys = {_resource_key(resource) for resource in bundled_resources}
        entries.extend(_library_only_entries(resource_dir, roadmap, bundled_keys, used_names, len(bundled_resources) + 1))
    finally:
        if close_client and http_client is not None:
            http_client.close()

    manifest = {
        "resource_dir": str(resource_dir.resolve()),
        "bundle_scope": bundle_scope,
        "policy": (
            "Copies explicit local files, downloads direct/open files and GitHub archives, "
            "and saves public web pages as lightweight HTML snapshots. Videos and restricted "
            "pages stay as links."
        ),
        "summary": _summary(entries),
        "resources": entries,
    }
    manifest["download_manager"] = _download_manager(manifest)
    (resource_dir / "study_bundle_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (resource_dir / "README.md").write_text(_render_bundle_readme(manifest), encoding="utf-8")
    (resource_dir / "links.md").write_text(_render_links_md(manifest), encoding="utf-8")
    (resource_dir / manifest["download_manager"]["download_queue_file"]).write_text(
        json.dumps(_download_queue(manifest), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (resource_dir / manifest["download_manager"]["retry_file"]).write_text(_render_retry_md(manifest), encoding="utf-8")
    return manifest


def public_bundle_summary(manifest: dict[str, Any], *, report_dir: Path | None = None) -> dict[str, Any]:
    resource_dir = _manifest_resource_dir(manifest)
    return {
        "manifest_file": "study_bundle_manifest.json",
        "links_file": "links.md",
        "readme_file": "README.md",
        "download_manager": dict(manifest.get("download_manager", {})),
        "bundle_scope": manifest.get("bundle_scope", "all"),
        "policy": manifest.get("policy", ""),
        "summary": dict(manifest.get("summary", {})),
        "resources": [
            _public_bundle_entry(entry, resource_dir=resource_dir, report_dir=report_dir)
            for entry in manifest.get("resources", [])
            if isinstance(entry, dict)
        ],
    }


def attach_study_bundle(roadmap: dict[str, Any], manifest: dict[str, Any], *, report_dir: Path | None = None) -> dict[str, Any]:
    """Attach a shareable bundle summary to a roadmap.

    The full manifest is intentionally local-only because it contains the
    absolute resource directory. Reports only need the status summary, relative
    file names, public URLs, and failure reasons so users can see what was
    actually downloaded, snapshotted, or left as a link.
    """

    updated = copy.deepcopy(roadmap)
    updated["study_bundle"] = public_bundle_summary(manifest, report_dir=report_dir)
    return updated


def _public_bundle_entry(entry: dict[str, Any], *, resource_dir: Path | None = None, report_dir: Path | None = None) -> dict[str, Any]:
    allowed = {
        "index",
        "title",
        "source",
        "type",
        "url",
        "status",
        "route_status",
        "selected",
        "selected_phase",
        "route_reason",
        "reason",
        "link_only_reason",
        "file",
        "download_url",
        "snapshot_url",
        "retryable",
        "attempts",
        "size_bytes",
        "content_type",
    }
    public = {key: value for key, value in entry.items() if key in allowed and value not in {None, ""}}
    local_href = _local_href(entry, resource_dir=resource_dir, report_dir=report_dir)
    if local_href:
        public["local_href"] = local_href
    return public


def _manifest_resource_dir(manifest: dict[str, Any]) -> Path | None:
    value = manifest.get("resource_dir")
    if not value:
        return None
    try:
        return Path(str(value))
    except Exception:
        return None


def _local_href(entry: dict[str, Any], *, resource_dir: Path | None, report_dir: Path | None) -> str:
    file_name = entry.get("file")
    if not file_name or resource_dir is None or report_dir is None:
        return ""
    if str(entry.get("status", "")) not in {"copied", "downloaded", "snapshotted", "generated"}:
        return ""
    target = resource_dir / str(file_name)
    try:
        relative = os.path.relpath(target.resolve(), report_dir.resolve())
    except Exception:
        relative = str(file_name)
    return Path(relative).as_posix()


def _bundle_resources(resources: list[Resource]) -> list[Resource]:
    output: list[Resource] = []
    seen: set[tuple[str, str]] = set()
    for resource in resources:
        key = _resource_key(resource)
        if key in seen:
            continue
        seen.add(key)
        output.append(resource)
    return output


def _library_metadata_by_key(roadmap: dict[str, Any]) -> dict[tuple[str, str], dict[str, Any]]:
    metadata: dict[tuple[str, str], dict[str, Any]] = {}
    for item in roadmap.get("resource_library", []):
        if not isinstance(item, dict):
            continue
        key = (str(item.get("title", "")), str(item.get("url", "")))
        metadata[key] = {
            "route_status": item.get("route_status", "unknown"),
            "selected": item.get("selected", False),
            "selected_phase": item.get("selected_phase"),
            "route_reason": item.get("route_reason"),
        }
    return metadata


def _resource_key(resource: Resource) -> tuple[str, str]:
    public = resource.to_dict()
    return (str(public.get("title", "")), str(public.get("url", "")))


def _is_omitted_route_resource(route_meta: dict[str, Any]) -> bool:
    if not route_meta:
        return False
    return route_meta.get("selected") is False or route_meta.get("route_status") == "omitted"


def _link_only_route_entry(index: int, resource: Resource, route_meta: dict[str, Any]) -> dict[str, Any]:
    return {
        "index": index,
        "title": resource.title,
        "source": resource.source,
        "type": resource.type,
        "url": resource.to_dict().get("url", resource.url),
        "status": "link-only",
        "reason": route_meta.get("route_reason") or "omitted_from_shortest_path",
        "attempts": 0,
        "retryable": False,
    }


def _library_only_entries(
    resource_dir: Path,
    roadmap: dict[str, Any],
    bundled_keys: set[tuple[str, str]],
    used_names: set[str],
    start_index: int,
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in roadmap.get("resource_library", []):
        if not isinstance(item, dict):
            continue
        key = (str(item.get("title", "")), str(item.get("url", "")))
        if key in bundled_keys:
            continue
        if _is_generated_library_resource(item):
            index = start_index + len(entries)
            existing_entry = _existing_generated_resource_entry(resource_dir, index, item, used_names)
            if existing_entry is not None:
                existing_entry.update(
                    {
                        "route_status": item.get("route_status", "generated"),
                        "selected": item.get("selected", False),
                        "selected_phase": item.get("selected_phase"),
                        "route_reason": item.get("route_reason"),
                    }
                )
                entries.append(existing_entry)
                continue
            target = _target_path(resource_dir, index, str(item.get("title", "Generated resource")), ".md", used_names)
            target.write_text(_render_generated_resource_md(item), encoding="utf-8")
            entries.append(
                {
                    "index": index,
                    "title": item.get("title", "Generated resource"),
                    "source": item.get("source", "fields-study-flow"),
                    "type": item.get("type", "checklist"),
                    "url": item.get("url", ""),
                    "status": "generated",
                    "file": str(target.relative_to(resource_dir)),
                    "reason": "generated_report_resource_materialized",
                    "attempts": 0,
                    "retryable": False,
                    "route_status": item.get("route_status", "generated"),
                    "selected": item.get("selected", False),
                    "selected_phase": item.get("selected_phase"),
                    "route_reason": item.get("route_reason"),
                }
            )
            continue
        entries.append(
            {
                "index": None,
                "title": item.get("title", "Resource"),
                "source": item.get("source", "roadmap"),
                "type": item.get("type", "resource"),
                "url": item.get("url", ""),
                "status": "link-only",
                "reason": "generated_or_report_only_resource",
                "attempts": 0,
                "retryable": False,
                "route_status": item.get("route_status", "unknown"),
                "selected": item.get("selected", False),
                "selected_phase": item.get("selected_phase"),
                "route_reason": item.get("route_reason"),
            }
        )
    return entries


def _existing_generated_resource_entry(
    resource_dir: Path,
    index: int,
    item: dict[str, Any],
    used_names: set[str],
) -> dict[str, Any] | None:
    title = str(item.get("title", "Generated resource"))
    slug = _safe_slug(title)
    candidates = [
        resource_dir / f"{index:02d}-{slug}.md",
        *sorted(resource_dir.glob(f"{index:02d}-{slug}-*.md")),
        *sorted(resource_dir.glob(f"*-{slug}.md")),
        *sorted(resource_dir.glob(f"*-{slug}-*.md")),
    ]
    for path in candidates:
        if not path.exists() or not path.is_file():
            continue
        if path.name.lower() in used_names:
            continue
        used_names.add(path.name.lower())
        return {
            "index": index,
            "title": title,
            "source": item.get("source", "fields-study-flow"),
            "type": item.get("type", "checklist"),
            "url": item.get("url", ""),
            "status": "generated",
            "file": str(path.relative_to(resource_dir)),
            "reason": "existing_bundle_file_reused",
            "attempts": 0,
            "retryable": False,
            **_existing_file_meta(path),
        }
    return None


def _is_generated_library_resource(item: dict[str, Any]) -> bool:
    url = str(item.get("url", ""))
    source = str(item.get("source", ""))
    route_status = str(item.get("route_status", ""))
    return source == "fields-study-flow" or route_status == "generated" or url.startswith("local://fields-study-flow")


def _render_generated_resource_md(item: dict[str, Any]) -> str:
    title = str(item.get("title", "Generated resource"))
    lines = [
        f"# {title}",
        "",
        "This local file materializes a generated fields-study-flow resource so the study bundle is self-contained.",
        "",
        f"- Source: {item.get('source', 'fields-study-flow')}",
        f"- Type: {item.get('type', 'checklist')}",
        f"- Route status: {item.get('route_status', 'generated')}",
        f"- Route reason: {item.get('route_reason', 'generated-resource')}",
        "",
    ]
    for label, key in (("Learning key points", "learning_key_points"), ("Focus areas", "focus_areas"), ("Concepts", "concepts")):
        values = [str(value) for value in item.get(key, []) if str(value)]
        if not values:
            continue
        lines.extend([f"## {label}", ""])
        lines.extend(f"- {value}" for value in values)
        lines.append("")
    if str(item.get("url", "")):
        lines.extend(["## Bundle reference", "", f"- {item.get('url')}", ""])
    return "\n".join(lines)


def _bundle_one_resource(
    resource_dir: Path,
    index: int,
    total: int,
    resource: Resource,
    client: Any | None,
    timeout: float,
    max_bytes: int,
    used_names: set[str],
    retries: int,
    progress: ProgressCallback | None,
) -> dict[str, Any]:
    base = {
        "index": index,
        "title": resource.title,
        "source": resource.source,
        "type": resource.type,
        "url": resource.to_dict().get("url", resource.url),
        "attempts": 0,
        "retryable": False,
    }
    if resource.type in SKIP_DOWNLOAD_TYPES:
        return {**base, "status": "link-only", "reason": "video_resources_are_not_downloaded"}

    local_path = Path(resource.local_path).expanduser() if resource.local_path else None
    download_candidates, reason = _downloadable_candidates(resource)
    existing_entry = _existing_bundle_entry(resource_dir, index, resource, download_candidates, used_names, base)
    if existing_entry is not None:
        return existing_entry

    if local_path and local_path.exists() and local_path.is_file():
        target = _target_path(resource_dir, index, resource.title, local_path.suffix or ".resource", used_names)
        shutil.copy2(local_path, target)
        return {
            **base,
            "status": "copied",
            "file": str(target.relative_to(resource_dir)),
            "source_path": str(local_path.resolve()),
            "attempts": 1,
        }

    if client is None:
        if download_candidates:
            return {
                **base,
                "status": "failed",
                "download_url": download_candidates[0][0],
                "reason": "http_client_unavailable",
                "retryable": True,
            }
        return {**base, "status": "link-only", "reason": reason}

    failures: list[str] = []
    attempt_log: list[dict[str, Any]] = []
    max_attempts = retries + 1
    for downloadable_url, suffix in download_candidates:
        target = _target_path(resource_dir, index, resource.title, suffix or _suffix_for_resource(resource) or ".resource", used_names)
        for attempt in range(1, max_attempts + 1):
            _emit_progress(
                progress,
                {
                    "event": "attempt",
                    "action": "download",
                    "index": index,
                    "total": total,
                    "title": resource.title,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "url": downloadable_url,
                },
            )
            try:
                file_meta = _download_file(client, downloadable_url, target, timeout, max_bytes)
            except Exception as exc:
                message = str(exc)
                failures.append(f"{downloadable_url} attempt {attempt}/{max_attempts}: {message}")
                attempt_log.append({"url": downloadable_url, "attempt": attempt, "status": "failed", "error": message})
                if target.exists():
                    target.unlink()
                used_names.discard(target.name.lower())
                continue
            attempt_log.append({"url": downloadable_url, "attempt": attempt, "status": "succeeded"})
            return {
                **base,
                "status": "downloaded",
                "download_url": downloadable_url,
                "file": str(target.relative_to(resource_dir)),
                "attempts": len(attempt_log),
                "attempt_log": attempt_log,
                **file_meta,
            }

    if download_candidates and failures:
        return {
            **base,
            "status": "failed",
            "download_url": download_candidates[0][0],
            "reason": "; ".join(failures),
            "attempts": len(attempt_log),
            "attempt_log": attempt_log,
            "retryable": True,
        }

    if _can_snapshot_webpage(resource):
        target = _target_path(resource_dir, index, f"{resource.title}-snapshot", ".html", used_names)
        for attempt in range(1, max_attempts + 1):
            _emit_progress(
                progress,
                {
                    "event": "attempt",
                    "action": "snapshot",
                    "index": index,
                    "total": total,
                    "title": resource.title,
                    "attempt": attempt,
                    "max_attempts": max_attempts,
                    "url": resource.url.strip(),
                },
            )
            try:
                file_meta = _download_html_snapshot(client, resource.url.strip(), target, timeout, max_bytes)
            except Exception as exc:
                message = str(exc)
                failures.append(f"{resource.url.strip()} snapshot attempt {attempt}/{max_attempts}: {message}")
                attempt_log.append({"url": resource.url.strip(), "attempt": attempt, "status": "failed", "error": message, "action": "snapshot"})
                if target.exists():
                    target.unlink()
                used_names.discard(target.name.lower())
                continue
            attempt_log.append({"url": resource.url.strip(), "attempt": attempt, "status": "succeeded", "action": "snapshot"})
            return {
                **base,
                "status": "snapshotted",
                "file": str(target.relative_to(resource_dir)),
                "snapshot_url": resource.url.strip(),
                "reason": "saved_public_html_snapshot",
                "attempts": len(attempt_log),
                "attempt_log": attempt_log,
                **file_meta,
            }
        detail = "; ".join(failures) if failures else reason
        return {
            **base,
            "status": "link-only",
            "reason": f"{detail}; snapshot_failed",
            "attempts": len(attempt_log),
            "attempt_log": attempt_log,
            "retryable": True,
        }

    if failures:
        return {
            **base,
            "status": "failed",
            "download_url": download_candidates[0][0],
            "reason": "; ".join(failures),
            "attempts": len(attempt_log),
            "attempt_log": attempt_log,
            "retryable": True,
        }
    return {**base, "status": "link-only", "reason": reason}


def _downloadable_url(resource: Resource) -> tuple[str, str]:
    candidates, reason = _downloadable_candidates(resource)
    if not candidates:
        return "", reason
    return candidates[0][0], ""


def _downloadable_candidates(resource: Resource) -> tuple[list[tuple[str, str]], str]:
    url = resource.url.strip()
    if not url or url.startswith("local://"):
        return [], "local_resource_without_copyable_path"
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if parsed.scheme not in {"http", "https"}:
        return [], "unsupported_url_scheme"
    if any(term in host for term in DISALLOWED_HOST_TERMS):
        return [], "disallowed_source"
    if "youtube.com" in host or "youtu.be" in host or "bilibili.com" in host:
        return [], "video_or_streaming_platform"
    if host == "arxiv.org" and parsed.path.startswith("/abs/"):
        paper_id = parsed.path.rsplit("/", 1)[-1]
        return [(f"https://arxiv.org/pdf/{paper_id}.pdf", ".pdf")], ""
    if host == "arxiv.org" and parsed.path.startswith("/pdf/"):
        clean_path = parsed.path
        if not clean_path.endswith(".pdf"):
            clean_path += ".pdf"
        return [(f"https://arxiv.org{clean_path}", ".pdf")], ""
    github_raw = _github_raw_url(parsed)
    if github_raw:
        return [(github_raw, _suffix_for_url(github_raw) or _suffix_for_resource(resource))], ""
    github_archives = _github_archive_urls(parsed)
    if github_archives:
        return [(archive_url, ".zip") for archive_url in github_archives], ""
    suffix = _suffix_for_url(url)
    if suffix in DOWNLOADABLE_EXTENSIONS:
        return [(url, suffix)], ""
    return [], "not_a_direct_downloadable_file"


def _github_raw_url(parsed: Any) -> str:
    host = parsed.netloc.lower()
    if host == "raw.githubusercontent.com":
        return parsed.geturl()
    if host != "github.com":
        return ""
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 5 and parts[2] == "blob":
        owner, repo, _blob, ref = parts[:4]
        path = "/".join(parts[4:])
        return f"https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
    return ""


def _github_archive_urls(parsed: Any) -> list[str]:
    host = parsed.netloc.lower()
    if host != "github.com":
        return []
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 2:
        return []
    if len(parts) >= 3 and parts[2] == "blob":
        return []
    owner, repo = parts[:2]
    if len(parts) >= 4 and parts[2] == "tree":
        ref = "/".join(parts[3:])
        return [f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{ref}"]
    return [
        f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/main",
        f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/master",
    ]


def _download_file(client: Any, url: str, target: Path, timeout: float, max_bytes: int) -> dict[str, Any]:
    with client.stream("GET", url, timeout=timeout) as response:
        response.raise_for_status()
        content_type = str(response.headers.get("content-type", "")).lower()
        if "text/html" in content_type and _suffix_for_url(url) not in {".html", ".htm"}:
            raise RuntimeError("download_returned_html_instead_of_file")
        total = 0
        with target.open("wb") as handle:
            for chunk in response.iter_bytes():
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError(f"file_exceeds_limit_{max_bytes}_bytes")
                handle.write(chunk)
        return {"size_bytes": total, "content_type": content_type}


def _download_html_snapshot(client: Any, url: str, target: Path, timeout: float, max_bytes: int) -> dict[str, Any]:
    with client.stream("GET", url, timeout=timeout) as response:
        response.raise_for_status()
        content_type = str(response.headers.get("content-type", "")).lower()
        if "html" not in content_type and "text/plain" not in content_type:
            raise RuntimeError(f"snapshot_not_html: {content_type or 'unknown_content_type'}")
        total = 0
        with target.open("wb") as handle:
            for chunk in response.iter_bytes():
                if not chunk:
                    continue
                total += len(chunk)
                if total > max_bytes:
                    raise RuntimeError(f"file_exceeds_limit_{max_bytes}_bytes")
                handle.write(chunk)
        return {"size_bytes": total, "content_type": content_type}


def _can_snapshot_webpage(resource: Resource) -> bool:
    url = resource.url.strip()
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if parsed.scheme not in {"http", "https"}:
        return False
    if any(term in host for term in DISALLOWED_HOST_TERMS):
        return False
    if "youtube.com" in host or "youtu.be" in host or "bilibili.com" in host:
        return False
    return resource.type not in SKIP_DOWNLOAD_TYPES


def _suffix_for_resource(resource: Resource) -> str:
    if resource.type == "paper":
        return ".pdf"
    if resource.type == "notebook":
        return ".ipynb"
    if resource.type == "code":
        return ".py"
    return ".resource"


def _suffix_for_url(url: str) -> str:
    parsed = urlparse(url)
    path = unquote(parsed.path.lower())
    if path.endswith(".tar.gz"):
        return ".tar.gz"
    suffix = Path(path).suffix
    return suffix if suffix in DOWNLOADABLE_EXTENSIONS else ""


def _existing_bundle_entry(
    resource_dir: Path,
    index: int,
    resource: Resource,
    download_candidates: list[tuple[str, str]],
    used_names: set[str],
    base: dict[str, Any],
) -> dict[str, Any] | None:
    for path in _existing_bundle_candidates(resource_dir, index, resource, download_candidates):
        if not path.exists() or not path.is_file():
            continue
        if path.name.lower() in used_names:
            continue
        used_names.add(path.name.lower())
        status = _status_for_existing_file(resource, path)
        entry = {
            **base,
            "status": status,
            "file": str(path.relative_to(resource_dir)),
            "attempts": 0,
            "reason": "existing_bundle_file_reused",
            **_existing_file_meta(path),
        }
        if download_candidates and status == "downloaded":
            entry["download_url"] = download_candidates[0][0]
        if status == "snapshotted" and resource.url.strip():
            entry["snapshot_url"] = resource.url.strip()
        return entry
    return None


def _existing_bundle_candidates(
    resource_dir: Path,
    index: int,
    resource: Resource,
    download_candidates: list[tuple[str, str]],
) -> list[Path]:
    slug = _safe_slug(resource.title)
    suffixes = _reusable_suffixes(resource, download_candidates)
    candidates: list[Path] = []
    for suffix in suffixes:
        candidates.append(resource_dir / f"{index:02d}-{slug}{suffix}")
        candidates.extend(sorted(resource_dir.glob(f"{index:02d}-{slug}-*{suffix}")))
        candidates.extend(sorted(resource_dir.glob(f"{index:02d}-{slug}*{suffix}")))
        candidates.extend(sorted(resource_dir.glob(f"*-{slug}*{suffix}")))
    output: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate.resolve()).lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(candidate)
    return output


def _reusable_suffixes(resource: Resource, download_candidates: list[tuple[str, str]]) -> list[str]:
    suffixes: list[str] = []
    if resource.local_path:
        suffixes.append(Path(resource.local_path).suffix.lower())
    suffixes.extend(suffix.lower() for _url, suffix in download_candidates if suffix)
    suffixes.append(_suffix_for_resource(resource).lower())
    suffixes.extend(COMMON_REUSABLE_EXTENSIONS)
    return [suffix for suffix in dict.fromkeys(suffixes) if suffix]


def _status_for_existing_file(resource: Resource, path: Path) -> str:
    suffix = path.suffix.lower()
    if resource.local_path and suffix == Path(resource.local_path).suffix.lower():
        return "copied"
    if suffix in {".html", ".htm"}:
        return "snapshotted"
    return "downloaded"


def _existing_file_meta(path: Path) -> dict[str, Any]:
    content_type = mimetypes.guess_type(path.name)[0] or ""
    return {"size_bytes": path.stat().st_size, "content_type": content_type}


def _target_path(resource_dir: Path, index: int, title: str, suffix: str, used_names: set[str]) -> Path:
    base_stem = f"{index:02d}-{_safe_slug(title)}"
    stem = base_stem
    counter = 2
    name = f"{stem}{suffix}"
    while name.lower() in used_names or (resource_dir / name).exists():
        stem = f"{base_stem}-{counter}"
        name = f"{stem}{suffix}"
        counter += 1
    used_names.add(name.lower())
    return resource_dir / name


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value).strip("-").lower()
    return slug[:80] or "resource"


def _summary(entries: list[dict[str, Any]]) -> dict[str, int]:
    statuses = {"copied": 0, "downloaded": 0, "snapshotted": 0, "generated": 0, "link-only": 0, "failed": 0}
    downloaded_selected = 0
    downloaded_omitted = 0
    for entry in entries:
        status = str(entry.get("status", "failed"))
        statuses[status] = statuses.get(status, 0) + 1
        if status == "downloaded":
            if entry.get("route_status") == "omitted" or entry.get("selected") is False:
                downloaded_omitted += 1
            else:
                downloaded_selected += 1
    statuses["completed"] = (
        statuses.get("copied", 0)
        + statuses.get("downloaded", 0)
        + statuses.get("snapshotted", 0)
        + statuses.get("generated", 0)
    )
    statuses["retryable"] = sum(1 for entry in entries if entry.get("retryable"))
    statuses["total"] = len(entries)
    statuses["downloaded_selected"] = downloaded_selected
    statuses["downloaded_omitted"] = downloaded_omitted
    return statuses


def _download_manager(manifest: dict[str, Any]) -> dict[str, Any]:
    summary = manifest.get("summary", {})
    return {
        "download_queue_file": "download_queue.json",
        "retry_file": "retry_failed.md",
        "completed": int(summary.get("completed", 0)),
        "retryable": int(summary.get("retryable", 0)),
        "failed": int(summary.get("failed", 0)),
        "total": int(summary.get("total", 0)),
        "retry_note": "Rerun the same fields-study-flow command after fixing network or access issues; existing bundle files are kept.",
    }


def _download_queue(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "summary": manifest.get("summary", {}),
        "policy": manifest.get("policy", ""),
        "retry_file": manifest.get("download_manager", {}).get("retry_file", "retry_failed.md"),
        "resources": [_queue_entry(item) for item in manifest.get("resources", []) if isinstance(item, dict)],
    }


def _queue_entry(item: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "index",
        "title",
        "source",
        "type",
        "url",
        "status",
        "route_status",
        "selected",
        "file",
        "download_url",
        "snapshot_url",
        "retryable",
        "attempts",
        "reason",
        "size_bytes",
        "content_type",
    ]
    return {key: item[key] for key in keys if key in item and item[key] not in {None, ""}}


def _render_retry_md(manifest: dict[str, Any]) -> str:
    retryable = [item for item in manifest.get("resources", []) if isinstance(item, dict) and item.get("retryable")]
    lines = [
        "# Retry Failed Downloads",
        "",
        manifest.get("download_manager", {}).get("retry_note", "Rerun the same command after fixing network or access issues."),
        "",
    ]
    if not retryable:
        lines.extend(["No retryable failed resources.", ""])
        return "\n".join(lines)
    lines.extend(["## Retry Queue", ""])
    for item in retryable:
        lines.append(f"- **{item.get('title', 'Resource')}** [{item.get('status', 'unknown')}]")
        retry_url = item.get("download_url") or item.get("snapshot_url") or item.get("url")
        if retry_url:
            lines.append(f"  - Retry URL: {retry_url}")
        lines.append(f"  - Attempts: {item.get('attempts', 0)}")
        if item.get("reason"):
            lines.append(f"  - Last error: {item['reason']}")
    lines.append("")
    return "\n".join(lines)


def _render_links_md(manifest: dict[str, Any]) -> str:
    lines = [
        "# Study Resource Bundle",
        "",
        manifest["policy"],
        "",
        f"Download queue: `{manifest.get('download_manager', {}).get('download_queue_file', 'download_queue.json')}`",
        f"Retry failed: `{manifest.get('download_manager', {}).get('retry_file', 'retry_failed.md')}`",
        "",
        "## Resources",
        "",
    ]
    for item in manifest.get("resources", []):
        title = item.get("title", "Resource")
        status = item.get("status", "unknown")
        lines.append(f"- **{title}** [{status}]")
        if item.get("file"):
            lines.append(f"  - File: `{item['file']}`")
        if item.get("url"):
            lines.append(f"  - Link: {item['url']}")
        if item.get("download_url"):
            lines.append(f"  - Download URL: {item['download_url']}")
        if item.get("retryable"):
            lines.append("  - Retryable: yes")
        if item.get("attempts"):
            lines.append(f"  - Attempts: {item['attempts']}")
        if item.get("reason"):
            lines.append(f"  - Note: {item['reason']}")
    lines.append("")
    return "\n".join(lines)


def _render_bundle_readme(manifest: dict[str, Any]) -> str:
    summary = manifest.get("summary", {})
    total = int(summary.get("total", 0) or 0)
    completed = int(summary.get("completed", 0) or 0)
    percent = round((completed / total) * 100) if total else 0
    selected = [
        item
        for item in manifest.get("resources", [])
        if isinstance(item, dict) and (item.get("selected") is True or item.get("route_status") in {"selected", "generated"})
    ]
    supplemental = [
        item
        for item in manifest.get("resources", [])
        if isinstance(item, dict) and item not in selected
    ]
    lines = [
        "# 学习资料包",
        "",
        f"- 完成度：{completed} / {total}（{percent}%）",
        f"- 路线资料：{len(selected)}",
        f"- 补充资料：{len(supplemental)}",
        f"- 已下载：{summary.get('downloaded', 0)}",
        f"- 已复制：{summary.get('copied', 0)}",
        f"- 已快照：{summary.get('snapshotted', 0)}",
        f"- 仅保留链接：{summary.get('link-only', 0)}",
        f"- 失败：{summary.get('failed', 0)}",
        "",
        "## 如何开始",
        "",
        "1. 先打开报告目录中的 `roadmap.html`。",
        "2. 按学习中控台右侧任务向导完成解释、推导、复现和批判任务。",
        "3. 在报告的资料库中优先点击“打开本地资料”。",
        "4. 如果有失败项，查看 `retry_failed.md` 后重新运行同一条 fields-study-flow 命令。",
        "",
        "## 路线资料",
        "",
    ]
    lines.extend(_readme_resource_lines(selected))
    lines.extend(["", "## 补充资料", ""])
    lines.extend(_readme_resource_lines(supplemental))
    lines.extend(
        [
            "",
            "## 文件说明",
            "",
            "- `study_bundle_manifest.json`：机器可读清单。",
            "- `links.md`：所有资料的原始链接和下载备注。",
            "- `download_queue.json`：下载管理与重试队列。",
            "- `retry_failed.md`：失败项与重试说明。",
            "",
        ]
    )
    return "\n".join(lines)


def _readme_resource_lines(resources: list[dict[str, Any]]) -> list[str]:
    if not resources:
        return ["- 暂无。"]
    lines: list[str] = []
    for item in resources:
        title = item.get("title", "Resource")
        status = _readme_status_label(str(item.get("status", "unknown")))
        route = _readme_route_label(str(item.get("route_status", "unknown")))
        lines.append(f"- **{title}** [{status} / {route}]")
        if item.get("file"):
            lines.append(f"  - 本地文件：`{item['file']}`")
        elif item.get("url"):
            lines.append(f"  - 链接：{item['url']}")
        if item.get("reason"):
            lines.append(f"  - 备注：{_readme_reason_label(str(item['reason']))}")
    return lines


def _readme_status_label(status: str) -> str:
    return {
        "copied": "已复制",
        "downloaded": "已下载",
        "snapshotted": "已快照",
        "generated": "已生成",
        "link-only": "仅链接",
        "failed": "失败",
    }.get(status, status)


def _readme_route_label(route_status: str) -> str:
    return {
        "selected": "路线资料",
        "generated": "生成资料",
        "omitted": "补充资料",
    }.get(route_status, route_status)


def _readme_reason_label(reason: str) -> str:
    labels = {
        "existing_bundle_file_reused": "复用已有文件",
        "generated_report_resource_materialized": "已生成本地学习资料",
        "saved_public_html_snapshot": "已保存公开网页快照",
        "video_resources_are_not_downloaded": "视频资源不自动下载，仅保留链接",
        "local_resource_without_copyable_path": "本地资源没有可复制路径",
        "not_a_direct_downloadable_file": "不是可直接下载文件",
        "manual link only": "需要手动打开链接",
    }
    return labels.get(reason, reason)


def _emit_progress(progress: ProgressCallback | None, event: dict[str, Any]) -> None:
    if progress is not None:
        progress(event)
