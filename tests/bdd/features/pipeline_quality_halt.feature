Feature: Quality gate failure halts the run with remediation (AC4)
  As an internal NMG game developer
  I want the pipeline to fail fast with a PipelineError when quality checks fail
  So that no partial asset is imported into UE

  Background:
    Given the artifact cache is rooted at a clean temporary directory
    And the MCP clients are scripted fakes with no real Blender, UE, or Meshy processes

  Scenario: Quality gate failure halts the run with remediation
    Given the Blender MCP fake is reachable
    And the UE MCP fake is reachable
    And the variants stage is configured to produce a mobile variant that exceeds its poly budget
    And a fixture prompt with category "Props", name "OverBudgetCrate", tier "standard", description "a crate intentionally over mobile budget"
    When I call pipeline.run with source "blender"
    Then a PipelineError is raised with code "quality.mobile_budget_exceeded"
    And the error's remediation string mentions the failing mobile poly budget
    And the import_ue stage is never invoked
    And no partial asset is written under the consumer Content/ tree
