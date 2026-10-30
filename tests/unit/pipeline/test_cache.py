"""Unit tests for the finalize content-addressed cache and alias index (AC4, #69)."""

from __future__ import annotations

from pathlib import Path

import pytest

from nmg_game_dev.pipeline.cache import ArtifactCache, default_cache_root


@pytest.fixture()
def cache(tmp_path: Path) -> ArtifactCache:
    return ArtifactCache(tmp_path / "cache")


def _put_blend(cache: ArtifactCache, key: str, job_dir: Path, payload: bytes) -> None:
    blend = job_dir / "bake.blend"
    blend.parent.mkdir(parents=True, exist_ok=True)
    blend.write_bytes(payload)
    cache.put(
        key,
        step="bake",
        output_hash="out-hash",
        outputs={"blend": str(blend)},
        blobs={"bake.blend": blend},
        job_dir=job_dir,
    )


class TestKey:
    def test_same_inputs_give_same_key(self, cache: ArtifactCache) -> None:
        assert cache.key("bake", "in", "set") == cache.key("bake", "in", "set")

    @pytest.mark.parametrize(
        "other",
        [("validate", "in", "set"), ("bake", "other", "set"), ("bake", "in", "other")],
    )
    def test_any_component_changes_the_key(
        self, cache: ArtifactCache, other: tuple[str, str, str]
    ) -> None:
        assert cache.key("bake", "in", "set") != cache.key(*other)

    def test_key_is_sha256_hex(self, cache: ArtifactCache) -> None:
        key = cache.key("bake", "in", "set")
        assert len(key) == 64
        assert all(char in "0123456789abcdef" for char in key)


class TestEntries:
    def test_miss_when_no_entry(self, cache: ArtifactCache, tmp_path: Path) -> None:
        assert cache.get("0" * 64, job_dir=tmp_path / "job") is None

    def test_put_then_get_round_trips_outputs_and_hash(
        self, cache: ArtifactCache, tmp_path: Path
    ) -> None:
        job = tmp_path / "job"
        _put_blend(cache, "k" * 64, job, b"baked")
        entry = cache.get("k" * 64, job_dir=job)
        assert entry is not None
        assert entry.step == "bake"
        assert entry.output_hash == "out-hash"
        assert entry.blob_names == ("bake.blend",)

    def test_job_directory_is_relocated_on_restore(
        self, cache: ArtifactCache, tmp_path: Path
    ) -> None:
        first = tmp_path / "job-a"
        _put_blend(cache, "k" * 64, first, b"baked")
        second = tmp_path / "job-b"
        entry = cache.get("k" * 64, job_dir=second)
        assert entry is not None
        assert entry.outputs["blend"] == str(second / "bake.blend")

    def test_restore_copies_the_blob_to_the_target(
        self, cache: ArtifactCache, tmp_path: Path
    ) -> None:
        job = tmp_path / "job"
        _put_blend(cache, "k" * 64, job, b"baked")
        target = tmp_path / "elsewhere" / "bake.blend"
        cache.restore("k" * 64, "bake.blend", target)
        assert target.read_bytes() == b"baked"

    def test_directory_blob_round_trips(self, cache: ArtifactCache, tmp_path: Path) -> None:
        folder = tmp_path / "export" / "Desktop"
        (folder / "textures").mkdir(parents=True)
        (folder / "SM_Crate.fbx").write_bytes(b"fbx")
        (folder / "textures" / "T.png").write_bytes(b"png")
        job = tmp_path / "job"
        cache.put(
            "d" * 64,
            step="export",
            output_hash="h",
            outputs={"variants": {"Desktop": {"dir": str(folder)}}},
            blobs={"Desktop": folder},
            job_dir=job,
        )
        restored = tmp_path / "restored"
        cache.restore("d" * 64, "Desktop", restored)
        assert (restored / "SM_Crate.fbx").read_bytes() == b"fbx"
        assert (restored / "textures" / "T.png").read_bytes() == b"png"

    def test_corrupt_meta_is_a_miss(self, cache: ArtifactCache, tmp_path: Path) -> None:
        job = tmp_path / "job"
        _put_blend(cache, "k" * 64, job, b"baked")
        entry_dir = cache.root / "by-key" / "kk" / ("k" * 64)
        (entry_dir / "entry.json").write_text("{not json", encoding="utf-8")
        assert cache.get("k" * 64, job_dir=job) is None

    def test_malformed_meta_is_a_miss(self, cache: ArtifactCache, tmp_path: Path) -> None:
        job = tmp_path / "job"
        _put_blend(cache, "k" * 64, job, b"baked")
        entry_dir = cache.root / "by-key" / "kk" / ("k" * 64)
        (entry_dir / "entry.json").write_text('{"step": 3}', encoding="utf-8")
        assert cache.get("k" * 64, job_dir=job) is None

    def test_missing_blob_is_a_miss_not_a_partial_hit(
        self, cache: ArtifactCache, tmp_path: Path
    ) -> None:
        job = tmp_path / "job"
        _put_blend(cache, "k" * 64, job, b"baked")
        (cache.root / "by-key" / "kk" / ("k" * 64) / "files" / "bake.blend").unlink()
        assert cache.get("k" * 64, job_dir=job) is None

    def test_put_replaces_an_existing_entry(self, cache: ArtifactCache, tmp_path: Path) -> None:
        job = tmp_path / "job"
        _put_blend(cache, "k" * 64, job, b"first")
        _put_blend(cache, "k" * 64, job, b"second")
        cache.restore("k" * 64, "bake.blend", tmp_path / "out.blend")
        assert (tmp_path / "out.blend").read_bytes() == b"second"


class TestAliasIndex:
    def test_missing_alias_is_none(self, cache: ArtifactCache, tmp_path: Path) -> None:
        assert cache.alias("a" * 64, job_dir=tmp_path / "job") is None

    def test_alias_round_trips_and_relocates_result_blend(
        self, cache: ArtifactCache, tmp_path: Path
    ) -> None:
        job = tmp_path / "job"
        cache.put_alias(
            "a" * 64,
            {"steps": {"validate": "k1"}, "result_blend": str(job / "variants.blend")},
            job_dir=job,
        )
        other = tmp_path / "job-2"
        record = cache.alias("a" * 64, job_dir=other)
        assert record is not None
        assert record["steps"] == {"validate": "k1"}
        assert record["result_blend"] == str(other / "variants.blend")

    def test_malformed_alias_is_none(self, cache: ArtifactCache, tmp_path: Path) -> None:
        runs = cache.root / "runs"
        runs.mkdir(parents=True)
        (runs / f"{'a' * 64}.json").write_text('{"steps": []}', encoding="utf-8")
        assert cache.alias("a" * 64, job_dir=tmp_path / "job") is None


def test_default_root_honours_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("NMG_GAME_DEV_CACHE_DIR", str(tmp_path / "custom"))
    assert default_cache_root() == tmp_path / "custom"
    assert ArtifactCache().root == tmp_path / "custom"
