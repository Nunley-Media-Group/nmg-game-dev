# File: tests/bdd/features/tiling_seam_check.feature
# Mirrors: specs/147-fix-the-tiling-seam-check-rejecting-high-frequency-textures-that-tile-correctly/feature.gherkin
# (SCN001-SCN004, SCN006, SCN007; SCN005 runs in tests/blender/test_bake_tiling.py)
Feature: Tiling seam check judges the wrap against the texture's own interior

  @SCN001 @regression
  Scenario: An exactly tileable busy texture passes
    Given an exactly periodic fine-noise texture whose interior adjacent-row difference is above 0.04
    When the tiling seam check runs on it
    Then no not_seamless error is raised

  @SCN002 @regression
  Scenario: A real wrap discontinuity on a busy texture fails
    Given a non-periodic noise texture whose wrap difference is at least 3 times its interior difference
    When the tiling seam check runs on it
    Then not_seamless is raised and the message names the failing channel

  @SCN003 @regression
  Scenario: A visible seam on a smooth texture fails
    Given a smooth gradient whose wrap step is under 0.04 but at least 10 times its interior difference
    When the tiling seam check runs on it
    Then not_seamless is raised

  @SCN004 @regression
  Scenario: Flat and near-flat textures pass
    Given a constant texture and a near-flat 8-bit texture with one level of noise
    When the tiling seam check runs on each
    Then no not_seamless error is raised

  @SCN006 @regression
  Scenario: Bake and texture-gen agree on what seamless means
    Given the seam test corpus in 8-bit and float, RGB and single-channel forms
    When each image is judged by the bake seam check and by is_seamless
    Then both give the same result for every image

  @SCN007 @regression
  Scenario: The error and docs describe the measure and a fix
    Given a not_seamless failure on a non-periodic texture
    When the author reads the message and its remediation
    Then the message reports the wrap and interior values for the failing channel
    And the remediation names python -m nmg_game_dev.texture seamless
