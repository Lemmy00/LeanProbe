"""Command-line interface for LeanProbe.

Subcommands mirror the MCP tool set (``check``, ``check-target``, ``status``,
``proof-state``) plus ``prepare`` (warm an env), the benchmark commands, and
``mcp`` (run the stdio server). Benchmark code is imported lazily so a benchmark
dependency problem never affects checking.
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from . import __version__
from .probe import LeanProbe


def _read_text_arg(value: str, file_value: str) -> str:
    if value and file_value:
        raise SystemExit("Use either the inline value or the --*-file form, not both.")
    if file_value:
        return Path(file_value).read_text(encoding="utf-8")
    return value


def _read_code(args: argparse.Namespace) -> str:
    code = _read_text_arg(args.code, args.code_file)
    if not code:
        code = sys.stdin.read()
    return code


def _emit(payload: dict[str, Any], *, pretty: bool) -> None:
    if pretty:
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _package_version() -> str:
    try:
        return version("lean-probe")
    except PackageNotFoundError:
        return __version__


def _probe_from_args(args: argparse.Namespace) -> LeanProbe:
    return LeanProbe(
        auto_build=bool(getattr(args, "auto_build", False)),
        local_repl_path=getattr(args, "local_repl_path", "") or None,
        lake_path=getattr(args, "lake_path", "lake") or "lake",
        verbose=bool(getattr(args, "verbose", False)),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lean-probe", description="Fast Lean 4 proof feedback for agents.")
    parser.add_argument("--version", action="version", version=f"lean-probe {_package_version()}")
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--cwd", default="", help="Lean project working directory")
    common.add_argument("--timeout-s", type=int, default=90, help="LeanInteract request timeout")
    common.add_argument("--auto-build", action="store_true", help="Let LeanInteract build the Lean project")
    common.add_argument("--local-repl-path", default="", help="Use a specific local Lean REPL checkout")
    common.add_argument("--lake-path", default="lake", help="Path to lake executable")
    common.add_argument("--verbose", action="store_true", help="Enable LeanInteract verbose setup")
    common.add_argument("--pretty", action="store_true", help="Pretty-print JSON")

    status = sub.add_parser("status", parents=[common], help="Report LeanProbe readiness and live sessions")
    status.add_argument("--warm", action="store_true", help="Boot the Lean REPL now")

    check = sub.add_parser("check", parents=[common], help="Verify a standalone Lean snippet")
    check.add_argument("--code", default="")
    check.add_argument("--code-file", default="")
    check.add_argument("--include-tactics", action="store_true")

    check_target = sub.add_parser("check-target", parents=[common], help="Check one declaration in a project file")
    check_target.add_argument("file_path")
    check_target.add_argument("name")
    check_target.add_argument("--replacement", default="")
    check_target.add_argument("--replacement-file", default="")
    check_target.add_argument("--with-feedback", action="store_true", help="Include tactics and feedback_lean")
    check_target.add_argument("--include-tactics", action="store_true")

    prepare = sub.add_parser("prepare", parents=[common], help="Warm imports and optional prior declarations")
    prepare.add_argument("file_path")
    prepare.add_argument("--theorem-id", default="")

    state = sub.add_parser("proof-state", parents=[common], help="Open proof states from Lean code with sorry")
    state.add_argument("--code", default="")
    state.add_argument("--code-file", default="")
    state.add_argument("--include-tactics", action="store_true")

    _add_benchmark_parsers(sub, common)

    sub.add_parser("mcp", help="Run the LeanProbe MCP stdio server")
    return parser


def _add_benchmark_parsers(sub: Any, common: argparse.ArgumentParser) -> None:
    benchmark = sub.add_parser("benchmark", parents=[common], help="Compare Lake and warm LeanProbe checks")
    benchmark.add_argument("file_path")
    benchmark.add_argument("theorem_id")
    benchmark.add_argument("--replacement", default="")
    benchmark.add_argument("--replacement-file", default="")
    benchmark.add_argument("--runs", type=int, default=5)
    benchmark.add_argument("--warmups", type=int, default=1)
    benchmark.add_argument("--include-feedback", action="store_true")
    benchmark.add_argument("--include-no-cache", action="store_true")
    benchmark.add_argument("--external-command", action="append", default=[])
    benchmark.add_argument("--results-dir", default="")
    benchmark.add_argument("--label", default="")

    suite = sub.add_parser("benchmark-suite", parents=[common], help="Run a JSON benchmark case suite")
    suite.add_argument("--cases-file", required=True)
    suite.add_argument("--runs", type=int, default=5)
    suite.add_argument("--warmups", type=int, default=1)
    suite.add_argument("--include-feedback", action="store_true")
    suite.add_argument("--include-no-cache", action="store_true")
    suite.add_argument("--external-command", action="append", default=[])
    suite.add_argument("--results-dir", default="")
    suite.add_argument("--case", action="append", default=[])

    file_benchmark = sub.add_parser(
        "benchmark-file", parents=[common], help="Compare repeated same-file checks with env reuse"
    )
    file_benchmark.add_argument("file_path")
    file_benchmark.add_argument("--runs", type=int, default=3)
    file_benchmark.add_argument("--max-declarations", dest="max_declarations", type=int, default=0)
    file_benchmark.add_argument("--max-cutoffs", dest="max_declarations", type=int, help=argparse.SUPPRESS)
    file_benchmark.add_argument("--skip-no-cache", action="store_true")
    file_benchmark.add_argument("--external-command", action="append", default=[])
    file_benchmark.add_argument("--results-dir", default="")
    file_benchmark.add_argument("--label", default="")


def _run_benchmark_command(args: argparse.Namespace) -> int:
    from .benchmark import (
        _external_command_specs,
        run_benchmark,
        run_benchmark_suite,
        run_file_level_benchmark,
    )

    try:
        external_commands = _external_command_specs(args.external_command)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    if args.command == "benchmark":
        payload = run_benchmark(
            file_path=args.file_path,
            theorem_id=args.theorem_id,
            cwd=args.cwd or None,
            replacement=_read_text_arg(args.replacement, args.replacement_file),
            runs=args.runs,
            warmups=args.warmups,
            include_feedback=args.include_feedback,
            timeout_s=args.timeout_s,
            auto_build=args.auto_build,
            local_repl_path=args.local_repl_path or None,
            lake_path=args.lake_path,
            verbose=args.verbose,
            include_no_cache=args.include_no_cache,
            external_commands=external_commands,
            results_dir=args.results_dir or None,
            label=args.label,
        )
    elif args.command == "benchmark-suite":
        payload = run_benchmark_suite(
            cases_file=args.cases_file,
            cwd=args.cwd or None,
            runs=args.runs,
            warmups=args.warmups,
            include_feedback=args.include_feedback,
            timeout_s=args.timeout_s,
            auto_build=args.auto_build,
            local_repl_path=args.local_repl_path or None,
            lake_path=args.lake_path,
            verbose=args.verbose,
            include_no_cache=args.include_no_cache,
            external_commands=external_commands,
            results_dir=args.results_dir or None,
            case_labels=args.case or None,
        )
    else:  # benchmark-file
        payload = run_file_level_benchmark(
            file_path=args.file_path,
            cwd=args.cwd or None,
            runs=args.runs,
            max_cutoffs=args.max_declarations,
            timeout_s=args.timeout_s,
            auto_build=args.auto_build,
            local_repl_path=args.local_repl_path or None,
            lake_path=args.lake_path,
            verbose=args.verbose,
            include_no_cache=not args.skip_no_cache,
            external_commands=external_commands,
            results_dir=args.results_dir or None,
            label=args.label,
        )
    _emit(payload, pretty=args.pretty)
    return 0 if payload.get("success") else 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "mcp":
        from .mcp_server import run

        try:
            run()
        except RuntimeError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0

    if args.command in {"benchmark", "benchmark-suite", "benchmark-file"}:
        return _run_benchmark_command(args)

    probe = _probe_from_args(args)
    try:
        if args.command == "status":
            payload = probe.capabilities(cwd=args.cwd or None, warm=args.warm)
        elif args.command == "check":
            payload = probe.check_code(
                _read_code(args),
                cwd=args.cwd or None,
                include_tactics=args.include_tactics,
                timeout_s=args.timeout_s,
            )
        elif args.command == "check-target":
            replacement = _read_text_arg(args.replacement, args.replacement_file)
            if args.with_feedback:
                payload = probe.feedback(
                    args.file_path,
                    theorem_id=args.name,
                    cwd=args.cwd or None,
                    replacement=replacement,
                    timeout_s=args.timeout_s,
                )
            else:
                payload = probe.check_target(
                    args.file_path,
                    theorem_id=args.name,
                    cwd=args.cwd or None,
                    replacement=replacement,
                    include_tactics=args.include_tactics,
                    timeout_s=args.timeout_s,
                )
        elif args.command == "prepare":
            payload = probe.prepare_file(
                args.file_path,
                theorem_id=args.theorem_id,
                cwd=args.cwd or None,
                timeout_s=args.timeout_s,
            )
        elif args.command == "proof-state":
            payload = probe.proof_state_from_code(
                _read_code(args),
                cwd=args.cwd or None,
                include_tactics=args.include_tactics,
                timeout_s=args.timeout_s,
            )
        else:
            raise SystemExit(f"Unknown command: {args.command}")
    finally:
        probe.close()

    _emit(payload, pretty=bool(getattr(args, "pretty", False)))
    if args.command == "status":
        return 0 if payload.get("available") else 1
    return 0 if payload.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
