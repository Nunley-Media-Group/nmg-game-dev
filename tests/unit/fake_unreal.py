"""In-memory stand-in for the ``unreal`` module, so the generated import code runs in tests (#145).

``build_import_code`` returns UE Python for the editor. ``FakeWorld.execute_python_code`` runs that
text with this module installed as ``unreal`` and returns what it printed, so a test checks what the
code does to the assets, not only its text. Nothing here contacts a running editor.

The fake models the parts of UE 5.8 Interchange that the static import depends on:

- A static import makes one static mesh per FBX node. Interchange puts the FBX unit conversion on
  the node transform, not the vertices. With ``transform_vertex_to_absolute`` off the vertices stay
  in metres, so a mesh reports its metre values read as centimetres, times its LOD0 build scale,
  and it is named after its mesh datablock. With it on, the node translation is baked in, the
  bounds are in centimetres, and the mesh is named after the node.
- Y is negated on the way into UE, the convention ``check_pivots`` expects.
- Bounds are computed when a mesh is imported or rebuilt. A build-settings write rebuilds the mesh
  and nothing else does, so bounds stay stale until one happens.
- A skeletal import reports the authored size. The rigged path is unchanged by #145, and it is
  correct today, so the fake does not model a scale for it.
- ``combine_meshes`` is not modelled. The generated code always turns it off, and the fake refuses
  a run that turns it on.
- A static LOD group (#146) is one FBX node whose ``lods`` is its LOD count. Interchange makes one
  static mesh from it, and the fake reports that count as ``get_num_lods()``.
- UE 5.8 lists only the first mesh of a multi-part FBX in ``imported_object_paths``. Which meshes a
  task reports is set by ``FakeWorld.reported_paths``, so a test can under-report (#141).
- A skeletal import makes the skeleton ``<Name>_Skeleton`` beside the mesh, unless it is handed one.
  It never makes the physics asset: UE 5.8 leaves that out, so the import code makes it through
  ``SkeletalMeshEditorSubsystem.create_physics_asset`` (#141).
- ``SkeletalMeshEditorSubsystem.import_lod`` records each LOD import (#141).
- ``FakeWorld.refused_renames`` and ``FakeWorld.refused_consolidations`` make ``rename_asset`` and
  ``consolidate_assets`` return False, as UE does when it refuses one, and change nothing (#203).
"""

from __future__ import annotations

import contextlib
import io
import sys
import types
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import nmg_game_dev.pipeline  # noqa: F401 - load the pipeline first; unreal imports it back
from nmg_game_dev.unreal import import_variant, parse_nmg_result

Triple = tuple[float, float, float]

_ASSET_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")
_CM_PER_METER = 100.0


def ue_asset_name(text: str) -> str:
    """Replace each character outside [A-Za-z0-9_] with an underscore, as UE names assets."""
    return "".join(char if char in _ASSET_CHARS else "_" for char in text)


@dataclass(frozen=True)
class FbxNode:
    """One mesh node of a fake FBX, in Blender axes and metres as the exporter writes them."""

    name: str
    """The node name, which is the Blender object name."""
    datablock: str
    """The mesh datablock name. With transform off, UE names the static mesh after this."""
    low: Triple
    """Object-local bounds, minimum corner, in metres."""
    high: Triple
    """Object-local bounds, maximum corner, in metres."""
    translation: Triple = (0.0, 0.0, 0.0)
    """The node origin in metres, in Blender axes."""
    materials: tuple[str, ...] = ()
    """Material slot names, each of the form M_<Name>_<Part>."""
    lods: int = 1
    """The LOD count of the static mesh this node makes. A static LOD group has three (#146)."""


def _ue_corners(node: FbxNode) -> tuple[list[float], list[float]]:
    """Blender metres to UE axes. Negating Y swaps the minimum and maximum Y."""
    low = [node.low[0], -node.high[1], node.low[2]]
    high = [node.high[0], -node.low[1], node.high[2]]
    return low, high


def _reported_bounds(node: FbxNode, transform: bool, scale: float) -> dict[str, list[float]]:
    """The bounds a static mesh reports for ``node``, as UE would read them.

    With ``transform`` on, the node translation is baked in and the result is in centimetres. With
    it off, the metre values are read as centimetres and multiplied by ``scale``, the LOD0 build
    scale: 1.0 leaves the file's 1/100 size, and 100 restores the authored size.
    """
    low, high = _ue_corners(node)
    if transform:
        offset = [node.translation[0], -node.translation[1], node.translation[2]]
        low = [(value + shift) * _CM_PER_METER for value, shift in zip(low, offset, strict=True)]
        high = [(value + shift) * _CM_PER_METER for value, shift in zip(high, offset, strict=True)]
    else:
        low = [value * scale for value in low]
        high = [value * scale for value in high]
    return {"min": low, "max": high}


class _Settings:
    """A plain attribute bag for the UE settings objects the generated code fills in."""

    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)


class Vector:
    """``unreal.Vector``: three float components."""

    def __init__(self, x: float = 0.0, y: float = 0.0, z: float = 0.0) -> None:
        self.x = float(x)
        self.y = float(y)
        self.z = float(z)


class _Box:
    def __init__(self, low: list[float], high: list[float]) -> None:
        self.min = Vector(*low)
        self.max = Vector(*high)


class _Bounds:
    def __init__(self, origin: Vector, box_extent: Vector) -> None:
        self.origin = origin
        self.box_extent = box_extent


class _Slot:
    """A material slot: its name, and the material instance assigned to it."""

    def __init__(self, name: str) -> None:
        self.material_slot_name = name
        self.material_interface: Any = None


class _Asset:
    """A package in the fake editor. ``path`` is its package path."""

    def __init__(self, path: str) -> None:
        self.path = path
        self.properties: dict[str, Any] = {}

    def set_editor_property(self, name: str, value: Any) -> None:
        self.properties[name] = value

    def get_editor_property(self, name: str) -> Any:
        return self.properties[name]


class Texture2D(_Asset):
    """A texture imported from a PNG. Its settings are the properties the generated code sets."""


class StaticMesh(_Asset):
    """A static mesh built from one FBX node, with its LOD0 build scale and reported bounds."""

    def __init__(self, path: str, node: FbxNode, *, transform: bool) -> None:
        super().__init__(path)
        self.node = node
        self.transform = transform
        self.build_scale = Vector(1.0, 1.0, 1.0)
        self.static_materials = [_Slot(name) for name in node.materials]
        self.bounds: dict[str, list[float]] = {}
        self.rebuild()

    def rebuild(self) -> None:
        self.bounds = _reported_bounds(self.node, self.transform, self.build_scale.x)

    def get_bounding_box(self) -> _Box:
        return _Box(self.bounds["min"], self.bounds["max"])

    def get_num_lods(self) -> int:
        return self.node.lods

    def set_material(self, index: int, material: Any) -> None:
        self.static_materials[index].material_interface = material


class SkeletalMesh(_Asset):
    """A skeletal mesh built from one FBX node at the authored size."""

    def __init__(self, path: str, node: FbxNode) -> None:
        super().__init__(path)
        self.bounds = _reported_bounds(node, True, 1.0)
        self.properties["materials"] = [_Slot(name) for name in node.materials]

    def get_bounds(self) -> _Bounds:
        low, high = self.bounds["min"], self.bounds["max"]
        origin = Vector(*[(a + b) / 2.0 for a, b in zip(low, high, strict=True)])
        extent = Vector(*[(b - a) / 2.0 for a, b in zip(low, high, strict=True)])
        return _Bounds(origin, extent)


class Skeleton(_Asset):
    """The rig a skeletal mesh is built on, made beside the mesh by its import (#141)."""


class PhysicsAsset(_Asset):
    """The physics asset of one skeletal mesh, made by ``create_physics_asset`` (#141)."""

    def get_path_name(self) -> str:
        """The object path UE returns: the package path, then a dot, then the asset name."""
        return self.path + "." + self.path.rsplit("/", 1)[-1]


class MaterialInstanceConstant(_Asset):
    """A material instance: its parent and the texture bound to each parameter."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.parent: Any = None
        self.texture_params: dict[str, str] = {}


class MaterialInstanceConstantFactoryNew:
    """``unreal.MaterialInstanceConstantFactoryNew``, passed to ``create_asset`` and not used."""


class FbxImportUI:
    """``unreal.FbxImportUI``. Defaults match UE's, so a run that forgets to set one shows it."""

    def __init__(self) -> None:
        self.import_materials = True
        self.import_textures = True
        self.import_as_skeletal = False
        self.mesh_type_to_import: Any = None
        self.import_animations = True
        self.create_physics_asset = False
        self.skeleton: Any = None
        self.physics_asset: Any = None
        self.static_mesh_import_data = _Settings(
            combine_meshes=True,
            transform_vertex_to_absolute=True,
            bake_pivot_in_vertex=False,
        )


class AssetImportTask:
    """``unreal.AssetImportTask``. ``imported_object_paths`` is filled in by the import."""

    def __init__(self) -> None:
        self.filename = ""
        self.destination_path = ""
        self.destination_name = ""
        self.automated = False
        self.replace_existing = False
        self.save = False
        self.options: Any = None
        self.imported_object_paths: list[str] = []


class FBXImportType:
    FBXIT_SKELETAL_MESH = "FBXIT_SKELETAL_MESH"


class TextureCompressionSettings:
    TC_NORMALMAP = "TC_NORMALMAP"
    TC_MASKS = "TC_MASKS"


class StaticMeshEditorSubsystem:
    """``unreal.StaticMeshEditorSubsystem``: LOD build settings, which a write rebuilds."""

    def __init__(self, world: FakeWorld) -> None:
        self._world = world

    def get_lod_build_settings(self, mesh: StaticMesh, lod: int) -> _Settings:
        _require_lod0(lod)
        scale = mesh.build_scale
        return _Settings(build_scale3d=Vector(scale.x, scale.y, scale.z))

    def set_lod_build_settings(self, mesh: StaticMesh, lod: int, settings: Any) -> None:
        _require_lod0(lod)
        scale = settings.build_scale3d
        mesh.build_scale = Vector(scale.x, scale.y, scale.z)
        mesh.rebuild()
        self._world.build_writes.append((mesh.path, lod, (scale.x, scale.y, scale.z)))


class SkeletalMeshEditorSubsystem:
    """``unreal.SkeletalMeshEditorSubsystem``: physics assets and LOD imports (#141)."""

    def __init__(self, world: FakeWorld) -> None:
        self._world = world

    def create_physics_asset(self, mesh: SkeletalMesh) -> PhysicsAsset:
        """Build ``<mesh>_PhysicsAsset`` beside the mesh, or in ``FakeWorld.physics_folder``."""
        mesh_folder, mesh_name = mesh.path.rsplit("/", 1)
        path = (self._world.physics_folder or mesh_folder) + "/" + mesh_name + "_PhysicsAsset"
        asset = PhysicsAsset(path)
        self._world.assets[path] = asset
        self._world.create_physics_calls.append(mesh.path)
        return asset

    def import_lod(self, mesh: SkeletalMesh, level: int, fbx: str) -> int:
        """Record the LOD import. The fake keeps no LOD geometry, so it places the asked level."""
        self._world.lod_imports.append((mesh.path, level, fbx))
        return level


def _require_lod0(lod: int) -> None:
    if lod != 0:
        raise RuntimeError("the fake models LOD0 only, got LOD " + str(lod))


class MaterialEditingLibrary:
    @staticmethod
    def set_material_instance_parent(instance: MaterialInstanceConstant, parent: Any) -> None:
        instance.parent = parent

    @staticmethod
    def set_material_instance_texture_parameter_value(
        instance: MaterialInstanceConstant, parameter: str, texture: Texture2D
    ) -> None:
        instance.texture_params[parameter] = texture.path


class EditorAssetLibrary:
    """``unreal.EditorAssetLibrary``, bound to the world whose Python is running."""

    @staticmethod
    def load_asset(path: str) -> _Asset | None:
        return _active_world().assets.get(path)

    @staticmethod
    def does_asset_exist(path: str) -> bool:
        return path in _active_world().assets

    @staticmethod
    def save_loaded_asset(asset: _Asset) -> bool:
        world = _active_world()
        bounds = asset.bounds if isinstance(asset, (StaticMesh, SkeletalMesh)) else None
        world.saved[asset.path] = bounds
        return True

    @staticmethod
    def rename_asset(source: str, destination: str) -> bool:
        world = _active_world()
        if source in world.refused_renames:
            return False
        if source not in world.assets:
            raise RuntimeError("asset not found: " + source)
        if destination in world.assets:
            raise RuntimeError("cannot rename over an existing asset: " + destination)
        asset = world.assets.pop(source)
        asset.path = destination
        world.assets[destination] = asset
        # A rename writes the package to disk, so the saved state moves with it.
        if source in world.saved:
            world.saved[destination] = world.saved.pop(source)
        return True

    @staticmethod
    def consolidate_assets(
        asset_to_consolidate_to: _Asset, assets_to_consolidate: list[Any]
    ) -> bool:
        world = _active_world()
        if any(asset.path in world.refused_consolidations for asset in assets_to_consolidate):
            return False
        target = asset_to_consolidate_to.path
        for asset in assets_to_consolidate:
            source: str = asset.path
            if world.assets.get(source) is not asset:
                raise RuntimeError("asset to consolidate is not in the editor: " + source)
            del world.assets[source]
            world.saved.pop(source, None)
            world.redirects[source] = target
        return True


class _AssetTools:
    def __init__(self, world: FakeWorld) -> None:
        self._world = world

    def import_asset_tasks(self, tasks: list[AssetImportTask]) -> None:
        for task in tasks:
            self._world.import_task(task)

    def create_asset(
        self, name: str, dest: str, asset_class: Any, factory: Any
    ) -> MaterialInstanceConstant:
        if asset_class is not MaterialInstanceConstant:
            raise NotImplementedError("the fake only creates material instances")
        del factory
        instance = MaterialInstanceConstant(dest + "/" + name)
        self._world.assets[instance.path] = instance
        return instance


class AssetToolsHelpers:
    @staticmethod
    def get_asset_tools() -> _AssetTools:
        return _AssetTools(_active_world())


def get_editor_subsystem(subsystem_class: type[Any]) -> Any:
    return subsystem_class(_active_world())


# The fake ``unreal`` module. ``FakeWorld.execute_python_code`` installs it in ``sys.modules``.
UNREAL = types.ModuleType("unreal")
UNREAL.__dict__.update(
    AssetImportTask=AssetImportTask,
    AssetToolsHelpers=AssetToolsHelpers,
    EditorAssetLibrary=EditorAssetLibrary,
    FBXImportType=FBXImportType,
    FbxImportUI=FbxImportUI,
    MaterialEditingLibrary=MaterialEditingLibrary,
    MaterialInstanceConstant=MaterialInstanceConstant,
    MaterialInstanceConstantFactoryNew=MaterialInstanceConstantFactoryNew,
    SkeletalMesh=SkeletalMesh,
    SkeletalMeshEditorSubsystem=SkeletalMeshEditorSubsystem,
    StaticMesh=StaticMesh,
    StaticMeshEditorSubsystem=StaticMeshEditorSubsystem,
    TextureCompressionSettings=TextureCompressionSettings,
    Vector=Vector,
    get_editor_subsystem=get_editor_subsystem,
)

_ACTIVE: list[FakeWorld] = []


def _active_world() -> FakeWorld:
    if not _ACTIVE:
        raise RuntimeError("the fake unreal module ran outside FakeWorld.execute_python_code")
    return _ACTIVE[-1]


def _every_path(created: list[str]) -> list[str]:
    """The default report: ``imported_object_paths`` lists every mesh the import made."""
    return list(created)


class FakeWorld:
    """One editor session: its assets, the FBX scenes on disk, and what the import did to them.

    It satisfies ``UnrealPythonClient``, so ``import_variant`` and ``build_import_code`` run the
    generated code against it. The tests set up FBX scenes and seed assets, then read the assets,
    saves, build-settings writes, and consolidation redirects back.

    The scenario knobs (#141) are plain attributes: ``reported_paths`` picks the subset of created
    meshes that ``imported_object_paths`` lists, ``skeleton_on_import`` turns off the skeleton the
    import makes, and ``physics_folder`` is where ``create_physics_asset`` places its asset.

    The refusal knobs (#203) are sets of asset paths. ``refused_renames`` holds the sources whose
    ``rename_asset`` returns False, and ``refused_consolidations`` the assets whose
    ``consolidate_assets`` returns False. Both are empty by default, so no refusal happens.
    """

    def __init__(self) -> None:
        self.assets: dict[str, _Asset] = {}
        self.fbx: dict[str, list[FbxNode]] = {}
        self.saved: dict[str, dict[str, list[float]] | None] = {}
        self.build_writes: list[tuple[str, int, Triple]] = []
        self.redirects: dict[str, str] = {}
        self.imported_fbx: list[str] = []
        self.import_options: list[Any] = []
        self.reported_paths: Callable[[list[str]], list[str]] = _every_path
        self.skeleton_on_import = True
        self.physics_folder: str | None = None
        self.create_physics_calls: list[str] = []
        self.lod_imports: list[tuple[str, int, str]] = []
        self.refused_renames: set[str] = set()
        self.refused_consolidations: set[str] = set()

    def add_fbx(self, path: str, nodes: list[FbxNode]) -> None:
        """Register the FBX scene that the import reads from ``path``. The file must exist too."""
        self.fbx[path] = list(nodes)

    def seed_static_mesh(self, path: str, node: FbxNode, *, transform: bool = False) -> None:
        """Place an existing static mesh at ``path``, as an earlier import would have left it."""
        self.assets[path] = StaticMesh(path, node, transform=transform)

    def seed_asset(self, path: str) -> None:
        """Place a plain asset at ``path``, such as the master material the import binds to."""
        self.assets[path] = _Asset(path)

    def static_mesh(self, path: str) -> StaticMesh:
        asset = self.assets.get(path)
        if not isinstance(asset, StaticMesh):
            raise AssertionError("no static mesh at " + path)
        return asset

    def static_mesh_paths(self) -> list[str]:
        return sorted(path for path, asset in self.assets.items() if isinstance(asset, StaticMesh))

    def import_task(self, task: AssetImportTask) -> None:
        if task.filename.lower().endswith(".fbx"):
            self._import_fbx(task)
        elif task.filename.lower().endswith(".png"):
            stem = task.destination_name
            path = task.destination_path + "/" + stem
            self.assets[path] = Texture2D(path)
            task.imported_object_paths = [path + "." + stem]
        else:
            raise RuntimeError("the fake cannot import " + task.filename)

    def _import_fbx(self, task: AssetImportTask) -> None:
        if task.filename not in self.fbx:
            raise RuntimeError("the fake has no FBX scene at " + task.filename)
        self.imported_fbx.append(task.filename)
        options = task.options
        self.import_options.append(options)
        nodes = self.fbx[task.filename]
        dest = task.destination_path
        created: list[str] = []
        if options.import_as_skeletal:
            node = nodes[0]
            path = dest + "/" + ue_asset_name(node.name)
            self.assets[path] = SkeletalMesh(path, node)
            created.append(path)
            # UE makes the skeleton beside the mesh, unless the import is handed one (#141).
            if self.skeleton_on_import and options.skeleton is None:
                self.assets[path + "_Skeleton"] = Skeleton(path + "_Skeleton")
        else:
            settings = options.static_mesh_import_data
            if settings.combine_meshes:
                raise RuntimeError("the fake does not model combine_meshes")
            transform = bool(settings.transform_vertex_to_absolute)
            for node in nodes:
                name = node.name if transform else node.datablock
                path = dest + "/" + ue_asset_name(name)
                if path in self.assets and not task.replace_existing:
                    raise RuntimeError("asset already exists: " + path)
                self.assets[path] = StaticMesh(path, node, transform=transform)
                created.append(path)
        reported = self.reported_paths(created)
        task.imported_object_paths = [path + "." + path.rsplit("/", 1)[-1] for path in reported]

    def execute_python_code(self, code: str) -> str:
        """Run UE Python against this world and return what it printed."""
        output = io.StringIO()
        previous = sys.modules.get("unreal")
        sys.modules["unreal"] = UNREAL
        _ACTIVE.append(self)
        try:
            with contextlib.redirect_stdout(output):
                exec(compile(code, "<ue-import>", "exec"), {"__name__": "__ue_import__"})
        finally:
            _ACTIVE.pop()
            if previous is None:
                sys.modules.pop("unreal", None)
            else:
                sys.modules["unreal"] = previous
        return output.getvalue()


# --- scene builders for the import tests (#145) ----------------------------------------------
#
# A scene is one variant folder with a placeholder SM_<Name>.fbx, whose FBX nodes the fake reads
# from the registration below, and the snapshot that the pre-export report carries for it.

DESKTOP_DEST = "/Game/Props/Crate/Desktop"
MOBILE_DEST = "/Game/Props/Crate/Mobile"
MASTER_PATH = "/nmg-game-dev/Materials/M_NmgORM"

# An 8 m part, 8 m from its origin on each axis, so its reported bounds are the -800/800 cm of the
# Gherkin scenarios. The small part is 1 m from its origin.
BIG_LOW: Triple = (-8.0, -8.0, -8.0)
BIG_HIGH: Triple = (8.0, 8.0, 8.0)
SMALL_LOW: Triple = (-1.0, -1.0, -1.0)
SMALL_HIGH: Triple = (1.0, 1.0, 1.0)
# Asymmetric on Y, so a missing Y negation shows in the bounds.
ASYM_LOW: Triple = (-1.0, 0.25, 0.0)
ASYM_HIGH: Triple = (1.0, 0.75, 2.0)


def dest_for(variant: str) -> str:
    return DESKTOP_DEST if variant == "desktop" else MOBILE_DEST


def box(value: float) -> dict[str, list[float]]:
    """Bounds of a box that extends ``value`` centimetres each way from the origin."""
    return {"min": [-value] * 3, "max": [value] * 3}


def part(
    variant: str,
    export: str,
    low: Triple,
    high: Triple,
    *,
    translation: Triple = (0.0, 0.0, 0.0),
    duplicate: bool = False,
    materials: tuple[str, ...] = (),
) -> tuple[FbxNode, str, dict[str, Any]]:
    """One part of a fake asset: its FBX node and its snapshot entry.

    The FBX node carries the export name, as variants_core writes it. On the Mobile variant the
    object and snapshot key carry ``_Mobile``, and the mesh datablock is the key, plus ``.001``
    when ``duplicate``. That datablock-named case is the one #145 fixes.
    """
    suffix = "" if variant == "desktop" else "_Mobile"
    key = export + suffix
    datablock = key + (".001" if duplicate else "")
    node = FbxNode(export, datablock, low, high, translation, materials)
    entry = {
        "variant": variant,
        "type": "MESH",
        "mesh": datablock,
        "local_bounds": {"min": list(low), "max": list(high)},
    }
    return node, key, entry


def contract_report(snapshot: dict[str, Any]) -> dict[str, Any]:
    """A pre-export contract report carrying ``snapshot``, as ``build_import_code`` reads it."""
    return {
        "kind": "contract",
        "asset": "Crate",
        "class": "standard_prop",
        "passed": True,
        "findings": [],
        "snapshot": snapshot,
    }


def stage(
    tmp_path: Path,
    variant: str,
    *parts: tuple[FbxNode, str, dict[str, Any]],
    textures: tuple[str, ...] = (),
    armature: bool = False,
    seed_master: bool = True,
) -> tuple[FakeWorld, Path, dict[str, Any]]:
    """Write the variant folder and register the FBX scene for ``parts`` in a fresh fake world.

    Returns the world, the variant folder, and the report to import. ``textures`` are stems of
    empty PNGs in the folder, ``armature`` adds the rig's SK_Crate, and ``seed_master`` places the
    master material the import binds to.
    """
    folder = tmp_path / "export" / "Props" / "Crate" / variant.capitalize()
    folder.mkdir(parents=True, exist_ok=True)
    fbx = folder / "SM_Crate.fbx"
    fbx.write_bytes(b"")  # the fake reads the scene registered below, not these bytes
    for stem in textures:
        (folder / (stem + ".png")).write_bytes(b"")
    world = FakeWorld()
    world.add_fbx(str(fbx), [part_[0] for part_ in parts])
    if seed_master:
        world.seed_asset(MASTER_PATH)
    snapshot = {key: entry for _, key, entry in parts}
    if armature:
        snapshot["SK_Crate"] = {"variant": "desktop", "type": "ARMATURE", "local_bounds": None}
    return world, folder, contract_report(snapshot)


def run_import(
    world: FakeWorld,
    folder: Path,
    variant: str,
    report: dict[str, Any],
    skeleton_dest: str | None = None,
) -> dict[str, Any]:
    """Run ``import_variant`` for one staged variant. It raises if the import or the pivots fail."""
    return import_variant(
        world,
        variant_dir=str(folder),
        dest=dest_for(variant),
        name="Crate",
        report=report,
        skeleton_dest=skeleton_dest,
    )


def run_import_code(code: str, scenario: FakeWorld) -> dict[str, Any]:
    """Run generated import code in ``scenario`` and return its parsed ``NMG_RESULT`` (#141).

    Unlike ``run_import``, a failed import is returned rather than raised, so a test can read the
    error text the code reported. ``execute_python_code`` installs the fake as ``unreal``.
    """
    return parse_nmg_result(scenario.execute_python_code(code))
