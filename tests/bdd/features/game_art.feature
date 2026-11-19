# File: tests/bdd/features/game_art.feature
# Generated from: specs/253-generate-and-finish-2d-game-art-icons-ui-art-paintings-with-the-local-texture-models/requirements.md
Feature: Generate and finish 2D game art

  @SCN001
  Scenario: 2D art generates without tiling
    Given the texture models are available through the fake worker
    When "texture art --kind icon --name HealthPotion --prompt 'red potion bottle' --seeds 1,2,3" runs
    Then SourceArt/Art/raw/icon/HealthPotion-1.png, -2.png, and -3.png hold the worker's pixels unchanged
    And no derived maps are written
    And HealthPotion.json and HealthPotion_sheet.png are written

  @SCN002
  Scenario Outline: Kinds set framing and size
    When art of kind "<kind>" with aspect "<aspect>" is generated at resolution 1024
    Then the raw image is <width> by <height> and its prompt carries the "<kind>" framing text

    Examples:
      | kind     | aspect | width | height |
      | icon     | 1:1    | 1024  | 1024   |
      | ui       | 1:1    | 1024  | 1024   |
      | painting | 16:9   | 1024  | 576    |
      | painting | 3:2    | 1024  | 704    |

  @SCN003
  Scenario: The project style is shared
    Given SourceArt/Art/style.json with style "hand-painted, warm palette"
    When icon art and a tiling texture are generated
    Then the art prompt is "red potion bottle, hand-painted, warm palette, <icon framing text>"
    And the texture prompt is unchanged and textures.json records the project style

  @SCN004
  Scenario: Existing takes are skipped
    Given SourceArt/Art/raw/icon/HealthPotion-2.png exists
    When the HealthPotion request with seeds 1,2,3 runs again
    Then seed 2 is reported as skipped and only seeds 1 and 3 are generated
    And a request for seed 2 alone starts no worker

  @SCN005
  Scenario: Icons are cut out
    Given a raw icon take of a disc on a flat grey background
    When "texture art-finish --kind icon --name HealthPotion --pick 2" runs twice
    Then game/assets/UI/Icons/HealthPotion.png is 512 px with transparent corners and a feathered edge
    And HealthPotion_small.png is 64 px
    And the second run's files are byte-identical to the first

  @SCN006
  Scenario Outline: A non-flat background is rejected
    Given a raw icon take <problem>
    When art-finish runs
    Then it fails with "<code>" and a remediation and writes nothing

    Examples:
      | problem                        | code                    |
      | whose corners differ in colour | art.background_not_flat |
      | whose subject touches the edge | art.subject_cropped     |

  @SCN007
  Scenario: Paintings are finished without a cut-out
    Given a raw 16:9 painting take
    When "texture art-finish --kind painting --name Dawn --pick 1 --width 1920" runs
    Then game/assets/UI/Paintings/Dawn.png is 1920 by 1080 with no alpha channel
