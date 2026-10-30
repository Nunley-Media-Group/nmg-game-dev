"""Export fixtures/smoke/SM_SmokeCube.fbx: a 1 m cube per docs/asset-contract.md.

Run headless from the repo root with the Blender that matches the toolchain (5.2):

  "$BLENDER_APP/Contents/MacOS/Blender" --background --factory-startup \
      --python fixtures/smoke/make_smoke_fbx.py

Follows the contract: meters, root origin at the bottom center on world origin, transforms
applied (section 2), and FBX export of the selected mesh only with modifiers applied, Face
smoothing, FBX Units Scale, and no embedded textures (section 7).
"""

from __future__ import annotations

import pathlib

import bpy

OUT_PATH = pathlib.Path(__file__).resolve().parent / "SM_SmokeCube.fbx"
ASSET_NAME = "SM_SmokeCube"

bpy.ops.wm.read_factory_settings(use_empty=True)

# A 1 m cube with its bottom face on z = 0 and its origin at the world origin.
bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0.0, 0.0, 0.5))
cube = bpy.context.active_object
assert cube is not None
cube.name = ASSET_NAME
cube.data.name = ASSET_NAME
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
cube.location = (0.0, 0.0, 0.0)

bpy.ops.object.select_all(action="DESELECT")
cube.select_set(True)
bpy.context.view_layer.objects.active = cube

bpy.ops.export_scene.fbx(
    filepath=str(OUT_PATH),
    use_selection=True,
    object_types={"MESH"},
    use_mesh_modifiers=True,
    mesh_smooth_type="FACE",
    apply_scale_options="FBX_SCALE_UNITS",
    embed_textures=False,
    add_leaf_bones=False,
    bake_space_transform=False,
)

if not OUT_PATH.is_file():
    raise SystemExit(f"FBX export did not write {OUT_PATH}")
print(f"WROTE {OUT_PATH}")
