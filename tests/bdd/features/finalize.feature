Feature: Finalize an authored asset
  As an NMG game developer
  I want one command, plus each of its steps as an agent tool, that makes an authored asset shippable
  So that freeform authoring ends in a contract-compliant asset in UE

  @SCN001
  Scenario: Finalize runs the six steps from an authored collection
    Given an authored collection "Crate" of class "standard_prop" in category "Props"
    When finalize runs
    Then the steps validate, bake, variants, export, reimport, and import_ue run in that order
    And the result lists each step and the UE content paths under /Game/Props/Crate/

  @SCN003
  Scenario: A single step runs through the same implementation
    Given an authoring session holding "Crate"
    When the agent calls run_finalize_step with step "validate" and wait_seconds 60
    Then it receives a result with step "validate", cache_hit, outputs, and summary

  @SCN004
  Scenario: An unchanged finalized asset is served from cache
    Given "Crate" was finalized and loaded back
    When finalize runs again without changes
    Then every step reports cache_hit true and nothing is reimported into UE
    And after a material change the bake step and every later step run again

  @SCN006
  Scenario: A failing step stops the run before UE import
    Given "Crate" fails contract validation
    When finalize runs
    Then it raises PipelineError "quality.contract_failed" with a remediation
    And no later step runs and nothing is imported into UE
