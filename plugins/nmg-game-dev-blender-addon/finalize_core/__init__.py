"""finalize_core: the Blender-side finalize steps and session load-back (#69).

content_hash keys the cache on the asset's content. run_step runs one step and returns its
envelope. load_back replaces the open session's asset with a finalized result. The host reaches
these through scripts/blender/finalize_entry.py (headless steps) and
scripts/blender/finalize_session.py (the live session).
"""

from __future__ import annotations

from .hashing import content_hash
from .load_back import LOAD_BACK_CODE, LoadBackError, load_back
from .steps import STEPS, run_step

__all__ = [
    "LOAD_BACK_CODE",
    "STEPS",
    "LoadBackError",
    "content_hash",
    "load_back",
    "run_step",
]
