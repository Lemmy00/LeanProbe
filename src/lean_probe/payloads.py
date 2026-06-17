"""Shaping LeanInteract responses into stable JSON payloads.

All success/ok semantics funnel through :func:`outcome` so every tool agrees on
what "Lean accepted this" means, and all failures funnel through
:func:`error_envelope` so every error payload has the same shape (including a
``hint``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .errors import _error_code_for_message, hint_for_code
from .segmentation import LeanIncrementalSegment

NOISY_MESSAGE_PREFIXES = ("note: this linter can be disabled with",)
DEFAULT_MESSAGE_LIMIT = 12
DEFAULT_TACTIC_LIMIT = 20
DEFAULT_SORRY_LIMIT = 20
FEEDBACK_TACTIC_LIMIT = 18
FEEDBACK_ENTRIES_PER_LINE = 4
FEEDBACK_MESSAGE_CHARS = 240
FEEDBACK_GOALS_CHARS = 300

BACKEND = "lean_interact"
TOOL = "lean_probe"

_SORRY_MESSAGE = re.compile(r"declaration uses ['`]sorry['`]")


def _pos_to_dict(pos: Any | None, *, line_offset: int = 0) -> dict[str, int] | None:
    if pos is None:
        return None
    line = int(getattr(pos, "line", 0) or 0)
    column = int(getattr(pos, "column", 0) or 0)
    return {"line": line + line_offset, "column": column}


def _clean_message_text(text: str) -> str:
    lines = []
    for line in str(text or "").splitlines():
        if any(line.strip().startswith(prefix) for prefix in NOISY_MESSAGE_PREFIXES):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _message_payloads(
    response: Any, *, line_offset: int = 0, limit: int = DEFAULT_MESSAGE_LIMIT
) -> list[dict[str, Any]]:
    payloads = []
    for message in list(getattr(response, "messages", []) or [])[:limit]:
        text = _clean_message_text(str(getattr(message, "data", "") or ""))
        payloads.append(
            {
                "severity": str(getattr(message, "severity", "") or ""),
                "message": text,
                "start": _pos_to_dict(getattr(message, "start_pos", None), line_offset=0),
                "end": _pos_to_dict(getattr(message, "end_pos", None), line_offset=0),
                "file_start": _pos_to_dict(getattr(message, "start_pos", None), line_offset=line_offset),
                "file_end": _pos_to_dict(getattr(message, "end_pos", None), line_offset=line_offset),
            }
        )
    return payloads


def _format_message_summary(messages: list[dict[str, Any]], *, limit: int = 3) -> str:
    parts: list[str] = []
    for item in messages[:limit]:
        pos = item.get("file_start") if isinstance(item.get("file_start"), Mapping) else item.get("start")
        location = ""
        if isinstance(pos, Mapping):
            line = pos.get("line")
            column = pos.get("column")
            if line:
                location = f"line {line}"
                if column is not None:
                    location += f":{column}"
        severity = str(item.get("severity", "") or "").strip()
        message = " ".join(str(item.get("message", "") or "").split())
        prefix = f"{location} " if location else ""
        if severity:
            prefix += f"{severity}: "
        if message:
            parts.append((prefix + message)[:240])
    return "; ".join(parts)


def _tactic_payloads(response: Any, *, line_offset: int = 0, limit: int = DEFAULT_TACTIC_LIMIT) -> list[dict[str, Any]]:
    payloads = []
    for tactic in list(getattr(response, "tactics", []) or [])[:limit]:
        payloads.append(
            {
                "tactic": str(getattr(tactic, "tactic", "") or ""),
                "goals": str(getattr(tactic, "goals", "") or ""),
                "proof_state": getattr(tactic, "proof_state", None),
                "start": _pos_to_dict(getattr(tactic, "start_pos", None), line_offset=0),
                "end": _pos_to_dict(getattr(tactic, "end_pos", None), line_offset=0),
                "file_start": _pos_to_dict(getattr(tactic, "start_pos", None), line_offset=line_offset),
                "file_end": _pos_to_dict(getattr(tactic, "end_pos", None), line_offset=line_offset),
                "used_constants": list(getattr(tactic, "used_constants", []) or []),
            }
        )
    return payloads


def _sorry_payloads(response: Any, *, limit: int = DEFAULT_SORRY_LIMIT) -> list[dict[str, Any]]:
    payloads = []
    for sorry in list(getattr(response, "sorries", []) or [])[:limit]:
        payloads.append(
            {
                "goal": str(getattr(sorry, "goal", "") or ""),
                "proof_state": getattr(sorry, "proof_state", None),
                "start": _pos_to_dict(getattr(sorry, "start_pos", None), line_offset=0),
                "end": _pos_to_dict(getattr(sorry, "end_pos", None), line_offset=0),
            }
        )
    return payloads


def _has_sorry(response: Any) -> bool:
    if list(getattr(response, "sorries", []) or []):
        return True
    for message in list(getattr(response, "messages", []) or []):
        if _SORRY_MESSAGE.search(str(getattr(message, "data", "") or "")):
            return True
    return False


def outcome(response: Any) -> tuple[bool, bool, bool]:
    """Return ``(has_errors, has_sorry, valid_without_sorry)`` for a response.

    ``ok`` for a check is ``valid_without_sorry and not has_errors and not has_sorry``;
    compute it from this tuple so all tools agree.
    """

    has_errors = bool(response.has_errors()) if response is not None and hasattr(response, "has_errors") else False
    has_sorry = _has_sorry(response) if response is not None else False
    valid_without_sorry = (
        bool(response.lean_code_is_valid(allow_sorry=False))
        if response is not None and hasattr(response, "lean_code_is_valid")
        else False
    )
    return has_errors, has_sorry, valid_without_sorry


_SEVERITY_GLYPH = {"error": "✗", "warning": "⚠", "info": "ℹ"}


def _feedback_lean(
    text: str, messages: list[dict[str, Any]], tactics: list[dict[str, Any]], *, limit: int = FEEDBACK_TACTIC_LIMIT
) -> str:
    """Annotate Lean source with compact inline feedback comments.

    Each diagnostic becomes a single ``-- <glyph> <severity>: <msg>`` line above
    the relevant source line; each proof state becomes ``-- goal: <state>``. No
    block-comment wrapper, and a goal already contained in an error message on the
    same line is dropped as redundant.
    """

    by_line: dict[int, list[str]] = {}
    seen: dict[int, set[str]] = {}
    msgs_on_line: dict[int, list[str]] = {}

    def _add(line: int, entry: str) -> None:
        line = max(1, line)
        bucket = seen.setdefault(line, set())
        if entry in bucket:
            return
        bucket.add(entry)
        by_line.setdefault(line, []).append(entry)

    for message in messages:
        pos = message.get("start") if isinstance(message.get("start"), Mapping) else None
        line = int(pos.get("line", 1) if isinstance(pos, Mapping) else 1)
        severity = str(message.get("severity", "") or "")
        raw = " ".join(str(message.get("message", "") or "").split())
        msgs_on_line.setdefault(max(1, line), []).append(raw)
        glyph = _SEVERITY_GLYPH.get(severity, "·")
        label = f"{glyph} {severity}".strip()
        _add(line, f"-- {label}: {raw}"[:FEEDBACK_MESSAGE_CHARS])
    for tactic in tactics[:limit]:
        pos = tactic.get("start") if isinstance(tactic.get("start"), Mapping) else None
        line = int(pos.get("line", 1) if isinstance(pos, Mapping) else 1)
        goals = " ".join(str(tactic.get("goals", "") or "").split())
        if not goals:
            continue
        if any(goals in existing for existing in msgs_on_line.get(max(1, line), [])):
            continue  # an error/warning here already shows this goal
        _add(line, f"-- goal: {goals}"[:FEEDBACK_GOALS_CHARS])

    output: list[str] = []
    for line_number, source_line in enumerate(text.splitlines(), start=1):
        if line_number in by_line:
            indent = source_line[: len(source_line) - len(source_line.lstrip())]
            output.extend(f"{indent}{entry}" for entry in by_line[line_number][:FEEDBACK_ENTRIES_PER_LINE])
        output.append(source_line)
    return "\n".join(output)


def error_envelope(
    *,
    action: str,
    error: str,
    error_code: str = "",
    file: str | Path | None = None,
    target: str = "",
    project_root: str | Path | None = None,
    timed_out: bool = False,
    elapsed_s: float | None = None,
    hint: str = "",
    searched: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Build the one canonical failure payload shared by every tool."""

    code = error_code or _error_code_for_message(error)
    payload: dict[str, Any] = {
        "success": False,
        "ok": False,
        "backend": BACKEND,
        "tool": TOOL,
        "action": action,
        "timed_out": timed_out,
        "error_code": code,
        "error": error,
        "output": error,
        "hint": hint or hint_for_code(code, searched=searched),
    }
    if file is not None:
        payload["file"] = str(file)
    if target:
        payload["target"] = target
    if project_root is not None:
        payload["project_root"] = str(project_root)
    if elapsed_s is not None:
        payload["elapsed_s"] = round(float(elapsed_s), 3)
    payload.update(extra)
    return payload


def response_payload(
    response: Any,
    *,
    action: str,
    file_path: Path,
    target: LeanIncrementalSegment | None,
    elapsed_s: float,
    env_before: int | None,
    env_after: int | None,
    cache_hit: bool,
    include_tactics: bool,
    checked_text: str,
    project_root: str | Path | None = None,
    timed_out: bool = False,
    error: str = "",
    error_code: str = "",
) -> dict[str, Any]:
    line_offset = (int(target.start_line) - 1) if target is not None else 0
    messages = _message_payloads(response, line_offset=line_offset) if response is not None else []
    tactics = _tactic_payloads(response, line_offset=line_offset) if response is not None and include_tactics else []
    has_errors, has_sorry, valid_without_sorry = outcome(response)
    if response is None and error:
        has_errors = True
    output = "\n".join(
        f"{item.get('severity', '')}: {item.get('message', '')}".strip()
        for item in messages
        if str(item.get("message", "") or "").strip()
    )
    code = error_code or _error_code_for_message(error)
    payload = {
        "success": not bool(error),
        "ok": valid_without_sorry and not has_errors and not has_sorry,
        "backend": BACKEND,
        "tool": TOOL,
        "action": action,
        "file": str(file_path),
        "target": target.name if target else "",
        "target_kind": target.kind if target else "",
        "target_range": {"start_line": target.start_line, "end_line": target.end_line} if target else {},
        "valid_without_sorry": valid_without_sorry,
        "has_errors": has_errors,
        "has_sorry": has_sorry,
        "timed_out": timed_out,
        "error_code": code if error else "",
        "error": error,
        "elapsed_s": round(float(elapsed_s), 3),
        "command": f"lean_probe {action}",
        "output": output or error,
        "messages": messages,
        "tactics": tactics,
        "feedback_lean": _feedback_lean(checked_text, messages, tactics) if (messages or tactics) else "",
        "cache": {
            "env_before": env_before,
            "env_after": env_after,
            "cache_hit": cache_hit,
            "header_env": env_before if target is None else None,
        },
    }
    if error:
        payload["hint"] = hint_for_code(code)
    if project_root is not None:
        payload["project_root"] = str(project_root)
    return payload
