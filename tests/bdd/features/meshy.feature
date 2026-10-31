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
