# ruff: noqa: E501  -- step decorators repeat the Gherkin text verbatim, so they run long.
"""pytest-bdd bindings for godot_engine.feature: SCN001-SCN010, SCN014, and SCN015 (issue #249).

The scenarios run the real finalize orchestrator, audio import, material-variant listing, design
scaffold, ship runner, onboarding, and gate script. Godot is ``FakeGodotRunner`` (or its finalize
subclass ``FinalizeGodot``), the Blender steps are ``FakeStepRunner``, ffmpeg is ``FakeFfmpeg``, and
the ship tools are PATH shims, so no editor, Godot, Blender, or ffmpeg process runs. The add-on's
GDScript tests (SCN008) run only through ``scripts/run-godot-tests.sh`` with a fake ``godot``, as
``tests/unit/test_run_godot_tests.py`` does. The steps share one ``state`` dict per scenario.
"""

from __future__ import annotations

import importlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any, Final

import pytest
from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.audio import import_audio
from nmg_game_dev.finalize import list_material_variants
from nmg_game_dev.godot import binary as godot_binary
from nmg_game_dev.godot.project import read_config
from nmg_game_dev.godot.terrain import decode_heights, parse_variant
from nmg_game_dev.pipeline import STEP_ORDER, FinalizeClients, FinalizeRequest, finalize
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.ship.artifacts import artifact_sha256
from nmg_game_dev.ship.errors import ShipError
from tests.bdd.test_onboard_bdd import HOOK_COMMANDS
from tests.bdd.test_onboard_bdd import _fresh as fresh_onboard_context
from tests.bdd.test_onboard_bdd import _install as onboard_install
from tests.bdd.test_rigged_animations_bdd import _exported as exported_clips
from tests.bdd.test_rigged_animations_bdd import _Project as RiggedProject
from tests.finalize_fakes import (
    FakeStepRunner,
    FinalizeGodot,
    TerrainStepRunner,
    asset_meshes,
)
from tests.godot_fakes import FakeGodotRunner, forbid_godot
from tests.onboard_fakes import snapshot
from tests.ship_fakes import APP, ShipSandbox, make_sandbox, write_mobile_report
from tests.unit.audio.conftest import FakeFfmpeg, audio_probe, fake_godot
from tests.unit.design.test_scaffold import _game_files, _nodes, _project, _run, _texts
from tests.unit.test_material_variants_host import _finalize as finalize_with_variants
from tests.unit.test_run_godot_tests import _FAKE_GODOT, ADDON, SCRIPT, _write_tool

FEATURE = "godot_engine.feature"
REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIO_FIXTURES = REPO_ROOT / "tests" / "fixtures" / "audio"
BLENDER_STEPS = list(STEP_ORDER[:6])
RUN = {"name": "Run", "hash": "hash-run"}
IDLE = {"name": "Idle", "hash": "hash-idle"}
WALK = {"name": "Walk", "hash": "hash-walk"}
# The repository guard (T015). Its module name spells the retired engine, which this file may not,
# so it is found by pattern.
engine_guard = importlib.import_module(
    "tests.unit." + next((REPO_ROOT / "tests" / "unit").glob("test_no_*_references.py")).stem
)


@pytest.fixture
def state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    # An empty project root, so no repository budget, backlog, or settings file is read.
    project_dir = tmp_path / "claude-project"
    project_dir.mkdir()
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project_dir))
    return {"tmp": tmp_path, "monkeypatch": monkeypatch, "error": None}


# --- Scenarios -----------------------------------------------------------------------------------


@scenario(FEATURE, "Finalize lands both variants in Godot")
def test_scn001_finalize_lands_both_variants_in_godot() -> None:
    """AC1: both variants export into game/assets, import headless, and match the probe."""


@scenario(FEATURE, "Godot import failures stop finalize")
def test_scn002_godot_import_failures_stop_finalize() -> None:
    """AC2: a missing binary, an ERROR line, or a probe mismatch stops finalize."""


@scenario(FEATURE, "Animation clips import per clip")
def test_scn003_animation_clips_import_per_clip() -> None:
    """AC3: only the changed clip re-exports and re-imports as an animation library."""


@scenario(FEATURE, "Terrain becomes chunked meshes with collision")
def test_scn004_terrain_becomes_chunked_meshes_with_collision() -> None:
    """AC4: chunk .glb files plus a .tscn with HeightMapShape3D collision."""


@scenario(FEATURE, "Music imports into Godot as a looping AudioStreamOggVorbis")
def test_scn005_music_imports_as_looping_ogg() -> None:
    """AC5: the WAV is kept under SourceArt and the Ogg imports with loop on."""


@scenario(FEATURE, "Music import fails without ffmpeg")
def test_scn015_music_import_fails_without_ffmpeg() -> None:
    """AC5: no ffmpeg is audio.ffmpeg_not_found and no Ogg is written."""


@scenario(FEATURE, "Material variants are listed without an editor")
def test_scn006_material_variants_listed_without_an_editor() -> None:
    """AC6: the listing reads the finalized files and starts no Godot."""


@scenario(FEATURE, "Design scaffolding writes Godot files")
def test_scn007_design_scaffolding_writes_godot_files() -> None:
    """AC7: a region scene, a mission resource, and a system script; reruns change nothing."""


@scenario(FEATURE, "The runtime add-on routes variants")
def test_scn008_the_runtime_addon_routes_variants() -> None:
    """AC8: the add-on's tests cover the routes and the runner fails on any failure."""


@scenario(FEATURE, "Ship exports every target through Godot")
def test_scn009_ship_exports_every_target_through_godot() -> None:
    """AC9: gates first, then every platform's artifact; dry-run prints every command."""


@scenario(FEATURE, "Onboarding sets up a Godot consumer")
def test_scn010_onboarding_sets_up_a_godot_consumer() -> None:
    """AC10: the Godot project, add-on, presets, and only the Blender hook; reruns change nothing."""


@scenario(FEATURE, "The retired engine is gone from nmg-game-dev")
def test_scn014_the_retired_engine_is_gone() -> None:
    """AC14: the repository guard passes and the manifest registers the Godot gate only."""


# --- Helpers -------------------------------------------------------------------------------------


class _TexturedStepRunner(FakeStepRunner):
    """The Blender fake whose export also writes the baked ``T_*.png`` into each variant folder.

    The asset contract puts ``<Name>.glb``, its ``T_*.png`` textures, and ``nmg-asset.json`` in
    each variant folder; the headless Blender suite owns the real export's texture copy.
    """

    def _export_outputs(self, job_dir: Path) -> dict[str, Any]:
        outputs = super()._export_outputs(job_dir)
        name = self.request.collection
        for variant in outputs["variants"].values():
            folder = Path(variant["dir"])
            for suffix in ("BC", "N", "ORM"):
                (folder / f"T_{name}_Body_{suffix}.png").write_bytes(b"png")
        return outputs


def _crate_request(root: Path, *, asset_class: str = "standard_prop") -> FinalizeRequest:
    """A Crate request whose export root is ``<root>/game/assets`` in a Godot project."""
    blend = root / "crate.blend"
    blend.write_bytes(b"authored")
    return FinalizeRequest(
        collection="Crate",
        category="Props",
        asset_class=asset_class,  # type: ignore[arg-type]
        export_root=root / "game" / "assets",
        blend=blend,
    )


def _finalize(state: dict[str, Any], runner: FakeStepRunner, godot: FinalizeGodot | None) -> None:
    state["runner"] = runner
    state["godot"] = godot
    try:
        state["result"] = finalize(
            state["request"],
            cache_dir=state["tmp"] / "cache",
            runner=runner,
            job_dir=state["tmp"] / "job",
            clients=FinalizeClients(godot=godot),
        )
        state["error"] = None
    except PipelineError as error:
        state["error"] = error


def _step_outputs(result: Any, step: str) -> dict[str, Any]:
    outputs: dict[str, Any] = next(item for item in result.steps if item.step == step).outputs
    return outputs


def _save_audio(state: dict[str, Any], name: str) -> Path:
    saved: Path = state["tmp"] / "saved"
    saved.mkdir(exist_ok=True)
    target = saved / name
    shutil.copyfile(AUDIO_FIXTURES / "tone.wav", target)
    return target


def _audio_project(state: dict[str, Any]) -> Path:
    """A consumer root with ``game/project.godot`` that ``CLAUDE_PROJECT_DIR`` names."""
    root: Path = state["tmp"] / "consumer"
    (root / "game").mkdir(parents=True, exist_ok=True)
    (root / "game" / "project.godot").write_text("config_version=5\n", encoding="utf-8")
    state["monkeypatch"].setenv("CLAUDE_PROJECT_DIR", str(root))
    state["root"] = root
    return root


def _wire_audio(state: dict[str, Any], *, fake_ffmpeg: bool) -> None:
    """Make the fake Godot (and, unless ``fake_ffmpeg`` is false, the fake ffmpeg) the runners."""
    core = "nmg_game_dev.audio.core"
    monkeypatch: pytest.MonkeyPatch = state["monkeypatch"]
    godot = fake_godot()
    state["godot"] = godot
    monkeypatch.setattr(f"{core}.resolve_godot", lambda: Path("/fake/godot"))
    monkeypatch.setattr(f"{core}.SubprocessGodotRunner", lambda _binary: godot)
    if fake_ffmpeg:
        ffmpeg = FakeFfmpeg()
        state["ffmpeg"] = ffmpeg
        monkeypatch.setattr(f"{core}.resolve_ffmpeg", lambda: Path("/fake/ffmpeg"))
        monkeypatch.setattr(f"{core}.SubprocessFfmpegRunner", lambda _binary: ffmpeg)


def _gate_env(root: Path) -> dict[str, str]:
    """The sandbox environment for scripts/run-godot-tests.sh with a fake ``godot`` on PATH."""
    godot = _write_tool(root / "path-bin" / "godot", _FAKE_GODOT)
    return {
        "PATH": os.pathsep.join(
            [str(godot.parent), str(Path(sys.executable).parent), "/usr/bin", "/bin"]
        ),
        "HOME": str(root),
        "LANG": "C",
        "GODOT_CACHE_DIR": str(root / "cache"),
        "FAKE_GODOT_LOG": str(root / "godot.jsonl"),
        "FAKE_EXPECTED": str(REPO_ROOT / "tests" / "godot" / "fixture" / "expected-probe.json"),
    }


def _run_gate(env: dict[str, str]) -> Any:
    import subprocess  # noqa: PLC0415

    return subprocess.run(
        [str(SCRIPT)], cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False
    )


def _ship(sandbox: ShipSandbox, state: dict[str, Any], *, dry_run: bool) -> list[Any]:
    capsys: pytest.CaptureFixture[str] = state["capsys"]
    capsys.readouterr()
    try:
        entries = sandbox.ship("all", dry_run=dry_run)
    except ShipError as error:
        pytest.fail(f"ship all failed: {error.code}: {error.message}")
    captured = capsys.readouterr()
    state["output"] = captured.out + captured.err
    return entries


def _all_target_sandbox(root: Path) -> ShipSandbox:
    sandbox = make_sandbox(root)
    tests = sandbox.game / "tests"
    tests.mkdir()
    (tests / "run_tests.gd").write_text("extends SceneTree\n", encoding="utf-8")
    write_mobile_report(
        sandbox.game,
        "Props/Crate",
        {"class": "standard_prop", "tris": 2800, "max_texture_px": 1024, "materials": 1},
    )
    return sandbox


# --- SCN001 --------------------------------------------------------------------------------------


@given(
    'a consumer with game/project.godot and a collection "Crate" in category "Props" that passes validation'
)
def _consumer_with_crate(state: dict[str, Any]) -> None:
    state["request"] = _crate_request(state["tmp"])
    state["events"] = []
    state["godot"] = FinalizeGodot(state["tmp"] / "game", events=state["events"])
    assert (state["tmp"] / "game" / "project.godot").is_file()


@when("finalize runs every step")
def _finalize_every_step(state: dict[str, Any]) -> None:
    runner = _TexturedStepRunner(state["request"], events=state["events"])
    _finalize(state, runner, state["godot"])


@then(
    "game/assets/Props/Crate/Desktop and game/assets/Props/Crate/Mobile each hold Crate.glb, its textures, and nmg-asset.json"
)
def _variant_folders(state: dict[str, Any]) -> None:
    assert state["error"] is None, state["error"]
    asset = state["tmp"] / "game" / "assets" / "Props" / "Crate"
    for variant in ("Desktop", "Mobile"):
        folder = asset / variant
        assert (folder / "Crate.glb").is_file(), variant
        assert (folder / "nmg-asset.json").is_file(), variant
        assert sorted(path.name for path in folder.glob("T_*.png")) == [
            "T_Crate_Body_BC.png",
            "T_Crate_Body_N.png",
            "T_Crate_Body_ORM.png",
        ]
    result = state["result"]
    assert result.desktop_resource_path == "res://assets/Props/Crate/Desktop/Crate.glb"
    assert result.mobile_resource_path == "res://assets/Props/Crate/Mobile/Crate.glb"


@then(
    "the headless import ran and the probe's mesh names, triangle counts, material slots, and bounds match the export"
)
def _import_matches(state: dict[str, Any]) -> None:
    godot: FinalizeGodot = state["godot"]
    assert godot.count("--import") == 1
    assert godot.calls[0] == ["--import"]
    assert [params["glb"] for params in godot.params] == [
        "res://assets/Props/Crate/Desktop/Crate.glb",
        "res://assets/Props/Crate/Mobile/Crate.glb",
    ]
    imports = _step_outputs(state["result"], "import_godot")["imports"]
    for variant in ("Desktop", "Mobile"):
        assert imports[variant]["meshes"] == asset_meshes("Crate", variant)


@then(
    "the steps ran in the order validate, bake, variants, export, export_anims, reimport, import_godot, import_anims"
)
def _step_order(state: dict[str, Any]) -> None:
    # The literal order AC1 names, not STEP_ORDER itself, so reordering the pipeline fails here.
    order = [
        "validate",
        "bake",
        "variants",
        "export",
        "export_anims",
        "reimport",
        "import_godot",
        "import_anims",
    ]
    assert [step.step for step in state["result"].steps] == order
    # As observed by the step runner and the Godot fake: the six Blender steps, then
    # import_godot's one headless import and one probe per variant.
    assert state["events"] == [*order[:6], "import", "probe_asset.gd", "probe_asset.gd"]


# --- SCN002 --------------------------------------------------------------------------------------


@given(parsers.parse("finalize reaches import_godot with {condition}"))
def _reaches_import(state: dict[str, Any], condition: str) -> None:
    tmp: Path = state["tmp"]
    # A rigged asset, so import_anims would run Godot's clip probe if it were reached.
    state["request"] = _crate_request(tmp, asset_class="character")
    project = tmp / "game"
    godot: FinalizeGodot | None
    if condition == "no Godot binary on the host":
        FinalizeGodot(project)  # the project exists; only the binary is missing
        monkeypatch: pytest.MonkeyPatch = state["monkeypatch"]
        monkeypatch.delenv("GODOT_BIN", raising=False)
        monkeypatch.setenv("PATH", str(tmp / "empty-bin"))
        monkeypatch.setattr(godot_binary, "DEFAULT_GODOT_APP_BINARY", tmp / "no-godot")
        godot = None
    elif condition == "an ERROR line from the import":
        godot = FinalizeGodot(project, import_errors=True)
    elif condition == "a probe triangle count mismatch":
        godot = FinalizeGodot(
            project,
            mesh_edits={
                "Mobile": lambda meshes: [{**mesh, "tris": mesh["tris"] + 1} for mesh in meshes]
            },
        )
    else:
        raise AssertionError(f"unknown condition {condition!r}")
    state["pending_godot"] = godot


@when("the step runs")
def _the_step_runs(state: dict[str, Any]) -> None:
    runner = FakeStepRunner(state["request"], clips=[IDLE])
    _finalize(state, runner, state["pending_godot"])


@then(parsers.parse('finalize fails with "{code}" and a remediation line'))
def _finalize_fails(state: dict[str, Any], code: str) -> None:
    error = state["error"]
    assert isinstance(error, PipelineError), "finalize did not fail"
    assert error.code == code
    assert error.remediation and "\n" not in error.remediation.strip()
    if code == "godot.not_found":
        assert "GODOT_BIN" in error.remediation


@then("no later step runs")
def _no_later_step(state: dict[str, Any]) -> None:
    # export_anims runs twice for a rigged asset: once to probe the clips, once to export them.
    assert list(dict.fromkeys(state["runner"].steps_run())) == BLENDER_STEPS
    godot: FinalizeGodot | None = state["godot"]
    if godot is not None:
        # import_anims would probe the clips; it never ran.
        assert godot.probe_calls("probe_anims.gd") == []


# --- SCN003 --------------------------------------------------------------------------------------


@given('a rigged asset with clips "Idle", "Walk", and "Run" already finalized')
def _rigged_finalized(state: dict[str, Any]) -> None:
    project = RiggedProject(state["tmp"])
    project.run(clips=(IDLE, WALK, RUN))
    state["project"] = project
    state["clip_bytes"] = {
        path.name: path.read_bytes() for path in project.animations.glob("*.glb")
    }
    assert sorted(state["clip_bytes"]) == [
        "A_Crate_Idle.glb",
        "A_Crate_Run.glb",
        "A_Crate_Walk.glb",
    ]


@when('the "Walk" clip changes and finalize runs again')
def _walk_changes(state: dict[str, Any]) -> None:
    project: RiggedProject = state["project"]
    result, runner, godot = project.run(clips=(IDLE, {**WALK, "hash": "hash-walk-2"}, RUN))
    state["result"], state["runner"], state["godot"] = result, runner, godot


@then("only A_<Name>_Walk.glb is re-exported and re-imported as an animation library")
def _only_walk(state: dict[str, Any]) -> None:
    project: RiggedProject = state["project"]
    assert exported_clips(state["runner"]) == [["Walk"]]
    assert state["godot"].probed_clips() == [["Walk"]]
    after = {path.name: path.read_bytes() for path in project.animations.glob("*.glb")}
    changed = sorted(name for name in after if after[name] != state["clip_bytes"][name])
    assert changed == ["A_Crate_Walk.glb"]
    settings = project.animations / "A_Crate_Walk.glb.import"
    assert 'importer="animation_library"' in settings.read_text(encoding="utf-8")
    animations = state["result"].animations
    assert animations is not None
    hits = {clip["name"]: clip["import_cache_hit"] for clip in animations["clips"]}
    assert hits == {"Idle": True, "Walk": False, "Run": True}


# --- SCN004 --------------------------------------------------------------------------------------


@given("an authored terrain asset with a heightfield")
def _terrain_asset(state: dict[str, Any]) -> None:
    tmp: Path = state["tmp"]
    blend = tmp / "hills.blend"
    blend.write_bytes(b"authored")
    state["request"] = FinalizeRequest(
        collection="Hills",
        category="Terrain",
        asset_class="terrain",
        export_root=tmp / "game" / "assets",
        blend=blend,
    )


@when("finalize runs")
def _finalize_runs(state: dict[str, Any]) -> None:
    request: FinalizeRequest = state["request"]
    _finalize(state, TerrainStepRunner(request), FinalizeGodot(state["tmp"] / "game"))


@then(
    "the variant folder holds chunk .glb files and a .tscn instancing every chunk with HeightMapShape3D collision from the same heightfield"
)
def _terrain_scene(state: dict[str, Any]) -> None:
    assert state["error"] is None, state["error"]
    asset = state["tmp"] / "game" / "assets" / "Terrain" / "Hills"
    sidecar = json.loads((asset / "nmg-variants.json").read_text(encoding="utf-8"))
    for variant in ("Desktop", "Mobile"):
        folder = asset / variant
        terrain = parse_variant(sidecar, variant)
        side = terrain.chunks_per_side
        chunks = sorted(path.name for path in folder.glob("Hills_Chunk_*.glb"))
        assert chunks == sorted(
            f"Hills_Chunk_{row}_{col}.glb" for row in range(side) for col in range(side)
        )
        text = (folder / "Hills.tscn").read_text(encoding="utf-8")
        for chunk in chunks:
            stem = chunk.removesuffix(".glb")
            assert f'[node name="{stem}" parent="." instance=ExtResource("chunk_{stem}")]' in text
        assert 'type="HeightMapShape3D"' in text
        match = re.search(r"map_data = PackedFloat32Array\(([^)]*)\)", text)
        assert match is not None
        values = [float(item) for item in match.group(1).split(",")]
        heights = decode_heights(folder / "T_Hills_Height.png", terrain)
        assert max(abs(a - b) for a, b in zip(values, heights, strict=True)) < 1e-3
    assert state["result"].desktop_resource_path == "res://assets/Terrain/Hills/Desktop/Hills.tscn"


@then(
    'a probe height range off by more than 0.05 m fails with "import_godot.terrain_height_mismatch"'
)
def _terrain_mismatch(state: dict[str, Any]) -> None:
    root: Path = state["tmp"] / "mismatch"
    root.mkdir()
    blend = root / "hills.blend"
    blend.write_bytes(b"authored")
    request = FinalizeRequest(
        collection="Hills",
        category="Terrain",
        asset_class="terrain",
        export_root=root / "game" / "assets",
        blend=blend,
    )
    with pytest.raises(PipelineError) as info:
        finalize(
            request,
            cache_dir=root / "cache",
            runner=TerrainStepRunner(request),
            job_dir=root / "job",
            clients=FinalizeClients(godot=FinalizeGodot(root / "game", mesh_range=(10.0, 40.06))),
        )
    assert info.value.code == "import_godot.terrain_height_mismatch"
    assert info.value.remediation


# --- SCN005 and SCN015 ---------------------------------------------------------------------------


@given('a music file "Theme.wav" passed to import_audio with loop enabled')
def _looping_music(state: dict[str, Any]) -> None:
    _audio_project(state)
    _wire_audio(state, fake_ffmpeg=True)
    state["audio"] = (_save_audio(state, "Theme.wav"), "Theme", "music", True)


@given("ffmpeg is not on PATH and FFMPEG_BIN is unset")
def _no_ffmpeg(state: dict[str, Any]) -> None:
    monkeypatch: pytest.MonkeyPatch = state["monkeypatch"]
    monkeypatch.delenv("FFMPEG_BIN", raising=False)
    empty = state["tmp"] / "empty-bin"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    assert shutil.which("ffmpeg") is None


@given('a music file "Theme.wav" passed to import_audio')
def _music(state: dict[str, Any]) -> None:
    _audio_project(state)
    # Only Godot is faked: ffmpeg resolves through the real FFMPEG_BIN and PATH lookup.
    _wire_audio(state, fake_ffmpeg=False)
    state["audio"] = (_save_audio(state, "Theme.wav"), "Theme", "music", False)


@when("the import runs")
def _import_runs(state: dict[str, Any]) -> None:
    src, name, kind, loop = state["audio"]
    try:
        state["result"] = import_audio(src, name, kind, loop)
        state["error"] = None
    except PipelineError as error:
        state["error"] = error


@then("SourceArt/Audio/Music/Theme.wav and game/assets/Audio/Theme.ogg exist")
def _music_files(state: dict[str, Any]) -> None:
    assert state["error"] is None, state["error"]
    root: Path = state["root"]
    assert (root / "SourceArt" / "Audio" / "Music" / "Theme.wav").is_file()
    assert (root / "game" / "assets" / "Audio" / "Theme.ogg").is_file()
    [call] = state["ffmpeg"].calls
    assert call[2:4] == ["-c:a", "libvorbis"]


@then("Godot imported it as an AudioStreamOggVorbis with loop enabled")
def _ogg_imported(state: dict[str, Any]) -> None:
    root: Path = state["root"]
    assert state["result"]["godot_asset"] == "res://assets/Audio/Theme.ogg"
    assert state["result"]["imported_to_godot"] is True
    config = read_config(root / "game" / "assets" / "Audio" / "Theme.ogg.import")
    assert config[("params", "loop")] == "true"
    godot: FakeGodotRunner = state["godot"]
    assert godot.count("--import") >= 1
    assert {"stream": "res://assets/Audio/Theme.ogg"} in godot.params
    probed = audio_probe(root / "game")({"stream": "res://assets/Audio/Theme.ogg"})
    assert probed == {"class": "AudioStreamOggVorbis", "loop": True}


@then("it fails with audio.ffmpeg_not_found and a remediation line")
def _ffmpeg_not_found(state: dict[str, Any]) -> None:
    error = state["error"]
    assert isinstance(error, PipelineError)
    assert error.code == "audio.ffmpeg_not_found"
    assert error.remediation == "Install ffmpeg or set FFMPEG_BIN to its executable."


@then("game/assets/Audio/Theme.ogg does not exist")
def _no_ogg(state: dict[str, Any]) -> None:
    assert not (state["root"] / "game" / "assets" / "Audio" / "Theme.ogg").exists()
    assert state["godot"].calls == []


# --- SCN006 --------------------------------------------------------------------------------------


@given('an asset finalized with material variants "Rusty" and "Clean"')
def _finalized_with_variants(state: dict[str, Any]) -> None:
    entries = [
        {
            "name": name,
            "material": "M_Crate_Body",
            "base_color": None,
            "parameters": {"Tint": tint},
        }
        for name, tint in (("Rusty", [0.6, 0.3, 0.1, 1.0]), ("Clean", [0.9, 0.9, 0.9, 1.0]))
    ]
    finalize_with_variants(state["tmp"], entries)


@when("list_material_variants runs")
def _list_variants(state: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> None:
    # Any attempt to resolve or start Godot (or any process) fails the scenario.
    forbid_godot(monkeypatch)
    state["no_process_guard"] = True
    state["rows"] = list_material_variants(
        category="Props",
        collection="Crate",
        export_root=str(state["tmp"] / "game" / "assets"),
    )


@then("it returns each variant's name and material slot for the Desktop and Mobile folders")
def _variant_rows(state: dict[str, Any]) -> None:
    base = "res://assets/Props/Crate"
    assert state["rows"] == [
        {
            "name": name,
            "material": "M_Crate_Body",
            "desktop": f"{base}/Desktop/M_Crate_Body_{name}.tres",
            "mobile": f"{base}/Mobile/M_Crate_Body_{name}.tres",
        }
        for name in ("Clean", "Rusty")
    ]


@then("no Godot process was started")
def _no_godot(state: dict[str, Any]) -> None:
    # The When step ran with resolve_godot, SubprocessGodotRunner.run, subprocess.run, and
    # subprocess.Popen all raising, so reaching here with rows means none of them was called.
    assert state["no_process_guard"] is True
    assert isinstance(state["rows"], list) and state["rows"]


# --- SCN007 --------------------------------------------------------------------------------------

_REGION_SCENE = "game/levels/OldTown/OldTown.tscn"
_MISSION_TRES = "game/missions/FirstLight.tres"
_SYSTEM_GD = "game/systems/Stealth/stealth.gd"
_SMOKE_CALL: Final = [
    "--fixed-fps",
    "60",
    "--quit-after",
    "600",
    "--",
    "--nmg-autoplay",
    "--nmg-test-saves",
]
"""The headless autoplay smoke run ship gates on (#251); the ship's Godot argv after the flags."""


@given('a backlog with region "OldTown", mission "FirstLight", and system "Stealth"')
def _design_backlog(state: dict[str, Any]) -> None:
    state["root"] = _project(
        state["tmp"] / "game-project",
        {
            "regions/old-town.md": "---\ntype: region\nname: Old Town\n---\n",
            "missions/first-light.md": (
                "---\ntype: mission\nname: First Light\nact: 1\nregion: Old Town\n"
                "depends_on: [Old Town]\n---\n"
            ),
            "systems/stealth.md": "---\ntype: system\nname: Stealth\n---\n",
        },
    )


@when("/design scaffolds")
def _design_scaffolds(state: dict[str, Any]) -> None:
    state["report"] = _run(state["root"])


@then(
    "game/levels/OldTown/OldTown.tscn, game/missions/FirstLight.tres, and game/systems/Stealth/stealth.gd exist with the specified contents"
)
def _scaffolded_files(state: dict[str, Any]) -> None:
    root: Path = state["root"]
    assert state["report"].failed is False
    assert _texts(state["report"]) == [
        f"created mission FirstLight: {_MISSION_TRES}",
        f"created region OldTown: {_REGION_SCENE}",
        f"created system Stealth: {_SYSTEM_GD}",
    ]
    scene = (root / _REGION_SCENE).read_text(encoding="utf-8")
    assert scene.startswith("[gd_scene format=3]")
    nodes = _nodes(scene)
    assert nodes["OldTown"] == {"name": "OldTown", "type": "Node3D"}
    assert nodes["PlayerSpawn"]["type"] == "Marker3D"
    assert nodes["DirectionalLight3D"]["type"] == "DirectionalLight3D"
    assert nodes["WorldEnvironment"]["type"] == "WorldEnvironment"
    assert nodes["Ground"]["type"] == "StaticBody3D"
    assert (root / _MISSION_TRES).read_text(encoding="utf-8") == (
        '[gd_resource type="Resource" script_class="NmgMissionDefinition" format=3]\n'
        "\n"
        '[ext_resource type="Script" path="res://addons/nmg_game_dev/nmg_mission_definition.gd" '
        'id="1_script"]\n'
        "\n"
        "[resource]\n"
        'script = ExtResource("1_script")\n'
        'mission_name = "First Light"\n'
        "act = 1\n"
        'region = &"OldTown"\n'
        'depends_on = Array[StringName]([&"OldTown"])\n'
        'design_doc_path = "docs/design/missions/first-light.md"\n'
    )
    assert (root / _SYSTEM_GD).read_text(encoding="utf-8") == (
        "## The Stealth system.\n"
        "##\n"
        "## Scaffolded by /design from docs/design/systems/stealth.md.\n"
        "## Add it as a child of the node it serves.\n"
        "class_name StealthComponent\n"
        "extends Node\n"
    )


@then("a second scaffold leaves every file unchanged")
def _second_scaffold(state: dict[str, Any]) -> None:
    root: Path = state["root"]
    before = {path: (root / path).read_bytes() for path in _game_files(root)}
    report = _run(root)
    assert _texts(report) == [
        f"unchanged mission FirstLight: {_MISSION_TRES}",
        f"unchanged region OldTown: {_REGION_SCENE}",
        f"unchanged system Stealth: {_SYSTEM_GD}",
    ]
    assert {path: (root / path).read_bytes() for path in _game_files(root)} == before


# --- SCN008 --------------------------------------------------------------------------------------


@given("the nmg_game_dev add-on")
def _the_addon(state: dict[str, Any]) -> None:
    for rel in (
        "nmg_assets.gd",
        "tests/run_tests.gd",
        "tests/nmg_log_capture.gd",
        "tests/test_nmg_assets.gd",
    ):
        assert (ADDON / rel).is_file(), rel


@when(
    'the add-on\'s headless test runner resolves "res://assets/Props/Crate/Crate.glb" for desktop, for mobile, and a malformed path'
)
def _addon_runner(state: dict[str, Any]) -> None:
    runs = {
        "pass": {},
        "fail": {"FAKE_GODOT_MODE": "tests_fail"},
        "missing_routing": {"FAKE_GODOT_MODE": "tests_missing_routing"},
        "script_error": {"FAKE_GODOT_MODE": "tests_script_error"},
    }
    state["gate"] = {}
    for label, extra in runs.items():
        root = state["tmp"] / f"gate-{label}"
        state["gate"][label] = (_run_gate({**_gate_env(root), **extra}), root / "godot.jsonl")


# The add-on tests the gate requires a PASS line for: Desktop routing, Mobile routing, and a
# malformed path returned unchanged with exactly one NmgAssets warning (captured by the runner's
# logger, nmg_log_capture.gd). The GDScript itself runs under real Godot in gate-godot-headless.
_ROUTING_TESTS: Final = (
    "test_nmg_assets.gd::test_desktop_variant",
    "test_nmg_assets.gd::test_mobile_variant",
    "test_nmg_assets.gd::test_malformed_path_is_unchanged_with_a_warning",
)


@then("it returns the Desktop path, the Mobile path, and the unchanged path with a warning")
def _addon_routes(state: dict[str, Any]) -> None:
    passing, log = state["gate"]["pass"]
    assert passing.returncode == 0, passing.stderr
    for test in _ROUTING_TESTS:
        assert f"PASS {test}" in passing.stdout.splitlines()
    # Without the malformed-path-with-warning test passing, the gate fails and names it.
    missing, _log = state["gate"]["missing_routing"]
    assert missing.returncode == 5
    assert f"no PASS line for {_ROUTING_TESTS[2]}" in missing.stderr
    # The gate ran the add-on's runner through Godot headless, after the import.
    calls = [json.loads(line) for line in log.read_text("utf-8").splitlines()]
    commands = [call["argv"][call["argv"].index("--path") + 2 :] for call in calls]
    assert commands[0] == ["--import"]
    assert commands[1] == ["-s", "res://addons/nmg_game_dev/tests/run_tests.gd"]
    assert calls[1]["argv"][:3] == ["--headless", "--audio-driver", "Dummy"]


@then('it prints "N passed, M failed" and exits non-zero on any failure')
def _addon_summary(state: dict[str, Any]) -> None:
    passing, _log = state["gate"]["pass"]
    assert any(re.fullmatch(r"\d+ passed, 0 failed", line) for line in passing.stdout.splitlines())
    assert "gate-godot-headless: import, add-on tests, and probes passed" in passing.stdout
    for label in ("fail", "script_error"):
        failing, _log = state["gate"][label]
        assert failing.returncode == 5, label
        assert "add-on tests failed" in failing.stderr


# --- SCN009 --------------------------------------------------------------------------------------


@given('a consumer Godot project and the environment for target "all"')
def _ship_consumer(state: dict[str, Any], capsys: pytest.CaptureFixture[str]) -> None:
    state["capsys"] = capsys
    state["sandbox"] = _all_target_sandbox(state["tmp"] / "ship")


@when("/ship all runs")
def _ship_all(state: dict[str, Any]) -> None:
    state["entries"] = _ship(state["sandbox"], state, dry_run=False)


@then("the script check, the project tests, and the mobile budget gate run before any export")
def _ship_gates_first(state: dict[str, Any]) -> None:
    sandbox: ShipSandbox = state["sandbox"]
    commands = sandbox.godot_commands()
    first_export = next(i for i, call in enumerate(commands) if call[0] == "--export-release")
    before = commands[:first_export]
    # A fresh checkout is imported first, so class_name types resolve in the script check.
    assert before[0] == ["--import"]
    before = before[1:]
    assert len(before) >= 3
    # The headless smoke run (#251) sits between the project tests and the first export.
    assert [call[0] for call in before[:-2]] == ["--check-only"] * (len(before) - 2)
    assert before[-2:] == [["-s", "res://tests/run_tests.gd"], _SMOKE_CALL]
    # The budget gate passed on the within-budget Mobile report, so the mobile exports ran.
    assert sorted(sandbox.exports()) == sorted(
        ["macOS", "iOS", "Android", "Windows Desktop", "Web"]
    )


@then(
    "release/ holds the macOS .app (signed and notarized), the .ipa, the .aab, the .exe, and the web folder, each with SHA-256 in RELEASE-NOTES.md"
)
def _ship_artifacts(state: dict[str, Any]) -> None:
    sandbox: ShipSandbox = state["sandbox"]
    release = sandbox.release_dir
    entries = state["entries"]
    assert {entry.platform: entry.path for entry in entries} == {
        "macos": f"macos/{APP}.app",
        "windows": f"windows/{APP}.exe",
        "ios": f"ios/{APP}.ipa",
        "android": f"android/{APP}.aab",
        "web": "web",
    }
    notes = (release / "RELEASE-NOTES.md").read_text(encoding="utf-8")
    for entry in entries:
        assert (release / entry.path).exists(), entry.path
        assert entry.sha256 == artifact_sha256(release / entry.path)
        assert f"`{entry.path}` | `{entry.sha256}`" in notes
    app = release / "macos" / f"{APP}.app"
    assert any(str(app) in call for call in sandbox.calls("codesign"))
    xcrun = sandbox.calls("xcrun")
    assert any(call[:2] == ["notarytool", "submit"] for call in xcrun)
    assert ["stapler", "staple", str(app)] in xcrun


@then("no WINDOWS_BUILD_* variable was required")
def _no_windows_build(state: dict[str, Any]) -> None:
    sandbox: ShipSandbox = state["sandbox"]
    assert not any(name.startswith("WINDOWS_") for name in sandbox.env)


@then('with --dry-run every command is printed with a "DRY-RUN:" prefix')
def _ship_dry_run(state: dict[str, Any]) -> None:
    sandbox = _all_target_sandbox(state["tmp"] / "ship-dry")
    _ship(sandbox, state, dry_run=True)
    output: str = state["output"]
    assert sandbox.godot.calls == []
    assert sandbox.calls() == []
    exports = [line for line in output.splitlines() if "--export-release" in line]
    assert exports and all(line.startswith("DRY-RUN: ") for line in exports), exports
    for preset in ("macOS", "iOS", "Android", "Windows Desktop", "Web"):
        assert any(
            f"--export-release {preset}" in line or f"--export-release '{preset}'" in line
            for line in exports
        ), preset
    assert all(
        line.startswith("DRY-RUN: ") for line in output.splitlines() if " --headless " in line
    )
    assert "DRY-RUN: codesign" in output
    assert "DRY-RUN: notarization pass" in output


# --- SCN010 --------------------------------------------------------------------------------------


@given("a game project with no nmg-game-dev setup")
def _bare_game(state: dict[str, Any]) -> None:
    state["ctx"] = fresh_onboard_context(state["tmp"] / "onboard")
    assert not (state["ctx"]["consumer"] / "game").exists()


@when("/onboard-consumer runs twice")
def _onboard_twice(state: dict[str, Any]) -> None:
    ctx = state["ctx"]
    onboard_install(ctx)
    assert ctx["error"] is None, ctx["error"]
    state["after_first"] = snapshot(ctx["consumer"])
    onboard_install(ctx)
    assert ctx["error"] is None, ctx["error"]
    state["after_second"] = snapshot(ctx["consumer"])
    state["second_results"] = ctx["results"]


@then(
    "game/project.godot, the add-on, and game/export_presets.cfg with variant filters exist after the first run"
)
def _godot_consumer_files(state: dict[str, Any]) -> None:
    first: dict[str, bytes] = state["after_first"]
    assert "game/project.godot" in first
    assert "game/addons/nmg_game_dev/plugin.cfg" in first
    assert "game/addons/nmg_game_dev/nmg_assets.gd" in first
    consumer: Path = state["ctx"]["consumer"]
    config = read_config(consumer / "game" / "export_presets.cfg")
    filters = {
        config[(section, "name")]: config[(section, "exclude_filter")]
        for (section, key) in config
        if key == "name"
    }
    for preset in ('"macOS"', '"Windows Desktop"'):
        assert filters[preset] == '"assets/*/Mobile/*"', preset
    for preset in ('"iOS"', '"Android"', '"Web"'):
        assert filters[preset] == '"assets/*/Desktop/*"', preset


@then("only the Blender SessionStart hook is installed")
def _blender_hook_only(state: dict[str, Any]) -> None:
    consumer: Path = state["ctx"]["consumer"]
    settings = json.loads((consumer / ".claude" / "settings.json").read_text(encoding="utf-8"))
    commands = [
        hook["command"] for group in settings["hooks"]["SessionStart"] for hook in group["hooks"]
    ]
    assert commands == list(HOOK_COMMANDS)
    assert sorted(path.name for path in (consumer / "scripts").iterdir()) == [
        "start-blender-mcp.sh"
    ]


@then("the second run changes no file")
def _second_run_unchanged(state: dict[str, Any]) -> None:
    assert state["after_second"] == state["after_first"]
    changed = [
        (result.name, result.status, result.detail)
        for result in state["second_results"]
        if result.status not in ("unchanged", "skipped")
    ]
    assert changed == []


# --- SCN014 --------------------------------------------------------------------------------------


@given("this repository's tracked files")
def _tracked_files(state: dict[str, Any]) -> None:
    state["tracked"] = engine_guard._tracked_files()
    assert state["tracked"]


@when("the retired-engine guard runs")
def _guard_runs(state: dict[str, Any]) -> None:
    state["manifest"] = json.loads(
        (REPO_ROOT / "steering" / "manifest.json").read_text(encoding="utf-8")
    )


@then(
    "no file outside specs/, CHANGELOG.md, and the exempt conversion files references the retired engine"
)
def _no_engine_references(state: dict[str, Any]) -> None:
    engine_guard.test_exemptions_are_exactly_the_listed_files_and_exist()
    engine_guard.test_no_tracked_file_references_the_retired_engine()
    # This binding and its feature are not exempt, so they are checked even before they are tracked.
    for path in (Path(__file__), REPO_ROOT / "tests" / "bdd" / "features" / FEATURE):
        lines = path.read_text(encoding="utf-8").splitlines()
        assert not [line for line in lines if engine_guard.references_engine(line)], path.name


@then("steering/manifest.json registers gate-godot-headless and not gate-ue-compile")
def _manifest_gates(state: dict[str, Any]) -> None:
    manifest = state["manifest"]
    validations = {item["id"] for item in manifest["validations"]}
    assert "gate-godot-headless" in validations
    assert "gate-ue-compile" not in validations
