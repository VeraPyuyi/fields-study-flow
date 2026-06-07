from __future__ import annotations

import copy
import json
import re
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
ProgressCallback = Callable[[dict[str, Any]], None]


def bundle_study_resources(
    resource_dir: Path,
    resources: list[Resource],
    roadmap: dict[str, Any],
    *,
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
            entry.update(library_meta.get(_resource_key(resource), {}))
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
        entries.extend(_library_only_entries(roadmap, bundled_keys))
    finally:
        if close_client and http_client is not None:
            http_client.close()

    manifest = {
        "resource_dir": str(resource_dir.resolve()),
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
    (resource_dir / "links.md").write_text(_render_links_md(manifest), encoding="utf-8")
    (resource_dir / manifest["download_manager"]["download_queue_file"]).write_text(
        json.dumps(_download_queue(manifest), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (resource_dir / manifest["download_manager"]["retry_file"]).write_text(_render_retry_md(manifest), encoding="utf-8")
    return manifest


def attach_study_bundle(roadmap: dict[str, Any], manifest: dict[str, Any]) -> dict[str, Any]:
    """Attach a shareable bundle summary to a roadmap.

    The full manifest is intentionally local-only because it contains the
    absolute resource directory. Reports only need the status summary, relative
    file names, public URLs, and failure reasons so users can see what was
    actually downloaded, snapshotted, or left as a link.
    """

    updated = copy.deepcopy(roadmap)
    updated["study_bundle"] = public_bundle_summary(manifest)
    return updated


def public_bundle_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest_file": "study_bundle_manifest.json",
        "links_file": "links.md",
        "download_manager": dict(manifest.get("download_manager", {})),
        "policy": manifest.get("policy", ""),
        "summary": dict(manifest.get("summary", {})),
        "resources": [
            _public_bundle_entry(entry)
            for entry in manifest.get("resources", [])
            if isinstance(entry, dict)
        ],
    }


def _public_bundle_entry(entry: dict[str, Any]) -> dict[str, Any]:
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
        "file",
        "download_url",
        "snapshot_url",
        "retryable",
        "attempts",
        "size_bytes",
        "content_type",
    }
    return {key: value for key, value in entry.items() if key in allowed and value not in {None, ""}}


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


def _library_only_entries(roadmap: dict[str, Any], bundled_keys: set[tuple[str, str]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in roadmap.get("resource_library", []):
        if not isinstance(item, dict):
            continue
        key = (str(item.get("title", "")), str(item.get("url", "")))
        if key in bundled_keys:
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

    download_candidates, reason = _downloadable_candidates(resource)
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


def _target_path(resource_dir: Path, index: int, title: str, suffix: str, used_names: set[str]) -> Path:
    base_stem = f"{index:02d}-{_safe_slug(title)}"
    stem = base_stem
    counter = 2
    name = f"{stem}{suffix}"
    while name.lower() in used_names:
        stem = f"{base_stem}-{counter}"
        name = f"{stem}{suffix}"
        counter += 1
    used_names.add(name.lower())
    return resource_dir / name


def _safe_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", value).strip("-").lower()
    return slug[:80] or "resource"


def _summary(entries: list[dict[str, Any]]) -> dict[str, int]:
    statuses = {"copied": 0, "downloaded": 0, "snapshotted": 0, "link-only": 0, "failed": 0}
    for entry in entries:
        status = str(entry.get("status", "failed"))
        statuses[status] = statuses.get(status, 0) + 1
    statuses["completed"] = statuses.get("copied", 0) + statuses.get("downloaded", 0) + statuses.get("snapshotted", 0)
    statuses["retryable"] = sum(1 for entry in entries if entry.get("retryable"))
    statuses["total"] = len(entries)
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


def _emit_progress(progress: ProgressCallback | None, event: dict[str, Any]) -> None:
    if progress is not None:
        progress(event)
