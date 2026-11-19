"""Fakes for the ship tests: a temp consumer Godot project, a fake Godot, and PATH shims.

The consumer is ``consumer/game/project.godot`` with ``export_presets.cfg`` from
``render_export_presets``. Godot is a ``FakeGodotRunner`` whose ``--export-release`` handler writes
each platform's artifact where the ship asked for it. Every other tool the ship flow calls
(codesign, security, xcrun, ditto) becomes a shell wrapper in the sandbox's ``bin/`` folder that
runs ``tests/ship_shim.py``, which logs argv and returns canned output. The environment is built
from scratch rather than inherited, so no real ``NOTARIZATION_*``, iOS, or keystore value reaches a
script. Every credential here is a placeholder. Nothing contacts Apple, Google, a store, or a
keychain.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from nmg_game_dev.godot.runner import CommandResult
    from nmg_game_dev.ship.artifacts import ReleaseEntry
    from tests.godot_fakes import FakeGodotRunner

# The ship and Godot imports are deferred so tests that only need REPO_ROOT or parse_frontmatter
# do not import the pipeline.

SHIM: Final[Path] = Path(__file__).resolve().parent / "ship_shim.py"
REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
SCRIPTS: Final[Path] = REPO_ROOT / "scripts"
WRAPPED_TOOLS: Final[tuple[str, ...]] = ("codesign", "security", "xcrun", "ditto")
PROJECT_NAME: Final = "Dogfood Game!"
APP: Final = "DogfoodGame"
"""``PROJECT_NAME`` with its non-alphanumerics removed: the exported artifact's name."""
VERSION: Final = "1.2.3"
"""The consumer's version. Its ``CHANGELOG.md`` has a ``## 1.2.3`` section."""

VERSION_KEYS: Final[frozenset[str]] = frozenset(
    {
        "config/version",
        "application/short_version",
        "application/version",
        "version/name",
        "version/code",
        "application/file_version",
        "application/product_version",
    }
)
"""The config keys a version ship sets; no other key may change (#254 AC1)."""


@dataclass
class ShipSandbox:
    """A consumer Godot project with a fake Godot and fake tools on PATH.

    Attributes:
        project: ``consumer/game/project.godot``.
        bin_dir: Folder of wrappers that come first on PATH.
        log: JSON-lines file where every fake tool records its argv.
        godot: The fake headless Godot every ship run uses.
        env: The complete environment every ship run uses. It is never inherited.
        web_pack_bytes: Size of the ``index.pck`` the fake web export writes.
        failing_preset: A preset whose export exits 1, or ``None``.
        presets_at_export: ``export_presets.cfg`` text seen by each export, keyed by preset.
    """

    project: Path
    bin_dir: Path
    log: Path
    godot: FakeGodotRunner
    env: dict[str, str] = field(default_factory=dict)
    web_pack_bytes: int = 1024
    failing_preset: str | None = None
    presets_at_export: dict[str, str] = field(default_factory=dict)

    @property
    def game(self) -> Path:
        return self.project.parent

    @property
    def release_dir(self) -> Path:
        return self.game.parent / "release"

    def ship(
        self,
        target: str,
        *,
        dry_run: bool = False,
        bump: str | None = None,
        version: str | None = None,
        **env: str,
    ) -> list[ReleaseEntry]:
        """Run the real ship flow against this sandbox, with ``env`` layered over its env.

        ``bump`` and ``version`` are the ``--bump`` and ``--version`` flags (#254).
        """
        from nmg_game_dev.ship.runner import run_ship  # noqa: PLC0415

        return run_ship(
            target,
            self.project,
            self.release_dir,
            dry_run,
            {**self.env, **env},
            godot=self.godot,
            bump=bump,
            version=version,
        )

    def calls(self, tool: str | None = None) -> list[list[str]]:
        """Return the argv of every recorded shim call, optionally only for one tool."""
        if not self.log.is_file():
            return []
        out: list[list[str]] = []
        for line in self.log.read_text(encoding="utf-8").splitlines():
            record: dict[str, Any] = json.loads(line)
            if tool is None or record["tool"] == tool:
                out.append([str(arg) for arg in record["argv"]])
        return out

    def invoked(self, tool: str) -> bool:
        return bool(self.calls(tool))

    def godot_commands(self, flag: str | None = None) -> list[list[str]]:
        """Return every recorded Godot argv, optionally only those starting with ``flag``."""
        return [call for call in self.godot.calls if flag is None or call[:1] == [flag]]

    def exports(self) -> list[str]:
        """Return the preset name of each ``--export-release`` call, in order."""
        return [call[1] for call in self.godot_commands("--export-release")]

    def export(self, args: list[str], project: Path) -> CommandResult:
        """The fake ``--export-release <preset> <out>``: write the artifact Godot would write."""
        from nmg_game_dev.godot.runner import CommandResult  # noqa: PLC0415

        preset, out = args[1], Path(args[2])
        presets = project / "export_presets.cfg"
        self.presets_at_export[preset] = presets.read_text(encoding="utf-8")
        if preset == self.failing_preset:
            return CommandResult(1, stderr=f"ERROR: Cannot export project with preset {preset}\n")
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.suffix == ".app":
            binary = out / "Contents" / "MacOS" / out.stem
            binary.parent.mkdir(parents=True)
            binary.write_bytes(b"macho")
        elif out.name == "index.html":
            out.write_text("<html></html>", encoding="utf-8")
            (out.parent / "index.js").write_text("// engine", encoding="utf-8")
            (out.parent / "index.wasm").write_bytes(b"wasm")
            with (out.parent / "index.pck").open("wb") as handle:
                handle.truncate(self.web_pack_bytes)
        else:
            out.write_bytes(f"{preset} artifact".encode())
        return CommandResult(0, stdout=f"Exported {preset} to {out}\n")


def make_sandbox(root: Path) -> ShipSandbox:
    """Build a consumer Godot project, a fake Godot, and PATH shims under ``root``."""
    from nmg_game_dev.godot.presets import render_export_presets  # noqa: PLC0415
    from tests.godot_fakes import FakeGodotRunner  # noqa: PLC0415

    game = root / "consumer" / "game"
    (game / "scripts").mkdir(parents=True)
    project = game / "project.godot"
    project.write_text(
        f'config_version=5\n\n[application]\n\nconfig/name="{PROJECT_NAME}"\n'
        f'config/version="{VERSION}"\n',
        encoding="utf-8",
    )
    (game.parent / "CHANGELOG.md").write_text(
        f"# Changelog\n\n## {VERSION}\n\n- The first player build.\n", encoding="utf-8"
    )
    (game / "export_presets.cfg").write_text(render_export_presets(PROJECT_NAME), encoding="utf-8")
    (game / "scripts" / "player.gd").write_text("extends Node3D\n", encoding="utf-8")
    (game / "main.gd").write_text("extends Node\n", encoding="utf-8")
    cache = game / ".godot" / "editor"
    cache.mkdir(parents=True)
    (cache / "cached.gd").write_text("extends Node\n", encoding="utf-8")

    bin_dir = root / "bin"
    bin_dir.mkdir()
    for tool in WRAPPED_TOOLS:
        _write_wrapper(bin_dir / tool, tool)

    log = root / "calls.jsonl"
    env = {
        "PATH": os.pathsep.join([str(bin_dir), "/usr/bin", "/bin", "/usr/sbin", "/sbin"]),
        "HOME": str(root),
        "LANG": "C",
        "NMG_SHIP_FAKE_LOG": str(log),
        "NOTARIZATION_APPLE_ID": "ship-test@example.invalid",
        "NOTARIZATION_APP_SPECIFIC_PASSWORD": "placeholder-app-password",
        "NOTARIZATION_TEAM_ID": "SMOKE00000",
        "IOS_PROVISIONING_PROFILE": str(root / "Dogfood.mobileprovision"),
        "IOS_TEAM_ID": "SMOKE00000",
        "ANDROID_KEYSTORE": str(root / "upload.keystore"),
        "ANDROID_KEYSTORE_PASSWORD": "placeholder-keystore-password",
    }
    sandbox = ShipSandbox(
        project=project, bin_dir=bin_dir, log=log, godot=FakeGodotRunner(), env=env
    )
    sandbox.godot.responses["--export-release"] = sandbox.export
    return sandbox


def write_mobile_report(game: Path, rel_dir: str, report: dict[str, object] | None) -> Path:
    """Create ``game/assets/<rel_dir>/Mobile/`` and, unless ``report`` is None, its report."""
    folder = game / "assets" / rel_dir / "Mobile"
    folder.mkdir(parents=True, exist_ok=True)
    if report is not None:
        (folder / "nmg-asset.json").write_text(json.dumps(report), encoding="utf-8")
    return folder


def run_script(
    sandbox: ShipSandbox,
    name: str,
    *args: str,
    extra_env: dict[str, str] | None = None,
    without: tuple[str, ...] = (),
) -> subprocess.CompletedProcess[str]:
    """Run ``scripts/<name>`` under the sandbox environment, minus any ``without`` variables."""
    merged = {**sandbox.env, **(extra_env or {})}
    env = {key: value for key, value in merged.items() if key not in without}
    return subprocess.run(
        [str(SCRIPTS / name), *args],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def parse_frontmatter(text: str) -> dict[str, str]:
    """Return the ``key: value`` lines between the leading ``---`` fences of a SKILL.md."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip()] = value.strip()
    return fields


def _write_wrapper(path: Path, tool: str) -> None:
    path.write_text(
        f"#!/bin/sh\nexec '{sys.executable}' '{SHIM}' '{tool}' \"$@\"\n",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def changed_keys(before: str, after: str) -> set[str]:
    """The key of every config line that differs between two texts (#254)."""
    before_lines, after_lines = before.splitlines(), after.splitlines()
    changed = [line for line in before_lines if line not in after_lines]
    changed += [line for line in after_lines if line not in before_lines]
    return {line.split("=", 1)[0].strip() for line in changed}


def consumer_bytes(sandbox: ShipSandbox) -> dict[str, bytes]:
    """The bytes of the project, its export presets, and the consumer's CHANGELOG.md (#254)."""
    paths = {
        "project": sandbox.project,
        "presets": sandbox.game / "export_presets.cfg",
        "changelog": sandbox.game.parent / "CHANGELOG.md",
    }
    return {name: path.read_bytes() for name, path in paths.items()}
