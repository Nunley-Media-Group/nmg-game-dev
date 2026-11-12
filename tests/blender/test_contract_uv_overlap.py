"""Contract UV overlap under Blender headless: AC1 to AC4 of #133.

Run with scripts/run-blender-tests.sh. Under plain CPython the module is skipped.

REFERENCE_* below is the pre-#133 pure-Python rasterizer, kept verbatim. It is the oracle that the
numpy core must match: the same pass/fail outcome always, and the same fraction whenever the core
does not stop early.
"""

from __future__ import annotations

import importlib
import math
import random
import time
from array import array
from collections.abc import Iterator
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")

import bmesh  # noqa: E402

from .contract_fixtures import build_crate, clear_scene  # noqa: E402

REFERENCE_GRID = 512

Faces = list[tuple[int, list[tuple[float, float]]]]


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    yield
    clear_scene()


@pytest.fixture()
def uv(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core.uv")


@pytest.fixture()
def validate(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core.validate")


@pytest.fixture()
def core(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core")


# ---------------------------------------------------------------------------
# The pre-#133 reference rasterizer (oracle)
# ---------------------------------------------------------------------------


def reference_fraction(faces: Faces) -> float:
    owner = array("i", [-1]) * (REFERENCE_GRID * REFERENCE_GRID)
    shared = bytearray(REFERENCE_GRID * REFERENCE_GRID)
    for face, uv_points in faces:
        points = [(x * REFERENCE_GRID, y * REFERENCE_GRID) for x, y in uv_points]
        for index in range(1, len(points) - 1):
            reference_rasterize((points[0], points[index], points[index + 1]), face, owner, shared)
    covered = sum(1 for value in owner if value != -1)
    if covered == 0:
        return 0.0
    return sum(shared) / covered


def reference_rasterize(corners: Any, face: int, owner: array, shared: bytearray) -> None:
    a, b, c = corners
    twice_area = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    if abs(twice_area) < 1e-12:
        return
    sign = 1.0 if twice_area > 0 else -1.0
    x0 = max(0, math.floor(min(a[0], b[0], c[0])))
    x1 = min(REFERENCE_GRID - 1, math.ceil(max(a[0], b[0], c[0])))
    y0 = max(0, math.floor(min(a[1], b[1], c[1])))
    y1 = min(REFERENCE_GRID - 1, math.ceil(max(a[1], b[1], c[1])))
    for row in range(y0, y1 + 1):
        py = row + 0.5
        for col in range(x0, x1 + 1):
            px = col + 0.5
            w0 = sign * ((c[0] - b[0]) * (py - b[1]) - (c[1] - b[1]) * (px - b[0]))
            w1 = sign * ((a[0] - c[0]) * (py - c[1]) - (a[1] - c[1]) * (px - c[0]))
            w2 = sign * ((b[0] - a[0]) * (py - a[1]) - (b[1] - a[1]) * (px - a[0]))
            if w0 < 0 or w1 < 0 or w2 < 0:
                continue
            index = row * REFERENCE_GRID + col
            prior = owner[index]
            if prior == -1:
                owner[index] = face
            elif prior != face:
                shared[index] = 1


def random_faces(rng: random.Random, count: int) -> Faces:
    """Faces of 3 to 7 corners around random centers, with some out of range and some degenerate."""
    faces: Faces = []
    for face in range(count):
        cx, cy = rng.uniform(-0.15, 1.15), rng.uniform(-0.15, 1.15)
        radius = rng.uniform(0.0, 0.12)
        if rng.random() < 0.1:
            # Collinear corners: every fan triangle has zero area.
            corners = [(cx + t * radius, cy + t * radius) for t in (0.0, 0.5, 1.0)]
        else:
            corners = [
                (cx + radius * rng.uniform(-1.0, 1.0), cy + radius * rng.uniform(-1.0, 1.0))
                for _ in range(rng.randint(3, 7))
            ]
        faces.append((face, corners))
    return faces


def assert_matches_reference(uv: Any, faces: Faces) -> bool:
    """Assert the core agrees with the reference. Return whether the overlap is over the limit."""
    reference = reference_fraction(faces)
    result = uv.polygon_overlap(faces)
    over_limit = reference > uv.OVERLAP_LIMIT

    assert uv.polygon_overlap_fraction(faces) == result.fraction
    assert (result.fraction > uv.OVERLAP_LIMIT) == over_limit, (result, reference)
    if result.exact:
        assert result.fraction == reference
        assert result.triangles_rasterized == result.triangles_total
    else:
        assert 0.0 < result.fraction <= reference
    return over_limit


# ---------------------------------------------------------------------------
# AC2 / SCN002: the early exit never changes the outcome
# ---------------------------------------------------------------------------


def test_ac2_random_face_sets_match_the_reference_outcome(uv: Any) -> None:
    rng = random.Random(133)
    outcomes = {
        assert_matches_reference(uv, random_faces(rng, rng.randint(1, 8))) for _ in range(24)
    }
    assert outcomes == {True, False}, "the random sets should cover both outcomes"


def test_ac2_non_overlapping_grid_is_exact_and_clean(uv: Any) -> None:
    cells = []
    for column in range(4):
        for row in range(4):
            x0, y0, x1, y1 = column / 4, row / 4, (column + 1) / 4, (row + 1) / 4
            cells.append((column * 4 + row, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]))

    assert assert_matches_reference(uv, cells) is False
    result = uv.polygon_overlap(cells)
    assert (result.exact, result.fraction) == (True, 0.0)
    assert result.triangles_total == 32


def test_ac2_empty_and_degenerate_input_have_no_overlap(uv: Any) -> None:
    empty = uv.polygon_overlap([])
    assert (empty.exact, empty.fraction, empty.triangles_total) == (True, 0.0, 0)

    faces: Faces = [
        (0, [(-0.5, -0.5), (1.5, -0.5), (1.5, 1.5), (-0.5, 1.5)]),
        (1, [(0.2, 0.2), (0.4, 0.4), (0.6, 0.6)]),
        (2, [(0.1, 0.1), (0.2, 0.1)]),
        (3, []),
    ]
    assert_matches_reference(uv, faces)


def test_ac2_stacked_full_square_quads_stop_after_the_first_batch(uv: Any) -> None:
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    result = uv.polygon_overlap([(face, square) for face in range(1000)])

    assert result.exact is False
    assert result.fraction > uv.OVERLAP_LIMIT
    assert result.triangles_total == 2000
    assert result.triangles_rasterized < result.triangles_total


# ---------------------------------------------------------------------------
# Mesh helpers for the scene-level checks
# ---------------------------------------------------------------------------


def quad_grid(segments: int, stacked: bool) -> bpy.types.Mesh:
    """A segments x segments grid of quads, one face each.

    stacked gives every quad the full UV square, so all of them overlap. Otherwise the whole grid
    maps onto the UV square, one quad per cell, so nothing overlaps.
    """
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=segments, y_segments=segments, size=0.5)
    uv_layer = bm.loops.layers.uv.new("UVMap")
    xs = [vert.co.x for vert in bm.verts]
    ys = [vert.co.y for vert in bm.verts]
    # The whole-grid bounds are computed once; recomputing them per loop is quadratic.
    x_lo, x_hi = min(xs), max(xs)
    y_lo, y_hi = min(ys), max(ys)
    for face in bm.faces:
        fx = [vert.co.x for vert in face.verts]
        fy = [vert.co.y for vert in face.verts]
        for loop in face.loops:
            if stacked:
                u = (loop.vert.co.x - min(fx)) / (max(fx) - min(fx))
                v = (loop.vert.co.y - min(fy)) / (max(fy) - min(fy))
            else:
                u = (loop.vert.co.x - x_lo) / (x_hi - x_lo)
                v = (loop.vert.co.y - y_lo) / (y_hi - y_lo)
            loop[uv_layer].uv = (u, v)
    mesh = bpy.data.meshes.new(f"grid{segments}_{'stacked' if stacked else 'separate'}")
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def uv_quads_mesh(quads: list[list[tuple[float, float]]]) -> bpy.types.Mesh:
    """A mesh of independent quads whose loop UVs are the given corners."""
    bm = bmesh.new()
    uv_layer = bm.loops.layers.uv.new("UVMap")
    for quad in quads:
        face = bm.faces.new([bm.verts.new((u, v, 0.0)) for u, v in quad])
        for loop, (u, v) in zip(face.loops, quad, strict=True):
            loop[uv_layer].uv = (u, v)
    mesh = bpy.data.meshes.new("uv_quads")
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def use_mesh_for_root(mesh: bpy.types.Mesh) -> bpy.types.Mesh:
    """Give the Crate's Desktop root the new mesh, keeping its material."""
    root = bpy.data.objects["SM_Crate"]
    old = root.data
    mesh.materials.append(old.materials[0])
    root.data = mesh
    bpy.data.meshes.remove(old)
    return mesh


def overlap_rules(findings: list[dict[str, str]]) -> list[dict[str, str]]:
    return [item for item in findings if item["rule"] == "uv.overlap"]


# ---------------------------------------------------------------------------
# AC1 / SCN001: stacked UVs on a 100k-triangle mesh fail fast
# ---------------------------------------------------------------------------


def test_ac1_stacked_uvs_on_a_100k_triangle_mesh_fail_fast(
    uv: Any, validate: Any, core: Any
) -> None:
    build_crate()
    mesh = use_mesh_for_root(quad_grid(224, stacked=True))
    assert validate.triangle_count(mesh) >= 100_000

    started = time.perf_counter()
    findings = uv.uv_findings("SM_Crate", mesh, check_overlap=True)
    elapsed = time.perf_counter() - started

    assert elapsed < 10.0, f"the overlap check took {elapsed:.1f} s"
    assert [item["rule"] for item in findings] == ["uv.overlap"]
    report = core.validate_asset("Crate", "standard_prop")
    assert overlap_rules(report["findings"])


# ---------------------------------------------------------------------------
# AC3 / SCN003: an early-exit finding states a lower bound, an exact one keeps its message
# ---------------------------------------------------------------------------


def test_ac3_early_exit_finding_states_a_lower_bound(uv: Any) -> None:
    build_crate()
    mesh = use_mesh_for_root(quad_grid(64, stacked=True))

    (overlap,) = overlap_rules(uv.uv_findings("SM_Crate", mesh, check_overlap=True))

    assert "at least" in overlap["message"]
    assert "0.5%" in overlap["message"]


def test_ac3_exact_overlap_keeps_the_original_message(uv: Any) -> None:
    # Two identical 0.05-wide squares cover about 650 texels, all of them shared. That stays under
    # the early-exit bound, so the result is exact and the message is the original form.
    square = [(0.0, 0.0), (0.05, 0.0), (0.05, 0.05), (0.0, 0.05)]
    mesh = uv_quads_mesh([square, square])

    (overlap,) = overlap_rules(uv.uv_findings("Sliver", mesh, check_overlap=True))

    assert "at least" not in overlap["message"]
    assert "100.0% of covered UV texels are shared" in overlap["message"]
    assert "the limit is 0.5%." in overlap["message"]


# ---------------------------------------------------------------------------
# AC4 / SCN004: a large non-overlapping layout stays fast and passes
# ---------------------------------------------------------------------------


def test_ac4_large_separate_layout_passes_fast(uv: Any, validate: Any, core: Any) -> None:
    build_crate()
    mesh = use_mesh_for_root(quad_grid(317, stacked=False))
    assert validate.triangle_count(mesh) >= 200_000

    started = time.perf_counter()
    findings = uv.uv_findings("SM_Crate", mesh, check_overlap=True)
    elapsed = time.perf_counter() - started

    assert elapsed < 30.0, f"the overlap check took {elapsed:.1f} s"
    assert overlap_rules(findings) == []
    report = core.validate_asset("Crate", "standard_prop")
    assert overlap_rules(report["findings"]) == []
