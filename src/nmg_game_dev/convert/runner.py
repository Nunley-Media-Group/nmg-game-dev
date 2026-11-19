"""Convert an Unreal consumer project to Godot (#249 FR11, AC11, AC12, AC13).

``run_convert`` composes the other stages through injected collaborators:

1. **Guards, before any write.** When no state file exists, ``convert.not_unreal`` when the root
   has no ``*.uproject`` and ``convert.dirty_worktree`` when ``git status --porcelain`` prints
   anything (or fails). A state file means the run is a resume, which skips both: a resume after a
   deletion that stopped part way has already lost its ``.uproject``.
2. **Preflight:** ``godot.not_found`` and ``finalize.blender_not_found``.
3. **Dry run:** print ``PLAN convert <item>`` (or ``PLAN fail <item> [<code>]`` for an item
   discovery already knows will fail) and ``PLAN delete <path>`` lines and return without
   writing.
4. **Onboard**, then each item not already done: re-finalize each asset from its Blender source
   into ``game/assets``, import each WAV, and re-scaffold the scaffolded backlog entries. A failure
   is recorded with its ``PipelineError`` code and remediation; the other items still run. The
   state file is written after each item succeeds.
5. **Hooks and settings:** remove every SessionStart hook whose command contains
   ``start-unreal-mcp.sh`` (dropping emptied groups) and every ``env`` key starting with ``UE_``
   from ``.claude/settings.json`` and ``.claude/settings.local.json``. A file that is not valid
   JSON is a ``convert.settings_invalid`` failure, recorded like any item.
6. **Deletions, only with zero failures:** ``git rm -r -q --ignore-unmatch -- <deletions>``, then
   remove any untracked remainder of those paths and the state file. A failure is recorded as
   ``deletions`` and the state file stays, so a rerun resumes and finishes them.
7. **Report:** write ``godot-conversion-report.md`` with the final outcome, deletions included.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final, TextIO

from nmg_game_dev.convert.plan import (
    AssetItem,
    AudioItem,
    ConversionPlan,
    Item,
    ScaffoldItem,
    convert_error,
    discover,
)
from nmg_game_dev.convert.report import Failure, render_report, write_report
from nmg_game_dev.convert.state import ConvertState, load_state, state_path
from nmg_game_dev.onboard.commands import Runner, default_run
from nmg_game_dev.pipeline.errors import PipelineError

UNREAL_HOOK: Final = "start-unreal-mcp.sh"
UNREAL_ENV_PREFIX: Final = "UE_"
SETTINGS_REL: Final = Path(".claude") / "settings.json"
SETTINGS_FILES: Final = (SETTINGS_REL, Path(".claude") / "settings.local.json")
EXPORT_ROOT: Final = Path("game") / "assets"
ITEM_FAILED: Final = "convert.item_failed"


@dataclass(frozen=True)
class ScaffoldOutcome:
    """One scaffold report line: ``code`` is ``None`` when the entry was written or unchanged."""

    entry_type: str
    name: str
    code: str | None = None
    message: str = ""


Onboard = Callable[[Path], object]
"""Onboard the consumer at the given root; raises ``PipelineError`` on failure."""
Finalize = Callable[[AssetItem, Path], object]
"""Finalize an asset into the given export root (``<root>/game/assets``)."""
ImportWav = Callable[[Path, AudioItem], object]
"""Import a stored WAV into the Godot project of the given consumer root."""
Scaffold = Callable[[Path], Sequence[ScaffoldOutcome]]
"""Scaffold the ``scaffolded`` backlog entries of the given consumer root."""
Preflight = Callable[[], object]
"""Resolve Godot and Blender; raises ``PipelineError`` when either is missing."""


@dataclass
class ConvertResult:
    """The outcome of one ``run_convert`` call."""

    plan: ConversionPlan
    converted: list[str] = field(default_factory=list)
    failures: list[Failure] = field(default_factory=list)
    deleted: bool = False
    dry_run: bool = False
    report: Path | None = None

    @property
    def exit_code(self) -> int:
        return 1 if self.failures else 0

    def as_json(self) -> dict[str, Any]:
        return {
            "dry_run": self.dry_run,
            "converted": self.converted,
            "failed": [
                {"item": f.item, "code": f.code, "message": f.message, "remediation": f.remediation}
                for f in self.failures
            ],
            "manual_port": [
                {"path": row.path, "reason": row.reason} for row in self.plan.manual_port
            ],
            "deletions": self.plan.deletions,
            "deleted": self.deleted,
            "report": None if self.report is None else str(self.report),
        }


# --- Default collaborators (imported lazily so this module loads without them) -------------------


def default_onboard(root: Path, models_dir: Path | None = None) -> object:
    """Onboard ``root``; ``models_dir`` is ``--models-dir`` (else ``TEXTURE_GEN_MODELS_DIR``)."""
    from nmg_game_dev.onboard.paths import framework_root
    from nmg_game_dev.onboard.runner import run_onboard

    return run_onboard(root, framework=framework_root(os.environ), models_dir=models_dir)


def default_finalize(item: AssetItem, export_root: Path) -> object:
    from nmg_game_dev.pipeline import finalize
    from nmg_game_dev.pipeline.request import FinalizeRequest

    request = FinalizeRequest.model_validate(
        {
            "blend": item.source,
            "collection": item.name,
            "category": item.category,
            "asset_class": item.asset_class,
            "export_root": export_root,
        }
    )
    return finalize(request)


def default_import_wav(root: Path, item: AudioItem) -> object:
    """Import ``item``, or re-check the import an interrupted earlier run already installed."""
    from nmg_game_dev.audio.godot_import import import_ogg, import_wav, installed_result
    from nmg_game_dev.godot.binary import resolve_godot
    from nmg_game_dev.godot.runner import SubprocessGodotRunner

    runner = SubprocessGodotRunner(resolve_godot())
    kind = "music" if item.kind == "Music" else "sfx"
    installed = installed_result(root, kind, item.name, item.loop, runner)
    if installed is not None:
        return installed
    if kind == "music":
        return import_ogg(root, item.wav, item.name, item.loop, runner)
    return import_wav(root, item.wav, item.name, item.loop, runner)


def default_scaffold(root: Path) -> list[ScaffoldOutcome]:
    from nmg_game_dev.design.scaffold import ScaffoldReport, run_scaffold

    report = ScaffoldReport()
    run_scaffold(root, report, statuses={"scaffolded"})
    return [
        ScaffoldOutcome(
            line.entry_type,
            line.asset_name,
            line.code if line.status == "error" else None,
            line.detail,
        )
        for line in report.lines
    ]


def default_preflight() -> object:
    from nmg_game_dev.godot.binary import resolve_godot
    from nmg_game_dev.pipeline.blender_proc import resolve_blender

    return (resolve_godot(), resolve_blender())


# --- Guards -------------------------------------------------------------------------------------


def _guard(root: Path, git: Runner, resume: bool) -> None:
    if resume:
        return
    if not any(path.is_file() for path in root.glob("*.uproject")):
        raise convert_error(
            "convert.not_unreal",
            f"{root} has no .uproject, so there is no Unreal project to convert.",
            "Run /convert-to-godot from the root of the Unreal consumer project (the folder "
            "holding its .uproject), or pass --project.",
        )
    status = git(["git", "-C", str(root), "status", "--porcelain"], None)
    if status.returncode != 0:
        raise convert_error(
            "convert.dirty_worktree",
            f"git status failed in {root}: {status.stderr.strip()}",
            "Run /convert-to-godot in a git repository with a clean working tree, so every "
            "change it makes can be reviewed and reverted.",
        )
    if status.stdout.strip():
        changed = len(status.stdout.strip().splitlines())
        raise convert_error(
            "convert.dirty_worktree",
            f"The git working tree in {root} has {changed} uncommitted change(s).",
            "Commit or stash your changes, then rerun /convert-to-godot.",
        )


# --- Conversion ---------------------------------------------------------------------------------


def _failure(item: str, error: BaseException) -> Failure:
    if isinstance(error, PipelineError):
        return Failure(item, error.code, error.message, error.remediation)
    return Failure(
        item,
        ITEM_FAILED,
        f"{type(error).__name__}: {error}",
        "Fix the cause shown in the message, then rerun /convert-to-godot to retry this item.",
    )


SCAFFOLD_REMEDIATION: Final = {
    "design.unknown_reference": "Fix the region's terrain field in its design doc, run "
    "/design sync, then rerun /convert-to-godot.",
}
SCAFFOLD_DEFAULT_REMEDIATION: Final = (
    "Check that game/ is writable and the backlog entry is valid, then rerun /convert-to-godot."
)


def _run_scaffolds(
    root: Path,
    pending: list[ScaffoldItem],
    scaffold: Scaffold,
    state: ConvertState,
    result: ConvertResult,
    out: TextIO,
) -> None:
    try:
        outcomes = list(scaffold(root))
    except Exception as error:  # noqa: BLE001 - one failed stage must not stop the report
        for item in pending:
            _record(result, _failure(item.key, error), out)
        return
    by_key = {f"scaffold:{o.entry_type}/{o.name}": o for o in outcomes}
    for item in pending:
        outcome = by_key.get(item.key)
        if outcome is None:
            failure = Failure(
                item.key,
                "convert.scaffold_not_run",
                f"The scaffold run produced no line for {item.key}.",
                "Run /design sync to refresh the backlog, then rerun /convert-to-godot.",
            )
            _record(result, failure, out)
        elif outcome.code is not None:
            remediation = SCAFFOLD_REMEDIATION.get(outcome.code, SCAFFOLD_DEFAULT_REMEDIATION)
            _record(result, Failure(item.key, outcome.code, outcome.message, remediation), out)
        else:
            _done(state, result, item.key, out)


def _record(result: ConvertResult, failure: Failure, out: TextIO) -> None:
    result.failures.append(failure)
    print(f"failed {failure.item} [{failure.code}]: {failure.message}", file=out)


def _done(state: ConvertState, result: ConvertResult, key: str, out: TextIO) -> None:
    state.add(key)
    result.converted.append(key)
    print(f"converted {key}", file=out)


def _convert_item(root: Path, item: Item, finalize: Finalize, import_wav: ImportWav) -> None:
    if isinstance(item, AssetItem):
        if item.problem is not None:
            raise item.problem
        finalize(item, root / EXPORT_ROOT)
    elif isinstance(item, AudioItem):
        import_wav(root, item)


# --- Hooks and settings -------------------------------------------------------------------------


def replace_settings(path: Path) -> bool:
    """Drop the Unreal SessionStart hooks and ``UE_*`` env keys; return whether the file changed.

    Raises ``convert.settings_invalid`` when the file cannot be read or is not valid JSON.
    """
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise convert_error(
            "convert.settings_invalid",
            f"{path} cannot be read as JSON: {error}",
            f"Fix the JSON in {path.name} (or restore it from git), then rerun /convert-to-godot "
            "to remove its Unreal hooks and UE_* env keys.",
        ) from error
    if not isinstance(data, dict):
        return False
    changed = False
    hooks = data.get("hooks")
    session = hooks.get("SessionStart") if isinstance(hooks, dict) else None
    if isinstance(hooks, dict) and isinstance(session, list):
        kept_groups: list[Any] = []
        for group in session:
            entries = group.get("hooks") if isinstance(group, dict) else None
            if not isinstance(entries, list):
                kept_groups.append(group)
                continue
            kept = [
                hook
                for hook in entries
                if not (isinstance(hook, dict) and UNREAL_HOOK in str(hook.get("command", "")))
            ]
            if len(kept) != len(entries):
                changed = True
            if kept:
                kept_groups.append({**group, "hooks": kept})
        hooks["SessionStart"] = kept_groups
    env = data.get("env")
    if isinstance(env, dict):
        for key in [key for key in env if str(key).startswith(UNREAL_ENV_PREFIX)]:
            del env[key]
            changed = True
    if changed:
        path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return changed


# --- Deletions ----------------------------------------------------------------------------------


def _delete(root: Path, deletions: Sequence[str], git: Runner) -> None:
    if deletions:
        paths = [path.rstrip("/") for path in deletions]
        removed = git(
            ["git", "-C", str(root), "rm", "-r", "-q", "--ignore-unmatch", "--", *paths], None
        )
        if removed.returncode != 0:
            raise convert_error(
                "convert.delete_failed",
                f"git rm failed in {root}: {removed.stderr.strip()}",
                "Resolve the git error, then rerun /convert-to-godot to finish the deletions.",
            )
        for rel in paths:
            target = root / rel
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
    state_path(root).unlink(missing_ok=True)


# --- Entry point --------------------------------------------------------------------------------


def run_convert(
    root: Path,
    *,
    dry_run: bool = False,
    git: Runner = default_run,
    onboard: Onboard = default_onboard,
    finalize: Finalize = default_finalize,
    import_wav: ImportWav = default_import_wav,
    scaffold: Scaffold = default_scaffold,
    preflight: Preflight = default_preflight,
    out: TextIO | None = None,
) -> ConvertResult:
    """Convert the Unreal consumer at ``root`` to Godot and return what happened.

    Guard and preflight failures raise ``PipelineError`` before anything is written. Item failures
    are collected in the result; ``result.exit_code`` is 1 when any item failed.
    """
    stream = sys.stdout if out is None else out
    root = root.expanduser().resolve()
    state = load_state(root)
    _guard(root, git, resume=state is not None)
    preflight()
    plan = discover(root)
    done = set() if state is None else set(state.done)
    pending = [item for item in plan.items if item.key not in done]
    result = ConvertResult(plan=plan, dry_run=dry_run)

    if dry_run:
        for item in pending:
            problem = item.problem if isinstance(item, AssetItem) else None
            if problem is not None:
                print(f"PLAN fail {item.key} [{problem.code}]: {problem.message}", file=stream)
            else:
                print(f"PLAN convert {item.key}", file=stream)
        for path in plan.deletions:
            print(f"PLAN delete {path}", file=stream)
        return result

    if state is None:
        state = ConvertState(state_path(root))
        state.save()
    result.converted.extend(key for key in state.done)

    try:
        onboard(root)
    except Exception as error:  # noqa: BLE001 - reported as a failed item
        _record(result, _failure("onboard", error), stream)
    else:
        for item in pending:
            if isinstance(item, ScaffoldItem):
                continue
            try:
                _convert_item(root, item, finalize, import_wav)
            except Exception as error:  # noqa: BLE001 - one item must not stop the others
                _record(result, _failure(item.key, error), stream)
            else:
                _done(state, result, item.key, stream)
        scaffolds = [item for item in pending if isinstance(item, ScaffoldItem)]
        if scaffolds:
            _run_scaffolds(root, scaffolds, scaffold, state, result, stream)

    for rel in SETTINGS_FILES:
        try:
            changed = replace_settings(root / rel)
        except PipelineError as error:
            _record(result, _failure(f"settings:{rel.as_posix()}", error), stream)
            continue
        if changed:
            print(f"updated {rel.as_posix()}: removed the Unreal hooks and UE_* env", file=stream)

    deletion_error: str | None = None
    if not result.failures:
        try:
            _delete(root, plan.deletions, git)
        except (PipelineError, OSError) as error:
            failure = _failure("deletions", error)
            deletion_error = failure.message
            _record(result, failure, stream)
        else:
            result.deleted = True
            for path in plan.deletions:
                print(f"deleted {path}", file=stream)
    result.report = write_report(
        root,
        render_report(
            result.converted,
            result.failures,
            plan.manual_port,
            plan.deletions,
            deleted=result.deleted,
            deletion_error=deletion_error,
        ),
    )
    print(f"report {result.report.name}", file=stream)
    return result
