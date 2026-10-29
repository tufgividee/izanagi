"""Build portable base snapshots of project files."""

from __future__ import annotations

import base64
import hashlib
import json
import re
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from izanagi.manifest import manifest_project

FORMAT_VERSION = 1


def _format_bytes(data: bytes) -> str:
    """Return UTF-8 text, or Base64 for binary data."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return (
            "[Binary content encoded as Base64]\n"
            + base64.b64encode(data).decode("ascii")
        )


def _is_utf8(data: bytes) -> bool:
    """Return whether bytes can be decoded as UTF-8."""
    try:
        data.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def _fence_for(content: str) -> str:
    """Choose a Markdown code fence longer than any run in content."""
    longest = max(
        (len(match.group(0)) for match in re.finditer(r"`+", content)),
        default=0,
    )
    return "`" * max(3, longest + 1)


def _directory_structure(records: list[dict[str, Any]]) -> str:
    """Build a deterministic tree from manifest records."""
    tree: dict[str, Any] = {}

    for record in records:
        path = record["path"].rstrip("/")
        if not path:
            continue

        parts = path.split("/")
        current = tree

        for part in parts:
            current = current.setdefault(part, {})

    lines: list[str] = []

    def walk(node: dict[str, Any], prefix: str = "") -> None:
        items = sorted(node.items())
        for index, (name, children) in enumerate(items):
            last = index == len(items) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{name}")
            if children:
                walk(children, prefix + ("    " if last else "│   "))

    walk(tree)
    return "\n".join(lines)


def _filter_markdown(content: str, config: dict[str, Any]) -> str:
    """Apply configured Markdown embedded-media filtering."""
    settings = config.get("markdown", {})
    if not settings.get("strip_embedded_media", False):
        return content

    preserve_alt = settings.get("preserve_alt_text", True)
    preserve_reference = settings.get("preserve_image_reference", True)

    # Replace data-URI payloads in Markdown image destinations.
    # Example: ![diagram](data:image/png;base64,AAAA...)
    data_uri_pattern = re.compile(
        r"data:[^,\s)]+(?:;[^,\s)]*)*;base64,[A-Za-z0-9+/=\r\n]+",
        re.IGNORECASE,
    )

    def replace_inline_image(match: re.Match[str]) -> str:
        alt = match.group("alt")
        destination = match.group("destination")
        title = match.group("title") or ""

        if destination.lower().startswith("data:"):
            if preserve_alt:
                if preserve_reference:
                    return f"![{alt}](embedded-media-removed){title}"
                return f"[Image: {alt}]"
            if preserve_reference:
                return "(embedded-media-removed)"
            return "[embedded media removed]"

        return match.group(0)

    inline_image_pattern = re.compile(
        r"!\[(?P<alt>[^\]]*)\]"
        r"\((?P<destination><[^>]*>|[^)\s]+)"
        r"(?P<title>\s+(['\"]).*?\4)?\)",
    )

    content = inline_image_pattern.sub(replace_inline_image, content)

    # Handle raw HTML img tags containing base64 data URIs.
    def replace_html_image(match: re.Match[str]) -> str:
        tag = match.group(0)
        src_match = re.search(
            r"""src\s*=\s*(["'])(.*?)\1""",
            tag,
            re.IGNORECASE | re.DOTALL,
        )
        if not src_match or not src_match.group(2).lower().startswith("data:"):
            return tag

        alt_match = re.search(
            r"""alt\s*=\s*(["'])(.*?)\1""",
            tag,
            re.IGNORECASE | re.DOTALL,
        )
        alt = alt_match.group(2) if alt_match else ""

        if preserve_alt and alt:
            if preserve_reference:
                return f'<img alt="{alt}" src="embedded-media-removed">'
            return f"[Image: {alt}]"

        return "[embedded media removed]"

    content = re.sub(
        r"<img\b[^>]*>",
        replace_html_image,
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    # Remove standalone base64 data URI payloads that may have been pasted
    # directly into Markdown, without an image wrapper.
    content = data_uri_pattern.sub("[embedded media removed]", content)

    return content


def _notebook_source(source: Any) -> str:
    """Normalize a Jupyter cell source into text."""
    if isinstance(source, str):
        return source
    if isinstance(source, list) and all(isinstance(item, str) for item in source):
        return "".join(source)
    return ""


def _filter_notebook(content: str, config: dict[str, Any]) -> str:
    """Apply configured notebook cell, output, and execution-count filters."""
    settings = config.get("ipynb", {})
    include_source = settings.get("include_source", True)
    include_outputs = settings.get("include_outputs", False)
    include_execution_counts = settings.get("include_execution_counts", False)

    try:
        notebook = json.loads(content)
    except json.JSONDecodeError:
        # Keep malformed notebook content visible rather than silently losing it.
        return content

    if not isinstance(notebook, dict):
        return content

    cells = notebook.get("cells")
    if not isinstance(cells, list):
        return content

    filtered_cells: list[Any] = []

    for cell in cells:
        if not isinstance(cell, dict):
            filtered_cells.append(cell)
            continue

        filtered_cell = dict(cell)

        if not include_source:
            filtered_cell.pop("source", None)
        else:
            # Keep a stable, readable JSON representation of cell source.
            if "source" in filtered_cell:
                filtered_cell["source"] = _notebook_source(filtered_cell["source"])

        if not include_outputs:
            filtered_cell.pop("outputs", None)

        if not include_execution_counts:
            filtered_cell.pop("execution_count", None)

        # Markdown cell text may contain embedded media and should use the
        # same Markdown filtering settings as standalone Markdown files.
        if (
            include_source
            and filtered_cell.get("cell_type") == "markdown"
            and isinstance(filtered_cell.get("source"), str)
        ):
            filtered_cell["source"] = _filter_markdown(
                filtered_cell["source"], config
            )

        filtered_cells.append(filtered_cell)

    notebook["cells"] = filtered_cells

    return json.dumps(notebook, indent=2, ensure_ascii=False) + "\n"


def _filter_content(path: str, content: bytes, config: dict[str, Any]) -> str:
    """Decode and filter content according to its file type."""
    text = _format_bytes(content)

    # Filtering applies to UTF-8 text only. Binary files retain the standard
    # Base64 representation produced by _format_bytes().
    if not _is_utf8(content):
        return text

    suffix = Path(path).suffix.lower()

    if suffix in {".md", ".markdown"}:
        return _filter_markdown(text, config)

    if suffix == ".ipynb":
        return _filter_notebook(text, config)

    return text


def build_snapshot(
    project: Path,
    *,
    config: dict[str, Any],
    izanagi_version: str | None = None,
) -> dict[str, Any]:
    """Build a base snapshot and JSON manifest for a project."""
    root = project.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Project path is not a directory: {root}")

    inventory = manifest_project(root, config=config, capture_content=True)

    timestamp = datetime.now(UTC).isoformat()
    snapshot_id = str(uuid.uuid4())

    records: list[dict[str, Any]] = []
    document_sections: list[tuple[str, str]] = []
    source_sections: list[tuple[str, str]] = []

    for record in inventory["files"]:
        item = {key: value for key, value in record.items() if key != "_content"}
        records.append(item)

        if not record.get("included") or record.get("kind") in {
            "directory",
            "symlink",
            "unreadable",
        }:
            continue

        content = record.get("_content")
        if not isinstance(content, bytes):
            continue

        filtered_content = _filter_content(record["path"], content, config)
        fence = _fence_for(filtered_content)

        section = "\n".join(
            [
                f"### `{record['path']}`",
                "",
                f"- Type: {record['kind']}",
                f"- Size: {record['size_bytes']} bytes",
                f"- SHA-256: `{record['sha256']}`",
                f"- Encoding: {'utf-8' if _is_utf8(content) else 'base64'}",
                "",
                fence,
                filtered_content,
                fence,
                "",
            ]
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