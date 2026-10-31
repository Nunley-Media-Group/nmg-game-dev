Feature: Generate local seamless textures

  @SCN012
  Scenario: The texture registry holds exactly the two pinned models
    Given the texture registry
    When its backends are listed
    Then it contains exactly "z-image-turbo" and "flux2-klein-4b" with their pinned repo, revision, license, quantization, steps, and peak memory
    And the registry cannot be extended at runtime

  @SCN013
  Scenario Outline: Only the pinned models load
    Given a texture request for <model>
    When generation is requested
    Then it raises "<code>" with a remediation listing the two allowed backends

    Examples:
      | model                               | code                       |
      | repo black-forest-labs/FLUX.2-klein-9B | texture.model_not_allowed |
      | repo black-forest-labs/FLUX.1-dev   | texture.model_not_allowed  |
      | backend id "sdxl"                   | texture.unknown_backend    |

  @SCN014
  Scenario: Missing weights point at onboarding
    Given TEXTURE_GEN_MODELS_DIR without a flux2-klein-4b-q4 directory
    When flux2-klein-4b availability is checked and generation is requested
    Then availability is "not_installed"
    And generation raises "texture.model_not_installed" naming /onboard-consumer, the mflux-save command, and the expected path

  @SCN015
  Scenario Outline: The hardware check refuses unfit backends
    Given hardware facts for <machine>
    When z-image-turbo is requested explicitly
    Then it raises "<code>" with a remediation

    Examples:
      | machine                              | code                         |
      | an x86_64 Linux host                 | texture.unsupported_platform |
      | an Apple Silicon Mac with 16 GB RAM  | texture.insufficient_memory  |

  @SCN016
  Scenario: Each backend batch runs in one isolated process
    Given a fake worker and a batch of three requests for flux2-klein-4b
    When the batch is generated
    Then the worker loaded the model once and three seamless PNGs were written

  @SCN017
  Scenario: Models never run concurrently
    Given a fake worker and a request for backend "both"
    When generation runs
    Then the flux2-klein-4b worker started only after the z-image-turbo worker exited
    And starting a second job while one is running raises "texture.job_running"

  @SCN018
  Scenario: Outputs tile seamlessly
    Given a 256x256 non-tiling synthetic image
    When the seamless post-process runs
    Then the dimensions are unchanged and both wrap seams are within 1.5x the interior pixel difference

  @SCN019
  Scenario: Derived PBR maps are seamless
    Given a seamless albedo and the "stone" preset
    When derived maps are requested with AO
    Then _N, _R, _M, and _AO PNGs exist at the albedo resolution and each passes the seam check

  @SCN020
  Scenario: The agent generates textures through the MCP tools
    Given a consumer project, a fake worker, and both backends available
    When the agent calls generate_textures for "burlap" with backend "both" and polls get_texture_job
    Then the job reports running and then succeeded with PNG paths and timings
    And the files are under SourceArt/Textures/Generated/burlap with textures.json and burlap_compare.png
