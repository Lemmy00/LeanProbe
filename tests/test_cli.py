from __future__ import annotations

import json
from types import SimpleNamespace

from lean_probe import cli, core


def _install_fake_lean_interact(monkeypatch):
    class _Command:
        def __init__(self, *, cmd: str, all_tactics: bool = False, env=None):
            self.cmd = cmd
            self.all_tactics = all_tactics
            self.env = env

        def model_copy(self, *, update):
            copied = _Command(cmd=self.cmd, all_tactics=self.all_tactics, env=self.env)
            for key, value in update.items():
                setattr(copied, key, value)
            return copied

    class _ProofStep:
        def __init__(self, *, proof_state: int, tactic: str):
            self.proof_state = proof_state
            self.tactic = tactic

    class _Response:
        env = 1
        messages = []
        sorries = []
        tactics = []

        def has_errors(self):
            return False

        def lean_code_is_valid(self, *, allow_sorry: bool = False):
            return True

    class _Server:
        def __init__(self, config):
            self.config = config

        def run(self, request, timeout=None):
            return _Response()

        def kill(self):
            pass

    class _Config:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class _Project:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(core, "_import_lean_interact", lambda: (_Command, _ProofStep, _Config, _Server, _Project, ""))
    monkeypatch.setattr(core, "_local_repl_dir", lambda project_root: project_root / ".lake" / "packages" / "repl")


def test_cli_check_outputs_json(monkeypatch, tmp_path, capsys):
    _install_fake_lean_interact(monkeypatch)
    project = tmp_path / "Demo"
    module_dir = project / "Demo"
    module_dir.mkdir(parents=True)
    (project / "lakefile.lean").write_text("import Lake\n", encoding="utf-8")
    target = module_dir / "Main.lean"
    target.write_text("theorem demo : True := by\n  trivial\n", encoding="utf-8")

    code = cli.main(["check", str(target), "demo", "--cwd", str(project)])
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["tool"] == "lean_probe"
    assert output["action"] == "check"
    assert output["target"] == "demo"


def test_cli_state_reads_stdin(monkeypatch, tmp_path, capsys):
    _install_fake_lean_interact(monkeypatch)
    project = tmp_path / "Demo"
    project.mkdir()
    (project / "lakefile.lean").write_text("import Lake\n", encoding="utf-8")

    class _Stdin:
        def read(self):
            return "theorem demo : True := by sorry"

    monkeypatch.setattr(cli.sys, "stdin", _Stdin())
    code = cli.main(["state", "--cwd", str(project)])
    output = json.loads(capsys.readouterr().out)

    assert code == 0
    assert output["action"] == "state"
    assert output["session_id"]
