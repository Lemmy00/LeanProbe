# AGENTS.md

Two kinds of "agent" relate to this repo:

1. **Agents *using* LeanProbe** — an LLM agent that calls the LeanProbe MCP server
   to verify Lean. The usage contract lives in **[the LeanProbe skill](src/lean_probe/skill/SKILL.md)**
   (`src/lean_probe/skill/SKILL.md`). Install it into Claude Code / Codex with
   `lean-probe install-skill` (see below), or read it directly.
2. **Agents/contributors *working on* this repo** — keep reading.

---

# Working on this repo

LeanProbe is a Python package (`src/lean_probe/`) exposing a Python API, a CLI, and an
MCP stdio server, backed by [LeanInteract](https://github.com/augustepoiroux/LeanInteract).

**Setup**

```bash
python -m venv .venv && source .venv/bin/activate
python -m pip install -U pip
python -m pip install -e ".[dev]"
```

**Checks (all must pass; CI runs these):**

```bash
ruff check src tests          # lint
ruff format --check src tests # formatting (run `ruff format src tests` to fix)
mypy src
pytest -q                     # unit tests use a fake LeanInteract backend
```

The optional real-LeanInteract test is gated and needs Lean/Lake + a built project:

```bash
LEAN_PROBE_RUN_INTEGRATION=1 pytest tests/test_integration.py -q
```

**Module layout:** `segmentation` (file → header + declaration chunks), `projects`
(Lake/REPL discovery), `errors` (error codes + hints), `payloads` (response shaping,
`feedback_lean`, the shared `ok` logic), `sessions` (LeanInteract lifecycle + the
single-shot `run_command`), `probe` (the `LeanProbe` orchestrator), `skills` (install
the bundled skill into agent clients). `core` is a backwards-compatible facade that
re-exports the public names. The agent-facing skill is shipped as package data at
`skill/SKILL.md` so `pip install lean-probe` carries it (no repo checkout needed to
run `lean-probe install-skill`).

**Conventions:**

- Keep LeanProbe independent of downstream projects (no project-specific code).
- The public Python API (`LeanProbe`, `LeanIncrementalSegment`, `segment_file`) is
  importable from the package root — keep it backwards compatible.
- If you change tool semantics, payload fields, or tool names, update the skill
  ([`src/lean_probe/skill/SKILL.md`](src/lean_probe/skill/SKILL.md)) and the server
  `instructions`/`TOOL_NAMES` in `mcp_server.py` together (a test asserts the tool
  table in the skill matches the server's `TOOL_NAMES`).
- Release: bump `version` in `pyproject.toml`, update `CHANGELOG.md`, then push a
  `vX.Y.Z` tag — `release.yml` builds and publishes to PyPI.

## The bundled skill

The agent usage guide is a real skill at `src/lean_probe/skill/SKILL.md` (YAML
frontmatter + the MCP tool contract). It is the single source of truth for "how to
use the LeanProbe tools": the README links to it, and the MCP server advertises a
condensed version of it in its `instructions` field (`SERVER_INSTRUCTIONS` in
`mcp_server.py`). `tests/test_mcp_server.py` (`test_skill_tool_table_matches_public_mcp_names`)
asserts the skill's tool table stays in sync with `TOOL_NAMES`.

`lean-probe install-skill` copies it into agent clients' skills directories:

```bash
lean-probe install-skill                 # install to every present client (~/.claude, ~/.codex)
lean-probe install-skill --client codex  # force one client (creates dirs if missing)
lean-probe install-skill --skills-dir ./.claude/skills   # install into an explicit skills root
lean-probe install-skill --dry-run       # show what would be written
lean-probe install-skill --print         # write SKILL.md to stdout
```

Both Claude Code and Codex discover personal skills under `<base>/skills/<name>/SKILL.md`
(`~/.claude/skills`, `~/.codex/skills`), so the installer just copies the bundle into
each. Editing the skill means editing `src/lean_probe/skill/SKILL.md` — re-run the
installer to refresh already-installed copies.
