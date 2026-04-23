Feature: Run a Blender-first pipeline end-to-end (AC1)
  As an internal NMG game developer
  I want to run pipeline.run with source "blender"
  So that all six stages execute in order and Desktop + Mobile paths are returned

  Background:
    Given the artifact cache is rooted at a clean temporary directory
    And the MCP clients are scripted fakes with no real Blender, UE, or Meshy processes

  Scenario: Run a Blender-first pipeline end-to-end on a fixture
    Given the Blender MCP fake is reachable
    And a fixture prompt with category "Props", name "TestCrate", tier "standard", description "wooden supply crate"
    When I call pipeline.run with source "blender"
    Then the stages execute in order: generate, texture, cleanup, variants, quality, import_ue
    And the result's desktop_path ends with "Content/Props/TestCrate/Desktop/"
    And the result's mobile_path ends with "Content/Props/TestCrate/Mobile/"
    And result.stages_executed contains all six stage names
    And result.cache_hits is empty
