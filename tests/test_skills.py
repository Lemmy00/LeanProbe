from __future__ import annotations

from lean_probe import skills


def test_skill_frontmatter_is_valid():
    meta = skills.parse_frontmatter(skills.read_skill_text())
    assert meta.get("name") == "lean-probe"
    assert "Lean" in meta.get("description", "")
    assert len(meta["description"]) > 40  # a real, non-empty trigger description


def test_bundle_contains_skill_md():
    names = [rel for rel, _ in skills.bundle_files()]
    assert "SKILL.md" in names
    assert all(isinstance(data, bytes) for _, data in skills.bundle_files())


def test_discover_auto_targets_only_present_clients(tmp_path):
    (tmp_path / ".claude").mkdir()  # codex absent
    targets = skills.discover_targets(clients=["all"], home=tmp_path)
    assert [t.client for t in targets] == ["claude"]
    assert targets[0].skill_file == tmp_path / ".claude" / "skills" / "lean-probe" / "SKILL.md"


def test_discover_auto_targets_both_when_both_present(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".codex").mkdir()
    targets = skills.discover_targets(clients=["all"], home=tmp_path)
    assert sorted(t.client for t in targets) == ["claude", "codex"]


def test_discover_explicit_client_targets_even_if_absent(tmp_path):
    targets = skills.discover_targets(clients=["codex"], home=tmp_path)
    assert [t.client for t in targets] == ["codex"]
    assert not targets[0].base.exists()  # nothing created during discovery


def test_discover_skills_dirs_override_clients(tmp_path):
    (tmp_path / ".claude").mkdir()
    explicit = tmp_path / "proj" / ".claude" / "skills"
    targets = skills.discover_targets(clients=["all"], skills_dirs=[explicit], home=tmp_path)
    assert [t.client for t in targets] == ["dir"]
    assert targets[0].skill_dir == explicit / "lean-probe"


def test_install_creates_unchanged_then_updated(tmp_path):
    targets = skills.discover_targets(clients=["claude"], home=tmp_path)

    created = skills.install_skill(targets)
    assert [r.status for r in created] == ["created"]
    skill_file = targets[0].skill_file
    assert skill_file.read_text(encoding="utf-8") == skills.read_skill_text()

    unchanged = skills.install_skill(targets)
    assert [r.status for r in unchanged] == ["unchanged"]

    skill_file.write_text("stale content", encoding="utf-8")
    updated = skills.install_skill(targets)
    assert [r.status for r in updated] == ["updated"]
    assert skill_file.read_text(encoding="utf-8") == skills.read_skill_text()


def test_install_dry_run_writes_nothing(tmp_path):
    targets = skills.discover_targets(clients=["claude"], home=tmp_path)
    results = skills.install_skill(targets, dry_run=True)
    assert [r.status for r in results] == ["created"]
    assert results[0].action == "would create"
    assert not targets[0].skill_file.exists()


def test_install_dry_run_reports_would_update_without_writing(tmp_path):
    targets = skills.discover_targets(clients=["claude"], home=tmp_path)
    skills.install_skill(targets)  # create it first
    targets[0].skill_file.write_text("stale content", encoding="utf-8")

    results = skills.install_skill(targets, dry_run=True)
    assert [r.status for r in results] == ["updated"]
    assert results[0].action == "would update"
    assert targets[0].skill_file.read_text(encoding="utf-8") == "stale content"  # untouched


def test_discover_dedups_repeated_skills_dirs(tmp_path):
    root = tmp_path / "root"
    targets = skills.discover_targets(skills_dirs=[root, root, tmp_path / "root"])
    assert len(targets) == 1


def test_install_into_explicit_dir(tmp_path):
    root = tmp_path / "skills-root"
    targets = skills.discover_targets(skills_dirs=[root])
    skills.install_skill(targets)
    assert (root / "lean-probe" / "SKILL.md").read_text(encoding="utf-8") == skills.read_skill_text()
