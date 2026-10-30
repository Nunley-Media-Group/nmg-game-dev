Feature: Texture stage bakes authored materials through the Blender MCP (AC5, AC6)
  As an NMG game developer
  I want the pipeline texture stage to run the one bake implementation
  So that its sidecar and its failures match the operator's result

  Scenario: The texture stage sidecar carries the texture paths, byte totals, proof, and summary
    Given a fixture prompt with category "Props", name "Crate", tier "standard", description "a supply crate"
    And the Blender MCP fake returns a successful bake for "Crate"
    When the texture stage runs
    Then the texture sidecar carries the Desktop and Mobile texture paths
    And the texture sidecar carries the texture byte totals, proof metrics, and summary

  Scenario: A material the bake cannot represent raises PipelineError for the texture stage
    Given a fixture prompt with category "Props", name "Crate", tier "standard", description "a supply crate"
    And the Blender MCP fake reports a texture.bake_failed error for a material with alpha 0.5
    When the texture stage runs
    Then a PipelineError is raised with code "texture.bake_failed" and stage "texture"
    And the PipelineError remediation names the transparency fix
