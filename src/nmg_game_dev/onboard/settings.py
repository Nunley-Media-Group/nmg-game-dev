"""Merge framework settings into a consumer's Claude settings files (#7 FR3, FR7, AC1, AC4, AC8).

Both merges keep every key they do not own and write only when something changed, so a re-run with
nothing new is reported as unchanged and leaves the file untouched.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from nmg_game_dev.onboard.report import StepResult


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _write(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def merge_session_hooks(name: str, settings_path: Path, template_path: Path) -> StepResult:
    """Add each template SessionStart hook whose ``command`` the settings do not already run.

    A hook the settings already run gets the template's ``timeout`` when its own is absent or lower
    (#103 AC5); that is reported as ``refreshed``. Groups from the template are appended, not
    rewritten. Existing hooks, groups, and other keys keep their order and values, except the
    ``timeout`` of a hook the template raises.
    """
    template = _load(template_path)
    wanted_groups: list[dict[str, Any]] = list(template.get("hooks", {}).get("SessionStart", []))
    settings = _load(settings_path)
    hooks = settings.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError(f"{settings_path}: 'hooks' must be an object")
    session: list[Any] = hooks.setdefault("SessionStart", [])
    existing: dict[Any, dict[str, Any]] = {
        hook.get("command"): hook
        for group in session
        if isinstance(group, dict)
        for hook in group.get("hooks", [])
        if isinstance(hook, dict)
    }
    added = 0
    for group in wanted_groups:
        missing = [
            hook
            for hook in group.get("hooks", [])
            if isinstance(hook, dict) and hook.get("command") not in existing
        ]
        if not missing:
            continue
        session.append({**{k: v for k, v in group.items() if k != "hooks"}, "hooks": missing})
        existing.update((hook.get("command"), hook) for hook in missing)
        added += len(missing)
    raised = 0
    for group in wanted_groups:
        for hook in group.get("hooks", []):
            if not isinstance(hook, dict) or "timeout" not in hook:
                continue
            current = existing[hook.get("command")].get("timeout")
            if not isinstance(current, (int, float)) or current < hook["timeout"]:
                existing[hook.get("command")]["timeout"] = hook["timeout"]
                raised += 1
    if added == 0 and raised == 0:
        return StepResult(
            name, "unchanged", f"{settings_path.name} already runs the SessionStart hooks"
        )
    _write(settings_path, settings)
    changes: list[str] = []
    if added:
        changes.append(f"merged {added} SessionStart hook(s) into {settings_path.name}")
    if raised:
        changes.append(
            f"raised the timeout of {raised} SessionStart hook(s) in {settings_path.name}"
        )
    return StepResult(name, "refreshed" if raised else "installed", "; ".join(changes))


def merge_env(name: str, settings_local_path: Path, values: Mapping[str, str]) -> StepResult:
    """Set ``env`` entries in ``settings.local.json``; other keys and env entries are kept."""
    settings = _load(settings_local_path)
    env = settings.setdefault("env", {})
    if not isinstance(env, dict):
        raise ValueError(f"{settings_local_path}: 'env' must be an object")
    changed = [key for key, value in values.items() if env.get(key) != value]
    if not changed:
        return StepResult(name, "unchanged", f"{settings_local_path.name} env already set")
    for key in changed:
        env[key] = values[key]
    _write(settings_local_path, settings)
    return StepResult(name, "installed", f"set {', '.join(changed)} in {settings_local_path.name}")
