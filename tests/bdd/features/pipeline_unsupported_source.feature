Feature: Reject non-Blender pipeline sources (AC2)
  As an internal NMG game developer
  I want pipeline.run to reject any source other than "blender"
  So that no Meshy route or credential is ever used and no work starts for a bad source

  Background:
    Given the artifact cache is rooted at a clean temporary directory
    And the MCP clients are scripted fakes with no real Blender or UE processes

  Scenario Outline: Non-Blender sources are rejected
    Given the Blender MCP fake is reachable
    And the UE MCP fake is reachable
    And a fixture prompt with category "Props", name "TestCrate", tier "standard", description "wooden supply crate"
    When I call pipeline.run with source "<source>"
    Then a PipelineError is raised with code "pipeline.unsupported_source"
    And the error's remediation string names "blender"
    And no MCP fake was called and no cache entry was written

    Examples:
      | source |
      | meshy  |
      | other  |
