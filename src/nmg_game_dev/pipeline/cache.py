"""Content-addressed step cache and finalized-hash alias index for finalize (#69).

Cache layout on disk::

    ${NMG_GAME_DEV_CACHE_DIR}/          # default: ~/.cache/nmg-game-dev
      by-key/{first-2-hex}/{key}/
        entry.json                      # step, output_hash, outputs, blob names
        files/<blob name>               # file or directory copy of each step output
      runs/{asset_hash}.json            # alias index: step keys, result_blend, content_paths
      tmp/                              # atomic-write staging
      jobs/                             # job directories (owned by jobs.py)

A step key is ``key(step, input_hash, settings_hash)``.  ``input_hash`` is the asset hash for the
first step and the previous step's output hash for the rest, so a change to any mesh, material,
or image misses from the first affected step onward.  Job-directory paths inside stored outputs
are rewritten to ``$JOB`` so a restored entry points at the current job.

A missing, corrupt, or incomplete entry is a cache miss, never a partial hit.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "nmg-game-dev"
_ENV_VAR = "NMG_GAME_DEV_CACHE_DIR"
_JOB_TOKEN = "$JOB"


def default_cache_root() -> Path:
    """Return the cache root from ``NMG_GAME_DEV_CACHE_DIR`` or the default."""
    env_val = os.environ.get(_ENV_VAR)
    return Path(env_val) if env_val else _DEFAULT_CACHE_ROOT


@dataclass(frozen=True)
class CacheEntry:
    """A complete cache entry.  Blobs are restored with ``ArtifactCache.restore``.

    Attributes:
        step: Step name that produced the entry.
        output_hash: Hash over the outputs and blobs; the next step's input hash.
        outputs: The step outputs, with ``$JOB`` resolved to the current job directory.
        blob_names: Names of the stored blobs, each restorable by name.
    """

    step: str
    output_hash: str
    outputs: dict[str, Any]
    blob_names: tuple[str, ...]


def _relocate(value: Any, job_dir: Path, *, to_token: bool) -> Any:
    """Swap the job directory prefix to or from ``$JOB`` in every string inside ``value``."""
    job = str(job_dir)
    if isinstance(value, str):
        return value.replace(job, _JOB_TOKEN) if to_token else value.replace(_JOB_TOKEN, job)
    if isinstance(value, dict):
        return {k: _relocate(v, job_dir, to_token=to_token) for k, v in value.items()}
    if isinstance(value, list):
        return [_relocate(v, job_dir, to_token=to_token) for v in value]
    return value


def _write_text_atomic(path: Path, text: str, tmp_root: Path) -> None:
    """Write ``text`` to a staging file and rename it into place."""
    tmp_root.mkdir(parents=True, exist_ok=True)
    staged = tmp_root / f"{uuid.uuid4().hex}.tmp"
    staged.write_text(text, encoding="utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    os.replace(staged, path)


class ArtifactCache:
    """Content-addressed store for finalize step outputs and the alias index.

    Parameters:
        root: Optional explicit cache root.  When ``None``, resolves from
            ``NMG_GAME_DEV_CACHE_DIR``, falling back to ``~/.cache/nmg-game-dev``.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = root if root is not None else default_cache_root()

    @property
    def root(self) -> Path:
        """The resolved cache root directory."""
        return self._root

    def key(self, step: str, input_hash: str, settings_hash: str) -> str:
        """Return the SHA-256 hex of the canonical ``(step, input_hash, settings_hash)`` tuple."""
        canonical = json.dumps(
            {"step": step, "input_hash": input_hash, "settings_hash": settings_hash},
            sort_keys=True,
        ).encode()
        return hashlib.sha256(canonical).hexdigest()

    def _entry_dir(self, key: str) -> Path:
        return self._root / "by-key" / key[:2] / key

    def _tmp_root(self) -> Path:
        return self._root / "tmp"

    def get(self, key: str, *, job_dir: Path) -> CacheEntry | None:
        """Return the complete entry for ``key``, or ``None`` when missing, corrupt, or partial."""
        meta_path = self._entry_dir(key) / "entry.json"
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Cache entry %s unreadable (%s) — treating as miss", key, exc)
            return None

        if not _is_valid_entry(data):
            logger.warning("Cache entry %s is malformed — treating as miss", key)
            return None

        blob_names: list[str] = data["blobs"]
        if not all((self._entry_dir(key) / "files" / name).exists() for name in blob_names):
            logger.warning("Cache entry %s is missing blobs — treating as miss", key)
            return None

        outputs = _relocate(data["outputs"], job_dir, to_token=False)
        return CacheEntry(
            step=data["step"],
            output_hash=data["output_hash"],
            outputs=outputs,
            blob_names=tuple(blob_names),
        )

    def put(
        self,
        key: str,
        *,
        step: str,
        output_hash: str,
        outputs: Mapping[str, Any],
        blobs: Mapping[str, Path],
        job_dir: Path,
    ) -> None:
        """Store outputs and blobs atomically.  The ``entry.json`` rename is the commit point."""
        tmp_root = self._tmp_root()
        tmp_root.mkdir(parents=True, exist_ok=True)
        staged = tmp_root / uuid.uuid4().hex
        files = staged / "files"
        files.mkdir(parents=True)

        blob_names: list[str] = []
        for name, source in blobs.items():
            target = files / name
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copy2(source, target)
            blob_names.append(name)

        meta = {
            "step": step,
            "output_hash": output_hash,
            "outputs": _relocate(dict(outputs), job_dir, to_token=True),
            "blobs": blob_names,
        }
        (staged / "entry.json").write_text(
            json.dumps(meta, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )

        entry = self._entry_dir(key)
        entry.parent.mkdir(parents=True, exist_ok=True)
        if entry.exists():
            shutil.rmtree(entry)
        os.replace(staged, entry)

    def restore(self, key: str, name: str, dest: Path) -> None:
        """Copy the stored blob ``name`` of entry ``key`` to ``dest``, replacing what is there."""
        source = self._entry_dir(key) / "files" / name
        if dest.is_dir():
            shutil.rmtree(dest)
        elif dest.exists():
            dest.unlink()
        dest.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, dest)
        else:
            shutil.copy2(source, dest)

    def alias(self, asset_hash: str, *, job_dir: Path) -> dict[str, Any] | None:
        """Return the alias record for ``asset_hash`` with ``$JOB`` resolved, or ``None``."""
        path = self._root / "runs" / f"{asset_hash}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("Alias %s unreadable (%s) — treating as miss", asset_hash, exc)
            return None
        if not isinstance(data, dict) or not isinstance(data.get("steps"), dict):
            logger.warning("Alias %s is malformed — treating as miss", asset_hash)
            return None
        result: dict[str, Any] = _relocate(data, job_dir, to_token=False)
        return result

    def put_alias(self, asset_hash: str, record: Mapping[str, Any], *, job_dir: Path) -> None:
        """Write the alias record for ``asset_hash`` atomically."""
        path = self._root / "runs" / f"{asset_hash}.json"
        text = json.dumps(_relocate(dict(record), job_dir, to_token=True), indent=2, sort_keys=True)
        _write_text_atomic(path, text + "\n", self._tmp_root())


def _is_valid_entry(data: object) -> bool:
    if not isinstance(data, dict):
        return False
    blobs = data.get("blobs")
    return (
        isinstance(data.get("step"), str)
        and isinstance(data.get("output_hash"), str)
        and isinstance(data.get("outputs"), dict)
        and isinstance(blobs, list)
        and all(isinstance(name, str) for name in blobs)
    )
