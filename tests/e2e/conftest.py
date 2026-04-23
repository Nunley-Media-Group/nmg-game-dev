"""E2E test configuration — adds ``--runslow`` option and ``slow`` marker.

E2E tests are gated behind ``pytest --runslow`` so that the default
``pytest tests/`` run skips the full-stack suite (which requires a running
Blender + UE + Meshy environment).

Usage::

    pytest tests/e2e/ --runslow          # run the e2e suite
    pytest tests/e2e/                    # skips all slow tests (default)
"""

from __future__ import annotations

import pytest


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--runslow",
        action="store_true",
        default=False,
        help="Run slow end-to-end tests that require live Blender + UE + Meshy.",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow / requiring live MCP servers (deselect with -m 'not slow')",
    )


def pytest_collection_modifyitems(
    config: pytest.Config,
    items: list[pytest.Item],
) -> None:
    if not config.getoption("--runslow"):
        skip_slow = pytest.mark.skip(reason="Pass --runslow to run end-to-end tests")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
