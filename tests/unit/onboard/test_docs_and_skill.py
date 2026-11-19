"""Onboarding docs and the onboard-consumer skill: links, frontmatter, and required content (#7
AC10, AC11)."""

from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
ONBOARDING = REPO / "docs" / "onboarding"
SKILL = REPO / "skills" / "onboard-consumer" / "SKILL.md"


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    assert match, f"{path} has no frontmatter"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_index_links_every_onboarding_guide() -> None:
    index = (ONBOARDING / "index.md").read_text(encoding="utf-8")
    for guide in ("first-asset.md", "first-ship.md", "upgrading.md", "texture-models.md"):
        assert f"({guide})" in index, guide
        assert (ONBOARDING / guide).is_file()


def test_guides_cover_the_required_topics() -> None:
    asset = (ONBOARDING / "first-asset.md").read_text(encoding="utf-8")
    for topic in (
        "prompt",
        "review",
        "contract",
        "texture",
        "nmg-budgets.json",
        "game/assets/<Category>/<Name>/{Desktop,Mobile}/",
        "NmgAssets.resolve_variant_path",
    ):
        assert topic in asset, topic
    models = (ONBOARDING / "texture-models.md").read_text(encoding="utf-8")
    for topic in (
        "Apple Silicon",
        "TEXTURE_GEN_MODELS_DIR",
        "HF_HOME",
        "/onboard-consumer",
        "generate_textures",
        "get_texture_job",
        "_compare.png",
        "SourceArt/Textures/Generated",
        "textures.json",
        "_N",
    ):
        assert topic in models, topic
    ship = (ONBOARDING / "first-ship.md").read_text(encoding="utf-8")
    assert "ship" in ship and "fixture" in ship
    upgrading = (ONBOARDING / "upgrading.md").read_text(encoding="utf-8")
    for topic in ("BREAKING CHANGE", "/plugin install nmg-game-dev@nmg-plugins", "--refresh"):
        assert topic in upgrading, topic


def test_index_links_the_conversion_guide() -> None:
    """#249: the onboarding index links the /convert-to-godot guide, and the guide exists."""
    index = (ONBOARDING / "index.md").read_text(encoding="utf-8")
    assert "(../skills/convert-to-godot.md)" in index
    assert (REPO / "docs" / "skills" / "convert-to-godot.md").is_file()


def test_docs_and_skill_describe_the_godot_setup() -> None:
    """#249 AC10: the skill, install steps, and index name the Godot steps and tool checks."""
    steps = (SKILL.parent / "references" / "install-steps.md").read_text(encoding="utf-8")
    for topic in (
        "godot_project",
        "godot_addon",
        "export_presets",
        "godot_binary",
        "ffmpeg_binary",
        "gl_compatibility",
        "game/.godot/",
        "--game-dir",
    ):
        assert topic in steps, topic
    skill = SKILL.read_text(encoding="utf-8")
    for topic in ("game/project.godot", "GODOT_BIN", "FFMPEG_BIN", "--game-dir"):
        assert topic in skill, topic
    template = json.loads(
        (REPO / "templates" / "consumer" / ".claude" / "settings.json").read_text()
    )
    commands = [h["command"] for g in template["hooks"]["SessionStart"] for h in g["hooks"]]
    assert commands == ['bash "$CLAUDE_PROJECT_DIR/scripts/start-blender-mcp.sh"']


def test_claude_readme_and_template_readme_link_the_index() -> None:
    for relative in ("CLAUDE.md", "README.md", "templates/consumer/README.md"):
        text = (REPO / relative).read_text(encoding="utf-8")
        assert "docs/onboarding/index.md" in text, relative


def test_skill_frontmatter_matches_the_contract() -> None:
    fields = _frontmatter(SKILL)
    assert fields["name"] == "onboard-consumer"
    assert fields["description"] and "\n" not in fields["description"]
    assert fields["required_mcp"] == "[]"
    assert fields["required_env"].startswith("[") and fields["required_env"].endswith("]")
    assert fields["unattended_safe"] == "true"


def test_skill_flow_runs_the_install_and_asks_the_disk() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "python -m nmg_game_dev.onboard install" in text
    assert "AskUserQuestion" in text and "fits_models" in text
    assert "NMG_SDLC_AUTOPILOT=1" in text and "TEXTURE_GEN_MODELS_DIR" in text
    assert "--refresh" in text
    assert (SKILL.parent / "references" / "install-steps.md").is_file()


def test_git_lfs_docs_and_skill_cover_the_new_steps() -> None:
    """#122 FR8: the step and preflight tables, the status list, the two error codes, and the
    conversion guidance name the Git LFS steps."""
    steps = (SKILL.parent / "references" / "install-steps.md").read_text(encoding="utf-8")
    for topic in (
        "onboard.git_lfs_missing",
        "gitattributes_lfs",
        "git_lfs_hooks",
        "git lfs install --local",
        "not a git repository",
    ):
        assert topic in steps, topic
    skill = SKILL.read_text(encoding="utf-8")
    for topic in ("skipped", "onboard.git_lfs_missing", "onboard.git_lfs_hooks_failed"):
        assert topic in skill, topic
    index = (ONBOARDING / "index.md").read_text(encoding="utf-8")
    for topic in ("Git LFS", "git add --renormalize .", "git lfs migrate"):
        assert topic in index, topic


def test_changelog_has_both_unreleased_entries_ending_with_issue() -> None:
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    # The entries start under [Unreleased]; each release bump pushes them down into
    # a versioned section, so read whichever section holds the #7 bullets.
    sections = text.split("## [Unreleased]", 1)[1].split("## [")
    section = next(part for part in sections if "(#7)" in part)
    bullets = [line for line in section.splitlines() if line.startswith("- ")]
    assert len(bullets) == 2
    assert all(line.rstrip().endswith("(#7)") for line in bullets)
    assert "onboard" in bullets[0].lower() and "texture" in bullets[1].lower()


def test_run_and_capture_docs_cover_launch_options_smoke_and_screenshots() -> None:
    """FR7 (#251): the launch options, smoke gate, and screenshot are documented where they ship."""
    guide = (ONBOARDING / "run-and-capture.md").read_text(encoding="utf-8")
    for topic in (
        "NmgLaunch",
        "get_option",
        "has_option",
        "autoplay_requested",
        "save_dir()",
        "user://nmg-test/",
        "--nmg-autoplay",
        "--nmg-test-saves",
        "#hour=12&at=Forest",
        "smoke passed (600 frames)",
        "smoke.runtime_error",
        "smoke.timeout",
        "--nmg-shot",
        "game_screenshot",
        "shot.no_image",
    ):
        assert topic in guide, topic
    index = (ONBOARDING / "index.md").read_text(encoding="utf-8")
    assert "(run-and-capture.md)" in index
    ship_skill = (REPO / "skills" / "ship" / "SKILL.md").read_text(encoding="utf-8")
    ship_doc = (REPO / "docs" / "skills" / "ship.md").read_text(encoding="utf-8")
    for text in (ship_skill, ship_doc, (ONBOARDING / "first-ship.md").read_text(encoding="utf-8")):
        assert "ship.smoke_failed" in text
    assert "--nmg-autoplay" in ship_skill
    finalize_doc = (REPO / "docs" / "mcp" / "finalize.md").read_text(encoding="utf-8")
    assert "game_screenshot" in finalize_doc and "shot.invalid_after" in finalize_doc
    install = (REPO / "skills" / "onboard-consumer" / "references" / "install-steps.md").read_text(
        encoding="utf-8"
    )
    assert 'NmgLaunch="*res://addons/nmg_game_dev/nmg_launch.gd"' in install
