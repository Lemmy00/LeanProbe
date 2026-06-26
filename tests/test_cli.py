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


def test_cli_install_skill_print_outputs_skill(capsys):
    code = cli.main(["install-skill", "--print"])
    out = capsys.readouterr().out
    assert code == 0
    assert "name: lean-probe" in out
    assert "lean_check" in out


def test_cli_install_skill_writes_into_home(tmp_path, capsys):
    (tmp_path / ".codex").mkdir()
    code = cli.main(["install-skill", "--home", str(tmp_path)])
    out = capsys.readouterr().out
    assert code == 0
    skill_file = tmp_path / ".codex" / "skills" / "lean-probe" / "SKILL.md"
    assert skill_file.is_file()
    assert "codex" in out and "created" in out


def test_cli_install_skill_into_explicit_dir(tmp_path, capsys):
    from lean_probe import skills

    root = tmp_path / "root"
    code = cli.main(["install-skill", "--skills-dir", str(root)])
    out = capsys.readouterr().out
    assert code == 0
    assert "dir" in out
    assert (root / "lean-probe" / "SKILL.md").read_text(encoding="utf-8") == skills.read_skill_text()


def test_cli_install_skill_named_client_creates_missing_home(tmp_path, capsys):
    # No ~/.codex pre-created: an explicit --client must create it anyway.
    code = cli.main(["install-skill", "--home", str(tmp_path), "--client", "codex"])
    out = capsys.readouterr().out
    assert code == 0
    assert (tmp_path / ".codex" / "skills" / "lean-probe" / "SKILL.md").is_file()
    assert "codex" in out and "created" in out


def test_cli_install_skill_dry_run_writes_nothing(tmp_path, capsys):
    code = cli.main(["install-skill", "--home", str(tmp_path), "--client", "claude", "--dry-run"])
    out = capsys.readouterr().out
    assert code == 0
    assert "[dry-run]" in out
    assert not (tmp_path / ".claude").exists()


def test_cli_install_skill_no_targets_exits_one(tmp_path, capsys):
    code = cli.main(["install-skill", "--home", str(tmp_path)])
    err = capsys.readouterr().err
    assert code == 1
    assert "No Claude Code or Codex" in err


def test_cli_version_uses_package_version(capsys):
    try:
        cli.main(["--version"])
    except SystemExit as exc:
        assert exc.code == 0
    assert capsys.readouterr().out.strip() == f"lean-probe {__version__}"
