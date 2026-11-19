# File: tests/bdd/features/godot_gate_required_tests.feature
# Generated from: specs/297-require-254-s-godot-build-tests-in-the-headless-godot-gate/requirements.md
Feature: Require the NmgBuild tests in the headless Godot gate

  @SCN001
  Scenario: Every build test is required
    Given scripts/run-godot-tests.sh and test_nmg_build.gd
    When the required_tests array is read
    Then it lists every test_* function in test_nmg_build.gd

  @SCN002
  Scenario: A missing build test fails the gate
    Given a Godot add-on test run with no PASS line for one test_nmg_build.gd test
    When scripts/run-godot-tests.sh runs
    Then it exits 5
    And stderr names the missing test_nmg_build.gd test
