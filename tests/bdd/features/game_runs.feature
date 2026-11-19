# File: tests/bdd/features/game_runs.feature
# Generated from: specs/251-add-launch-options-a-headless-autoplay-smoke-run-and-on-demand-game-screenshots-for-godot-games/requirements.md
Feature: Launch options, smoke runs, and screenshots for Godot games

  @SCN001
  Scenario: Launch options read the same on desktop and web
    Given the NmgLaunch autoload
    When it is configured with the user arguments "--hour=12 --at=Forest --nmg-autoplay" or the hash "#hour=12&at=Forest&nmg-autoplay"
    Then get_option "hour" is "12", get_option "at" is "Forest", "nmg-autoplay" reads "true", and an absent option returns its default

  @SCN002
  Scenario: The smoke run passes a clean game
    Given a consumer Godot project whose game run prints no error line and exits 0
    When "python -m nmg_game_dev.godot smoke --frames 600" runs
    Then Godot ran with "--fixed-fps 60 --quit-after 600 -- --nmg-autoplay --nmg-test-saves" headless
    And the command prints "smoke passed (600 frames)" and exits 0

  @SCN003
  Scenario Outline: The smoke run fails on runtime errors
    Given a game run that <outcome>
    When the smoke run runs
    Then it exits 1 with "<code>", at most 20 error lines, and a remediation line

    Examples:
      | outcome                          | code                |
      | prints a SCRIPT ERROR line       | smoke.runtime_error |
      | prints a Parse Error line        | smoke.runtime_error |
      | prints an ERROR: line            | smoke.runtime_error |
      | exits 1                          | smoke.runtime_error |
      | does not exit within its timeout | smoke.timeout       |

  @SCN004
  Scenario: /ship gates on the smoke run
    Given a ship of target "all" whose smoke run prints a SCRIPT ERROR line
    When the ship runs
    Then it fails with "ship.smoke_failed" after the project tests and no export runs
    And a dry run prints the smoke command with the "DRY-RUN:" prefix

  @SCN005
  Scenario: A screenshot is saved on demand
    Given a consumer Godot project whose game run writes a 1280x720 PNG
    When "python -m nmg_game_dev.godot shot build/shots/forest.png --after 3 -- --at=Forest --hour=18" runs, or game_screenshot is called with the same values
    Then Godot ran without --headless with "--at=Forest --hour=18 --nmg-test-saves", "--nmg-shot=<absolute path>", and "--nmg-shot-after=3"
    And the result JSON has the path, width 1280, and height 720

  @SCN006
  Scenario: A failed screenshot is reported
    Given a game run that exits without writing the PNG
    When the shot command runs
    Then it exits 1 with "shot.no_image" and the last lines of the game's output
    And with no Godot binary it fails with "godot.not_found"

  @SCN007
  Scenario: Test runs use their own save folder
    Given the NmgLaunch autoload
    When it is configured with "--nmg-test-saves"
    Then save_dir returns "user://nmg-test/", and without the flag it returns "user://"

  @SCN008
  Scenario: Onboarding registers the NmgLaunch autoload
    Given a consumer game/project.godot with only the NmgAssets autoload
    When onboarding runs
    Then [autoload] holds NmgLaunch="*res://addons/nmg_game_dev/nmg_launch.gd" and the key is reported as refreshed
