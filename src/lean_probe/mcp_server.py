"""MCP stdio server for LeanProbe."""

from __future__ import annotations

from typing import Any

from .core import LeanProbe


MCP_SERVER_NAME = "lean-probe"
TOOL_NAMES = [
    "lean_probe_prepare",
    "lean_probe_check",
    "lean_probe_feedback",
    "lean_probe_state",
    "lean_probe_step",
]

_PROBE = LeanProbe()


def create_server() -> Any:
    try:
        from mcp.server.fastmcp import FastMCP
    except Exception as exc:
        raise RuntimeError(f"mcp package unavailable: {exc}") from exc

    mcp = FastMCP(MCP_SERVER_NAME)

    @mcp.tool()
    def lean_probe_prepare(
        file_path: str,
        theorem_id: str = "",
        cwd: str = "",
        timeout_s: int = 60,
    ) -> dict[str, Any]:
        """Warm a Lean file header/imports and optionally prior declarations for a target."""

        return _PROBE.prepare_file(
            file_path,
            theorem_id=theorem_id,
            cwd=cwd or None,
            timeout_s=timeout_s,
        )

    @mcp.tool()
    def lean_probe_check(
        file_path: str,
        theorem_id: str,
        cwd: str = "",
        replacement: str = "",
        include_tactics: bool = False,
        timeout_s: int = 60,
    ) -> dict[str, Any]:
        """Check one Lean declaration or replacement declaration quickly."""

        return _PROBE.check_target(
            file_path,
            theorem_id=theorem_id,
            cwd=cwd or None,
            replacement=replacement,
            include_tactics=include_tactics,
            timeout_s=timeout_s,
        )

    @mcp.tool()
    def lean_probe_feedback(
        file_path: str,
        theorem_id: str,
        cwd: str = "",
        replacement: str = "",
        timeout_s: int = 60,
    ) -> dict[str, Any]:
        """Return diagnostics, tactic metadata, goals, and annotated Lean feedback."""

        return _PROBE.feedback(
            file_path,
            theorem_id=theorem_id,
            cwd=cwd or None,
            replacement=replacement,
            timeout_s=timeout_s,
        )

    @mcp.tool()
    def lean_probe_state(
        code: str,
        cwd: str = "",
        include_tactics: bool = False,
        timeout_s: int = 60,
    ) -> dict[str, Any]:
        """Create or inspect a proof state from Lean code containing sorry."""

        return _PROBE.proof_state_from_code(
            code,
            cwd=cwd or None,
            include_tactics=include_tactics,
            timeout_s=timeout_s,
        )

    @mcp.tool()
    def lean_probe_step(
        session_id: str,
        proof_state: int,
        tactic: str,
        timeout_s: int = 60,
    ) -> dict[str, Any]:
        """Apply one tactic to a LeanProbe proof state."""

        return _PROBE.tactic_step(
            session_id,
            proof_state,
            tactic,
            timeout_s=timeout_s,
        )

    return mcp


def run() -> None:
    create_server().run()


if __name__ == "__main__":
    run()
