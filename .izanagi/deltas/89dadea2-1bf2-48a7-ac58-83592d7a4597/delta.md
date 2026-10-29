# Izanagi Project — Delta

- Project: izanagi
- Delta ID: `89dadea2-1bf2-48a7-ac58-83592d7a4597`
- Created: 2026-10-28T17:20:06.177698+00:00
- Project root: `/run/media/xiaonan/nn120gssd/career_build/ai/izanagi`
- Base snapshot ID: `f9b99056-8fa3-48fd-ae4d-c1d4423a6ad2`
- Snapshot format version: 1

# Izanagi Project Context — Incremental Snapshot

This is an Izanagi incremental snapshot created to streamline project
synchronization and communication with AI assistants.

Base snapshot ID: f9b99056-8fa3-48fd-ae4d-c1d4423a6ad2

This document contains updates relative to the referenced base snapshot.
Interpret it together with that base context.

## Change Summary

- Added: 1
- Modified: 3
- Deleted: 0
- Unchanged: 13

## Changes

### Modified: `.izanagi/config.toml`

- Previous SHA-256: `2e2e07cbce122165ad6579c48c967a46356142ea2c3b1c34509b9eee45ac619c`
- Current SHA-256: `18246e0f39c6e9a65ba22b5698901d0cce77d032850ec4b4fde68c360962045c`
- Size: 1608 bytes
- Encoding: utf-8

```
[project]
name = ""
root = "."
output_dir = ".izanagi"

[scan]
include_hidden_files = true

[scan.inclusions]
rules = [
    "experiments/",
    "*.ipynb",
    "/special_config.json",
    "*.py",
    "*.c",
    "*.cpp",
    "*.h",
    "*.rs",
    "*.sv",
    "*.md",
    "*.rst",
    "*.txt",
    "pyproject.toml",
    "requirements.txt",
    "uv.lock",
    "Makefile",
    "LICENSE",
    "Dockerfile",
    ".gitignore",
    "*.toml",
]

[scan.exclusions]
rules = [
    ".git/",
    ".venv/",
    "__pycache__/",
    "*.pyc",
    "*.log",
    ".DS_Store",
    ".pytest_cache/",
    ".ruff_cache/",
    "uv.lock",
    ".pytest_cache/",
    ".ruff_cache",
]

[preamble]
base_preamble = """
# Izanagi Project Context — Base Snapshot

This document is an Izanagi snapshot created to streamline project
synchronization and communication with AI assistants.

It captures the project's structure, relevant files, configuration,
and recorded state at a specific point in time. It serves as the base
context for ongoing discussion and future project work.

The content below describes the project as captured, not necessarily
its current state.
"""

incremental_preamble = """
# Izanagi Project Context — Incremental Snapshot

This is an Izanagi incremental snapshot created to streamline project
synchronization and communication with AI assistants.

Base snapshot ID: {base_snapshot_id}

This document contains updates relative to the referenced base snapshot.
Interpret it together with that base context.
"""

[context]
# Reserved for future segmentation. Do not silently truncate snapshots.
char_limit = 5000

```

### Modified: `src/izanagi/__init__.py`

- Previous SHA-256: `60854c5d4e102a4702d5fa213538e5674f3cd4d53613e887fb219274fb019e56`
- Current SHA-256: `19c7f8cb41aa6611624b2bde84826e9cb79209aa122dcf0d9ad5b53eb213e926`
- Size: 7381 bytes
- Encoding: utf-8

```
"""Izanagi: persistent snapshots for software engineering."""

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

from izanagi.base import build_snapshot, write_snapshot
from izanagi.clipboard import copy_to_clipboard
from izanagi.config import initialize_project, load_project_config
from izanagi.delta import build_delta, write_delta
from izanagi.manifest import manifest_project


def _update_current(source: Path, output_root: Path) -> Path:
    """Atomically publish the latest successful Izanagi output as current.md."""
    output_root.mkdir(parents=True, exist_ok=True)
    current_path = output_root / "current.md"

    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=".current-",
        suffix=".tmp",
        dir=output_root,
    )
    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(file_descriptor, "wb") as temporary_file:
            temporary_file.write(source.read_bytes())
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, current_path)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise

    return current_path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="izanagi",
        description="Build reliable, local project context.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    for command, help_text in (
        ("init", "Initialize project-local Izanagi configuration."),
        ("manifest", "Inspect project files and inclusion decisions."),
        ("base", "Create a full baseline snapshot."),
        ("delta", "Create an incremental update relative to a base."),
    ):
        command_parser = subparsers.add_parser(command, help=help_text)
        command_parser.add_argument(
            "--project",
            type=Path,
            default=Path.cwd(),
            help="Project directory (defaults to the current directory).",
        )

        if command in {"base", "delta"}:
            command_parser.add_argument(
                "--output",
                type=Path,
                help=(
                    "Output directory. Defaults to the configured Izanagi "
                    "output directory."
                ),
            )
            command_parser.add_argument(
                "--copy",
                action="store_true",
                help="Copy the generated output to the clipboard.",
            )

        if command == "delta":
            command_parser.add_argument(
                "--base",
                help="Base snapshot ID (defaults to the latest saved base).",
            )

    args = parser.parse_args()

    try:
        if args.command == "init":
            config_path = initialize_project(args.project)
            print("Izanagi project initialized.")
            print(f"Configuration: {config_path}")
            return

        project = args.project.expanduser().resolve()
        if not project.is_dir():
            raise ValueError(f"Project directory does not exist: {project}")

        config = load_project_config(project)

        if args.command == "manifest":
            result = manifest_project(project, config=config)

            print(f"Project root: {result['project_root']}")
            print(f"Git root:     {result['git_root'] or '(not found)'}")
            print()

            for record in result["files"]:
                marker = "IN " if record["included"] else "OUT"
                size = record["size_bytes"]
                size_text = (
                    f"{size:>10,} B" if size is not None else "   unknown"
                )
                print(
                    f"{marker:>3} {size_text}  "
                    f"{record['path']} [{record['kind']}]"
                )
                if not record["included"]:
                    print(f"    Reason: {record['reason']}")

            summary = result["summary"]
            print("\nSummary")
            print(f"  Files:           {summary['file_count']}")
            print(f"  Included:        {summary['included_count']}")
            print(f"  Excluded:        {summary['excluded_count']}")
            print(f"  Included size:   {summary['included_bytes']:,} bytes")
            print(f"  Known file size: {summary['total_bytes']:,} bytes")
            return

        configured_output = (
            project / config["project"].get("output_dir", ".izanagi")
        ).resolve()

        output_root = (
            args.output.expanduser().resolve()
            if args.output
            else configured_output
        )

        if args.command == "base":
            snapshot = build_snapshot(project, config=config)

            base_id = snapshot["manifest"]["snapshot_id"]
            archive_dir = output_root / "bases" / base_id

            archived_snapshot_path, _ = write_snapshot(snapshot, archive_dir)

            manifest_path = output_root / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    snapshot["manifest"],
                    indent=2,
                    ensure_ascii=False,
                )
                + "\n",
                encoding="utf-8",
            )

            current_path = _update_current(archived_snapshot_path, output_root)

            if args.copy:
                copy_to_clipboard(current_path.read_text(encoding="utf-8"))

            print("Base snapshot created successfully.")
            print(f"Current:  {current_path.resolve()}")
            print(f"Manifest: {manifest_path.resolve()}")
            print(f"Archive:  {archive_dir.resolve()}")
            print(f"Base ID:  {base_id}")
            if args.copy:
                print("Copied base to clipboard.")
            return

        if args.command == "delta":
            delta = build_delta(
                project,
                config=config,
                output_root=configured_output,
                base_id=args.base,
            )

            delta_output_root = (
                output_root / "deltas"
                if not args.output
                else output_root
            )
            delta_path, manifest_path = write_delta(delta, delta_output_root)

            current_path = _update_current(delta_path, configured_output)

            if args.copy:
                copy_to_clipboard(current_path.read_text(encoding="utf-8"))

            summary = delta["manifest"]["summary"]
            print("Delta created successfully.")
            print(f"Current:  {current_path.resolve()}")
            print(f"Delta:    {delta_path.resolve()}")
            print(f"Manifest: {manifest_path.resolve()}")
            print(f"Delta ID: {delta['manifest']['delta_id']}")
            print(f"Base ID:  {delta['manifest']['base_snapshot_id']}")
            print(
                "Changes:  "
                f"+{summary['added_count']} "
                f"~{summary['modified_count']} "
                f"-{summary['deleted_count']}"
            )
            if args.copy:
                print("Copied delta to clipboard.")

    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as error:
        print(f"izanagi: error: {error}", file=sys.stderr)
        raise SystemExit(2) from error


if __name__ == "__main__":
    main()
```

### Added: `src/izanagi/clipboard.py`

- Current SHA-256: `48beeb68485c1566dc559f901da43d44c6ca6e05887f5b9728f771012f00a9ed`
- Size: 1570 bytes
- Encoding: utf-8

```

"""Cross-platform clipboard support for Izanagi."""

from __future__ import annotations

import platform
import shutil
import subprocess
from pathlib import Path


def copy_to_clipboard(content: str) -> None:
    """Copy text to the system clipboard on Linux, macOS, or Windows."""
    system = platform.system()

    if system == "Linux":
        if shutil.which("wl-copy"):
            command = ["wl-copy"]
        elif shutil.which("xclip"):
            command = ["xclip", "-selection", "clipboard"]
        elif shutil.which("xsel"):
            command = ["xsel", "--clipboard", "--input"]
        else:
            raise RuntimeError(
                "No supported clipboard utility found. "
                "Install wl-clipboard (Wayland) or xclip (X11)."
            )

    elif system == "Darwin":
        command = ["pbcopy"]

    elif system == "Windows":
        command = ["clip"]

    else:
        raise RuntimeError(
            f"Unsupported operating system: {system}"
        )

    subprocess.run(
        command,
        input=content,
        text=True,
        encoding="utf-8",
        check=True,
    )


def copy_current(output_root: Path) -> Path:
    """Copy the current Izanagi context file and return its path."""
    current_path = output_root.expanduser().resolve() / "current.md"

    if not current_path.is_file():
        raise FileNotFoundError(
            f"Current context file not found: {current_path}"
        )

    content = current_path.read_text(encoding="utf-8")
    copy_to_clipboard(content)

    return current_path

```

### Modified: `src/izanagi/config.toml`

- Previous SHA-256: `2e2e07cbce122165ad6579c48c967a46356142ea2c3b1c34509b9eee45ac619c`
- Current SHA-256: `0e1762be3a218b8e69bc89ed1a372415f0c025f014d939fe14264f467bf5d08d`
- Size: 1665 bytes
- Encoding: utf-8

```
[project]
name = ""
root = "."
output_dir = ".izanagi"

[scan]
include_hidden_files = true

# file > directory > pattern, non-inclusion = exclusion

[scan.inclusions]
rules = [
    "experiments/",
    "*.ipynb",
    "/special_config.json",
    "*.py",
    "*.c",
    "*.cpp",
    "*.h",
    "*.rs",
    "*.sv",
    "*.md",
    "*.rst",
    "*.txt",
    "pyproject.toml",
    "requirements.txt",
    "uv.lock",
    "Makefile",
    "LICENSE",
    "Dockerfile",
    ".gitignore",
    "*.toml",
]

[scan.exclusions]
rules = [
    ".git/",
    ".venv/",
    "__pycache__/",
    "*.pyc",
    "*.log",
    ".DS_Store",
    ".pytest_cache/",
    ".ruff_cache/",
    "uv.lock",
    ".pytest_cache/",
    ".ruff_cache",
]

[preamble]
base_preamble = """
# Izanagi Project Context — Base Snapshot

This document is an Izanagi snapshot created to streamline project
synchronization and communication with AI assistants.

It captures the project's structure, relevant files, configuration,
and recorded state at a specific point in time. It serves as the base
context for ongoing discussion and future project work.

The content below describes the project as captured, not necessarily
its current state.
"""

incremental_preamble = """
# Izanagi Project Context — Incremental Snapshot

This is an Izanagi incremental snapshot created to streamline project
synchronization and communication with AI assistants.

Base snapshot ID: {base_snapshot_id}

This document contains updates relative to the referenced base snapshot.
Interpret it together with that base context.
"""

[context]
# Reserved for future segmentation. Do not silently truncate snapshots.
char_limit = 5000

```
