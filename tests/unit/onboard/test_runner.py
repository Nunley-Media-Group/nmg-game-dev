"""End-to-end onboarding of a fixture consumer: AC1–AC9, the CLI, and the preflight guarantees
(#7)."""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from pathlib import Path

import pytest

from nmg_game_dev.onboard import OnboardError, run_onboard
from nmg_game_dev.onboard.__main__ import main as onboard_main
from nmg_game_dev.onboard.commands import HostFacts
from nmg_game_dev.onboard.paths import framework_root
from nmg_game_dev.onboard.report import StepResult
from tests.onboard_fakes import (
    APPLE_SILICON,
    PINNED_COMMIT,
    FakeRunner,
    all_tools_present,
    gib_free,
    make_consumer,
    make_framework,
    mflux_missing,
    small_disk,
    snapshot,
)

HOOK_COMMANDS = (
    'bash "$CLAUDE_PROJECT_DIR/scripts/start-blender-mcp.sh"',
    'bash "$CLAUDE_PROJECT_DIR/scripts/start-unreal-mcp.sh"',
)


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
) -> list[StepResult]:
    return run_onboard(
        consumer,
        framework=framework,
        models_dir=models,
        refresh=refresh,
        env=env,
        run=runner or FakeRunner(),
        which=which,
        host=host,
        free_bytes=free,
    )


def test_fresh_install_installs_framework_files(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC1: scripts, hooks, asset contract, and the CLAUDE.md block; no .mcp.json, fixtures, or
    API keys."""
    results = install(consumer, framework, models, env)

    for script in ("start-blender-mcp.sh", "start-unreal-mcp.sh"):
        installed = consumer / "scripts" / script
        assert installed.read_bytes() == (framework / "scripts" / script).read_bytes()
        assert os.access(installed, os.X_OK)

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
    assert not (consumer / "Plugins" / "nmg-game-dev" / "Binaries").exists()
    local = json.loads((consumer / ".claude" / "settings.local.json").read_text())
    assert not [key for key in local["env"] if key.endswith("_API_KEY")]
    assert {r.name for r in results} >= {"settings_hooks", "asset_contract", "texture_env"}


def test_unreal_plugins_installed_and_enabled(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC2: the UE plugin copy, the pinned VibeUE clone, the four .uproject plugins, and the MCP
    ini."""
    runner = FakeRunner()
    install(consumer, framework, models, env, runner=runner)

    plugin = consumer / "Plugins" / "nmg-game-dev"
    assert (plugin / "nmg-game-dev.uplugin").is_file()
    assert (plugin / "Source" / "NmgGameDevRuntime" / "Public" / "NmgAssetResolver.h").is_file()
    assert not (plugin / "Binaries").exists()
    assert not (plugin / "Intermediate").exists()

    clone = runner.argv_starting("git", "clone")
    assert clone == [
        [
            "git",
            "clone",
            "--depth",
            "1",
            "--branch",
            "v5.0-ue5.8",
            "https://github.com/kevinpbuckley/VibeUE.git",
            str(consumer / "Plugins" / "VibeUE"),
        ]
    ]

    uproject = json.loads((consumer / "Game.uproject").read_text())
    enabled = {entry["Name"]: entry["Enabled"] for entry in uproject["Plugins"]}
    assert enabled == {
        "Other": True,
        "ModelContextProtocol": True,
        "EditorToolset": True,
        "VibeUE": True,
        "nmg-game-dev": True,
    }
    assert uproject["Description"] == "keep me"
    assert uproject["Modules"] == [{"Name": "Game", "Type": "Runtime"}]

    ini = (consumer / "Config" / "DefaultEditorPerProjectUserSettings.ini").read_text()
    assert "[/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]" in ini
    assert "bAutoStartServer=True" in ini
    assert "ServerPortNumber=8000" in ini


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
        framework = make_framework(tmp_path / scope / "framework")
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
    """AC8: a second run adds no duplicates, runs no clone or mflux-save, and exits cleanly."""
    install(consumer, framework, models, env)
    before = snapshot(consumer)
    runner = FakeRunner()
    results = install(consumer, framework, models, env, runner=runner)

    assert runner.argv_starting("git", "clone") == []
    assert runner.argv_starting("mflux-save") == []
    assert all(result.status == "unchanged" for result in results), [r.as_json() for r in results]
    settings = json.loads((consumer / ".claude" / "settings.json").read_text())
    assert len(settings["hooks"]["SessionStart"]) == 1
    uproject = json.loads((consumer / "Game.uproject").read_text())
    assert [e["Name"] for e in uproject["Plugins"]].count("VibeUE") == 1
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


def test_vibeue_pin_drift_is_repaired_with_refresh(
    consumer: Path, framework: Path, models: Path, env: dict[str, str]
) -> None:
    """AC9: a VibeUE HEAD other than the pin is drift; --refresh checks the pin out again."""
    install(consumer, framework, models, env)
    drifted_runner = FakeRunner(head="0" * 40)
    results = install(consumer, framework, models, env, runner=drifted_runner)
    assert {r.name: r.status for r in results}["vibeue"] == "drift"
    assert drifted_runner.argv_starting("git", "clone") == []

    refresh_runner = FakeRunner(head="0" * 40)
    results = install(consumer, framework, models, env, runner=refresh_runner, refresh=True)
    assert {r.name: r.status for r in results}["vibeue"] == "refreshed"
    checkout = refresh_runner.argv_starting("git", "-C")
    assert any(call[-3:] == ["checkout", "--force", PINNED_COMMIT] for call in checkout)


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
    assert (
        onboard_main(["install", "--consumer", str(empty), "--models-dir", str(tmp_path / "m")])
        == 1
    )
    err = capsys.readouterr().err
    assert "ERROR [onboard.uproject_not_found]" in err
    assert "Remediation:" in err
    assert not (empty / "scripts").exists()
