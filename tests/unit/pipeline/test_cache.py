"""Unit tests for ArtifactCache (T016)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nmg_game_dev.pipeline.cache import _DEFAULT_CACHE_ROOT, _ENV_VAR, ArtifactCache
from nmg_game_dev.pipeline.stages._base import StageArtifact


@pytest.fixture()
def cache(tmp_path: Path) -> ArtifactCache:
    return ArtifactCache(root=tmp_path / "cache")


@pytest.fixture()
def sample_artifact(tmp_path: Path) -> StageArtifact:
    blob = tmp_path / "mesh.fbx"
    blob.write_bytes(b"FAKE_MESH_DATA")
    return StageArtifact(
        stage="generate",
        blob_path=blob,
        sidecar={"source": "blender", "name": "TestCrate"},
    )


class TestCacheKey:
    def test_same_inputs_same_key(self, cache: ArtifactCache) -> None:
        k1 = cache.key("generate", "abc123", None)
        k2 = cache.key("generate", "abc123", None)
        assert k1 == k2

    def test_different_stage_different_key(self, cache: ArtifactCache) -> None:
        k1 = cache.key("generate", "abc123", None)
        k2 = cache.key("texture", "abc123", None)
        assert k1 != k2

    def test_different_prompt_hash_different_key(self, cache: ArtifactCache) -> None:
        k1 = cache.key("generate", "abc", None)
        k2 = cache.key("generate", "xyz", None)
        assert k1 != k2

    def test_different_upstream_hash_different_key(self, cache: ArtifactCache) -> None:
        k1 = cache.key("texture", "abc", "upstream1")
        k2 = cache.key("texture", "abc", "upstream2")
        assert k1 != k2

    def test_none_vs_string_upstream_different_key(self, cache: ArtifactCache) -> None:
        k1 = cache.key("generate", "abc", None)
        k2 = cache.key("generate", "abc", "something")
        assert k1 != k2

    def test_key_is_64_char_hex(self, cache: ArtifactCache) -> None:
        k = cache.key("generate", "abc", None)
        assert len(k) == 64
        int(k, 16)


class TestCacheMiss:
    def test_get_returns_none_on_miss(self, cache: ArtifactCache) -> None:
        assert cache.get("nonexistent" * 4) is None

    def test_get_returns_none_for_nonexistent_key(self, cache: ArtifactCache) -> None:
        result = cache.get("a" * 64)
        assert result is None


class TestCachePutGet:
    def test_put_then_get_returns_artifact(
        self, cache: ArtifactCache, sample_artifact: StageArtifact
    ) -> None:
        key = cache.key("generate", "abc", None)
        cache.put(key, sample_artifact)
        result = cache.get(key)
        assert result is not None
        assert result.stage == "generate"
        assert result.sidecar == {"source": "blender", "name": "TestCrate"}

    def test_put_copies_blob_to_cache_dir(
        self, cache: ArtifactCache, sample_artifact: StageArtifact
    ) -> None:
        key = cache.key("generate", "abc", None)
        cache.put(key, sample_artifact)
        entry_dir = cache._entry_dir(key)
        assert any(entry_dir.iterdir()), "Entry directory should contain files"

    def test_sidecar_json_written(
        self, cache: ArtifactCache, sample_artifact: StageArtifact
    ) -> None:
        key = cache.key("generate", "abc", None)
        cache.put(key, sample_artifact)
        entry_dir = cache._entry_dir(key)
        sidecar_path = entry_dir / "sidecar.json"
        assert sidecar_path.exists()
        data = json.loads(sidecar_path.read_text())
        assert data["stage"] == "generate"

    def test_artifact_with_none_sidecar(self, cache: ArtifactCache, tmp_path: Path) -> None:
        blob = tmp_path / "mesh.fbx"
        blob.write_bytes(b"DATA")
        artifact = StageArtifact(stage="cleanup", blob_path=blob, sidecar=None)
        key = cache.key("cleanup", "abc", "upstream")
        cache.put(key, artifact)
        result = cache.get(key)
        assert result is not None
        assert result.sidecar is None


class TestCorruptedEntry:
    def test_corrupted_sidecar_treated_as_miss(
        self, cache: ArtifactCache, sample_artifact: StageArtifact
    ) -> None:
        key = cache.key("generate", "abc", None)
        cache.put(key, sample_artifact)
        # Corrupt the sidecar.
        entry_dir = cache._entry_dir(key)
        (entry_dir / "sidecar.json").write_text("NOT JSON {{{")
        result = cache.get(key)
        assert result is None

    def test_empty_sidecar_treated_as_miss(
        self, cache: ArtifactCache, sample_artifact: StageArtifact
    ) -> None:
        key = cache.key("generate", "abc", None)
        cache.put(key, sample_artifact)
        entry_dir = cache._entry_dir(key)
        (entry_dir / "sidecar.json").write_text("")
        result = cache.get(key)
        assert result is None


class TestEnvVarDefault:
    def test_env_var_sets_root(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        custom = tmp_path / "custom_cache"
        monkeypatch.setenv(_ENV_VAR, str(custom))
        cache = ArtifactCache()
        assert cache.root == custom

    def test_explicit_root_overrides_env(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(_ENV_VAR, "/should/be/ignored")
        cache = ArtifactCache(root=tmp_path / "explicit")
        assert cache.root == tmp_path / "explicit"

    def test_no_env_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(_ENV_VAR, raising=False)
        cache = ArtifactCache()
        assert cache.root == _DEFAULT_CACHE_ROOT
