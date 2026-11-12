# File: tests/bdd/features/start_unreal_plugin_relaunch.feature
# Generated from: specs/150-fix-start-unreal-mcp-sh-rebuilding-plugins-on-every-launch-and-failing-to-relaunch-the-editor-after-a-config-change/requirements.md
Feature: start-unreal-mcp.sh relaunches the editor without needless or broken plugin builds

  @SCN001 @regression
  Scenario: A config change does not trigger a build
    Given a project whose plugin "Fake" has a libUnrealEditor-FakeEditor.dylib newer than its sources
    And the project's Config/DefaultEngine.ini is newer than that binary
    When start-unreal-mcp.sh runs
    Then Build.sh does not run
    And the editor launches

  @SCN002 @regression
  Scenario Outline: The plugin build selects a single editor target
    Given a <kind> project whose plugin "Fake" has no editor binary
    When start-unreal-mcp.sh runs
    Then Build.sh runs with Mac Development -Project=<uproject> -TargetType=Editor -NoEngineChanges
    And Build.sh receives no UnrealEditor target name

    Examples:
      | kind           |
      | Blueprint-only |
      | code           |

  @SCN003 @regression
  Scenario: Current UE 5.8 binaries skip the build
    Given a project whose plugin "Fake" has a libUnrealEditor-FakeEditor.dylib newer than its sources
    When start-unreal-mcp.sh runs
    Then Build.sh does not run
    And the editor launches

  @SCN004 @regression
  Scenario: A change to one module does not mark the plugin stale
    Given a project whose plugin "Fake" has modules A and B
    And module A's binary is newer than module A's sources and older than module B's sources
    And module B's binary is newer than module B's sources
    When start-unreal-mcp.sh runs
    Then Build.sh does not run
    And the editor launches

  @SCN005 @regression
  Scenario: A failed rebuild with existing binaries still launches
    Given a project whose plugin "Fake" has a libUnrealEditor-FakeEditor.dylib older than its sources
    And Build.sh prints "Result: Failed (ActionGraphInvalid)" and exits 9
    When start-unreal-mcp.sh runs
    Then it exits 0
    And stderr warns that the plugin build failed, names /tmp/unreal-mcp-build.log, and says the editor starts on the existing plugin binaries
    And the editor launches after the build

  @SCN006 @regression
  Scenario: A failed build with a missing binary stops the launch
    Given a project whose plugin "Fake" has no editor binary
    And Build.sh prints "Result: Failed (ActionGraphInvalid)" and exits 9
    When start-unreal-mcp.sh runs
    Then it exits non-zero
    And the editor does not launch
    And stderr names /tmp/unreal-mcp-build.log

  @SCN007 @regression
  Scenario: The failure report shows UnrealBuildTool's reason
    Given a project whose plugin "Fake" has no editor binary
    And Build.sh prints "Action graph is invalid; unable to continue" then "Result: Failed (ActionGraphInvalid)" and exits 9
    When start-unreal-mcp.sh runs
    Then stderr contains "Result: Failed (ActionGraphInvalid)"
    And stderr does not contain "no compiler error found"
