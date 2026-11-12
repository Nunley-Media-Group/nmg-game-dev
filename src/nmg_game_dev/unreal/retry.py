"""Bounded retry for Unreal MCP timeouts during ``import_ue`` (#149, FR6-FR8).

Only ``UnrealTimeoutError`` is retried.  The first send is attempt 1.  Each retry sleeps
``base_delay_s * k`` (``k`` is the 1-based retry number), pings the editor with a 10 s timeout,
and re-sends the same code only after the ping gets an answer.  A ping that times out uses up that
retry.  Every other failure propagates unchanged.

``attempts`` counts the first send plus each retry cycle, so a run that times out every time reports
``retries + 1`` attempts.  Defaults are 4 retries and a 20 s base delay, overridable with
``NMG_GAME_DEV_UE_RETRIES`` and ``NMG_GAME_DEV_UE_RETRY_DELAY_S``.
"""

from __future__ import annotations

import math
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Final, Protocol

from nmg_game_dev.pipeline.clients.unreal_mcp import UnrealTimeoutError
from nmg_game_dev.pipeline.errors import PipelineError

RETRIES_ENV: Final = "NMG_GAME_DEV_UE_RETRIES"
RETRY_DELAY_ENV: Final = "NMG_GAME_DEV_UE_RETRY_DELAY_S"
DEFAULT_RETRIES: Final = 4
DEFAULT_RETRY_DELAY_S: Final = 20.0
PING_TIMEOUT_S: Final = 10.0
PING_CODE: Final = 'print("NMG_PING")'
_STAGE: Final = "import_ue"
_RETRY_REMEDIATION: Final = (
    "Wait for the UE editor to finish its current work, then rerun finalize. Raise "
    f"{RETRIES_ENV} or {RETRY_DELAY_ENV} to give the editor longer."
)

Sleep = Callable[[float], None]
Clock = Callable[[], float]


class TimeoutAwareClient(Protocol):
    """The client surface the retry needs: UE Python with an optional per-call timeout."""

    def execute_python_code(self, code: str, *, timeout: float | None = None) -> str:
        """Run UE Python and return the tool's text output."""
        ...


@dataclass(frozen=True)
class RetrySettings:
    """How many times a timed-out Unreal request is retried, and the back-off base in seconds."""

    retries: int
    base_delay_s: float


def retry_settings() -> RetrySettings:
    """Read the retry settings from the environment, falling back to the documented defaults."""
    return RetrySettings(
        retries=_env_whole_number(RETRIES_ENV, DEFAULT_RETRIES),
        base_delay_s=_env_seconds(RETRY_DELAY_ENV, DEFAULT_RETRY_DELAY_S),
    )


def call_with_retry(
    client: TimeoutAwareClient,
    code: str,
    *,
    retries: int,
    base_delay_s: float,
    sleep: Sleep = time.sleep,
    clock: Clock = time.monotonic,
) -> tuple[str, int]:
    """Run ``code`` through ``client`` and return ``(output, attempts)``.

    Raises ``import_ue.failed`` with the attempt count and the seconds spent once every retry is
    used up.  Any failure other than a timeout is raised as it is.
    """
    started = clock()
    attempts = 1
    try:
        return client.execute_python_code(code), attempts
    except UnrealTimeoutError:
        pass

    for retry in range(1, retries + 1):
        sleep(base_delay_s * retry)
        attempts = retry + 1
        try:
            client.execute_python_code(PING_CODE, timeout=PING_TIMEOUT_S)
        except UnrealTimeoutError:
            continue
        try:
            return client.execute_python_code(code), attempts
        except UnrealTimeoutError:
            continue

    raise PipelineError(
        code="import_ue.failed",
        message=f"Unreal MCP did not answer after {attempts} attempts over "
        f"{clock() - started:.0f} s",
        remediation=_RETRY_REMEDIATION,
        stage=_STAGE,
    )


def _env_whole_number(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        value = -1
    if value < 0:
        raise _invalid_setting(name, raw, "a whole number of 0 or more")
    return value


def _env_seconds(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        value = math.nan
    if not math.isfinite(value) or value < 0:
        raise _invalid_setting(name, raw, "a number of seconds, 0 or more")
    return value


def _invalid_setting(name: str, raw: str, expected: str) -> PipelineError:
    return PipelineError(
        code="import_ue.failed",
        message=f"{name} must be {expected}, got {raw!r}",
        remediation=f"Unset {name} or set it to {expected}, then rerun finalize.",
        stage=_STAGE,
    )
