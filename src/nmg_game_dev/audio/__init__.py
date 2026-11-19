"""Import generated audio into the Godot project (#155, #249, #252).

The official ElevenLabs MCP server generates sound effects and music; the developer runs it.
``import_audio`` takes the saved file, stores a 16-bit WAV under ``SourceArt/Audio/``, finishes the
game copy (trim, cut, loop crossfade, loudness match), and imports it headless into ``game/``: a
sound effect as an ``AudioStreamWAV`` and music, encoded with ffmpeg, as an
``AudioStreamOggVorbis``. ``refinish`` re-finishes stored sounds from ``SourceArt``.
``python -m nmg_game_dev.audio`` and the ``import_audio`` tool on the finalize server share these
functions. Nothing here calls ElevenLabs.
"""

from __future__ import annotations

from nmg_game_dev.audio.core import import_audio, refinish
from nmg_game_dev.audio.errors import AudioError
from nmg_game_dev.audio.godot_import import import_ogg, import_wav

__all__ = ["AudioError", "import_audio", "import_ogg", "import_wav", "refinish"]
