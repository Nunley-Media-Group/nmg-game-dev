Feature: Run a Meshy-supplement pipeline end-to-end (AC2)
  As an internal NMG game developer
  I want to run pipeline.run with source "meshy"
  So that generation happens via Meshy and all other stages use Blender + UE

  Background:
    Given the artifact cache is rooted at a clean temporary directory
    And the MCP clients are scripted fakes with no real Blender, UE, or Meshy processes

  Scenario: Run a Meshy-supplement pipeline end-to-end on a fixture
    Given the Meshy MCP fake is reachable
    And the Blender MCP fake is reachable
    And the UE MCP fake is reachable
    And a fixture prompt with category "Guards", name "Patrol", tier "hero", description "futuristic patrol guard"
    When I call pipeline.run with source "meshy"
    Then the generate stage called the Meshy MCP fake exactly once
    And the cleanup, variants, and quality stages called the Blender MCP fake
    And the import_ue stage called the UE MCP fake exactly once
    And the result's desktop_path ends with "Content/Guards/Patrol/Desktop/"
    And the result's mobile_path ends with "Content/Guards/Patrol/Mobile/"
