"""Copy framework-owned files and trees into a consumer, with drift detection (#7 FR9, AC1, AC9).

``sync_file`` and ``sync_tree`` compare bytes against the framework copy. A missing item is
installed. An identical item is unchanged. A differing item is drift, and its content stays as it
is. With ``refresh`` the framework copy is restored and the item is reported as refreshed. Copies
keep the executable bit (``shutil.copy2``).
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

from nmg_game_dev.onboard.errors import OnboardError
from nmg_game_dev.onboard.paths import assert_not_excluded
from nmg_game_dev.onboard.report import REFRESH_REMEDIATION, StepResult

TREE_IGNORE: tuple[str, ...] = ("Binaries", "Intermediate")


def _same_bytes(a: Path, b: Path) -> bool:
    return a.read_bytes() == b.read_bytes()


def sync_file(src: Path, consumer: Path, rel: str, *, name: str, refresh: bool) -> StepResult:
    """Install, verify, or (with ``refresh``) restore one framework-owned file."""
    rel_path = Path(rel)
    assert_not_excluded(rel_path)
    if not src.is_file():
        raise OnboardError(
            "onboard.framework_incomplete",
            f"Framework file missing: {src}",
            "Check the plugin install (CLAUDE_PLUGIN_ROOT) or reinstall nmg-game-dev.",
        )
    dst = consumer / rel_path
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        return StepResult(name, "installed", f"copied to {rel}")
    if _same_bytes(src, dst):
        return StepResult(name, "unchanged", rel)
    if refresh:
        shutil.copy2(src, dst)
        return StepResult(name, "refreshed", f"restored {rel} from the framework")
    return StepResult(
        name,
        "drift",
        f"{rel} differs from the framework copy; content left unchanged",
        REFRESH_REMEDIATION,
    )


def _tree_files(src: Path, ignore: Iterable[str]) -> list[Path]:
    skip = set(ignore)
    out: list[Path] = []
    for path in sorted(src.rglob("*")):
        if not path.is_file():
            continue
        if any(part in skip for part in path.relative_to(src).parts):
            continue
        out.append(path)
    return out


def sync_tree(
    src: Path,
    consumer: Path,
    rel: str,
    *,
    name: str,
    refresh: bool,
    ignore: Iterable[str] = TREE_IGNORE,
) -> StepResult:
    """Install, verify, or (with ``refresh``) restore a framework-owned tree.

    Files the consumer adds in the tree (for example UE build output) are not compared.
    """
    rel_path = Path(rel)
    assert_not_excluded(rel_path)
    dst_root = consumer / rel_path
    files = _tree_files(src, ignore)
    if not files:
        raise OnboardError(
            "onboard.framework_incomplete",
            f"Framework tree is empty: {src}",
            "Check the plugin install (CLAUDE_PLUGIN_ROOT) or reinstall nmg-game-dev.",
        )
    fresh = not dst_root.exists()
    changed: list[Path] = []
    for path in files:
        target = dst_root / path.relative_to(src)
        if not target.is_file() or not _same_bytes(path, target):
            changed.append(path)
    if fresh:
        for path in files:
            target = dst_root / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        return StepResult(name, "installed", f"copied {len(files)} files to {rel}")
    if not changed:
        return StepResult(name, "unchanged", rel)
    if refresh:
        for path in changed:
            target = dst_root / path.relative_to(src)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        return StepResult(name, "refreshed", f"restored {len(changed)} file(s) under {rel}")
    return StepResult(
        name,
        "drift",
        f"{len(changed)} file(s) under {rel} differ from the framework copy; "
        "content left unchanged",
        REFRESH_REMEDIATION,
    )
