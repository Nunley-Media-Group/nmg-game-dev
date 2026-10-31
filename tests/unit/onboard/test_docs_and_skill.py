"""Onboarding docs and the onboard-consumer skill: links, frontmatter, and required content (#7
AC10, AC11)."""

from __future__ import annotations

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
        "Content/<Category>/<Name>/{Desktop,Mobile}/",
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


def test_changelog_has_both_unreleased_entries_ending_with_issue() -> None:
    text = (REPO / "CHANGELOG.md").read_text(encoding="utf-8")
    # The entries start under [Unreleased]; the release bump moves them into the
    # first versioned section, so read whichever of the two holds the #7 bullets.
    sections = text.split("## [Unreleased]", 1)[1].split("## [")
    unreleased, first_release = sections[0], sections[1] if len(sections) > 1 else ""
    section = unreleased if "(#7)" in unreleased else first_release
    bullets = [line for line in section.splitlines() if line.startswith("- ")]
    assert len(bullets) == 2
    assert all(line.rstrip().endswith("(#7)") for line in bullets)
    assert "onboard" in bullets[0].lower() and "texture" in bullets[1].lower()
