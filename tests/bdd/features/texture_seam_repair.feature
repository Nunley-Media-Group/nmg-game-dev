# File: tests/bdd/features/texture_seam_repair.feature
# Mirrors: specs/238-make-every-texture-gen-map-pass-the-bake-seam-rule-and-stop-texture-seamless-from-worsening-tiled-images/feature.gherkin
Feature: Every texture-gen map passes the bake seam rule

  @SCN001 @regression
  Scenario: Generated albedo and derived maps pass the seam rule
    Given a fake worker that writes the low-contrast band-limited image
    And a request with the "stone" preset and AO
    When texture generation runs
    Then the albedo and its N, R, M and AO PNGs each pass is_seamless

  @SCN002 @regression
  Scenario Outline: Derived maps pass for a passing albedo
    Given the passing albedo "<albedo>"
    When maps.derive writes N, R, M and AO
    Then each derived map passes is_seamless

    Examples:
      | albedo                  |
      | seamless synthetic      |
      | seamless low-contrast   |

  @SCN003 @regression
  Scenario: texture seamless leaves a passing image unchanged
    Given a PNG of the seamless synthetic albedo
    When python -m nmg_game_dev.texture seamless runs on it
    Then the written pixels equal the input pixels
    And the printed JSON reports seamless true

  @SCN004 @regression
  Scenario Outline: texture seamless repairs a failing image without worsening it
    Given a PNG of the failing image "<image>"
    When python -m nmg_game_dev.texture seamless runs on it
    Then the written image passes is_seamless with the input's shape and dtype
    And on neither axis is its wrap larger than the input's

    Examples:
      | image                |
      | non-tiling synthetic |
      | narrow seam albedo   |
      | stepped normal map   |

  @SCN005 @regression
  Scenario: Existing texture behaviour is preserved
    Given the existing texture unit tests and texture BDD scenarios
    When they run against the fixed package
    Then they all pass

  @SCN006
  Scenario: Docs tell consumers to reload or repack fixed textures
    Given docs/onboarding/texture-models.md and docs/skills/bake-materials.md
    When the seamless section and the not_seamless remediation are read
    Then each says images packed into a .blend file must be reloaded or repacked from the fixed files
