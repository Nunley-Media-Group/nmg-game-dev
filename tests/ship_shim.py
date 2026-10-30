"""Shim behind the ship tests' fake tools. Never contacts a service or reads a real credential.

``tests/ship_fakes.py`` writes one wrapper per tool into a sandbox's ``bin/`` folder. Each wrapper
runs ``python ship_shim.py <tool> <args...>``. The shim appends ``{"tool", "argv"}`` to
``$NMG_SHIP_FAKE_LOG`` and then behaves like the tool the ship scripts expect:

- ``RunUAT.sh BuildCookRun`` logs ``Parsing command line: <argv>`` as UE 5.8's AutomationTool does,
  then writes the archive and the cooked content the cook-manifest gate reads. An Android build
  fails, as ``UEDeployAndroid`` does, when no ``KeyStorePassword`` comes from the command line or
  the project's ``Config/UserEngine.ini``.
- ``codesign``, ``security``, ``xcrun``, ``ditto``, ``ssh``, and ``scp`` return canned output.

Failure switches, set in the environment: ``NMG_SHIP_FAKE_UAT_FAIL``,
``NMG_SHIP_FAKE_CODESIGN_FAIL``, ``NMG_SHIP_FAKE_NOTARY_FAIL``. ``NMG_SHIP_FAKE_COOK_LEAK`` is a
relative path written into the cooked output. ``NMG_SHIP_FAKE_UAT_ECHO`` is a line UAT writes to
stderr. ``NMG_SHIP_FAKE_IDENTITIES`` replaces the
``security find-identity`` listing.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DEFAULT_IDENTITIES = (
    '  1) 0123456789ABCDEF0123456789ABCDEF01234567 "Developer ID Application: Example Studio '
    '(SMOKE00000)"\n     1 valid identities found\n'
)


def main(argv: list[str]) -> int:
    tool, args = argv[0], argv[1:]
    log = os.environ.get("NMG_SHIP_FAKE_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"tool": tool, "argv": args}) + "\n")
    if tool == "RunUAT.sh":
        return _uat(args)
    if tool == "codesign":
        return _codesign(args)
    if tool == "security":
        sys.stdout.write(os.environ.get("NMG_SHIP_FAKE_IDENTITIES", DEFAULT_IDENTITIES))
        return 0
    if tool == "xcrun":
        return _xcrun(args)
    if tool == "ditto":
        _write(Path(args[-1]), b"zip")
        return 0
    if tool == "ssh":
        return _ssh(args)
    if tool == "scp":
        return _scp(args)
    sys.stderr.write(f"fake tool not modelled: {tool}\n")
    return 127


def _value(args: list[str], prefix: str) -> str:
    for arg in args:
        if arg.startswith(prefix):
            return arg[len(prefix) :]
    return ""


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _uat(args: list[str]) -> int:
    if os.environ.get("NMG_SHIP_FAKE_UAT_FAIL"):
        sys.stderr.write("UAT: fake failure\n")
        return 1
    sys.stdout.write(f"Parsing command line: {' '.join(args)}\n")
    echo = os.environ.get("NMG_SHIP_FAKE_UAT_ECHO")
    if echo:
        sys.stderr.write(f"echo: {echo}\n")
    project = Path(_value(args, "-project="))
    archive = Path(_value(args, "-archivedirectory="))
    platform = _value(args, "-platform=")
    if platform == "Android" and not _keystore_password(args, project):
        sys.stderr.write("UEDeployAndroid: KeyStorePassword is not set\n")
        return 1
    stem = project.stem
    if platform == "Mac":
        cooked, artifact = "Mac", archive / "Mac" / f"{stem}.app" / "Contents" / "MacOS" / stem
    elif platform == "IOS":
        cooked, artifact = "IOS", archive / "IOS" / f"{stem}.ipa"
    elif platform == "Android":
        cooked, artifact = "Android_ASTC", archive / "Android" / f"{stem}.aab"
    else:
        sys.stderr.write(f"fake UAT: unsupported platform {platform!r}\n")
        return 1
    _write(artifact, b"artifact")
    cooked_root = project.parent / "Saved" / "Cooked" / cooked / stem
    _write(cooked_root / "Content" / "Shared" / "Common.uasset", b"common")
    leak = os.environ.get("NMG_SHIP_FAKE_COOK_LEAK")
    if leak:
        _write(cooked_root / leak, b"leak")
    return 0


def _keystore_password(args: list[str], project: Path) -> str:
    """Return the KeyStorePassword UAT would read from its -ini: overrides or UserEngine.ini."""
    for arg in args:
        _, sep, value = arg.partition("KeyStorePassword=")
        if arg.startswith("-ini:") and sep:
            return value.split(",")[0]
    user_ini = project.parent / "Config" / "UserEngine.ini"
    if user_ini.is_file():
        for line in user_ini.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip() == "KeyStorePassword":
                return value.strip()
    return ""


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


def _ssh(args: list[str]) -> int:
    remote = args[-1]
    if "BuildCookRun" in remote:
        if os.environ.get("NMG_SHIP_FAKE_UAT_FAIL"):
            sys.stderr.write("RunUAT.bat: fake failure\n")
            return 1
        return 0
    if "dir /s /b" in remote:
        base = "C:\\build\\Dogfood\\Saved\\Cooked\\Windows\\Dogfood"
        sys.stdout.write(f"{base}\\Content\\Shared\\Common.uasset\r\n")
        leak = os.environ.get("NMG_SHIP_FAKE_COOK_LEAK")
        if leak:
            win_leak = leak.replace("/", "\\")
            sys.stdout.write(f"{base}\\{win_leak}\r\n")
        return 0
    return 1


def _scp(args: list[str]) -> int:
    dest = Path(args[-1])
    _write(dest / "Windows" / "Dogfood.exe", b"exe")
    _write(dest / "Windows" / "Dogfood" / "Engine" / "CrashReportClient.exe", b"helper")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
