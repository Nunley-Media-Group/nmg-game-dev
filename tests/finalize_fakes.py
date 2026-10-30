"""In-process fakes for the finalize pipeline (#69).

``FakeStepRunner`` executes each Blender step in the test process.  It writes the same files and
returns the envelope ``scripts/blender/finalize_entry.py`` would, so the real orchestrator,
cache, gates, and envelope handling all run.  ``FakeBlenderSession`` and ``FakeUnrealRunner`` stand
in for the live session and the Unreal MCP.  Import them as ``from finalize_fakes import ...``; the
``tests`` directory is on the pytest pythonpath.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

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
    ) -> None:
        self.request = request
        self.bake_result = dict(bake_result) if bake_result is not None else None
        self.failures = dict(failures or {})
        self.failing_reports = failing_reports
        self.hash_value = hash_value
        self.events = events
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
    ) -> dict[str, Any]:
        self.load_backs.append(
            {
                "result_blend": str(result_blend),
                "collection": collection,
                "expected_hash": expected_hash,
            }
        )
        if self.events is not None:
            self.events.append("load_back")
        if self.load_result is not None:
            return dict(self.load_result)
        return {"ok": True, "loaded": True, "hash": "post-load-hash"}


class FakeUnrealRunner:
    """An Unreal MCP stand-in that records each UE Python call and replies with ``NMG_RESULT``.

    Parameters:
        result: The result object to print.  ``ok`` defaults to true.
        raises: An exception to raise instead of replying.
    """

    def __init__(
        self,
        *,
        result: Mapping[str, Any] | None = None,
        raises: Exception | None = None,
        events: list[str] | None = None,
    ) -> None:
        # An empty snapshot has no mesh parts to compare, so the pivot check passes on this reply.
        self.result = dict(result) if result is not None else {"ok": True, "static_meshes": {}}
        self.raises = raises
        self.events = events
        self.codes: list[str] = []

    def execute_python_code(self, code: str) -> str:
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
