"""The #255 secret scanner: each pattern, masking, the allow file, the git sources, and the exit
codes (AC1, AC2, AC3, FR1, FR4).

Every key below is assembled at runtime from fragments, so no key-shaped literal sits in the
repository. The repositories are temporary git work trees; nothing contacts a service.
"""

from __future__ import annotations

import ast
import hashlib
import subprocess
import sys
from pathlib import Path

import pytest

from nmg_game_dev.secrets import scan
from nmg_game_dev.secrets.__main__ import main as cli_main
from nmg_game_dev.secrets.scan import (
    GitError,
    Match,
    fingerprint,
    main,
    mask,
    scan_shippable,
    scan_staged,
    scan_text,
    scan_tracked,
)

MESHY = "msy_" + "Ab3dEf6hIj9kLm2nOp5q"
ELEVENLABS = "sk_" + "0123456789abcdef" * 3
ANTHROPIC = "sk-ant-" + "api03-" + "Zx9Qw7Er5Ty3Ui1Op0As8Df"
OPENAI_PROJECT = "sk-" + "proj-" + "Qw8Er5Ty3Ui1Op0As8DfGh"
OPENAI_LEGACY = "sk-" + "Qw8Er5Ty3Ui1Op0As8DfGhJk"
GITHUB_CLASSIC = "ghp_" + "a" * 36
GITHUB_FINE_GRAINED = "github_pat_" + "B" * 30
AWS = "AKIA" + "ABCDEFGHIJKLMNOP"
PEM = "-----BEGIN RSA PRIVATE KEY-----"
LFS_HEADER = b"version https://git-lfs.github.com/spec/v1\n"

KIND_CASES = [
    pytest.param(MESHY, "meshy", id="meshy"),
    pytest.param(ELEVENLABS, "elevenlabs", id="elevenlabs"),
    pytest.param(ANTHROPIC, "anthropic", id="anthropic"),
    pytest.param(OPENAI_PROJECT, "openai", id="openai-proj"),
    pytest.param(OPENAI_LEGACY, "openai", id="openai-legacy"),
    pytest.param(GITHUB_CLASSIC, "github", id="github-classic"),
    pytest.param(GITHUB_FINE_GRAINED, "github", id="github-fine-grained"),
    pytest.param(AWS, "aws", id="aws"),
    pytest.param(PEM, "private-key", id="pem"),
]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Scan Test",
            "-c",
            "user.email=scan-test@example.invalid",
            *args,
        ],
        check=True,
        capture_output=True,
    )


def _stage(repo: Path, name: str, data: bytes) -> None:
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    _git(repo, "add", "--", name)


def _allow(repo: Path, text: str) -> None:
    (repo / ".nmg").mkdir(exist_ok=True)
    (repo / ".nmg" / "secret-scan-allow").write_text(text, encoding="utf-8")


def _err_lines(capsys: pytest.CaptureFixture[str]) -> list[str]:
    return capsys.readouterr().err.splitlines()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "consumer"
    root.mkdir()
    _git(root, "init", "-q")
    return root


# Patterns and the staged-commit gate (AC1) -------------------------------------------------------


@pytest.mark.parametrize(("value", "pattern"), KIND_CASES)
def test_a_staged_key_is_blocked_with_a_masked_line(
    repo: Path, capsys: pytest.CaptureFixture[str], value: str, pattern: str
) -> None:
    _stage(repo, "scripts/setup.gd", f'var key = "{value}"\n'.encode())

    assert main(["--staged", "--root", str(repo)]) == 1

    err = capsys.readouterr().err
    lines = [line for line in err.splitlines() if line.startswith("scripts/setup.gd:")]
    assert len(lines) == 1
    digest = hashlib.sha256(value.encode()).hexdigest()
    assert lines[0] == (f"scripts/setup.gd:1: {pattern} {value[:4]}… (sha256:{digest})")
    assert value not in err


def test_a_staged_env_file_is_blocked_on_line_zero(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stage(repo, ".env", b"MESHY_API_KEY=placeholder\n")

    assert main(["--staged", "--root", str(repo)]) == 1

    lines = _err_lines(capsys)
    assert lines[1].startswith(".env:0: env-file .env… (sha256:")


def test_every_match_gets_its_own_line_and_the_summary_counts_them(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    second = "msy_" + "Zz8Yy7Xx6Ww5Vv4Uu3Tt2"
    _stage(repo, "a.gd", f'var a = "{MESHY}"\nvar b = "{second}"\n'.encode())

    assert main(["--staged", "--root", str(repo)]) == 1

    lines = _err_lines(capsys)
    assert lines[0] == "secret scan: 2 match(es) blocked"
    assert [line.split(" ")[0] for line in lines[1:3]] == ["a.gd:1:", "a.gd:2:"]
    assert lines[-1] == scan.REMEDIATION
    assert MESHY not in "\n".join(lines) and second not in "\n".join(lines)


def test_a_clean_commit_passes_silently(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """AC2: no match gives exit 0 with empty stdout and stderr."""
    _stage(repo, "main.gd", b"extends Node\n")

    assert main(["--staged", "--root", str(repo)]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_a_key_split_across_lines_is_not_one_match(repo: Path) -> None:
    """Patterns are matched one line at a time, so the key must sit on one line."""
    head, tail = MESHY[:8], MESHY[8:]
    _stage(repo, "a.gd", f'var a = "{head}"\nvar b = "{tail}"\n'.encode())

    assert scan_staged(repo) == []


# Allow file (AC3) -------------------------------------------------------------------------------


def test_a_fingerprint_entry_suppresses_only_its_match(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    second = "msy_" + "Zz8Yy7Xx6Ww5Vv4Uu3Tt2"
    _stage(repo, "a.gd", f'var a = "{MESHY}"\nvar b = "{second}"\n'.encode())
    _allow(
        repo,
        f"# the fixture key in the docs\n\n{fingerprint(MESHY)}\n",
    )

    assert main(["--staged", "--root", str(repo)]) == 1

    lines = _err_lines(capsys)
    assert lines[0] == "secret scan: 1 match(es) blocked"
    assert lines[1].startswith("a.gd:2: meshy msy_… (sha256:")


def test_a_path_and_pattern_entry_suppresses_that_pattern_in_that_file(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stage(repo, "a.gd", f'var a = "{MESHY}"\nvar b = "{AWS}"\n'.encode())
    _stage(repo, "b.gd", f'var c = "{MESHY}"\n'.encode())
    _allow(repo, "a.gd:meshy\n")

    assert main(["--staged", "--root", str(repo)]) == 1

    lines = _err_lines(capsys)
    assert lines[0] == "secret scan: 2 match(es) blocked"
    assert lines[1].startswith("a.gd:2: aws ")
    assert lines[2].startswith("b.gd:1: meshy ")


def test_a_path_and_pattern_entry_does_not_cover_another_pattern(repo: Path) -> None:
    _stage(repo, "a.gd", f'var a = "{AWS}"\n'.encode())
    _allow(repo, "a.gd:meshy\n")

    assert [match.pattern for match in scan_staged(repo)] == ["aws"]


# Masking and the raw value (FR4) ----------------------------------------------------------------


def test_mask_keeps_four_characters_and_an_ellipsis() -> None:
    assert mask(ANTHROPIC) == "sk-a…"
    assert mask("ab") == "ab…"


def test_fingerprint_is_the_sha256_of_the_value() -> None:
    assert fingerprint("value") == "sha256:" + hashlib.sha256(b"value").hexdigest()


def test_a_match_never_shows_its_value_in_its_repr_or_render() -> None:
    match = Match("a.gd", 4, "meshy", MESHY)
    assert MESHY not in repr(match)
    assert MESHY not in match.render()
    assert match.render().startswith("a.gd:4: meshy msy_… (sha256:")


def test_scan_text_reports_nothing_for_binary_or_lfs_pointer_content() -> None:
    """Binary data (a NUL byte in the first 8000 bytes) and LFS pointers are skipped (T001)."""
    assert scan_text("tex.png", b"\x89PNG\x00" + MESHY.encode()) == []
    assert scan_text("big.glb", LFS_HEADER + f"oid {MESHY}\n".encode()) == []
    assert scan_text("note.txt", f"key {MESHY}\n".encode())[0].line == 1


def test_a_binary_file_staged_with_a_key_is_not_reported(repo: Path) -> None:
    _stage(repo, "art/tex.bin", b"\x00\x01" + f'"{MESHY}"'.encode())
    _stage(repo, "art/big.glb", LFS_HEADER + f"oid {MESHY}\n".encode())

    assert scan_staged(repo) == []


# Sources: staged index, tracked files, and the walk (T001, AC4 fallback) ------------------------


def test_staged_reads_the_index_and_ignores_unstaged_working_tree_edits(repo: Path) -> None:
    _stage(repo, "clean.gd", b"extends Node\n")
    (repo / "clean.gd").write_text(f'var k = "{MESHY}"\n', encoding="utf-8")

    assert scan_staged(repo) == []
    assert main(["--staged", "--root", str(repo)]) == 0


def test_tracked_reads_working_tree_bytes_for_tracked_paths(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stage(repo, "clean.gd", b"extends Node\n")
    (repo / "clean.gd").write_text(f'var k = "{MESHY}"\n', encoding="utf-8")

    assert main(["--tracked", "--root", str(repo)]) == 1
    assert _err_lines(capsys)[1].startswith("clean.gd:1: meshy msy_… ")


def test_tracked_reports_a_committed_env_file(repo: Path) -> None:
    _stage(repo, ".env", b"MESHY_API_KEY=placeholder\n")
    _git(repo, "commit", "-q", "-m", "commit a file that should be ignored")

    assert [m.render().split(" ")[0] for m in scan_tracked(repo)] == [".env:0:"]


def test_tracked_skips_untracked_files_in_a_git_work_tree(repo: Path) -> None:
    (repo / "untracked.gd").write_text(f'var k = "{MESHY}"\n', encoding="utf-8")

    assert scan_tracked(repo) == []


# The /ship file source: tracked files plus untracked files under the project (#296) -------------


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_an_untracked_unignored_file_under_the_project_is_scanned(repo: Path) -> None:
    """AC1: a key in a file Godot could export is reported before the file is ever added."""
    _write(repo, "game/scripts/leak.gd", f'var k = "{MESHY}"\n')

    assert [(m.path, m.line, m.pattern) for m in scan_shippable(repo, "game")] == [
        ("game/scripts/leak.gd", 1, "meshy")
    ]


def test_an_untracked_file_that_gitignore_covers_is_not_scanned(repo: Path) -> None:
    """AC2: an ignored local file under the project is never exported, so it does not block."""
    _write(repo, ".gitignore", "game/local_keys.gd\n")
    _write(repo, "game/local_keys.gd", f'var k = "{MESHY}"\n')

    assert scan_shippable(repo, "game") == []


def test_an_untracked_file_outside_the_project_is_not_scanned(repo: Path) -> None:
    """AC2: Godot exports only the project folder, so a key beside it does not block."""
    _write(repo, "notes/keys.gd", f'var k = "{MESHY}"\n')

    assert scan_shippable(repo, "game") == []


def test_an_untracked_file_under_the_godot_cache_is_not_scanned(repo: Path) -> None:
    """AC2: game/.godot/ is the editor cache that every import rebuilds, never exported."""
    _write(repo, "game/.godot/editor/keys.gd", f'var k = "{MESHY}"\n')

    assert scan_shippable(repo, "game") == []


def test_a_tracked_file_is_scanned_wherever_it_lives(repo: Path) -> None:
    """Tracked files stay in the scan as they were, whatever folder holds them."""
    _stage(repo, "notes/keys.txt", f"key {MESHY}\n".encode())

    assert [(m.path, m.line) for m in scan_shippable(repo, "game")] == [("notes/keys.txt", 1)]


def test_a_symlink_and_a_nested_repository_under_the_project_are_skipped(repo: Path) -> None:
    """FR2: a symbolic link is not followed, and a nested repository is listed as a directory."""
    _write(repo, "game/real.gd", f'var k = "{MESHY}"\n')
    (repo / "game" / "link.gd").symlink_to("real.gd")
    nested = repo / "game" / "nested"
    nested.mkdir()
    _git(nested, "init", "-q")
    _write(nested, "inner.gd", f'var k = "{MESHY}"\n')

    assert [m.path for m in scan_shippable(repo, "game")] == ["game/real.gd"]


def test_a_failing_untracked_listing_raises_git_error(repo: Path) -> None:
    """A git failure while listing the untracked files is a GitError, not a silent pass."""

    def failing_untracked(argv: list[str], **_: object) -> subprocess.CompletedProcess[bytes]:
        if "--others" in argv:
            return subprocess.CompletedProcess(argv, 128, b"", b"fatal: index file corrupt\n")
        return subprocess.run(argv, capture_output=True, check=False)

    with pytest.raises(GitError, match="index file corrupt"):
        scan_shippable(repo, "game", run=failing_untracked)


def test_outside_a_work_tree_the_ship_scan_walks_as_before(tmp_path: Path) -> None:
    """FR3: outside git the walk and its exclusions are unchanged, so a file under the root is
    scanned while the local stores and the .godot/ cache are skipped."""
    root = tmp_path / "consumer"
    root.mkdir()
    _write(root, "game/notes.txt", f"key {MESHY}\n")
    _write(root, "notes/keys.txt", f"key {MESHY}\n")
    for skipped in (".env", ".claude/settings.local.json", ".venv/lib/x.py", "game/.godot/x.txt"):
        _write(root, skipped, f"MESHY_API_KEY={MESHY}\n")

    assert [(m.path, m.line) for m in scan_shippable(root, "game")] == [
        ("game/notes.txt", 1),
        ("notes/keys.txt", 1),
    ]


def test_outside_a_work_tree_tracked_walks_every_file_under_the_root(tmp_path: Path) -> None:
    root = tmp_path / "consumer"
    root.mkdir()
    (root / "notes.txt").write_text(f"key {MESHY}\n", encoding="utf-8")
    for skipped in ("release", ".git", "game/.godot"):
        folder = root / skipped
        folder.mkdir(parents=True)
        (folder / "hidden.txt").write_text(MESHY, encoding="utf-8")

    matches = scan_tracked(root)

    assert [(match.path, match.line) for match in matches] == [("notes.txt", 1)]


def test_the_walk_skips_local_only_secret_stores(tmp_path: Path) -> None:
    """A non-git consumer keeps its keys in ``.env`` as the remediation says; the walk must not
    block every ship on them (#255 review F1)."""
    root = tmp_path / "consumer"
    root.mkdir()
    (root / "notes.txt").write_text(f"key {MESHY}\n", encoding="utf-8")
    for skipped in (
        ".env",
        ".env.local",
        "tools/.env",
        ".claude/settings.local.json",
        ".venv/lib/site.py",
        "web/node_modules/pkg/index.js",
    ):
        path = root / skipped
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"MESHY_API_KEY={MESHY}\n", encoding="utf-8")
    (root / ".claude" / "settings.json").write_text(f'"{MESHY}"\n', encoding="utf-8")

    matches = scan_tracked(root)

    assert [(match.path, match.line) for match in matches] == [
        (".claude/settings.json", 1),
        ("notes.txt", 1),
    ]


def test_the_walk_reads_only_the_probe_bytes_of_a_binary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files stream one at a time, and a binary asset is never read past its probe (review F6)."""
    root = tmp_path / "consumer"
    root.mkdir()
    (root / "asset.glb").write_bytes(b"glTF\0" + b"x" * (scan.BINARY_PROBE_BYTES * 4))
    (root / "notes.txt").write_text(f"key {MESHY}\n", encoding="utf-8")
    reads: list[int] = []
    real_open = Path.open

    def recording_open(self: Path, *args: object, **kwargs: object) -> object:
        handle = real_open(self, *args, **kwargs)  # type: ignore[call-overload]
        real_read = handle.read

        def read(size: int = -1) -> bytes:
            data: bytes = real_read(size)
            if self.name == "asset.glb":
                reads.append(len(data))
            return data

        handle.read = read
        return handle

    monkeypatch.setattr(Path, "open", recording_open)

    files = scan.tracked_files(root)
    assert not isinstance(files, list)
    assert dict(files)["asset.glb"] == b""
    assert reads == [scan.BINARY_PROBE_BYTES]
    assert [(m.path, m.line) for m in scan_tracked(root)] == [("notes.txt", 1)]


def test_a_staged_submodule_is_skipped_and_the_rest_is_scanned(repo: Path) -> None:
    """A gitlink has no blob to read; it must not fail the commit with exit 2 (review F4)."""
    inner = repo / "inner"
    inner.mkdir()
    _git(inner, "init", "-q")
    (inner / "README.md").write_text("inner\n", encoding="utf-8")
    _git(inner, "add", "README.md")
    _git(inner, "commit", "-q", "-m", "inner")
    _git(repo, "add", "inner")
    _stage(repo, "clean.gd", b"extends Node\n")

    assert scan_staged(repo) == []
    assert main(["--staged", "--root", str(repo)]) == 0

    _stage(repo, "leak.gd", f'var k = "{MESHY}"\n'.encode())
    assert [(m.path, m.pattern) for m in scan_staged(repo)] == [("leak.gd", "meshy")]


def test_a_staged_type_change_is_scanned(repo: Path) -> None:
    """A symlink replaced by a regular file holding a key is a "T" change (review F1)."""
    (repo / "f.txt").symlink_to("target.txt")
    _git(repo, "add", "f.txt")
    _git(repo, "commit", "-q", "-m", "a symlink")
    (repo / "f.txt").unlink()
    _stage(repo, "f.txt", f"{AWS}\n".encode())

    assert [(m.path, m.pattern) for m in scan_staged(repo)] == [("f.txt", "aws")]
    assert main(["--staged", "--root", str(repo)]) == 1


def test_a_staged_path_that_looks_like_an_index_stage_is_scanned(repo: Path) -> None:
    """``:0:x`` would read stage 0 of ``x``; the blob read must name stage 0 explicitly
    (review F1)."""
    _stage(repo, "0:x", f"{AWS}\n".encode())
    _stage(repo, "clean.gd", b"var ok = 1\n")

    assert [(m.path, m.pattern) for m in scan_staged(repo)] == [("0:x", "aws")]
    assert main(["--staged", "--root", str(repo)]) == 1


def test_a_staged_rename_is_scanned_under_its_new_path(repo: Path) -> None:
    _stage(repo, "old.gd", f'var k = "{MESHY}"\n'.encode())
    _allow(repo, "old.gd:meshy\n")
    _git(repo, "commit", "-q", "-m", "allowed under the old name")
    _git(repo, "mv", "old.gd", "new.gd")

    assert [(m.path, m.pattern) for m in scan_staged(repo)] == [("new.gd", "meshy")]


def test_staged_outside_a_work_tree_exits_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--staged", "--root", str(tmp_path)]) == 2
    assert _err_lines(capsys)[0].startswith("secret scan: git diff")


def test_the_allow_file_is_read_relative_to_the_root(repo: Path) -> None:
    _stage(repo, "a.gd", f'var a = "{MESHY}"\n'.encode())
    _allow(repo, f"{fingerprint(MESHY)}\n")

    assert scan_staged(repo) == []


# Entry points and the stdlib-only contract (FR1) ------------------------------------------------


def test_the_cli_scan_subcommand_delegates_to_the_scanner(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _stage(repo, "clean.gd", b"extends Node\n")

    assert cli_main(["scan", "--staged", "--root", str(repo)]) == 0
    assert cli_main([]) == 2
    assert "usage: python -m nmg_game_dev.secrets scan" in capsys.readouterr().err


def test_the_scanner_imports_only_the_standard_library() -> None:
    tree = ast.parse(Path(scan.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= set(sys.stdlib_module_names)
