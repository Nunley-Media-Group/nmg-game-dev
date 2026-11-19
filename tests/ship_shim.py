"""Shim behind the ship tests' fake tools. Never contacts a service or reads a real credential.

``tests/ship_fakes.py`` writes one wrapper per tool into a sandbox's ``bin/`` folder. Each wrapper
runs ``python ship_shim.py <tool> <args...>``. The shim appends ``{"tool", "argv"}`` to
``$NMG_SHIP_FAKE_LOG`` and then behaves like the tool the ship flow expects:

- ``security find-identity`` lists one Developer ID identity (``NMG_SHIP_FAKE_IDENTITIES`` replaces
  the listing). ``security cms -D -i <profile>`` prints a provisioning-profile plist whose UUID is
  ``NMG_SHIP_FAKE_PROFILE_UUID`` (default below); ``NMG_SHIP_FAKE_PROFILE_FAIL`` makes it fail.
- ``codesign``, ``xcrun``, and ``ditto`` return canned output.

Failure switches, set in the environment: ``NMG_SHIP_FAKE_CODESIGN_FAIL``,
``NMG_SHIP_FAKE_NOTARY_FAIL``, ``NMG_SHIP_FAKE_PROFILE_FAIL``.
"""

from __future__ import annotations

import json
import os
import plistlib
import sys
from pathlib import Path

DEFAULT_IDENTITIES = (
    '  1) 0123456789ABCDEF0123456789ABCDEF01234567 "Developer ID Application: Example Studio '
    '(SMOKE00000)"\n     1 valid identities found\n'
)
DEFAULT_PROFILE_UUID = "11111111-2222-3333-4444-555555555555"


def main(argv: list[str]) -> int:
    tool, args = argv[0], argv[1:]
    log = os.environ.get("NMG_SHIP_FAKE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"tool": tool, "argv": args}) + "\n")
    if tool == "codesign":
        return _codesign(args)
    if tool == "security":
        return _security(args)
    if tool == "xcrun":
        return _xcrun(args)
    if tool == "ditto":
        _write(Path(args[-1]), b"zip")
        return 0
    sys.stderr.write(f"fake tool not modelled: {tool}\n")
    return 127


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _security(args: list[str]) -> int:
    if args[:1] == ["cms"]:
        if os.environ.get("NMG_SHIP_FAKE_PROFILE_FAIL"):
            sys.stderr.write("security: SecCMSDecoder failed\n")
            return 1
        profile = {
            "Name": "Dogfood App Store",
            "TeamIdentifier": ["SMOKE00000"],
            "UUID": os.environ.get("NMG_SHIP_FAKE_PROFILE_UUID", DEFAULT_PROFILE_UUID),
        }
        sys.stdout.write(plistlib.dumps(profile).decode("utf-8"))
        return 0
    sys.stdout.write(os.environ.get("NMG_SHIP_FAKE_IDENTITIES", DEFAULT_IDENTITIES))
    return 0


def _codesign(args: list[str]) -> int:
    if os.environ.get("NMG_SHIP_FAKE_CODESIGN_FAIL") and "--verify" not in args:
        sys.stderr.write("codesign: fake failure\n")
        return 1
    return 0


def _xcrun(args: list[str]) -> int:
    if args[:2] == ["notarytool", "submit"]:
        if os.environ.get("NMG_SHIP_FAKE_NOTARY_FAIL"):
            sys.stdout.write("Conducting pre-submission checks\n  status: Invalid\n")
            return 1
        sys.stdout.write("Conducting pre-submission checks\n  status: Accepted\n")
        return 0
    if args[:1] == ["stapler"]:
        return 0
    sys.stderr.write(f"fake xcrun: unsupported subcommand {args[:1]}\n")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
