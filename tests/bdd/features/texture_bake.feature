Feature: Finalize bake step bakes authored materials through the one bake implementation (AC5, AC6 of #67)
  As an NMG game developer
  I want the finalize bake step to run the one bake implementation
  So that its outputs and its failures match the operator's result

  Scenario: The bake step outputs carry the texture paths, byte totals, proof, and summary
    Given an authored collection "Crate" of class "standard_prop" in category "Props"
    And the Blender runner returns a successful bake for "Crate"
    When the bake step runs
    Then the bake outputs carry the Desktop and Mobile texture paths
    And the bake outputs carry the texture byte totals, proof metrics, and summary

  Scenario: A material the bake cannot represent raises PipelineError for the bake step
    Given an authored collection "Crate" of class "standard_prop" in category "Props"
    And the Blender runner reports a texture.bake_failed error for a material with alpha 0.5
    When the bake step runs
    Then a PipelineError is raised with code "bake.texture.bake_failed" and stage "bake"
    And the PipelineError remediation names the transparency fix
