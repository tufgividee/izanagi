
"""Build canonical project base."""

from __future__ import annotations

import base64
import hashlib
import json
import uuid
from datetime import UTC, datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from izanagi.manifest import manifest_project

FORMAT_VERSION = 1


def _izanagi_version() -> str | None:
    """Return the installed package version, if available."""
    try:
        return version("izanagi")
    except PackageNotFoundError:
        return None


def _format_bytes(data: bytes) -> str:
    """Represent file bytes as UTF-8 when possible, otherwise as Base64."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return "Base64-encoded binary file\n\n" + base64.b64encode(data).decode(
            "ascii"
        )


def _is_utf8(data: bytes) -> bool:
    """Return whether bytes can be decoded as UTF-8."""
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def _fence_for(content: str) -> str:
    """Choose a Markdown fence longer than any backtick run in the content."""
    longest = 0
    current = 0

    for character in content:
        if character == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0

    return "`" * max(3, longest + 1)


def _directory_structure(records: list[dict[str, Any]]) -> str:
    """Render a deterministic tree, pruning excluded directories without included descendants."""
    nodes: dict[str, dict[str, Any]] = {}

    for record in records:
        path = record["path"].rstrip("/")
        if not path:
            continue

        parts = path.split("/")
        for index in range(len(parts)):
            relative = "/".join(parts[: index + 1])
            is_explicit_record = index == len(parts) - 1
            existing = nodes.get(relative)

            if existing is None:
                nodes[relative] = {
                    "path": relative,
                    "name": parts[index],
                    "kind": (
                        record["kind"] if is_explicit_record else "directory"
                    ),
                    "included": (
                        bool(record["included"]) if is_explicit_record else False
                    ),
                    "explicit": is_explicit_record,
                }
            elif is_explicit_record:
                existing.update(
                    {
                        "kind": record["kind"],
                        "included": bool(record["included"]),
                        "explicit": True,
                    }
                )

    children: dict[str, list[str]] = {}
    for path in nodes:
        parent = path.rpartition("/")[0]
        children.setdefault(parent, []).append(path)

    for child_paths in children.values():
        child_paths.sort(key=lambda item: (nodes[item]["name"].casefold(), item))

    # A directory is visible if it is included, is not explicitly excluded,
    # or contains an included descendant that is a specific inclusion override.
    visible: set[str] = set()
    for path, node in nodes.items():
        if node["kind"] != "directory":
            if node["included"]:
                visible.add(path)
            continue

        descendants = [
            other
            for other in nodes
            if other.startswith(path + "/") and nodes[other]["included"]
        ]
        explicitly_excluded = node["explicit"] and not node["included"]
        if not explicitly_excluded or descendants:
            visible.add(path)

    lines: list[str] = []

    def render(parent: str, prefix: str = "") -> None:
        child_paths = [
            path
            for path in children.get(parent, [])
            if path in visible
        ]

        for index, path in enumerate(child_paths):
            node = nodes[path]
            is_last = index == len(child_paths) - 1
            connector = "└── " if is_last else "├── "
            name = node["name"]

            if node["kind"] == "directory":
                name += "/"

            lines.append(f"{prefix}{connector}{name}")
            if node["kind"] == "directory":
                render(path, prefix + ("    " if is_last else "│   "))

    render("")
    return "\n".join(lines) if lines else "(no included paths)"


def build_snapshot(project: Path, *, config: dict[str, Any]) -> dict[str, Any]:
    """Build base Markdown and a JSON-serializable manifest.

    Project code is never executed. Included file bytes are captured by
    manifest_project() and reused here for content, size, and SHA-256.
    Excluded files are not read or hashed.
    """
    inventory = manifest_project(project, config=config, capture_content=True)
    root = Path(inventory["project_root"])
    timestamp = datetime.now(UTC).isoformat()
    snapshot_id = str(uuid.uuid4())
    izanagi_version = _izanagi_version()

    records: list[dict[str, Any]] = []
    document_sections: list[tuple[str, str]] = []
    source_sections: list[tuple[str, str]] = []

    for original in inventory["files"]:
        record = dict(original)
        data = record.pop("_content", None)

        if (
            not record["included"]
            or record["kind"] in {"directory", "symlink", "unreadable"}
        ):
            record.pop("sha256", None)
            record.pop("encoding", None)
            if not record["included"]:
                record["size_bytes"] = None
            records.append(record)
            continue

        if data is None:
            record["included"] = False
            record["reason"] = "included file content was not captured"
            record["size_bytes"] = None
            record.pop("sha256", None)
            records.append(record)
            continue

        digest = hashlib.sha256(data).hexdigest()
        size = len(data)
        encoding = "utf-8" if _is_utf8(data) else "base64"

        record["size_bytes"] = size
        record["sha256"] = digest
        record["encoding"] = encoding
        records.append(record)

        content = _format_bytes(data)
        fence = _fence_for(content)
        section = (
            f"### `{record['path']}`\n\n"
            f"- Type: {record['kind']}\n"
            f"- Size: {size} bytes\n"
            f"- SHA-256: `{digest}`\n"
            f"- Encoding: {encoding}\n\n"
            f"{fence}\n{content}\n{fence}"
        )

        if record["kind"] == "documentation":
            document_sections.append((record["path"], section))
        else:
            source_sections.append((record["path"], section))

    records.sort(key=lambda item: item["path"])
    document_sections.sort(key=lambda item: item[0])
    source_sections.sort(key=lambda item: item[0])

    project_name = config.get("project", {}).get("name", "").strip()
    project_name = project_name or root.name

    preamble = config.get("preamble", {}).get("base_preamble", "").strip()
    header = [
        "# Izanagi Project — Base",
        "",
        f"- Project: {project_name}",
        f"- Base ID: `{snapshot_id}`",
        f"- Created: {timestamp}",
        f"- Project root: `{root}`",
        f"- Git root: `{inventory['git_root'] or 'not found'}`",
        f"- Base format version: {FORMAT_VERSION}",
        f"- Izanagi version: {izanagi_version or 'unavailable'}",
        "",
    ]
    if preamble:
        header.extend([preamble, ""])

    file_records = [record for record in records if record["kind"] != "directory"]
    included_records = [record for record in file_records if record["included"]]
    excluded_records = [record for record in file_records if not record["included"]]

    included_bytes = sum(record["size_bytes"] or 0 for record in included_records)
    known_sizes = [
        record["size_bytes"]
        for record in file_records
        if record["size_bytes"] is not None
    ]

    categories: dict[str, int] = {}
    for record in included_records:
        category = record["kind"]
        categories[category] = categories.get(category, 0) + 1

    inventory_lines = [
        "## Inventory Summary",
        "",
        f"- Discovered files: {len(file_records)}",
        f"- Included: {len(included_records)}",
        f"- Excluded: {len(excluded_records)}",
        f"- Included bytes: {included_bytes:,}",
        f"- Known file bytes: {sum(known_sizes):,}",
        "- Excluded file sizes: not measured",
        "",
        "### Included File Categories",
        "",
    ]

    for category, count in sorted(categories.items()):
        inventory_lines.append(f"- {category}: {count}")

    inventory_lines.extend(["", "### Inventory", ""])

    for record in records:
        status = "IN" if record["included"] else "OUT"
        size = (
            f"{record['size_bytes']:,} bytes"
            if record["size_bytes"] is not None
            else "size not measured"
        )
        inventory_lines.append(
            f"- [{status}] `{record['path']}` — {record['kind']}, {size}"
            + (f"; {record['reason']}" if not record["included"] else "")
        )

    document = "\n".join(
        header
        + inventory_lines
        + [
            "",
            "## Documentation",
            "",
            *[section for _, section in document_sections],
            "",
            "## Directory Structure",
            "",
            _directory_structure(records),
            "",
            "## Source and Configuration Files",
            "",
            *[section for _, section in source_sections],
            "",
        ]
    )

    manifest = {
        "format_version": FORMAT_VERSION,
        "izanagi_version": izanagi_version,
        "snapshot_id": snapshot_id,
        "created_at": timestamp,
        "project_name": project_name,
        "project_root": str(root),
        "git_root": inventory["git_root"],
        "summary": {
            "file_count": len(file_records),
            "included_count": len(included_records),
            "excluded_count": len(excluded_records),
            "included_bytes": included_bytes,
            "known_file_bytes": sum(known_sizes),
            "categories": categories,
        },
        "files": records,
    }

    return {"snapshot": document, "manifest": manifest}


def write_snapshot(
    base: dict[str, Any],
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write base.md and manifest.json to the output directory."""
    output_dir.mkdir(parents=True, exist_ok=True)

    snapshot_path = output_dir / "base.md"
    manifest_path = output_dir / "manifest.json"

    snapshot_path.write_text(base["snapshot"], encoding="utf-8")
    manifest_path.write_text(
        json.dumps(base["manifest"], indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return snapshot_path, manifest_path
