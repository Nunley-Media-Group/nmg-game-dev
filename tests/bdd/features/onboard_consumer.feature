Feature: Onboard a consumer game project

  @SCN001
  Scenario: Fresh onboarding installs the framework files
    Given a consumer with Game.uproject, unrelated Claude settings, and a CLAUDE.md
    When onboarding installs into the consumer
    Then both start scripts are in the consumer scripts folder and executable
    And the SessionStart hooks are merged and the unrelated settings are unchanged
    And the asset contract is installed and CLAUDE.md references it once
    And no .mcp.json, fixtures file, or _API_KEY variable is written

  @SCN002
  Scenario: Unreal plugins are installed and enabled
    Given a consumer with Game.uproject and git available
    When onboarding installs into the consumer
    Then the nmg-game-dev UE plugin is in Plugins/nmg-game-dev
    And VibeUE is cloned at tag v5.0-ue5.8 into Plugins/VibeUE
    And Game.uproject enables ModelContextProtocol, EditorToolset, VibeUE, and nmg-game-dev
    And the MCP settings section has bAutoStartServer=True and ServerPortNumber=8000

  @SCN003
  Scenario: The Blender add-on is linked into Blender's extensions
    Given BLENDER_EXTENSIONS_DIR points at an empty directory
    When onboarding installs into the consumer
    Then nmg_game_dev_blender_addon in that directory links to the framework add-on

  @SCN004
  Scenario: Local texture models are installed on the chosen disk
    Given a models directory on a volume with 60 GiB free on Apple Silicon macOS
    When onboarding installs into the consumer
    Then mflux-save saves z-image-turbo and then flux2-klein-4b with --quantize 4 into the models directory
    And HF_HOME is the hf-cache folder in the models directory
    And settings.local.json records TEXTURE_GEN_MODELS_DIR and HF_HOME

  @SCN005
  Scenario: Texture prerequisites fail before anything changes
    Given a models directory on a volume with 10 GiB free
    When onboarding installs into the consumer
    Then it exits 1 with code "onboard.insufficient_disk" and a remediation
    And no consumer file was created or changed

  @SCN006
  Scenario: The skill asks which disk to use
    Given mounted volumes with different free space
    When the volumes command runs
    Then it lists each volume with free bytes and whether it fits the models
    And the onboard-consumer skill asks the developer to choose a qualifying volume

  @SCN007
  Scenario: Install scope does not change the result
    Given two copies of the framework root in different directories
    When each onboards an identical fresh consumer
    Then the consumer trees are identical apart from the Blender link target

  @SCN008
  Scenario: Re-running is idempotent
    Given a consumer that has already been onboarded
    When onboarding installs into the consumer again
    Then no hook, plugin entry, ini key, or CLAUDE.md block is duplicated
    And no git clone or mflux-save runs and the command exits 0

  @SCN009
  Scenario: Drift is reported and --refresh repairs it
    Given an onboarded consumer with an edited start-blender-mcp.sh and an nmg-budgets.json
    When onboarding installs into the consumer again
    Then start-blender-mcp.sh is reported as drift with a "re-run with --refresh" remediation and left unchanged
    When onboarding installs into the consumer with --refresh
    Then start-blender-mcp.sh matches the framework copy
    And nmg-budgets.json is unchanged

  @SCN010
  Scenario: Onboarding docs exist and are linked
    Given the repository
    When docs/onboarding is read
    Then index.md links to first-asset.md, first-ship.md, upgrading.md, and texture-models.md
    And CLAUDE.md and README.md link to docs/onboarding/index.md

  @SCN011
  Scenario: The onboard-consumer skill is the entry point
    Given the plugin checkout
    When skills/onboard-consumer/SKILL.md is parsed
    Then its frontmatter has name "onboard-consumer", a description, required_mcp, required_env, and unattended_safe true
    And its flow runs "python -m nmg_game_dev.onboard install"
