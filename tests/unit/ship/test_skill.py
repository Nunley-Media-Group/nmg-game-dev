"""AC11: skills/ship/SKILL.md is the single Claude Code entry point (#6)."""

from __future__ import annotations

from tests.ship_fakes import REPO_ROOT, parse_frontmatter

SKILL = REPO_ROOT / "skills" / "ship" / "SKILL.md"


def test_frontmatter_declares_the_ac11_fields() -> None:
    fields = parse_frontmatter(SKILL.read_text(encoding="utf-8"))
    assert fields["name"] == "ship"
    assert fields["description"]
    assert "\n" not in fields["description"]
    assert fields["required_mcp"] == "[]"
    assert fields["required_env"].startswith("[")
    assert "NOTARIZATION_TEAM_ID" in fields["required_env"]
    assert fields["unattended_safe"] == "true"


def test_flow_invokes_the_ship_cli_and_lists_the_failure_codes() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert "python -m nmg_game_dev.ship" in text
    assert 'uv run --project "${CLAUDE_PLUGIN_ROOT}"' in text
    for code in ("ship.env_missing", "ship.mobile_budget_exceeded", "ship.cook_manifest_failed"):
        assert code in text


def test_the_skill_directory_is_named_for_its_skill() -> None:
    assert SKILL.parent.name == "ship"
    assert (SKILL.parent / "SKILL.md").is_file()
