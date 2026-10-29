
"""Manifest project files using configured inclusion and exclusion rules."""

from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path
from typing import Any


def _is_izanagi_output(relative: str) -> bool:
    """Return whether a path is generated Izanagi output."""
    path = relative.replace("\\", "/").strip("/")

    return (
        path
        in (
            ".izanagi/current.md",
            ".izanagi/base.md",
            ".izanagi/delta.md",
            ".izanagi/manifest.json",
        )
        or path.startswith((".izanagi/bases/", ".izanagi/deltas/"))
    )


def classify_file(path: Path) -> str:
    """Classify a file for reporting; classification does not control inclusion."""
    name = path.name
    suffix = path.suffix.lower()

    if name in {
        "pyproject.toml",
        "requirements.txt",
        "uv.lock",
        "Makefile",
        "Dockerfile",
        "Cargo.toml",
        "CMakeLists.txt",
    }:
        return "config"
    if suffix in {
        ".py", ".c", ".cc", ".cpp", ".h", ".hpp", ".rs",
        ".sv", ".svh", ".v", ".vh", ".sh",
    }:
        return "source"
    if suffix == ".ipynb":
        return "notebook"
    if suffix in {".md", ".rst", ".txt"}:
        return "documentation"
    if suffix in {".toml", ".json", ".yaml", ".yml", ".ini", ".cfg"}:
        return "config"
    if suffix in {
        ".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf",
        ".zip", ".gz", ".pt", ".pth", ".bin",
    }:
        return "binary_or_artifact"
    return "other"


def _file_match(pattern: str, relative: str) -> bool:
    """Slash-free patterns match basenames at any depth."""
    pattern = pattern.replace("\\", "/")
    relative = relative.replace("\\", "/")

    if pattern.startswith("/"):
        return fnmatch.fnmatchcase(relative, pattern[1:])
    if "/" not in pattern:
        return fnmatch.fnmatchcase(Path(relative).name, pattern)
    return fnmatch.fnmatchcase(relative, pattern)


def _directory_match(pattern: str, relative: str) -> bool:
    """Match a directory rule against a directory or its descendants."""
    pattern = pattern.replace("\\", "/")
    anchored = pattern.startswith("/")
    pattern = pattern.removeprefix("/").rstrip("/")
    relative = relative.replace("\\", "/").strip("/")

    if not pattern or not relative:
        return False

    parts = relative.split("/")
    prefixes = ["/".join(parts[:i]) for i in range(1, len(parts) + 1)]

    if anchored:
        return any(fnmatch.fnmatchcase(prefix, pattern) for prefix in prefixes)

    if "/" not in pattern:
        return any(fnmatch.fnmatchcase(part, pattern) for part in parts)

    return any(
        fnmatch.fnmatchcase(prefix, pattern)
        for prefix in prefixes
        if "/" in prefix
    )


def _rule_matches(rule: str, relative: str) -> bool:
    """Test a path against a directory rule or file/pattern rule."""
    if rule.endswith("/"):
        return _directory_match(rule, relative)
    return _file_match(rule, relative)


def _rule_specificity(rule: str) -> tuple[int, int]:
    """Rank exact file paths above directory rules and broad patterns.

    Tier 3: literal file paths.
    Tier 2: directory rules.
    Tier 1: wildcard filename or path patterns.

    Within each tier, deeper paths are more specific.
    """
    normalized = rule.replace("\\", "/").removeprefix("/")
    has_wildcards = any(char in normalized for char in "*?[")

    if not normalized.endswith("/") and not has_wildcards:
        return (3, normalized.count("/"))

    if normalized.endswith("/"):
        return (2, normalized.rstrip("/").count("/") + 1)

    return (1, normalized.count("/"))


def inclusion_decision(
    path: Path,
    *,
    inclusion_rules: list[str],
    exclusion_rules: list[str],
) -> tuple[bool, str]:
    """Apply the most-specific matching rule; exclusions win ties."""
    relative = path.as_posix().replace("\\", "/").strip("/")

    matches: list[tuple[tuple[int, int], bool, str]] = []

    for included, rules in (
        (True, inclusion_rules),
        (False, exclusion_rules),
    ):
        for rule in rules:
            if _rule_matches(rule, relative):
                matches.append((_rule_specificity(rule), included, rule))

    if not matches:
        return False, "no inclusion rule matched"

    highest_specificity = max(match[0] for match in matches)
    winners = [match for match in matches if match[0] == highest_specificity]

    # Exclusion wins when rules have equal specificity.
    winner = next(
        (match for match in winners if not match[1]),
        winners[0],
    )

    included, rule = winner[1], winner[2]
    decision = "included" if included else "excluded"
    return included, f"{decision} by rule: {rule}"


def _should_traverse_excluded_directory(
    relative: str,
    *,
    inclusion_rules: list[str],
) -> bool:
    """Determine whether an excluded directory may contain an override.

    Only a more-specific inclusion can justify traversing an excluded
    directory. Broad filename patterns alone do not override directory
    exclusions.
    """
    directory = relative.replace("\\", "/").strip("/")
    prefix = directory + "/"
    directory_specificity = (2, directory.count("/") + 1)

    for rule in inclusion_rules:
        normalized = rule.replace("\\", "/").removeprefix("/")
        rule_specificity = _rule_specificity(rule)

        # An explicit file path under this directory can override it.
        if (
            not rule.endswith("/")
            and not any(char in normalized for char in "*?[")
            and normalized.startswith(prefix)
            and rule_specificity > directory_specificity
        ):
            return True

        # A narrower included directory can override this directory.
        if (
            rule.endswith("/")
            and normalized.startswith(prefix)
            and rule_specificity > directory_specificity
        ):
            return True

    return False


def discover_git_root(project_root: Path) -> Path | None:
    """Find the nearest ancestor containing a .git entry without invoking Git."""
    for candidate in (project_root, *project_root.parents):
        if (candidate / ".git").exists():
            return candidate
    return None


def manifest_project(
    project: Path,
    *,
    config: dict[str, Any],
    capture_content: bool = False,
) -> dict[str, Any]:
    """Build a project manifest using configured inclusion and exclusion rules.

    Excluded files are not read. Included files are read once to determine
    their size and hash. When capture_content=True, their bytes are attached
    under the private '_content' key for snapshot generation to reuse.

    Generated Izanagi output files are skipped. The local config file remains
    eligible for inclusion.

    Callers must remove '_content' before serializing the manifest to JSON.
    """
    root = project.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise NotADirectoryError(f"Project path is not a directory: {root}")

    scan = config["scan"]
    inclusion_rules = scan["inclusions"]["rules"]
    exclusion_rules = scan["exclusions"]["rules"]
    include_hidden = scan.get("include_hidden_files", True)
    records: list[dict[str, Any]] = []

    def walk_error(error: OSError) -> None:
        records.append(
            {
                "path": str(error.filename or "<unknown>"),
                "kind": "unreadable",
                "included": False,
                "reason": f"directory traversal error: {error}",
                "size_bytes": None,
            }
        )

    for current, dirs, filenames in os.walk(
        root,
        topdown=True,
        followlinks=False,
        onerror=walk_error,
    ):
        current_path = Path(current)
        dirs[:] = sorted(dirs)
        kept_dirs: list[str] = []

        for name in dirs:
            path = current_path / name
            relative = path.relative_to(root).as_posix()

            if _is_izanagi_output(relative):
                continue

            if path.is_symlink():
                records.append(
                    {
                        "path": relative,
                        "kind": "symlink",
                        "included": False,
                        "reason": "directory symlink not followed",
                        "size_bytes": None,
                    }
                )
                continue

            if (
                not include_hidden
                and any(part.startswith(".") for part in Path(relative).parts)
                and not any(
                    rule.endswith("/") and _directory_match(rule, relative)
                    for rule in inclusion_rules
                )
                and not any(
                    not rule.endswith("/") and _file_match(rule, relative)
                    for rule in inclusion_rules
                )
            ):
                continue

            excluded_rule = next(
                (
                    rule
                    for rule in exclusion_rules
                    if rule.endswith("/") and _directory_match(rule, relative)
                ),
                None,
            )

            if excluded_rule:
                records.append(
                    {
                        "path": relative + "/",
                        "kind": "directory",
                        "included": False,
                        "reason": f"excluded by rule: {excluded_rule}",
                        "size_bytes": None,
                    }
                )

                if _should_traverse_excluded_directory(
                    relative,
                    inclusion_rules=inclusion_rules,
                ):
                    kept_dirs.append(name)

                continue

            kept_dirs.append(name)

        dirs[:] = kept_dirs

        for filename in sorted(filenames):
            path = current_path / filename
            relative_path = path.relative_to(root)
            relative = relative_path.as_posix()

            # Generated output must never become a project delta.
            if _is_izanagi_output(relative):
                continue

            if path.is_symlink():
                records.append(
                    {
                        "path": relative,
                        "kind": "symlink",
                        "included": False,
                        "reason": "symlink not followed",
                        "size_bytes": None,
                    }
                )
                continue

            if (
                not include_hidden
                and any(part.startswith(".") for part in relative_path.parts)
                and not any(
                    rule.endswith("/") and _directory_match(rule, relative)
                    for rule in inclusion_rules
                )
                and not any(
                    not rule.endswith("/") and _file_match(rule, relative)
                    for rule in inclusion_rules
                )
            ):
                records.append(
                    {
                        "path": relative,
                        "kind": classify_file(path),
                        "included": False,
                        "reason": "hidden file excluded by scan setting",
                        "size_bytes": None,
                    }
                )
                continue

            included, reason = inclusion_decision(
                relative_path,
                inclusion_rules=inclusion_rules,
                exclusion_rules=exclusion_rules,
            )

            record: dict[str, Any] = {
                "path": relative,
                "kind": classify_file(path),
                "included": included,
                "reason": reason,
                "size_bytes": None,
            }

            # Avoid reading excluded file contents.
            if not included:
                records.append(record)
                continue

            try:
                content = path.read_bytes()
            except OSError as error:
                record["kind"] = "unreadable"
                record["included"] = False
                record["reason"] = f"file read error: {error}"
                records.append(record)
                continue

            record["size_bytes"] = len(content)
            record["sha256"] = hashlib.sha256(content).hexdigest()

            if capture_content:
                record["_content"] = content

            records.append(record)

    records.sort(key=lambda record: record["path"])

    file_records = [
        record for record in records if record["kind"] != "directory"
    ]
    included_records = [record for record in file_records if record["included"]]

    categories: dict[str, int] = {}
    for record in included_records:
        category = record["kind"]
        categories[category] = categories.get(category, 0) + 1

    known_sizes = [
        record["size_bytes"]
        for record in included_records
        if record["size_bytes"] is not None
    ]

    return {
        "project_root": str(root),
        "git_root": (
            str(git_root) if (git_root := discover_git_root(root)) else None
        ),
        "files": records,
        "summary": {
            "file_count": len(file_records),
            "included_count": len(included_records),
            "excluded_count": len(file_records) - len(included_records),
            "included_bytes": sum(known_sizes),
            "categories": categories,
        },
    }
