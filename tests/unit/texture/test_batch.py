"""One worker process per backend batch, backends in sequence, never concurrent (#7 FR14, AC16,
AC17)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nmg_game_dev.texture.batch import Batch, ImageItem, run_backend_batches
from nmg_game_dev.texture.errors import TextureGenError
from nmg_game_dev.texture.registry import REGISTRY
from tests.texture_fakes import fake_spawn, read_log


def _batch(spec_id: str, root: Path, count: int, models: Path) -> Batch:
    spec = REGISTRY[spec_id]
    items = tuple(
        ImageItem(
            index=i,
            prompt="burlap weave, seamless",
            seed=100 + i,
            resolution=256,
            path=root / f"{spec_id}_{100 + i}_256.png",
        )
        for i in range(count)
    )
    return Batch(
        spec=spec,
        weights=models / f"{spec_id}-q4",
        items=items,
        batch_file=root / ".batch" / f"{spec_id}.json",
    )


def test_one_process_loads_once_and_writes_one_png_per_request(
    tmp_path: Path, worker: Path, log: Path, models: Path
) -> None:
    batch = _batch("flux2-klein-4b", tmp_path / "out", 3, models)
    results = run_backend_batches([batch], spawn=fake_spawn(worker, log))

    events = read_log(log)
    assert [e["event"] for e in events] == ["start", "exit"]
    assert all(e["backend"] == "flux2-klein-4b" for e in events)
    assert len(results["flux2-klein-4b"]) == 3
    assert all(item.path.exists() for item in batch.items)


def test_batch_file_names_the_entry_point_and_steps(
    tmp_path: Path, worker: Path, log: Path, models: Path
) -> None:
    batch = _batch("z-image-turbo", tmp_path / "out", 1, models)
    run_backend_batches([batch], spawn=fake_spawn(worker, log))
    written = json.loads(batch.batch_file.read_text())
    assert written["mflux_entry"] == "ZImage"
    assert written["steps"] == 9
    assert written["items"][0]["seed"] == 100


def test_backends_run_strictly_in_sequence(
    tmp_path: Path, worker: Path, log: Path, models: Path
) -> None:
    first = _batch("z-image-turbo", tmp_path / "out", 2, models)
    second = _batch("flux2-klein-4b", tmp_path / "out", 2, models)
    run_backend_batches([first, second], spawn=fake_spawn(worker, log))

    events = read_log(log)
    assert [(e["backend"], e["event"]) for e in events] == [
        ("z-image-turbo", "start"),
        ("z-image-turbo", "exit"),
        ("flux2-klein-4b", "start"),
        ("flux2-klein-4b", "exit"),
    ]
    assert events[1]["t"] <= events[2]["t"]


def test_non_zero_worker_exit_raises_worker_failed(
    tmp_path: Path, worker: Path, log: Path, models: Path
) -> None:
    batch = _batch("z-image-turbo", tmp_path / "out", 1, models)
    with pytest.raises(TextureGenError) as caught:
        run_backend_batches([batch], spawn=fake_spawn(worker, log, fail=True))
    assert caught.value.code == "texture.worker_failed"
    assert "simulated worker crash" in caught.value.remediation
