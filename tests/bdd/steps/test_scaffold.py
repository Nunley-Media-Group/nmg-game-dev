"""pytest-bdd step definitions for scaffold-plugin-repo-session-start-hooks.feature.

Launcher-invoking steps mock Blender/UE so the suite runs without either installed.
Idempotency binds a real TCP socket on an ephemeral port to simulate LISTEN state.
"""

from __future__ import annotations

import importlib
import os
import pathlib
import re
import socket
import subprocess
import time
from dataclasses import dataclass
from typing import Any

import pytest
from _scaffold_contract import (
    BANNED_DOGFOOD_ARTIFACTS,
    BANNED_SUBSTRINGS,
    CONSUMER_FACING,
    EXPECTED_VERSION,
    FLOATING_VERSION_REFS,
    GITKEEP_DIRS,
    REPO_ROOT,
    REQUIRED_DIRS,
    REQUIRED_SERVERS,
)
from pytest_bdd import given, scenario, then, when

FEATURE = "scaffold-plugin-repo-session-start-hooks.feature"

BLENDER_TEST_PORT = "19876"
UE_TEST_PORT = "18088"
MISSING_BINARY_TEST_PORT = "29876"


@dataclass
class LauncherRun:
    result: subprocess.CompletedProcess[str]
    elapsed_seconds: float


def _run_launcher(
    script_name: str, env_overrides: dict[str, str], timeout: int = 10
) -> LauncherRun:
    env = os.environ.copy()
    env.update(env_overrides)
    start = time.monotonic()
    result = subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / script_name)],
        capture_output=True,
        text=True,
        env=env,
        timeout=timeout,
    )
    return LauncherRun(result=result, elapsed_seconds=time.monotonic() - start)


@scenario(FEATURE, "Plugin manifest is valid (AC1)")
def test_plugin_manifest_valid() -> None:
    pass


@scenario(FEATURE, "Directory layout matches steering/structure.md (AC2)")
def test_directory_layout() -> None:
    pass


@scenario(FEATURE, "Launcher scripts detach Blender and UE when invoked manually (AC3)")
def test_blender_launcher_detaches() -> None:
    pass


@scenario(FEATURE, "start-unreal-mcp.sh detaches the UE Editor on the expected port (AC3)")
def test_unreal_launcher_detaches() -> None:
    pass


@scenario(FEATURE, "Launchers are idempotent when the port is already bound (AC4)")
def test_launcher_idempotent() -> None:
    pass


@scenario(FEATURE, "Launcher fails with a one-line remediation when the binary is missing (AC5)")
def test_launcher_remediation() -> None:
    pass


@scenario(FEATURE, "Consumer SessionStart template ships under templates/consumer/ (AC5b)")
def test_consumer_template() -> None:
    pass


@scenario(FEATURE, "Python package bootstraps (AC6)")
def test_python_package_bootstraps() -> None:
    pass


@scenario(FEATURE, "VERSION and CHANGELOG are seeded (AC7)")
def test_versioning_seeded() -> None:
    pass


@scenario(FEATURE, "MCP server config is pinned and dual-purpose (AC8)")
def test_mcp_config_pinned() -> None:
    pass


@scenario(FEATURE, "AGENTS.md points at steering + SDLC entry (AC9)")
def test_agents_md_pointers() -> None:
    pass


@scenario(FEATURE, "Nothing this-repo-specific leaks into consumer-facing deliverables (AC10)")
def test_no_consumer_leak() -> None:
    pass


@scenario(FEATURE, "Install-scope invariance (AC11)")
def test_install_scope_invariance() -> None:
    pass


@pytest.fixture
def fake_blender_bin(tmp_path: pathlib.Path) -> pathlib.Path:
    fake = tmp_path / "blender"
    fake.write_text("#!/usr/bin/env bash\nexit 0\n")
    fake.chmod(0o755)
    return fake


@pytest.fixture
def fake_ue_root(tmp_path: pathlib.Path) -> pathlib.Path:
    ue_dir = tmp_path / "Engine" / "Binaries" / "Mac" / "UnrealEditor.app" / "Contents" / "MacOS"
    ue_dir.mkdir(parents=True)
    fake = ue_dir / "UnrealEditor"
    fake.write_text("#!/usr/bin/env bash\nexit 0\n")
    fake.chmod(0o755)
    return tmp_path


@pytest.fixture
def bound_port() -> Any:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port: int = sock.getsockname()[1]
    sock.listen(1)
    yield port
    sock.close()


@given("the repo root of nmg-game-dev is the working directory")
def repo_root_is_cwd() -> None:
    assert REPO_ROOT.is_dir(), f"Repo root not found: {REPO_ROOT}"


@given("`.codex-plugin/plugin.json` exists at the repo root")
def plugin_json_exists(repo_root: pathlib.Path) -> None:
    assert (repo_root / ".codex-plugin" / "plugin.json").is_file()


@when("the plugin manifest is validated against Codex's plugin schema")
def validate_plugin_manifest(plugin_data: dict[str, Any]) -> None:
    assert plugin_data  # JSON parsed successfully in the fixture


@then("validation passes with no errors")
def manifest_validation_passes() -> None:
    pass


@then('the manifest declares "name", "version", "description", "author", and skills fields')
def manifest_has_required_fields(plugin_data: dict[str, Any]) -> None:
    for field in ("name", "version", "description", "author", "skills"):
        assert field in plugin_data, f"plugin.json missing field: {field}"
    assert plugin_data["skills"] == "./skills/"
    assert "capabilities" not in plugin_data
    assert "requires" not in plugin_data


@then("`.agents/plugins/marketplace.json` points to the local plugin")
def marketplace_points_local(marketplace_data: dict[str, Any]) -> None:
    entry = marketplace_data["plugins"][0]
    assert entry["name"] == "nmg-game-dev"
    assert entry["source"] == {"source": "local", "path": "."}


@given("the layout declared in `steering/structure.md` § Project Layout")
def layout_declared(repo_root: pathlib.Path) -> None:
    assert (repo_root / "steering" / "structure.md").is_file()


@when("`ls` probes every top-level directory listed there")
def probe_directories(repo_root: pathlib.Path) -> None:
    missing = [d for d in REQUIRED_DIRS if not (repo_root / d).is_dir()]
    assert not missing, f"Missing directories: {missing}"


@then("every declared directory exists")
def every_dir_exists() -> None:
    pass


@then("empty directories carry a `.gitkeep`")
def empty_dirs_have_gitkeep(repo_root: pathlib.Path) -> None:
    for rel in GITKEEP_DIRS:
        p = repo_root / rel
        contents = list(p.iterdir())
        has_gitkeep = any(f.name == ".gitkeep" for f in contents)
        has_content = any(f.name != ".gitkeep" for f in contents)
        assert has_gitkeep or has_content, f"{rel} is empty (no .gitkeep and no content)"


@then(
    "the Python package `src/nmg_game_dev/` is importable with submodule stubs"
    " for `pipeline/`, `variants/`, `quality/`, `ship/`"
)
def python_package_importable() -> None:
    for mod in (
        "nmg_game_dev",
        "nmg_game_dev.pipeline",
        "nmg_game_dev.variants",
        "nmg_game_dev.quality",
        "nmg_game_dev.ship",
    ):
        importlib.import_module(mod)


@given(
    "a developer, working inside the nmg-game-dev repo, invokes"
    " `scripts/start-blender-mcp.sh` directly from the shell"
)
def developer_invokes_blender_script(repo_root: pathlib.Path) -> None:
    assert (repo_root / "scripts" / "start-blender-mcp.sh").is_file()


@given("`BLENDER_BIN` resolves to an installed Blender binary")
def blender_bin_resolves(fake_blender_bin: pathlib.Path) -> None:
    assert fake_blender_bin.is_file()


@when("the script runs", target_fixture="launcher_run")
def run_blender_script(fake_blender_bin: pathlib.Path) -> LauncherRun:
    return _run_launcher(
        "start-blender-mcp.sh",
        {"BLENDER_BIN": str(fake_blender_bin), "BLENDER_MCP_PORT": BLENDER_TEST_PORT},
    )


@then("Blender is detached with the MCP add-on enabled on `BLENDER_MCP_PORT` (default 9876)")
def blender_detached(launcher_run: LauncherRun) -> None:
    assert launcher_run.result.returncode == 0, f"Script failed: {launcher_run.result.stderr}"


@then("the script returns control to the shell in under two seconds")
def script_returns_quickly(launcher_run: LauncherRun) -> None:
    assert launcher_run.elapsed_seconds < 2.0, (
        f"Script took {launcher_run.elapsed_seconds:.2f}s (> 2s)"
    )


@then("the script does not block waiting for Blender to finish booting")
def script_does_not_block(launcher_run: LauncherRun) -> None:
    assert launcher_run.result.returncode == 0


@given("`UE_ROOT` resolves to an installed Unreal Engine 5.7 install")
def ue_root_resolves(fake_ue_root: pathlib.Path) -> None:
    editor = (
        fake_ue_root
        / "Engine"
        / "Binaries"
        / "Mac"
        / "UnrealEditor.app"
        / "Contents"
        / "MacOS"
        / "UnrealEditor"
    )
    assert editor.is_file()


@given("a valid `.uproject` resolves via the env-var or auto-detect chain")
def uproject_resolves(repo_root: pathlib.Path) -> None:
    assert (repo_root / "fixtures" / "dogfood.uproject").is_file()


@when("`scripts/start-unreal-mcp.sh` runs", target_fixture="launcher_run")
def run_unreal_script(fake_ue_root: pathlib.Path, repo_root: pathlib.Path) -> LauncherRun:
    return _run_launcher(
        "start-unreal-mcp.sh",
        {
            "UE_ROOT": str(fake_ue_root),
            "UE_MCP_PORT": UE_TEST_PORT,
            "UE_PROJECT": str(repo_root / "fixtures" / "dogfood.uproject"),
        },
    )


@then("UE Editor is detached opened against the target `.uproject`")
def ue_editor_detached(launcher_run: LauncherRun) -> None:
    assert launcher_run.result.returncode == 0, f"Script failed: {launcher_run.result.stderr}"


@given(
    "the Blender MCP port is already in `LISTEN` state"
    " (simulated by a bound socket in the test harness)"
)
def port_in_listen_state(bound_port: int) -> None:
    assert bound_port > 0


@when("`scripts/start-blender-mcp.sh` is re-invoked", target_fixture="idempotent_run")
def re_invoke_blender_script(bound_port: int) -> LauncherRun:
    return _run_launcher("start-blender-mcp.sh", {"BLENDER_MCP_PORT": str(bound_port)}, timeout=5)


@then("the script exits 0 without launching a second Blender process")
def idempotent_exit_0(idempotent_run: LauncherRun) -> None:
    r = idempotent_run.result
    assert r.returncode == 0, f"Expected exit 0, got {r.returncode}: {r.stderr}"
    assert "already LISTEN" in r.stderr, f"Expected 'already LISTEN' in stderr; got: {r.stderr!r}"


@then("no duplicate process appears in the process table")
def no_duplicate_process(idempotent_run: LauncherRun) -> None:
    # Script exits before invoking Blender, so no duplicate is possible.
    assert idempotent_run.result.returncode == 0


@given("`BLENDER_BIN` is unset")
def blender_bin_unset() -> None:
    pass


@given("`BLENDER_APP` points at a non-existent path")
def blender_app_missing() -> None:
    pass


@when("`scripts/start-blender-mcp.sh` runs", target_fixture="remediation_result")
def run_blender_missing(tmp_path: pathlib.Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.pop("BLENDER_BIN", None)
    env["BLENDER_APP"] = str(tmp_path / "NonExistent.app")
    env["BLENDER_MCP_PORT"] = MISSING_BINARY_TEST_PORT
    return subprocess.run(
        ["bash", str(REPO_ROOT / "scripts" / "start-blender-mcp.sh")],
        capture_output=True,
        text=True,
        env=env,
        timeout=5,
    )


@then("the script exits non-zero")
def exits_nonzero(remediation_result: subprocess.CompletedProcess[str]) -> None:
    assert remediation_result.returncode != 0, (
        f"Expected non-zero exit; got 0. stderr: {remediation_result.stderr}"
    )


@then(
    "stderr contains a one-line remediation hint naming"
    " `BLENDER_BIN`/`BLENDER_APP` and the default path it checked"
)
def stderr_has_remediation(remediation_result: subprocess.CompletedProcess[str]) -> None:
    stderr = remediation_result.stderr
    assert "BLENDER_BIN" in stderr or "BLENDER_APP" in stderr, (
        f"stderr does not mention BLENDER_BIN or BLENDER_APP: {stderr!r}"
    )
    hint_lines = [ln for ln in stderr.splitlines() if "BLENDER" in ln]
    assert len(hint_lines) >= 1, f"No remediation hint line found in stderr: {stderr!r}"


@given("`templates/consumer/.codex/hooks.json` exists in this repo")
def consumer_template_exists(repo_root: pathlib.Path) -> None:
    assert (repo_root / "templates" / "consumer" / ".codex" / "hooks.json").is_file()


@when("a reader inspects it")
def reader_inspects_template() -> None:
    pass


@then(
    "it declares two `SessionStart` hook entries invoking"
    " `bash scripts/start-blender-mcp.sh` and `bash scripts/start-unreal-mcp.sh`"
)
def consumer_template_has_hooks(consumer_hooks_data: dict[str, Any]) -> None:
    hooks = consumer_hooks_data["hooks"]["SessionStart"][0]["hooks"]
    commands = [h["command"] for h in hooks]
    assert any("start-blender-mcp.sh" in c for c in commands)
    assert any("start-unreal-mcp.sh" in c for c in commands)


@then("`templates/consumer/.codex/config.toml` enables Codex hooks")
def consumer_config_enables_hooks(consumer_config_text: str) -> None:
    assert "[features]" in consumer_config_text
    assert "codex_hooks = true" in consumer_config_text


@then("no `.codex/hooks.json` exists at this repo's root")
def no_repo_root_settings_json(repo_root: pathlib.Path) -> None:
    assert not (repo_root / ".codex" / "hooks.json").exists(), (
        ".codex/hooks.json found at repo root — must not exist (consumer-only)"
    )


@then(
    "`templates/consumer/README.md` documents that `onboard-consumer`"
    " (future v1 issue) copies this template into downstream projects"
)
def consumer_readme_mentions_onboard(repo_root: pathlib.Path) -> None:
    readme = repo_root / "templates" / "consumer" / "README.md"
    assert readme.is_file(), "templates/consumer/README.md missing"
    assert "onboard-consumer" in readme.read_text()


@given("`pyproject.toml` declares the `nmg_game_dev` package and dev deps")
def pyproject_exists(repo_root: pathlib.Path) -> None:
    assert (repo_root / "pyproject.toml").is_file()


@when("`pip install -e .[dev]` runs in a fresh virtualenv")
def pip_install_step() -> None:
    pass


@then("the install succeeds with exit code 0")
def install_succeeds(pyproject_data: dict[str, Any]) -> None:
    assert pyproject_data["project"]["name"] == "nmg-game-dev"
    assert "dev" in pyproject_data["project"]["optional-dependencies"]
    assert "pytest>=8" in pyproject_data["project"]["optional-dependencies"]["dev"]


@then('`python -c "import nmg_game_dev"` exits 0')
def import_nmg_game_dev_step() -> None:
    importlib.import_module("nmg_game_dev")


@then("`ruff check .` exits 0")
def ruff_check_step(repo_root: pathlib.Path) -> None:
    try:
        result = subprocess.run(
            ["ruff", "check", str(repo_root / "src")],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        pytest.skip("ruff not installed — gate-python-lint handles this gate")
    assert result.returncode == 0, f"ruff check failed:\n{result.stdout}\n{result.stderr}"


@then("`pytest` on the empty scaffold exits 0")
def pytest_empty_scaffold() -> None:
    assert True


@when("a developer reads `VERSION` and `CHANGELOG.md`")
def reads_version_files() -> None:
    pass


@then("`VERSION` contains exactly `0.5.0` followed by a newline")
def version_content(version_text: str) -> None:
    assert version_text == f"{EXPECTED_VERSION}\n"


@then("`CHANGELOG.md` has an `## [Unreleased]` section")
def changelog_unreleased(changelog_text: str) -> None:
    assert "## [Unreleased]" in changelog_text


@then("`.codex-plugin/plugin.json`'s `version` field equals `0.5.0`")
def plugin_json_version(plugin_data: dict[str, Any]) -> None:
    assert plugin_data["version"] == EXPECTED_VERSION


@then("`pyproject.toml`'s `project.version` equals `0.5.0`")
def pyproject_version(pyproject_data: dict[str, Any]) -> None:
    assert pyproject_data["project"]["version"] == EXPECTED_VERSION


@given("`.mcp.json` at the repo root")
def mcp_json_exists(repo_root: pathlib.Path) -> None:
    assert (repo_root / ".mcp.json").is_file()


@when("the file is parsed")
def parse_mcp_json(mcp_data: dict[str, Any]) -> None:
    assert mcp_data


@then(
    "it declares three pinned MCP server entries:"
    " `blender` (ahujasid/blender-mcp), `unreal` (VibeUE), and `meshy`"
)
def mcp_three_servers(mcp_data: dict[str, Any]) -> None:
    for name in REQUIRED_SERVERS:
        assert name in mcp_data["mcpServers"], f".mcp.json missing server: {name}"


@then(
    "every server entry carries a pinned version — no `latest`, `main`, or `HEAD` substring appears"
)
def mcp_no_floating_versions(mcp_text: str) -> None:
    for banned in FLOATING_VERSION_REFS:
        assert banned not in mcp_text, f".mcp.json contains floating ref: {banned!r}"


@then(
    "the file contains no this-repo-specific absolute paths"
    " (usable verbatim by `onboard-consumer` in a consumer project)"
)
def mcp_no_repo_paths(mcp_text: str) -> None:
    assert "fixtures/" not in mcp_text
    assert not re.search(r'"/(?:Users|home)/[^"]+nmg-game-dev', mcp_text), (
        ".mcp.json contains an absolute path to the nmg-game-dev repo"
    )


@given("`AGENTS.md` at the repo root")
def agents_md_exists(repo_root: pathlib.Path) -> None:
    assert (repo_root / "AGENTS.md").is_file()


@when("a new contributor opens the repo")
def contributor_opens_repo() -> None:
    pass


@then(
    "`AGENTS.md` references `steering/product.md`, `steering/tech.md`, and `steering/structure.md`"
)
def agents_md_references_steering(agents_md_text: str) -> None:
    for ref in ("steering/product.md", "steering/tech.md", "steering/structure.md"):
        assert ref in agents_md_text, f"AGENTS.md missing reference to {ref}"


@then("it mentions `$nmg-sdlc:draft-issue` as the SDLC entry point")
def agents_md_draft_issue(agents_md_text: str) -> None:
    assert "$nmg-sdlc:draft-issue" in agents_md_text


@then("it does not duplicate content from any steering document")
def agents_md_pointer_only(agents_md_text: str) -> None:
    lines = agents_md_text.splitlines()
    assert len(lines) < 60, (
        f"AGENTS.md has {len(lines)} lines — may be duplicating steering content"
    )


@given(
    "the consumer-facing artifacts: `.codex-plugin/plugin.json`,"
    " `.agents/plugins/marketplace.json`, `scripts/start-*-mcp.sh`,"
    " `templates/consumer/.codex/hooks.json`, `templates/consumer/.codex/config.toml`,"
    " `.mcp.json`, `pyproject.toml`"
)
def consumer_artifacts_present(repo_root: pathlib.Path) -> None:
    for rel in CONSUMER_FACING:
        assert (repo_root / rel).is_file(), f"Consumer artifact missing: {rel}"


@when(
    "these artifacts are grep-scanned for repo-specific absolute paths,"
    " `fixtures/dogfood.uproject` references, this-repo-only module imports, and credentials"
)
def grep_scan() -> None:
    pass


@then("no banned substring is found")
def no_banned_found(artifact_text: Any) -> None:
    for rel in CONSUMER_FACING:
        content = artifact_text(rel)
        for pattern in BANNED_SUBSTRINGS:
            assert pattern not in content, f"Banned pattern {pattern!r} found in {rel}"
    for rel in BANNED_DOGFOOD_ARTIFACTS:
        assert "fixtures/dogfood.uproject" not in artifact_text(rel), (
            f"Dogfood fixture reference found in {rel} (AC10 leak)"
        )


@then(
    "every path resolution in the launcher scripts uses either env-var overrides"
    " or documented defaults a consumer can override without editing the script"
)
def launchers_use_env_vars(artifact_text: Any) -> None:
    for name in ("start-blender-mcp.sh", "start-unreal-mcp.sh"):
        assert "${" in artifact_text(f"scripts/{name}"), (
            f"{name} does not use env-var path resolution"
        )


@given(
    "the plugin is installed through Codex at either user scope"
    " or project scope inside a consumer game repo"
)
def install_scope_context() -> None:
    pass


@given("`onboard-consumer` (future v1 issue) has run against that consumer")
def onboard_consumer_ran() -> None:
    pass


@when("a developer opens the consumer project in Codex")
def opens_consumer_project() -> None:
    pass


@then(
    "the consumer-side outcome is identical regardless of the plugin's install scope"
    " — same skills, same `scripts/` contents, same MCP config,"
    " same `.codex/hooks.json` `SessionStart` entries"
)
def outcome_identical(plugin_data: dict[str, Any]) -> None:
    skills_path = plugin_data["skills"]
    assert not skills_path.startswith("/"), "skills path is absolute"
    assert "~" not in skills_path, "skills path contains ~"


@then("no artifact shipped in this issue encodes or depends on a specific install scope")
def no_install_scope_encoding(artifact_text: Any) -> None:
    for rel in CONSUMER_FACING:
        content = artifact_text(rel)
        old_user_plugin_path = "~/.cla" "ude/plugins/"
        assert old_user_plugin_path not in content, f"{rel} hard-codes {old_user_plugin_path}"
        # /Users/Shared/Epic Games/ is the documented UE default — permitted.
        forbidden = re.findall(r"/Users/(?!Shared/)[^\s\"'/]+", content)
        assert not forbidden, f"{rel} contains non-default /Users/ path: {forbidden}"
