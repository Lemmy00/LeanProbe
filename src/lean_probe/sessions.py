"""LeanInteract session lifecycle and the low-level command runner.

``run_command`` runs exactly one REPL command and classifies failures; it does
NOT retry. Dead-server recovery is the orchestrator's job (see ``probe.py``),
because recovering an environment-bearing command requires rebuilding the cached
environment on the fresh REPL — replaying a stale ``env`` id against a restarted
server is a silent correctness bug.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import ErrorCode, _error_code_for_exception


def _import_lean_interact() -> tuple[Any, Any, Any, Any, Any, str]:
    try:
        from lean_interact import Command, LeanREPLConfig, LeanServer, LocalProject, ProofStep
    except Exception as exc:
        return None, None, None, None, None, f"lean-interact unavailable: {exc}"
    return Command, ProofStep, LeanREPLConfig, LeanServer, LocalProject, ""


def import_error() -> str:
    """Return the LeanInteract import error, or '' when the backend is importable."""

    return _import_lean_interact()[5]


def get_proof_step() -> tuple[Any, str]:
    """Return ``(ProofStep, error)`` for tactic stepping."""

    _, ProofStep, _, _, _, error = _import_lean_interact()
    return ProofStep, error


@dataclass
class _Checkpoint:
    before_env: int | None
    after_env: int | None
    text_hash: str


@dataclass
class _IncrementalSession:
    project_root: Path
    file_path: Path
    repl_dir: Path | None
    server: Any
    config: Any
    header_hash: str = ""
    header_env: int | None = None
    # Keyed by segment index; reuse is gated on matching (before_env, text_hash),
    # and Lean elaboration is deterministic, so a matching pair is always a valid
    # cache hit regardless of how indices shift across edits.
    checkpoints: dict[int, _Checkpoint] = field(default_factory=dict)

    def close(self) -> None:
        try:
            self.server.kill()
        except Exception:
            pass


@dataclass
class _CodeSession:
    server: Any
    config: Any
    cwd: Path | None

    def close(self) -> None:
        try:
            self.server.kill()
        except Exception:
            pass


def build_server(
    *,
    project_root: Path | None,
    repl_dir: Path | None,
    lake_path: str | Path,
    auto_build: bool,
    verbose: bool,
) -> tuple[Any | None, Any | None, str]:
    """Start a LeanServer; return ``(server, config, error)``.

    ``project_root=None`` builds a project-less server (standalone snippets).
    """

    _, _, LeanREPLConfig, LeanServer, LocalProject, import_error = _import_lean_interact()
    if LeanREPLConfig is None or LeanServer is None or LocalProject is None:
        return None, None, import_error
    try:
        kwargs: dict[str, Any] = {"lake_path": str(lake_path), "verbose": verbose}
        if project_root is not None:
            kwargs["project"] = LocalProject(directory=str(project_root), auto_build=auto_build)
        if repl_dir is not None:
            kwargs.update({"local_repl_path": str(repl_dir), "build_repl": False})
        config = LeanREPLConfig(**kwargs)
        server = LeanServer(config)
    except Exception as exc:
        return None, None, f"failed to start LeanInteract server: {exc}"
    return server, config, ""


def run_command(
    server: Any,
    cmd: str,
    *,
    env: int | None,
    include_tactics: bool,
    timeout_s: int,
) -> tuple[Any | None, float, str, str, bool]:
    """Run one REPL command. Returns ``(response, elapsed_s, error, error_code, timed_out)``."""

    Command, _, _, _, _, import_error = _import_lean_interact()
    if Command is None:
        return None, 0.0, import_error, ErrorCode.LEAN_INTERACT_UNAVAILABLE, False
    start = time.perf_counter()
    try:
        request = Command(cmd=cmd, all_tactics=True) if include_tactics else Command(cmd=cmd)
        if env is not None:
            request = request.model_copy(update={"env": env})
        response = server.run(request, timeout=timeout_s)
    except Exception as exc:
        error_code = _error_code_for_exception(exc)
        return None, time.perf_counter() - start, str(exc), error_code, error_code == ErrorCode.TIMEOUT
    return response, time.perf_counter() - start, "", "", False
