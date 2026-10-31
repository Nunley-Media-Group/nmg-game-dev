"""pytest-bdd bindings for onboard_consumer.feature: SCN001–SCN011 (#7).

Each scenario runs the real onboarding package against a fixture consumer, with stub commands from
``tests/onboard_fakes.py``. No real git, mflux-save, or uv runs.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.onboard import OnboardError, list_volumes, run_onboard
from nmg_game_dev.onboard.paths import framework_root
from tests.onboard_fakes import (
    APPLE_SILICON,
    GIB,
    REPO_ROOT,
    FakeRunner,
    all_tools_present,
    gib_free,
    make_consumer,
    make_framework,
    small_disk,
    snapshot,
)

FEATURE = "onboard_consumer.feature"
HOOK_COMMANDS = (
    'bash "$CLAUDE_PROJECT_DIR/scripts/start-blender-mcp.sh"',
    'bash "$CLAUDE_PROJECT_DIR/scripts/start-unreal-mcp.sh"',
)


def _context(
    tmp_path: Path, framework: Path, consumer: Path, free: Callable[[Path], int] = gib_free
) -> dict[str, Any]:
    volume = tmp_path / "volume"
    extensions = tmp_path / "ext" / "user_default"
    return {
        "tmp": tmp_path,
        "framework": framework,
        "consumer": consumer,
        "models": volume / "nmg-texture-models",
        "extensions": extensions,
        "env": {
            "BLENDER_EXTENSIONS_DIR": str(extensions),
            "TEXTURE_GEN_MODELS_DIR": str(volume / "nmg-texture-models"),
        },
        "runner": FakeRunner(),
        "host": APPLE_SILICON,
        "free": free,
        "error": None,
        "results": [],
        "before": None,
    }


def _install(ctx: dict[str, Any], *, refresh: bool = False) -> None:
    try:
        ctx["results"] = run_onboard(
            ctx["consumer"],
            framework=ctx["framework"],
            models_dir=ctx["models"],
            refresh=refresh,
            env=ctx["env"],
            run=ctx["runner"],
            which=all_tools_present,
            host=ctx["host"],
            free_bytes=ctx["free"],
        )
        ctx["error"] = None
    except OnboardError as error:
        ctx["error"] = error


def _fresh(tmp_path: Path, free: Callable[[Path], int] = gib_free) -> dict[str, Any]:
    framework = make_framework(tmp_path / "framework")
    consumer = make_consumer(tmp_path)
    return _context(tmp_path, framework, consumer, free=free)


# --- SCN001 ------------------------------


@scenario(FEATURE, "Fresh onboarding installs the framework files")
def test_fresh_onboarding_installs_framework_files() -> None:
    """AC1: scripts, hooks, asset contract, CLAUDE.md block, and the exclusions."""


@given(
    "a consumer with Game.uproject, unrelated Claude settings, and a CLAUDE.md",
    target_fixture="ctx",
)
def _consumer_with_settings(tmp_path: Path) -> dict[str, Any]:
    return _fresh(tmp_path)


@when("onboarding installs into the consumer")
def _onboard(ctx: dict[str, Any]) -> None:
    _install(ctx)


@then("both start scripts are in the consumer scripts folder and executable")
def _scripts_executable(ctx: dict[str, Any]) -> None:
    for script in ("start-blender-mcp.sh", "start-unreal-mcp.sh"):
        path = ctx["consumer"] / "scripts" / script
        assert path.is_file() and os.access(path, os.X_OK), script


@then("the SessionStart hooks are merged and the unrelated settings are unchanged")
def _hooks_merged(ctx: dict[str, Any]) -> None:
    settings = json.loads((ctx["consumer"] / ".claude" / "settings.json").read_text())
    assert settings["model"] == "opus"
    assert settings["permissions"] == {"allow": ["Bash(ls)"]}
    commands = [h["command"] for g in settings["hooks"]["SessionStart"] for h in g["hooks"]]
    assert commands == list(HOOK_COMMANDS)


@then("the asset contract is installed and CLAUDE.md references it once")
def _contract_referenced(ctx: dict[str, Any]) -> None:
    contract = ctx["consumer"] / "docs" / "nmg-game-dev" / "asset-contract.md"
    assert contract.read_bytes() == (REPO_ROOT / "docs" / "asset-contract.md").read_bytes()
    claude_md = (ctx["consumer"] / "CLAUDE.md").read_text()
    assert claude_md.count("docs/nmg-game-dev/asset-contract.md") == 1
    assert claude_md.count("<!-- nmg-game-dev:begin -->") == 1


@then("no .mcp.json, fixtures file, or _API_KEY variable is written")
def _nothing_excluded(ctx: dict[str, Any]) -> None:
    consumer = ctx["consumer"]
    assert not (consumer / ".mcp.json").exists()
    assert not (consumer / "fixtures").exists()
    local = json.loads((consumer / ".claude" / "settings.local.json").read_text())
    assert not [key for key in local["env"] if key.endswith("_API_KEY")]


# --- SCN002 ------------------------------


@scenario(FEATURE, "Unreal plugins are installed and enabled")
def test_unreal_plugins_installed_and_enabled() -> None:
    """AC2: UE plugin copy, pinned VibeUE clone, .uproject plugins, and MCP auto-start."""


@given("a consumer with Game.uproject and git available", target_fixture="ctx")
def _consumer_with_git(tmp_path: Path) -> dict[str, Any]:
    return _fresh(tmp_path)


@then("the nmg-game-dev UE plugin is in Plugins/nmg-game-dev")
def _ue_plugin_present(ctx: dict[str, Any]) -> None:
    assert (ctx["consumer"] / "Plugins" / "nmg-game-dev" / "nmg-game-dev.uplugin").is_file()


@then("VibeUE is cloned at tag v5.0-ue5.8 into Plugins/VibeUE")
def _vibeue_cloned(ctx: dict[str, Any]) -> None:
    clones = ctx["runner"].argv_starting("git", "clone")
    assert len(clones) == 1
    assert "v5.0-ue5.8" in clones[0]
    assert clones[0][-1] == str(ctx["consumer"] / "Plugins" / "VibeUE")


@then("Game.uproject enables ModelContextProtocol, EditorToolset, VibeUE, and nmg-game-dev")
def _uproject_enabled(ctx: dict[str, Any]) -> None:
    uproject = json.loads((ctx["consumer"] / "Game.uproject").read_text())
    enabled = {entry["Name"] for entry in uproject["Plugins"] if entry["Enabled"]}
    assert {"ModelContextProtocol", "EditorToolset", "VibeUE", "nmg-game-dev"} <= enabled


@then("the MCP settings section has bAutoStartServer=True and ServerPortNumber=8000")
def _mcp_section(ctx: dict[str, Any]) -> None:
    ini = (ctx["consumer"] / "Config" / "DefaultEditorPerProjectUserSettings.ini").read_text()
    assert "bAutoStartServer=True" in ini
    assert "ServerPortNumber=8000" in ini


# --- SCN003 ------------------------------


@scenario(FEATURE, "The Blender add-on is linked into Blender's extensions")
def test_blender_addon_linked() -> None:
    """AC3: the extensions folder holds a symlink to the framework add-on."""


@given("BLENDER_EXTENSIONS_DIR points at an empty directory", target_fixture="ctx")
def _empty_extensions(tmp_path: Path) -> dict[str, Any]:
    ctx = _fresh(tmp_path)
    ctx["extensions"].mkdir(parents=True)
    return ctx


@then("nmg_game_dev_blender_addon in that directory links to the framework add-on")
def _blender_linked(ctx: dict[str, Any]) -> None:
    link = ctx["extensions"] / "nmg_game_dev_blender_addon"
    assert link.is_symlink()
    assert Path(os.readlink(link)) == ctx["framework"] / "plugins" / "nmg-game-dev-blender-addon"


# --- SCN004 ------------------------------


@scenario(FEATURE, "Local texture models are installed on the chosen disk")
def test_texture_models_installed() -> None:
    """AC4: mflux-save runs for both models on the chosen disk; settings.local records them."""


@given(
    "a models directory on a volume with 60 GiB free on Apple Silicon macOS", target_fixture="ctx"
)
def _sixty_gib(tmp_path: Path) -> dict[str, Any]:
    return _fresh(tmp_path, free=lambda _path: 60 * GIB)


@then(
    "mflux-save saves z-image-turbo and then flux2-klein-4b with --quantize 4 "
    "into the models directory"
)
def _mflux_saves(ctx: dict[str, Any]) -> None:
    saves = ctx["runner"].argv_starting("mflux-save")
    assert [s[s.index("--model") + 1] for s in saves] == ["z-image-turbo", "flux2-klein-4b"]
    assert all(s[s.index("--quantize") + 1] == "4" for s in saves)
    assert all(str(ctx["models"]) in s[s.index("--path") + 1] for s in saves)


@then("HF_HOME is the hf-cache folder in the models directory")
def _hf_home(ctx: dict[str, Any]) -> None:
    saves = [
        env
        for call, env in zip(ctx["runner"].calls, ctx["runner"].envs, strict=True)
        if call[:1] == ["mflux-save"]
    ]
    assert saves and all(env == {"HF_HOME": str(ctx["models"] / "hf-cache")} for env in saves)


@then("settings.local.json records TEXTURE_GEN_MODELS_DIR and HF_HOME")
def _settings_local(ctx: dict[str, Any]) -> None:
    env = json.loads((ctx["consumer"] / ".claude" / "settings.local.json").read_text())["env"]
    assert env["TEXTURE_GEN_MODELS_DIR"] == str(ctx["models"])
    assert env["HF_HOME"] == str(ctx["models"] / "hf-cache")


# --- SCN005 ------------------------------


@scenario(FEATURE, "Texture prerequisites fail before anything changes")
def test_prerequisites_fail_before_changes() -> None:
    """AC5: a volume under 60 GiB stops onboarding before any consumer file changes."""


@given("a models directory on a volume with 10 GiB free", target_fixture="ctx")
def _ten_gib(tmp_path: Path) -> dict[str, Any]:
    ctx = _fresh(tmp_path, free=small_disk)
    ctx["before"] = snapshot(ctx["consumer"])
    return ctx


@then(parsers.parse('it exits 1 with code "{code}" and a remediation'))
def _exit_one(ctx: dict[str, Any], code: str) -> None:
    assert ctx["error"] is not None, "onboarding did not fail"
    assert ctx["error"].code == code
    assert ctx["error"].remediation


@then("no consumer file was created or changed")
def _unchanged(ctx: dict[str, Any]) -> None:
    assert snapshot(ctx["consumer"]) == ctx["before"]


# --- SCN006 ------------------------------


@scenario(FEATURE, "The skill asks which disk to use")
def test_skill_asks_which_disk() -> None:
    """AC6: volumes lists free bytes and fit; the skill asks the developer to choose."""


@given("mounted volumes with different free space", target_fixture="ctx")
def _mounted(tmp_path: Path) -> dict[str, Any]:
    ctx = _fresh(tmp_path)
    big = tmp_path / "Big"
    small = tmp_path / "Small"
    big.mkdir()
    small.mkdir()
    free = {big: 200 * GIB, small: 10 * GIB}
    ctx["mounts"] = (big, small)
    ctx["free_map"] = free
    return ctx


@when("the volumes command runs")
def _volumes(ctx: dict[str, Any]) -> None:
    ctx["volumes"] = list_volumes(
        free_bytes=lambda p: ctx["free_map"][p], mounts=lambda: list(ctx["mounts"])
    )


@then("it lists each volume with free bytes and whether it fits the models")
def _lists_volumes(ctx: dict[str, Any]) -> None:
    rows = {row["mount"]: row for row in ctx["volumes"]}
    assert rows[str(ctx["mounts"][0])] == {
        "mount": str(ctx["mounts"][0]),
        "free_bytes": 200 * GIB,
        "fits_models": True,
    }
    assert rows[str(ctx["mounts"][1])]["fits_models"] is False


@then("the onboard-consumer skill asks the developer to choose a qualifying volume")
def _skill_asks(ctx: dict[str, Any]) -> None:
    text = (REPO_ROOT / "skills" / "onboard-consumer" / "SKILL.md").read_text()
    assert "AskUserQuestion" in text and "qualifying" in text


# --- SCN007 ------------------------------


@scenario(FEATURE, "Install scope does not change the result")
def test_install_scope_does_not_change_result() -> None:
    """AC7: two framework copies onboard identical consumers to the same tree."""


@given("two copies of the framework root in different directories", target_fixture="ctx")
def _two_scopes(tmp_path: Path) -> dict[str, Any]:
    shared_models = tmp_path / "shared-volume" / "nmg-texture-models"
    scopes = {}
    for scope in ("user-scope", "project-scope"):
        framework = make_framework(tmp_path / scope / "framework")
        consumer = make_consumer(tmp_path / scope)
        ctx = _context(tmp_path / scope, framework, consumer)
        ctx["models"] = shared_models
        ctx["env"] = {**ctx["env"], "TEXTURE_GEN_MODELS_DIR": str(shared_models)}
        scopes[scope] = ctx
    return {"scopes": scopes}


@when("each onboards an identical fresh consumer")
def _each_onboards(ctx: dict[str, Any]) -> None:
    for scope in ctx["scopes"].values():
        _install(scope)
        assert scope["error"] is None


@then("the consumer trees are identical apart from the Blender link target")
def _trees_match(ctx: dict[str, Any]) -> None:
    user, project = ctx["scopes"]["user-scope"], ctx["scopes"]["project-scope"]
    assert snapshot(user["consumer"]) == snapshot(project["consumer"])
    assert os.readlink(user["extensions"] / "nmg_game_dev_blender_addon") != os.readlink(
        project["extensions"] / "nmg_game_dev_blender_addon"
    )
    assert (
        framework_root({"CLAUDE_PLUGIN_ROOT": str(user["framework"])})
        == user["framework"].resolve()
    )


# --- SCN008 ------------------------------


@scenario(FEATURE, "Re-running is idempotent")
def test_rerun_is_idempotent() -> None:
    """AC8: a second run duplicates nothing, runs no clone or mflux-save, and exits 0."""


@given("a consumer that has already been onboarded", target_fixture="ctx")
def _already_onboarded(tmp_path: Path) -> dict[str, Any]:
    ctx = _fresh(tmp_path)
    _install(ctx)
    assert ctx["error"] is None
    ctx["runner"] = FakeRunner()
    return ctx


@when("onboarding installs into the consumer again")
def _again(ctx: dict[str, Any]) -> None:
    _install(ctx)


@then("no hook, plugin entry, ini key, or CLAUDE.md block is duplicated")
def _no_duplicates(ctx: dict[str, Any]) -> None:
    settings = json.loads((ctx["consumer"] / ".claude" / "settings.json").read_text())
    assert len(settings["hooks"]["SessionStart"]) == 1
    uproject = json.loads((ctx["consumer"] / "Game.uproject").read_text())
    assert [e["Name"] for e in uproject["Plugins"]].count("VibeUE") == 1
    ini = (ctx["consumer"] / "Config" / "DefaultEditorPerProjectUserSettings.ini").read_text()
    assert ini.count("ServerPortNumber=") == 1
    assert (ctx["consumer"] / "CLAUDE.md").read_text().count("<!-- nmg-game-dev:begin -->") == 1


@then("no git clone or mflux-save runs and the command exits 0")
def _no_clone(ctx: dict[str, Any]) -> None:
    assert ctx["error"] is None
    assert ctx["runner"].argv_starting("git", "clone") == []
    assert ctx["runner"].argv_starting("mflux-save") == []


# --- SCN009 ------------------------------


@scenario(FEATURE, "Drift is reported and --refresh repairs it")
def test_drift_reported_and_refreshed() -> None:
    """AC9: drift is reported with its remediation and left; --refresh restores it; budgets stay."""


@given(
    "an onboarded consumer with an edited start-blender-mcp.sh and an nmg-budgets.json",
    target_fixture="ctx",
)
def _edited(tmp_path: Path) -> dict[str, Any]:
    ctx = _fresh(tmp_path)
    _install(ctx)
    (ctx["consumer"] / "scripts" / "start-blender-mcp.sh").write_text(
        "#!/usr/bin/env bash\necho edited\n"
    )
    (ctx["consumer"] / "nmg-budgets.json").write_text('{"Hero": {"tris": 60000}}\n')
    ctx["budgets_before"] = (ctx["consumer"] / "nmg-budgets.json").read_bytes()
    return ctx


@then(
    'start-blender-mcp.sh is reported as drift with a "re-run with --refresh" remediation '
    "and left unchanged"
)
def _drift_reported(ctx: dict[str, Any]) -> None:
    drifted = [
        r
        for r in ctx["results"]
        if r.status == "drift" and r.name == "scripts/start-blender-mcp.sh"
    ]
    assert drifted and drifted[0].remediation == "re-run with --refresh"
    assert (
        ctx["consumer"] / "scripts" / "start-blender-mcp.sh"
    ).read_text() == "#!/usr/bin/env bash\necho edited\n"


@when("onboarding installs into the consumer with --refresh")
def _refresh(ctx: dict[str, Any]) -> None:
    _install(ctx, refresh=True)


@then("start-blender-mcp.sh matches the framework copy")
def _restored(ctx: dict[str, Any]) -> None:
    assert (ctx["consumer"] / "scripts" / "start-blender-mcp.sh").read_bytes() == (
        ctx["framework"] / "scripts" / "start-blender-mcp.sh"
    ).read_bytes()


@then("nmg-budgets.json is unchanged")
def _budgets_unchanged(ctx: dict[str, Any]) -> None:
    assert (ctx["consumer"] / "nmg-budgets.json").read_bytes() == ctx["budgets_before"]


# --- SCN010 ------------------------------


@scenario(FEATURE, "Onboarding docs exist and are linked")
def test_docs_exist_and_are_linked() -> None:
    """AC10: the onboarding index links the four guides; CLAUDE.md and README.md link the index."""


@given("the repository", target_fixture="ctx")
def _repository(tmp_path: Path) -> dict[str, Any]:
    return {"repo": REPO_ROOT}


@when("docs/onboarding is read")
def _read_docs(ctx: dict[str, Any]) -> None:
    ctx["index"] = (ctx["repo"] / "docs" / "onboarding" / "index.md").read_text()


@then("index.md links to first-asset.md, first-ship.md, upgrading.md, and texture-models.md")
def _index_links(ctx: dict[str, Any]) -> None:
    for guide in ("first-asset.md", "first-ship.md", "upgrading.md", "texture-models.md"):
        assert f"({guide})" in ctx["index"], guide


@then("CLAUDE.md and README.md link to docs/onboarding/index.md")
def _root_links(ctx: dict[str, Any]) -> None:
    for name in ("CLAUDE.md", "README.md"):
        assert "docs/onboarding/index.md" in (ctx["repo"] / name).read_text(), name


# --- SCN011 ------------------------------


@scenario(FEATURE, "The onboard-consumer skill is the entry point")
def test_skill_is_the_entry_point() -> None:
    """AC11: the skill frontmatter and flow point at the install command."""


@given("the plugin checkout", target_fixture="ctx")
def _plugin_checkout(tmp_path: Path) -> dict[str, Any]:
    return {"skill": REPO_ROOT / "skills" / "onboard-consumer" / "SKILL.md"}


@when("skills/onboard-consumer/SKILL.md is parsed")
def _parse_skill(ctx: dict[str, Any]) -> None:
    ctx["text"] = ctx["skill"].read_text()


@then(
    'its frontmatter has name "onboard-consumer", a description, required_mcp, required_env, '
    "and unattended_safe true"
)
def _frontmatter(ctx: dict[str, Any]) -> None:
    text = ctx["text"]
    assert "name: onboard-consumer" in text
    assert "description:" in text and "required_mcp: []" in text and "required_env:" in text
    assert "unattended_safe: true" in text


@then('its flow runs "python -m nmg_game_dev.onboard install"')
def _flow(ctx: dict[str, Any]) -> None:
    assert "python -m nmg_game_dev.onboard install" in ctx["text"]
