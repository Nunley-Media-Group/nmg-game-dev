"""pytest-bdd bindings for texture_bake.feature: the texture stage at AC5 and AC6 (#67)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from pytest_bdd import given, parsers, scenario, then, when

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.prompt import Prompt, Tier
from nmg_game_dev.pipeline.stages._base import McpClients, StageArtifact, StageContext
from nmg_game_dev.pipeline.stages.texture import texture


class _BakeBlender:
    def __init__(self, result: dict[str, object]) -> None:
        self.result = result

    def run_script(self, script: str, **_kwargs: object) -> dict[str, object]:
        self.script = script
        return self.result

    def ping(self) -> bool:
        return True


@scenario(
    "texture_bake.feature",
    "The texture stage sidecar carries the texture paths, byte totals, proof, and summary",
)
def test_sidecar_carries_bake_fields() -> None:
    """AC5: the stage reports the same texture paths, byte totals, proof, and summary."""


@scenario(
    "texture_bake.feature",
    "A material the bake cannot represent raises PipelineError for the texture stage",
)
def test_unrepresentable_material_raises() -> None:
    """AC6: a bake error becomes a PipelineError with stage texture and a remediation."""


@given(
    parsers.parse(
        'a fixture prompt with category "{category}", name "{name}", '
        'tier "{tier}", description "{description}"'
    ),
    target_fixture="prompt",
)
def _prompt(category: str, name: str, tier: str, description: str) -> Prompt:
    return Prompt(category=category, name=name, tier=cast(Tier, tier), description=description)


@given(
    parsers.parse('the Blender MCP fake returns a successful bake for "{name}"'),
    target_fixture="blender",
)
def _successful_bake(name: str, tmp_path: Path) -> _BakeBlender:
    out = tmp_path / "work"
    return _BakeBlender(
        {
            "kind": "bake",
            "asset": name,
            "class": "standard_prop",
            "mode": "unique",
            "merged": False,
            "cache_hit": False,
            "manifest_path": str(out / "bake.json"),
            "desktop_dir": str(out / "Desktop"),
            "mobile_dir": str(out / "Mobile"),
            "desktop_textures": [str(out / "Desktop" / f"T_{name}_Body_BC.png")],
            "mobile_textures": [str(out / "Mobile" / f"T_{name}_Body_BC.png")],
            "texture_bytes_desktop": 4096,
            "texture_bytes_mobile": 1024,
            "materials": [{"name": f"M_{name}_Body", "source": ["Wood"]}],
            "proof": {"pre_bake": "p", "baked": "b", "mean_abs_diff": 0.012, "outlier_ratio": 0.0},
            "summary": f"Baked 1 material for {name} (standard_prop): Desktop 2048 px",
        }
    )


@given(
    parsers.parse(
        "the Blender MCP fake reports a texture.bake_failed error for a material with alpha 0.5"
    ),
    target_fixture="blender",
)
def _failed_bake() -> _BakeBlender:
    return _BakeBlender(
        {
            "error": {
                "code": "texture.bake_failed",
                "message": "Material 'Crate_Glass' has Alpha below 1 on 'Principled BSDF'.",
                "remediation": "Set Alpha to 1 and Transmission Weight to 0, then rerun the bake.",
                "target": "Crate_Glass",
                "reason": "transparency",
            }
        }
    )


@when("the texture stage runs", target_fixture="stage_state")
def _run_texture(prompt: Prompt, blender: _BakeBlender, tmp_path: Path) -> dict[str, Any]:
    clients = McpClients(blender=cast(Any, blender), unreal=cast(Any, None))
    ctx = StageContext(
        prompt=prompt,
        upstream_artifact=None,
        cache_dir=tmp_path / "cache",
        mcp_clients=clients,
    )
    state: dict[str, Any] = {}
    try:
        state["artifact"] = texture(ctx)
    except PipelineError as error:
        state["error"] = error
    return state


@then("the texture sidecar carries the Desktop and Mobile texture paths")
def _paths(stage_state: dict[str, Any]) -> None:
    artifact = stage_state["artifact"]
    assert isinstance(artifact, StageArtifact)
    sidecar = artifact.sidecar or {}
    assert sidecar["desktop_textures"]
    assert sidecar["mobile_textures"]


@then("the texture sidecar carries the texture byte totals, proof metrics, and summary")
def _totals(stage_state: dict[str, Any]) -> None:
    sidecar = stage_state["artifact"].sidecar or {}
    assert sidecar["texture_bytes_desktop"] == 4096
    assert sidecar["texture_bytes_mobile"] == 1024
    assert sidecar["proof"]["mean_abs_diff"] == 0.012
    assert str(sidecar["summary"]).startswith("Baked 1 material")


@then(parsers.parse('a PipelineError is raised with code "{code}" and stage "{stage}"'))
def _error(stage_state: dict[str, Any], code: str, stage: str) -> None:
    error = stage_state.get("error")
    assert isinstance(error, PipelineError)
    assert error.code == code
    assert error.stage == stage


@then("the PipelineError remediation names the transparency fix")
def _remediation(stage_state: dict[str, Any]) -> None:
    error = stage_state["error"]
    assert "Alpha" in error.remediation
