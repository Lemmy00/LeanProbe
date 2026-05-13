"""LeanProbe public API."""

from importlib.metadata import PackageNotFoundError, version

from .core import LeanIncrementalSegment, LeanProbe

__all__ = ["LeanIncrementalSegment", "LeanProbe"]
try:
    __version__ = version("lean-probe")
except PackageNotFoundError:
    __version__ = "0+unknown"
