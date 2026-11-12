"""Import generated audio into Unreal (#155).

The official ElevenLabs MCP server generates sound effects and music; the developer runs it.
``import_audio`` takes the saved file, stores a 16-bit WAV under ``SourceArt/Audio/``, and imports
it through the Unreal MCP as a SoundWave. ``python -m nmg_game_dev.audio import`` and the
``import_audio`` tool on the finalize server share this function. Nothing here calls ElevenLabs.
"""

from __future__ import annotations

from nmg_game_dev.audio.core import import_audio
from nmg_game_dev.audio.errors import AudioError

__all__ = ["AudioError", "import_audio"]
