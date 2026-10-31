"""Ship targets: platform groups, their expansion order, and the environment each platform needs.

``expand_target`` returns platforms in the fixed order ``desktop = [macos, windows]``,
``mobile = [ios, android]``, and ``all = [macos, windows, ios, android]``. ``preflight_env``
raises ``ship.env_missing`` naming each unset variable, never its value.

See: specs/6-ship-skills-per-platform-build-sign-notarize-package/design.md (§ Modules)
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, Literal

from nmg_game_dev.ship.errors import ShipError

Platform = Literal["macos", "ios", "android", "windows"]
Target = Literal["macos", "ios", "android", "windows", "desktop", "mobile", "all"]

TARGETS: Final[tuple[str, ...]] = (
    "macos",
    "ios",
    "android",
    "windows",
    "desktop",
    "mobile",
    "all",
)
MOBILE_PLATFORMS: Final[frozenset[Platform]] = frozenset({"ios", "android"})

_APPLE_ID_CREDENTIALS: Final[tuple[str, ...]] = (
    "NOTARIZATION_APPLE_ID",
    "NOTARIZATION_APP_SPECIFIC_PASSWORD",
)

_PLATFORMS: Final[tuple[Platform, ...]] = ("macos", "ios", "android", "windows")
_GROUPS: Final[dict[str, tuple[Platform, ...]]] = {
    "desktop": ("macos", "windows"),
    "mobile": ("ios", "android"),
    "all": ("macos", "windows", "ios", "android"),
}

REQUIRED_ENV: Final[dict[Platform, tuple[str, ...]]] = {
    "macos": (
        "NOTARIZATION_APPLE_ID",
        "NOTARIZATION_APP_SPECIFIC_PASSWORD",
        "NOTARIZATION_TEAM_ID",
    ),
    "ios": ("IOS_PROVISIONING_PROFILE",),
    "android": ("ANDROID_KEYSTORE", "ANDROID_KEYSTORE_PASSWORD"),
    "windows": (
        "WINDOWS_BUILD_HOST",
        "WINDOWS_BUILD_USER",
        "WINDOWS_BUILD_SSH_KEY",
        "WINDOWS_REMOTE_PROJECT_PATH",
    ),
}


def expand_target(target: str) -> tuple[Platform, ...]:
    """Return the ordered platforms for ``target``; raise ``ship.unknown_target`` otherwise."""
    group = _GROUPS.get(target)
    if group is not None:
        return group
    for platform in _PLATFORMS:
        if platform == target:
            return (platform,)
    raise ShipError(
        code="ship.unknown_target",
        message=f"Unknown ship target {target!r}.",
        remediation=f"Use one of: {', '.join(TARGETS)}.",
        stage="preflight",
    )


def _required(platform: Platform, env: Mapping[str, str]) -> tuple[str, ...]:
    """Return the variables ``platform`` needs; a keychain profile replaces the Apple ID pair."""
    if platform == "macos" and env.get("NOTARIZATION_KEYCHAIN_PROFILE"):
        return tuple(name for name in REQUIRED_ENV[platform] if name not in _APPLE_ID_CREDENTIALS)
    return REQUIRED_ENV[platform]


def preflight_env(platforms: Sequence[Platform], env: Mapping[str, str]) -> None:
    """Raise ``ship.env_missing`` naming every required variable that is unset or empty."""
    missing = list(
        dict.fromkeys(
            name for platform in platforms for name in _required(platform, env) if not env.get(name)
        )
    )
    if missing:
        names = ", ".join(missing)
        raise ShipError(
            code="ship.env_missing",
            message=f"Required environment variables are not set: {names}.",
            remediation=(
                f"Set {names} in the environment or in .claude/settings.local.json, "
                "then rerun the ship."
            ),
            stage="preflight",
        )
