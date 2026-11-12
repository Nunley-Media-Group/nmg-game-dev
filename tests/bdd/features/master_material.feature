# File: tests/bdd/features/master_material.feature
# Generated from: specs/101-fix-m-nmgorm-sampler-defaults-and-skeletal-mesh-usage-so-finalized-assets-render-their-textures/requirements.md
Feature: M_NmgORM compiles with typed sampler defaults and supports skeletal meshes

  @SCN001 @regression
  Scenario: The master material's samplers default to textures that match their sampler type
    Given the M_NmgORM builder code from scripts/unreal/build_master_material.py
    When it builds the BaseColor, Normal, and ORM sampler parameters
    Then Normal defaults to /Engine/EngineMaterials/DefaultNormal
    And ORM defaults to /Engine/EngineMaterials/DefaultDiffuse_TC_Masks
    And the shipped M_NmgORM.uasset references both default textures

  @SCN002 @regression
  Scenario: The master material is usable on skeletal meshes
    Given the M_NmgORM builder code from scripts/unreal/build_master_material.py
    When it builds the material
    Then it enables used_with_skeletal_mesh before recompiling
    And the shipped M_NmgORM.uasset records bUsedWithSkeletalMesh

  @SCN003 @regression
  Scenario: Rebuilding keeps instances, parameter names, and channel wiring
    Given an existing M_NmgORM asset
    When the builder runs again
    Then it loads and clears the existing material instead of recreating it
    And the BaseColor, Normal, and ORM parameters keep their names
    And ORM R, G, and B still feed Ambient Occlusion, Roughness, and Metallic

  @SCN004 @regression
  Scenario: The master material is rebuilt by a separate headless UnrealEditor-Cmd process
    Given UE_ROOT holds a fake Build.sh and a fake UnrealEditor-Cmd that log their arguments
    And the Unreal MCP client fails if it is constructed
    When the builder runs with --headless
    Then UnrealEditor-Cmd opens fixtures/dogfood.uproject with -ExecutePythonScript and the MCP plugins disabled
    And the script it runs is the builder's graph code
    And the builder exits 0 without contacting an editor

  @SCN005 @regression
  Scenario: The committed master material carries the Tint parameter
    Given the committed M_NmgORM.uasset
    When its name table is inspected
    Then it holds the parameter names Tint, BaseColor, Normal, and ORM

  @SCN006 @regression
  Scenario: The rebuilt master material keeps its path and package name
    Given the committed M_NmgORM.uasset and the builder's graph code
    When the master is rebuilt in place
    Then the asset's package name is /nmg-game-dev/Materials/M_NmgORM
    And the builder loads and clears the existing material instead of recreating it
