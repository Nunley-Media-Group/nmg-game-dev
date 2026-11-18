"""In-process fakes for the finalize pipeline (#69).

``FakeStepRunner`` executes each Blender step in the test process.  It writes the same files and
returns the envelope ``scripts/blender/finalize_entry.py`` would, so the real orchestrator,
cache, gates, and envelope handling all run.  ``FakeBlenderSession`` stands in for the live session,
and ``FinalizeGodot`` (a ``tests.godot_fakes.FakeGodotRunner``) for ``godot --headless`` (#249): it
creates the ``project.godot`` the import looks for and answers the finalize probes from the files
the export wrote.  Import them as ``from tests.finalize_fakes import ...``.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from nmg_game_dev.godot.runner import CommandResult
from nmg_game_dev.pipeline import FinalizeClients, jobs
from nmg_game_dev.pipeline.request import FinalizeRequest
from tests.godot_fakes import FakeGodotRunner

Failure = tuple[str, str, str]

ASSET_TEXTURES_BYTES = {"desktop": 4096, "mobile": 1024}
VARIANT_TRIS = {"Desktop": 1200, "Mobile": 800}
PROJECT_FILE = 'config_version=5\n\n[application]\n\nconfig/name="Fixture"\n'


def asset_meshes(name: str, variant: str) -> list[dict[str, Any]]:
    """The ``nmg-asset.json`` ``meshes`` the fake export writes for one variant."""
    return [
        {
            "name": name,
            "tris": VARIANT_TRIS[variant],
            "material_slots": 1,
            "bounds": {"min": [-0.5, 0.0, -0.5], "max": [0.5, 1.0, 0.5]},
        }
    ]


def contract_report(
    kind: str,
    asset: str,
    asset_class: str,
    *,
    passed: bool = True,
    findings: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Return a contract or re-import report as the Blender side writes it."""
    return {
        "kind": kind,
        "asset": asset,
        "class": asset_class,
        "passed": passed,
        "findings": findings or [],
        "snapshot": {},
    }


def default_bake_result(job_dir: Path, collection: str, asset_class: str) -> dict[str, Any]:
    """Return a bake_core-shaped success result with paths under ``job_dir``."""
    out = job_dir / "bake"
    return {
        "kind": "bake",
        "asset": collection,
        "class": asset_class,
        "mode": "unique",
        "merged": False,
        "cache_hit": False,
        "device": "CPU",
        "manifest_path": str(out / "bake.json"),
        "desktop_dir": str(out / "Desktop"),
        "mobile_dir": str(out / "Mobile"),
        "desktop_textures": [str(out / "Desktop" / f"T_{collection}_Body_BC.png")],
        "mobile_textures": [str(out / "Mobile" / f"T_{collection}_Body_BC.png")],
        "texture_bytes_desktop": ASSET_TEXTURES_BYTES["desktop"],
        "texture_bytes_mobile": ASSET_TEXTURES_BYTES["mobile"],
        "materials": [{"name": f"M_{collection}_Body", "source": ["Wood"]}],
        "proof": {
            "pre_bake": str(out / "pre.png"),
            "baked": str(out / "baked.png"),
            "mean_abs_diff": 0.012,
            "outlier_ratio": 0.0,
        },
        "summary": f"Baked 1 material for {collection} ({asset_class}): Desktop 2048 px",
    }


class FakeStepRunner:
    """Runs Blender steps in-process and records every call.

    Parameters:
        request: The request being finalized.  The fake takes its collection, class, and export
            root from it.
        bake_result: Optional bake_core-shaped result to return from the bake step.
        failures: Optional mapping of step name to ``(code, message, remediation)``.  That step
            returns a failing envelope.
        hash_value: The content hash returned by ``hash``.
        clips: Optional rig clips the ``export_anims`` probe reports, each a mapping with ``name``,
            ``hash``, and optionally ``valid_name`` (default true) and ``source`` (default
            ``"authored"``).  Empty means an unrigged asset.

    The export writes ``<Variant>/<Name>.glb`` and ``<Variant>/nmg-asset.json`` (with ``meshes``)
    for both variants, plus ``nmg-variants.json``.  The clip export writes
    ``Animations/A_<Name>_<Clip>.glb`` spanning frames 1 to 10 at 30 fps.
    """

    def __init__(
        self,
        request: FinalizeRequest,
        *,
        bake_result: Mapping[str, Any] | None = None,
        failures: Mapping[str, Failure] | None = None,
        failing_reports: frozenset[str] = frozenset(),
        hash_value: str = "asset-hash-0",
        events: list[str] | None = None,
        clips: Sequence[Mapping[str, Any]] = (),
    ) -> None:
        self.request = request
        self.bake_result = dict(bake_result) if bake_result is not None else None
        self.failures = dict(failures or {})
        self.failing_reports = failing_reports
        self.hash_value = hash_value
        self.events = events
        self.clips = [dict(clip) for clip in clips]
        self.calls: list[dict[str, Any]] = []

    def steps_run(self) -> list[str]:
        """Return the Blender steps that ran, in order.  ``hash`` calls are not included."""
        return [str(call["step"]) for call in self.calls if call["step"] != "hash"]

    def hash(self, *, job_dir: Path, in_blend: Path) -> str:
        self.calls.append({"step": "hash", "in_blend": str(in_blend)})
        return self.hash_value

    def run_step(
        self,
        step: str,
        *,
        job_dir: Path,
        in_blend: Path | None,
        inputs: Mapping[str, Any] | None = None,
        on_progress: Any = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "step": step,
                "in_blend": None if in_blend is None else str(in_blend),
                "inputs": inputs,
            }
        )
        if on_progress is not None:
            on_progress({"state": "running", "step": step, "progress": 0.5, "message": "fake"})
        if self.events is not None:
            self.events.append(step)
        job_dir.mkdir(parents=True, exist_ok=True)
        if step in self.failures:
            code, message, remediation = self.failures[step]
            return _envelope(
                step,
                ok=False,
                outputs={},
                error={"code": code, "message": message, "remediation": remediation},
            )
        return _envelope(step, ok=True, outputs=self._outputs(step, job_dir, inputs))

    def _outputs(
        self, step: str, job_dir: Path, inputs: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        request = self.request
        name = request.collection
        asset_class = request.asset_class
        if step == "validate":
            report = job_dir / "validate.report.json"
            _write_json(report, self._report("contract", step))
            return {"report": str(report)}
        if step == "bake":
            blend = job_dir / "bake.blend"
            blend.write_bytes(b"baked")
            result = self.bake_result or default_bake_result(job_dir, name, asset_class)
            return {"blend": str(blend), "bake": dict(result)}
        if step == "variants":
            blend = job_dir / "variants.blend"
            blend.write_bytes(b"variants")
            return {
                "blend": str(blend),
                "tris": {"Desktop": {"LOD0": 1200}, "Mobile": {"LOD0": 800}},
            }
        if step == "export":
            return self._export_outputs(job_dir)
        if step == "export_anims":
            return self._anim_outputs(job_dir, inputs)
        if step == "reimport":
            assert inputs is not None, "reimport receives the export variants as inputs"
            reports: dict[str, str] = {}
            for variant in ("Desktop", "Mobile"):
                path = job_dir / f"reimport.{variant}.json"
                _write_json(path, self._report("reimport", step))
                reports[variant] = str(path)
            return {"reports": reports}
        raise AssertionError(f"FakeStepRunner has no outputs for step {step!r}")

    def _report(self, kind: str, step: str) -> dict[str, Any]:
        """Return a passing report, or a failing one when ``step`` is in ``failing_reports``."""
        if step not in self.failing_reports:
            return contract_report(kind, self.request.collection, self.request.asset_class)
        finding = {
            "rule": "transform.root_applied",
            "target": self.request.collection,
            "message": "the root transform is not applied",
            "remediation": "Apply all transforms on the collection, then rerun.",
        }
        return contract_report(
            kind,
            self.request.collection,
            self.request.asset_class,
            passed=False,
            findings=[finding],
        )

    def _anim_outputs(self, job_dir: Path, inputs: Mapping[str, Any] | None) -> dict[str, Any]:
        """Probe the fake rig's clips, or write the named clips' .glb files and records."""
        request = self.request
        if inputs is None or inputs.get("mode") == "probe":
            return {
                "clips": [
                    {
                        "name": str(clip["name"]),
                        "hash": str(clip["hash"]),
                        "valid_name": bool(clip.get("valid_name", True)),
                    }
                    for clip in self.clips
                ],
                "options": "fake-anim-options",
            }
        folder = request.export_root / request.category / request.collection / "Animations"
        folder.mkdir(parents=True, exist_ok=True)
        sources = {str(clip["name"]): clip.get("source", "authored") for clip in self.clips}
        hashes = {str(clip["name"]): str(clip["hash"]) for clip in self.clips}
        records = []
        for name in inputs.get("clips", []):
            file_name = f"A_{request.collection}_{name}.glb"
            # The .glb bytes follow the clip's hash, as a real export does when the clip changes.
            (folder / file_name).write_bytes(f"glb {name} {hashes.get(str(name), '')}".encode())
            records.append(
                {
                    "name": name,
                    "file": file_name,
                    "frame_start": 1,
                    "frame_end": 10,
                    "frame_count": 10,
                    "fps": 30.0,
                    "source": sources.get(str(name), "authored"),
                }
            )
        return {"clips": records}

    def _export_outputs(self, job_dir: Path) -> dict[str, Any]:
        request = self.request
        folder = request.export_root / request.category / request.collection
        variants: dict[str, Any] = {}
        for variant in ("Desktop", "Mobile"):
            directory = folder / variant
            directory.mkdir(parents=True, exist_ok=True)
            (directory / f"{request.collection}.glb").write_bytes(f"glb {variant}".encode())
            _write_json(
                directory / "nmg-asset.json",
                {
                    "class": request.asset_class,
                    "tris": VARIANT_TRIS[variant],
                    "max_texture_px": 2048 if variant == "Desktop" else 1024,
                    "materials": 1,
                    "meshes": asset_meshes(request.collection, variant),
                },
            )
            pre_report = job_dir / f"export.pre-report-{variant}.json"
            _write_json(pre_report, self._report("contract", "export"))
            variants[variant] = {"dir": str(directory), "pre_report": str(pre_report)}
        sidecar = folder / "nmg-variants.json"
        _write_json(sidecar, self._sidecar())
        return {"variants": variants, "sidecar": str(sidecar)}

    def _sidecar(self) -> dict[str, Any]:
        """The ``nmg-variants.json`` payload.  Subclasses add terrain or material-variant keys."""
        name = self.request.collection
        return {
            "asset": name,
            "desktop": {"path": f"Desktop/{name}.glb"},
            "mobile": {"path": f"Mobile/{name}.glb"},
        }


class FakeBlenderSession:
    """A live session that records checkpoints and load-back calls.

    Parameters:
        hash_value: The content hash returned at checkpoint.
        load_result: The reply to ``load_back``.  Defaults to a successful load that moves the
            hash to ``post-load-hash``.
    """

    def __init__(
        self,
        *,
        hash_value: str = "asset-hash-0",
        load_result: Mapping[str, Any] | None = None,
        events: list[str] | None = None,
    ) -> None:
        self.hash_value = hash_value
        self.load_result = dict(load_result) if load_result is not None else None
        self.events = events
        self.checkpoints: list[str] = []
        self.load_backs: list[dict[str, Any]] = []

    def checkpoint(self, *, collection: str, path: Path) -> str:
        path.write_bytes(b"session-checkpoint")
        self.checkpoints.append(collection)
        return self.hash_value

    def load_back(
        self,
        *,
        result_blend: Path,
        collection: str,
        expected_hash: str,
        suffixes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        self.load_backs.append(
            {
                "result_blend": str(result_blend),
                "collection": collection,
                "expected_hash": expected_hash,
                "suffixes": None if suffixes is None else list(suffixes),
            }
        )
        if self.events is not None:
            self.events.append("load_back")
        if self.load_result is not None:
            return dict(self.load_result)
        return {"ok": True, "loaded": True, "hash": "post-load-hash"}


class FakeReduceRunner:
    """Runs the reduce step in-process (#139): writes reduce.blend and the reduce.json envelope.

    Parameters:
        result: The ``reduce_asset`` result dict the step reports.  Defaults to a reduced asset.
        failure: Optional ``(code, message, remediation)``.  The step then reports a failing
            envelope instead.
        hash_value: The content hash returned by ``hash``.
    """

    def __init__(
        self,
        *,
        result: Mapping[str, Any] | None = None,
        failure: Failure | None = None,
        hash_value: str = "asset-hash-0",
    ) -> None:
        self.result = dict(result) if result is not None else default_reduce_result()
        self.failure = failure
        self.hash_value = hash_value
        self.calls: list[dict[str, Any]] = []

    def hash(self, *, job_dir: Path, in_blend: Path) -> str:
        self.calls.append({"step": "hash", "in_blend": str(in_blend)})
        return self.hash_value

    def run_step(
        self,
        step: str,
        *,
        job_dir: Path,
        in_blend: Path | None,
        inputs: Mapping[str, Any] | None = None,
        on_progress: Any = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "step": step,
                "in_blend": None if in_blend is None else str(in_blend),
                "inputs": inputs,
            }
        )
        if on_progress is not None:
            on_progress({"state": "running", "step": step, "progress": 0.5, "message": "fake"})
        job_dir.mkdir(parents=True, exist_ok=True)
        blend = job_dir / "reduce.blend"
        blend.write_bytes(b"reduced")
        if self.failure is not None:
            code, message, remediation = self.failure
            envelope = _envelope(
                step,
                ok=False,
                outputs={},
                error={"code": code, "message": message, "remediation": remediation},
            )
        else:
            envelope = _envelope(
                step, ok=True, outputs={"result": dict(self.result), "blend": str(blend)}
            )
        _write_json(job_dir / f"{step}.json", envelope)
        return envelope


def default_reduce_result() -> dict[str, Any]:
    """A reduced asset's ``reduce_asset`` result, with the FR11 fields the host passes through."""
    return {
        "state": "reduced",
        "collection": "Crate",
        "asset_class": "standard_prop",
        "budget": 3000,
        "parts": {
            "Body": {
                "source_tris": 20000,
                "target": 3000,
                "final_tris": 2990,
                "cage_extrusion": 0.03,
                "max_ray_distance": 0.1,
                "unbaked_share": 0.0,
            }
        },
        "total_tris": 2990,
        "textures": {"BC": "BC.png", "N": "N.png", "ORM": "ORM.png"},
        "texture_px": 256,
        "device": "CPU",
        "summary": "Reduced Crate (standard_prop) to 2990 of 3000 triangles",
    }


def _envelope(
    step: str,
    *,
    ok: bool,
    outputs: Mapping[str, Any],
    error: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "step": step,
        "ok": ok,
        "summary": f"{step} fake",
        "outputs": dict(outputs),
        "error": dict(error) if error is not None else None,
    }


def _write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


class ItemBlender(FakeBlenderSession):
    """A live session whose content hash follows the collection, so batch items cache apart."""

    def checkpoint(self, *, collection: str, path: Path) -> str:
        path.write_bytes(b"session-checkpoint")
        self.checkpoints.append(collection)
        return f"hash-{collection}"

    def load_back(
        self,
        *,
        result_blend: Path,
        collection: str,
        expected_hash: str,
        suffixes: Sequence[str] | None = None,
    ) -> dict[str, Any]:
        return {"ok": True, "loaded": True, "hash": f"post-{expected_hash}"}


class BatchRouter:
    """Routes each batch item's steps to a ``FakeStepRunner`` for that item's request (#149).

    ``on_step`` runs before every step with the item's directory, so a test can read the job while
    it runs.  ``order`` lists the collections in the order they started.
    """

    def __init__(
        self,
        requests: Mapping[str, FinalizeRequest],
        *,
        failures: Mapping[str, Mapping[str, Failure]] | None = None,
        on_step: Callable[[Path, str], None] | None = None,
    ) -> None:
        per_item = failures or {}
        self._runners = {
            name: FakeStepRunner(request, failures=per_item.get(name))
            for name, request in requests.items()
        }
        self.on_step = on_step
        self.order: list[str] = []

    def hash(self, *, job_dir: Path, in_blend: Path) -> str:
        return self._runner(job_dir).hash(job_dir=job_dir, in_blend=in_blend)

    def run_step(
        self,
        step: str,
        *,
        job_dir: Path,
        in_blend: Path | None,
        inputs: Mapping[str, Any] | None = None,
        on_progress: Any = None,
    ) -> dict[str, Any]:
        name = _collection_of(job_dir)
        if name not in self.order:
            self.order.append(name)
        if self.on_step is not None:
            self.on_step(job_dir, step)
        return self._runner(job_dir).run_step(
            step, job_dir=job_dir, in_blend=in_blend, inputs=inputs, on_progress=on_progress
        )

    def _runner(self, job_dir: Path) -> FakeStepRunner:
        return self._runners[_collection_of(job_dir)]


def _collection_of(item_dir: Path) -> str:
    """Return the collection named by an item directory, ``items/<index>-<collection>``."""
    return item_dir.name.split("-", 1)[1]


def batch_launcher(
    make_router: Callable[[dict[str, FinalizeRequest]], BatchRouter],
    *,
    godot: FakeGodotRunner | None = None,
    project: Path | None = None,
) -> Callable[[Path], int]:
    """Return a launcher that runs a batch job in-process through ``make_router``'s router.

    Without ``godot``, a ``FinalizeGodot`` for ``project`` (default: the first item's export root's
    parent) answers the import.
    """

    def launch(job_dir: Path) -> int:
        job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        requests = {
            str(item["collection"]): FinalizeRequest.model_validate(item) for item in job["items"]
        }
        runner = godot
        if runner is None:
            first = next(iter(requests.values()))
            runner = FinalizeGodot(project or first.export_root.parent)
        jobs.run_job(
            job_dir,
            clients=FinalizeClients(blender=ItemBlender(), godot=runner),
            runner=make_router(requests),
        )
        return dead_pid()

    return launch


def dead_pid() -> int:
    """Return the PID of a process that has already exited."""
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


class FinalizeGodot(FakeGodotRunner):
    """``godot --headless`` for finalize tests: a project plus probes answered from the export.

    Creating one writes ``<project>/project.godot`` when it is missing, so ``find_project`` finds it
    above an export root inside ``project``.  The default probe answers:

    - ``probe_asset.gd`` echoes the probed variant's ``nmg-asset.json`` ``meshes``, so an unchanged
      export matches.  ``mesh_edits`` maps a variant (``Desktop``/``Mobile``) to a function that
      changes the echoed meshes, to script a mismatch.
    - ``probe_anims.gd`` measures each requested clip as ``frame_count`` 9 (frames 1 to 10 at 30
      fps) or ``frame_counts[name]``, animating ``clip_bones`` (default ``["root"]``), and absent
      when listed in ``missing_clips``.  A skeleton scene is found when its file exists, with
      ``skeleton_bones[<res path>]`` (default ``["root"]``) as its bones.
    - ``probe_terrain.gd`` lists one ``Mesh`` node per chunk, and for a scene reports the chunk
      instances and the ``map_data`` range it reads back from the written ``.tscn``; the mesh range
      equals that range unless ``mesh_range`` overrides it.

    ``responses`` replaces any default.  ``events`` (when given) records ``import`` for each
    ``--import`` and the probe file name for each probe.
    """

    def __init__(
        self,
        project: Path,
        *,
        responses: Mapping[str, Any] | None = None,
        import_errors: bool = False,
        events: list[str] | None = None,
        mesh_edits: Mapping[str, Callable[[list[dict[str, Any]]], list[dict[str, Any]]]]
        | None = None,
        frame_counts: Mapping[str, int] | None = None,
        clip_bones: Sequence[str] = ("root",),
        missing_clips: Sequence[str] = (),
        skeleton_bones: Mapping[str, Sequence[str]] | None = None,
        mesh_range: tuple[float, float] | None = None,
    ) -> None:
        self.project = project
        project.mkdir(parents=True, exist_ok=True)
        marker = project / "project.godot"
        if not marker.is_file():
            marker.write_text(PROJECT_FILE, encoding="utf-8")
        self.events = events
        self.mesh_edits = dict(mesh_edits or {})
        self.frame_counts = dict(frame_counts or {})
        self.clip_bones = list(clip_bones)
        self.missing_clips = set(missing_clips)
        self.skeleton_bones = {key: list(value) for key, value in (skeleton_bones or {}).items()}
        self.mesh_range = mesh_range
        defaults: dict[str, Any] = {
            "probe_asset.gd": self._asset,
            "probe_anims.gd": self._anims,
            "probe_terrain.gd": self._terrain,
        }
        super().__init__({**defaults, **dict(responses or {})}, import_errors=import_errors)

    def run(
        self,
        args: Sequence[str],
        *,
        project: Path,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        if self.events is not None:
            argv = list(args)
            self.events.append("import" if argv[:1] == ["--import"] else Path(argv[1]).name)
        return super().run(args, project=project, timeout=timeout, env=env)

    def file(self, resource: str) -> Path:
        """Return the file a ``res://`` path names in this project."""
        return self.project / resource.removeprefix("res://")

    def probed_clips(self) -> list[list[str]]:
        """Return the clip names each ``probe_anims.gd`` call asked for, in call order."""
        return [
            [str(clip["name"]) for clip in params["clips"]]
            for params in self.params
            if "skeletons" in params
        ]

    def _asset(self, params: dict[str, Any]) -> dict[str, Any]:
        glb = self.file(str(params["glb"]))
        sidecar = json.loads((glb.parent / "nmg-asset.json").read_text(encoding="utf-8"))
        meshes = [dict(mesh) for mesh in sidecar["meshes"]]
        edit = self.mesh_edits.get(glb.parent.name)
        return {"meshes": edit(meshes) if edit is not None else meshes}

    def _anims(self, params: dict[str, Any]) -> dict[str, Any]:
        clips: dict[str, Any] = {}
        for clip in params["clips"]:
            name = str(clip["name"])
            if name in self.missing_clips:
                continue
            clips[name] = {
                "animation": name,
                "frame_count": self.frame_counts.get(name, 9),
                "bones": list(self.clip_bones),
            }
        skeletons: dict[str, Any] = {}
        for resource in params["skeletons"]:
            found = self.file(str(resource)).is_file()
            bones = self.skeleton_bones.get(str(resource), ["root"]) if found else []
            skeletons[str(resource)] = {"found": found, "bones": bones}
        return {"clips": clips, "skeletons": skeletons}

    def _terrain(self, params: dict[str, Any]) -> dict[str, Any]:
        if params.get("mode") == "meshes":
            return {"meshes": {str(glb): ["Mesh"] for glb in params["glbs"]}}
        text = self.file(str(params["scene"])).read_text(encoding="utf-8")
        chunks = len(re.findall(r"^\[node name=\"[^\"]+\" parent=\"\.\" instance=", text, re.M))
        match = re.search(r"map_data = PackedFloat32Array\(([^)]*)\)", text)
        values = [float(item) for item in match.group(1).split(",")] if match else [0.0]
        low, high = min(values), max(values)
        mesh_low, mesh_high = self.mesh_range if self.mesh_range is not None else (low, high)
        return {
            "chunks": chunks,
            "height_min": low,
            "height_max": high,
            "mesh_height_min": mesh_low,
            "mesh_height_max": mesh_high,
        }


def write_height_png(path: Path, codes: Sequence[int], size: int) -> None:
    """Write a ``size`` x ``size`` 16-bit grayscale PNG holding ``codes`` row-major (filter 0)."""
    import struct
    import zlib

    rows = b"".join(
        b"\x00" + struct.pack(f">{size}H", *codes[row * size : (row + 1) * size])
        for row in range(size)
    )

    def chunk(kind: bytes, body: bytes) -> bytes:
        crc = zlib.crc32(kind + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", crc)

    header = struct.pack(">IIBBBBB", size, size, 16, 0, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def terrain_entry(
    variant: str,
    *,
    heightmap_px: int = 127,
    spacing_m: float = 1.0,
    height_min_m: float = 10.0,
    height_max_m: float = 40.0,
    layers: Sequence[str] = ("Grass", "Rock"),
) -> dict[str, Any]:
    """One variant's terrain entry in ``nmg-variants.json``."""
    side = (heightmap_px - 1) // 63
    return {
        "heightmap": f"{variant}/T_<Name>_Height.png",
        "splat": f"{variant}/T_<Name>_Splat.png",
        "chunks": [f"<Name>_Chunk_{row}_{col}.glb" for row in range(side) for col in range(side)],
        "chunk_quads": 63,
        "heightmap_px": heightmap_px,
        "spacing_m": spacing_m,
        "height_min_m": height_min_m,
        "height_max_m": height_max_m,
        "uv_tile_m": 8.0,
        "layers": list(layers),
        "max_texture_px": 2048 if variant == "Desktop" else 1024,
        "texture_bytes": 1024,
    }


class TerrainStepRunner(FakeStepRunner):
    """The Blender fake with a terrain export (#249 FR4).

    Each variant folder gets ``<Name>_Chunk_<r>_<c>.glb`` for a ``(heightmap_px - 1) / 63`` grid,
    ``T_<Name>_Height.png`` (a ramp from code 0 to 65535), ``T_<Name>_Splat.png`` and each layer's
    ``T_<Name>_<Layer>_{BC,N,ORM}.png``; ``nmg-variants.json`` holds ``terrain: true`` and the
    ``entries`` (default ``terrain_entry`` for both variants, Mobile at 2 m spacing).
    ``skip_chunks`` names chunk files to leave out.
    """

    def __init__(
        self,
        request: FinalizeRequest,
        *,
        entries: Mapping[str, Mapping[str, Any]] | None = None,
        skip_chunks: Sequence[str] = (),
        **kwargs: Any,
    ) -> None:
        super().__init__(request, **kwargs)
        self.entries = {
            key: dict(value)
            for key, value in (
                entries
                if entries is not None
                else {
                    "desktop": terrain_entry("Desktop"),
                    "mobile": terrain_entry("Mobile", spacing_m=2.0),
                }
            ).items()
        }
        self.skip_chunks = set(skip_chunks)

    def _export_outputs(self, job_dir: Path) -> dict[str, Any]:
        request = self.request
        name = request.collection
        folder = request.export_root / request.category / name
        variants: dict[str, Any] = {}
        for variant in ("Desktop", "Mobile"):
            directory = folder / variant
            directory.mkdir(parents=True, exist_ok=True)
            entry = self.entries.get(variant.lower())
            if entry is not None:
                size = int(entry["heightmap_px"])
                side = max(1, -(-(size - 1) // 63))
                for row in range(side):
                    for col in range(side):
                        chunk = f"{name}_Chunk_{row}_{col}.glb"
                        if chunk not in self.skip_chunks:
                            (directory / chunk).write_bytes(b"glb chunk")
                codes = [round(i / (size * size - 1) * 65535) for i in range(size * size)]
                write_height_png(directory / f"T_{name}_Height.png", codes, size)
                (directory / f"T_{name}_Splat.png").write_bytes(b"png")
                for layer in entry["layers"]:
                    for suffix in ("BC", "N", "ORM"):
                        (directory / f"T_{name}_{layer}_{suffix}.png").write_bytes(b"png")
            pre_report = job_dir / f"export.pre-report-{variant}.json"
            _write_json(pre_report, self._report("contract", "export"))
            variants[variant] = {"dir": str(directory), "pre_report": str(pre_report)}
        sidecar = folder / "nmg-variants.json"
        _write_json(sidecar, {"terrain": True, "name": name, "class": "terrain", **self.entries})
        return {"variants": variants, "sidecar": str(sidecar)}
