"""Spatial inspection of one asset collection (#127).

Reports, for the mesh parts of collection <Name>: each part's world bounds, floating parts
(blocking), interpenetrating pairs (non-blocking), non-manifold edges (blocking), and the Desktop
triangle budget (blocking when exceeded). Each part also carries the contract geometry findings.

Read-only. Every evaluated mesh copy is removed before the call returns, and nothing else in
bpy.data changes, so the open file keeps its objects, transforms, and datablocks.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Final

import bmesh
import bpy
from mathutils import Vector, geometry
from mathutils.bvhtree import BVHTree

from ..contract_core.geometry import geometry_findings
from ..contract_core.report import ContractError
from ..contract_core.validate import triangle_count
from ..utils.budgets import (
    ASSET_CLASSES,
    CONTRACT_BUDGETS,
    BudgetOverrideError,
    resolve_budget,
)

DEFAULT_GAP_TOLERANCE: Final = 0.001
# Triangles are shrunk toward their centroids by this fraction before the crossing test, so
# faces that only touch along an edge or lie flush on a shared plane do not count as crossing.
_SHRINK: Final = 1e-3
_DECIMALS: Final = 6

INSPECT_RULES: Final[dict[str, str]] = {
    "floating": "Move or extend the part until it touches the body, or join it to its neighbour.",
    "interpenetration": (
        "Separate the two parts so they only touch, unless the overlap is intentional."
    ),
    "non_manifold": (
        "Close the open edges so every edge has exactly two faces "
        "(Select > Select All by Trait > Non Manifold shows them)."
    ),
    "over_budget": (
        "Remove triangles (decimate or delete hidden faces), or raise this class's Desktop "
        "tris in nmg-budgets.json."
    ),
}


@dataclass(frozen=True)
class _Part:
    name: str
    world: list[Vector]
    tris: list[tuple[int, int, int]]
    tree: BVHTree
    tri_count: int
    non_manifold: int
    geometry: list[dict[str, str]]
    lo: Vector
    hi: Vector

    def volume(self) -> float:
        extent = self.hi - self.lo
        return extent.x * extent.y * extent.z


def inspect_asset(
    collection: str,
    asset_class: str,
    budgets_path: str | None = None,
    *,
    gap_tolerance: float = DEFAULT_GAP_TOLERANCE,
) -> dict[str, Any]:
    """Return the spatial inspection report for collection <Name>.

    Raises ContractError with inspect.unknown_asset_class or inspect.collection_missing before
    any mesh is evaluated. An invalid nmg-budgets.json raises its own budget code.
    """
    if asset_class not in CONTRACT_BUDGETS:
        raise ContractError(
            "inspect.unknown_asset_class",
            f"Asset class '{asset_class}' is not in the contract budgets.",
            f"Use one of: {', '.join(ASSET_CLASSES)}.",
        )
    source = bpy.data.collections.get(collection)
    if source is None:
        raise ContractError(
            "inspect.collection_missing",
            f"No collection named '{collection}' in the open file.",
            "Pass the exact name of the asset collection <Name>, or block out the parts "
            "into a collection with that name first.",
        )
    try:
        budget = resolve_budget(asset_class, budgets_path, variant="desktop")["tris"]
    except BudgetOverrideError as error:
        raise ContractError(error.code, error.message, error.remediation) from error

    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    measured: list[_Part] = []
    for obj in sorted(source.all_objects, key=lambda item: item.name):
        if obj.type != "MESH":
            continue
        part = _measure(obj, depsgraph)
        if part is not None:
            measured.append(part)

    findings = _findings(measured, gap_tolerance)
    total = sum(part.tri_count for part in measured)
    if total > budget:
        findings.append(
            {
                "rule": "over_budget",
                "blocking": True,
                "parts": [],
                "triangles": total,
                "budget": budget,
                "message": (
                    f"{total} triangles exceed the {budget} Desktop budget for {asset_class}."
                ),
                "remediation": INSPECT_RULES["over_budget"],
            }
        )
    findings.sort(key=lambda item: (item["rule"], item["parts"]))

    return {
        "kind": "inspect",
        "asset": collection,
        "class": asset_class,
        # Rounded like the other lengths: a Blender FloatProperty stores float32, so 0.001
        # arrives here as 0.0010000000474974513.
        "gap_tolerance": round(float(gap_tolerance), _DECIMALS),
        "passed": not any(item["blocking"] for item in findings),
        "parts": [_part_report(part) for part in measured],
        "findings": findings,
        "triangles": {"total": total, "budget": budget, "headroom": budget - total},
    }


def _measure(obj: bpy.types.Object, depsgraph: bpy.types.Depsgraph) -> _Part | None:
    """Measure one mesh object from an evaluated copy; None when it has no vertices."""
    copy = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph), depsgraph=depsgraph)
    try:
        if len(copy.vertices) == 0:
            return None
        copy.calc_loop_triangles()
        world = [obj.matrix_world @ vert.co for vert in copy.vertices]
        tris = [tuple(tri.vertices) for tri in copy.loop_triangles]
        bm = bmesh.new()
        try:
            bm.from_mesh(copy)
            non_manifold = sum(1 for edge in bm.edges if not edge.is_manifold)
        finally:
            bm.free()
        lo = Vector(tuple(min(vert[axis] for vert in world) for axis in range(3)))
        hi = Vector(tuple(max(vert[axis] for vert in world) for axis in range(3)))
        return _Part(
            name=obj.name,
            world=world,
            tris=tris,
            tree=BVHTree.FromPolygons(world, tris),
            tri_count=triangle_count(copy),
            non_manifold=non_manifold,
            geometry=geometry_findings(obj.name, copy),
            lo=lo,
            hi=hi,
        )
    finally:
        bpy.data.meshes.remove(copy)


def _findings(parts: list[_Part], gap_tolerance: float) -> list[dict[str, Any]]:
    """Floating and non-manifold findings (blocking), plus interpenetration (non-blocking)."""
    if not parts:
        return []
    findings: list[dict[str, Any]] = []
    gaps: dict[tuple[int, int], float] = {}
    overlapping: set[tuple[int, int]] = set()
    for i, first in enumerate(parts):
        for j in range(i + 1, len(parts)):
            second = parts[j]
            gap, overlaps = _relate(first, second, gap_tolerance)
            gaps[(i, j)] = gap
            if overlaps:
                overlapping.add((i, j))
                findings.append(
                    {
                        "rule": "interpenetration",
                        "blocking": False,
                        "parts": [first.name, second.name],
                        "message": f"{first.name} and {second.name} interpenetrate.",
                        "remediation": INSPECT_RULES["interpenetration"],
                    }
                )

    def linked(a: int, b: int) -> bool:
        pair = (min(a, b), max(a, b))
        return pair in overlapping or gaps[pair] <= gap_tolerance

    components = _components(len(parts), linked)
    # The main body is the component with the largest summed bounds volume; ties go to more
    # parts, then to the component whose first part name sorts first.
    main = min(
        components,
        key=lambda comp: (
            -sum(parts[index].volume() for index in comp),
            -len(comp),
            parts[comp[0]].name,
        ),
    )
    for component in components:
        if component is main:
            continue
        for index in component:
            gap = min(gaps[(min(index, other), max(index, other))] for other in main)
            findings.append(_floating(parts[index].name, gap))
    for part in parts:
        if part.non_manifold:
            findings.append(
                {
                    "rule": "non_manifold",
                    "blocking": True,
                    "parts": [part.name],
                    "edges": part.non_manifold,
                    "message": f"{part.name} has {part.non_manifold} non-manifold edge(s).",
                    "remediation": INSPECT_RULES["non_manifold"],
                }
            )
    return findings


def _floating(name: str, gap: float) -> dict[str, Any]:
    """A blocking floating finding; gap is None when the part has no surface to measure from."""
    if not math.isfinite(gap):
        return {
            "rule": "floating",
            "blocking": True,
            "parts": [name],
            "gap": None,
            "message": f"{name} has no surface connected to the rest of the asset.",
            "remediation": INSPECT_RULES["floating"],
        }
    rounded = round(gap, _DECIMALS)
    return {
        "rule": "floating",
        "blocking": True,
        "parts": [name],
        "gap": rounded,
        "message": f"{name} is {rounded} m from the rest of the asset.",
        "remediation": INSPECT_RULES["floating"],
    }


def _relate(a: _Part, b: _Part, gap_tolerance: float) -> tuple[float, bool]:
    """Return the surface gap between two parts and whether they interpenetrate."""
    gap = min(_gap_to(a.world, b.tree), _gap_to(b.world, a.tree))
    crossing = any(_crosses(a, b, ia, ib) for ia, ib in a.tree.overlap(b.tree))
    nested = _inside(a.world[0], b.tree, gap_tolerance) or _inside(
        b.world[0], a.tree, gap_tolerance
    )
    return gap, crossing or nested


def _gap_to(points: list[Vector], tree: BVHTree) -> float:
    """Smallest distance from any of points to the surface in tree; inf when there is none."""
    best = math.inf
    for point in points:
        _, _, _, distance = tree.find_nearest(point)
        if distance is not None and distance < best:
            best = distance
    return best


def _inside(point: Vector, tree: BVHTree, gap_tolerance: float) -> bool:
    """True when point lies deeper than gap_tolerance inside the closed surface in tree."""
    nearest, normal, _, distance = tree.find_nearest(point)
    if nearest is None or normal is None or distance is None or distance <= gap_tolerance:
        return False
    return (nearest - point).dot(normal) > 0


def _crosses(a: _Part, b: _Part, ia: int, ib: int) -> bool:
    """True when triangle ia of a and triangle ib of b cross, not merely touch."""
    tri_a = _shrunk([a.world[index] for index in a.tris[ia]])
    tri_b = _shrunk([b.world[index] for index in b.tris[ib]])
    return _edge_pierces(tri_a, tri_b) or _edge_pierces(tri_b, tri_a)


def _shrunk(tri: list[Vector]) -> list[Vector]:
    centre = (tri[0] + tri[1] + tri[2]) / 3
    return [centre + (vert - centre) * (1 - _SHRINK) for vert in tri]


def _edge_pierces(edged: list[Vector], target: list[Vector]) -> bool:
    """True when an edge of edged passes through the triangle target."""
    for start, end in ((edged[0], edged[1]), (edged[1], edged[2]), (edged[2], edged[0])):
        direction = end - start
        hit = geometry.intersect_ray_tri(target[0], target[1], target[2], direction, start, True)
        if hit is not None and (hit - start).dot(direction) <= direction.length_squared:
            return True
    return False


def _components(count: int, linked: Callable[[int, int], bool]) -> list[list[int]]:
    """Connected components of part indices, each sorted; ordered by their lowest index."""
    seen: set[int] = set()
    components: list[list[int]] = []
    for start in range(count):
        if start in seen:
            continue
        seen.add(start)
        stack = [start]
        members: list[int] = []
        while stack:
            current = stack.pop()
            members.append(current)
            for other in range(count):
                if other not in seen and linked(current, other):
                    seen.add(other)
                    stack.append(other)
        components.append(sorted(members))
    return components


def _part_report(part: _Part) -> dict[str, Any]:
    return {
        "name": part.name,
        "bounds": {
            "min": [round(part.lo[axis], _DECIMALS) for axis in range(3)],
            "max": [round(part.hi[axis], _DECIMALS) for axis in range(3)],
        },
        "tris": part.tri_count,
        "non_manifold_edges": part.non_manifold,
        "geometry": part.geometry,
    }
