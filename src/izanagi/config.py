from __future__ import annotations

import shutil
import tomllib
from pathlib import Path
from typing import Any


def default_config_path() -> Path:
    """Return the path to Izanagi's bundled default configuration."""
    return Path(__file__).with_name("config.toml")


def load_default_config() -> dict[str, Any]:
    """Load the configuration bundled with Izanagi."""
    return load_config(default_config_path())


def load_config(config_path: Path) -> dict[str, Any]:
    """Load and validate a TOML configuration file."""
    with config_path.open("rb") as file:
        config = tomllib.load(file)
    validate_config(config)
    return config


def initialize_project(project_dir: Path) -> Path:
    """Create .izanagi/config.toml without overwriting existing configuration."""
    project_dir = project_dir.expanduser().resolve()
    if not project_dir.is_dir():
        raise ValueError(f"Project directory does not exist: {project_dir}")

    config_dir = project_dir / ".izanagi"
    config_dir.mkdir(parents=True, exist_ok=True)

    destination = config_dir / "config.toml"
    if destination.exists():
        raise FileExistsError(f"Configuration already exists: {destination}")

    shutil.copy2(default_config_path(), destination)
    return destination


def load_project_config(project_dir: Path) -> dict[str, Any]:
    """Load project configuration if present; otherwise use bundled defaults."""
    project_dir = project_dir.expanduser().resolve()
    local_config = project_dir / ".izanagi" / "config.toml"

    if local_config.is_file():
        return load_config(local_config)

    return load_default_config()


def validate_config(config: dict[str, Any]) -> None:
    """Validate the supported configuration structure and values."""
    if not isinstance(config, dict):
        raise TypeError("Configuration must be a dictionary")

    for section in ("project", "scan", "preamble"):
        if section not in config or not isinstance(config[section], dict):
            raise ValueError(
                f"Missing or invalid configuration section: {section}"
            )

    scan = config["scan"]

    if not isinstance(scan.get("include_hidden_files"), bool):
        raise TypeError("scan.include_hidden_files must be a boolean")

    for section in ("inclusions", "exclusions"):
        section_config = scan.get(section)
        if not isinstance(section_config, dict):
            raise TypeError(f"scan.{section} must be a table")

        rules = section_config.get("rules")
        if not isinstance(rules, list):
            raise TypeError(f"scan.{section}.rules must be a list")

        for rule in rules:
            if not isinstance(rule, str):
                raise TypeError(
                    f"Every scan.{section}.rules entry must be a string"
                )
            if not rule.strip():
                raise ValueError(
                    f"Empty rules are not allowed in scan.{section}.rules"
                )
