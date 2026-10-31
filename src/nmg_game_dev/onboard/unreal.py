"""Unreal setup for a consumer project on UE 5.8 (#7 FR5, AC2, AC9).

Three pieces: the four plugins enabled in the ``.uproject``, MCP auto-start written to the
per-project editor ini, and VibeUE cloned from its UE 5.8 branch. Each merge keeps the
entries it does not own. VibeUE is drift-checked against the head of that branch on origin, and
``--refresh`` moves it to that head.
"""

from __future__ import annotations

import json
import re
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Final

from nmg_game_dev.onboard.commands import CommandResult, Runner
from nmg_game_dev.onboard.errors import OnboardError
from nmg_game_dev.onboard.paths import assert_not_excluded
from nmg_game_dev.onboard.report import REFRESH_REMEDIATION, StepResult

UPROJECT_PLUGINS: tuple[str, ...] = (
    "ModelContextProtocol",
    "EditorToolset",
    "VibeUE",
    "nmg-game-dev",
)
MCP_SECTION = "[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]"
DEFAULT_PORT = 8000
VIBEUE_URL = "https://github.com/kevinpbuckley/VibeUE.git"
VIBEUE_BRANCH: Final = "5-8"
VIBEUE_REL = "Plugins/VibeUE"
_SHA = re.compile(r"[0-9a-f]{40}")


def enable_plugins(
    name: str, uproject: Path, plugins: Sequence[str] = UPROJECT_PLUGINS
) -> StepResult:
    """Enable each plugin in the ``.uproject``'s ``Plugins`` list, keeping all other entries."""
    data: dict[str, Any] = json.loads(uproject.read_text(encoding="utf-8"))
    entries: list[Any] = data.setdefault("Plugins", [])
    changed = False
    for plugin in plugins:
        match = next((e for e in entries if isinstance(e, dict) and e.get("Name") == plugin), None)
        if match is None:
            entries.append({"Name": plugin, "Enabled": True})
            changed = True
        elif match.get("Enabled") is not True:
            match["Enabled"] = True
            changed = True
    if not changed:
        return StepResult(name, "unchanged", f"{uproject.name} enables {', '.join(plugins)}")
    uproject.write_text(json.dumps(data, indent="\t") + "\n", encoding="utf-8")
    return StepResult(name, "installed", f"enabled {', '.join(plugins)} in {uproject.name}")


def _find_section(lines: list[str]) -> tuple[int, int] | None:
    """Return (header index, end index) of MCP_SECTION, end being the next header or EOF."""
    for index, line in enumerate(lines):
        if line.strip() == MCP_SECTION:
            end = len(lines)
            for later in range(index + 1, len(lines)):
                if lines[later].lstrip().startswith("["):
                    end = later
                    break
            return index, end
    return None


def ensure_mcp_autostart(name: str, ini_path: Path) -> StepResult:
    """Set ``bAutoStartServer=True`` and, only when no port is set, ``ServerPortNumber=8000``."""
    existed = ini_path.exists()
    text = ini_path.read_text(encoding="utf-8") if existed else ""
    lines = text.splitlines()
    found = _find_section(lines)
    if found is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([MCP_SECTION, "bAutoStartServer=True", f"ServerPortNumber={DEFAULT_PORT}"])
    else:
        header, end = found
        body = lines[header + 1 : end]
        auto_index = next(
            (i for i, ln in enumerate(body) if ln.strip().startswith("bAutoStartServer=")), None
        )
        if auto_index is None:
            body.insert(0, "bAutoStartServer=True")
        else:
            body[auto_index] = "bAutoStartServer=True"
        if not any(ln.strip().startswith("ServerPortNumber=") for ln in body):
            body.append(f"ServerPortNumber={DEFAULT_PORT}")
        lines = lines[: header + 1] + body + lines[end:]
    updated = "\n".join(lines) + "\n"
    if existed and updated == text:
        return StepResult(name, "unchanged", f"{ini_path.name} has MCP auto-start")
    ini_path.parent.mkdir(parents=True, exist_ok=True)
    ini_path.write_text(updated, encoding="utf-8")
    return StepResult(name, "installed", f"MCP auto-start set in {ini_path.name}")


def _head(run: Runner, target: Path) -> str | None:
    if not (target / ".git").exists():
        return None
    result = run(["git", "-C", str(target), "rev-parse", "HEAD"], None)
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _remote_head(run: Runner) -> str | None:
    """The head SHA of VibeUE's branch on origin, or None when ls-remote fails or finds nothing."""
    result = run(["git", "ls-remote", VIBEUE_URL, f"refs/heads/{VIBEUE_BRANCH}"], None)
    if result.returncode != 0:
        return None
    fields = result.stdout.split()
    if not fields or not _SHA.fullmatch(fields[0]):
        return None
    return fields[0]


def _clone(run: Runner, target: Path) -> CommandResult:
    target.parent.mkdir(parents=True, exist_ok=True)
    result = run(
        ["git", "clone", "--depth", "1", "--branch", VIBEUE_BRANCH, VIBEUE_URL, str(target)],
        None,
    )
    if result.returncode != 0:
        raise OnboardError(
            "onboard.vibeue_clone_failed",
            f"git clone of VibeUE branch {VIBEUE_BRANCH} failed (exit {result.returncode}).",
            "Check network access to github.com and that git is installed, then re-run onboarding.",
        )
    return result


def ensure_vibeue(consumer: Path, *, run: Runner, refresh: bool) -> StepResult:
    """Clone VibeUE from its UE 5.8 branch, drift-check it against that branch's origin head, and
    with ``refresh`` move it to that head."""
    assert_not_excluded(Path(VIBEUE_REL))
    target = consumer / VIBEUE_REL
    if not target.exists():
        _clone(run, target)
        cloned = _head(run, target)
        short = cloned[:12] if cloned else "unknown"
        return StepResult(
            "vibeue", "installed", f"cloned {VIBEUE_BRANCH} ({short}) into {VIBEUE_REL}"
        )
    head = _head(run, target)
    if head is None:
        if not refresh:
            return StepResult(
                "vibeue",
                "drift",
                f"{VIBEUE_REL} is not a git checkout; left unchanged",
                REFRESH_REMEDIATION,
            )
        shutil.rmtree(target)
        _clone(run, target)
        return StepResult("vibeue", "refreshed", f"cloned {VIBEUE_BRANCH} again into {VIBEUE_REL}")
    remote = _remote_head(run)
    if remote is None:
        return StepResult(
            "vibeue",
            "unchanged",
            f"could not check the {VIBEUE_BRANCH} head (git ls-remote failed); "
            f"{VIBEUE_REL} left at {head[:12]}",
        )
    if head == remote:
        return StepResult("vibeue", "unchanged", f"{VIBEUE_REL} is at {head[:12]}")
    detail = f"{VIBEUE_REL} is at {head[:12]}, branch {VIBEUE_BRANCH} is at {remote[:12]}"
    if not refresh:
        return StepResult("vibeue", "drift", f"{detail}; left unchanged", REFRESH_REMEDIATION)
    fetch = run(["git", "-C", str(target), "fetch", "--depth", "1", "origin", VIBEUE_BRANCH], None)
    checkout = run(["git", "-C", str(target), "checkout", "--force", "FETCH_HEAD"], None)
    if fetch.returncode != 0 or checkout.returncode != 0:
        raise OnboardError(
            "onboard.vibeue_refresh_failed",
            f"Could not move VibeUE to branch {VIBEUE_BRANCH} in {VIBEUE_REL}.",
            f"Remove {VIBEUE_REL} and re-run onboarding to clone it again.",
        )
    return StepResult("vibeue", "refreshed", f"checked out {remote[:12]} in {VIBEUE_REL}")
