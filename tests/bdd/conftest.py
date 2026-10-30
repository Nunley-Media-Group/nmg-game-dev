"""BDD fixtures for the pipeline scenarios.

The finalize scenarios run the real orchestrator, cache, and job layer with the in-process fakes in
``tests/finalize_fakes.py``.  Shared fixtures for them live in ``test_finalize_bdd.py``.
"""

from __future__ import annotations
