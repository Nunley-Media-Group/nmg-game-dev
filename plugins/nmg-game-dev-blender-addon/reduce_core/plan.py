"""Reduce plan: the budget split, override checks, bake settings, and miss threshold (#139).

Pure Python on purpose: the unit suite loads this file by path under plain CPython, so it must
not import bpy or use relative imports. Every function here is arithmetic on numbers and names.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any, Final, NamedTuple

DEFAULTS: Final[dict[str, Any]] = {
    "cage_extrusion": 0.03,
    "max_ray_distance": 0.10,
    "miss_threshold": 0.01,
    "smooth_angle_deg": 40,
    "min_part_tris": 12,
    "samples": {"BC": 4, "R": 4, "M": 4, "N": 8, "AO": 48},
}

_OVERRIDE_KEYS: Final = frozenset({"share", "tris", "cage_extrusion", "max_ray_distance"})
_SETTING_KEYS: Final = ("cage_extrusion", "max_ray_distance")


class ReduceError(Exception):
    """A reduce step that must stop before or after the change, with a stable code."""

    def __init__(self, code: str, message: str, remediation: str, target: str = "") -> None:
        super().__init__(f"{code}: {message} {remediation}".strip())
        self.code = code
        self.message = message
        self.remediation = remediation
        self.target = target

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "remediation": self.remediation,
            "target": self.target,
        }


class PartStats(NamedTuple):
    """One source part: its world-space surface area in square metres and its triangle count."""

    area_m2: float
    tris: int


def split_budget(
    parts: Mapping[str, PartStats],
    budget: int,
    overrides: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    """Return each part's triangle target: overrides first, then the rest split by area.

    An override's ``tris`` is used as given, or ``floor(share * budget)`` for ``share``. The
    remaining budget is split among the other parts in proportion to area, with at least
    DEFAULTS["min_part_tris"] each (or the part's own triangles when it has fewer). A target
    never exceeds its source triangles. Overrides are refused before any change is made.
    """
    _check_overrides(parts, overrides)
    fixed: dict[str, int] = {}
    for name, spec in overrides.items():
        if "share" in spec and spec["share"] is not None:
            wanted = math.floor(float(spec["share"]) * budget)
        elif "tris" in spec and spec["tris"] is not None:
            wanted = int(spec["tris"])
        else:
            continue
        fixed[name] = min(wanted, parts[name].tris)

    if sum(fixed.values()) > budget:
        raise ReduceError(
            "reduce.overrides_exceed_budget",
            f"The part overrides total {sum(fixed.values())} triangles, above the "
            f"{budget}-triangle Desktop budget.",
            "Lower the share or tris values so they fit within the Desktop budget.",
        )

    others = [name for name in parts if name not in fixed]
    if not others:
        return dict(fixed)

    floors = {name: min(DEFAULTS["min_part_tris"], parts[name].tris) for name in others}
    remaining = budget - sum(fixed.values())
    if remaining < sum(floors.values()):
        if overrides:
            raise ReduceError(
                "reduce.overrides_exceed_budget",
                f"The overrides leave {remaining} triangles for {len(others)} other part(s), "
                f"fewer than the {sum(floors.values())} they need at minimum.",
                "Lower the overrides, or raise the Desktop budget in nmg-budgets.json.",
            )
        raise ReduceError(
            "reduce.budget_too_small",
            f"The {budget}-triangle Desktop budget cannot hold {len(others)} part(s) at "
            f"{DEFAULTS['min_part_tris']} triangles each.",
            "Raise the Desktop tris budget in nmg-budgets.json.",
        )

    weights = {name: parts[name].area_m2 for name in others}
    if sum(weights.values()) <= 0.0:
        weights = {name: float(parts[name].tris) for name in others}
    total_weight = sum(weights.values())
    targets: dict[str, int] = {}
    for name in others:
        share = math.floor(remaining * weights[name] / total_weight) if total_weight > 0 else 0
        targets[name] = min(max(share, floors[name]), parts[name].tris)

    excess = sum(targets.values()) - remaining
    while excess > 0:
        name = max(others, key=lambda item: targets[item] - floors[item])
        room = targets[name] - floors[name]
        if room <= 0:
            raise ReduceError(
                "reduce.overrides_exceed_budget",
                "The part targets cannot be fitted within the Desktop budget.",
                "Lower the overrides, or raise the Desktop budget in nmg-budgets.json.",
            )
        take = min(room, excess)
        targets[name] -= take
        excess -= take

    return {**fixed, **targets}


def bake_settings(
    part_names: list[str],
    asset_wide: Mapping[str, float | None],
    per_part: Mapping[str, Mapping[str, float | None]],
) -> dict[str, dict[str, float]]:
    """Cage extrusion and ray distance for each part: per part, then asset-wide, then DEFAULTS.

    Every value must be greater than zero. A per-part entry for a name that is not a part is
    reduce.unknown_part.
    """
    known = set(part_names)
    for name in per_part:
        if name not in known:
            raise ReduceError(
                "reduce.unknown_part",
                f"Per-part settings name {name!r}, which is not a part of the asset.",
                f"Use one of: {', '.join(part_names)}.",
                target=name,
            )
    resolved: dict[str, dict[str, float]] = {}
    for name in part_names:
        values: dict[str, float] = {}
        for key in _SETTING_KEYS:
            value = _pick(per_part.get(name, {}), key)
            if value is None:
                value = _pick(asset_wide, key)
            if value is None:
                value = DEFAULTS[key]
            if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
                raise ReduceError(
                    "reduce.invalid_override",
                    f"{key} for {name!r} must be a number greater than zero, got {value!r}.",
                    f"Set {key} to a positive distance in metres.",
                    target=name,
                )
            values[key] = float(value)
        resolved[name] = values
    return resolved


def unbaked_share(island_px: int, missed_px: int) -> float:
    """Share of an island's texels that no ray reached: 0.0 when the island has no texels."""
    if island_px <= 0:
        return 0.0
    return missed_px / island_px


def check_misses(
    shares: Mapping[str, float],
    threshold: float,
    settings: Mapping[str, Mapping[str, float]],
) -> None:
    """Raise reduce.bake_misses for the first part whose unbaked share exceeds threshold."""
    for name, share in shares.items():
        if share > threshold:
            used = settings.get(name, {})
            raise ReduceError(
                "reduce.bake_misses",
                f"Part {name!r} has {share:.2%} of its texels unbaked, above the "
                f"{threshold:.2%} limit (cage_extrusion {used.get('cage_extrusion')} m, "
                f"max_ray_distance {used.get('max_ray_distance')} m).",
                "Raise max_ray_distance or cage_extrusion for this part, or lower "
                "miss_threshold only if the gaps are acceptable, then rerun the reduce.",
                target=name,
            )


def _check_overrides(
    parts: Mapping[str, PartStats], overrides: Mapping[str, Mapping[str, Any]]
) -> None:
    for name, spec in overrides.items():
        if name not in parts:
            raise ReduceError(
                "reduce.unknown_part",
                f"Override names {name!r}, which is not a part of the asset.",
                f"Use one of: {', '.join(parts)}.",
                target=name,
            )
        unknown = set(spec) - _OVERRIDE_KEYS
        if unknown:
            raise ReduceError(
                "reduce.invalid_override",
                f"Override for {name!r} has unknown key(s): {', '.join(sorted(unknown))}.",
                "Use share or tris for the triangle split.",
                target=name,
            )
        share = spec.get("share")
        tris = spec.get("tris")
        if share is not None and tris is not None:
            raise ReduceError(
                "reduce.invalid_override",
                f"Override for {name!r} sets both share and tris.",
                "Set one of share or tris for each part.",
                target=name,
            )
        if share is not None and (
            isinstance(share, bool) or not isinstance(share, int | float) or not 0 < share <= 1
        ):
            raise ReduceError(
                "reduce.invalid_override",
                f"Share for {name!r} must be greater than 0 and at most 1, got {share!r}.",
                "Set share to a fraction of the Desktop budget, such as 0.25.",
                target=name,
            )
        if tris is not None and (isinstance(tris, bool) or not isinstance(tris, int) or tris <= 0):
            raise ReduceError(
                "reduce.invalid_override",
                f"Tris for {name!r} must be a positive whole number, got {tris!r}.",
                "Set tris to a positive triangle count.",
                target=name,
            )


def _pick(values: Mapping[str, Any], key: str) -> Any:
    value = values.get(key)
    return None if value is None else value
