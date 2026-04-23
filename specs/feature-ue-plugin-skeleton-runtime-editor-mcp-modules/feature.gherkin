# File: tests/bdd/features/ue_plugin_skeleton.feature
#
# Generated from: specs/feature-ue-plugin-skeleton-runtime-editor-mcp-modules/requirements.md
# Issue: #2

Feature: UE plugin skeleton — Runtime + Editor modules
  As an internal NMG game developer
  I want a buildable UE plugin with Runtime and Editor modules
  So that downstream skills have a place to land editor code and shipped games can resolve asset variants

  Background:
    Given the repo-root VERSION file reads "0.2.0"
    And UE 5.7 is installed at the path resolved by UE_ROOT (default /Users/Shared/Epic Games/UE_5.7)
    And fixtures/dogfood.uproject exists from issue #1

  # --- Manifest validity (AC1) ---

  Scenario: Plugin manifest parses cleanly under UE 5.7
    Given the file plugins/nmg-game-dev-ue-plugin/nmg-game-dev.uplugin exists
    When UnrealBuildTool regenerates project files for fixtures/dogfood.uproject
    Then UBT exits 0 with no manifest-parse errors
    And the manifest declares VersionName "0.2.0"
    And the manifest declares EngineVersion "5.7.0"
    And the manifest declares two Modules entries: NmgGameDevRuntime and NmgGameDevEditor
    And NmgGameDevRuntime has Type "Runtime" and LoadingPhase "Default"
    And NmgGameDevEditor has Type "Editor" and LoadingPhase "Default"

  # --- Module load (AC2) ---

  Scenario: Both modules load and emit Initialized lines
    Given fixtures/dogfood.uproject has the nmg-game-dev plugin enabled
    When scripts/start-unreal-mcp.sh launches UE Editor against the dogfood fixture
    And the editor reaches the main UI
    Then the Output Log contains "LogNmgGameDev: Display: NmgGameDevRuntime Initialized v0.2.0"
    And the Output Log contains "LogNmgGameDev: Display: NmgGameDevEditor Initialized v0.2.0"
    And LogModuleManager reports no failures for NmgGameDevRuntime or NmgGameDevEditor

  # --- Cook isolation (AC3) ---

  Scenario: Runtime module cooks; Editor module does NOT cook
    Given the dogfood fixture has the nmg-game-dev plugin enabled
    When a UE Development cook runs for a desktop target (Mac, Win64, or Linux)
    Then the cook completes with exit code 0
    And the cooked output contains the platform-appropriate NmgGameDevRuntime binary
    And the cooked output does NOT contain any NmgGameDevEditor binary
    And the cook log contains zero references to editor-only types from the runtime module

  # --- AssetResolver: variant routing (AC4) ---

  Scenario Outline: AssetResolver routes the parent path to the platform-appropriate variant
    Given an asset exists at /Game/Weapons/Katana/Desktop/Katana.uasset
    And an asset exists at /Game/Weapons/Katana/Mobile/Katana.uasset
    And UGameplayStatics::GetPlatformName returns "<platform>"
    When UNmgAssetResolver::ResolveVariantPath is called with "/Game/Weapons/Katana/Katana"
    Then the returned FSoftObjectPath resolves to "/Game/Weapons/Katana/<variant>/Katana"

    Examples:
      | platform | variant  |
      | Windows  | Desktop  |
      | Mac      | Desktop  |
      | Linux    | Desktop  |
      | IOS      | Mobile   |
      | Android  | Mobile   |

  Scenario: AssetResolver is callable from Blueprint
    Given UNmgAssetResolver is a UBlueprintFunctionLibrary
    Then ResolveVariantPath is exposed as a BlueprintPure UFUNCTION
    And the function appears in Blueprint search under category "nmg-game-dev|Variants"
    And the display name is "Resolve Variant Path"

  # --- AssetResolver: fail-closed (AC5) ---

  Scenario Outline: AssetResolver returns input unchanged + warning on malformed parent path
    Given UGameplayStatics::GetPlatformName returns "Mac"
    When UNmgAssetResolver::ResolveVariantPath is called with "<malformed>"
    Then the returned FSoftObjectPath equals "<malformed>" unchanged
    And the Output Log contains a single LogNmgGameDev warning naming "<malformed>" and the parent-path-convention rule
    And no crash, check failure, or empty FSoftObjectPath occurs

    Examples:
      | malformed                                |
      | /Game/Weapons/Katana/Desktop/Katana      |
      | /Game/Weapons/Katana/Mobile/Katana       |
      | /Game/TooShort                           |
      | /Game/Foo/Bar.Bar_C                      |

  # --- Test runner (AC6) ---

  Scenario: scripts/run-ue-tests.sh runs the Spec tests headlessly
    Given scripts/run-ue-tests.sh is on disk and executable
    And UE_ROOT resolves to a UE 5.7 install
    When scripts/run-ue-tests.sh is invoked from the repo root
    Then the script runs UnrealEditor-Cmd headlessly with -nullrhi -unattended
    And the automation runner executes every test under the prefix "NmgGameDev."
    And the script exits 0 if every test passes
    And tests/ue-automation/results.xml exists and is valid JUnit XML

  Scenario: Test runner surfaces failures with the failing test name
    Given a test under NmgGameDev.Runtime.AssetResolver has been deliberately broken
    When scripts/run-ue-tests.sh is invoked
    Then the script exits non-zero
    And the failing test name is printed to stderr
    And tests/ue-automation/results.xml records the failure as a failed JUnit test case

  # --- Dogfood fixture wiring (AC7) ---

  Scenario: Plugin enabled in the existing dogfood fixture (no second .uproject)
    Given fixtures/dogfood.uproject from issue #1 with an empty Plugins array
    When this issue lands
    Then the same fixtures/dogfood.uproject file exists at the same path
    And its Plugins array contains an entry { "Name": "nmg-game-dev", "Enabled": true }
    And no second .uproject file exists under fixtures/
    And scripts/start-unreal-mcp.sh from issue #1 successfully launches the editor against the updated fixture

  # --- Platform whitelist (AC8) ---

  Scenario: Cookable platforms match steering/tech.md's desktop+mobile target list
    Given the .uplugin manifest at plugins/nmg-game-dev-ue-plugin/nmg-game-dev.uplugin
    When jq is used to inspect each Modules entry's PlatformAllowList
    Then NmgGameDevRuntime PlatformAllowList equals ["Mac", "Win64", "Linux", "IOS", "Android"]
    And NmgGameDevEditor PlatformAllowList equals ["Mac", "Win64", "Linux"]
    And no other platforms (HoloLens, console SDK names) appear in any whitelist
    And no top-level PlatformAllowList exists on the manifest
