# File: tests/bdd/features/audio_import.feature
# Generated from: the #155 requirements (ElevenLabs audio import)
# Updated for: the #249 requirements (AC5, audio imports into Godot)
Feature: Import generated audio into Godot

  @SCN001
  Scenario: A WAV sound effect is stored and imported
    Given a saved WAV file and an installed Godot
    When import_audio runs with name "DoorCreak" and kind "sfx"
    Then SourceArt/Audio/SFX/DoorCreak.wav holds the file
    And res://assets/Audio/DoorCreak.wav is imported as an AudioStreamWAV with looping off

  @SCN002
  Scenario Outline: Compressed audio is converted to WAV
    Given a saved <format> file
    When it is imported with name "ForestTheme" and kind "music"
    Then SourceArt/Audio/Music/ForestTheme.wav is a 16-bit PCM WAV at the source rate and channels
    And the result reports converted true

    Examples:
      | format |
      | MP3    |
      | OGG    |
      | FLAC   |

  @SCN003
  Scenario: Looping is set on request
    Given a saved audio file
    When it is imported with loop true
    Then the AudioStreamWAV loops forward

  @SCN009
  Scenario: Music imports as a looping AudioStreamOggVorbis
    Given a saved WAV file
    When it is imported with name "Theme" and kind "music" and loop true
    Then SourceArt/Audio/Music/Theme.wav and game/assets/Audio/Theme.ogg exist
    And res://assets/Audio/Theme.ogg is imported as an AudioStreamOggVorbis with loop enabled

  @SCN010
  Scenario: Music import fails without ffmpeg
    Given a saved WAV file and no ffmpeg
    When it is imported with name "Theme" and kind "music"
    Then it fails with audio.ffmpeg_not_found and a remediation line
    And game/assets/Audio/Theme.ogg does not exist

  @SCN004
  Scenario: A missing Godot keeps the files
    Given a saved audio file and no Godot
    When it is imported
    Then the result has imported_to_godot false and warning godot.not_found
    And the WAV stays under SourceArt/Audio

  @SCN005
  Scenario: Invalid requests write nothing
    Given an import request with a bad name, kind, path, format, or an existing target
    When it is submitted
    Then it fails with audio.invalid_request, audio.unsupported_format, or audio.asset_exists
    And nothing is written and Godot is not run

  @SCN006
  Scenario: Undecodable audio fails cleanly
    Given a corrupt MP3 file
    When it is imported
    Then it fails with audio.decode_failed and leaves no file behind

  @SCN007
  Scenario: The CLI and the finalize MCP tool share one implementation
    Given the same request and fakes
    When it runs through the CLI and through the import_audio tool
    Then both return the same result JSON

  @SCN008
  Scenario: No ElevenLabs integration ships in the plugin config
    Given the repository
    When the guards run
    Then .mcp.json has no elevenlabs entry and no ELEVENLABS text
