"""Where Meshy writes its files under the project root (#98 Data / Storage).

``SourceArt/Meshy/<Name>/<Name>.glb`` holds a generated model, ``SourceArt/Textures/Meshy/<Name>/``
holds retextured maps, and ``SourceArt/Meshy/.jobs/<job_id>/`` holds one job's files.
"""

from __future__ import annotations

from pathlib import Path


def model_dir(root: Path, name: str) -> Path:
    return root / "SourceArt" / "Meshy" / name


def glb_path(root: Path, name: str) -> Path:
    return model_dir(root, name) / f"{name}.glb"


def maps_dir(root: Path, name: str) -> Path:
    return root / "SourceArt" / "Textures" / "Meshy" / name


def jobs_root(root: Path) -> Path:
    return root / "SourceArt" / "Meshy" / ".jobs"
