"""PIE preflight before each variant import (#149, FR9, AC10).

``import_ue`` must not send an import request while the editor is in Play In Editor (PIE).  The
check is a short UE Python call with a 10 s timeout.  A check that times out counts as busy.

``refuse`` mode fails at once with ``import_ue.editor_busy``.  ``wait`` mode polls every 5 s until
PIE ends or the wait limit passes, then fails the same way.  Either failure tells the caller to stop
PIE and rerun finalize.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Final

from nmg_game_dev.pipeline.clients.unreal_mcp import UnrealTimeoutError
from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.request import PieMode

from .import_asset import parse_nmg_result
from .retry import TimeoutAwareClient

PIE_CHECK_TIMEOUT_S: Final = 10.0
PIE_POLL_S: Final = 5.0
PIE_REMEDIATION: Final = "Stop the Play In Editor session, then rerun finalize."
PIE_CODE: Final = """
import json
import unreal
pie = bool(unreal.get_editor_subsystem(unreal.LevelEditorSubsystem).is_in_play_in_editor())
print("NMG_RESULT " + json.dumps({"pie": pie}, sort_keys=True))
"""

Sleep = Callable[[float], None]
Clock = Callable[[], float]


def is_in_pie(client: TimeoutAwareClient) -> bool:
    """Return ``True`` when the editor is in PIE.  A check that times out counts as busy."""
    try:
        output = client.execute_python_code(PIE_CODE, timeout=PIE_CHECK_TIMEOUT_S)
    except UnrealTimeoutError:
        return True
    return parse_nmg_result(output).get("pie") is True


def ensure_not_in_pie(
    client: TimeoutAwareClient,
    *,
    mode: PieMode,
    wait_s: float,
    poll_s: float = PIE_POLL_S,
    sleep: Sleep = time.sleep,
    clock: Clock = time.monotonic,
) -> None:
    """Return once the editor is out of PIE.  Raise ``import_ue.editor_busy`` otherwise.

    Call this before every import request, so no import is sent while PIE is reported.
    """
    deadline = clock() + wait_s
    while is_in_pie(client):
        if mode == "refuse" or clock() >= deadline:
            raise PipelineError(
                code="import_ue.editor_busy",
                message="The Unreal editor is in Play In Editor (or did not answer the PIE check), "
                "so no import was sent"
                + ("" if mode == "refuse" else f" within the {wait_s:g} s PIE wait limit"),
                remediation=PIE_REMEDIATION,
                stage="import_ue",
            )
        sleep(min(poll_s, max(deadline - clock(), 0.0)))
