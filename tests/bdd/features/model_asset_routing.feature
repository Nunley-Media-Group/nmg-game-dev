# File: tests/bdd/features/model_asset_routing.feature
#
# Generated from: specs/130-route-blender-asset-authoring-to-model-asset-automatically/requirements.md
# Issue: #130

Feature: Route Blender asset authoring to /model-asset

  @SCN001 @regression
  Scenario: The skill description states its trigger
    Given the frontmatter of skills/model-asset/SKILL.md
    When its description is read
    Then it is one line that says the skill is used whenever creating or changing an asset's geometry or materials in Blender
    And it contains "freeform" and "Blender MCP"

  @SCN002 @regression
  Scenario: Onboarding refreshes the block with the /model-asset routing
    Given a consumer CLAUDE.md holding the 0.21.0 nmg-game-dev block
    When onboarding writes the agent-instructions block
    Then the step reports "refreshed"
    And the block tells the agent to run /model-asset for asset authoring or editing in Blender
    And the block exempts scene inspection and /finalize-asset

  @SCN003 @regression
  Scenario: The first execute_blender_code call in a session gets the reminder
    Given an empty hook state directory
    When the reminder hook receives an execute_blender_code PreToolUse event for session "s-1"
    Then it exits 0
    And its additionalContext tells Claude to use /model-asset and exempts inspection and /finalize-asset
    And it makes no permission or block decision

  @SCN004 @regression
  Scenario: Later calls in the same session stay silent
    Given the reminder hook has already reminded session "s-1"
    When it receives another execute_blender_code event for session "s-1"
    Then it exits 0 with no output
    And an event for session "s-2" receives the reminder

  @SCN005 @regression
  Scenario: Existing behavior is kept and the hook fails open
    Given the onboarding block and the reminder hook
    When the block is generated and the hook receives invalid JSON, an event without a session id, or an unwritable state directory
    Then the block still links the asset contract and the design contract
    And the hook exits 0 with no output in each case
