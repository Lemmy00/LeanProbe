"""Benchmark helpers for LeanProbe."""

from __future__ import annotations

import json
import platform
import statistics
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .core import LeanProbe, find_lean_project_root, segment_file


def _summary(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"runs": 0, "min": 0.0, "p50": 0.0, "mean": 0.0, "max": 0.0}
    return {
        "runs": len(values),
        "min": round(min(values), 3),
        "p50": round(statistics.median(values), 3),
        "mean": round(statistics.fmean(values), 3),
        "max": round(max(values), 3),
    }


def _run_lake_check(project_root: Path, file_path: Path, timeout_s: int) -> tuple[bool, float, str]:
    try:
        relative = file_path.relative_to(project_root)
    except ValueError:
        relative = file_path
    start = time.perf_counter()
    proc = subprocess.run(
        ["lake", "env", "lean", str(relative)],
        cwd=str(project_root),
        text=True,
        capture_output=True,
        timeout=timeout_s,
        check=False,
    )
    elapsed = time.perf_counter() - start
    output = (proc.stdout + "\n" + proc.stderr).strip()
    return proc.returncode == 0, elapsed, output[-4000:]


def _lake_target_with_replacement(
    original: Path,
    theorem_id: str,
    replacement: str,
) -> tuple[Path, Path | None, str]:
    if not replacement:
        return original, None, ""

    text = original.read_text(encoding="utf-8")
    _header, segments = segment_file(text)
    short = theorem_id.split(".")[-1]
    target = next((segment for segment in segments if segment.name in {theorem_id, short}), None)
    if target is None:
        return original, None, "target declaration not found; Lake benchmark used original file"

    tmp = tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(original.parent),
        prefix=".lean_probe_bench_",
        suffix=".lean",
        delete=False,
    )
    try:
        tmp.write(text[: target.start])
        tmp.write(replacement.rstrip() + "\n")
        tmp.write(text[target.end :])
    finally:
        tmp.close()
    tmp_path = Path(tmp.name)
    return tmp_path, tmp_path, ""


def run_benchmark(
    *,
    file_path: str | Path,
    theorem_id: str,
    cwd: str | Path | None = None,
    replacement: str = "",
    runs: int = 5,
    warmups: int = 1,
    include_feedback: bool = False,
    timeout_s: int = 120,
    auto_build: bool = False,
    local_repl_path: str | Path | None = None,
    lake_path: str | Path = "lake",
    verbose: bool = False,
) -> dict[str, Any]:
    project_root = find_lean_project_root(cwd or file_path)
    if project_root is None:
        return {"success": False, "error": "Lean project root not detected"}
    path = Path(file_path).expanduser()
    resolved = path.resolve() if path.is_absolute() else (project_root / path).resolve()
    if not resolved.is_file():
        return {"success": False, "error": f"Lean file not found: {resolved}"}

    lake_target, cleanup_path, lake_target_warning = _lake_target_with_replacement(resolved, theorem_id, replacement)
    probe = LeanProbe(
        auto_build=auto_build,
        local_repl_path=local_repl_path,
        lake_path=lake_path,
        verbose=verbose,
    )
    lake_times: list[float] = []
    probe_times: list[float] = []
    feedback_times: list[float] = []
    failures: list[dict[str, str]] = []
    try:
        for _ in range(max(0, warmups)):
            _run_lake_check(project_root, lake_target, timeout_s)
            probe.check_target(
                resolved,
                theorem_id=theorem_id,
                cwd=project_root,
                replacement=replacement,
                timeout_s=timeout_s,
            )
        probe.prepare_file(resolved, theorem_id=theorem_id, cwd=project_root, timeout_s=timeout_s)
        for _ in range(max(1, runs)):
            lake_ok, lake_elapsed, lake_output = _run_lake_check(project_root, lake_target, timeout_s)
            lake_times.append(lake_elapsed)
            if not lake_ok:
                failures.append({"kind": "lake", "output": lake_output})

            check = probe.check_target(
                resolved,
                theorem_id=theorem_id,
                cwd=project_root,
                replacement=replacement,
                timeout_s=timeout_s,
            )
            probe_times.append(float(check.get("elapsed_s", 0.0) or 0.0))
            if not check.get("success"):
                failures.append({"kind": "lean_probe_check", "output": str(check.get("error", ""))})

            if include_feedback:
                feedback = probe.feedback(
                    resolved,
                    theorem_id=theorem_id,
                    cwd=project_root,
                    replacement=replacement,
                    timeout_s=timeout_s,
                )
                feedback_times.append(float(feedback.get("elapsed_s", 0.0) or 0.0))
                if not feedback.get("success"):
                    failures.append({"kind": "lean_probe_feedback", "output": str(feedback.get("error", ""))})
    finally:
        probe.close()
        if cleanup_path is not None:
            try:
                cleanup_path.unlink()
            except FileNotFoundError:
                pass

    lake = _summary(lake_times)
    check = _summary(probe_times)
    feedback = _summary(feedback_times)
    lake_p50 = float(lake.get("p50", 0.0) or 0.0)
    check_p50 = float(check.get("p50", 0.0) or 0.0)
    speedup = round(lake_p50 / check_p50, 2) if check_p50 else 0.0
    return {
        "success": True,
        "project_root": str(project_root),
        "file": str(resolved),
        "lake_file": str(lake_target),
        "lake_target_warning": lake_target_warning,
        "theorem_id": theorem_id,
        "runs": runs,
        "warmups": warmups,
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python": platform.python_version(),
        },
        "lake_env_lean": lake,
        "lean_probe_check": check,
        "lean_probe_feedback": feedback if include_feedback else None,
        "speedup_p50": speedup,
        "failures": failures[:5],
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run a LeanProbe benchmark.")
    parser.add_argument("file_path")
    parser.add_argument("theorem_id")
    parser.add_argument("--cwd", default="")
    parser.add_argument("--replacement", default="")
    parser.add_argument("--replacement-file", default="")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--include-feedback", action="store_true")
    parser.add_argument("--timeout-s", type=int, default=120)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    replacement = args.replacement
    if args.replacement_file:
        replacement = Path(args.replacement_file).read_text(encoding="utf-8")
    result = run_benchmark(
        file_path=args.file_path,
        theorem_id=args.theorem_id,
        cwd=args.cwd or None,
        replacement=replacement,
        runs=args.runs,
        warmups=args.warmups,
        include_feedback=args.include_feedback,
        timeout_s=args.timeout_s,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=True))


if __name__ == "__main__":
    main()
