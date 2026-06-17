from __future__ import annotations

import pytest

from lean_probe import errors, payloads
from lean_probe.errors import ErrorCode
from lean_probe.probe import LeanProbe, _looks_like_declaration
from lean_probe.segmentation import _find_segment, segment_file

# --------------------------------------------------------------------- segmentation


def test_segment_file_keeps_doc_comment_with_declaration():
    header, segments = segment_file(
        "import Mathlib\n\n/-- First theorem. -/\ntheorem first : True := by\n  trivial\n\n"
        "lemma second : True := by\n  trivial\n"
    )
    assert header == "import Mathlib\n"
    assert [s.name for s in segments] == ["first", "second"]
    assert segments[0].text.startswith("/-- First theorem. -/")
    assert segments[0].start_line == 3
    assert segments[1].start_line == 7


def test_segment_file_ignores_keywords_inside_comments_and_strings():
    _header, segments = segment_file(
        "import Mathlib\n\n/-- theorem fake : True := by trivial -/\ntheorem real : True := by\n"
        '  have s := "def also_fake := 1"\n  trivial\n\n/-\nlemma hidden : True := by trivial\n-/\n'
        "def actual : Nat := 1\n"
    )
    assert [s.name for s in segments] == ["real", "actual"]


def test_segment_file_recognizes_modifiers_and_kinds():
    text = (
        "import Mathlib\n\n@[simp, reducible]\nprivate theorem private_thm : True := by\n  trivial\n\n"
        "noncomputable abbrev hiddenValue : Nat := 1\n\nprotected structure Box where\n  value : Nat\n\n"
        "inductive Color where\n  | red\n\nclass HasFoo (α : Type) where\n  foo : α\n\n"
        "axiom trusted : True\n\nopaque secret : Nat\n"
    )
    _header, segments = segment_file(text)
    assert [(s.kind, s.name) for s in segments] == [
        ("theorem", "private_thm"),
        ("abbrev", "hiddenValue"),
        ("structure", "Box"),
        ("inductive", "Color"),
        ("class", "HasFoo"),
        ("axiom", "trusted"),
        ("opaque", "secret"),
    ]
    assert segments[0].text.startswith("@[simp, reducible]\nprivate theorem")


def test_segment_file_strips_universe_params_from_names():
    _header, segments = segment_file(
        "theorem foo.{u} (α : Sort u) : True := by\n  trivial\n\ninstance inst.{u, v} : Inhabited (Sort u) := ⟨PUnit⟩\n"
    )
    assert [(s.kind, s.name) for s in segments] == [("theorem", "foo"), ("instance", "inst")]


def test_segment_file_keeps_mutual_block_as_one_chunk():
    text = (
        "theorem before : True := by\n  trivial\n\nmutual\n  def evenly : Nat → Bool\n    | 0 => true\n"
        "    | n + 1 => oddly n\n\n  def oddly : Nat → Bool\n    | 0 => false\n    | n + 1 => evenly n\nend\n\n"
        "theorem after : True := by\n  trivial\n"
    )
    _header, segments = segment_file(text)
    assert [(s.kind, s.name) for s in segments] == [
        ("theorem", "before"),
        ("mutual", ""),
        ("theorem", "after"),
    ]
    assert "def evenly" in segments[1].text and "def oddly" in segments[1].text


def test_segment_file_keeps_where_block_with_parent():
    # Regression: a `where`-clause helper using a declaration keyword must NOT be
    # torn off into its own top-level segment.
    text = (
        "import Mathlib\n\ntheorem outer : True := by\n  exact trivial\nwhere\n  helper : Nat := 0\n\n"
        "def real_next : Nat := 1\n"
    )
    _header, segments = segment_file(text)
    assert [(s.kind, s.name) for s in segments] == [("theorem", "outer"), ("def", "real_next")]
    assert "helper" in segments[0].text


def test_find_segment_matches_qualified_and_short_names():
    _header, segments = segment_file("namespace N\n\ntheorem demo : True := by\n  trivial\n\nend N\n")
    assert _find_segment(segments, "demo").name == "demo"
    assert _find_segment(segments, "N.demo").name == "demo"
    assert _find_segment(segments, "missing") is None


# --------------------------------------------------------------------- helpers


def test_feedback_lean_is_compact_indented_and_truncated():
    text = "theorem demo : True := by\n  exact False.elim ?h\n"
    messages = [{"severity": "error", "message": "x" * 400, "start": {"line": 2, "column": 2}}]
    tactics = [{"goals": "⊢ True", "start": {"line": 2, "column": 2}}]
    feedback = payloads._feedback_lean(text, messages, tactics)
    assert "<feedback>" not in feedback  # no heavyweight block wrapper anymore
    assert "  -- ✗ error: " in feedback  # indentation preserved, compact marker
    assert "-- goal: ⊢ True" in feedback
    assert "x" * 260 not in feedback


def test_feedback_lean_drops_goal_already_shown_in_error():
    text = "theorem demo (n : Nat) : n = n + 1 := by\n  rfl\n"
    messages = [{"severity": "error", "message": "unsolved goals n : Nat ⊢ n = n + 1", "start": {"line": 2, "column": 2}}]
    tactics = [{"goals": "n : Nat ⊢ n = n + 1", "start": {"line": 2, "column": 2}}]
    feedback = payloads._feedback_lean(text, messages, tactics)
    # The goal is already contained in the error message, so no separate goal line.
    assert feedback.count("-- goal:") == 0
    assert "-- ✗ error: unsolved goals" in feedback


def test_dead_server_error_tokens_are_stable():
    for text in ["Lean server is not running", "broken pipe", "connection reset by peer", "process has exited"]:
        assert errors._dead_server_error(text) is True


@pytest.mark.parametrize(
    ("message", "code"),
    [
        ("request timed out", "timeout"),
        ("failed to start LeanInteract server: no such file", "lean_interact_start_failed"),
        ("lean-interact unavailable: missing", "lean_interact_unavailable"),
        ("Lean server is not running", "dead_server"),
        ("Lean project root not detected", "no_project_root"),
        ("Lean file not found", "file_not_found"),
        ("target declaration not found", "target_not_found"),
        ("LeanInteract header warmup failed", "header_failed"),
        ("failed to build env before target at demo", "prior_decl_failed"),
        ("unexpected backend failure", "backend_error"),
    ],
)
def test_error_code_for_message_is_stable(message, code):
    assert errors._error_code_for_message(message) == code


def test_hints_are_present_for_every_documented_code():
    for code in errors.ALL_ERROR_CODES:
        assert errors.hint_for_code(code), code


def test_looks_like_declaration_guard():
    assert _looks_like_declaration("theorem t : True := by trivial") is True
    assert _looks_like_declaration("@[simp]\ntheorem t : True := rfl") is True
    assert _looks_like_declaration("  simp [foo]") is False
    assert _looks_like_declaration("by\n  exact h") is False


# --------------------------------------------------------------------- capabilities


def test_capabilities_reports_degraded_codes(monkeypatch, tmp_path):
    monkeypatch.setattr(
        LeanProbe, "_resolve_project_root", lambda self, cwd, file_path=None: None
    )
    from lean_probe import sessions

    monkeypatch.setattr(sessions, "_import_lean_interact", lambda: (None, None, None, None, None, "lean-interact unavailable: missing"))
    probe = LeanProbe()
    payload = probe.capabilities(tmp_path)
    assert payload["available"] is False
    assert "lean_interact_unavailable" in payload["degraded_codes"]
    assert "no_project_root" in payload["degraded_codes"]
    assert payload["hint"]


def test_capabilities_warm_boots_repl(fake_backend, lean_project):
    state = fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    payload = probe.capabilities(project, warm=True)
    assert payload["available"] is True
    assert payload["warmed"] is True
    assert len(state["servers"]) == 1


# --------------------------------------------------------------------- check_target


def test_check_target_reuses_header_and_prior_declaration_env(fake_backend, lean_project):
    state = fake_backend()
    project, target = lean_project(
        "import Mathlib\n\ntheorem first : True := by\n  trivial\n\ntheorem second : True := by\n  trivial\n"
    )
    probe = LeanProbe()
    first = probe.check_target(target, theorem_id="second", cwd=project)
    second = probe.check_target(target, theorem_id="second", cwd=project)

    assert first["ok"] is True and second["ok"] is True
    assert first["cache"]["cache_hit"] is False
    assert second["cache"]["cache_hit"] is True
    assert first["project_root"] == str(project)
    cmds = [run["cmd"].strip().splitlines()[0] for run in state["servers"][0].runs]
    assert cmds == ["import Mathlib", "theorem first : True := by", "theorem second : True := by", "theorem second : True := by"]


def test_check_target_reports_chunk_and_file_locations_on_failure(fake_backend, lean_project):
    state = fake_backend()
    project, target = lean_project("import Mathlib\n\ntheorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    payload = probe.check_target(target, theorem_id="demo", cwd=project, replacement="theorem demo : True := by\n  bad\n")
    assert payload["success"] is True
    assert payload["ok"] is False
    assert payload["has_errors"] is True
    assert payload["messages"][0]["start"] == {"line": 1, "column": 7}
    assert payload["messages"][0]["file_start"] == {"line": 3, "column": 7}
    assert "-- ✗ error: unexpected token" in payload["feedback_lean"]
    assert state["servers"][0].runs[-1]["all_tactics"] is True


def test_check_target_success_does_not_rerun_with_tactics(fake_backend, lean_project):
    state = fake_backend()
    project, target = lean_project("import Mathlib\n\ntheorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    payload = probe.check_target(target, theorem_id="demo", cwd=project)
    assert payload["ok"] is True
    assert [run["all_tactics"] for run in state["servers"][0].runs] == [False, False]


def test_replacement_body_only_is_rejected(fake_backend, lean_project):
    fake_backend()
    project, target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    payload = probe.check_target(target, theorem_id="demo", cwd=project, replacement="  trivial")
    assert payload["success"] is False
    assert payload["error_code"] == ErrorCode.REPLACEMENT_NOT_A_DECLARATION
    assert "complete declaration" in payload["hint"].lower()


def test_target_not_found_returns_error_code(fake_backend, lean_project):
    fake_backend()
    project, target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    payload = probe.check_target(target, theorem_id="missing", cwd=project)
    assert payload["success"] is False
    assert payload["error_code"] == "target_not_found"
    assert payload["hint"]


def test_target_inside_mutual_returns_hint(fake_backend, lean_project):
    fake_backend()
    project, target = lean_project(
        "mutual\n  def evenly : Nat -> Bool\n    | 0 => true\n    | n + 1 => oddly n\n\n"
        "  def oddly : Nat -> Bool\n    | 0 => false\n    | n + 1 => evenly n\nend\n"
    )
    probe = LeanProbe()
    payload = probe.check_target(target, theorem_id="evenly", cwd=project)
    assert payload["error_code"] == "target_not_found"
    assert "inside a mutual block" in payload["hint"]


def test_explicit_invalid_cwd_does_not_fall_back(fake_backend, lean_project, tmp_path):
    fake_backend()
    _project, target = lean_project("theorem demo : True := by\n  trivial\n")
    invalid = tmp_path / "NotAProject"
    invalid.mkdir()
    probe = LeanProbe()
    payload = probe.check_target(target, theorem_id="demo", cwd=invalid)
    assert payload["success"] is False
    assert payload["error_code"] == "no_project_root"
    assert "lakefile" in payload["hint"]


def test_prepare_target_not_found_returns_error_code(fake_backend, lean_project):
    fake_backend()
    project, target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    payload = probe.prepare_file(target, theorem_id="missing", cwd=project)
    assert payload["success"] is False
    assert payload["error_code"] == "target_not_found"


def test_header_change_restarts_incremental_session(fake_backend, lean_project):
    state = fake_backend()
    project, target = lean_project("import Mathlib\n\ntheorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    assert probe.check_target(target, theorem_id="demo", cwd=project)["ok"] is True
    target.write_text("import Std\n\ntheorem demo : True := by\n  trivial\n", encoding="utf-8")
    assert probe.check_target(target, theorem_id="demo", cwd=project)["ok"] is True
    assert len(state["servers"]) == 2


def test_dead_server_restart_rebuilds_env(fake_backend, lean_project):
    # The first REPL dies on any env-bearing command. The probe must restart and
    # REBUILD the header/env on the fresh server (fresh env ids), never replay the
    # stale env id (which the fresh server would reject).
    state = fake_backend(first_server_dies_on_env=True)
    project, target = lean_project("import Mathlib\n\ntheorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    payload = probe.check_target(target, theorem_id="demo", cwd=project)
    assert payload["success"] is True
    assert payload["ok"] is True
    assert len(state["servers"]) == 2
    assert state["servers"][0].killed is True


def test_timeout_sets_structured_fields(fake_backend, lean_project, monkeypatch):
    fake_backend()
    project, target = lean_project("import Mathlib\n\ntheorem timeout_demo : True := by\n  trivial\n")
    from lean_probe import sessions

    real_run = sessions.run_command

    def _run(server, cmd, *, env, include_tactics, timeout_s):
        if "timeout_demo" in cmd:
            return None, 0.01, "request timed out", ErrorCode.TIMEOUT, True
        return real_run(server, cmd, env=env, include_tactics=include_tactics, timeout_s=timeout_s)

    monkeypatch.setattr(sessions, "run_command", _run)
    monkeypatch.setattr("lean_probe.probe.run_command", _run)
    probe = LeanProbe()
    payload = probe.check_target(target, theorem_id="timeout_demo", cwd=project)
    assert payload["success"] is False
    assert payload["timed_out"] is True
    assert payload["error_code"] == "timeout"


# --------------------------------------------------------------------- check_code


def test_check_code_valid_snippet_is_ok(fake_backend, lean_project):
    fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    payload = probe.check_code("import Mathlib\n\ntheorem ex : True := by\n  trivial\n", cwd=project)
    assert payload["success"] is True
    assert payload["ok"] is True
    assert payload["has_sorry"] is False
    assert payload["action"] == "check"


def test_check_code_reports_errors(fake_backend, lean_project):
    fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    payload = probe.check_code("theorem ex : True := by\n  bad\n", cwd=project)
    assert payload["success"] is True
    assert payload["ok"] is False
    assert payload["has_errors"] is True


def test_check_code_detects_sorry(fake_backend, lean_project):
    fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    payload = probe.check_code("theorem ex (n : Nat) : n = n := by sorry", cwd=project)
    assert payload["success"] is True
    assert payload["ok"] is False
    assert payload["has_sorry"] is True
    assert payload["sorries"]


def test_check_code_reuses_warm_server(fake_backend, lean_project):
    state = fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    first = probe.check_code("theorem a : True := by trivial", cwd=project)
    second = probe.check_code("theorem b : True := by trivial", cwd=project)
    assert first["cache"]["reused_server"] is False
    assert second["cache"]["reused_server"] is True
    assert len(state["servers"]) == 1


def test_check_code_invalid_cwd_returns_hint(fake_backend, tmp_path):
    fake_backend()
    invalid = tmp_path / "NotAProject"
    invalid.mkdir()
    probe = LeanProbe()
    payload = probe.check_code("theorem ex : True := by trivial", cwd=invalid)
    assert payload["success"] is False
    assert payload["error_code"] == "no_project_root"
    assert payload["hint"]


# --------------------------------------------------------------------- proof states


def test_proof_state_and_tactic_step(fake_backend, lean_project):
    fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    state = probe.proof_state_from_code("theorem ex (n : Nat) : n = n := by sorry", cwd=project)
    step = probe.tactic_step(state["session_id"], state["sorries"][0]["proof_state"], "rfl")
    assert state["success"] is True
    assert state["sorries"][0]["proof_state"] == 5
    assert step["ok"] is True
    assert step["proof_status"] == "Completed"


def test_proof_state_without_sorry_is_not_ok(fake_backend, lean_project):
    fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    state = probe.proof_state_from_code("theorem ex : True := by trivial", cwd=project)
    assert state["success"] is True
    assert state["ok"] is False
    assert state["sorries"] == []


def test_close_state_releases_session(fake_backend, lean_project):
    state = fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    opened = probe.proof_state_from_code("theorem ex (n : Nat) : n = n := by sorry", cwd=project)
    state_server = state["servers"][-1]
    closed = probe.close_state(opened["session_id"])
    second = probe.close_state(opened["session_id"])
    assert closed["ok"] is True
    assert state_server.killed is True
    assert second["success"] is False
    assert second["error_code"] == "unknown_session"


def test_code_sessions_are_lru_bounded(fake_backend, lean_project):
    state = fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe(max_code_sessions=2)
    first = probe.proof_state_from_code("theorem a : True := by sorry", cwd=project)
    second = probe.proof_state_from_code("theorem b : True := by sorry", cwd=project)
    third = probe.proof_state_from_code("theorem c : True := by sorry", cwd=project)
    assert list(probe._code_sessions.keys()) == [second["session_id"], third["session_id"]]
    assert first["session_id"] not in probe._code_sessions
    assert state["servers"][0].killed is True


def test_tactic_step_dead_server_marks_session_dead(fake_backend, lean_project):
    fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")
    probe = LeanProbe()
    opened = probe.proof_state_from_code("theorem ex (n : Nat) : n = n := by sorry", cwd=project)
    session = probe._code_sessions[opened["session_id"]]

    class _DeadStepServer:
        def run(self, request, timeout=None):
            raise RuntimeError("Lean server is not running")

        def kill(self):
            pass

    session.server = _DeadStepServer()
    step = probe.tactic_step(opened["session_id"], opened["sorries"][0]["proof_state"], "rfl")
    assert step["success"] is False
    assert step["error_code"] == "session_dead"
    assert step["session_dead"] is True
    assert "lean_proof_state" in step["hint"]
    assert opened["session_id"] not in probe._code_sessions


def test_resolve_file_path_prefers_project_root(tmp_path):
    project = tmp_path / "Project"
    project.mkdir()
    probe = LeanProbe()
    assert probe._resolve_file_path("Demo/Main.lean", project) == (project / "Demo" / "Main.lean").resolve()
