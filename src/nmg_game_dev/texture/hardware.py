"""Hardware and weights checks that decide whether a backend can run here (#7 FR13, AC14, AC15).

``availability`` is a pure function of injected facts, so tests pass ``HardwareFacts`` directly.
Production code calls ``probe()`` for the real host.
"""

from __future__ import annotations

import platform
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.paths import install_command, weights_dir
from nmg_game_dev.texture.registry import BackendSpec

Availability = Literal["available", "not_installed", "unsupported_platform", "insufficient_memory"]

RESERVE_ENV = "TEXTURE_GEN_BLENDER_RESERVE_GB"
DEFAULT_RESERVE_GB = 8.0

_CODES: dict[str, str] = {
    "not_installed": "texture.model_not_installed",
    "unsupported_platform": "texture.unsupported_platform",
    "insufficient_memory": "texture.insufficient_memory",
}


@dataclass(frozen=True)
class HardwareFacts:
    """What the host offers: OS name, CPU architecture, and total RAM in GiB."""

    system: str
    machine: str
    total_ram_gb: float


def probe() -> HardwareFacts:
    """Read the real host facts. RAM comes from ``sysctl hw.memsize``; 0 when unavailable."""
    return HardwareFacts(
        system=platform.system(),
        machine=platform.machine(),
        total_ram_gb=_total_ram_gb(),
    )


def _total_ram_gb() -> float:
    try:
        out = subprocess.run(
            ["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, check=True
        ).stdout
        return int(out.strip()) / 2**30
    except (OSError, subprocess.CalledProcessError, ValueError):
        return 0.0


def reserve_gb(env: Mapping[str, str]) -> float:
    """RAM kept free for Blender, from ``TEXTURE_GEN_BLENDER_RESERVE_GB`` (default 8)."""
    raw = env.get(RESERVE_ENV)
    if raw is None or raw.strip() == "":
        return DEFAULT_RESERVE_GB
    try:
        value = float(raw)
    except ValueError:
        raise TextureGenError(
            "texture.invalid_request",
            f"{RESERVE_ENV} must be a number of GiB, got {raw!r}.",
            f"Set {RESERVE_ENV} to a number such as {DEFAULT_RESERVE_GB:g}, or unset it.",
        ) from None
    if value < 0:
        raise TextureGenError(
            "texture.invalid_request",
            f"{RESERVE_ENV} must not be negative, got {raw!r}.",
            f"Set {RESERVE_ENV} to zero or a positive number of GiB, or unset it.",
        )
    return value


def availability(
    spec: BackendSpec,
    facts: HardwareFacts,
    models_dir: Path | None,
    reserve: float,
) -> Availability:
    """Report whether ``spec`` can run: hardware first, then memory, then installed weights."""
    if facts.system != "Darwin" or facts.machine != "arm64":
        return "unsupported_platform"
    if facts.total_ram_gb - reserve < spec.peak_memory_gb:
        return "insufficient_memory"
    if models_dir is None:
        return "not_installed"
    weights = weights_dir(spec, models_dir)
    if not weights.is_dir() or not any(weights.iterdir()):
        return "not_installed"
    return "available"


def require_available(
    spec: BackendSpec,
    facts: HardwareFacts,
    models_dir: Path | None,
    reserve: float,
) -> None:
    """Raise the matching ``texture.*`` error unless ``spec`` is available."""
    status = availability(spec, facts, models_dir, reserve)
    if status == "available":
        return
    code = _CODES[status]
    if status == "not_installed":
        if models_dir is None:
            where = "TEXTURE_GEN_MODELS_DIR is unset"
            expected = f"<models dir>/{spec.id}-q4"
        else:
            where = f"no weights at {weights_dir(spec, models_dir)}"
            expected = str(weights_dir(spec, models_dir))
        raise TextureGenError(
            code,
            f"Backend {spec.id!r} is not installed: {where}.",
            (
                f"Run /onboard-consumer to install the local texture models, or run "
                f"`{install_command(spec.id, models_dir or Path('<models dir>'))}` "
                f"(expected at {expected})."
            ),
        )
    if status == "unsupported_platform":
        message = (
            f"Backend {spec.id!r} needs Apple Silicon macOS; this host is "
            f"{facts.system} {facts.machine}."
        )
        remediation = (
            "Run texture generation on an Apple Silicon Mac, or use procedural Blender materials."
        )
    else:
        available_gb = facts.total_ram_gb - reserve
        message = (
            f"Backend {spec.id!r} needs about {spec.peak_memory_gb:g} GB; "
            f"{available_gb:.1f} GB is free after the Blender reserve of {reserve:g} GB."
        )
        remediation = (
            f"Close other memory-heavy apps, lower {RESERVE_ENV} if Blender is idle, "
            "or generate on a Mac with more memory."
        )
    raise TextureGenError(code, message, remediation)
