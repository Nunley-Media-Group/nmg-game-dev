"""Signing identity resolution (#6, FR8, AC2, AC9).

The lookup is injected as ``run``, so no test runs the real ``security`` tool.
"""

from __future__ import annotations

import subprocess
from typing import Any

import pytest

from nmg_game_dev.ship.errors import ShipError
from nmg_game_dev.ship.identity import Runner, resolve_signing_identity

_TEAM = "SMOKE00000"
_LISTING = (
    '  1) 1111 "Developer ID Application: Other Studio (OTHER00000)"\n'
    '  2) 2222 "Developer ID Application: Example Studio (SMOKE00000)"\n'
    "     2 valid identities found\n"
)


def _fake_run(stdout: str, calls: list[list[str]], kwargs: list[dict[str, Any]]) -> Runner:
    def run(args: list[str], **options: Any) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        kwargs.append(options)
        return subprocess.CompletedProcess(args=args, returncode=0, stdout=stdout, stderr="")

    return run


def test_explicit_identity_wins_and_runs_nothing() -> None:
    calls: list[list[str]] = []
    kwargs: list[dict[str, Any]] = []
    identity = resolve_signing_identity(
        {"MACOS_SIGNING_IDENTITY": "Developer ID Application: Pinned (PIN0000000)"},
        run=_fake_run(_LISTING, calls, kwargs),
    )
    assert identity == "Developer ID Application: Pinned (PIN0000000)"
    assert calls == []


def test_dry_run_returns_placeholder_without_running_security() -> None:
    calls: list[list[str]] = []
    kwargs: list[dict[str, Any]] = []
    identity = resolve_signing_identity(
        {"NOTARIZATION_TEAM_ID": _TEAM},
        run=_fake_run(_LISTING, calls, kwargs),
        dry_run=True,
    )
    assert identity == f"<Developer ID Application for team {_TEAM}>"
    assert calls == []


def test_first_identity_for_the_team_is_selected() -> None:
    calls: list[list[str]] = []
    kwargs: list[dict[str, Any]] = []
    identity = resolve_signing_identity(
        {"NOTARIZATION_TEAM_ID": _TEAM},
        run=_fake_run(_LISTING, calls, kwargs),
    )
    assert identity == "Developer ID Application: Example Studio (SMOKE00000)"
    assert calls == [["security", "find-identity", "-v", "-p", "codesigning"]]


def test_lookup_runs_under_the_explicit_environment() -> None:
    calls: list[list[str]] = []
    kwargs: list[dict[str, Any]] = []
    resolve_signing_identity(
        {"NOTARIZATION_TEAM_ID": _TEAM, "PATH": "/only/this"},
        run=_fake_run(_LISTING, calls, kwargs),
    )
    assert kwargs[0]["env"] == {"NOTARIZATION_TEAM_ID": _TEAM, "PATH": "/only/this"}


def test_no_identity_for_the_team_is_a_ship_error_with_no_identity_text() -> None:
    calls: list[list[str]] = []
    kwargs: list[dict[str, Any]] = []
    with pytest.raises(ShipError) as caught:
        resolve_signing_identity(
            {"NOTARIZATION_TEAM_ID": "NOPE000000"},
            run=_fake_run(_LISTING, calls, kwargs),
        )
    assert caught.value.code == "ship.signing_identity_missing"
    assert "Example Studio" not in caught.value.message + caught.value.remediation
