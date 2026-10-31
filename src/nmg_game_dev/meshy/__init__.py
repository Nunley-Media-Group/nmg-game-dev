"""Optional Meshy model generation and retexturing (#98).

Meshy is opt-in: it runs only when a key is set in ``MESHY_API_KEY`` or the project's git-ignored
``.env``. Nothing in ``pipeline/`` or ``finalize/`` depends on this package. The ``meshy`` MCP
server and ``python -m nmg_game_dev.meshy`` share the functions in ``jobs``.
"""

from __future__ import annotations
