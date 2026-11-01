"""The Git LFS onboarding steps: the managed ``.gitattributes`` block and the LFS hooks (#122).

``ensure_gitattributes_lfs`` owns one marker-delimited block in the consumer's ``.gitattributes``.
It adds the block when it is missing, reports drift when the block differs, and replaces only the
block with ``refresh``. Every byte outside the block is kept, including CRLF line endings. The block
runs from the last begin marker to the first end marker after it, so a stray marker that a consumer
left behind is never swept into a refresh. ``ensure_lfs_hooks`` runs ``git lfs install --local`` in
a consumer git work tree that has no LFS ``pre-push`` hook. All git commands go through the injected
``Runner``.
"""

from __future__ import annotations

from pathlib import Path

from nmg_game_dev.onboard.commands import Runner
from nmg_game_dev.onboard.errors import OnboardError
from nmg_game_dev.onboard.report import REFRESH_REMEDIATION, StepResult

LFS_PATTERNS: tuple[str, ...] = (
    "*.blend",
    "*.glb",
    "*.fbx",
    "*.obj",
    "*.abc",
    "*.usd",
    "*.usdz",
    "*.uasset",
    "*.umap",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.tga",
    "*.tif",
    "*.tiff",
    "*.exr",
    "*.hdr",
    "*.psd",
    "*.wav",
    "*.mp3",
    "*.ogg",
    "*.mp4",
)
BEGIN = "# nmg-game-dev:begin"
END = "# nmg-game-dev:end"
HOOK_NAME = "pre-push"
HOOK_MARKER = "git lfs"
NOT_A_REPO = "not a git repository"
HOOKS_FAILED_REMEDIATION = (
    "Check the repository's existing git hooks (git lfs install --local refuses to overwrite a "
    "custom pre-push), then re-run onboarding."
)
HOOKS_LOOKUP_REMEDIATION = (
    "Check that the consumer is a healthy git repository, then re-run onboarding."
)


def block_text() -> str:
    """The framework block: both markers and one LFS rule per pattern, joined by newlines."""
    rules = [f"{pattern} filter=lfs diff=lfs merge=lfs -text" for pattern in LFS_PATTERNS]
    return "\n".join([BEGIN, *rules, END])


def _read_exact(path: Path) -> str:
    # newline="" keeps CRLF as written, so the bytes outside the block come back unchanged.
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def _write_exact(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def ensure_gitattributes_lfs(name: str, path: Path, *, refresh: bool) -> StepResult:
    """Create, append, verify, or (with ``refresh``) replace the LFS block in ``path``."""
    block = block_text()
    if not path.exists():
        _write_exact(path, block + "\n")
        return StepResult(
            name, "installed", "created .gitattributes with the nmg-game-dev LFS block"
        )
    text = _read_exact(path)
    start = text.rfind(BEGIN)
    end = text.find(END, start) if start >= 0 else -1
    if start >= 0 and end >= 0:
        end += len(END)
        if text[start:end] == block:
            return StepResult(name, "unchanged", ".gitattributes LFS block is current")
        if not refresh:
            return StepResult(
                name,
                "drift",
                ".gitattributes LFS block differs from the framework block; content left unchanged",
                REFRESH_REMEDIATION,
            )
        _write_exact(path, text[:start] + block + text[end:])
        return StepResult(
            name, "refreshed", "replaced the nmg-game-dev LFS block in .gitattributes"
        )
    separator = "\n" if text and not text.endswith("\n") else ""
    spacer = "\n" if text.strip() else ""
    _write_exact(path, text + separator + spacer + block + "\n")
    return StepResult(name, "installed", "added the nmg-game-dev LFS block to .gitattributes")


def _display(hooks: Path, target: Path) -> str:
    try:
        return str(hooks.relative_to(target))
    except ValueError:
        return str(hooks)


def ensure_lfs_hooks(name: str, target: Path, *, run: Runner) -> StepResult:
    """Install the LFS hooks in the git work tree at ``target``, or report why it cannot.

    Returns ``skipped`` outside a git work tree, ``unchanged`` when a ``pre-push`` hook that
    mentions ``git lfs`` already exists, and ``installed`` after ``git lfs install --local`` runs.
    """
    inside = run(["git", "-C", str(target), "rev-parse", "--is-inside-work-tree"], None)
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return StepResult(name, "skipped", NOT_A_REPO)
    lookup = run(["git", "-C", str(target), "rev-parse", "--git-path", "hooks"], None)
    if lookup.returncode != 0 or not lookup.stdout.strip():
        raise OnboardError(
            "onboard.git_lfs_hooks_failed",
            f"git rev-parse --git-path hooks failed in {target}: {lookup.stderr.strip()}",
            HOOKS_LOOKUP_REMEDIATION,
        )
    hooks = Path(lookup.stdout.strip())
    if not hooks.is_absolute():
        hooks = target / hooks
    pre_push = hooks / HOOK_NAME
    if pre_push.is_file():
        text = pre_push.read_text(encoding="utf-8", errors="replace")
        if HOOK_MARKER in text:
            return StepResult(name, "unchanged", f"LFS hooks present in {_display(hooks, target)}")
    installed = run(["git", "-C", str(target), "lfs", "install", "--local"], None)
    if installed.returncode != 0:
        raise OnboardError(
            "onboard.git_lfs_hooks_failed",
            f"git lfs install --local failed in {target}: {installed.stderr.strip()}",
            HOOKS_FAILED_REMEDIATION,
        )
    return StepResult(name, "installed", "ran git lfs install --local")
