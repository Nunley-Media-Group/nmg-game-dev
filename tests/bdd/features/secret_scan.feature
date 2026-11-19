# File: tests/bdd/features/secret_scan.feature
# Generated from: specs/255-block-commits-and-builds-that-contain-api-keys-in-consumer-projects/requirements.md
Feature: Block API keys from commits and builds

  @SCN001
  Scenario Outline: A commit containing a key is blocked
    Given an onboarded consumer git repository
    And a staged file containing a <kind> key
    When the pre-commit hook runs
    Then it exits 1 and prints the file, line, pattern "<pattern>", the value masked to its first 4 characters, and its fingerprint
    And the unmasked value does not appear in the output

    Examples:
      | kind               | pattern     |
      | Meshy              | meshy       |
      | ElevenLabs         | elevenlabs  |
      | Anthropic          | anthropic   |
      | OpenAI             | openai      |
      | GitHub             | github      |
      | AWS                | aws         |
      | PEM private key    | private-key |
      | staged .env file   | env-file    |

  @SCN002
  Scenario: A clean commit passes silently
    Given an onboarded consumer git repository with a staged file containing no key
    When the pre-commit hook runs
    Then it exits 0 with no output

  @SCN003
  Scenario: False positives can be allowed
    Given a staged file with two Meshy-pattern matches
    And .nmg/secret-scan-allow lists the first match's fingerprint
    When the scan runs
    Then only the second match is reported

  @SCN004
  Scenario: /ship refuses to build with a key in tracked files
    Given a consumer whose tracked file contains an AWS key
    When "/ship macos --dry-run" runs
    Then it stops with "ship.secret_found" listing the masked match
    And no Godot command ran

  @SCN005
  Scenario Outline: Onboarding installs the hook safely
    Given a consumer git repository with <existing>
    When onboarding runs
    Then the precommit_hook step is "<status>"
    And a foreign hook is left byte-identical

    Examples:
      | existing                  | status    |
      | no pre-commit hook        | installed |
      | the nmg pre-commit hook   | unchanged |
      | a foreign pre-commit hook | conflict  |
