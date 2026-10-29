
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
