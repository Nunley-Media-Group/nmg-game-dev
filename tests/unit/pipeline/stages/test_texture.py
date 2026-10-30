"""Unit tests for the texture stage, which bakes authored materials via the Blender MCP (#67)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from nmg_game_dev.pipeline.errors import PipelineError
from nmg_game_dev.pipeline.prompt import Prompt
from nmg_game_dev.pipeline.stages._base import McpClients, StageArtifact, StageContext
from nmg_game_dev.pipeline.stages.texture import texture


class ScriptedBlender:
    """Records the bake script and answers with a canned result, error, or exception."""

    def __init__(
        self,
        result: dict[str, object] | None = None,
        raises: Exception | None = None,
    ) -> None:
        self.result = result or {}
        self.raises = raises
        self.scripts: list[str] = []

    def run_script(self, script: str, **_kwargs: object) -> dict[str, object]:
        self.scripts.append(script)
        if self.raises is not None:
            raise self.raises
        return self.result

    def ping(self) -> bool:
        return True


def _ctx(prompt: Prompt, blender: ScriptedBlender, cache_dir: Path) -> StageContext:
    clients = McpClients(blender=cast(Any, blender), unreal=cast(Any, None))
    return StageContext(
        prompt=prompt,
        upstream_artifact=None,
        cache_dir=cache_dir,
        mcp_clients=clients,
    )


def _success(out: Path) -> dict[str, object]:
    desktop = out / "Desktop" / "T_Crate_Body_BC.png"
    mobile = out / "Mobile" / "T_Crate_Body_BC.png"
    return {
        "kind": "bake",
        "asset": "Crate",
        "class": "standard_prop",
        "mode": "unique",
        "merged": False,
        "cache_hit": False,
        "device": "CPU",
        "manifest_path": str(out / "bake.json"),
        "desktop_dir": str(out / "Desktop"),
        "mobile_dir": str(out / "Mobile"),
        "desktop_px": 2048,
        "mobile_px": 1024,
        "materials": [{"name": "M_Crate_Body", "source": ["Wood"]}],
        "desktop_textures": [str(desktop)],
        "mobile_textures": [str(mobile)],
        "texture_bytes_desktop": 4096,
        "texture_bytes_mobile": 1024,
        "proof": {"pre_bake": "p", "baked": "b", "mean_abs_diff": 0.012, "outlier_ratio": 0.0},
        "summary": "Baked 1 material for Crate (standard_prop): Desktop 2048 px, Mobile 1024 px",
    }


@pytest.fixture()
def prompt() -> Prompt:
    return Prompt(
        category="Props",
        name="Crate",
        tier="standard",
        description="wooden supply crate",
    )


class TestScript:
    def test_calls_run_for_mcp_with_collection_class_and_out_dir(
        self, prompt: Prompt, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "no-project"))
        blender = ScriptedBlender(result=_success(tmp_path))
        texture(_ctx(prompt, blender, tmp_path / "cache"))
        script = blender.scripts[0]
        assert "from nmg_game_dev_blender_addon.bake_core import run_for_mcp" in script
        assert "collection='Crate'" in script
        assert "asset_class='standard_prop'" in script
        assert str(tmp_path / "cache" / "work" / "texture" / "Props" / "Crate") in script
        assert "budgets_path=None" in script

    def test_hero_tier_maps_to_hero_prop(self, tmp_path: Path) -> None:
        hero = Prompt(category="Props", name="Vehicle", tier="hero", description="a cart")
        blender = ScriptedBlender(result=_success(tmp_path))
        texture(_ctx(hero, blender, tmp_path / "cache"))
        assert "asset_class='hero_prop'" in blender.scripts[0]

    def test_project_budget_file_is_passed_when_present(
        self, prompt: Prompt, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "nmg-budgets.json").write_text("{}", encoding="utf-8")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        blender = ScriptedBlender(result=_success(tmp_path))
        texture(_ctx(prompt, blender, tmp_path / "cache"))
        assert str(tmp_path / "nmg-budgets.json") in blender.scripts[0]


class TestSidecar:
    def test_success_returns_bake_manifest_with_sidecar_fields(
        self, prompt: Prompt, tmp_path: Path
    ) -> None:
        blender = ScriptedBlender(result=_success(tmp_path))
        artifact = texture(_ctx(prompt, blender, tmp_path / "cache"))
        assert isinstance(artifact, StageArtifact)
        assert artifact.stage == "texture"
        assert artifact.blob_path == tmp_path / "bake.json"
        sidecar = artifact.sidecar or {}
        assert sidecar["name"] == "Crate"
        assert sidecar["category"] == "Props"
        assert sidecar["class"] == "standard_prop"
        assert sidecar["desktop_textures"] == [str(tmp_path / "Desktop" / "T_Crate_Body_BC.png")]
        assert sidecar["mobile_textures"] == [str(tmp_path / "Mobile" / "T_Crate_Body_BC.png")]
        assert sidecar["texture_bytes_desktop"] == 4096
        assert sidecar["texture_bytes_mobile"] == 1024
        assert sidecar["proof"] == {
            "pre_bake": "p",
            "baked": "b",
            "mean_abs_diff": 0.012,
            "outlier_ratio": 0.0,
        }
        assert str(sidecar["summary"]).startswith("Baked 1 material for Crate")

    def test_cache_hit_passes_through(self, prompt: Prompt, tmp_path: Path) -> None:
        result = {**_success(tmp_path), "cache_hit": True}
        artifact = texture(_ctx(prompt, ScriptedBlender(result=result), tmp_path / "cache"))
        assert (artifact.sidecar or {})["cache_hit"] is True


class TestErrors:
    def test_bake_error_raises_pipeline_error_with_stage_texture(
        self, prompt: Prompt, tmp_path: Path
    ) -> None:
        error = {
            "code": "texture.bake_failed",
            "message": "Material 'Glass' has Alpha below 1 or linked on 'Principled BSDF'.",
            "remediation": "Set Alpha to 1 and Transmission Weight to 0, then rerun the bake.",
            "target": "Glass",
            "reason": "transparency",
        }
        blender = ScriptedBlender(result={"error": error})
        with pytest.raises(PipelineError) as info:
            texture(_ctx(prompt, blender, tmp_path / "cache"))
        assert info.value.code == "texture.bake_failed"
        assert info.value.stage == "texture"
        assert "Glass" in info.value.message
        assert "Alpha" in info.value.remediation

    def test_missing_manifest_path_is_invalid_response(
        self, prompt: Prompt, tmp_path: Path
    ) -> None:
        result = {k: v for k, v in _success(tmp_path).items() if k != "manifest_path"}
        with pytest.raises(PipelineError) as info:
            texture(_ctx(prompt, ScriptedBlender(result=result), tmp_path / "cache"))
        assert info.value.code == "mcp.blender.invalid_response"
        assert info.value.stage == "texture"

    def test_raised_client_exception_is_unreachable(self, prompt: Prompt, tmp_path: Path) -> None:
        blender = ScriptedBlender(raises=ConnectionError("socket closed"))
        with pytest.raises(PipelineError) as info:
            texture(_ctx(prompt, blender, tmp_path / "cache"))
        assert info.value.code == "mcp.blender.unreachable"
        assert info.value.stage == "texture"
