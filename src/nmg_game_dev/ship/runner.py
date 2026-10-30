"""The ship runner: preflight, the mobile budget gate, then each platform's build and publish.

``run_ship`` follows the design architecture. A failing gate or script raises ``ShipError`` and
stops the run. A platform that already finished keeps its artifact. Each script is one tool,
run with ``subprocess.run`` under an explicit environment. The runner never calls a tool
directly, so a test can shim every tool with a script on ``PATH``.

A dry run sends ``--dry-run`` to every script, skips the cook-manifest gate and the artifact copy,
and writes ``release/<platform>/DRY-RUN.txt``.

See: specs/6-ship-skills-per-platform-build-sign-notarize-package/design.md (§ Architecture)
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from nmg_game_dev.quality.mobile_budgets import (
    GATE_CODE_ORDER,
    MobileBudgetAudit,
    check_mobile_budgets,
)
from nmg_game_dev.ship.artifacts import (
    ReleaseEntry,
    artifact_sha256,
    locate_artifact,
    publish_artifact,
)
from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.identity import resolve_signing_identity
from nmg_game_dev.ship.release_notes import write_release_notes
from nmg_game_dev.ship.targets import (
    MOBILE_PLATFORMS,
    Platform,
    expand_target,
    preflight_env,
)

SCRIPTS_DIR: Final[Path] = Path(__file__).resolve().parents[3] / "scripts"
DRY_RUN_FILE: Final = "DRY-RUN.txt"


@dataclass(frozen=True)
class _Ship:
    project: Path
    release_dir: Path
    dry_run: bool
    env: Mapping[str, str]
    scripts_dir: Path
    identity: str


def run_ship(
    target: str,
    project: Path,
    release_dir: Path,
    dry_run: bool,
    env: Mapping[str, str],
    scripts_dir: Path = SCRIPTS_DIR,
) -> list[ReleaseEntry]:
    """Ship ``target`` from ``project`` into ``release_dir`` and return the published artifacts."""
    platforms = expand_target(target)
    if not project.is_file():
        raise ShipError(
            code="ship.project_missing",
            message=f"UE project not found: {project}",
            remediation="Pass --project with the path to the consumer's .uproject file.",
            stage="preflight",
        )
    preflight_env(platforms, env)
    identity = resolve_signing_identity(env, dry_run=dry_run) if "macos" in platforms else ""
    if any(platform in MOBILE_PLATFORMS for platform in platforms):
        _gate_mobile_budgets(check_mobile_budgets(project.parent))

    ship = _Ship(
        project=project,
        release_dir=release_dir,
        dry_run=dry_run,
        env=env,
        scripts_dir=scripts_dir,
        identity=identity,
    )
    entries: list[ReleaseEntry] = []
    for platform in platforms:
        entry = _ship_platform(platform, ship)
        if entry is not None:
            entries.append(entry)
    write_release_notes(release_dir, target, entries, dry_run, platforms)
    return entries


def _ship_platform(platform: Platform, ship: _Ship) -> ReleaseEntry | None:
    project_root = ship.project.parent
    archive = project_root / "Saved" / "NmgShip" / platform
    listing = archive / "cooked-listing.txt"
    dry_args = ["--dry-run"] if ship.dry_run else []
    if not ship.dry_run:
        _clear_dir(ship.release_dir / platform)

    if platform == "windows":
        build_script = "build-windows.sh"
        build_args = ["--archive", str(archive), "--listing", str(listing), *dry_args]
    else:
        build_script = f"build-{platform}.sh"
        build_args = [
            "--project",
            str(ship.project),
            "--archive",
            str(archive),
            *dry_args,
        ]
    lines = _run_script(ship, build_script, build_args, "build", platform)

    if ship.dry_run:
        if platform == "macos":
            planned = archive / "Mac" / f"{ship.project.stem}.app"
            lines += _run_script(
                ship,
                "sign-macos.sh",
                [str(planned), "--identity", ship.identity, "--dry-run"],
                "sign",
                platform,
            )
            lines += _run_script(
                ship, "notarize-macos.sh", [str(planned), "--dry-run"], "notarize", platform
            )
        lines.append("DRY-RUN: cook-manifest gate and artifact copy skipped")
        dest = ship.release_dir / platform
        dest.mkdir(parents=True, exist_ok=True)
        (dest / DRY_RUN_FILE).write_text("\n".join(lines) + "\n", encoding="utf-8")
        return None

    for variant, cooked in _cook_targets(platform, project_root, listing):
        _run_script(
            ship,
            "verify-cook-manifest.sh",
            ["--variant", variant, str(cooked)],
            "cook_manifest",
            platform,
        )
    artifact = locate_artifact(archive, platform)
    if platform == "macos":
        _run_script(
            ship,
            "sign-macos.sh",
            [str(artifact), "--identity", ship.identity],
            "sign",
            platform,
        )
        _run_script(ship, "notarize-macos.sh", [str(artifact)], "notarize", platform)
    published = publish_artifact(artifact, ship.release_dir, platform)
    return ReleaseEntry(
        platform=platform,
        path=published.relative_to(ship.release_dir).as_posix(),
        sha256=artifact_sha256(published),
    )


def _cook_targets(platform: Platform, project_root: Path, listing: Path) -> list[tuple[str, Path]]:
    cooked = project_root / "Saved" / "Cooked"
    if platform == "macos":
        return [("desktop", cooked / "Mac")]
    if platform == "ios":
        return [("mobile", cooked / "IOS")]
    if platform == "android":
        dirs = sorted(cooked.glob("Android*")) or [cooked / "Android"]
        return [("mobile", path) for path in dirs]
    return [("desktop", listing)]


def _run_script(ship: _Ship, name: str, args: Sequence[str], step: str, platform: str) -> list[str]:
    """Run one script, echo its output, and return its stdout lines. Raise on a non-zero exit."""
    script = ship.scripts_dir / name
    if not script.is_file():
        raise ShipError(
            code="ship.script_missing",
            message=f"Ship script not found: {script}",
            remediation="Restore the scripts/ directory from the plugin checkout, then rerun.",
            stage=step,
        )
    result = subprocess.run(
        [str(script), *args],
        check=False,
        env=dict(ship.env),
        capture_output=True,
        text=True,
    )
    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)
    if result.returncode != 0:
        raise ShipError(
            code=f"ship.{step}_failed",
            message=f"{name} failed for {platform} (exit {result.returncode}).",
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


def _clear_dir(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path)
