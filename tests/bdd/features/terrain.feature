# File: tests/bdd/features/terrain.feature
# Generated from the #154 terrain asset class requirements; #249 moved the import to Godot, so the
# import and region scenarios describe chunked .glb meshes in a .tscn with HeightMapShape3D collision.
Feature: Terrain asset class finalized into Godot terrain scenes

  @SCN001
  Scenario: A valid terrain grid passes the terrain contract
    Given a collection with one centered 1 m grid mesh at a valid terrain resolution
    And two Layer attributes, each with a matching tiling material
    When the contract validator runs with class terrain
    Then the report passes
    And it records resolution, height range, layers, and texel density for Desktop and Mobile

  @SCN002
  Scenario: Finalize exports heightmaps, weightmaps, and layer textures
    Given a terrain collection that passes validation
    When finalize exports it
    Then each variant folder holds T_<Name>_Height.png, <Name>_Chunk_<r>_<c>.glb chunks, T_<Name>_Splat.png, and each layer's BC, N, and ORM textures
    And every weightmap pixel set sums to 255
    And nmg-variants.json records terrain true with each variant's resolution, height range, and layers

  @SCN003
  Scenario: The Mobile terrain fits the Mobile budget
    Given a Desktop terrain at 2017 with 4 layers
    When the Mobile variant is built
    Then its heightmap is 1009 at 2 m spacing over the same extent
    And it keeps 3 layers, with the lowest-weight layer renormalized into the rest

  @SCN004
  Scenario: Godot import builds a terrain scene per variant
    Given exported Desktop and Mobile terrain variants
    When the import_godot step runs
    Then each variant gets <Name>.tscn instancing every chunk with the terrain shader and a HeightMapShape3D built from the heightfield
    And a probed height range more than 5 cm from the heightfield fails with import_godot.terrain_height_mismatch

  @SCN005
  Scenario: A region with an imported terrain instances it instead of a plane
    Given a region entry whose terrain names an imported terrain entry
    When scaffold creates the region level
    Then the level loads the terrain's platform variant and has no ground plane

  @SCN006
  Scenario: A region without an imported terrain keeps the flat plane
    Given a region entry without terrain, or whose terrain scene does not exist yet
    When scaffold creates the region level
    Then the level has the flat ground plane

  @SCN007
  Scenario Outline: Out-of-contract terrain fails with a named finding
    Given a terrain collection that breaks the <rule> rule
    When validation runs
    Then the report fails with <rule> and a remediation
    And finalize exports nothing and imports nothing into Godot

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
