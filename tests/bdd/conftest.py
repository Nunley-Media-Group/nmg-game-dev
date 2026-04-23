"""BDD-specific pytest fixtures for pipeline scenarios.

Reuses the scripted MCP fakes defined in ``tests/conftest.py`` so BDD and
unit tests share a single implementation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.pipeline.stages._base import StageArtifact, StageContext
from tests.conftest import FakeBlenderMcp, FakeMeshyMcp, FakeUnrealMcp


class BddFakeBlenderOverBudget(FakeBlenderMcp):
    """Variant of the Blender fake that returns over-budget poly counts."""

    def run_script(self, script: str, **kwargs: object) -> dict[str, object]:
        result = super().run_script(script, **kwargs)
        # 999k polys vs the default 15k budget triggers AC4's quality halt.
        result["poly_count_mobile"] = 999_999
        result["texture_bytes_mobile"] = 512_000
        return result


@pytest.fixture()
def bdd_tmp_path(tmp_path: Path) -> Path:
    """A temporary directory for BDD scenario artifacts."""
    return tmp_path


@pytest.fixture()
def bdd_fake_blender(bdd_tmp_path: Path) -> FakeBlenderMcp:
    return FakeBlenderMcp(bdd_tmp_path)


@pytest.fixture()
def bdd_fake_blender_over_budget(bdd_tmp_path: Path) -> BddFakeBlenderOverBudget:
    return BddFakeBlenderOverBudget(bdd_tmp_path)


@pytest.fixture()
def bdd_fake_unreal(bdd_tmp_path: Path) -> FakeUnrealMcp:
    return FakeUnrealMcp(bdd_tmp_path)


@pytest.fixture()
def bdd_fake_meshy(bdd_tmp_path: Path) -> FakeMeshyMcp:
    return FakeMeshyMcp(bdd_tmp_path)


@pytest.fixture()
def bdd_cache_dir(bdd_tmp_path: Path) -> Path:
    d = bdd_tmp_path / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def fixture_texture_stage(ctx: StageContext) -> StageArtifact:
    """Test-seam texture stage that passes the upstream blob through unchanged."""
    upstream = ctx.upstream_artifact
    blob = upstream.blob_path if upstream is not None else ctx.cache_dir / "texture_out.fbx"
    if not blob.exists():
        blob.parent.mkdir(parents=True, exist_ok=True)
        blob.write_bytes(b"FAKE_TEXTURE")
    return StageArtifact(stage="texture", blob_path=blob, sidecar={"textured": True})
