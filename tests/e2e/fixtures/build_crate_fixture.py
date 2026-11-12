"""Build the single-mesh static Crate for the opt-in finalize e2e test of a static LOD group (#146).

``build_static_crate()`` makes a non-rigged ``Crate`` collection in the open Blender scene with one
mesh, ``SM_Crate``, and no child parts. The Desktop box and its baked-style material come from
``tests/blender/contract_fixtures.py``, which this module loads by path. Its edges are then
subdivided into a grid of about 3,900 triangles, so the variants step can decimate Mobile LOD0 and
still record strictly decreasing LOD triangle counts. The Mobile collection that ``build_crate``
also makes is removed, because the variants step builds Mobile from Desktop.

Run it headless to write the fixture::

    blender --background --factory-startup --python build_crate_fixture.py -- <out.blend>

The module imports bpy, so only Blender runs it. The default suite never imports it.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import bmesh
import bpy

COLLECTION = "Crate"
MOBILE_COLLECTION = "Crate_Mobile"
#: Cuts per box edge. 18 segments a side gives 18 x 18 quads on each face: 3,888 triangles.
_SUBDIVISION_CUTS = 17
_CONTRACT_FIXTURES = Path(__file__).resolve().parents[2] / "blender" / "contract_fixtures.py"


def _load_contract_fixtures() -> ModuleType:
    spec = importlib.util.spec_from_file_location("contract_fixtures", _CONTRACT_FIXTURES)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _subdivide(obj: bpy.types.Object) -> None:
    """Subdivide every edge of the box in obj into a grid, keeping its UVs and its material."""
    old = obj.data
    name = old.name
    bm = bmesh.new()
    bm.from_mesh(old)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=_SUBDIVISION_CUTS, use_grid_fill=True)
    mesh = bpy.data.meshes.new(name + "_dense")
    bm.to_mesh(mesh)
    bm.free()
    mesh.materials.append(old.materials[0])
    obj.data = mesh
    bpy.data.meshes.remove(old)
    mesh.name = name


def build_static_crate() -> bpy.types.Collection:
    """Replace the open scene's content with the single-mesh Crate and return its collection."""
    _load_contract_fixtures().build_crate()
    mobile = bpy.data.collections[MOBILE_COLLECTION]
    for obj in list(mobile.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    bpy.data.collections.remove(mobile)
    _subdivide(bpy.data.objects["SM_Crate"])
    return bpy.data.collections[COLLECTION]


def _main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 1:
        raise SystemExit(
            "usage: blender --background --python build_crate_fixture.py -- <out.blend>"
        )
    build_static_crate()
    bpy.ops.wm.save_as_mainfile(filepath=str(Path(args[0]).resolve()))


if __name__ == "__main__":
    _main()
