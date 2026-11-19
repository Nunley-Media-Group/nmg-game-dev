# Generated from: specs/233-let-one-blend-hold-several-rigged-characters-that-share-clip-names/feature.gherkin
# Bound in tests/bdd/test_shared_clip_names_bdd.py (SCN004-SCN006, SCN009: host proofs with the
# finalize fakes and the docs) and tests/blender/test_shared_clip_names_bdd.py (SCN001-SCN003,
# SCN007, SCN008: real Blender data).
Feature: Several rigged characters in one .blend share clip names

  @SCN001
  Scenario: An @-suffixed action exports under its bare clip name
    Given rig "SK_StreetThug" holds action "Idle@SK_StreetThug"
    When StreetThug's clips are probed and exported
    Then the clip is named "Idle"
    And the file "Animations/A_StreetThug_Idle.glb" is written
    And the export record lists the clip as "Idle"

  @SCN002
  Scenario: Two characters in one file each export their own Idle
    Given one file holds "SK_StreetThug" with "Idle@SK_StreetThug" and "SK_Cop" with "Idle@SK_Cop"
    When each character's clips are exported
    Then "A_StreetThug_Idle.glb" holds StreetThug's action
    And "A_Cop_Idle.glb" holds Cop's action

  @SCN003
  Scenario: Unsuffixed action names export as before
    Given rig "SK_StreetThug" holds action "Idle"
    When its clips are probed and exported
    Then the clip name, file name, and record match the pre-change output
    And the clip hash equals the hash computed from the action name

  @SCN004
  Scenario: A suffix naming another rig stops the export
    Given the probe of "StreetThug" reports rig-mismatched action "Idle@SK_Cop"
    When export_anims runs
    Then it fails with "finalize.clip_rig_mismatch" naming "Idle@SK_Cop"
    And no clip file or sidecar is written

  @SCN005
  Scenario: Two actions resolving to one clip stop the export
    Given the probe of "StreetThug" reports clip "Idle" from actions "Idle" and "Idle@SK_StreetThug"
    When export_anims runs
    Then it fails with "finalize.clip_name_duplicate" naming "Idle" and both actions
    And no clip file or sidecar is written

  @SCN006
  Scenario: The bare clip name is still validated
    Given the probe of "StreetThug" reports clip "1Idle" with an invalid name
    When export_anims runs
    Then it fails with "finalize.clip_name_invalid" naming "1Idle"
    And no clip file or sidecar is written

  @SCN007
  Scenario: Importing a clip onto one character leaves the others alone
    Given one file holds "SK_StreetThug" with imported clip "Idle" and "SK_Cop" with none
    When "Idle" is imported onto "SK_Cop"
    Then "SK_Cop" has action "Idle@SK_Cop"
    And "Idle@SK_StreetThug" and StreetThug's provenance are unchanged
    And both rigs' provenance is keyed by "Idle"

  @SCN008
  Scenario: Re-importing a clip replaces only that rig's action
    Given "SK_StreetThug" has action "Idle@SK_StreetThug"
    When "Idle" is imported onto "SK_StreetThug" again
    Then exactly one action named "Idle@SK_StreetThug" exists and none named "Idle@SK_StreetThug.001"
    And no other rig's action changed

  @SCN009
  Scenario: The clip naming rule is documented
    Given the asset contract, rigging, finalize MCP, and finalize-asset skill docs
    When a reader looks up how clip names are derived
    Then they state the optional "<Clip>@SK_<Name>" suffix and that the pattern applies to the bare clip name
    And they list "finalize.clip_rig_mismatch" and "finalize.clip_name_duplicate" with remediations
