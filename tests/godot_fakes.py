"""An in-process stand-in for ``godot --headless`` (#249).

``FakeGodotRunner`` records every argv and answers from a script:

- ``--import`` succeeds, or prints an ``ERROR:`` line when ``import_errors`` is true.
- ``-s res://.../<probe>.gd -- <params.json>`` looks up ``responses["<probe>.gd"]``. The value may
  be a dict (printed as the ``NMG_RESULT`` line), a list of dicts (one per call, in order), a
  callable taking the params dict and returning a dict, or a ``CommandResult`` returned as is.
- Any other command looks up ``responses[args[0]]`` (for example ``"--export-release"``). The
  value may be a ``CommandResult`` or a callable ``(args, project) -> CommandResult``; absent keys
  succeed.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

from nmg_game_dev.godot.runner import CommandResult

ProbeResponse = (
    dict[str, Any] | list[dict[str, Any]] | Callable[[dict[str, Any]], Any] | CommandResult
)


class FakeGodotRunner:
    """Records every headless Godot call and returns scripted output."""

    def __init__(
        self,
        responses: Mapping[str, Any] | None = None,
        *,
        import_errors: bool = False,
    ) -> None:
        self.responses: dict[str, Any] = dict(responses or {})
        self.import_errors = import_errors
        self.calls: list[list[str]] = []
        self.projects: list[Path] = []
        self.params: list[dict[str, Any]] = []
        self.envs: list[dict[str, str] | None] = []

    def run(
        self,
        args: Sequence[str],
        *,
        project: Path,
        timeout: float | None = None,
        env: Mapping[str, str] | None = None,
    ) -> CommandResult:
        argv = list(args)
        self.calls.append(argv)
        self.projects.append(project)
        self.envs.append(None if env is None else dict(env))
        if argv[:1] == ["--import"]:
            if self.import_errors:
                return CommandResult(1, stdout="ERROR: Failed loading resource: res://bad.glb\n")
            return CommandResult(0, stdout="")
        if argv[:1] == ["-s"] and "--" in argv:
            return self._probe(argv)
        handler = self.responses.get(argv[0]) if argv else None
        if handler is None:
            return CommandResult(0)
        if isinstance(handler, CommandResult):
            return handler
        result = handler(argv, project)
        assert isinstance(result, CommandResult)
        return result

    def _probe(self, argv: list[str]) -> CommandResult:
        script = Path(argv[1]).name
        params_path = Path(argv[argv.index("--") + 1])
        params: dict[str, Any] = (
            json.loads(params_path.read_text(encoding="utf-8")) if params_path.is_file() else {}
        )
        self.params.append(params)
        response = self.responses.get(script)
        if response is None:
            return CommandResult(1, stderr=f"ERROR: no scripted response for {script}")
        if isinstance(response, CommandResult):
            return response
        if isinstance(response, list):
            if not response:
                return CommandResult(1, stderr=f"ERROR: scripted responses for {script} ran out")
            payload = response.pop(0)
        elif callable(response):
            payload = response(params)
            if isinstance(payload, CommandResult):
                return payload
        else:
            payload = response
        return CommandResult(0, stdout=f"Godot Engine v4\nNMG_RESULT {json.dumps(payload)}\n")

    # Convenience views over the recorded calls.
    def probe_calls(self, script: str | None = None) -> list[list[str]]:
        """Return the recorded ``-s`` calls, optionally only those for ``script``."""
        return [
            call
            for call in self.calls
            if call[:1] == ["-s"] and (script is None or Path(call[1]).name == script)
        ]

    def count(self, flag: str) -> int:
        """Return how many recorded calls start with ``flag``."""
        return sum(1 for call in self.calls if call[:1] == [flag])
