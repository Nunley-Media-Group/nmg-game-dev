# File: tests/bdd/features/start_unreal_plugin_build.feature
# Generated from: specs/103-build-missing-project-plugin-binaries-before-start-unreal-mcp-sh-launches-the-editor/requirements.md
Feature: start-unreal-mcp.sh builds missing project plugin binaries before launch

  @SCN001
  Scenario: Missing plugin binaries are built before the editor launches
    Given a project whose plugin "Fake" has Source/ but no Binaries/Mac/UnrealEditor-FakeEditor.dylib
    When start-unreal-mcp.sh runs
    Then it logs that it is building project plugins (Fake)
    And Build.sh runs with UnrealEditor Mac Development -Project=<uproject> -TargetType=Editor -NoEngineChanges
    And the editor launches after the build succeeds

  @SCN002
  Scenario: Current plugin binaries skip the build
    Given a project whose plugin "Fake" has an editor dylib newer than its sources
    When start-unreal-mcp.sh runs
    Then the editor launches
    And Build.sh does not run

  @SCN003
  Scenario: A failed plugin build stops the launch
    Given a project whose plugin "Fake" needs a build
    And Build.sh prints "Foo.cpp:3:1: error: boom" and exits 2
    When start-unreal-mcp.sh runs
    Then it exits non-zero
    And the editor does not launch
    And stderr names /tmp/unreal-mcp-build.log and "Foo.cpp:3:1: error: boom"

  @SCN004
  Scenario: A missing Build.sh is reported
    Given a project whose plugin "Fake" needs a build
    And UE_ROOT has no Engine/Build/BatchFiles/Mac/Build.sh
    When start-unreal-mcp.sh runs
    Then it exits non-zero without launching the editor
    And stderr names the missing Build.sh path and UE_ROOT

  @SCN005
  Scenario: Onboarding gives the Unreal hook room to build
    Given a consumer settings.json whose start-unreal-mcp.sh hook has no timeout
    When the SessionStart hooks are merged
    Then the start-unreal-mcp.sh hook has timeout 900
    And the merge reports refreshed
