"""Block API keys from commits and builds in consumer projects (#255).

This module is stdlib-only. ``/onboard-consumer`` copies it byte-for-byte into the consumer as
``scripts/nmg_secret_scan.py``, and the pre-commit hook runs that copy with no plugin, uv, or
package on the path. ``/ship`` and ``python -m nmg_game_dev.secrets`` import the same functions.

Every match is reported masked: the first four characters of the value, then ``…``, and the
value's SHA-256 fingerprint. The raw value never reaches an output, a log, or a ``repr``.

Exit codes for ``main``: 0 when nothing is blocked (silent), 1 when a match is blocked (one masked
line per match on stderr), 2 when a git command the scan needs fails.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import subprocess
import sys
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

Runner = Callable[..., "subprocess.CompletedProcess[bytes]"]
"""A ``subprocess.run``-shaped callable; tests inject their own."""

PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("openai", re.compile(r"\bsk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{20,}")),
    ("elevenlabs", re.compile(r"\bsk_[0-9a-f]{48}\b")),
    ("meshy", re.compile(r"\bmsy_[A-Za-z0-9_-]{16,}")),
    ("github", re.compile(r"\b(?:ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{22,})")),
    ("aws", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private-key", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
)
ENV_FILE_NAME: Final = ".env"
ENV_FILE_PATTERN: Final = "env-file"
"""A staged or tracked path named exactly ``.env`` is a match on line 0, valued by its path."""
ALLOW_FILE: Final = Path(".nmg") / "secret-scan-allow"
BINARY_PROBE_BYTES: Final = 8000
LFS_POINTER_PREFIX: Final = b"version https://git-lfs.github.com/spec/v1"
WALK_SKIP_TOP: Final = (".git", "release")
WALK_SKIP_GODOT_CACHE: Final = ("game", ".godot")
WALK_SKIP_DIRS: Final = (".venv", "node_modules")
"""Skipped at any depth by the walk: local environments that are never committed."""
WALK_SKIP_FILES: Final = (".claude/settings.local.json",)
"""Root-relative local-only secret stores the walk skips, along with every ``.env`` and
``.env.*`` file: outside git, the scan cannot tell them from committed files, and they are where
keys are meant to live."""
GITLINK_MODE: Final = "160000"
REMEDIATION: Final = (
    "Remove the key (keep keys in .env), or allow a false positive in .nmg/secret-scan-allow"
)


class GitError(RuntimeError):
    """A git command the scan needs could not run or exited non-zero."""


@dataclass(frozen=True)
class Match:
    """One blocked value. ``value`` is kept for fingerprinting and is never rendered."""

    path: str
    line: int
    pattern: str
    value: str = field(repr=False)

    @property
    def fingerprint(self) -> str:
        return fingerprint(self.value)

    def render(self) -> str:
        return f"{self.path}:{self.line}: {self.pattern} {mask(self.value)} ({self.fingerprint})"


@dataclass(frozen=True)
class Allow:
    """Entries from ``.nmg/secret-scan-allow``: fingerprints and ``<path>:<pattern>`` pairs."""

    fingerprints: frozenset[str] = frozenset()
    pairs: frozenset[str] = frozenset()

    def permits(self, match: Match) -> bool:
        return (
            match.fingerprint in self.fingerprints or f"{match.path}:{match.pattern}" in self.pairs
        )


def mask(value: str) -> str:
    """The first four characters of ``value`` followed by an ellipsis."""
    return value[:4] + "…"


def fingerprint(value: str) -> str:
    """``sha256:`` and the hex SHA-256 of the value's UTF-8 bytes (surrogates kept as bytes)."""
    return "sha256:" + hashlib.sha256(value.encode("utf-8", "surrogateescape")).hexdigest()


def load_allow(root: Path) -> Allow:
    """Read ``<root>/.nmg/secret-scan-allow``. Blank lines and ``#`` comments are ignored; a
    missing file allows nothing."""
    path = root / ALLOW_FILE
    if not path.is_file():
        return Allow()
    fingerprints: set[str] = set()
    pairs: set[str] = set()
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        if entry.startswith("sha256:"):
            fingerprints.add(entry)
        else:
            pairs.add(entry)
    return Allow(frozenset(fingerprints), frozenset(pairs))


def scan_text(path: str, data: bytes) -> list[Match]:
    """Every content match in ``data``. Binary data and Git LFS pointers yield nothing."""
    if b"\0" in data[:BINARY_PROBE_BYTES] or data.startswith(LFS_POINTER_PREFIX):
        return []
    text = data.decode("utf-8", errors="replace")
    matches: list[Match] = []
    for number, line in enumerate(text.split("\n"), start=1):
        for name, pattern in PATTERNS:
            for found in pattern.finditer(line):
                matches.append(Match(path, number, name, found.group(0)))
    return matches


def _scan_files(files: Iterable[tuple[str, bytes]]) -> list[Match]:
    matches: list[Match] = []
    for path, data in files:
        if Path(path).name == ENV_FILE_NAME:
            matches.append(Match(path, 0, ENV_FILE_PATTERN, path))
        matches.extend(scan_text(path, data))
    return matches


def _unallowed(matches: Iterable[Match], allow: Allow) -> list[Match]:
    kept = [match for match in matches if not allow.permits(match)]
    return sorted(kept, key=lambda match: (match.path, match.line))


def _git(root: Path, run: Runner, *args: str) -> bytes:
    argv = ["git", "-C", str(root), *args]
    try:
        proc = run(argv, capture_output=True, check=False)
    except OSError as error:
        raise GitError(f"git {args[0]} could not run in {root}: {error}") from error
    if proc.returncode != 0:
        detail = proc.stderr.decode("utf-8", errors="replace").strip()
        raise GitError(f"git {args[0]} failed in {root}: {detail or f'exit {proc.returncode}'}")
    return bytes(proc.stdout)


def _split_z(data: bytes) -> list[str]:
    return [os.fsdecode(part) for part in data.split(b"\0") if part]


def _in_work_tree(root: Path, run: Runner) -> bool:
    try:
        return _git(root, run, "rev-parse", "--is-inside-work-tree").strip() == b"true"
    except GitError:
        return False


def _walk_skipped(path: Path, root: Path) -> bool:
    relative = path.relative_to(root)
    parts = relative.parts
    name = parts[-1]
    return (
        parts[0] in WALK_SKIP_TOP
        or parts[:2] == WALK_SKIP_GODOT_CACHE
        or any(part in WALK_SKIP_DIRS for part in parts)
        or name == ENV_FILE_NAME
        or name.startswith(ENV_FILE_NAME + ".")
        or relative.as_posix() in WALK_SKIP_FILES
    )


def _read_text_file(path: Path) -> bytes:
    """The file's bytes, or ``b""`` when its first ``BINARY_PROBE_BYTES`` mark it binary or an LFS
    pointer, so a large asset is never read whole."""
    with path.open("rb") as handle:
        head = handle.read(BINARY_PROBE_BYTES)
        if b"\0" in head or head.startswith(LFS_POINTER_PREFIX):
            return b""
        return head + handle.read()


def _walk_files(root: Path) -> Iterator[tuple[str, bytes]]:
    """Every regular file under ``root``, one at a time, except ``.git/``, ``release/``,
    ``game/.godot/``, ``.venv/`` and ``node_modules/`` folders, ``.env`` and ``.env.*`` files, and
    ``.claude/settings.local.json``. Symbolic links are not followed."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if not _walk_skipped(Path(dirpath, name), root)]
        for name in filenames:
            path = Path(dirpath, name)
            if _walk_skipped(path, root) or path.is_symlink() or not path.is_file():
                continue
            yield path.relative_to(root).as_posix(), _read_text_file(path)


def _staged_paths(root: Path, run: Runner) -> list[str]:
    """Staged added, copied, modified, renamed, or type-changed paths, except gitlinks
    (submodules), which have no blob to read."""
    raw = _git(root, run, "diff", "--cached", "--raw", "-z", "--no-renames", "--diff-filter=ACMRT")
    fields = _split_z(raw)
    # Each record is ":<old mode> <new mode> <old id> <new id> <status>" then its path.
    return [
        path
        for header, path in zip(fields[0::2], fields[1::2], strict=True)
        if header.split(" ")[1] != GITLINK_MODE
    ]


def staged_files(root: Path, run: Runner = subprocess.run) -> Iterator[tuple[str, bytes]]:
    """Each staged added, copied, modified, renamed, or type-changed path with its index blob
    bytes. The explicit stage-0 form ``:0:<path>`` keeps a path such as ``0:x`` from being
    read as an index stage."""
    names = _staged_paths(root, run)
    return ((name, _git(root, run, "cat-file", "blob", f":0:{name}")) for name in names)


def _tracked_from_index(root: Path, names: list[str]) -> Iterator[tuple[str, bytes]]:
    for name in names:
        path = root / name
        if path.is_file() and not path.is_symlink():
            yield name, _read_text_file(path)


def tracked_files(root: Path, run: Runner = subprocess.run) -> Iterator[tuple[str, bytes]]:
    """Each tracked path with its working-tree bytes, read one file at a time. Outside a git work
    tree, the regular files under ``root`` are walked instead (see ``_walk_files``)."""
    if not _in_work_tree(root, run):
        return _walk_files(root)
    return _tracked_from_index(root, _split_z(_git(root, run, "ls-files", "-z")))


def scan_staged(root: Path, run: Runner = subprocess.run) -> list[Match]:
    """The unallowed matches in the staged index blobs, sorted by path and line."""
    return _unallowed(_scan_files(staged_files(root, run)), load_allow(root))


def scan_tracked(root: Path, run: Runner = subprocess.run) -> list[Match]:
    """The unallowed matches in the tracked files, sorted by path and line."""
    return _unallowed(_scan_files(tracked_files(root, run)), load_allow(root))


def _default_root() -> Path:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"], capture_output=True, check=False
        )
    except OSError:
        return Path.cwd()
    top = proc.stdout.decode("utf-8", errors="replace").strip() if proc.returncode == 0 else ""
    return Path(top) if top else Path.cwd()


def main(argv: Sequence[str] | None = None) -> int:
    """Scan staged blobs (default) or tracked files under ``--root`` and return the exit code."""
    parser = argparse.ArgumentParser(
        prog="nmg_secret_scan",
        description="Block API keys in staged or tracked files.",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--staged", action="store_true", help="scan the staged blobs (default)")
    mode.add_argument("--tracked", action="store_true", help="scan the tracked files")
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repository or consumer root (default: the git top level, else the cwd)",
    )
    args = parser.parse_args(argv)
    root = args.root if args.root is not None else _default_root()
    try:
        matches = scan_tracked(root) if args.tracked else scan_staged(root)
    except GitError as error:
        print(f"secret scan: {error}", file=sys.stderr)
        return 2
    if not matches:
        return 0
    print(f"secret scan: {len(matches)} match(es) blocked", file=sys.stderr)
    for match in matches:
        print(match.render(), file=sys.stderr)
    print(REMEDIATION, file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
