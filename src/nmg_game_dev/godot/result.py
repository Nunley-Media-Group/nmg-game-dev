"""Parse the ``NMG_RESULT {json}`` line a headless GDScript probe prints (#249 FR1)."""

from __future__ import annotations

import json
from typing import Any, Final, NoReturn, cast

from nmg_game_dev.pipeline.errors import PipelineError

RESULT_PREFIX: Final = "NMG_RESULT "


def _fail(error_code: str, message: str) -> NoReturn:
    raise PipelineError(
        code=error_code,
        message=message,
        remediation="Read the Godot output above, fix the reported problem, then rerun.",
        stage=error_code.split(".", 1)[0],
    )


def parse_nmg_result(output: str, *, error_code: str) -> dict[str, Any]:
    """Return the JSON object on the last ``NMG_RESULT`` line of ``output``.

    A missing line, malformed JSON, or a non-object payload raises ``error_code``.
    """
    for line in reversed(output.splitlines()):
        stripped = line.strip()
        if not stripped.startswith(RESULT_PREFIX):
            continue
        try:
            decoded: Any = json.loads(stripped[len(RESULT_PREFIX) :])
        except json.JSONDecodeError as error:
            _fail(error_code, f"NMG_RESULT line is not valid JSON: {error}")
        if not isinstance(decoded, dict):
            _fail(error_code, "NMG_RESULT line does not hold a JSON object")
        return cast(dict[str, Any], decoded)
    _fail(error_code, "Godot printed no NMG_RESULT line; the probe did not report a result")
