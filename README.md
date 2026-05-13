# LeanProbe

LeanProbe is a small, standalone Lean 4 feedback server for coding agents.
It keeps a LeanInteract-backed REPL warm, reuses the elaborated imports and
prior declarations in a file, and checks only the declaration an agent is
currently editing.

The useful loop is simple:

1. warm the file once,
2. try one proof or tactic edit,
3. get exact Lean diagnostics, tactic goals, and annotated Lean feedback,
4. repeat without paying full `lake env lean` startup cost every time.

LeanProbe is not a replacement for final verification. Use it for the inner
loop, then run `lake env lean File.lean` or `lake build` before accepting a
change.

## Why Agents Like It

LLMs tend to repair Lean proofs incrementally: try a tactic, read the new goal,
try another tactic, inspect the failure, and refine. A full-file Lake check is
correct but expensive for that loop, especially in Mathlib projects where imports
dominate latency.

LeanProbe exposes that loop through stable MCP tool names:

- `lean_probe_prepare`: warm imports/header and prior declarations.
- `lean_probe_check`: check one declaration or replacement declaration.
- `lean_probe_feedback`: return diagnostics, tactic ranges, goal states, and
  `feedback_lean` with comments inserted at the failing lines.
- `lean_probe_state`: create a proof state from Lean code containing `sorry`.
- `lean_probe_step`: apply one tactic to a proof state.

## When It Helps

LeanProbe is best when:

- the agent repeatedly edits one theorem in a larger file,
- imports and earlier declarations stay stable,
- the proof is tactic-heavy and intermediate goals matter,
- many candidate proof bodies need to be screened,
- the final correctness gate is still Lake or CI.

LeanProbe helps less when:

- the file is checked only once,
- imports or earlier declarations change every attempt,
- the target depends on edits to future declarations,
- the bottleneck is a single very expensive tactic rather than startup/imports,
- you need final project-level assurance.

## Current Results

These numbers were produced by `lean-probe benchmark` on May 13, 2026. They
should be refreshed for every release because Lean, Mathlib, hardware, and
caches all matter.

Benchmark target:

- project: EPFLemma `testdata/workflow_projects/GaussTest`
- file: `GaussTest/RealTheorems.lean`
- target: `absLipschitz1`
- candidate replacement: a complete proof of `absLipschitz1`
- comparison: repeated full-file `lake env lean` checks on a temporary file
  containing the replacement vs warm target checks of the same replacement

| Platform | CPU / OS | Lean | Runs | Full-file p50 | LeanProbe check p50 | Speedup | Feedback p50 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| macOS local | Apple Silicon arm64, Darwin 25.4.0, Python 3.11.15 | v4.30.0-rc2 | 5 | 4.281s | 0.019s | 225.32x | 0.019s |
| Linux `larapc2` | x86_64, Linux 6.8.0-111-generic, Python 3.12.12 | v4.30.0-rc2 | 5 | 2.636s | 0.020s | 131.80x | 0.018s |

Interpretation:

- `lean_probe_check` is the fast acceptance-style inner-loop check for one
  declaration.
- `lean_probe_feedback` asks LeanInteract for tactic metadata too, so it is
  usually slower than a plain check but much more useful after a failed proof.
- Final verification remains a full Lean/Lake command.

## Install

From this standalone subproject:

```bash
python -m pip install -e ".[dev]"
```

Requirements:

- Python 3.10+
- Lean 4 and Lake through `elan`
- `git`
- a Lean project that already builds, or `--auto-build` when you want
  LeanInteract to build it

## CLI

```bash
lean-probe prepare GaussTest/RealTheorems.lean --theorem-id absLipschitz1

lean-probe check GaussTest/RealTheorems.lean absLipschitz1 \
  --replacement-file /tmp/candidate.lean --pretty

lean-probe feedback GaussTest/RealTheorems.lean absLipschitz1 --pretty

lean-probe benchmark GaussTest/RealTheorems.lean absLipschitz1 \
  --cwd /path/to/GaussTest --runs 5 --include-feedback --pretty
```

## MCP

Run the MCP server over stdio:

```bash
lean-probe mcp
```

Example MCP configuration:

```json
{
  "mcpServers": {
    "lean-probe": {
      "command": "lean-probe",
      "args": ["mcp"]
    }
  }
}
```

Agents should call `lean_probe_prepare` at the start of a same-file theorem
turn, then use `lean_probe_check` after concrete candidate edits. When ordinary
diagnostics do not explain the failure, call `lean_probe_feedback` and read
`messages`, `tactics`, and `feedback_lean`.

## Python

```python
from lean_probe import LeanProbe

probe = LeanProbe()
probe.prepare_file("GaussTest/RealTheorems.lean", theorem_id="absLipschitz1")

result = probe.check_target(
    "GaussTest/RealTheorems.lean",
    theorem_id="absLipschitz1",
    replacement="""
theorem absLipschitz1 : isLipschitz abs 1 := by
  intro x y
  simpa using abs_abs_sub_abs_le x y
""",
)
print(result["ok"], result["elapsed_s"])
```

For tactic-by-tactic exploration:

```python
state = probe.proof_state_from_code("theorem ex (n : Nat) : n = n := by sorry")
proof_state = state["sorries"][0]["proof_state"]
step = probe.tactic_step(state["session_id"], proof_state, "rfl")
print(step["proof_status"])
```

## Output Shape

`lean_probe_check` and `lean_probe_feedback` return JSON-compatible dictionaries:

- `ok`: true only when Lean accepts the target without `sorry`
- `messages`: Lean diagnostics with both chunk-local and file-global positions
- `tactics`: tactic text, ranges, goals, proof states, and used constants
- `feedback_lean`: target declaration with inline feedback comments
- `cache`: header/prior-declaration environment reuse metadata
- `elapsed_s`: wall-clock time for the check

## Benchmarking More Platforms

Use the same benchmark command on each machine and paste the JSON into the
README table:

```bash
lean-probe benchmark GaussTest/RealTheorems.lean absLipschitz1 \
  --cwd /path/to/GaussTest \
  --runs 5 \
  --include-feedback \
  --pretty
```

Suggested platforms for public reporting:

- local macOS laptop or workstation,
- Linux workstation/server,
- CI Linux runner after Lake caches are warm.

## Relationship To LeanInteract

LeanProbe is intentionally thin. LeanInteract provides the REPL process,
incremental elaboration, parallel elaboration, command responses, proof states,
and tactic stepping. LeanProbe packages one agent-oriented workflow on top:
same-file declaration targeting, warm prior environments, replacement checking,
and MCP-friendly feedback.

See LeanInteract: https://github.com/augustepoiroux/LeanInteract
