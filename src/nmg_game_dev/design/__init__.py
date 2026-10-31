"""Markdown design docs as a backlog that drives finalize and Unreal scaffolding (#112).

``docs/design/**/*.md`` holds one file per design entity.  ``sync`` parses those files into
``docs/design/backlog.json``.  ``scaffold`` creates the non-asset entries in Unreal.  The
``finalize`` tools read the backlog for a collection's category and asset class.

Modules: ``paths`` (project root and file locations), ``model`` (vocabulary and value types),
``parse`` (frontmatter validation), ``backlog`` (merge, dump, atomic write), ``scaffold`` (Unreal
work), and ``__main__`` (the ``sync`` and ``scaffold`` commands).
"""

from __future__ import annotations
