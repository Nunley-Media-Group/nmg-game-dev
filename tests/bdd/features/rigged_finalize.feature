# Generated from: specs/102-preserve-the-rig-when-finalizing-a-character-rigged-with-rig-humanoid/requirements.md
# Bound in tests/bdd/test_rigged_finalize_bdd.py. The Blender steps run the headless cases in
# tests/blender/test_variants_rigged.py and tests/blender/test_contract_reimport.py; the Godot steps
# run import_godot through the finalize fakes. #249 moved the import to Godot, which generates the
# Mobile LODs at import time, so the Mobile scenario describes one skinned .glb.
Feature: Finalize keeps the rig of a character rigged with rig_humanoid
  As an NMG game developer
  I want a character rigged with rig_humanoid to finalize as skinned variants
  So that Godot imports it as a skinned scene with working LODs

  @SCN001 @regression
  Scenario: Desktop exports skinned and imports as a skinned scene
    Given a character collection "Hero" whose SK_Hero skins SM_Hero through an Armature modifier
    When the Hero asset is finalized
    Then Desktop/Hero.glb holds an armature named Armature with 26 deform bones and SM_Hero skinned to it
    And res://export/Characters/Hero/Desktop/Hero.glb is imported and its probed meshes match Desktop/nmg-asset.json

  @SCN002 @regression
  Scenario: Mobile exports one skinned scene and imports beside the Desktop variant
    Given the same rigged Hero collection
    When the Hero asset is finalized
    Then Mobile holds Hero.glb with the armature and one skinned mesh and no _LOD files
    And res://export/Characters/Hero/Mobile/Hero.glb is imported and its probed meshes match Mobile/nmg-asset.json

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
    Then Desktop and Mobile each hold one static Crate.glb and both import into Godot

  @SCN005 @regression
  Scenario: The re-import check covers rigged variants
    Given exported rigged Hero variants
    When the re-import check runs on the Mobile folder
    Then it imports the skinned .glb and passes
    And a mesh exported without its skin is reported as reimport.skin_missing
