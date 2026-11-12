"""Unreal MCP timeout retry during ``import_ue`` (#149, AC7-AC9, FR6-FR8).

The fake client scripts each reply.  Sleeps and the clock are injected, so no test waits for real
back-off.  No editor is started.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

import pytest

from nmg_game_dev.pipeline.clients.unreal_mcp import UnrealMcpClient, UnrealTimeoutError
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.unreal import import_asset
from nmg_game_dev.unreal.import_asset import import_variant
from nmg_game_dev.unreal.retry import (
    DEFAULT_RETRIES,
    DEFAULT_RETRY_DELAY_S,
    PING_CODE,
    PING_TIMEOUT_S,
    RETRIES_ENV,
    RETRY_DELAY_ENV,
    RetrySettings,
    call_with_retry,
    retry_settings,
)

Reply = str | Exception


def _ok() -> str:
    return "NMG_RESULT " + json.dumps({"ok": True, "static_meshes": {}}, sort_keys=True)


def _timeout() -> UnrealTimeoutError:
    return UnrealTimeoutError(
        "Unreal MCP request timed out after 120 s at http://127.0.0.1:8000/mcp",
        "Wait for the editor to finish its current work, then retry.",
    )


class _Clock:
    """Records each sleep and moves the clock forward by it."""

    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds

    def read(self) -> float:
        return self.now


class _Scripted:
    """A UE client whose import and ping replies are scripted, in order."""

    def __init__(self, imports: list[Reply], pings: list[Reply] | None = None) -> None:
        self.imports = list(imports)
        self.pings = list(pings or [])
        self.calls: list[tuple[str, str, float | None]] = []

    def execute_python_code(self, code: str, *, timeout: float | None = None) -> str:
        if code == PING_CODE:
            self.calls.append(("ping", code, timeout))
            reply: Reply = self.pings.pop(0) if self.pings else "NMG_PING"
        else:
            self.calls.append(("import", code, timeout))
            reply = self.imports.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply

    def kinds(self) -> list[str]:
        return [kind for kind, _, _ in self.calls]

    def import_codes(self) -> list[str]:
        return [code for kind, code, _ in self.calls if kind == "import"]


def _import(client: Any, clock: _Clock, **overrides: Any) -> dict[str, Any]:
    options: dict[str, Any] = {
        "variant_dir": "/exports/Crate/Desktop",
        "dest": "/Game/Props/Crate/Desktop",
        "name": "Crate",
        "report": {"snapshot": {}},
        "sleep": clock.sleep,
        "clock": clock.read,
    }
    options.update(overrides)
    return import_variant(client, **options)


def test_two_timeouts_then_success_takes_three_attempts_with_back_off() -> None:
    client = _Scripted([_timeout(), _timeout(), _ok()])
    clock = _Clock()

    result = _import(client, clock, retry=RetrySettings(retries=4, base_delay_s=20.0))

    assert result["attempts"] == 3
    assert clock.sleeps == [20.0, 40.0]
    assert client.kinds() == ["import", "ping", "import", "ping", "import"]
    assert [timeout for kind, _, timeout in client.calls if kind == "ping"] == [PING_TIMEOUT_S] * 2


def test_a_first_time_success_records_one_attempt_and_never_sleeps() -> None:
    client = _Scripted([_ok()])
    clock = _Clock()

    result = _import(client, clock, retry=RetrySettings(retries=4, base_delay_s=20.0))

    assert result["attempts"] == 1
    assert clock.sleeps == []
    assert client.kinds() == ["import"]


def test_a_client_that_always_times_out_fails_after_five_attempts() -> None:
    client = _Scripted([_timeout() for _ in range(5)])
    clock = _Clock()

    with pytest.raises(PipelineError) as info:
        _import(client, clock, retry=RetrySettings(retries=4, base_delay_s=20.0))

    assert info.value.code == "import_ue.failed"
    assert info.value.stage == "import_ue"
    assert "did not answer after 5 attempts over 200 s" in info.value.message
    assert clock.sleeps == [20.0, 40.0, 60.0, 80.0]
    assert len(client.import_codes()) == 5


def test_a_ping_that_times_out_uses_up_its_retry_without_resending_the_import() -> None:
    client = _Scripted([_timeout(), _ok()], pings=[_timeout(), "NMG_PING"])
    clock = _Clock()

    result = _import(client, clock, retry=RetrySettings(retries=4, base_delay_s=20.0))

    assert result["attempts"] == 3
    assert client.kinds() == ["import", "ping", "ping", "import"]
    assert clock.sleeps == [20.0, 40.0]


def test_environment_overrides_change_the_retry_count_and_the_delay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(RETRIES_ENV, "1")
    monkeypatch.setenv(RETRY_DELAY_ENV, "0.5")
    assert retry_settings() == RetrySettings(retries=1, base_delay_s=0.5)

    client = _Scripted([_timeout(), _timeout()])
    clock = _Clock()
    with pytest.raises(PipelineError) as info:
        _import(client, clock)  # no explicit retry, so the environment decides

    assert "did not answer after 2 attempts" in info.value.message
    assert clock.sleeps == [0.5]


def test_the_documented_defaults_apply_when_the_environment_is_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(RETRIES_ENV, raising=False)
    monkeypatch.delenv(RETRY_DELAY_ENV, raising=False)
    assert DEFAULT_RETRIES == 4
    assert DEFAULT_RETRY_DELAY_S == 20.0
    assert retry_settings() == RetrySettings(retries=4, base_delay_s=20.0)


@pytest.mark.parametrize(
    ("name", "raw"),
    [(RETRIES_ENV, "-1"), (RETRIES_ENV, "many"), (RETRY_DELAY_ENV, "-2"), (RETRY_DELAY_ENV, "nan")],
)
def test_an_invalid_retry_setting_is_refused(
    monkeypatch: pytest.MonkeyPatch, name: str, raw: str
) -> None:
    monkeypatch.setenv(name, raw)
    with pytest.raises(PipelineError) as info:
        retry_settings()
    assert info.value.code == "import_ue.failed"
    assert name in info.value.message


@pytest.mark.parametrize(
    "failure",
    [
        PipelineError(
            code="import_ue.failed", message="HTTP 500", remediation="x", stage="import_ue"
        ),
        PipelineError(
            code="mcp.unreal.unreachable", message="refused", remediation="x", stage="import_ue"
        ),
    ],
    ids=["http_error", "unreachable"],
)
def test_http_errors_and_an_unreachable_editor_are_not_retried(failure: PipelineError) -> None:
    client = _Scripted([failure])
    clock = _Clock()

    with pytest.raises(PipelineError) as info:
        _import(client, clock, retry=RetrySettings(retries=4, base_delay_s=20.0))

    assert info.value.code == failure.code
    assert clock.sleeps == []
    assert client.kinds() == ["import"]


def test_an_editor_reported_failure_is_not_retried() -> None:
    reply = "NMG_RESULT " + json.dumps({"ok": False, "error": "asset not found"})
    client = _Scripted([reply])
    clock = _Clock()

    with pytest.raises(PipelineError) as info:
        _import(client, clock, retry=RetrySettings(retries=4, base_delay_s=20.0))

    assert info.value.code == "import_ue.failed"
    assert "asset not found" in info.value.message
    assert clock.sleeps == []
    assert client.kinds() == ["import"]


def test_a_retried_import_sends_the_identical_code_and_checks_pivots_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _Scripted([_timeout(), _ok()])
    clock = _Clock()
    checks: list[dict[str, Any]] = []
    real_check = import_asset.check_pivots

    def counting_check(report: dict[str, Any], result: dict[str, Any]) -> None:
        checks.append(result)
        real_check(report, result)

    monkeypatch.setattr(import_asset, "check_pivots", counting_check)

    _import(client, clock, retry=RetrySettings(retries=4, base_delay_s=20.0))

    first, second = client.import_codes()
    assert first == second
    # The template reuses the existing assets, so a re-sent import cannot duplicate them.
    assert "task.replace_existing = True" in first
    assert "_instance(tools, dest" in first
    assert len(checks) == 1
    assert checks[0]["attempts"] == 2


def test_call_with_retry_returns_the_output_and_its_attempts() -> None:
    client = _Scripted([_timeout(), _ok()])
    clock = _Clock()

    output, attempts = call_with_retry(
        client, "print(1)", retries=4, base_delay_s=1.0, sleep=clock.sleep, clock=clock.read
    )

    assert output == _ok()
    assert attempts == 2


def test_a_request_that_times_out_is_an_unreal_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timed_out(request: object, timeout: float) -> None:
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", timed_out)
    client = UnrealMcpClient("http://127.0.0.1:9/mcp", timeout=3)

    with pytest.raises(UnrealTimeoutError) as info:
        client.execute_python_code("print(1)")

    assert info.value.code == "import_ue.failed"
    assert info.value.stage == "import_ue"
    assert "timed out after 3 s" in info.value.message


def test_a_connect_timeout_is_also_an_unreal_timeout_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def timed_out(request: object, timeout: float) -> None:
        raise urllib.error.URLError(TimeoutError("connect timed out"))

    monkeypatch.setattr(urllib.request, "urlopen", timed_out)

    with pytest.raises(UnrealTimeoutError):
        UnrealMcpClient("http://127.0.0.1:9/mcp", timeout=3).execute_python_code("print(1)")


def test_a_per_call_timeout_replaces_the_client_timeout_for_that_call_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[float] = []

    def record(request: object, timeout: float) -> None:
        seen.append(timeout)
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", record)
    client = UnrealMcpClient("http://127.0.0.1:9/mcp", timeout=120)

    with pytest.raises(UnrealTimeoutError):
        client.execute_python_code("print(1)", timeout=10)
    with pytest.raises(UnrealTimeoutError):
        client.execute_python_code("print(2)")

    assert seen[0] == 10
    assert seen[-1] == 120
