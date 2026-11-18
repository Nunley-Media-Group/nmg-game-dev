"""Fakes for the /convert-to-godot tests (#249 AC11–AC13).

``make_unreal_consumer`` builds a fixture Unreal consumer in a real git repository with one commit:
a ``.uproject``, two finalized assets, unfinalized ``.uasset`` and ``.umap`` files, C++ sources,
``SourceArt`` Blender sources whose names differ in case from the assets, a Music and an SFX WAV, a
design backlog with scaffolded and planned entries, the Unreal start script, and Claude settings
with an Unreal SessionStart hook and ``UE_*`` env keys. The collaborator fakes record each call and
write what the real stage would leave behind, so no Blender, Godot, or ffmpeg runs.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Collection
from dataclasses import dataclass, field
from pathlib import Path

from nmg_game_dev.convert.plan import AssetItem, AudioItem
from nmg_game_dev.convert.runner import ScaffoldOutcome
from nmg_game_dev.pipeline.errors import PipelineError

BLENDER_HOOK = 'bash "$CLAUDE_PROJECT_DIR/scripts/start-blender-mcp.sh"'
UNREAL_HOOK = 'bash "$CLAUDE_PROJECT_DIR/scripts/start-unreal-mcp.sh"'
FAIL_CODE = "finalize.validate_failed"
FAIL_REMEDIATION = "Fix the contract violation in Blender, then finalize again."


def git(root: Path, *args: str) -> str:
    """Run git in ``root`` with a fixed identity and return stdout."""
    proc = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout


def _write(path: Path, text: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")


def _backlog_entry(entry_type: str, name: str, status: str, **fields: object) -> dict[str, object]:
    return {
        "type": entry_type,
        "name": name,
        "asset_name": name,
        "source": f"docs/design/{name.lower()}.md",
        "fields": dict(fields),
        "status": status,
    }


def make_unreal_consumer(root: Path, *, uproject: bool = True, commit: bool = True) -> Path:
    """Create the fixture consumer at ``root`` and return it."""
    root.mkdir(parents=True, exist_ok=True)
    if uproject:
        _write(root / "Game.uproject", '{"FileVersion": 3}\n')
    for category, name, asset_class in (
        ("Props", "Crate", "standard_prop"),
        ("Characters", "Hero", "character"),
    ):
        folder = root / "Content" / category / name
        for variant in ("Desktop", "Mobile"):
            _write(folder / variant / f"SM_{name}.uasset", b"uasset")
        _write(folder / "Mobile" / "nmg-asset.json", json.dumps({"class": asset_class}) + "\n")
    _write(root / "Content" / "Maps" / "Main.umap", b"umap")
    _write(root / "Content" / "Misc" / "Stray.uasset", b"uasset")
    _write(root / "Source" / "Game" / "Game.cpp", "// game\n")
    _write(root / "Source" / "Game" / "Game.h", "#pragma once\n")
    _write(root / "Config" / "DefaultEngine.ini", "[/Script/Engine]\n")
    _write(root / "Plugins" / "Other" / "Other.uplugin", "{}\n")
    _write(root / "scripts" / "start-unreal-mcp.sh", "#!/usr/bin/env bash\n")
    _write(root / "scripts" / "start-blender-mcp.sh", "#!/usr/bin/env bash\n")
    _write(root / "SourceArt" / "Props" / "crate.blend", b"blend")
    _write(root / "SourceArt" / "Characters" / "HERO.blend", b"blend")
    _write(root / "SourceArt" / "Audio" / "SFX" / "Click.wav", b"RIFFclick")
    _write(root / "SourceArt" / "Audio" / "Music" / "Theme.wav", b"RIFFtheme")
    backlog = {
        "version": 1,
        "entries": [
            _backlog_entry("asset", "Crate", "finalized", category="Props"),
            _backlog_entry("mission", "Intro", "scaffolded", act=1, region="Harbor"),
            _backlog_entry("mission", "Later", "planned", act=2),
            _backlog_entry("region", "Harbor", "scaffolded"),
            _backlog_entry("system", "Inventory", "scaffolded"),
        ],
    }
    _write(root / "docs" / "design" / "backlog.json", json.dumps(backlog, indent=2) + "\n")
    settings = {
        "model": "opus",
        "env": {"UE_ROOT": "/Engines/5.8", "UE_EDITOR": "x", "KEEP_ME": "1"},
        "hooks": {
            "SessionStart": [
                {
                    "matcher": "startup",
                    "hooks": [
                        {"type": "command", "command": BLENDER_HOOK},
                        {"type": "command", "command": UNREAL_HOOK, "timeout": 900},
                    ],
                },
                {"matcher": "resume", "hooks": [{"type": "command", "command": UNREAL_HOOK}]},
            ]
        },
    }
    _write(root / ".claude" / "settings.json", json.dumps(settings, indent=2) + "\n")
    _write(root / "README.md", "# Game\n")
    if commit:
        git(root, "init", "-q")
        git(root, "add", "-A")
        git(root, "commit", "-q", "-m", "fixture")
    return root


def snapshot(root: Path) -> dict[str, bytes]:
    """Every work-tree file under ``root`` (outside ``.git``) mapped to its bytes."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


@dataclass
class Collaborators:
    """Recording fakes for every ``run_convert`` collaborator.

    ``fail`` holds item keys whose stage raises a ``PipelineError``. ``scaffold_fail`` holds
    ``<type>/<Name>`` entries the scaffold fake reports as errors.
    """

    fail: set[str] = field(default_factory=set)
    scaffold_fail: set[str] = field(default_factory=set)
    onboard_calls: list[Path] = field(default_factory=list)
    finalized: list[tuple[str, str, str, Path | None, Path]] = field(default_factory=list)
    imported: list[tuple[str, str, Path, bool]] = field(default_factory=list)
    scaffold_calls: int = 0
    preflight_calls: int = 0
    preflight_error: PipelineError | None = None

    def onboard(self, root: Path) -> object:
        self.onboard_calls.append(root)
        project = root / "game" / "project.godot"
        if not project.exists():
            _write(project, 'config_version=5\n\n[application]\n\nconfig/name="Game"\n')
        return []

    def _maybe_fail(self, key: str) -> None:
        if key in self.fail:
            raise PipelineError(
                code=FAIL_CODE,
                message=f"{key} failed validation.",
                remediation=FAIL_REMEDIATION,
                stage="validate",
            )

    def finalize(self, item: AssetItem, export_root: Path) -> object:
        self.finalized.append(
            (item.category, item.name, item.asset_class, item.source, export_root)
        )
        self._maybe_fail(item.key)
        for variant in ("Desktop", "Mobile"):
            _write(export_root / item.category / item.name / variant / f"{item.name}.glb", b"glb")
        return None

    def import_wav(self, root: Path, item: AudioItem) -> object:
        self.imported.append((item.kind, item.name, item.wav, item.loop))
        self._maybe_fail(item.key)
        suffix = "ogg" if item.kind == "Music" else "wav"
        _write(root / "game" / "assets" / "Audio" / f"{item.name}.{suffix}", b"audio")
        return None

    def scaffold(self, root: Path) -> list[ScaffoldOutcome]:
        self.scaffold_calls += 1
        backlog = json.loads((root / "docs" / "design" / "backlog.json").read_text())
        outcomes: list[ScaffoldOutcome] = []
        for entry in backlog["entries"]:
            if entry["type"] not in ("region", "mission", "system"):
                continue
            if entry["status"] != "scaffolded":
                continue
            ident = f"{entry['type']}/{entry['asset_name']}"
            if ident in self.scaffold_fail:
                outcomes.append(
                    ScaffoldOutcome(
                        entry["type"], entry["asset_name"], "design.scaffold_failed", "disk full"
                    )
                )
                continue
            _write(root / "game" / "scaffolded" / f"{entry['asset_name']}.txt", "ok\n")
            outcomes.append(ScaffoldOutcome(entry["type"], entry["asset_name"]))
        return outcomes

    def preflight(self) -> object:
        self.preflight_calls += 1
        if self.preflight_error is not None:
            raise self.preflight_error
        return None

    def kwargs(self) -> dict[str, object]:
        """The collaborator keyword arguments for ``run_convert``."""
        return {
            "onboard": self.onboard,
            "finalize": self.finalize,
            "import_wav": self.import_wav,
            "scaffold": self.scaffold,
            "preflight": self.preflight,
        }


def finalized_names(fakes: Collaborators) -> list[str]:
    return [name for _category, name, *_rest in fakes.finalized]


def tracked(root: Path, paths: Collection[str]) -> list[str]:
    """The given paths that git still tracks."""
    out = git(root, "ls-files", "--", *paths)
    return sorted({line.split("/")[0] for line in out.splitlines() if line})
