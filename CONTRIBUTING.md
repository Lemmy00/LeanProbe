# Contributing

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

LeanProbe tests use fake LeanInteract backends by default. Real Lean tests are
opt-in.

## Checks

```bash
pre-commit run --all-files
python -m mypy src tests
python -m pytest -q
python -m build
python -m twine check dist/*
```

Run the optional real LeanInteract smoke test with:

```bash
LEAN_PROBE_RUN_INTEGRATION=1 python -m pytest tests/test_integration.py -q
```

## Development Notes

- Keep LeanProbe independent of downstream projects.
- Keep `TOOL_NAMES` in `src/lean_probe/mcp_server.py` and the tool table in `AGENTS.md`
  in sync (a test asserts this); changing tool names is a breaking change.
- Update `AGENTS.md` when tool semantics or payload fields change.
- CI runs mypy after installing the package with development dependencies; the
  pre-commit hooks handle formatting and fast lint checks.
- CI does not run the real LeanInteract integration test. Run it locally before
  changing REPL/session behavior.
- Keep generated benchmark result files out of commits.
