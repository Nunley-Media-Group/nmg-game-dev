#!/usr/bin/env python3
"""Build /nmg-game-dev/Materials/M_NmgORM in UE 5.8 (#69, FR5; headless mode #204).

    uv run --group dev python scripts/unreal/build_master_material.py [--url URL]
    uv run --group dev python scripts/unreal/build_master_material.py --headless

The graph has three texture parameters. ``BaseColor`` (Color) is multiplied by the ``Tint`` vector
parameter (default white, #148) and feeds Base Color, ``Normal`` (Normal) feeds Normal, and ``ORM``
(Masks) feeds Ambient Occlusion from R, Roughness from G, and Metallic from B. Each sampler starts
from a default texture of its own sampler type:
``DefaultTexture`` for BaseColor, ``DefaultNormal`` for Normal, and ``DefaultDiffuse_TC_Masks``
for ORM. The material is also enabled for skeletal meshes, so instances compile on both mesh
types. The nmg-game-dev plugin mounts at /nmg-game-dev/, so the asset saves to
plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset.

Running it again rebuilds the graph of an existing M_NmgORM in place, so material instances
keep their parent. The default mode sends the UE work through UnrealMcpClient to a running
editor, and the result is read from the NMG_RESULT line the UE code prints.

``--headless`` needs no running editor. It builds ``DogfoodEditor`` with ``Build.sh``, then runs
the same graph code in a separate ``UnrealEditor-Cmd`` process that opens fixtures/dogfood.uproject
with the MCP plugins disabled and tracing off (``-notrace``), so the process binds no MCP port and
forks no trace server. Headless mode never constructs UnrealMcpClient or opens a connection.
``UE_ROOT`` overrides the engine install (default /Users/Shared/Epic Games/UE_5.8).

Exit codes: 0 built and saved. 1 UE reported an error, or printed no result line. 2 the Unreal MCP
endpoint is unreachable (MCP mode). 3 a headless prerequisite is missing, or the DogfoodEditor
build failed (``--headless``).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

from nmg_game_dev.pipeline.clients.unreal_mcp import UnrealMcpClient  # noqa: E402
from nmg_game_dev.pipeline.errors import PipelineError  # noqa: E402
from nmg_game_dev.unreal.import_asset import parse_nmg_result  # noqa: E402

_MATERIAL_CODE: Final = r"""
import json
import unreal

PACKAGE_DIR = "/nmg-game-dev/Materials"
NAME = "M_NmgORM"
RESULT = {"ok": False, "asset": PACKAGE_DIR + "/" + NAME, "error": None}


def _sampler(material, parameter, y, sampler_type, default_texture):
    node = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureSampleParameter2D, -700, y
    )
    node.set_editor_property("parameter_name", parameter)
    node.set_editor_property("sampler_type", sampler_type)
    texture = unreal.EditorAssetLibrary.load_asset(default_texture)
    if not isinstance(texture, unreal.Texture):
        raise RuntimeError("could not load default texture " + default_texture)
    node.set_editor_property("texture", texture)
    return node


def _clear(material):
    # delete_all_material_expressions can leave a node behind, so delete node by node and retry.
    mel = unreal.MaterialEditingLibrary
    for _ in range(3):
        remaining = list(mel.get_material_expressions(material))
        if not remaining:
            return
        for expression in remaining:
            mel.delete_material_expression(material, expression)
    if list(mel.get_material_expressions(material)):
        raise RuntimeError("could not clear the existing M_NmgORM graph")


def _tint(material):
    # Tint is the one vector parameter (#148, FR6). Its white default leaves a base colour as it is.
    node = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionVectorParameter, -700, 700
    )
    node.set_editor_property("parameter_name", "Tint")
    node.set_editor_property("default_value", unreal.LinearColor(1.0, 1.0, 1.0, 1.0))
    return node


def _build(material):
    mel = unreal.MaterialEditingLibrary
    base = _sampler(
        material,
        "BaseColor",
        -200,
        unreal.MaterialSamplerType.SAMPLERTYPE_COLOR,
        "/Engine/EngineResources/DefaultTexture",
    )
    tint = _tint(material)
    tinted = mel.create_material_expression(material, unreal.MaterialExpressionMultiply, -300, -200)
    mel.connect_material_expressions(base, "RGB", tinted, "A")
    mel.connect_material_expressions(tint, "", tinted, "B")
    mel.connect_material_property(tinted, "", unreal.MaterialProperty.MP_BASE_COLOR)
    normal = _sampler(
        material,
        "Normal",
        100,
        unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL,
        "/Engine/EngineMaterials/DefaultNormal",
    )
    mel.connect_material_property(normal, "RGB", unreal.MaterialProperty.MP_NORMAL)
    orm = _sampler(
        material,
        "ORM",
        400,
        unreal.MaterialSamplerType.SAMPLERTYPE_MASKS,
        "/Engine/EngineMaterials/DefaultDiffuse_TC_Masks",
    )
    mel.connect_material_property(orm, "R", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    mel.connect_material_property(orm, "G", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(orm, "B", unreal.MaterialProperty.MP_METALLIC)
    material.set_editor_property("used_with_skeletal_mesh", True)
    mel.recompile_material(material)


def _run():
    path = PACKAGE_DIR + "/" + NAME
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        material = unreal.EditorAssetLibrary.load_asset(path)
        if not isinstance(material, unreal.Material):
            raise RuntimeError(path + " exists and is not a Material")
        _clear(material)
    else:
        material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            NAME, PACKAGE_DIR, unreal.Material, unreal.MaterialFactoryNew()
        )
    if material is None:
        raise RuntimeError("could not create " + path)
    _build(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    RESULT["ok"] = True


try:
    _run()
except Exception as error:
    RESULT["error"] = type(error).__name__ + ": " + str(error)
print("NMG_RESULT " + json.dumps(RESULT, sort_keys=True))
"""


DOGFOOD_PROJECT: Final = REPO_ROOT / "fixtures" / "dogfood.uproject"
DEFAULT_UE_ROOT: Final = "/Users/Shared/Epic Games/UE_5.8"
BUILD_SCRIPT: Final = Path("Engine/Build/BatchFiles/Mac/Build.sh")
EDITOR_CMD: Final = Path("Engine/Binaries/Mac/UnrealEditor-Cmd")
DISABLED_PLUGINS: Final = "ModelContextProtocol,EditorToolset,VibeUE"
RESULT_MARKER: Final = "NMG_RESULT "
EXIT_HEADLESS_UNAVAILABLE: Final = 3


def _print_pipeline_error(error: PipelineError) -> None:
    print(f"ERROR [{error.code}] {error.message}", file=sys.stderr)
    print(f"Remediation: {error.remediation}", file=sys.stderr)


def _report(result: dict[str, Any]) -> int:
    if result.get("ok") is not True:
        print(
            f"ERROR [import_ue.failed] {result.get('error') or 'UE reported no error text'}",
            file=sys.stderr,
        )
        return 1
    print(f"Built {result['asset']}")
    return 0


def _build_via_mcp(url: str | None) -> int:
    try:
        with UnrealMcpClient(url) as client:
            output = client.execute_python_code(_MATERIAL_CODE)
        result = parse_nmg_result(output)
    except PipelineError as error:
        _print_pipeline_error(error)
        return 2 if error.code == "mcp.unreal.unreachable" else 1
    return _report(result)


def _missing_headless_path(ue_root: Path) -> Path | None:
    for executable in (ue_root / BUILD_SCRIPT, ue_root / EDITOR_CMD):
        if not (executable.is_file() and os.access(executable, os.X_OK)):
            return executable
    return None if DOGFOOD_PROJECT.is_file() else DOGFOOD_PROJECT


def _report_headless(returncode: int, output: str) -> int:
    lines = [
        line[line.index(RESULT_MARKER) :] for line in output.splitlines() if RESULT_MARKER in line
    ]
    if not lines:
        print(
            f"ERROR [import_ue.failed] UnrealEditor-Cmd exited {returncode} "
            "and printed no NMG_RESULT line",
            file=sys.stderr,
        )
        print("\n".join(output.splitlines()[-20:]), file=sys.stderr)
        return 1
    try:
        result = parse_nmg_result("\n".join(lines))
    except PipelineError as error:
        _print_pipeline_error(error)
        return 1
    return _report(result)


def _build_headless() -> int:
    ue_root = Path(os.environ.get("UE_ROOT") or DEFAULT_UE_ROOT)
    missing = _missing_headless_path(ue_root)
    if missing is not None:
        print(f"ERROR [master_material.headless_unavailable] missing {missing}", file=sys.stderr)
        print(
            f"Remediation: install UE 5.8 and set UE_ROOT to its engine root (UE_ROOT={ue_root}).",
            file=sys.stderr,
        )
        return EXIT_HEADLESS_UNAVAILABLE
    build = subprocess.run(
        [
            str(ue_root / BUILD_SCRIPT),
            "DogfoodEditor",
            "Mac",
            "Development",
            f"-Project={DOGFOOD_PROJECT}",
            "-WaitMutex",
            "-NoUBA",
        ],
        check=False,
    )
    if build.returncode != 0:
        print(
            f"ERROR [master_material.build_failed] Build.sh exited {build.returncode}",
            file=sys.stderr,
        )
        print(
            "Remediation: fix the build errors above. fixtures/Plugins must hold VibeUE "
            "(scripts/install-vibeue.sh).",
            file=sys.stderr,
        )
        return EXIT_HEADLESS_UNAVAILABLE
    with tempfile.TemporaryDirectory(prefix="m_nmg_orm_") as scratch:
        script = Path(scratch) / "build_master_material_headless.py"
        script.write_text(_MATERIAL_CODE, encoding="utf-8")
        log = Path(scratch) / "UnrealEditor-Cmd.log"
        # The log is a file, not a pipe. An engine helper (UnrealTraceServer) can outlive the editor
        # and keep an inherited pipe open, which would block a captured run until it closes.
        # -notrace stops the editor from forking that helper; the wait ends on the editor's exit.
        with log.open("w", encoding="utf-8", errors="replace") as sink:
            run = subprocess.run(
                [
                    str(ue_root / EDITOR_CMD),
                    str(DOGFOOD_PROJECT),
                    f"-ExecutePythonScript={script}",
                    f"-DisablePlugins={DISABLED_PLUGINS}",
                    "-EnablePlugins=PythonScriptPlugin",
                    "-notrace",
                    "-unattended",
                    "-nopause",
                    "-nosplash",
                    "-nullrhi",
                    "-stdout",
                    "-FullStdOutLogOutput",
                ],
                stdout=sink,
                stderr=subprocess.STDOUT,
                check=False,
            )
        output = log.read_text(encoding="utf-8", errors="replace")
    return _report_headless(run.returncode, output)


def main(argv: list[str] | None = None) -> int:
    """Build M_NmgORM through the MCP endpoint, or headlessly with --headless; return the code."""
    parser = argparse.ArgumentParser(description="Build /nmg-game-dev/Materials/M_NmgORM.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--url",
        default=None,
        help="Unreal MCP endpoint (default http://127.0.0.1:$UE_MCP_PORT/mcp)",
    )
    mode.add_argument(
        "--headless",
        action="store_true",
        help="Build DogfoodEditor and run the graph in a separate UnrealEditor-Cmd process",
    )
    args = parser.parse_args(argv)
    if args.headless:
        return _build_headless()
    return _build_via_mcp(args.url)


if __name__ == "__main__":
    sys.exit(main())
