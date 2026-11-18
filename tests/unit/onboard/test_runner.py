"""End-to-end onboarding of a fixture consumer: #7 AC1–AC9, #249 AC10, the CLI, and the preflight
guarantees."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from nmg_game_dev.godot.presets import render_export_presets
from nmg_game_dev.godot.project import read_config
from nmg_game_dev.onboard import OnboardError, run_onboard
from nmg_game_dev.onboard.__main__ import main as onboard_main
from nmg_game_dev.onboard.commands import HostFacts
from nmg_game_dev.onboard.paths import framework_root
from nmg_game_dev.onboard.report import StepResult
from tests.onboard_fakes import (
    APPLE_SILICON,
    GODOT_ADDON_FILES,
    FakeRunner,
    all_tools_present,
    gib_free,
    make_consumer,
    make_executable,
    make_framework,
    mflux_missing,
    no_godot_tools,
    small_disk,
    snapshot,
)

HOOK_COMMANDS = ('bash "$CLAUDE_PROJECT_DIR/scripts/start-blender-mcp.sh"',)
STEP_ORDER = [
    "scripts/start-blender-mcp.sh",
    "settings_hooks",
    "asset_contract",
    "design_contract",
    "design_dir",
    "agent_instructions:CLAUDE.md",
    "godot_project",
    "godot_addon",
    "export_presets",
    "godot_binary",
    "ffmpeg_binary",
    "blender_addon",
    "texture_models",
    "texture_env",
    "gitignore_env",
    "gitattributes_lfs",
    "git_lfs_hooks",
]
DESIGN_CONTRACT_TEXT = "# Design contract\n\nFixture copy for the onboarding tests.\n"


def _framework_tree(root: Path) -> Path:
    """The shared fake framework plus a design contract, which onboarding now requires (#112)."""
    framework = make_framework(root)
    (framework / "docs" / "design-contract.md").write_text(DESIGN_CONTRACT_TEXT, encoding="utf-8")
    return framework


@pytest.fixture
def framework(tmp_path: Path) -> Path:
    return _framework_tree(tmp_path / "framework")


def install(
    consumer: Path,
    framework: Path,
    models: Path,
    env: dict[str, str],
    *,
    runner: FakeRunner | None = None,
    refresh: bool = False,
    free: Callable[[Path], int] = gib_free,
    which: Callable[[str], str | None] = all_tools_present,
    host: HostFacts = APPLE_SILICON,
    game_dir: str = "game",
    godot_app: Path | None = None,
) -> list[StepResult]:
    return run_onboard(
        consumer,
        framework=framework,
        game_dir=game_dir,
        models_dir=models,
        refresh=refresh,
        env=env,
        run=runner or FakeRunner(),
        which=which,
        host=host,
        free_bytes=free,
        godot_app=godot_app or consumer.parent / "no-godot-app",
    )


def test_fresh_install_installs_framework_files(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC1: scripts, hooks, asset contract, and the CLAUDE.md block; no .mcp.json, fixtures, or
    API keys."""
    results = install(consumer, framework, models, env)

    installed = consumer / "scripts" / "start-blender-mcp.sh"
    assert installed.read_bytes() == (framework / "scripts" / "start-blender-mcp.sh").read_bytes()
    assert os.access(installed, os.X_OK)
    assert sorted(path.name for path in (consumer / "scripts").iterdir()) == [
        "start-blender-mcp.sh"
    ]

    settings = json.loads((consumer / ".claude" / "settings.json").read_text())
    assert settings["model"] == "opus"
    assert settings["permissions"] == {"allow": ["Bash(ls)"]}
    commands = [
        hook["command"] for group in settings["hooks"]["SessionStart"] for hook in group["hooks"]
    ]
    assert commands == list(HOOK_COMMANDS)

    contract = consumer / "docs" / "nmg-game-dev" / "asset-contract.md"
    assert contract.read_bytes() == (framework / "docs" / "asset-contract.md").read_bytes()
    claude_md = (consumer / "CLAUDE.md").read_text()
    assert claude_md.count("<!-- nmg-game-dev:begin -->") == 1
    assert "docs/nmg-game-dev/asset-contract.md" in claude_md
    assert claude_md.startswith("# Game")

    assert not (consumer / ".mcp.json").exists()
    assert not (consumer / "fixtures").exists()
    assert not (consumer / "Plugins").exists()
    local = json.loads((consumer / ".claude" / "settings.local.json").read_text())
    assert not [key for key in local["env"] if key.endswith("_API_KEY")]
    assert {r.name for r in results} >= {
        "settings_hooks",
        "asset_contract",
        "design_contract",
        "design_dir",
        "texture_env",
        "gitignore_env",
        "gitattributes_lfs",
        "git_lfs_hooks",
    }
    ignore = (consumer / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ignore.count(".env") == 1
    assert ignore.count("game/.godot/") == 1
    assert not (consumer / ".env").exists(), "onboarding must never create the project .env"


def test_steps_run_in_design_order(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """#249 design: the Godot steps sit between the agent instructions and the Blender add-on."""
    assert [r.name for r in install(consumer, framework, models, env)] == STEP_ORDER


def test_godot_project_is_created_with_compatibility_renderer(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC10: game/project.godot gets the name, renderer keys, editor plugin, and autoload."""
    results = {r.name: r for r in install(consumer, framework, models, env)}
    assert results["godot_project"].status == "installed"
    config = read_config(consumer / "game" / "project.godot")
    assert config[("", "config_version")] == "5"
    assert config[("application", "config/name")] == '"Game"'
    assert config[("rendering", "renderer/rendering_method.mobile")] == '"gl_compatibility"'
    assert config[("rendering", "renderer/rendering_method.web")] == '"gl_compatibility"'
    assert config[("editor_plugins", "enabled")] == (
        'PackedStringArray("res://addons/nmg_game_dev/plugin.cfg")'
    )
    assert config[("autoload", "NmgAssets")] == '"*res://addons/nmg_game_dev/nmg_assets.gd"'


def test_godot_addon_is_copied_without_its_tests(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC10: the add-on lands in game/addons/nmg_game_dev; its tests/ folder stays behind."""
    results = {r.name: r for r in install(consumer, framework, models, env)}
    assert results["godot_addon"].status == "installed"
    addon = consumer / "game" / "addons" / "nmg_game_dev"
    expected = sorted(rel for rel in GODOT_ADDON_FILES if not rel.startswith("tests/"))
    assert sorted(str(p.relative_to(addon)) for p in addon.rglob("*") if p.is_file()) == expected
    assert not (addon / "tests").exists()


def test_export_presets_carry_variant_filters(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC10: desktop presets exclude Mobile/ folders; mobile and web presets exclude Desktop/."""
    install(consumer, framework, models, env)
    presets = consumer / "game" / "export_presets.cfg"
    assert presets.read_text(encoding="utf-8") == render_export_presets("Game")
    config = read_config(presets)
    filters = {
        config[(section, "name")]: config[(section, "exclude_filter")]
        for (section, key) in config
        if key == "name"
    }
    assert filters == {
        '"macOS"': '"assets/*/Mobile/*"',
        '"Windows Desktop"': '"assets/*/Mobile/*"',
        '"iOS"': '"assets/*/Desktop/*"',
        '"Android"': '"assets/*/Desktop/*"',
        '"Web"': '"assets/*/Desktop/*"',
    }


def test_existing_project_gets_missing_keys_and_keeps_its_own(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """FR10: an existing project.godot keeps its name and keys; missing keys are refreshed."""
    project = consumer / "game" / "project.godot"
    project.parent.mkdir()
    original = 'config_version=5\n\n[application]\n\nconfig/name="Hollow Peak"\nrun/x=1\n'
    project.write_text(original, encoding="utf-8")

    results = {r.name: r for r in install(consumer, framework, models, env)}

    assert results["godot_project"].status == "refreshed"
    text = project.read_text(encoding="utf-8")
    assert text.startswith(original)
    config = read_config(project)
    assert config[("application", "config/name")] == '"Hollow Peak"'
    assert config[("application", "run/x")] == "1"
    assert config[("autoload", "NmgAssets")] == '"*res://addons/nmg_game_dev/nmg_assets.gd"'
    presets = (consumer / "game" / "export_presets.cfg").read_text(encoding="utf-8")
    assert presets == render_export_presets("Hollow Peak")


def test_renderer_drift_is_reported_then_refreshed(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC10: a changed renderer key is drift and stays; --refresh restores it."""
    install(consumer, framework, models, env)
    project = consumer / "game" / "project.godot"
    edited = project.read_text(encoding="utf-8").replace(
        'rendering_method.mobile="gl_compatibility"', 'rendering_method.mobile="mobile"'
    )
    project.write_text(edited, encoding="utf-8")

    drifted = {r.name: r for r in install(consumer, framework, models, env)}
    assert drifted["godot_project"].status == "drift"
    assert "renderer/rendering_method.mobile" in drifted["godot_project"].detail
    assert drifted["godot_project"].remediation == "re-run with --refresh"
    assert project.read_text(encoding="utf-8") == edited

    refreshed = {r.name: r for r in install(consumer, framework, models, env, refresh=True)}
    assert refreshed["godot_project"].status == "refreshed"
    config = read_config(project)
    assert config[("rendering", "renderer/rendering_method.mobile")] == '"gl_compatibility"'
    again = {r.name: r for r in install(consumer, framework, models, env)}
    assert again["godot_project"].status == "unchanged"


def test_preset_drift_is_reported_then_refreshed(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC10: a changed export preset is drift and stays; --refresh rewrites the framework copy."""
    install(consumer, framework, models, env)
    presets = consumer / "game" / "export_presets.cfg"
    presets.write_text(presets.read_text(encoding="utf-8") + "\n; local\n", encoding="utf-8")
    edited = presets.read_bytes()

    drifted = {r.name: r for r in install(consumer, framework, models, env)}
    assert drifted["export_presets"].status == "drift"
    assert presets.read_bytes() == edited

    refreshed = {r.name: r for r in install(consumer, framework, models, env, refresh=True)}
    assert refreshed["export_presets"].status == "refreshed"
    assert presets.read_text(encoding="utf-8") == render_export_presets("Game")


def test_godot_and_ffmpeg_are_reported_found(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC10: a tool on PATH is unchanged with "found at <path>"."""
    results = {r.name: r for r in install(consumer, framework, models, env)}
    assert (results["godot_binary"].status, results["godot_binary"].detail) == (
        "unchanged",
        "found at /usr/bin/godot",
    )
    assert (results["ffmpeg_binary"].status, results["ffmpeg_binary"].detail) == (
        "unchanged",
        "found at /usr/bin/ffmpeg",
    )


def test_missing_godot_and_ffmpeg_are_skipped_with_remediation(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC10: missing tools are skipped with their remediation; the rest of the install runs."""
    results = {r.name: r for r in install(consumer, framework, models, env, which=no_godot_tools)}
    assert results["godot_binary"].status == "skipped"
    assert results["godot_binary"].remediation == "Install Godot 4 or set GODOT_BIN"
    assert results["ffmpeg_binary"].status == "skipped"
    assert results["ffmpeg_binary"].remediation == (
        "Install ffmpeg or set FFMPEG_BIN (needed to import music)"
    )
    assert results["git_lfs_hooks"].status == "skipped"


def test_tool_overrides_win_over_path(
    consumer: Path, framework: Path, models: Path, env: dict[str, str], tmp_path: Path
) -> None:
    """FR2/FR5: GODOT_BIN and FFMPEG_BIN, when executable, are what the report names."""
    godot = make_executable(tmp_path / "bin" / "Godot")
    ffmpeg = make_executable(tmp_path / "bin" / "ffmpeg")
    tool_env = {**env, "GODOT_BIN": str(godot), "FFMPEG_BIN": str(ffmpeg)}
    results = {
        r.name: r for r in install(consumer, framework, models, tool_env, which=no_godot_tools)
    }
    assert results["godot_binary"].detail == f"found at {godot}"
    assert results["ffmpeg_binary"].detail == f"found at {ffmpeg}"


def test_game_dir_option_moves_the_godot_project(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """--game-dir puts the project, add-on, presets, and cache ignore under that folder."""
    install(consumer, framework, models, env, game_dir="client")
    assert (consumer / "client" / "project.godot").is_file()
    assert (consumer / "client" / "addons" / "nmg_game_dev" / "plugin.cfg").is_file()
    assert (consumer / "client" / "export_presets.cfg").is_file()
    assert not (consumer / "game").exists()
    assert "client/.godot/" in (consumer / ".gitignore").read_text(encoding="utf-8").splitlines()


def test_game_dir_outside_the_consumer_fails_before_any_write(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    before = snapshot(consumer)
    with pytest.raises(OnboardError) as caught:
        install(consumer, framework, models, env, game_dir="../elsewhere")
    assert caught.value.code == "onboard.game_dir_invalid"
    assert snapshot(consumer) == before


def test_blender_addon_is_linked(
    consumer: Path, framework: Path, models: Path, env: dict[str, str], extensions: Path
) -> None:
    """AC3: the extensions folder holds a symlink to the framework add-on."""
    install(consumer, framework, models, env)

    link = extensions / "nmg_game_dev_blender_addon"
    assert link.is_symlink()
    assert Path(os.readlink(link)) == framework / "plugins" / "nmg-game-dev-blender-addon"


def test_texture_models_install_on_chosen_disk(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC4: mflux-save runs for both registry models in order, with HF_HOME, and settings.local
    records them."""
    runner = FakeRunner()
    install(consumer, framework, models, env, runner=runner)

    saves = runner.argv_starting("mflux-save")
    assert saves == [
        [
            "mflux-save",
            "--model",
            "z-image-turbo",
            "--quantize",
            "4",
            "--path",
            str(models / "z-image-turbo-q4"),
        ],
        [
            "mflux-save",
            "--model",
            "flux2-klein-4b",
            "--quantize",
            "4",
            "--path",
            str(models / "flux2-klein-4b-q4"),
        ],
    ]
    save_envs = [
        e for call, e in zip(runner.calls, runner.envs, strict=True) if call[:1] == ["mflux-save"]
    ]
    assert all(e == {"HF_HOME": str(models / "hf-cache")} for e in save_envs)
    local = json.loads((consumer / ".claude" / "settings.local.json").read_text())
    assert local["env"] == {
        "TEXTURE_GEN_MODELS_DIR": str(models),
        "HF_HOME": str(models / "hf-cache"),
    }


def test_existing_model_is_not_saved_again(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC4: a model whose <id>-q4 folder is already populated is skipped."""
    (models / "z-image-turbo-q4").mkdir(parents=True)
    (models / "z-image-turbo-q4" / "weights.safetensors").write_bytes(b"w")
    runner = FakeRunner()
    install(consumer, framework, models, env, runner=runner)

    saved = [call[call.index("--model") + 1] for call in runner.argv_starting("mflux-save")]
    assert saved == ["flux2-klein-4b"]


def test_mflux_installed_only_when_mflux_save_missing(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC4: `uv tool install mflux==0.24.0` runs first only when mflux-save is not on PATH."""
    runner = FakeRunner()
    install(consumer, framework, models, env, runner=runner, which=mflux_missing)
    assert runner.argv_starting("uv", "tool", "install") == [
        ["uv", "tool", "install", "mflux==0.24.0"]
    ]

    other = FakeRunner()
    install(consumer, framework, models, env, runner=other)
    assert other.argv_starting("uv") == []


def _run_preflight(
    consumer: Path,
    framework: Path,
    models_env: dict[str, str],
    *,
    models_dir: Path | None = None,
    host: HostFacts = APPLE_SILICON,
    free_bytes: Callable[[Path], int] = gib_free,
) -> list[StepResult]:
    return run_onboard(
        consumer,
        framework=framework,
        models_dir=models_dir,
        env=models_env,
        run=FakeRunner(),
        which=all_tools_present,
        host=host,
        free_bytes=free_bytes,
    )


def test_missing_models_dir_fails_before_any_write(
    consumer: Path, framework: Path, env: dict[str, str]
) -> None:
    """AC5: no --models-dir and no TEXTURE_GEN_MODELS_DIR raises onboard.models_dir_missing."""
    before = snapshot(consumer)
    no_models = {key: value for key, value in env.items() if key != "TEXTURE_GEN_MODELS_DIR"}
    with pytest.raises(OnboardError) as caught:
        _run_preflight(consumer, framework, no_models)
    assert caught.value.code == "onboard.models_dir_missing"
    assert caught.value.remediation
    assert snapshot(consumer) == before


def test_low_disk_fails_before_any_write(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC5: a volume under 60 GiB free with a missing model raises onboard.insufficient_disk."""
    before = snapshot(consumer)
    with pytest.raises(OnboardError) as caught:
        _run_preflight(consumer, framework, env, models_dir=models, free_bytes=small_disk)
    assert caught.value.code == "onboard.insufficient_disk"
    assert snapshot(consumer) == before


def test_non_apple_silicon_fails_before_any_write(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC5: a host that is not Apple Silicon macOS raises onboard.unsupported_platform."""
    before = snapshot(consumer)
    linux = HostFacts(system="Linux", machine="x86_64")
    with pytest.raises(OnboardError) as caught:
        _run_preflight(consumer, framework, env, models_dir=models, host=linux)
    assert caught.value.code == "onboard.unsupported_platform"
    assert snapshot(consumer) == before


def test_install_scope_does_not_change_result(
    tmp_path: Path, env: dict[str, str], models: Path, extensions: Path
) -> None:
    """AC7: two framework copies onboard identical consumers to identical trees."""
    trees = []
    for scope in ("user-scope", "project-scope"):
        framework = _framework_tree(tmp_path / scope / "framework")
        consumer_root = tmp_path / scope / "consumer"
        consumer_root.mkdir(parents=True)
        consumer = make_consumer(consumer_root)
        scope_env = {**env, "BLENDER_EXTENSIONS_DIR": str(tmp_path / scope / "ext")}
        install(consumer, framework, models, scope_env)
        link = tmp_path / scope / "ext" / "nmg_game_dev_blender_addon"
        trees.append((snapshot(consumer), os.readlink(link)))
    assert trees[0][0] == trees[1][0]
    assert trees[0][1] != trees[1][1]


def test_framework_root_prefers_plugin_root_env(tmp_path: Path) -> None:
    """AC7: CLAUDE_PLUGIN_ROOT wins; without it the package location is used."""
    assert framework_root({"CLAUDE_PLUGIN_ROOT": str(tmp_path)}) == tmp_path.resolve()
    fallback = framework_root({})
    assert (fallback / "src" / "nmg_game_dev" / "onboard").is_dir()


def test_rerun_is_a_no_op(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC8, #249 AC10: a second run duplicates nothing, runs no mflux-save, and leaves every
    file byte-identical."""
    install(consumer, framework, models, env)
    before = snapshot(consumer)
    runner = FakeRunner()
    results = install(consumer, framework, models, env, runner=runner)

    assert runner.argv_starting("mflux-save") == []
    # The fake consumer is not a git work tree, so git_lfs_hooks is the one step that is skipped.
    assert all(
        result.status == "unchanged"
        or (result.name == "git_lfs_hooks" and result.status == "skipped")
        for result in results
    ), [r.as_json() for r in results]
    settings = json.loads((consumer / ".claude" / "settings.json").read_text())
    assert len(settings["hooks"]["SessionStart"]) == 1
    assert (consumer / "CLAUDE.md").read_text().count("<!-- nmg-game-dev:begin -->") == 1
    assert snapshot(consumer) == before


def test_drift_is_reported_then_repaired_by_refresh(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC9: an edited script is drift and stays edited; --refresh restores it and keeps
    nmg-budgets.json."""
    install(consumer, framework, models, env)
    budgets = consumer / "nmg-budgets.json"
    budgets.write_text('{"Hero": {"tris": 60000}}\n')
    script = consumer / "scripts" / "start-blender-mcp.sh"
    script.write_text("#!/usr/bin/env bash\necho local edit\n")

    results = install(consumer, framework, models, env)
    drifted = [r for r in results if r.status == "drift"]
    assert [r.name for r in drifted] == ["scripts/start-blender-mcp.sh"]
    assert drifted[0].remediation == "re-run with --refresh"
    assert script.read_text() == "#!/usr/bin/env bash\necho local edit\n"
    assert budgets.read_text() == '{"Hero": {"tris": 60000}}\n'

    refreshed = install(consumer, framework, models, env, refresh=True)
    fixed = {r.name: r.status for r in refreshed}
    assert fixed["scripts/start-blender-mcp.sh"] == "refreshed"
    assert script.read_bytes() == (framework / "scripts" / "start-blender-mcp.sh").read_bytes()
    assert budgets.read_text() == '{"Hero": {"tris": 60000}}\n'


def test_design_contract_is_installed_and_unchanged_on_rerun(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC7: the design contract is copied beside the asset contract; a second run reports it
    unchanged."""
    first = install(consumer, framework, models, env)
    assert {r.name: r.status for r in first}["design_contract"] == "installed"
    copy = consumer / "docs" / "nmg-game-dev" / "design-contract.md"
    assert copy.read_bytes() == (framework / "docs" / "design-contract.md").read_bytes()

    second = install(consumer, framework, models, env)
    assert {r.name: r.status for r in second}["design_contract"] == "unchanged"


def test_design_contract_drift_is_reported_then_refreshed(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC7: an edited design contract copy is drift and stays edited; --refresh restores it."""
    install(consumer, framework, models, env)
    copy = consumer / "docs" / "nmg-game-dev" / "design-contract.md"
    copy.write_text("local edit\n", encoding="utf-8")

    drifted = {r.name: r for r in install(consumer, framework, models, env)}
    assert drifted["design_contract"].status == "drift"
    assert drifted["design_contract"].remediation == "re-run with --refresh"
    assert copy.read_text(encoding="utf-8") == "local edit\n"

    refreshed = install(consumer, framework, models, env, refresh=True)
    assert {r.name: r.status for r in refreshed}["design_contract"] == "refreshed"
    assert copy.read_bytes() == (framework / "docs" / "design-contract.md").read_bytes()


def test_design_dir_is_created_when_absent(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC7: docs/design/ is created empty on the first run and reported unchanged after."""
    design = consumer / "docs" / "design"
    assert not design.exists()

    first = install(consumer, framework, models, env)
    assert {r.name: r.status for r in first}["design_dir"] == "installed"
    assert design.is_dir() and not any(design.iterdir())

    second = install(consumer, framework, models, env)
    assert {r.name: r.status for r in second}["design_dir"] == "unchanged"


def test_existing_design_docs_are_untouched(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC7: design docs already in docs/design/ keep their exact bytes, and the step reports
    unchanged."""
    design = consumer / "docs" / "design"
    (design / "missions").mkdir(parents=True)
    (design / "hero.md").write_bytes(b"---\r\nname: Hero\r\n---\n\nNo trailing newline")
    (design / "missions" / "boss.md").write_text("# Boss\n", encoding="utf-8")
    before = snapshot(design)

    results = install(consumer, framework, models, env)

    assert {r.name: r.status for r in results}["design_dir"] == "unchanged"
    assert snapshot(design) == before


def test_missing_design_contract_fails_before_any_write(
    consumer: Path, tmp_path: Path, models: Path, env: dict[str, str]
) -> None:
    """AC7: a framework without docs/design-contract.md is incomplete, and nothing is written."""
    framework = make_framework(tmp_path / "bare-framework")
    (framework / "docs" / "design-contract.md").unlink()
    before = snapshot(consumer)
    with pytest.raises(OnboardError) as caught:
        install(consumer, framework, models, env)
    assert caught.value.code == "onboard.framework_incomplete"
    assert "docs/design-contract.md" in caught.value.message
    assert snapshot(consumer) == before


def test_cli_volumes_prints_a_json_list(capsys: pytest.CaptureFixture[str]) -> None:
    """FR1/AC6: `volumes` prints a JSON list with mount, free bytes, and fits_models."""
    assert onboard_main(["volumes"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert isinstance(rows, list) and rows
    assert {"mount", "free_bytes", "fits_models"} <= set(rows[0])


def test_cli_install_error_exits_one_with_remediation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """FR2: a failed preflight prints ERROR [code] and Remediation, then exits 1."""
    framework = make_framework(tmp_path / "framework")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(framework))
    empty = tmp_path / "empty-project"
    empty.mkdir()
    argv = ["install", "--consumer", str(empty), "--models-dir", str(tmp_path / "m")]
    assert onboard_main([*argv, "--game-dir", "/abs/game"]) == 1
    err = capsys.readouterr().err
    assert "ERROR [onboard.game_dir_invalid]" in err
    assert "Remediation:" in err
    assert not (empty / "scripts").exists()


def test_missing_git_lfs_fails_before_any_write(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC6: git-lfs off PATH raises onboard.git_lfs_missing with its remediation; nothing is
    written."""
    before = snapshot(consumer)

    def without_git_lfs(name: str) -> str | None:
        return None if name == "git-lfs" else f"/usr/bin/{name}"

    with pytest.raises(OnboardError) as caught:
        install(consumer, framework, models, env, which=without_git_lfs)
    assert caught.value.code == "onboard.git_lfs_missing"
    assert caught.value.remediation == (
        "Install Git LFS (brew install git-lfs), then re-run onboarding."
    )
    assert snapshot(consumer) == before


def test_lfs_steps_follow_gitignore_env(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """FR7: gitattributes_lfs then git_lfs_hooks run directly after gitignore_env."""
    names = [r.name for r in install(consumer, framework, models, env)]
    assert names[-3:] == ["gitignore_env", "gitattributes_lfs", "git_lfs_hooks"]


def test_git_consumer_gets_lfs_hooks_once(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC5: in a git work tree the LFS hooks are installed on the first run and left alone after."""
    first_runner = FakeRunner(work_tree=True)
    first = {r.name: r for r in install(consumer, framework, models, env, runner=first_runner)}
    assert first["git_lfs_hooks"].status == "installed"
    assert first_runner.argv_starting("git", "-C", str(consumer), "lfs", "install", "--local")

    second_runner = FakeRunner(work_tree=True)
    second = {r.name: r for r in install(consumer, framework, models, env, runner=second_runner)}
    assert second["git_lfs_hooks"].status == "unchanged"
    assert second_runner.argv_starting("git", "-C", str(consumer), "lfs") == []
