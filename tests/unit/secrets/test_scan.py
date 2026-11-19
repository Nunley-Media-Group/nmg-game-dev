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
    Match,
    fingerprint,
    main,
    mask,
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
