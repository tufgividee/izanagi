"""Build incremental project updates relative to a saved base snapshot."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from izanagi.base import (
    FORMAT_VERSION,
    _fence_for,
    _filter_content,
    _is_utf8,
)
from izanagi.manifest import manifest_project


def _read_manifest(path: Path) -> dict[str, Any] | None:
    """Read a manifest, returning None when the file does not exist."""
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise TypeError(f"Invalid snapshot manifest: {path}")
    return data


def _find_base(
    output_root: Path,
    *,
    project_root: str,
    base_id: str | None,
) -> dict[str, Any]:
    """Find a saved base manifest, preferring the newest when no ID is given."""
    candidates: list[dict[str, Any]] = []

    latest_manifest = _read_manifest(output_root / "manifest.json")
    if latest_manifest is not None:
        candidates.append(latest_manifest)

    bases_dir = output_root / "bases"
    if bases_dir.is_dir():
        for manifest_path in sorted(bases_dir.glob("*/manifest.json")):
            manifest = _read_manifest(manifest_path)
            if manifest is not None:
                candidates.append(manifest)

    candidates = [
        item
        for item in candidates
        if item.get("project_root") == project_root
        and item.get("format_version") == FORMAT_VERSION
    ]

    if base_id is not None:
        matches = [
            item for item in candidates
            if item.get("snapshot_id") == base_id
        ]
        if not matches:
            raise ValueError(
                f"Base snapshot '{base_id}' was not found for project "
                f"{project_root}. Create a base with 'izanagi base' first."
            )
        return matches[0]

    if not candidates:
        raise ValueError(
            f"No saved base snapshot found for {project_root}. "
            "Create one with 'izanagi base' first."
        )

    return max(candidates, key=lambda item: item.get("created_at", ""))


def _included_files(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Index included regular files by their project-relative paths."""
    return {
        record["path"]: record
        for record in manifest.get("files", [])
        if record.get("included")
        and record.get("kind") not in {"directory", "symlink", "unreadable"}
    }


def build_delta(
    project: Path,
    *,
    config: dict[str, Any],
    output_root: Path,
    base_id: str | None = None,
) -> dict[str, Any]:
    """Compare current included-file state with a saved base manifest."""
    root = project.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Project path is not a directory: {root}")

    base = _find_base(
        output_root.resolve(),
        project_root=str(root),
        base_id=base_id,
    )

    current = manifest_project(root, config=config, capture_content=True)

    # Never infer deletions from a scan known to be incomplete.
    scan_errors = [
        record
        for record in current["files"]
        if record.get("kind") == "unreadable"
        or str(record.get("reason", "")).startswith(
            "directory traversal error:"
        )
    ]
    if scan_errors:
        paths = ", ".join(record["path"] for record in scan_errors[:5])
        raise ValueError(
            "Delta aborted because the project scan was incomplete "
            f"({paths}). Resolve the errors and try again."
        )

    base_files = _included_files(base)
    current_files = _included_files(current)

    changes: list[dict[str, Any]] = []
    content_by_path: dict[str, bytes] = {}

    for path in sorted(current_files):
        record = current_files[path]
        previous = base_files.get(path)

        action = (
            "added"
            if previous is None
            else "modified"
            if previous.get("sha256") != record.get("sha256")
            else None
        )
        if action is None:
            continue

        content = record.get("_content")
        if not isinstance(content, bytes):
            raise TypeError(f"Could not capture current file contents: {path}")

        entry = {
            key: value
            for key, value in record.items()
            if key != "_content"
        }
        entry["action"] = action
        entry["previous_sha256"] = (
            previous.get("sha256") if previous is not None else None
        )
        changes.append(entry)
        content_by_path[path] = content

    for path in sorted(set(base_files) - set(current_files)):
        previous = base_files[path]
        changes.append(
            {
                "path": path,
                "action": "deleted",
                "previous_sha256": previous.get("sha256"),
            }
        )

    changes.sort(key=lambda item: (item["path"], item["action"]))

    delta_id = str(uuid.uuid4())
    timestamp = datetime.now(UTC).isoformat()
    project_name = (
        config.get("project", {}).get("name", "").strip() or root.name
    )

    preamble = config.get("preamble", {}).get(
        "incremental_preamble", ""
    ).strip()
    if preamble:
        preamble = preamble.format(base_snapshot_id=base["snapshot_id"])

    lines = [
        "# Izanagi Project — Delta",
        "",
        f"- Project: {project_name}",
        f"- Delta ID: `{delta_id}`",
        f"- Created: {timestamp}",
        f"- Project root: `{root}`",
        f"- Base snapshot ID: `{base['snapshot_id']}`",
        f"- Snapshot format version: {FORMAT_VERSION}",
        "",
    ]
    if preamble:
        lines.extend([preamble, ""])

    counts = {
        action: sum(change["action"] == action for change in changes)
        for action in ("added", "modified", "deleted")
    }
    unchanged_count = sum(
        path in base_files
        and base_files[path].get("sha256") == record.get("sha256")
        for path, record in current_files.items()
    )

    lines.extend(
        [
            "## Change Summary",
            "",
            f"- Added: {counts['added']}",
            f"- Modified: {counts['modified']}",
            f"- Deleted: {counts['deleted']}",
            f"- Unchanged: {unchanged_count}",
            "",
            "## Changes",
            "",
        ]
    )

    if not changes:
        lines.append("No included-file changes detected.")
    else:
        for change in changes:
            path = change["path"]
            action = change["action"]
            lines.extend([f"### {action.title()}: `{path}`", ""])

            if action == "deleted":
                lines.extend(
                    [
                        "- Previous SHA-256: "
                        f"`{change.get('previous_sha256') or 'unavailable'}`",
                        "",
                    ]
                )
                continue

            if action == "modified":
                lines.append(
                    "- Previous SHA-256: "
                    f"`{change.get('previous_sha256') or 'unavailable'}`"
                )

            content = content_by_path[path]
            filtered_content = _filter_content(path, content, config)
            fence = _fence_for(filtered_content)

            lines.extend(
                [
                    f"- Current SHA-256: `{change['sha256']}`",
                    f"- Size: {change['size_bytes']} bytes",
                    f"- Encoding: {'utf-8' if _is_utf8(content) else 'base64'}",
                    "",
                    fence,
                    filtered_content,
                    fence,
                    "",
                ]
            )

    document = "\n".join(lines).rstrip() + "\n"

    delta_manifest = {
        "format_version": FORMAT_VERSION,
        "izanagi_version": base.get("izanagi_version"),
        "delta_id": delta_id,
        "created_at": timestamp,
        "project_name": project_name,
        "project_root": str(root),
        "base_snapshot_id": base["snapshot_id"],
        "summary": {
            "added_count": counts["added"],
            "modified_count": counts["modified"],
            "deleted_count": counts["deleted"],
            "unchanged_count": unchanged_count,
        },
        "changes": changes,
    }

    return {"delta": document, "manifest": delta_manifest}


def write_delta(
    delta: dict[str, Any],
    output_root: Path,
) -> tuple[Path, Path]:
    """Write a delta document and manifest into a unique directory."""
    delta_id = delta["manifest"]["delta_id"]
    output_dir = output_root / delta_id
    output_dir.mkdir(parents=True, exist_ok=False)

    delta_path = output_dir / "delta.md"
    manifest_path = output_dir / "manifest.json"

    delta_path.write_text(delta["delta"], encoding="utf-8")
    manifest_path.write_text(
        json.dumps(delta["manifest"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return delta_path, manifest_path