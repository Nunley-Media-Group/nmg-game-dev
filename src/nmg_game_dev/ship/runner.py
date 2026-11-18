"""The ship runner: preflight, the pre-export gates, then each platform's Godot export (#249 FR9).

``run_ship`` follows the design order:

1. Expand the target, check the project, check the environment, and resolve the macOS signing
   identity.
2. ``--check-only`` every ``.gd`` under the project, skipping ``.godot/``
   (``ship.script_check_failed``).
3. ``res://tests/run_tests.gd`` when the project has one (``ship.tests_failed``).
4. The mobile budget gate for ios, android, and web, also in a dry run.
5. Per platform, ``--export-release "<preset>" <out>`` into ``release/<platform>/``. iOS patches
   its preset's team and provisioning UUID and restores ``export_presets.cfg`` byte-for-byte
   afterwards. Android installs the build template when ``android/build/`` is missing and passes
   the keystore only in the child environment. macOS is signed and notarized. A web ``index.pck``
   over 38 MiB prints ``ship.web_pack_large``.
6. ``release/RELEASE-NOTES.md`` with each artifact's SHA-256.

A failing gate or export raises ``ShipError`` and stops the run; a platform that already finished
keeps its artifact. A dry run prints every Godot, ``security``, sign and notarize command as
``DRY-RUN: <argv>`` with secrets as ``***``, runs no Godot, and writes
``release/<platform>/DRY-RUN.txt``.

See: the #249 design
(§ Ship)
"""

from __future__ import annotations

import plistlib
import re
import shlex
import shutil
import subprocess
import sys
from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from nmg_game_dev.godot.binary import resolve_godot
from nmg_game_dev.godot.presets import PRESETS
from nmg_game_dev.godot.project import parse_config, read_config
from nmg_game_dev.godot.runner import CommandResult, GodotRunner, SubprocessGodotRunner
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.quality.mobile_budgets import (
    GATE_CODE_ORDER,
    OVERRIDES_NAME,
    MobileBudgetAudit,
    check_mobile_budgets,
)
from nmg_game_dev.ship.artifacts import (
    ReleaseEntry,
    artifact_sha256,
    export_path,
    release_artifact,
)
from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.identity import Runner, resolve_signing_identity
from nmg_game_dev.ship.release_notes import write_release_notes
from nmg_game_dev.ship.targets import BUDGET_PLATFORMS, Platform, expand_target, preflight_env

SCRIPTS_DIR: Final[Path] = Path(__file__).resolve().parents[3] / "scripts"
DRY_RUN_FILE: Final = "DRY-RUN.txt"
PROJECT_FILE: Final = "project.godot"
PRESETS_FILE: Final = "export_presets.cfg"
TESTS_SCRIPT: Final = "tests/run_tests.gd"
WEB_PACK_LIMIT: Final = 38 * 1024 * 1024
"""Bytes: a web ``index.pck`` above this prints ``ship.web_pack_large``."""
DEFAULT_KEYSTORE_ALIAS: Final = "upload"
MASK: Final = "***"

IOS_TEAM_KEY: Final = "application/app_store_team_id"
IOS_PROFILE_KEY: Final = "application/provisioning_profile_uuid_release"


@dataclass
class _Ship:
    project_dir: Path
    release_dir: Path
    dry_run: bool
    env: Mapping[str, str]
    scripts_dir: Path
    identity: str
    app: str
    godot: GodotRunner | None
    godot_display: str
    run: Runner
    gate_lines: list[str] = field(default_factory=list)


def run_ship(
    target: str,
    project: Path,
    release_dir: Path,
    dry_run: bool,
    env: Mapping[str, str],
    *,
    godot: GodotRunner | None = None,
    scripts_dir: Path = SCRIPTS_DIR,
    run: Runner = subprocess.run,
) -> list[ReleaseEntry]:
    """Ship ``target`` from ``project`` (``game/project.godot``) into ``release_dir``.

    ``godot`` runs headless Godot; when ``None`` the binary is resolved from ``env`` (a dry run
    without one prints the literal ``godot``). ``run`` executes ``security`` for the signing
    identity and the iOS provisioning profile. Returns the published artifacts.
    """
    platforms = expand_target(target)
    project_dir = _check_project(project).absolute()
    release_dir = release_dir.absolute()
    preflight_env(platforms, env)
    identity = resolve_signing_identity(env, run, dry_run=dry_run) if "macos" in platforms else ""
    presets = _check_presets(project_dir, platforms)
    runner, display = _godot(godot, env, dry_run)
    ship = _Ship(
        project_dir=project_dir,
        release_dir=release_dir,
        dry_run=dry_run,
        env=env,
        scripts_dir=scripts_dir,
        identity=identity,
        app=app_name(project),
        godot=runner,
        godot_display=display,
        run=run,
    )

    _check_scripts(ship)
    _run_project_tests(ship)
    if any(platform in BUDGET_PLATFORMS for platform in platforms):
        _gate_mobile_budgets(
            check_mobile_budgets(project_dir / "assets", project_dir.parent / OVERRIDES_NAME)
        )

    entries: list[ReleaseEntry] = []
    for platform in platforms:
        entry = _ship_platform(platform, ship, presets[platform])
        if entry is not None:
            entries.append(entry)
    write_release_notes(release_dir, target, entries, dry_run, platforms)
    return entries


def app_name(project: Path) -> str:
    """``application/config/name`` with every non-alphanumeric removed, or ``Game``."""
    try:
        literal = read_config(project).get(("application", "config/name"), "")
    except (OSError, UnicodeDecodeError):
        literal = ""
    name = literal[1:-1] if len(literal) >= 2 and literal[0] == literal[-1] == '"' else literal
    return re.sub(r"[^A-Za-z0-9]", "", name) or "Game"


# Preflight ---------------------------------------------------------------------------------------


def _check_project(project: Path) -> Path:
    if project.name != PROJECT_FILE or not project.is_file():
        raise ShipError(
            code="ship.project_missing",
            message=f"Godot project not found: {project}",
            remediation=(
                "Pass --project with the path to the consumer's game/project.godot, or run "
                "/onboard-consumer to create it."
            ),
            stage="preflight",
        )
    return project.parent


def _godot(
    godot: GodotRunner | None, env: Mapping[str, str], dry_run: bool
) -> tuple[GodotRunner | None, str]:
    """Return the runner to use and the binary shown in printed commands.

    An injected runner owns its own binary, so commands show the literal ``godot`` for it.
    """
    if godot is not None:
        return godot, "godot"
    try:
        binary = resolve_godot(env, lambda name: shutil.which(name, path=env.get("PATH")))
    except PipelineError:
        if dry_run:
            return None, "godot"
        raise
    return SubprocessGodotRunner(binary), str(binary)


def _check_presets(project_dir: Path, platforms: Sequence[Platform]) -> dict[Platform, int]:
    """Return the ``[preset.N]`` index of each platform's preset; raise when one is missing."""
    path = project_dir / PRESETS_FILE
    remediation = (
        "Run /onboard-consumer --refresh to write game/export_presets.cfg with every ship preset."
    )
    if not path.is_file():
        raise ShipError(
            code="ship.presets_missing",
            message=f"{path} does not exist.",
            remediation=remediation,
            stage="preflight",
        )
    names: dict[str, int] = {}
    for (section, key), value in parse_config(path.read_text(encoding="utf-8")).items():
        match = re.fullmatch(r"preset\.(\d+)", section)
        if match and key == "name":
            names[value.strip('"')] = int(match.group(1))
    missing = [PRESETS[platform] for platform in platforms if PRESETS[platform] not in names]
    if missing:
        raise ShipError(
            code="ship.preset_missing",
            message=f"{path} has no preset named {', '.join(missing)}.",
            remediation=remediation,
            stage="preflight",
        )
    return {platform: names[PRESETS[platform]] for platform in platforms}


# Gates -------------------------------------------------------------------------------------------


def project_scripts(project_dir: Path) -> list[str]:
    """Every ``.gd`` under ``project_dir`` as a sorted POSIX relative path, skipping ``.godot/``."""
    found = []
    for path in project_dir.rglob("*.gd"):
        rel = path.relative_to(project_dir)
        if rel.parts[0] != ".godot" and path.is_file():
            found.append(rel.as_posix())
    return sorted(found)


def _check_scripts(ship: _Ship) -> None:
    for rel in project_scripts(ship.project_dir):
        result = _godot_run(ship, ["--check-only", "-s", f"res://{rel}"], ship.gate_lines)
        if result is not None and (result.returncode != 0 or _script_errors(result)):
            raise ShipError(
                code="ship.script_check_failed",
                message=f"{rel} does not parse: {_first_error(result)}",
                remediation=f"Fix the script error in {rel}, then rerun the ship.",
                stage="script_check",
            )


def _run_project_tests(ship: _Ship) -> None:
    if not (ship.project_dir / TESTS_SCRIPT).is_file():
        return
    result = _godot_run(ship, ["-s", f"res://{TESTS_SCRIPT}"], ship.gate_lines)
    if result is not None and result.returncode != 0:
        raise ShipError(
            code="ship.tests_failed",
            message=f"res://{TESTS_SCRIPT} failed (exit {result.returncode}).",
            remediation="Fix the failing project tests reported above, then rerun the ship.",
            stage="tests",
        )


def _script_errors(result: CommandResult) -> list[str]:
    lines = f"{result.stdout}\n{result.stderr}".splitlines()
    return [line.strip() for line in lines if line.strip().startswith("SCRIPT ERROR:")]


def _first_error(result: CommandResult) -> str:
    for line in f"{result.stdout}\n{result.stderr}".splitlines():
        if "ERROR" in line:
            return line.strip()
    return f"exit code {result.returncode}"


def _gate_mobile_budgets(audit: MobileBudgetAudit) -> None:
    if audit.passed:
        return
    codes = {finding.code for finding in audit.findings}
    code = next(candidate for candidate in GATE_CODE_ORDER if candidate in codes)
    raise ShipError(
        code=code,
        message="Mobile budget gate failed: "
        + " | ".join(finding.message for finding in audit.findings),
        remediation=" | ".join(dict.fromkeys(finding.remediation for finding in audit.findings)),
        stage="mobile_budget",
    )


# Platforms ---------------------------------------------------------------------------------------


def _ship_platform(platform: Platform, ship: _Ship, preset_index: int) -> ReleaseEntry | None:
    dest = ship.release_dir / platform
    if dest.is_dir() and not ship.dry_run:
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    out = export_path(ship.release_dir, platform, ship.app)
    lines: list[str] = list(ship.gate_lines)

    args = ["--export-release", PRESETS[platform], str(out)]
    child_env: dict[str, str] | None = None
    shown_env: list[str] = []
    if platform == "android":
        if not (ship.project_dir / "android" / "build").is_dir():
            args.append("--install-android-build-template")
        child_env, shown_env = android_env(ship.env)

    if platform == "ios":
        with _ios_preset(ship, preset_index, lines):
            _export(ship, platform, args, child_env, shown_env, lines)
    else:
        _export(ship, platform, args, child_env, shown_env, lines)

    if platform == "macos":
        lines += _run_script(ship, "sign-macos.sh", [str(out), "--identity", ship.identity], "sign")
        lines += _run_script(ship, "notarize-macos.sh", [str(out)], "notarize")

    if ship.dry_run:
        (dest / DRY_RUN_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return None

    if not out.exists():
        raise ShipError(
            code="ship.artifact_not_found",
            message=f"The {platform} export exited 0 but {out} does not exist.",
            remediation=(
                f"Read the Godot output above and check that the {PRESETS[platform]} export "
                "templates are installed (Editor > Manage Export Templates), then rerun."
            ),
            stage="export",
        )
    if platform == "web":
        warn_large_web_pack(dest)
    artifact = release_artifact(ship.release_dir, platform, ship.app)
    return ReleaseEntry(
        platform=platform,
        path=artifact.relative_to(ship.release_dir).as_posix(),
        sha256=artifact_sha256(artifact),
    )


def _export(
    ship: _Ship,
    platform: Platform,
    args: list[str],
    child_env: dict[str, str] | None,
    shown_env: list[str],
    lines: list[str],
) -> None:
    result = _godot_run(ship, args, lines, env=child_env, shown_env=shown_env)
    if result is not None and result.returncode != 0:
        raise ShipError(
            code="ship.export_failed",
            message=(
                f'godot --export-release "{PRESETS[platform]}" failed for {platform} '
                f"(exit {result.returncode}): {_first_error(result)}"
            ),
            remediation=(
                f"Read the Godot output above. Check that the {PRESETS[platform]} export "
                "templates are installed and the preset's signing settings are valid, then rerun."
            ),
            stage="export",
        )


def android_env(env: Mapping[str, str]) -> tuple[dict[str, str], list[str]]:
    """The keystore variables for the export child only, and their masked display."""
    child = {
        "GODOT_ANDROID_KEYSTORE_RELEASE_PATH": env.get("ANDROID_KEYSTORE", ""),
        "GODOT_ANDROID_KEYSTORE_RELEASE_USER": env.get("ANDROID_KEYSTORE_ALIAS")
        or DEFAULT_KEYSTORE_ALIAS,
        "GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD": env.get("ANDROID_KEYSTORE_PASSWORD", ""),
    }
    shown = [
        f"GODOT_ANDROID_KEYSTORE_RELEASE_PATH={child['GODOT_ANDROID_KEYSTORE_RELEASE_PATH']}",
        f"GODOT_ANDROID_KEYSTORE_RELEASE_USER={child['GODOT_ANDROID_KEYSTORE_RELEASE_USER']}",
        f"GODOT_ANDROID_KEYSTORE_RELEASE_PASSWORD={MASK}",
    ]
    return child, shown


@contextmanager
def _ios_preset(ship: _Ship, preset_index: int, lines: list[str]) -> Iterator[None]:
    """Set the iOS preset's team and profile UUID; restore the file byte-for-byte afterwards."""
    profile = ship.env.get("IOS_PROVISIONING_PROFILE", "")
    team = ship.env.get("IOS_TEAM_ID", "")
    security = ["security", "cms", "-D", "-i", profile]
    path = ship.project_dir / PRESETS_FILE
    if ship.dry_run:
        planned = [
            _show("DRY-RUN:", security),
            f"DRY-RUN: set {IOS_TEAM_KEY}={team} and {IOS_PROFILE_KEY}=<UUID of {profile}> "
            f"in {path} for the export, then restore it",
        ]
        for line in planned:
            print(line)
        lines += planned
        yield
        return
    uuid = _profile_uuid(ship, security)
    original = path.read_bytes()
    try:
        patched = patch_preset_options(
            original.decode("utf-8"), preset_index, {IOS_TEAM_KEY: team, IOS_PROFILE_KEY: uuid}
        )
        path.write_bytes(patched.encode("utf-8"))
        yield
    finally:
        path.write_bytes(original)


def _profile_uuid(ship: _Ship, command: list[str]) -> str:
    print(_show("RUN:", command))
    result = ship.run(command, env=dict(ship.env), capture_output=True, text=True, check=False)
    remediation = (
        "Set IOS_PROVISIONING_PROFILE to a readable .mobileprovision file for the app's bundle id, "
        "then rerun."
    )
    uuid: object = None
    if result.returncode == 0:
        try:
            data = plistlib.loads(result.stdout.encode("utf-8"))
        except (plistlib.InvalidFileException, ValueError):
            data = None
        if isinstance(data, dict):
            uuid = data.get("UUID")
    if not isinstance(uuid, str) or not uuid:
        raise ShipError(
            code="ship.ios_profile_invalid",
            message=f"No provisioning profile UUID could be read from {command[-1]}.",
            remediation=remediation,
            stage="export",
        )
    return uuid


def patch_preset_options(text: str, preset_index: int, values: Mapping[str, str]) -> str:
    """Set ``values`` as strings in ``[preset.<index>.options]``; replace or append each key."""
    lines = text.splitlines(keepends=True)
    header = f"[preset.{preset_index}.options]"
    start = next((i for i, line in enumerate(lines) if line.strip() == header), None)
    if start is None:
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines += ["\n", f"{header}\n", "\n"]
        start = len(lines) - 2
    end = next(
        (i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
        len(lines),
    )
    pending = dict(values)
    for i in range(start + 1, end):
        key = lines[i].split("=", 1)[0].strip()
        if key in pending:
            lines[i] = f'{key}="{pending.pop(key)}"\n'
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines[insert_at:insert_at] = [f'{key}="{value}"\n' for key, value in pending.items()]
    return "".join(lines)


def warn_large_web_pack(web_dir: Path) -> None:
    """Print ``ship.web_pack_large`` when ``index.pck`` is over 38 MiB."""
    pack = web_dir / "index.pck"
    if not pack.is_file():
        return
    size = pack.stat().st_size
    if size > WEB_PACK_LIMIT:
        print(
            f"WARNING [ship.web_pack_large]: index.pck is {size / (1024 * 1024):.1f} MB, "
            "over 38 MB",
            file=sys.stderr,
        )


# Commands ----------------------------------------------------------------------------------------


def _godot_run(
    ship: _Ship,
    args: Sequence[str],
    lines: list[str],
    *,
    env: Mapping[str, str] | None = None,
    shown_env: Sequence[str] = (),
) -> CommandResult | None:
    """Print and run one headless Godot command; a dry run only records it and returns None."""
    argv = [
        *shown_env,
        ship.godot_display,
        "--headless",
        "--audio-driver",
        "Dummy",
        "--path",
        str(ship.project_dir),
        *args,
    ]
    if ship.dry_run:
        line = _show("DRY-RUN:", argv)
        print(line)
        lines.append(line)
        return None
    print(_show("RUN:", argv))
    if ship.godot is None:  # pragma: no cover - _godot always returns a runner outside a dry run
        raise AssertionError("no Godot runner outside a dry run")
    result = ship.godot.run(args, project=ship.project_dir, env=env)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    return result


def _run_script(ship: _Ship, name: str, args: Sequence[str], step: str) -> list[str]:
    """Run one ship script, echo its output, and return its stdout lines. Raise on non-zero."""
    script = ship.scripts_dir / name
    if not script.is_file():
        raise ShipError(
            code="ship.script_missing",
            message=f"Ship script not found: {script}",
            remediation="Restore the scripts/ directory from the plugin checkout, then rerun.",
            stage=step,
        )
    argv = [str(script), *args, *(["--dry-run"] if ship.dry_run else [])]
    result = subprocess.run(argv, check=False, env=dict(ship.env), capture_output=True, text=True)
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise ShipError(
            code=f"ship.{step}_failed",
            message=f"{name} failed for macos (exit {result.returncode}).",
            remediation=_remediation(result.stderr),
            stage=step,
        )
    return result.stdout.splitlines()


def _remediation(stderr: str) -> str:
    lines = [line.strip() for line in stderr.splitlines() if line.strip()]
    for line in reversed(lines):
        if line.startswith("Remediation:"):
            return line.removeprefix("Remediation:").strip()
    if lines:
        return lines[-1]
    return "Read the script output above, fix the reported problem, and rerun the ship."


def _show(prefix: str, argv: Sequence[str]) -> str:
    return f"{prefix} {shlex.join(argv)}"
