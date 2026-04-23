"""Content-addressed artifact cache for the NMG pipeline.

Cache layout on disk::

    ${NMG_GAME_DEV_CACHE_DIR}/      # default: ~/.cache/nmg-game-dev
      by-key/
        {first-2-hex}/
          {full-sha256}/
            blob.<ext>              # primary produced artifact
            sidecar.json            # metadata + provenance
      tmp/                          # atomic-write staging area

Keys are SHA-256 hex digests of the canonical ``(stage, prompt_hash,
upstream_hash)`` tuple.  A missing or corrupt sidecar is treated as a cache
miss — no partial state is exposed to the caller.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path

from .stages._base import StageArtifact

logger = logging.getLogger(__name__)

_DEFAULT_CACHE_ROOT = Path.home() / ".cache" / "nmg-game-dev"
_ENV_VAR = "NMG_GAME_DEV_CACHE_DIR"


def default_cache_root() -> Path:
    """Return the cache root from ``NMG_GAME_DEV_CACHE_DIR`` or the default."""
    env_val = os.environ.get(_ENV_VAR)
    return Path(env_val) if env_val else _DEFAULT_CACHE_ROOT


def _resolve_root(root: Path | None) -> Path:
    return root if root is not None else default_cache_root()


class ArtifactCache:
    """Content-addressed, append-only artifact cache.

    Parameters:
        root: Optional explicit cache root.  When ``None``, resolves from the
            ``NMG_GAME_DEV_CACHE_DIR`` environment variable, falling back to
            ``~/.cache/nmg-game-dev``.
    """

    def __init__(self, root: Path | None = None) -> None:
        self._root = _resolve_root(root)

    @property
    def root(self) -> Path:
        """The resolved cache root directory."""
        return self._root

    def key(
        self,
        stage: str,
        prompt_hash: str,
        upstream_hash: str | None,
    ) -> str:
        """Return SHA-256 hex of the canonical ``(stage, prompt_hash, upstream_hash)`` tuple.

        ``upstream_hash`` is ``None`` for the first stage (generate) and the
        ``content_hash()`` of the previous stage's artifact for all subsequent
        stages.
        """
        canonical = json.dumps(
            {
                "stage": stage,
                "prompt_hash": prompt_hash,
                "upstream_hash": upstream_hash,
            },
            sort_keys=True,
        ).encode()
        return hashlib.sha256(canonical).hexdigest()

    def _entry_dir(self, key: str) -> Path:
        return self._root / "by-key" / key[:2] / key

    def get(self, key: str) -> StageArtifact | None:
        """Return the cached artifact, or ``None`` on a miss or corrupt entry.

        A corrupt or missing ``sidecar.json`` is logged as a warning and
        treated as a cache miss — the caller will re-run the stage.
        """
        entry = self._entry_dir(key)
        sidecar_path = entry / "sidecar.json"

        try:
            raw = sidecar_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.warning("Cache entry %s unreadable (%s) — treating as miss", key, exc)
            return None

        try:
            sidecar_data: dict[str, object] = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "Cache entry %s has corrupt sidecar.json (%s) — treating as miss",
                key,
                exc,
            )
            return None

        blob_filename = sidecar_data.get("blob_filename")
        stage_name = sidecar_data.get("stage")

        if not isinstance(blob_filename, str) or not isinstance(stage_name, str):
            logger.warning("Cache entry %s has malformed sidecar.json — treating as miss", key)
            return None

        blob_path = entry / blob_filename
        artifact_sidecar_raw = sidecar_data.get("artifact_sidecar")
        artifact_sidecar: dict[str, object] | None = None
        if isinstance(artifact_sidecar_raw, dict):
            artifact_sidecar = artifact_sidecar_raw

        return StageArtifact(
            stage=stage_name,
            blob_path=blob_path,
            sidecar=artifact_sidecar,
        )

    def put(self, key: str, artifact: StageArtifact) -> None:
        """Store blob + sidecar atomically via write-then-rename.

        Both the blob and the sidecar are staged in ``tmp/`` first and then
        ``os.replace``-d into the entry directory. The sidecar rename is the
        commit marker — a crash before the sidecar rename leaves no visible
        entry (``get()`` returns ``None``), and a crash between the blob and
        sidecar renames likewise leaves no readable entry.
        """
        entry = self._entry_dir(key)
        tmp_root = self._root / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        entry.mkdir(parents=True, exist_ok=True)

        suffix = artifact.blob_path.suffix or ".bin"
        blob_dest = entry / f"blob{suffix}"

        # Skip the copy when the blob is already in-place (cache-hit pass-through).
        # Comparing os.fspath first avoids a double resolve() syscall in the common case.
        already_in_place = os.fspath(artifact.blob_path) == os.fspath(blob_dest) or (
            artifact.blob_path.exists()
            and blob_dest.exists()
            and artifact.blob_path.samefile(blob_dest)
        )
        if not already_in_place:
            if artifact.blob_path.exists():
                # Stage the blob in tmp/, then atomic rename into the entry dir.
                # A crash before the rename leaves a tmp file that the next run
                # (or a cleaner) can remove; it never becomes a visible entry.
                with tempfile.NamedTemporaryFile(
                    suffix=suffix,
                    dir=tmp_root,
                    delete=False,
                ) as tmp_fh:
                    tmp_blob = Path(tmp_fh.name)
                shutil.copy2(artifact.blob_path, tmp_blob)
                os.replace(tmp_blob, blob_dest)
            else:
                # Sidecar-only artifact — create an empty sentinel in place.
                blob_dest.touch()

        sidecar_data: dict[str, object] = {
            "stage": artifact.stage,
            "blob_filename": blob_dest.name,
            "artifact_sidecar": artifact.sidecar,
        }
        sidecar_json = json.dumps(sidecar_data, indent=2, default=str)

        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".json",
            dir=tmp_root,
            delete=False,
            encoding="utf-8",
        ) as fh:
            fh.write(sidecar_json)
            tmp_path = Path(fh.name)

        os.replace(tmp_path, entry / "sidecar.json")
