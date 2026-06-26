"""Install the LeanProbe usage skill into agent clients (Claude Code, Codex).

The canonical skill bundle ships *inside* the package at ``lean_probe/skill/`` so
a plain ``pip install lean-probe`` carries it — installing the skill needs no repo
checkout. Agent clients discover skills under ``<base>/skills/<name>/SKILL.md``
(Claude Code reads ``~/.claude/skills``; Codex reads ``~/.codex/skills``), both
with the same layout, so installing is just copying the bundle into each client's
skills directory.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any

SKILL_NAME = "lean-probe"

# Known agent clients and the home-relative base directory each reads skills from.
CLIENT_BASES: dict[str, str] = {
    "claude": ".claude",
    "codex": ".codex",
}
# Valid `--client` values: a specific client or "all" (every present client).
CLIENT_CHOICES: list[str] = ["all", *CLIENT_BASES]


def _bundle_root() -> Any:
    """The packaged skill bundle directory (``lean_probe/skill``)."""

    return resources.files("lean_probe").joinpath("skill")


def _iter_bundle(root: Any = None, prefix: str = "") -> Iterator[tuple[str, bytes]]:
    """Yield ``(relative_path, contents)`` for every file in the skill bundle."""

    node = _bundle_root() if root is None else root
    for entry in sorted(node.iterdir(), key=lambda e: e.name):
        rel = f"{prefix}{entry.name}"
        if entry.is_dir():
            yield from _iter_bundle(entry, prefix=f"{rel}/")
        else:
            yield rel, entry.read_bytes()


def bundle_files() -> list[tuple[str, bytes]]:
    """All files in the skill bundle as ``(relative_path, bytes)`` pairs."""

    return list(_iter_bundle())


def read_skill_text() -> str:
    """The canonical ``SKILL.md`` text shipped inside the package."""

    return _bundle_root().joinpath("SKILL.md").read_text(encoding="utf-8")


def parse_frontmatter(text: str) -> dict[str, str]:
    """Parse the leading ``---`` YAML frontmatter into a flat ``str -> str`` dict.

    Handles the small subset this skill uses: inline ``key: value`` scalars and
    folded/literal blocks (``key: >``/``>-``/``|``) whose indented continuation
    lines are joined with spaces. Not a general YAML parser.
    """

    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}

    data: dict[str, str] = {}
    body = lines[1:end]
    i = 0
    while i < len(body):
        raw = body[i]
        i += 1
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in raw:
            continue
        key, _, value = raw.partition(":")
        key = key.strip()
        value = value.strip()
        if value in {">", ">-", "|", "|-"}:
            collected: list[str] = []
            while i < len(body) and (not body[i].strip() or body[i][:1] in {" ", "\t"}):
                collected.append(body[i].strip())
                i += 1
            data[key] = " ".join(part for part in collected if part).strip()
        else:
            data[key] = value.strip().strip('"').strip("'")
    return data


def home_dir(home: str | Path | None = None) -> Path:
    return Path(home).expanduser() if home is not None else Path.home()


@dataclass(frozen=True)
class SkillTarget:
    """One place to install the skill: a ``skills`` root and the client it serves."""

    client: str  # "claude", "codex", or "dir" for an explicit --skills-dir
    skills_root: Path  # directory that holds skill folders, e.g. ~/.claude/skills
    base: Path | None = None  # client home base (~/.claude); None for explicit dirs

    @property
    def skill_dir(self) -> Path:
        return self.skills_root / SKILL_NAME

    @property
    def skill_file(self) -> Path:
        return self.skill_dir / "SKILL.md"


def discover_targets(
    *,
    clients: Iterable[str] | None = None,
    skills_dirs: Iterable[str | Path] | None = None,
    home: str | Path | None = None,
) -> list[SkillTarget]:
    """Resolve where to install.

    ``skills_dirs`` (explicit ``skills`` roots) take precedence: when given, only
    those are targeted. Otherwise ``clients`` decides:

    - ``"all"`` (the default) auto-detects — a client is targeted only if its base
      dir (``~/.claude`` / ``~/.codex``) already exists ("both if both present").
    - a named client (``"claude"``/``"codex"``) is always targeted, creating its
      directories if missing (explicit intent overrides auto-detection).
    """

    base_home = home_dir(home)
    targets: list[SkillTarget] = []
    seen: set[str] = set()

    def _add(target: SkillTarget) -> None:
        key = str(target.skill_dir)
        if key not in seen:
            seen.add(key)
            targets.append(target)

    if skills_dirs:
        for raw in skills_dirs:
            root = Path(raw).expanduser()
            _add(SkillTarget(client="dir", skills_root=root, base=None))
        return targets

    requested = list(clients) if clients is not None else ["all"]
    auto = "all" in requested
    names = list(CLIENT_BASES) if auto else [c for c in requested if c in CLIENT_BASES]
    for name in names:
        base = base_home / CLIENT_BASES[name]
        if auto and not base.is_dir():
            continue  # auto mode installs only to clients that are present
        _add(SkillTarget(client=name, skills_root=base / "skills", base=base))
    return targets


@dataclass
class InstallResult:
    target: SkillTarget
    status: str  # "created" | "updated" | "unchanged"
    dry_run: bool = False
    files: list[str] = field(default_factory=list)

    @property
    def action(self) -> str:
        if self.dry_run and self.status != "unchanged":
            return f"would {self.status[:-1] if self.status.endswith('d') else self.status}"
        return self.status


def _status_for(target: SkillTarget, bundle: list[tuple[str, bytes]]) -> str:
    if not target.skill_file.exists():
        return "created"
    for rel, data in bundle:
        dest = target.skill_dir / rel
        if not dest.exists() or dest.read_bytes() != data:
            return "updated"
    return "unchanged"


def install_skill(targets: Iterable[SkillTarget], *, dry_run: bool = False) -> list[InstallResult]:
    """Write the skill bundle into each target, idempotently.

    Returns one :class:`InstallResult` per target. ``unchanged`` targets are never
    rewritten. With ``dry_run`` nothing is written.
    """

    bundle = bundle_files()
    results: list[InstallResult] = []
    for target in targets:
        status = _status_for(target, bundle)
        if not dry_run and status != "unchanged":
            for rel, data in bundle:
                dest = target.skill_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(data)
        results.append(InstallResult(target=target, status=status, dry_run=dry_run, files=[rel for rel, _ in bundle]))
    return results
