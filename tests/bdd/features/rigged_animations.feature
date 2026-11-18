# Generated from: specs/138-export-and-import-rigged-character-animation-clips-through-finalize/feature.gherkin
# Bound in tests/bdd/test_rigged_animations_bdd.py. Each scenario runs its own host proof with the
# finalize fakes, plus the headless Blender cases named for it there. #249 moved the import side
# from the previous engine to Godot animation libraries, so the import scenarios describe Godot.
Feature: Export and import rigged-character animation clips through finalize

  @SCN001
  Scenario: Finalize exports one animation .glb per clip
    Given a rigged character whose SK_<Name> has clips Idle and Walk
    When finalize all runs
    Then export_anims writes A_<Name>_Idle.glb and A_<Name>_Walk.glb under <export_root>/<Category>/<Name>/Animations/
    And each file holds only the armature named Armature and exactly one clip, with the rigged export's armature and axis settings

  @SCN002
  Scenario: The clip set is provenance clips plus actions held on the rig
    Given SK_<Name> has provenance clip Idle, an NLA action Wave, and the file holds an unrelated action Other
    When export_anims runs
    Then Idle and Wave are exported and Other is not

  @SCN003
  Scenario: nmg-animations.json records real clip data
    Given export_anims exported clips for <Name>
    When the step finishes
    Then nmg-animations.json in Animations/ lists each clip's name, file, asset path, frame start, end, count, and fps
    And provenance clips carry their recorded source and other clips carry source authored

  @SCN004
  Scenario: Clips import as Godot animation libraries
    Given import_godot has imported the Desktop <Name>.glb with its skeleton
    When import_anims runs
    Then each clip's A_<Name>_<Clip>.glb.import selects the animation_library importer and the clip is res://.../Animations/A_<Name>_<Clip>.glb
    And the project is imported once and the result lists the clips

  @SCN005
  Scenario: An imported clip is checked against the sidecar
    Given a clip whose sidecar entry records its frame count
    When the imported animation library has a different frame count or is missing
    Then the step fails naming the clip, the expected value, and the measured value

  @SCN006
  Scenario: Clips are cached individually
    Given a finished finalize of a character with clips Idle and Walk
    When only Walk changes and finalize runs again
    Then Walk is re-exported and re-imported, Idle is served from cache, and the mesh steps are served from cache

  @SCN007
  Scenario: Force reruns every clip
    Given a finished finalize with every clip cached
    When finalize runs with force
    Then every clip is re-exported and re-imported

  @SCN008
  Scenario: Assets without clips pass through
    Given an unrigged asset or a rigged character with no clips
    When finalize all runs
    Then both animation steps succeed with zero clips, nothing is written under Animations/, and other outputs are unchanged

  @SCN009
  Scenario: The new steps run alone
    Given a rigged character whose mesh steps have completed
    When run_finalize_step or the CLI is called with export_anims or import_anims
    Then that step runs with its dependencies served from cache and returns the standard result shape

  @SCN010
  Scenario: import_anims needs the Desktop skeleton
    Given the Desktop <Name>.glb does not exist
    When import_anims runs
    Then it fails with finalize.skeleton_not_found telling the user to run import_godot first, and Godot does not run

  @SCN011
  Scenario: An invalid clip name stops the export
    Given a rig-held action whose name does not match ^[A-Za-z][A-Za-z0-9_]*$
    When export_anims runs
    Then it fails with finalize.clip_name_invalid naming the action and writes no clip .glb or sidecar

  @SCN012
  Scenario: Stale clip files are reported, never deleted
    Given Animations/ holds A_<Name>_Run.glb and Run is no longer a clip
    When import_anims runs
    Then A_<Name>_Run.glb still exists and is listed under stale

  @SCN013
  Scenario: Compatible skeletons are checked on request
    Given character B is finalized and A's request sets compatible_with to B
    When import_anims runs for A
    Then every bone A's clips animate exists in B's Desktop skeleton, and the result lists B's Desktop scene as compatible

  @SCN014
  Scenario: Compatible checking is idempotent
    Given A and B were already checked as compatible
    When finalize runs again for A with the same compatible_with
    Then the result lists B's Desktop scene exactly once

  @SCN015
  Scenario: A compatible target must exist and match bone names
    Given compatible_with names a missing character or one with different bone names
    When import_anims runs
    Then it fails with finalize.skeleton_not_found or finalize.skeleton_mismatch naming the target

  @SCN016
  Scenario: Without compatible_with nothing is checked
    Given a finalize request that omits compatible_with
    When finalize runs
    Then no skeleton scene is probed and the result lists no compatible scene
