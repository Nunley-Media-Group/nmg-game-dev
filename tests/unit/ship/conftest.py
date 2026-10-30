"""Fixtures for the ship unit tests: a fresh sandbox per test, from tests/ship_fakes.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.ship_fakes import ShipSandbox, make_sandbox


@pytest.fixture
def sandbox(tmp_path: Path) -> ShipSandbox:
    return make_sandbox(tmp_path)
