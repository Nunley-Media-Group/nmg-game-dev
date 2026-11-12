"""Parameters of the M_NmgORM master material that material variants may set (#148).

Pure Python on purpose: the contract core and the unit suite read this table under plain CPython,
and a unit test keeps scripts/unreal/build_master_material.py in step with it.
"""

from __future__ import annotations

from typing import Final

#: Parameter name to value kind. A ``vector`` takes [r, g, b] or [r, g, b, a]; alpha defaults to 1.
#: Tint multiplies the base colour and defaults to white in the master material.
MASTER_PARAMETERS: Final[dict[str, str]] = {"Tint": "vector"}
