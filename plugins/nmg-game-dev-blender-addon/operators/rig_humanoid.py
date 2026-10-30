from __future__ import annotations

import json
from pathlib import Path

import bpy

from ..rig_core import rig_humanoid as build_rig
from ..rig_core.outcome import STATUS_FALLBACK, fail
from ..utils.logging import log_operator_result
from ._common import store_rig_result

_OP_NAME = "nmggamedev.rig_humanoid"


class NMGGAMEDEV_OT_rig_humanoid(bpy.types.Operator):
    bl_idname = "nmggamedev.rig_humanoid"
    bl_label = "Rig humanoid"
    bl_description = (
        "Build the deform-only UE5 Mannequin armature SK_<Name> from landmarks and skin the "
        "collection's meshes with automatic weights"
    )
    bl_options = {"REGISTER", "UNDO"}

    collection_name: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Asset collection",
        description="Collection <Name> that holds the root mesh SM_<Name>",
        default="",
    )
    body_type: bpy.props.EnumProperty(  # type: ignore[valid-type]
        name="Body type",
        description="Only humanoid bodies are auto-rigged",
        items=(
            ("humanoid", "Humanoid", "Two-legged, two-armed body"),
            ("quadruped", "Quadruped", "Reported as a follow-up spike"),
            ("non_biped", "Non-biped", "Reported as a follow-up spike"),
        ),
        default="humanoid",
    )
    landmarks_path: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Landmarks file",
        description="JSON object of landmark keys to [x, y, z] in meters, world space",
        subtype="FILE_PATH",
        default="",
    )

    def invoke(self, context: bpy.types.Context, event: bpy.types.Event) -> set[str]:
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context: bpy.types.Context) -> set[str]:
        landmarks = _read_landmarks(self.landmarks_path)
        if landmarks is None:
            result = fail(
                STATUS_FALLBACK,
                "rig.landmarks_missing",
                f"Could not read landmarks from {self.landmarks_path or '(no file)'}.",
                "Choose a JSON file that maps each landmark key to [x, y, z].",
            )
        else:
            result = build_rig(self.collection_name, self.body_type, landmarks)
        store_rig_result(context, result)
        if result["status"] == "ok":
            log_operator_result(_OP_NAME, f"{self.collection_name}: rig built")
            return {"FINISHED"}
        self.report(
            {"ERROR"},
            f"{result['code']}: {result['message']} — {result['remediation']}",
        )
        return {"CANCELLED"}


def _read_landmarks(path: str) -> dict[str, list[float]] | None:
    if not path:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None
