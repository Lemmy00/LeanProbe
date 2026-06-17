"""LeanProbe public API."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .probe import LeanProbe
from .projects import find_lean_project_root
from .segmentation import LeanIncrementalSegment, segment_file

__all__ = ["LeanIncrementalSegment", "LeanProbe", "find_lean_project_root", "segment_file"]


def _source_tree_version() -> str:
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    try:
        for line in pyproject.read_text(encoding="utf-8").splitlines():
            if line.startswith("version = "):
                return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        pass
    return "0+unknown"


try:
    __version__ = version("lean-probe")
except PackageNotFoundError:
    __version__ = _source_tree_version()
