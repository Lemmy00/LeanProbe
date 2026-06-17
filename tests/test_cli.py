from __future__ import annotations

import json

from lean_probe import __version__, cli


def test_cli_check_snippet_outputs_json(fake_backend, lean_project, capsys):
    fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")
    code = cli.main(["check", "--cwd", str(project), "--code", "theorem ex : True := by trivial"])
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["tool"] == "lean_probe"
    assert output["action"] == "check"
    assert output["ok"] is True


def test_cli_check_target_outputs_json(fake_backend, lean_project, capsys):
    fake_backend()
    project, target = lean_project("theorem demo : True := by\n  trivial\n")
    code = cli.main(["check-target", str(target), "demo", "--cwd", str(project)])
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["action"] == "check"
    assert output["target"] == "demo"


def test_cli_status_reports_readiness(fake_backend, lean_project, capsys):
    fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")
    code = cli.main(["status", "--cwd", str(project)])
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["available"] is True
    assert output["project_root"] == str(project)
    assert output["degraded_codes"] == []


def test_cli_check_target_with_feedback_pretty(fake_backend, lean_project, capsys):
    fake_backend()
    project, target = lean_project("import Mathlib\n\ntheorem demo : True := by\n  trivial\n")
    code = cli.main(["check-target", str(target), "demo", "--cwd", str(project), "--with-feedback", "--pretty"])
    text = capsys.readouterr().out
    assert code == 0
    payload = json.loads(text)
    assert payload["action"] == "feedback"
    assert payload["tactics"]


def test_cli_replacement_file_and_failure_exit_code(fake_backend, lean_project, tmp_path, capsys):
    fake_backend()
    project, target = lean_project("theorem demo : True := by\n  trivial\n")
    replacement = tmp_path / "replacement.lean"
    replacement.write_text("theorem demo : True := by\n  trivial\n", encoding="utf-8")
    ok_code = cli.main(
        ["check-target", str(target), "demo", "--cwd", str(project), "--replacement-file", str(replacement)]
    )
    capsys.readouterr()
    bad_code = cli.main(["check-target", str(target), "missing", "--cwd", str(project)])
    output = json.loads(capsys.readouterr().out)
    assert ok_code == 0
    assert bad_code == 1
    assert output["error_code"] == "target_not_found"


def test_cli_strict_cwd_miss_exits_one(fake_backend, lean_project, tmp_path, capsys):
    fake_backend()
    _project, target = lean_project("theorem demo : True := by\n  trivial\n")
    invalid = tmp_path / "NotAProject"
    invalid.mkdir()
    code = cli.main(["check-target", str(target), "demo", "--cwd", str(invalid)])
    output = json.loads(capsys.readouterr().out)
    assert code == 1
    assert output["error_code"] == "no_project_root"
    assert output["hint"]


def test_cli_proof_state_reads_stdin(fake_backend, lean_project, monkeypatch, capsys):
    fake_backend()
    project, _target = lean_project("theorem demo : True := by\n  trivial\n")

    class _Stdin:
        def read(self):
            return "theorem demo : True := by sorry"

    monkeypatch.setattr(cli.sys, "stdin", _Stdin())
    code = cli.main(["proof-state", "--cwd", str(project)])
    output = json.loads(capsys.readouterr().out)
    assert code == 0
    assert output["action"] == "state"
    assert output["session_id"]


def test_cli_version_uses_package_version(capsys):
    try:
        cli.main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert capsys.readouterr().out.strip() == f"lean-probe {__version__}"
