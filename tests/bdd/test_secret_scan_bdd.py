"""pytest-bdd bindings for secret_scan.feature: SCN001–SCN005 (#255 AC1–AC5).

Each scenario uses a temporary git repository. SCN001, SCN002 and SCN005 run real ``git`` and the
hook that onboarding installed, SCN003 runs the scanner CLI, and SCN004 runs the real ship runner
against the fake Godot in ``tests/ship_fakes.py``. Every key is assembled at runtime, and no
scenario contacts a service.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.onboard import OnboardError, run_onboard
from nmg_game_dev.onboard.commands import default_run
from nmg_game_dev.onboard.report import format_report
from nmg_game_dev.onboard.secrets_hook import (
    HOOK_TEXT,
    ensure_precommit_hook,
    ensure_secret_scanner,
)
from nmg_game_dev.secrets.scan import fingerprint, mask
from nmg_game_dev.ship.errors import ShipError
from tests.onboard_fakes import (
    APPLE_SILICON,
    FakeRunner,
    all_tools_present,
    gib_free,
    make_consumer,
    make_framework,
)
from tests.ship_fakes import ShipSandbox, make_sandbox

FEATURE = "secret_scan.feature"
COMMIT_IDENTITY = ("-c", "user.name=Scan BDD", "-c", "user.email=scan-bdd@example.invalid")
FOREIGN_HOOK = "#!/bin/sh\necho 'a team hook'\nexit 0\n"
EXISTING_HOOKS: dict[str, str | None] = {
    "no pre-commit hook": None,
    "the nmg pre-commit hook": HOOK_TEXT,
    "a foreign pre-commit hook": FOREIGN_HOOK,
}
KEYS: dict[str, tuple[str, str]] = {
    # kind -> (value that is put in the file, pattern name the scanner reports)
    "Meshy": ("msy_" + "Ab3dEf6hIj9kLm2nOp5q", "meshy"),
    "ElevenLabs": ("sk_" + "0123456789abcdef" * 3, "elevenlabs"),
    "Anthropic": ("sk-ant-" + "api03-" + "Zx9Qw7Er5Ty3Ui1Op0As8Df", "anthropic"),
    "OpenAI": ("sk-" + "proj-" + "Qw8Er5Ty3Ui1Op0As8DfGh", "openai"),
    "GitHub": ("ghp_" + "a" * 36, "github"),
    "AWS": ("AKIA" + "ABCDEFGHIJKLMNOP", "aws"),
    "PEM private key": ("-----BEGIN RSA PRIVATE KEY-----", "private-key"),
}
MESHY = KEYS["Meshy"][0]


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *COMMIT_IDENTITY, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _new_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "consumer"
    repo.mkdir()
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True, capture_output=True)
    return repo


def _onboard_hook(repo: Path) -> None:
    """Install the two #255 onboarding steps into a real repository."""
    framework = make_framework(repo.parent / "framework")
    assert ensure_secret_scanner("secret_scanner", framework, repo, False).status == "installed"
    assert ensure_precommit_hook("precommit_hook", repo, run=default_run).status == "installed"


def _stage(repo: Path, rel: str, data: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "--", rel], check=True, capture_output=True)


def _commit(ctx: dict[str, Any]) -> None:
    ctx["commit"] = _git(ctx["repo"], "commit", "-q", "-m", "scenario commit")


def _scanner_cli(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "nmg_game_dev.secrets", "scan", *args, "--root", str(repo)],
        capture_output=True,
        text=True,
        check=False,
    )


# --- SCN001 ------------------------------


@scenario(FEATURE, "A commit containing a key is blocked")
def test_a_commit_containing_a_key_is_blocked() -> None:
    """AC1: the hook exits 1 and prints the masked match, and the raw value never appears."""


@given("an onboarded consumer git repository", target_fixture="ctx")
def _onboarded_repo(tmp_path: Path) -> dict[str, Any]:
    repo = _new_repo(tmp_path)
    _onboard_hook(repo)
    return {"repo": repo, "value": None, "location": None, "commit": None}


@given(parsers.parse("a staged file containing a {kind} key"))
def _staged_key(ctx: dict[str, Any], kind: str) -> None:
    if kind == "staged .env file":
        _stage(ctx["repo"], ".env", "MESHY_API_KEY=placeholder\n")
        ctx["location"] = (".env", 0)
        ctx["value"] = ".env"
        ctx["pattern"] = "env-file"
        return
    value, pattern = KEYS[kind]
    _stage(ctx["repo"], "scripts/setup.gd", f'var key = "{value}"\n')
    ctx["location"] = ("scripts/setup.gd", 1)
    ctx["value"] = value
    ctx["pattern"] = pattern


@when("the pre-commit hook runs")
def _run_hook(ctx: dict[str, Any]) -> None:
    _commit(ctx)


@then(
    parsers.parse(
        'it exits 1 and prints the file, line, pattern "{pattern}", the value masked to its first '
        "4 characters, and its fingerprint"
    )
)
def _blocked_line(ctx: dict[str, Any], pattern: str) -> None:
    commit = ctx["commit"]
    assert commit.returncode == 1, commit.stderr
    path, line = ctx["location"]
    value = ctx["value"]
    expected = f"{path}:{line}: {pattern} {mask(value)} ({fingerprint(value)})"
    assert expected in commit.stderr.splitlines(), commit.stderr


@then("the unmasked value does not appear in the output")
def _value_hidden(ctx: dict[str, Any]) -> None:
    output = ctx["commit"].stdout + ctx["commit"].stderr
    if ctx["pattern"] != "env-file":
        assert ctx["value"] not in output


# --- SCN002 ------------------------------


@scenario(FEATURE, "A clean commit passes silently")
def test_a_clean_commit_passes_silently() -> None:
    """AC2: no match gives exit 0 with no output."""


@given(
    "an onboarded consumer git repository with a staged file containing no key",
    target_fixture="ctx",
)
def _clean_repo(tmp_path: Path) -> dict[str, Any]:
    repo = _new_repo(tmp_path)
    _onboard_hook(repo)
    _stage(repo, "main.gd", "extends Node\n")
    return {"repo": repo}


@then("it exits 0 with no output")
def _clean_passes(ctx: dict[str, Any]) -> None:
    assert ctx["commit"].returncode == 0
    assert ctx["commit"].stdout == "" and ctx["commit"].stderr == ""


# --- SCN003 ------------------------------


@scenario(FEATURE, "False positives can be allowed")
def test_false_positives_can_be_allowed() -> None:
    """AC3: an allowed fingerprint suppresses only its match."""


@given("a staged file with two Meshy-pattern matches", target_fixture="ctx")
def _two_matches(tmp_path: Path) -> dict[str, Any]:
    repo = _new_repo(tmp_path)
    second = "msy_" + "Zz8Yy7Xx6Ww5Vv4Uu3Tt2"
    _stage(repo, "scripts/keys.gd", f'var a = "{MESHY}"\nvar b = "{second}"\n')
    return {"repo": repo}


@given(".nmg/secret-scan-allow lists the first match's fingerprint")
def _allow_first(ctx: dict[str, Any]) -> None:
    allow = ctx["repo"] / ".nmg" / "secret-scan-allow"
    allow.parent.mkdir(exist_ok=True)
    allow.write_text(f"{fingerprint(MESHY)}\n", encoding="utf-8")


@when("the scan runs")
def _scan(ctx: dict[str, Any]) -> None:
    ctx["scan"] = _scanner_cli(ctx["repo"], "--staged")


@then("only the second match is reported")
def _second_only(ctx: dict[str, Any]) -> None:
    result = ctx["scan"]
    assert result.returncode == 1, result.stderr
    lines = result.stderr.splitlines()
    assert lines[0] == "secret scan: 1 match(es) blocked"
    assert lines[1].startswith("scripts/keys.gd:2: meshy msy_… ")


# --- SCN004 ------------------------------


@scenario(FEATURE, "/ship refuses to build with a key in tracked files")
def test_ship_refuses_to_build_with_a_key_in_tracked_files() -> None:
    """AC4: the ship gate stops with ship.secret_found before any Godot command."""


@given("a consumer whose tracked file contains an AWS key", target_fixture="ship")
def _tracked_aws_key(tmp_path: Path) -> ShipSandbox:
    sandbox = make_sandbox(tmp_path)
    consumer = sandbox.game.parent
    subprocess.run(["git", "-C", str(consumer), "init", "-q"], check=True, capture_output=True)
    player = sandbox.game / "scripts" / "player.gd"
    player.write_text(player.read_text(encoding="utf-8") + f'var k = "{KEYS["AWS"][0]}"\n')
    subprocess.run(
        ["git", "-C", str(consumer), "add", "game/scripts/player.gd"],
        check=True,
        capture_output=True,
    )
    return sandbox


@when(parsers.parse('"/ship {target} --dry-run" runs'), target_fixture="ship_error")
def _ship_dry_run(ship: ShipSandbox, target: str) -> ShipError | None:
    try:
        ship.ship(target, dry_run=True)
    except ShipError as error:
        return error
    return None


@then(parsers.parse('it stops with "{code}" listing the masked match'))
def _stops_with_code(ship_error: ShipError | None, code: str) -> None:
    assert ship_error is not None, "the ship ran past the secret scan"
    assert ship_error.code == code
    assert "scripts/player.gd:2: aws AKIA… (sha256:" in ship_error.message
    assert KEYS["AWS"][0] not in ship_error.message


@then("no Godot command ran")
def _no_godot(ship: ShipSandbox) -> None:
    assert ship.godot.calls == []


# --- SCN005 ------------------------------


@scenario(FEATURE, "Onboarding installs the hook safely")
def test_onboarding_installs_the_hook_safely() -> None:
    """AC5: the hook is installed, unchanged, or a conflict that never overwrites a foreign hook."""


@given(parsers.parse("a consumer git repository with {existing}"), target_fixture="ctx")
def _consumer_with_hook(tmp_path: Path, existing: str) -> dict[str, Any]:
    consumer = make_consumer(tmp_path)
    hooks = consumer / ".git" / "hooks"
    hooks.mkdir(parents=True)
    before = EXISTING_HOOKS[existing]
    if before is not None:
        (hooks / "pre-commit").write_text(before, encoding="utf-8")
    return {"consumer": consumer, "before": before, "results": []}


@when("onboarding runs")
def _onboard(ctx: dict[str, Any], tmp_path: Path) -> None:
    volume = tmp_path / "volume"
    try:
        ctx["results"] = run_onboard(
            ctx["consumer"],
            framework=make_framework(tmp_path / "framework"),
            models_dir=volume / "nmg-texture-models",
            env={
                "BLENDER_EXTENSIONS_DIR": str(tmp_path / "ext" / "user_default"),
                "TEXTURE_GEN_MODELS_DIR": str(volume / "nmg-texture-models"),
            },
            run=FakeRunner(work_tree=True),
            which=all_tools_present,
            host=APPLE_SILICON,
            free_bytes=gib_free,
        )
    except OnboardError as error:  # pragma: no cover - a preflight failure is a test defect
        raise AssertionError(error.code) from error


@then(parsers.parse('the precommit_hook step is "{status}"'))
def _hook_status(ctx: dict[str, Any], status: str) -> None:
    step = next(result for result in ctx["results"] if result.name == "precommit_hook")
    assert step.status == status, format_report(ctx["results"])


@then("a foreign hook is left byte-identical")
def _foreign_unchanged(ctx: dict[str, Any]) -> None:
    hook = ctx["consumer"] / ".git" / "hooks" / "pre-commit"
    if ctx["before"] is not None:
        assert hook.read_text(encoding="utf-8") == ctx["before"]
    else:
        assert hook.read_text(encoding="utf-8") == HOOK_TEXT
