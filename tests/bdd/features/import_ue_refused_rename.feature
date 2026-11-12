# Generated from: specs/203-fail-import-ue-when-unreal-refuses-to-rename-or-consolidate-an-imported-asset/feature.gherkin
# Bound in tests/bdd/steps/test_import_ue_refused_rename.py. Each scenario runs the generated UE
# import code against tests/unit/fake_unreal.py with the refusal knobs set, so it checks the error
# the import reports and the assets it leaves behind.
Feature: import_ue fails when Unreal refuses to rename or consolidate an imported asset

  @SCN001 @regression
  Scenario: A refused part rename fails the import
    Given a Desktop multi-part static import whose part "SM_Crate_Lid" imports as "SM_Crate_Lid_001"
    And Unreal refuses to rename "SM_Crate_Lid_001"
    When import_ue imports the variant
    Then the import fails with "import_ue.failed"
    And the error names "SM_Crate_Lid_001" and the target "SM_Crate_Lid"

  @SCN002 @regression
  Scenario: A refused consolidation fails the import
    Given a Desktop re-import where "SM_Crate_Lid" already exists beside the new "SM_Crate_Lid_001"
    And Unreal refuses to consolidate "SM_Crate_Lid"
    When import_ue imports the variant
    Then the import fails with "import_ue.failed"
    And the error names the mesh "SM_Crate_Lid_001" and the target "SM_Crate_Lid"

  @SCN003 @regression
  Scenario: A refused physics-asset rename names both paths
    Given a rigged Desktop import whose physics asset is created in a "Physics" subfolder
    And Unreal refuses to rename the created physics asset
    When import_ue imports the variant
    Then the import fails with "import_ue.failed"
    And the error names the created physics asset path and the expected "SM_Crate_PhysicsAsset" path

  @SCN004 @regression
  Scenario: Successful renames and consolidations are unchanged
    Given a Desktop re-import where every rename and consolidation succeeds
    When import_ue imports the variant
    Then the import succeeds with a static mesh for every part
    And the old "SM_Crate_Lid" is consolidated into the new mesh
