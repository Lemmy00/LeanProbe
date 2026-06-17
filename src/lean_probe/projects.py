"""Lean/Lake project-root and local-REPL discovery."""

from __future__ import annotations

import platform
from pathlib import Path

PROJECT_MARKERS = ("lakefile.lean", "lakefile.toml")
LOCAL_REPL_CANDIDATES = (
    ".lake/packages/repl",
    ".lake/build",
)


def find_lean_project_root(start: str | Path) -> Path | None:
    """Find the nearest Lake project root at or above ``start``."""

    path = Path(start).expanduser().resolve()
    if path.is_file():
        path = path.parent
    for candidate in (path, *path.parents):
        if any((candidate / marker).is_file() for marker in PROJECT_MARKERS):
            return candidate
    return None


def _local_repl_dir(project_root: Path) -> Path | None:
    suffix = ".exe" if platform.system() == "Windows" else ""
    for candidate in LOCAL_REPL_CANDIDATES:
        root = project_root / candidate
        binary = root / ".lake" / "build" / "bin" / f"repl{suffix}"
        if binary.is_file():
            return root
    return None
