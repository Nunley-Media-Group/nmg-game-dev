# File: tests/bdd/features/godot_engine.feature
# Generated from: the issue #249 requirements (AC1-AC10, AC14; SCN015 is AC5)
Feature: Godot 4 is the engine target

  @SCN001
  Scenario: Finalize lands both variants in Godot
    Given a consumer with game/project.godot and a collection "Crate" in category "Props" that passes validation
    When finalize runs every step
    Then game/assets/Props/Crate/Desktop and game/assets/Props/Crate/Mobile each hold Crate.glb, its textures, and nmg-asset.json
    And the headless import ran and the probe's mesh names, triangle counts, material slots, and bounds match the export
    And the steps ran in the order validate, bake, variants, export, export_anims, reimport, import_godot, import_anims

  @SCN002
  Scenario Outline: Godot import failures stop finalize
    Given finalize reaches import_godot with <condition>
    When the step runs
    Then finalize fails with "<code>" and a remediation line
    And no later step runs

    Examples:
      | condition                       | code                       |
      | no Godot binary on the host     | godot.not_found            |
      | an ERROR line from the import   | import_godot.import_failed |
      | a probe triangle count mismatch | import_godot.mismatch      |

  @SCN003
  Scenario: Animation clips import per clip
    Given a rigged asset with clips "Idle", "Walk", and "Run" already finalized
    When the "Walk" clip changes and finalize runs again
    Then only A_<Name>_Walk.glb is re-exported and re-imported as an animation library

  @SCN004
  Scenario: Terrain becomes chunked meshes with collision
    Given an authored terrain asset with a heightfield
    When finalize runs
    Then the variant folder holds chunk .glb files and a .tscn instancing every chunk with HeightMapShape3D collision from the same heightfield
    And a probe height range off by more than 0.05 m fails with "import_godot.terrain_height_mismatch"

  @SCN005
  Scenario: Music imports into Godot as a looping AudioStreamOggVorbis
    Given a music file "Theme.wav" passed to import_audio with loop enabled
    When the import runs
    Then SourceArt/Audio/Music/Theme.wav and game/assets/Audio/Theme.ogg exist
    And Godot imported it as an AudioStreamOggVorbis with loop enabled

  @SCN015
  Scenario: Music import fails without ffmpeg
    Given ffmpeg is not on PATH and FFMPEG_BIN is unset
    And a music file "Theme.wav" passed to import_audio
    When the import runs
    Then it fails with audio.ffmpeg_not_found and a remediation line
    And game/assets/Audio/Theme.ogg does not exist

  @SCN006
  Scenario: Material variants are listed without an editor
    Given an asset finalized with material variants "Rusty" and "Clean"
    When list_material_variants runs
    Then it returns each variant's name and material slot for the Desktop and Mobile folders
    And no Godot process was started

  @SCN007
  Scenario: Design scaffolding writes Godot files
    Given a backlog with region "OldTown", mission "FirstLight", and system "Stealth"
    When /design scaffolds
    Then game/levels/OldTown/OldTown.tscn, game/missions/FirstLight.tres, and game/systems/Stealth/stealth.gd exist with the specified contents
    And a second scaffold leaves every file unchanged

  @SCN008
  Scenario: The runtime add-on routes variants
    Given the nmg_game_dev add-on
    When the add-on's headless test runner resolves "res://assets/Props/Crate/Crate.glb" for desktop, for mobile, and a malformed path
    Then it returns the Desktop path, the Mobile path, and the unchanged path with a warning
    And it prints "N passed, M failed" and exits non-zero on any failure

  @SCN009
  Scenario: Ship exports every target through Godot
    Given a consumer Godot project and the environment for target "all"
    When /ship all runs
    Then the script check, the project tests, and the mobile budget gate run before any export
    And release/ holds the macOS .app (signed and notarized), the .ipa, the .aab, the .exe, and the web folder, each with SHA-256 in RELEASE-NOTES.md
    And no WINDOWS_BUILD_* variable was required
    And with --dry-run every command is printed with a "DRY-RUN:" prefix

  @SCN010
  Scenario: Onboarding sets up a Godot consumer
    Given a game project with no nmg-game-dev setup
    When /onboard-consumer runs twice
    Then game/project.godot, the add-on, and game/export_presets.cfg with variant filters exist after the first run
    And only the Blender SessionStart hook is installed
    And the second run changes no file

  @SCN014
  Scenario: The retired engine is gone from nmg-game-dev
    Given this repository's tracked files
    When the retired-engine guard runs
    Then no file outside specs/, CHANGELOG.md, and the exempt conversion files references the retired engine
    And steering/manifest.json registers gate-godot-headless and not gate-ue-compile
