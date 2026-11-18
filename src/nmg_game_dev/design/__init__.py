"""Markdown design docs as a backlog that drives finalize and Godot scaffolding (#112, #249).

``docs/design/**/*.md`` holds one file per design entity.  ``sync`` parses those files into
``docs/design/backlog.json``.  ``scaffold`` writes the non-asset entries as Godot files.  The
``finalize`` tools read the backlog for a collection's category and asset class.

Modules: ``paths`` (project root and file locations), ``model`` (vocabulary and value types),
``parse`` (frontmatter validation), ``backlog`` (merge, dump, atomic write), ``scaffold`` (Godot
files), and ``__main__`` (the ``sync`` and ``scaffold`` commands).
"""

from __future__ import annotations
