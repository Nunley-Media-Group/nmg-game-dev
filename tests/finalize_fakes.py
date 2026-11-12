"""In-process fakes for the finalize pipeline (#69).

``FakeStepRunner`` executes each Blender step in the test process.  It writes the same files and
returns the envelope ``scripts/blender/finalize_entry.py`` would, so the real orchestrator,
cache, gates, and envelope handling all run.  ``FakeBlenderSession`` and ``FakeUnrealRunner`` stand
in for the live session and the Unreal MCP.  Import them as ``from finalize_fakes import ...``; the
``tests`` directory is on the pytest pythonpath.
"""

from __future__ import annotations

import ast
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from nmg_game_dev.pipeline import FinalizeClients, jobs
from nmg_game_dev.pipeline.request import FinalizeRequest

Failure = tuple[str, str, str]

ASSET_TEXTURES_BYTES = {"desktop": 4096, "mobile": 1024}


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
        """Probe the fake rig's clips, or write the named clips' FBX files and records."""
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
            file_name = f"A_{request.collection}_{name}.fbx"
            # The FBX bytes follow the clip's hash, as a real export does when the clip changes.
            (folder / file_name).write_bytes(f"fbx {name} {hashes.get(str(name), '')}".encode())
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
            (directory / f"SM_{request.collection}.fbx").write_bytes(b"fbx")
            pre_report = job_dir / f"export.pre-report-{variant}.json"
            _write_json(pre_report, self._report("contract", "export"))
            variants[variant] = {"dir": str(directory), "pre_report": str(pre_report)}
        sidecar = folder / "nmg-variants.json"
        _write_json(sidecar, {"asset": request.collection})
        return {"variants": variants, "sidecar": str(sidecar)}


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


class FakeUnrealRunner:
    """An Unreal MCP stand-in that records each import and replies with ``NMG_RESULT``.

    The PIE preflight (#149) is answered separately: each check consumes the next entry of
    ``pie_replies`` (``True`` means PIE is on), and checks after the list is spent report no PIE.
    PIE checks are counted in ``pie_checks`` and are not recorded in ``codes``.

    Parameters:
        result: The result object to print.  ``ok`` defaults to true.
        raises: An exception to raise instead of replying.
        pie_replies: The PIE state reported by successive PIE checks.
    """

    def __init__(
        self,
        *,
        result: Mapping[str, Any] | None = None,
        raises: Exception | None = None,
        events: list[str] | None = None,
        pie_replies: Sequence[bool] = (),
    ) -> None:
        # An empty snapshot has no mesh parts to compare, so the pivot check passes on this reply.
        self.result = dict(result) if result is not None else {"ok": True, "static_meshes": {}}
        self.raises = raises
        self.events = events
        self.codes: list[str] = []
        self.pie_replies = list(pie_replies)
        self.pie_checks = 0

    def execute_python_code(self, code: str, *, timeout: float | None = None) -> str:
        if "is_in_play_in_editor" in code:
            self.pie_checks += 1
            pie = self.pie_replies.pop(0) if self.pie_replies else False
            return "NMG_RESULT " + json.dumps({"pie": pie})
        self.codes.append(code)
        if self.events is not None:
            self.events.append("import_ue")
        if self.raises is not None:
            raise self.raises
        return "NMG_RESULT " + json.dumps(self.result)


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
    unreal: FakeUnrealRunner | None = None,
) -> Callable[[Path], int]:
    """Return a launcher that runs a batch job in-process through ``make_router``'s router."""

    def launch(job_dir: Path) -> int:
        job = json.loads((job_dir / "job.json").read_text(encoding="utf-8"))
        requests = {
            str(item["collection"]): FinalizeRequest.model_validate(item) for item in job["items"]
        }
        jobs.run_job(
            job_dir,
            clients=FinalizeClients(blender=ItemBlender(), unreal=unreal or FakeUnrealRunner()),
            runner=make_router(requests),
        )
        return dead_pid()

    return launch


def dead_pid() -> int:
    """Return the PID of a process that has already exited."""
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait()
    return process.pid


class FakeAnimUnrealRunner:
    """An Unreal MCP stand-in for ``import_anims`` (#138).

    It decodes the PARAMS that ``build_anim_import_code`` embeds, applies the same checks as the UE
    program, and replies with the ``NMG_RESULT`` line the host reads.  Nothing is imported into a
    live editor.

    Parameters:
        skeletons: Skeleton asset paths that exist in the project.  Each character's own Desktop
            skeleton and each compatible target must be listed here.
        bones: Reference bone names per skeleton path.  A path not listed reads as ``["root"]``.
        frame_counts: Measured sampled key count per clip name.  Default: the expected count.
        skeleton_of: Measured skeleton path per clip name.  Default: the clip's own skeleton.
        present: AnimSequence paths that already exist before the call.
        stale: Asset names in the Animations folder that are no longer clips.
        error: Optional error text the program reports instead of a result.
    """

    def __init__(
        self,
        *,
        skeletons: Sequence[str],
        bones: Mapping[str, Sequence[str]] | None = None,
        frame_counts: Mapping[str, int] | None = None,
        skeleton_of: Mapping[str, str] | None = None,
        present: Sequence[str] = (),
        stale: Sequence[str] = (),
        error: str | None = None,
    ) -> None:
        self.skeletons = set(skeletons)
        self.bones = {path: list(names) for path, names in (bones or {}).items()}
        self.frame_counts = dict(frame_counts or {})
        self.skeleton_of = dict(skeleton_of or {})
        self.present = set(present)
        self.stale = list(stale)
        self.error = error
        self.codes: list[str] = []
        self.params: list[dict[str, Any]] = []
        self.imported: list[str] = []
        self.compatible: dict[str, list[str]] = {}

    def execute_python_code(self, code: str, *, timeout: float | None = None) -> str:
        self.codes.append(code)
        params = _decode_params(code)
        self.params.append(params)
        return "NMG_RESULT " + json.dumps(self._reply(params), sort_keys=True)

    def _names(self, path: str) -> list[str]:
        return self.bones.get(path, ["root"])

    def _reply(self, params: Mapping[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {
            "ok": False,
            "skeleton": params["skeleton"],
            "blocked": None,
            "clips": {},
            "mismatch": [],
            "stale": [],
            "compatible": [],
            "error": None,
        }
        if self.error is not None:
            result["error"] = self.error
            return result
        own = params["skeleton"]
        if own not in self.skeletons:
            result["blocked"] = {
                "code": "skeleton_not_found",
                "target": own,
                "path": own,
                "bones": [],
            }
            return result
        for target in params["compatible"]:
            path = target["skeleton"]
            if path not in self.skeletons:
                result["blocked"] = {
                    "code": "skeleton_not_found",
                    "target": target["name"],
                    "path": path,
                    "bones": [],
                }
                return result
            if self._names(path) != self._names(own):
                differing = sorted(set(self._names(path)) ^ set(self._names(own)))
                result["blocked"] = {
                    "code": "skeleton_mismatch",
                    "target": target["name"],
                    "path": path,
                    "bones": differing,
                }
                return result
        for clip in params["clips"]:
            if clip["import"] or clip["asset_path"] not in self.present:
                self.imported.append(clip["name"])
                self.present.add(clip["asset_path"])
            result["clips"][clip["name"]] = {
                "asset_path": clip["asset_path"],
                "skeleton": self.skeleton_of.get(clip["name"], own),
                "frame_count": self.frame_counts.get(clip["name"], clip["expected_frame_count"]),
                "imported": bool(clip["import"]),
            }
            measured = result["clips"][clip["name"]]
            if measured["skeleton"] != own:
                result["mismatch"].append(
                    {
                        "clip": clip["name"],
                        "field": "skeleton",
                        "expected": own,
                        "measured": measured["skeleton"],
                    }
                )
            if measured["frame_count"] != clip["expected_frame_count"]:
                result["mismatch"].append(
                    {
                        "clip": clip["name"],
                        "field": "frame_count",
                        "expected": clip["expected_frame_count"],
                        "measured": measured["frame_count"],
                    }
                )
        result["stale"] = [f"{params['anim_dir']}/{name}" for name in self.stale]
        if not result["mismatch"]:
            for target in params["compatible"]:
                for a, b in ((own, target["skeleton"]), (target["skeleton"], own)):
                    listed = self.compatible.setdefault(a, [])
                    if b not in listed:
                        listed.append(b)
                result["compatible"].append(target["skeleton"])
        result["ok"] = True
        return result


def _decode_params(code: str) -> dict[str, Any]:
    """Return the PARAMS literal that ``build_anim_import_code`` embeds, decoded."""
    line = next(line for line in code.splitlines() if line.startswith("PARAMS = json.loads("))
    decoded = ast.literal_eval(line[len("PARAMS = json.loads(") : -1])
    params: dict[str, Any] = json.loads(decoded)
    return params
