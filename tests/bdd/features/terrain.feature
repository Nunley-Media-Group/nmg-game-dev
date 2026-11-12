# File: tests/bdd/features/terrain.feature
# Generated from: specs/154-add-a-terrain-asset-class-that-finalizes-blender-heightfields-into-unreal-landscapes/requirements.md
Feature: Terrain asset class finalized into Unreal Landscapes

  @SCN001
  Scenario: A valid terrain grid passes the terrain contract
    Given a collection with one centered 1 m grid mesh at a valid Landscape resolution
    And two Layer attributes, each with a matching tiling material
    When the contract validator runs with class terrain
    Then the report passes
    And it records resolution, height range, layers, and texel density for Desktop and Mobile

  @SCN002
  Scenario: Finalize exports heightmaps, weightmaps, and layer textures
    Given a terrain collection that passes validation
    When finalize exports it
    Then each variant folder holds T_<Name>_Height.png, one weightmap per layer, and each layer's BC, N, and ORM textures
    And every weightmap pixel set sums to 255
    And nmg-variants.json records terrain true with each variant's resolution, height range, and layers

  @SCN003
  Scenario: The Mobile terrain fits the Mobile budget
    Given a Desktop terrain at 2017 with 4 layers
    When the Mobile variant is built
    Then its heightmap is 1009 at 2 m spacing over the same extent
    And it keeps 3 layers, with the lowest-weight layer renormalized into the rest

  @SCN004
  Scenario: Unreal import builds a Landscape level per variant
    Given exported Desktop and Mobile terrain variants
    When the import_ue step runs
    Then each variant gets M_<Name>_Landscape, one layer info per layer, and the level L_<Name> with a Landscape at the derived transform
    And a sampled height more than 5 cm from the Blender height fails with import_ue.terrain_height_mismatch

  @SCN005
  Scenario: A region with an imported terrain streams it instead of a plane
    Given a region entry whose terrain names an imported terrain entry
    When scaffold creates the region level
    Then the level streams the terrain's Desktop level and has no ground plane

  @SCN006
  Scenario: A region without an imported terrain keeps the flat plane
    Given a region entry without terrain, or whose terrain level does not exist yet
    When scaffold creates the region level
    Then the level has the flat ground plane

  @SCN007
  Scenario Outline: Out-of-contract terrain fails with a named finding
    Given a terrain collection that breaks the <rule> rule
    When validation runs
    Then the report fails with <rule> and a remediation
    And finalize exports nothing and creates no Unreal asset

    Examples:
      | rule                          |
      | terrain.resolution_invalid    |
      | terrain.spacing               |
      | terrain.not_centered          |
      | terrain.structure             |
      | terrain.layer_missing         |
      | terrain.layer_range           |
      | terrain.over_budget           |
      | terrain.layer_texture_missing |

  @SCN008
  Scenario: A region naming no terrain entry is an unknown reference
    Given a region entry whose terrain names no environment entry with asset_class terrain
    When the design docs are synced or scaffolded
    Then the run reports design.unknown_reference for the terrain field
