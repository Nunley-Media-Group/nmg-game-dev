# Generated from: specs/102-preserve-the-rig-when-finalizing-a-character-rigged-with-rig-humanoid/requirements.md
# Bound in tests/bdd/test_rigged_finalize_bdd.py. The Blender steps run the headless cases in
# tests/blender/test_variants_rigged.py and tests/blender/test_contract_reimport.py; the UE steps
# check the import code that build_import_code writes.
Feature: Finalize keeps the rig of a character rigged with rig_humanoid
  As an NMG game developer
  I want a character rigged with rig_humanoid to finalize as skinned variants
  So that Unreal imports it as a Skeletal Mesh with working LODs

  @SCN001 @regression
  Scenario: Desktop exports skinned and imports as a Skeletal Mesh
    Given a character collection "Hero" whose SK_Hero skins SM_Hero through an Armature modifier
    When the Hero asset is finalized
    Then Desktop/SM_Hero.fbx holds an armature named Armature with 26 deform bones and SM_Hero skinned to it
    And /Game/Characters/Hero/Desktop/SM_Hero is a Skeletal Mesh with SM_Hero_Skeleton, SM_Hero_PhysicsAsset, and MI_Hero_<Part> on every slot

  @SCN002 @regression
  Scenario: Mobile exports three skinned LODs and imports onto the Desktop skeleton
    Given the same rigged Hero collection
    When the Hero asset is finalized
    Then Mobile holds SM_Hero.fbx, SM_Hero_LOD1.fbx, and SM_Hero_LOD2.fbx, each with the armature and one skinned mesh
    And LOD1 and LOD2 are at most 50% and 25% of LOD0's triangles
    And /Game/Characters/Hero/Mobile/SM_Hero is a Skeletal Mesh with 3 LODs using the Desktop skeleton and physics asset

  @SCN003 @regression
  Scenario: Cleanup keeps the Armature modifier and vertex groups
    Given a rigged Hero mesh that also has a non-Armature modifier
    When the variants cleanup runs
    Then the non-Armature modifier is applied
    And the Armature modifier targeting SK_Hero and the vertex groups remain

  @SCN004 @regression
  Scenario: Unrigged assets keep the static path
    Given a collection "Crate" with no SK_Crate
    When the Crate asset is finalized
    Then Desktop and Mobile import as Static Meshes and Mobile keeps its single-FBX LodGroup layout

  @SCN005 @regression
  Scenario: The re-import check covers rigged variants
    Given exported rigged Hero variants
    When the re-import check runs on the Mobile folder
    Then it imports all three LOD files and passes
    And a mesh exported without its skin is reported as reimport.skin_missing
