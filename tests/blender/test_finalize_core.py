"""finalize_core under Blender headless: the content hash, the five steps, load-back, and the entry
and session scripts (#69, T002 and T009).

Run with scripts/run-blender-tests.sh. The runner executes every test in one Blender process, so
reimport and the entry and session scripts run in fresh Blender subprocesses, as they do in
production. Under plain CPython the module is skipped.
"""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

from .bake_fixtures import budgets_file, build_asset, procedural_material  # noqa: E402
from .contract_fixtures import build_crate, clear_scene  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
ENTRY = REPO_ROOT / "scripts" / "blender" / "finalize_entry.py"
SESSION = REPO_ROOT / "scripts" / "blender" / "finalize_session.py"
ADDON_DIR = REPO_ROOT / "plugins" / "nmg-game-dev-blender-addon"


@pytest.fixture(autouse=True)
def _isolated_scene(enabled_addon: str) -> Any:  # noqa: ARG001 - ordering dependency
    clear_scene()
    yield
    clear_scene()


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.finalize_core")


def _request(tmp_path: Path, **overrides: Any) -> dict[str, Any]:
    request: dict[str, Any] = {
        "collection": "Crate",
        "category": "Props",
        "asset_class": "standard_prop",
        "export_root": str(tmp_path / "export"),
        "blend": None,
        "budgets_path": None,
        "device": "CPU",
        "samples": 4,
    }
    request.update(overrides)
    return request


def _job_dir(tmp_path: Path, request: dict[str, Any], name: str = "job") -> Path:
    """Make a job directory with request.json, as the host does before it starts a run."""
    job = tmp_path / name
    job.mkdir(parents=True, exist_ok=True)
    (job / "request.json").write_text(json.dumps(request), encoding="utf-8")
    return job


def _record(job: Path, envelope: dict[str, Any]) -> None:
    """Write an envelope where the entry script would, so later steps can read its outputs."""
    (job / f"{envelope['step']}.json").write_text(json.dumps(envelope), encoding="utf-8")


def _save(path: Path) -> Path:
    bpy.ops.wm.save_as_mainfile(filepath=str(path), copy=True)
    return path


def _run_entry(
    blend: Path | None, argv: list[str], *, factory_startup: bool = False
) -> subprocess.CompletedProcess[str]:
    command = [bpy.app.binary_path, "--background"]
    if factory_startup:
        command.append("--factory-startup")
    if blend is not None:
        command.append(str(blend))
    command += ["--python", str(ENTRY), "--", *argv]
    return subprocess.run(command, capture_output=True, text=True, check=False, timeout=900)


def _leftover_old_names() -> list[str]:
    blocks = [
        *bpy.data.objects,
        *bpy.data.meshes,
        *bpy.data.materials,
        *bpy.data.images,
        *bpy.data.collections,
    ]
    return [block.name for block in blocks if block.name.startswith("__nmg_old_")]


def test_content_hash_is_stable_for_an_unchanged_scene(core: Any) -> None:
    build_crate()

    first = core.content_hash("Crate")

    assert core.content_hash("Crate") == first
    assert len(first) == 64


def test_content_hash_changes_when_a_vertex_moves(core: Any) -> None:
    build_crate()
    before = core.content_hash("Crate")

    bpy.data.objects["SM_Crate"].data.vertices[0].co.x += 0.25

    assert core.content_hash("Crate") != before


def test_content_hash_changes_when_an_unlinked_material_input_changes(core: Any) -> None:
    build_crate()
    material = bpy.data.objects["SM_Crate"].material_slots[0].material
    bsdf = next(node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED")
    socket = next(
        item
        for item in bsdf.inputs
        if not item.is_linked and isinstance(getattr(item, "default_value", None), float)
    )
    before = core.content_hash("Crate")

    socket.default_value = 0.0 if socket.default_value > 0.5 else 1.0

    assert core.content_hash("Crate") != before


def test_content_hash_matches_the_same_content_reopened_from_a_file(
    core: Any, tmp_path: Path
) -> None:
    build_crate()
    session_hash = core.content_hash("Crate")
    blend = _save(tmp_path / "crate.blend")
    job = _job_dir(tmp_path, _request(tmp_path))

    completed = _run_entry(blend, ["hash", "--job-dir", str(job)])

    assert completed.returncode == 0, completed.stderr[-2000:]
    assert json.loads((job / "hash.json").read_text(encoding="utf-8"))["hash"] == session_hash


def test_validate_step_writes_the_contract_report(core: Any, tmp_path: Path) -> None:
    build_crate()
    job = _job_dir(tmp_path, _request(tmp_path))

    envelope = core.run_step("validate", _request(tmp_path), job)

    assert envelope["ok"] is True
    assert envelope["error"] is None
    report = json.loads(Path(envelope["outputs"]["report"]).read_text(encoding="utf-8"))
    assert report["kind"] == "contract"
    assert report["passed"] is True, report["findings"]


def test_a_missing_collection_stops_the_step_before_any_work(core: Any, tmp_path: Path) -> None:
    job = _job_dir(tmp_path, _request(tmp_path, collection="Missing"))

    envelope = core.run_step("bake", _request(tmp_path, collection="Missing"), job)

    assert envelope["ok"] is False
    assert envelope["error"]["code"] == "finalize.collection_not_found"
    assert not (job / "bake").exists()


def test_bake_step_writes_textures_and_the_bake_blend(core: Any, tmp_path: Path) -> None:
    build_asset("Crate", [procedural_material("Authored")])
    request = _request(tmp_path, budgets_path=budgets_file(tmp_path))
    job = _job_dir(tmp_path, request)

    envelope = core.run_step("bake", request, job)

    assert envelope["ok"] is True, envelope["error"]
    assert envelope["outputs"]["bake"]["desktop_textures"]
    assert Path(envelope["outputs"]["blend"]).is_file()


def _unbaked_crate_on_the_floor() -> None:
    """An authored crate from the bake fixtures, lifted so its base sits at z=0 (contract pivot)."""
    collection = build_asset("Crate", [procedural_material("Authored")])
    for vertex in collection.objects["SM_Crate"].data.vertices:
        vertex.co.z += 0.5


def test_variants_export_and_reimport_chain_from_a_compliant_asset(
    core: Any, tmp_path: Path
) -> None:
    # The compliant fixture has UV Map nodes on every image, which contract section 4 requires.
    # Bake output leaves image vectors unlinked (bake_core/rewire.py), so the export gate
    # rejects it; see test_export_gate_rejects_bake_output_without_uv_map_nodes.
    build_crate()
    request = _request(tmp_path)
    job = _job_dir(tmp_path, request)

    variants = core.run_step("variants", request, job)
    _record(job, variants)
    assert variants["ok"] is True, variants["error"]
    assert variants["outputs"]["tris"]["Mobile"]["lod_levels"] >= 1

    export = core.run_step("export", request, job)
    _record(job, export)
    assert export["ok"] is True, export["error"]
    pre_report = json.loads(
        Path(export["outputs"]["variants"]["Desktop"]["pre_report"]).read_text(encoding="utf-8")
    )
    assert pre_report["passed"] is True, pre_report["findings"]
    assert export["outputs"]["exported"] is True, export["summary"]
    for variant in ("Desktop", "Mobile"):
        assert Path(export["outputs"]["variants"][variant]["dir"], "SM_Crate.fbx").is_file()

    reimport = _run_entry(None, ["reimport", "--job-dir", str(job)], factory_startup=True)

    assert reimport.returncode == 0, reimport.stderr[-2000:]
    envelope = json.loads((job / "reimport.json").read_text(encoding="utf-8"))
    assert envelope["ok"] is True, envelope["error"]
    desktop = json.loads(Path(envelope["outputs"]["reports"]["Desktop"]).read_text("utf-8"))
    assert desktop["kind"] == "reimport"
    assert desktop["passed"] is True, desktop["findings"]


def test_reimport_of_the_decimated_mobile_variant_passes(core: Any, tmp_path: Path) -> None:
    build_crate()
    request = _request(tmp_path)
    job = _job_dir(tmp_path, request)
    _record(job, core.run_step("variants", request, job))
    _record(job, core.run_step("export", request, job))

    reimport = _run_entry(None, ["reimport", "--job-dir", str(job)], factory_startup=True)

    assert reimport.returncode == 0, reimport.stderr[-2000:]
    envelope = json.loads((job / "reimport.json").read_text(encoding="utf-8"))
    mobile = json.loads(Path(envelope["outputs"]["reports"]["Mobile"]).read_text("utf-8"))
    assert mobile["passed"] is True, mobile["findings"]


def test_bake_output_passes_the_export_gate_with_uv_map_nodes(core: Any, tmp_path: Path) -> None:
    # #67 bake output links every image Vector to a UV Map node, which contract section 4
    # (material.uv_coordinates) requires, so the export gate passes.
    _unbaked_crate_on_the_floor()
    request = _request(tmp_path, budgets_path=budgets_file(tmp_path))
    job = _job_dir(tmp_path, request)
    _record(job, core.run_step("bake", request, job))
    _record(job, core.run_step("variants", request, job))

    export = core.run_step("export", request, job)

    assert export["ok"] is True
    assert export["outputs"]["exported"] is True
    pre_report = json.loads(
        Path(export["outputs"]["variants"]["Desktop"]["pre_report"]).read_text(encoding="utf-8")
    )
    assert pre_report["passed"] is True, pre_report["findings"]


def test_entry_runs_validate_headless_and_writes_the_envelope(tmp_path: Path) -> None:
    build_crate()
    blend = _save(tmp_path / "crate.blend")
    job = _job_dir(tmp_path, _request(tmp_path))

    completed = _run_entry(blend, ["validate", "--job-dir", str(job)])

    assert completed.returncode == 0, completed.stderr[-2000:]
    envelope = json.loads((job / "validate.json").read_text(encoding="utf-8"))
    assert envelope["ok"] is True
    assert "NMG_PROGRESS " in completed.stdout


def test_entry_exits_one_with_a_collection_error_envelope(tmp_path: Path) -> None:
    build_crate()
    blend = _save(tmp_path / "crate.blend")
    job = _job_dir(tmp_path, _request(tmp_path, collection="Missing"))

    completed = _run_entry(blend, ["validate", "--job-dir", str(job)])

    assert completed.returncode == 1
    envelope = json.loads((job / "validate.json").read_text(encoding="utf-8"))
    assert envelope["error"]["code"] == "finalize.collection_not_found"


def _run_session(op: str, payload: dict[str, Any], live: Path, tmp_path: Path) -> dict[str, Any]:
    """Run finalize_session.py against the open file live, as the MCP exec call does."""
    driver = tmp_path / f"driver-{op}.py"
    full = {"addon_dir": str(ADDON_DIR), **payload}
    driver.write_text(
        f"NMG_OP = {op!r}\nNMG_PAYLOAD = {full!r}\n"
        f"exec(compile(open({str(SESSION)!r}).read(), {str(SESSION)!r}, 'exec'))\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [bpy.app.binary_path, "--background", str(live), "--python", str(driver)],
        capture_output=True,
        text=True,
        check=False,
        timeout=900,
    )
    assert completed.returncode == 0, completed.stderr[-2000:]
    result_lines = [line for line in completed.stdout.splitlines() if "NMG_RESULT " in line]
    assert len(result_lines) == 1, completed.stdout[-2000:]
    return json.loads(result_lines[0].split("NMG_RESULT ", 1)[1])


def test_session_checkpoint_prints_one_result_line(core: Any, tmp_path: Path) -> None:
    build_crate()
    expected = core.content_hash("Crate")
    live = _save(tmp_path / "live.blend")
    checkpoint = tmp_path / "checkpoint.blend"

    result = _run_session(
        "checkpoint",
        {"collection": "Crate", "path": str(checkpoint)},
        live,
        tmp_path,
    )

    assert result == {"hash": expected, "ok": True, "path": str(checkpoint)}
    assert checkpoint.is_file()


def test_session_load_back_replaces_the_open_scene(core: Any, tmp_path: Path) -> None:
    build_crate()
    checkpoint_hash = core.content_hash("Crate")
    live = _save(tmp_path / "live.blend")
    bpy.data.objects["SM_Crate"].data.vertices[0].co.x += 0.25
    result_hash = core.content_hash("Crate")
    result = _save(tmp_path / "result.blend")

    outcome = _run_session(
        "load_back",
        {
            "result_blend": str(result),
            "collection": "Crate",
            "expected_hash": checkpoint_hash,
        },
        live,
        tmp_path,
    )

    assert outcome == {"hash": result_hash, "loaded": True, "ok": True}


def test_load_back_replaces_the_session_asset_and_moves_the_hash(core: Any, tmp_path: Path) -> None:
    build_crate()
    bpy.data.objects["SM_Crate"].data.vertices[0].co.x += 0.25
    result_hash = core.content_hash("Crate")
    result = _save(tmp_path / "result.blend")
    clear_scene()
    build_crate()
    checkpoint_hash = core.content_hash("Crate")
    assert checkpoint_hash != result_hash

    outcome = core.load_back(str(result), "Crate", checkpoint_hash)

    assert outcome == {"loaded": True, "hash": result_hash}
    assert core.content_hash("Crate") == result_hash
    assert _leftover_old_names() == []


def test_load_back_refuses_when_the_session_changed_after_the_checkpoint(
    core: Any, tmp_path: Path
) -> None:
    build_crate()
    checkpoint_hash = core.content_hash("Crate")
    result = _save(tmp_path / "result.blend")
    bpy.data.objects["SM_Crate"].data.vertices[0].co.x += 0.5
    edited_hash = core.content_hash("Crate")
    edited_object = bpy.data.objects["SM_Crate"].as_pointer()

    outcome = core.load_back(str(result), "Crate", checkpoint_hash)

    assert outcome == {"loaded": False, "reason": "session_changed"}
    assert core.content_hash("Crate") == edited_hash
    assert bpy.data.objects["SM_Crate"].as_pointer() == edited_object


def test_load_back_rejects_a_result_without_the_asset_and_leaves_the_session(
    core: Any, tmp_path: Path
) -> None:
    build_crate()
    expected = core.content_hash("Crate")
    clear_scene()
    other = bpy.data.collections.new("Other")
    bpy.context.scene.collection.children.link(other)
    result = _save(tmp_path / "other.blend")
    clear_scene()
    build_crate()

    with pytest.raises(core.LoadBackError) as raised:
        core.load_back(str(result), "Crate", expected)

    assert raised.value.code == "finalize.load_back_failed"
    assert core.content_hash("Crate") == expected
    assert _leftover_old_names() == []


def test_load_back_restores_the_session_when_it_fails_after_appending(
    core: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    build_crate()
    before = core.content_hash("Crate")
    names_before = sorted(obj.name for obj in bpy.data.objects)
    bpy.data.objects["SM_Crate"].data.vertices[0].co.x += 0.25
    result = _save(tmp_path / "result.blend")
    bpy.data.objects["SM_Crate"].data.vertices[0].co.x -= 0.25
    load_back_module = importlib.import_module(f"{core.__name__}.load_back")

    def fail_after_append(_renamed: Any) -> None:
        raise RuntimeError("simulated failure after append")

    monkeypatch.setattr(load_back_module, "_remove_old", fail_after_append)
    with pytest.raises(core.LoadBackError, match="simulated failure after append"):
        core.load_back(str(result), "Crate", before)

    assert core.content_hash("Crate") == before
    assert sorted(obj.name for obj in bpy.data.objects) == names_before
    assert sorted(collection.name for collection in bpy.data.collections) == [
        "Crate",
        "Crate_Mobile",
    ]
    assert _leftover_old_names() == []
