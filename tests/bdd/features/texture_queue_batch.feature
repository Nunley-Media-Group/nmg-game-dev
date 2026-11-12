# File: tests/bdd/features/texture_queue_batch.feature
# Generated from: specs/143-make-texture-generation-work-from-the-plugin-root-and-queue-or-batch-texture-jobs/requirements.md
Feature: Texture generation from the plugin root, with queued and batched jobs

  @SCN001
  Scenario: The root project declares the generation dependencies for Apple Silicon
    Given the root pyproject.toml
    When its project dependencies are read
    Then mflux>=0.24.0 and hf_transfer>=0.1.9 are listed as floors with the arm64 macOS marker
    And the texture-ai extra uses the same floors with no exact pin
    And the texture-gen server still depends on nmg-game-dev[texture-ai]

  @SCN002
  Scenario: Missing mlx fails fast with the plugin-root command
    Given an import probe that cannot find mlx
    When a texture request is generated
    Then it fails with texture.dependencies_missing naming mlx and "uv run --project"
    And no worker is spawned and no job is queued
    And the backend status is dependencies_missing

  @SCN003
  Scenario: A worker import failure names the missing module
    Given a worker that exits with "ModuleNotFoundError: No module named 'mlx'"
    When the backend batch runs
    Then texture.worker_failed names mlx and the plugin-root command
    And it does not mention models or the memory reserve

  @SCN004
  Scenario: A second request is queued and runs after the first
    Given a texture job is queued or running
    When another valid request is started
    Then it returns a new job id in state queued
    And the queue runner runs both jobs one at a time in submission order

  @SCN005
  Scenario: A batch through the MCP tool loads each model once
    Given generate_textures called with two requests for the same backend
    When the job runs
    Then that backend's worker is spawned once with both requests' images
    And progress counts every image
    And the result lists two results in request order

  @SCN006
  Scenario: A batch through the CLI prints a combined result
    Given a JSON file with an array of two requests
    When "python -m nmg_game_dev.texture generate --batch <file>" runs
    Then it prints one JSON object with two results

  @SCN007
  Scenario: An invalid batch is rejected whole
    Given a batch whose requests 1 and 3 are invalid
    When it is submitted
    Then texture.invalid_request names requests 1 and 3
    And nothing is generated or queued

  @SCN008
  Scenario: Single requests keep their shape
    Given a single request through the CLI or generate_textures
    When it completes
    Then its parameters and result keys are unchanged
