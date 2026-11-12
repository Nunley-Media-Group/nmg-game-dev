# Bound by tests/bdd/test_meshy_bdd.py (#98). Scenarios match the approved spec
# specs/98-add-optional-meshy-model-generation-and-retexturing-through-the-meshy-api/feature.gherkin.
Feature: Optional Meshy model generation and retexturing

  @SCN001
  Scenario: Prompt-only generation lands in the Blender session
    Given a Meshy API key is available and a reachable session with no "Crate" collection
    When the agent calls generate_model with name "Crate" and prompt "weathered wooden crate" and polls the job to completion
    Then Meshy text-to-3D receives a "preview" request and then a "refine" request with enable_pbr true
    And the job reports "succeeded" with loaded_into_session true and the GLB path
    And "SourceArt/Meshy/Crate/Crate.glb" exists
    And the session has collection "Crate" with mesh "SM_Crate" and material "M_Crate_Body"

  @SCN002
  Scenario Outline: Reference images alone shape the model
    Given a Meshy API key is available and <count> local reference images
    When the agent calls generate_model with name "Lamppost" and those image paths
    Then Meshy <endpoint> receives the images as base64 data URIs with their MIME types
    And no texture_prompt is sent
    And the session has collection "Lamppost" with mesh "SM_Lamppost"

    Examples:
      | count | endpoint           |
      | 1     | image-to-3D        |
      | 3     | multi-image-to-3D  |

  @SCN003
  Scenario: Reference images and a prompt together
    Given a Meshy API key is available and 2 local reference images
    When the agent calls generate_model with name "Ghost", those image paths, and prompt "pale translucent cloth"
    Then Meshy multi-image-to-3D receives the images and texture_prompt "pale translucent cloth" in one request
    And the session has collection "Ghost" with mesh "SM_Ghost"

  @SCN004
  Scenario: Pose is sent only when the agent asks for it
    Given a Meshy API key is available and 1 local reference image
    When the agent calls generate_model with name "Ghost", that image path, and pose "a-pose"
    Then the image-to-3D request carries pose_mode "a-pose"
    And a generate_model call for "Crate" without pose sends no pose_mode

  @SCN005
  Scenario: Untextured generation runs only the untextured stage
    Given a Meshy API key is available
    When the agent calls generate_model with name "Crate", a prompt, and texture false
    Then exactly one text-to-3D request is sent, with mode "preview"
    And the untextured mesh lands in the session as "SM_Crate"

  @SCN006
  Scenario: Unreachable session at import time keeps the GLB
    Given a generation job whose Meshy task succeeded
    And the Blender session is unreachable at import time
    When the job finishes
    Then it reports "succeeded" with loaded_into_session false and a warning "mcp.blender.unreachable"
    And the GLB stays on disk

  @SCN007
  Scenario: Retexture an authored mesh
    Given a Meshy API key is available and the session has collection "Crate" with mesh "SM_Crate"
    When the agent calls retexture_model with name "Crate" and prompt "mossy stone" and polls it to completion
    Then Meshy retexture receives the exported collection as a GLB data URI
    And base color, normal, roughness, and metallic maps are saved under "SourceArt/Textures/Meshy/Crate/"
    And the job reports applied_to_session true with the map paths

  @SCN008
  Scenario: The key comes from the project .env unless the environment sets it
    Given MESHY_API_KEY is unset and the project .env contains "MESHY_API_KEY=key-from-dotenv"
    When a Meshy request is sent
    Then it carries "Authorization: Bearer key-from-dotenv"
    And with MESHY_API_KEY "key-from-env" in the environment the next request carries "Authorization: Bearer key-from-env"

  @SCN009
  Scenario: Missing API key fails fast
    Given MESHY_API_KEY is unset and the project has no .env
    When the agent calls generate_model with name "Crate" and a prompt
    Then it returns error "meshy.api_key_missing" with a remediation naming "MESHY_API_KEY" and ".env"
    And no HTTP request was sent and no job directory exists

  @SCN010
  Scenario Outline: Meshy API failures are structured and never leak the key
    Given a Meshy job in progress
    When Meshy <failure>
    Then the job reports "failed" with code "<code>" and a remediation
    And the API key appears in no job file and no error message

    Examples:
      | failure                | code                       |
      | answers 401            | meshy.auth_failed          |
      | answers 402            | meshy.insufficient_credits |
      | answers 429            | meshy.rate_limited         |
      | ends the task FAILED   | meshy.task_failed          |
      | ends the task CANCELED | meshy.task_failed          |
      | ends the task EXPIRED  | meshy.task_failed          |

  @SCN011
  Scenario Outline: Invalid requests are rejected before any Meshy call
    Given a Meshy API key is available
    When the agent sends <request>
    Then it returns "<code>" with a remediation
    And no Meshy request was sent

    Examples:
      | request                                                      | code                       |
      | generate_model with name "crate"                             | meshy.invalid_request      |
      | generate_model with neither a prompt nor images              | meshy.invalid_request      |
      | generate_model with five images                              | meshy.invalid_request      |
      | generate_model with a ".gif" image                           | meshy.invalid_request      |
      | generate_model with an image path that does not exist        | meshy.invalid_request      |
      | generate_model with images and an 801-character prompt       | meshy.invalid_request      |
      | generate_model with images, a prompt, and texture false      | meshy.invalid_request      |
      | generate_model with pose "sitting"                           | meshy.invalid_request      |
      | retexture_model with both a prompt and an image path         | meshy.invalid_request      |
      | generate_model for an existing "Crate" collection            | meshy.collection_exists    |
      | retexture_model for a missing "Crate" collection             | meshy.collection_not_found |

  @SCN012
  Scenario: The CLI and the MCP tools share one implementation
    Given the same generate inputs
    When the developer runs "python -m nmg_game_dev.meshy generate" and then "status" for the job
    Then the CLI prints the same status JSON that get_meshy_job returns for that job

  @SCN013
  Scenario: Configuration and guards admit the optional meshy server
    Given the repository
    When the guard tests and scripts/validate-mcp-tools.py run
    Then .mcp.json declares a "meshy" uv run server with no MESHY_API_KEY text and the other four entries unchanged
    And the generate_model description limits pose to characters and creatures with limbs
    And pipeline and finalize sources contain no Meshy code
    And product steering lists Meshy as an optional opt-in paid source

  @SCN014
  Scenario: The project .env is git-ignored
    Given a consumer project whose .gitignore lacks a ".env" entry
    When onboarding runs twice
    Then the consumer .gitignore contains exactly one ".env" line
    And the "gitignore_env" step reports "installed" then "unchanged"
    And no ".env" file was created

  # #105 spec SCN004. Numbered SCN015 here, because SCN004 is already this file's pose scenario.
  @SCN015
  Scenario: The import and job results report the normalization
    Given a Meshy generate job whose session import succeeds
    When the job finishes
    Then the import result and the job result carry merged_vertices and origin_offset

  # #106 spec SCN001–SCN004. Numbered SCN016–SCN019 here, because SCN001–SCN015 are this file's
  # #98 and #105 scenarios. The geometry steps need bpy, so tests/blender/test_meshy_session.py
  # runs them under the same #106 tests; the bindings here check the contract and the neutral-pose
  # check on the rotation that contract reports.

  @SCN016
  Scenario: A 55 degree A-pose is raised to 48 degrees
    Given a GLB of a 1.8 m box humanoid with both arms dropped 55 degrees
    When import_glb imports it as "Hero" with pose a-pose
    Then each arm's drop is 48 degrees within 0.5
    And torso-midline and leg vertices have not moved
    And vertex count, face count, and connectivity are unchanged with no flipped faces

  @SCN017
  Scenario: Compliant or non-A-pose imports are untouched
    Given a GLB of the box humanoid
    When import_glb imports it with pose t-pose, with no pose, or as an A-pose dropped 45 degrees
    Then no vertex moves

  @SCN018
  Scenario: The job result reports the arm raise
    Given a Meshy generate job with pose a-pose whose session import succeeds
    When the job finishes
    Then the job result carries arm_raise with left and right detected, shoulder, hand_tip, drop_before_deg, drop_after_deg, and rotation_deg

  @SCN019
  Scenario: The raised humanoid passes the neutral-pose check
    Given the raised Hero with shoulder landmarks at the pivots and wrist landmarks on the raised arms
    When rig_core.landmarks.validate runs for a humanoid
    Then it does not report rig.pose_not_neutral

  # #135 spec SCN001–SCN009. Numbered SCN020–SCN028 here, because SCN001–SCN019 are this file's #98,
  # #105, and #106 scenarios. The geometry needs bpy, so tests/blender/test_meshy_session.py runs the
  # geometry steps under the #135 tests of the same name; the bindings here check the contract
  # through the fakes and that the Blender suite defines each test they name.

  @SCN020 @regression
  Scenario: Legs, boots, and skirt stay put on a stylized character
    Given a GLB of a stylized character with shoulders at 0.6 H, arms dropped 55 degrees, and wide legs, boots, and a skirt
    When import_glb imports it as "Hero" with pose a-pose
    Then every leg, boot, skirt, torso, and head vertex is where normalization left it
    And only arm vertices have moved

  @SCN021 @regression
  Scenario: The arm is raised from the detected shoulder
    Given the stylized character GLB
    When import_glb imports it as "Hero" with pose a-pose
    Then each side's drop_before_deg is 55 degrees within 3
    And each side's drop_after_deg is 48 degrees within 0.5

  @SCN022 @regression
  Scenario: The shoulder is found at the armpit
    Given the stylized character GLB with a gap between each arm and the torso
    When import_glb imports it as "Hero" with pose a-pose
    Then each reported shoulder lies within 0.03 H of the fixture's true shoulder

  @SCN023 @regression
  Scenario: Unconnected or out-of-reach geometry does not move
    Given the stylized character GLB with a detached box outboard of each arm below its hand
    When import_glb imports it as "Hero" with pose a-pose
    Then the detached boxes have not moved
    And every moved vertex lies within the arm's length of its detected shoulder

  @SCN024
  Scenario: The detected landmarks are reported
    Given the stylized character GLB
    When import_glb imports it as "Hero" with pose a-pose
    Then each side of arm_raise holds detected true, shoulder, and hand_tip as world-space points after the raise
    And the left points have x greater than 0 and the right points x less than 0, inside the mesh's bounding box

  @SCN025 @regression
  Scenario: A fused arm is left untouched
    Given a GLB of the stylized character whose right arm is fused to the torso
    When import_glb imports it as "Hero" with pose a-pose
    Then the import succeeds
    And the right side reports detected false with reason "no_armpit" and rotation_deg 0
    And no right-side vertex has moved
    And the left arm's drop is 48 degrees within 0.5

  @SCN026
  Scenario: The raise can be skipped
    Given a generate_model request with pose "a-pose" and raise_arms false
    When the job generates and imports the model
    Then Meshy receives pose_mode "a-pose"
    And the import normalizes the mesh and moves no vertex by an arm raise
    And the job result's arm_raise is null

  @SCN027 @regression
  Scenario: Realistic humanoids still import correctly
    Given a GLB of a 1.8 m box humanoid with both arms dropped 55 degrees
    When import_glb imports it as "Hero" with pose a-pose
    Then each arm's drop is 48 degrees within 0.5
    And a side already at 48 degrees or less keeps every vertex and still reports its shoulder
    And vertex count, face count, connectivity, and face orientation are unchanged

  @SCN028 @regression
  Scenario: Other poses are unchanged
    Given a GLB of the box humanoid
    When import_glb imports it with pose t-pose or with no pose
    Then no vertex moves
    And arm_raise is null
