Feature: Idempotent re-entry at a partial failure point (AC3)
  As an internal NMG game developer
  I want a re-run to resume from the first uncompleted stage
  So that expensive upstream MCP calls are not repeated

  Background:
    Given the artifact cache is rooted at a clean temporary directory
    And the MCP clients are scripted fakes with no real Blender, UE, or Meshy processes

  Scenario: Idempotent re-entry at a partial failure point
    Given a prior pipeline.run attempt succeeded through generate, texture, and cleanup
    And the prior attempt failed at the variants stage
    And the artifact cache retains the generate, texture, and cleanup artifacts
    And a fixture prompt with category "Props", name "ResumeCrate", tier "standard", description "a crate used to exercise idempotent resume"
    When I call pipeline.run with the same prompt and source "blender"
    Then the generate, texture, and cleanup stages are served from cache
    And the variants, quality, and import_ue stages execute
    And result.cache_hits equals ["generate", "texture", "cleanup"]
    And result.stages_executed equals ["variants", "quality", "import_ue"]
    And the Blender MCP fake was not invoked for the cached stages
