# File: tests/bdd/features/onboard_git_lfs.feature
# Generated from: specs/122-configure-git-lfs-for-binary-assets-during-consumer-onboarding/requirements.md
Feature: Configure Git LFS during consumer onboarding

  @SCN001
  Scenario: Fresh consumer gets the LFS block
    Given a consumer with no .gitattributes and git-lfs on PATH
    When onboarding installs into the consumer
    Then .gitattributes holds the nmg-game-dev managed block with one LFS line per framework pattern
    And the report prints "installed gitattributes_lfs"

  @SCN002
  Scenario: Consumer lines outside the block are preserved
    Given a consumer whose .gitattributes has its own lines and no managed block
    When onboarding installs into the consumer
    Then the managed block is appended once
    And every original line is kept byte-for-byte

  @SCN003
  Scenario: Re-running onboarding leaves the block unchanged
    Given a consumer that has been onboarded once
    When onboarding installs into the consumer again
    Then .gitattributes is byte-for-byte unchanged
    And the report prints "unchanged gitattributes_lfs"

  @SCN004
  Scenario: An edited block reports drift and refresh restores it
    Given an onboarded consumer whose managed block has been edited
    When onboarding installs into the consumer without --refresh
    Then the report prints "drift gitattributes_lfs" with remediation "re-run with --refresh"
    And .gitattributes is unchanged
    When onboarding installs into the consumer with --refresh
    Then only the managed block is replaced
    And the report prints "refreshed gitattributes_lfs"

  @SCN005
  Scenario: LFS hooks are installed in a git consumer
    Given a consumer that is a git work tree with no LFS pre-push hook
    When onboarding installs into the consumer
    Then "git lfs install --local" runs in the consumer
    And the report prints "installed git_lfs_hooks"
    When onboarding installs into the consumer again
    Then no "git lfs install" runs
    And the report prints "unchanged git_lfs_hooks"

  @SCN006
  Scenario: Missing git-lfs fails preflight
    Given a consumer and git-lfs is not on PATH
    When onboarding installs into the consumer
    Then onboarding fails with "onboard.git_lfs_missing" and remediation "Install Git LFS (brew install git-lfs), then re-run onboarding."
    And no consumer file is written

  @SCN007
  Scenario: A consumer that is not a git repository
    Given a consumer that is not inside a git work tree
    When onboarding installs into the consumer
    Then .gitattributes holds the nmg-game-dev managed block
    And the report prints "skipped git_lfs_hooks: not a git repository"
    And onboarding completes
