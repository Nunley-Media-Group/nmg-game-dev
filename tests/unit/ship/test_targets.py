"""Target expansion and the environment preflight (#6, FR1, FR2, AC9)."""

from __future__ import annotations

import pytest

from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.targets import REQUIRED_ENV, expand_target, preflight_env


def test_groups_expand_in_design_order() -> None:
    assert expand_target("desktop") == ("macos", "windows")
    assert expand_target("mobile") == ("ios", "android")
    assert expand_target("all") == ("macos", "windows", "ios", "android")
    assert expand_target("ios") == ("ios",)


def test_unknown_target_is_a_ship_error() -> None:
    with pytest.raises(ShipError) as caught:
        expand_target("linux")
    assert caught.value.code == "ship.unknown_target"


def test_preflight_names_each_missing_variable_and_no_value() -> None:
    env = {
        "NOTARIZATION_APPLE_ID": "ship-test@example.invalid",
        "NOTARIZATION_APP_SPECIFIC_PASSWORD": "value-that-must-not-leak",
    }
    with pytest.raises(ShipError) as caught:
        preflight_env(("macos",), env)
    error = caught.value
    assert error.code == "ship.env_missing"
    assert "NOTARIZATION_TEAM_ID" in error.message
    assert "NOTARIZATION_APPLE_ID" not in error.message
    assert "value-that-must-not-leak" not in error.message + error.remediation


def test_preflight_passes_when_every_variable_is_set() -> None:
    env = {name: "placeholder" for names in REQUIRED_ENV.values() for name in names}
    preflight_env(("macos", "ios", "android", "windows"), env)


def test_preflight_treats_an_empty_variable_as_missing() -> None:
    env = {name: "placeholder" for name in REQUIRED_ENV["ios"]}
    env["IOS_PROVISIONING_PROFILE"] = ""
    with pytest.raises(ShipError, match="IOS_PROVISIONING_PROFILE"):
        preflight_env(("ios",), env)
