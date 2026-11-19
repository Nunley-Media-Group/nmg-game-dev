# Generated from: specs/236-evaluate-rigged-assets-in-their-rest-pose-during-finalize-so-a-leftover-pose-does-not-fail-pivot-bottom-center/feature.gherkin
# Bound in tests/bdd/test_rest_pose_finalize_bdd.py. Each binding runs its proof in
# tests/blender/test_rest_pose_finalize.py through scripts/run-blender-tests.sh.
Feature: Rigged assets are evaluated in their rest pose during finalize

  @SCN001 @regression
  Scenario: A posed rig does not fail the pivot check
    Given a rigged hero whose rest pose has its origin at the bottom center
    And its rig has no action and pose bones that move the skin's bounds by more than 1 mm
    When validate_asset runs on it
    Then the report has no "pivot.bottom_center" finding

  @SCN002 @regression
  Scenario: The mesh checks measure the rest pose
    Given the posed rigged hero
    When validate_asset runs on it and on the same hero with its pose cleared
    Then both reports have the same findings and measured values

  @SCN003 @regression
  Scenario: Export and reduction do not bake the pose
    Given the posed rigged hero
    When export_variants writes its Desktop and Mobile .glb files and reduce_asset reduces it
    Then each re-imported skinned mesh has the rest-pose bounds within 1e-3 m
    And each re-imported armature's rest heads match the source rest heads within 1e-3 m
    And each reduced copy has the rest-pose bounds within 1e-3 m

  @SCN004 @regression
  Scenario: The scene is left unchanged
    Given the posed rigged hero
    When validate_asset, reduce_asset, or export_variants finishes or raises
    Then every pose bone's transforms, the armature's pose_position, and the rig's action are what they were before

  @SCN005 @regression
  Scenario: Exporting clips does not leave a stray pose
    Given a rig with no action assigned and its pose bones at identity
    When export_clips exports its clips
    Then every pose bone is at identity and the rig has no action assigned
