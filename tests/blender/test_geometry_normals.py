"""geometry.normals judges open sheets by winding and closed parts by orientation (#144).

SCN001-SCN007 cover AC1-AC7. The callers test checks that validate_asset and inspect_asset keep
working unchanged (FR5). Run with scripts/run-blender-tests.sh. Under plain CPython the module is
skipped.
"""

from __future__ import annotations

import importlib
import math
import random
from collections.abc import Iterator, Sequence
from typing import Any

import pytest

bpy = pytest.importorskip("bpy")
bmesh = pytest.importorskip("bmesh")

from .contract_fixtures import build_crate, clear_scene  # noqa: E402

Vec = tuple[float, float, float]
NORMALS = "geometry.normals"
SEED = 144
PLACEMENTS = 500
TILTED = 500
TOUCHING_ARRANGEMENTS = 200
SIZES = (1.0, 1.5, 2.0)
OFFSETS = (-1.0, -0.5, 0.0, 0.5, 1.0)
FLOOR: list[Vec] = [(0.0, 0.0, 0.0), (4.0, 0.0, 0.0), (4.0, 4.0, 0.0), (0.0, 4.0, 0.0)]
WALL: list[Vec] = [(0.0, 4.0, 0.0), (4.0, 4.0, 0.0), (4.0, 4.0, 3.0), (0.0, 4.0, 3.0)]
ISSUE_QUAD: list[Vec] = [
    (3.37, -2.11, 0.4),
    (7.9, -2.11, 0.4),
    (7.9, 1.63, 0.4),
    (3.37, 1.63, 0.4),
]
# Exact floats from a seeded search: the pre-#144 whole-mesh recalculation counted two faces here.
FLAGGED_FLOOR: list[Vec] = [
    (8.910737835199864, -7.6375279622518555, 3.1678390792223947),
    (10.457713089852401, -7.6375279622518555, 3.1678390792223947),
    (10.457713089852401, -4.1128317860588, 3.1678390792223947),
    (8.910737835199864, -4.1128317860588, 3.1678390792223947),
]


@pytest.fixture(autouse=True)
def _isolated_scene() -> Iterator[None]:
    yield
    clear_scene()


@pytest.fixture()
def geometry(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core.geometry")


@pytest.fixture()
def report(enabled_addon: str) -> Any:
    return importlib.import_module(f"{enabled_addon}.contract_core.report")


class _Sheet:
    """Polygons whose vertices are shared when their coordinates match exactly."""

    def __init__(self) -> None:
        self.bm = bmesh.new()
        self._verts: dict[Vec, Any] = {}

    def polygon(self, corners: Sequence[Vec], *, reverse: bool = False) -> None:
        ordered = list(reversed(corners)) if reverse else list(corners)
        verts = []
        for co in ordered:
            if co not in self._verts:
                self._verts[co] = self.bm.verts.new(co)
            verts.append(self._verts[co])
        self.bm.faces.new(verts)


def _mesh(name: str, bm: Any) -> Any:
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    return mesh


def _normal_findings(geometry: Any, name: str, mesh: Any) -> list[dict[str, str]]:
    return [item for item in geometry.geometry_findings(name, mesh) if item["rule"] == NORMALS]


def _add_box(bm: Any, lo: Vec, hi: Vec) -> list[Any]:
    """A closed box with outward faces, from bmesh's unit cube scaled to lo..hi."""
    existing = set(bm.faces)
    result = bmesh.ops.create_cube(bm, size=1.0)
    centre = [(lo[k] + hi[k]) / 2 for k in range(3)]
    span = [hi[k] - lo[k] for k in range(3)]
    for vert in result["verts"]:
        vert.co = tuple(centre[k] + vert.co[k] * span[k] for k in range(3))
    return [face for face in bm.faces if face not in existing]


def _cross(a: Vec, b: Vec) -> Vec:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _unit(v: Vec) -> Vec:
    length = math.sqrt(sum(c * c for c in v))
    return (v[0] / length, v[1] / length, v[2] / length)


def _point(centre: Vec, e1: Vec, s: float, e2: Vec, t: float) -> Vec:
    return tuple(centre[k] + s * e1[k] + t * e2[k] for k in range(3))  # type: ignore[return-value]


def _tilted_quad(rng: random.Random) -> list[Vec]:
    """One quad with a random tilt whose normal points up, wound counter-clockwise about it."""
    theta = math.acos(rng.uniform(0.3, 1.0))
    phi = rng.uniform(0.0, 2.0 * math.pi)
    normal: Vec = (
        math.sin(theta) * math.cos(phi),
        math.sin(theta) * math.sin(phi),
        math.cos(theta),
    )
    helper: Vec = (1.0, 0.0, 0.0) if abs(normal[0]) < 0.9 else (0.0, 1.0, 0.0)
    e1 = _unit(_cross(normal, helper))
    e2 = _cross(normal, e1)  # e1 x e2 == normal, so the corner order winds about +normal
    centre: Vec = (rng.uniform(-10, 10), rng.uniform(-10, 10), rng.uniform(-10, 10))
    w, h = rng.uniform(0.2, 4.0), rng.uniform(0.2, 4.0)
    return [
        _point(centre, e1, -w, e2, -h),
        _point(centre, e1, w, e2, -h),
        _point(centre, e1, w, e2, h),
        _point(centre, e1, -w, e2, h),
    ]


def _room_sheet(*, reverse_wall: bool = False, reverse_all: bool = False) -> _Sheet:
    """A floor and a back wall sharing one edge, both facing into the room."""
    sheet = _Sheet()
    sheet.polygon(FLOOR, reverse=reverse_all)
    sheet.polygon(WALL, reverse=reverse_all != reverse_wall)
    return sheet


def _ground_sheet(
    cells: int = 8, *, reversed_cell: tuple[int, int] | None = None, reverse_all: bool = False
) -> _Sheet:
    """A welded grid of unit quads on the ground plane, wound upward unless reversed."""
    sheet = _Sheet()
    for i in range(cells):
        for j in range(cells):
            corners = [
                (float(i), float(j), 0.0),
                (float(i + 1), float(j), 0.0),
                (float(i + 1), float(j + 1), 0.0),
                (float(i), float(j + 1), 0.0),
            ]
            sheet.polygon(corners, reverse=reverse_all or (i, j) == reversed_cell)
    return sheet


def _overlaps(a: tuple[Vec, Vec], b: tuple[Vec, Vec]) -> bool:
    """True when two boxes share volume; boxes that only touch do not overlap."""
    return all(min(a[1][k], b[1][k]) - max(a[0][k], b[0][k]) > 1e-9 for k in range(3))


def _touching_boxes(rng: random.Random) -> list[tuple[Vec, Vec]]:
    """Two to four boxes where each touches an earlier one, possibly at a vertex or an edge."""
    first_size = [rng.choice(SIZES) for _ in range(3)]
    boxes = [((0.0, 0.0, 0.0), (first_size[0], first_size[1], first_size[2]))]
    for _ in range(rng.randint(2, 4) - 1):
        for _attempt in range(200):
            base_lo, base_hi = rng.choice(boxes)
            axis = rng.randrange(3)
            size = [rng.choice(SIZES) for _ in range(3)]
            lo = [0.0, 0.0, 0.0]
            for k in range(3):
                if k == axis:
                    lo[k] = base_hi[k] if rng.random() < 0.5 else base_lo[k] - size[k]
                else:
                    lo[k] = base_lo[k] + rng.choice(OFFSETS)
            hi = [lo[k] + size[k] for k in range(3)]
            candidate = (tuple(lo), tuple(hi))
            touches = all(
                max(candidate[0][k], base_lo[k]) <= min(candidate[1][k], base_hi[k])
                for k in range(3)
                if k != axis
            )
            if touches and not any(_overlaps(candidate, other) for other in boxes):
                boxes.append(candidate)  # type: ignore[arg-type]
                break
    return boxes  # type: ignore[return-value]


def _merged_boxes(boxes: Sequence[tuple[Vec, Vec]]) -> Any:
    bm = bmesh.new()
    for lo, hi in boxes:
        _add_box(bm, lo, hi)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-6)
    return bm


# ---------------------------------------------------------------------------
# AC1 / SCN001: a correctly facing single open quad passes wherever it sits
# ---------------------------------------------------------------------------


def test_scn001_axis_aligned_quad_passes_at_every_placement(geometry: Any) -> None:
    rng = random.Random(SEED * 1000 + 1)
    for _ in range(PLACEMENTS):
        cx, cy, cz = (rng.uniform(-10, 10) for _ in range(3))
        hx, hy = rng.uniform(0.2, 4.0), rng.uniform(0.2, 4.0)
        corners = [
            (cx - hx, cy - hy, cz),
            (cx + hx, cy - hy, cz),
            (cx + hx, cy + hy, cz),
            (cx - hx, cy + hy, cz),
        ]
        sheet = _Sheet()
        sheet.polygon(corners)
        mesh = _mesh("Quad", sheet.bm)
        try:
            assert _normal_findings(geometry, "Quad", mesh) == [], corners
        finally:
            bpy.data.meshes.remove(mesh)


def test_scn001_tilted_quad_passes_at_every_placement(geometry: Any) -> None:
    rng = random.Random(SEED * 1000 + 2)
    for _ in range(TILTED):
        corners = _tilted_quad(rng)
        sheet = _Sheet()
        sheet.polygon(corners)
        mesh = _mesh("Tilted", sheet.bm)
        try:
            assert _normal_findings(geometry, "Tilted", mesh) == [], corners
        finally:
            bpy.data.meshes.remove(mesh)


def test_scn001_issue_quad_passes(geometry: Any) -> None:
    sheet = _Sheet()
    sheet.polygon(ISSUE_QUAD)
    mesh = _mesh("Issue", sheet.bm)
    assert _normal_findings(geometry, "Issue", mesh) == []


# ---------------------------------------------------------------------------
# AC2 / SCN002: a consistently wound open sheet passes regardless of its facing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("reverse_all", [False, True], ids=["facing_room", "facing_away"])
def test_scn002_floor_and_back_wall_pass(geometry: Any, reverse_all: bool) -> None:
    mesh = _mesh("Room", _room_sheet(reverse_all=reverse_all).bm)
    assert _normal_findings(geometry, "Room", mesh) == []


@pytest.mark.parametrize("reverse_all", [False, True], ids=["upward", "downward"])
def test_scn002_welded_ground_sheet_passes(geometry: Any, reverse_all: bool) -> None:
    mesh = _mesh("Ground", _ground_sheet(reverse_all=reverse_all).bm)
    assert _normal_findings(geometry, "Ground", mesh) == []


# ---------------------------------------------------------------------------
# AC3 / SCN003: inconsistent winding inside an open sheet is still reported
# ---------------------------------------------------------------------------


def test_scn003_reversed_wall_is_counted_once(geometry: Any) -> None:
    mesh = _mesh("Room", _room_sheet(reverse_wall=True).bm)
    findings = _normal_findings(geometry, "Room", mesh)
    assert len(findings) == 1
    assert findings[0]["target"] == "Room"
    assert findings[0]["message"] == "Room has 1 face(s) whose normals are inconsistent or inward."


def test_scn003_reversed_interior_grid_cell_is_counted_once(geometry: Any) -> None:
    mesh = _mesh("Ground", _ground_sheet(reversed_cell=(3, 3)).bm)
    findings = _normal_findings(geometry, "Ground", mesh)
    assert [item["message"] for item in findings] == [
        "Ground has 1 face(s) whose normals are inconsistent or inward."
    ]


def test_scn003_reversed_corner_grid_cell_is_counted_once(geometry: Any) -> None:
    mesh = _mesh("Ground", _ground_sheet(reversed_cell=(0, 7)).bm)
    findings = _normal_findings(geometry, "Ground", mesh)
    assert [item["message"] for item in findings] == [
        "Ground has 1 face(s) whose normals are inconsistent or inward."
    ]


# ---------------------------------------------------------------------------
# AC4 / SCN004: closed islands are still required to face outward
# ---------------------------------------------------------------------------


def test_scn004_correct_closed_box_passes(geometry: Any) -> None:
    bm = bmesh.new()
    _add_box(bm, (0.0, 0.0, 0.0), (1.0, 2.0, 3.0))
    mesh = _mesh("Box", bm)
    assert _normal_findings(geometry, "Box", mesh) == []


@pytest.mark.parametrize("face_index", range(6))
def test_scn004_box_with_one_flipped_face_counts_one(geometry: Any, face_index: int) -> None:
    bm = bmesh.new()
    faces = _add_box(bm, (0.0, 0.0, 0.0), (1.0, 2.0, 3.0))
    bmesh.ops.reverse_faces(bm, faces=[faces[face_index]])
    mesh = _mesh("Box", bm)
    findings = _normal_findings(geometry, "Box", mesh)
    assert [item["message"] for item in findings] == [
        "Box has 1 face(s) whose normals are inconsistent or inward."
    ]


def test_scn004_box_turned_inside_out_counts_six(geometry: Any) -> None:
    bm = bmesh.new()
    faces = _add_box(bm, (0.0, 0.0, 0.0), (1.0, 2.0, 3.0))
    bmesh.ops.reverse_faces(bm, faces=faces)
    mesh = _mesh("Box", bm)
    findings = _normal_findings(geometry, "Box", mesh)
    assert [item["message"] for item in findings] == [
        "Box has 6 face(s) whose normals are inconsistent or inward."
    ]


# ---------------------------------------------------------------------------
# AC5 / SCN005: islands are judged independently
# ---------------------------------------------------------------------------


def test_scn005_exactly_the_flipped_face_of_one_box_is_counted(geometry: Any) -> None:
    bm = bmesh.new()
    _add_box(bm, (0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
    bm.faces.new([bm.verts.new(co) for co in FLAGGED_FLOOR])
    faces = _add_box(bm, (10.0, 10.0, 0.0), (11.0, 11.0, 1.0))
    bmesh.ops.reverse_faces(bm, faces=[faces[2]])
    mesh = _mesh("Mixed", bm)
    findings = _normal_findings(geometry, "Mixed", mesh)
    assert [item["message"] for item in findings] == [
        "Mixed has 1 face(s) whose normals are inconsistent or inward."
    ]


# ---------------------------------------------------------------------------
# AC6 / SCN006: welded touching closed primitives pass
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "boxes",
    [
        pytest.param(
            [((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), ((1.0, 1.0, 1.0), (2.0, 2.0, 2.0))], id="vertex"
        ),
        pytest.param(
            [((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), ((1.0, 1.0, 0.0), (2.0, 2.0, 1.0))], id="edge"
        ),
        pytest.param(
            [((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), ((1.0, 0.5, 0.0), (2.0, 1.5, 1.0))],
            id="partial_face",
        ),
        pytest.param(
            [((0.0, 0.0, 0.0), (1.0, 1.0, 1.0)), ((1.0, 0.5, 0.0), (2.0, 1.0, 1.0))],
            id="partial_face_shared_edge",
        ),
    ],
)
def test_scn006_welded_touching_boxes_pass(geometry: Any, boxes: list[tuple[Vec, Vec]]) -> None:
    mesh = _mesh("Welded", _merged_boxes(boxes))
    assert _normal_findings(geometry, "Welded", mesh) == []


def test_scn006_random_welded_touching_boxes_pass(geometry: Any) -> None:
    rng = random.Random(SEED * 1000 + 6)
    for _ in range(TOUCHING_ARRANGEMENTS):
        boxes = _touching_boxes(rng)
        mesh = _mesh("Welded", _merged_boxes(boxes))
        try:
            assert _normal_findings(geometry, "Welded", mesh) == [], boxes
        finally:
            bpy.data.meshes.remove(mesh)


# ---------------------------------------------------------------------------
# AC7 / SCN007: remediation text fits open surfaces
# ---------------------------------------------------------------------------


def test_scn007_remediation_distinguishes_closed_parts_from_open_sheets(
    report: Any, geometry: Any
) -> None:
    text = report.RULES[NORMALS]
    assert text.startswith("Closed parts:")
    assert "Open sheets" in text
    assert "do not recalculate outside" in text
    assert text != "Recalculate normals outside (Shift+N) so every face points outward."
    sheet = _room_sheet(reverse_wall=True)
    findings = geometry.geometry_findings("Room", _mesh("Room", sheet.bm))
    remediation = [item["remediation"] for item in findings if item["rule"] == NORMALS]
    assert remediation == [text]


# ---------------------------------------------------------------------------
# FR5: both callers keep working with the per-island check
# ---------------------------------------------------------------------------


def test_callers_report_no_normals_finding_for_a_floor_quad(enabled_addon: str) -> None:
    contract = importlib.import_module(f"{enabled_addon}.contract_core")
    inspect = importlib.import_module(f"{enabled_addon}.inspect_core")
    build_crate()
    sheet = _Sheet()
    sheet.polygon([(3.0, 3.0, 0.0), (5.0, 3.0, 0.0), (5.0, 5.0, 0.0), (3.0, 5.0, 0.0)])
    floor = bpy.data.objects.new("SM_Crate_Floor", _mesh("SM_Crate_Floor", sheet.bm))
    bpy.data.collections["Crate"].objects.link(floor)

    validation = contract.validate_asset("Crate", "standard_prop")
    assert [item for item in validation["findings"] if item["rule"] == NORMALS] == []

    inspection = inspect.inspect_asset("Crate", "standard_prop")
    parts = {part["name"]: part for part in inspection["parts"]}
    assert "SM_Crate_Floor" in parts
    assert [item for item in parts["SM_Crate_Floor"]["geometry"] if item["rule"] == NORMALS] == []
