#!/usr/bin/env python3
"""Build /nmg-game-dev/Materials/M_NmgORM in the running UE 5.8 editor (#69, FR5).

    uv run --group dev python scripts/unreal/build_master_material.py [--url URL]

The graph has three texture parameters. ``BaseColor`` (Color) feeds Base Color, ``Normal``
(Normal) feeds Normal, and ``ORM`` (Masks) feeds Ambient Occlusion from R, Roughness from G, and
Metallic from B. The nmg-game-dev plugin mounts at /nmg-game-dev/, so the asset saves to
plugins/nmg-game-dev-ue-plugin/Content/Materials/M_NmgORM.uasset.

Running it again rebuilds the graph of an existing M_NmgORM in place, so material instances
keep their parent. The UE work goes through UnrealMcpClient, and the result is read from the
NMG_RESULT line the UE code prints.

Exit codes: 0 built and saved. 1 UE reported an error. 2 the Unreal MCP endpoint is unreachable.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Final

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


def _sampler(material, parameter, y, sampler_type):
    node = unreal.MaterialEditingLibrary.create_material_expression(
        material, unreal.MaterialExpressionTextureSampleParameter2D, -700, y
    )
    node.set_editor_property("parameter_name", parameter)
    node.set_editor_property("sampler_type", sampler_type)
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


def _build(material):
    mel = unreal.MaterialEditingLibrary
    base = _sampler(material, "BaseColor", -200, unreal.MaterialSamplerType.SAMPLERTYPE_COLOR)
    mel.connect_material_property(base, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    normal = _sampler(material, "Normal", 100, unreal.MaterialSamplerType.SAMPLERTYPE_NORMAL)
    mel.connect_material_property(normal, "RGB", unreal.MaterialProperty.MP_NORMAL)
    orm = _sampler(material, "ORM", 400, unreal.MaterialSamplerType.SAMPLERTYPE_MASKS)
    mel.connect_material_property(orm, "R", unreal.MaterialProperty.MP_AMBIENT_OCCLUSION)
    mel.connect_material_property(orm, "G", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(orm, "B", unreal.MaterialProperty.MP_METALLIC)
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


def main(argv: list[str] | None = None) -> int:
    """Build M_NmgORM through the Unreal MCP endpoint and return the process exit code."""
    parser = argparse.ArgumentParser(description="Build /nmg-game-dev/Materials/M_NmgORM.")
    parser.add_argument(
        "--url",
        default=None,
        help="Unreal MCP endpoint (default http://127.0.0.1:$UE_MCP_PORT/mcp)",
    )
    args = parser.parse_args(argv)
    try:
        with UnrealMcpClient(args.url) as client:
            output = client.execute_python_code(_MATERIAL_CODE)
        result = parse_nmg_result(output)
    except PipelineError as error:
        print(f"ERROR [{error.code}] {error.message}", file=sys.stderr)
        print(f"Remediation: {error.remediation}", file=sys.stderr)
        return 2 if error.code == "mcp.unreal.unreachable" else 1
    if result.get("ok") is not True:
        print(
            f"ERROR [import_ue.failed] {result.get('error') or 'UE reported no error text'}",
            file=sys.stderr,
        )
        return 1
    print(f"Built {result['asset']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
