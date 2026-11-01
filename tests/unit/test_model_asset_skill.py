"""The /model-asset skill's contract: frontmatter, Flow order, and consumer docs (#127).

SCN001 (AC1), SCN002 (AC2), SCN008 (AC8). The Blender-side behavior is covered under
tests/blender/ and runs only through scripts/run-blender-tests.sh.
"""

from __future__ import annotations

import re

from tests.ship_fakes import REPO_ROOT, parse_frontmatter

SKILL = REPO_ROOT / "skills" / "model-asset" / "SKILL.md"
DOC = REPO_ROOT / "docs" / "skills" / "model-asset.md"
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

# The Flow's steps, in the order AC2 requires. Each marker must appear once, after the previous one.
FLOW_ORDER = [
    "Inspect the scene",
    "Plan the asset",
    "generating script",
    "Block out",
    "inspect_asset",
    "Fix the blocking findings",
    "Add detail and materials",
    "Present the result",
]
ASSET_TYPE_NOUNS = re.compile(
    r"\b(chair|table|sword|crate|barrel|lamp|tree|house|door)s?\b", re.IGNORECASE
)
WAITING_PHRASES = ("wait for the developer", "ask the developer", "developer approv")


def _flow(text: str) -> str:
    start = text.index("## Flow")
    end = text.index("## Failure modes and remediation")
    return text[start:end]


def test_frontmatter_declares_the_ac1_contract() -> None:
    """SCN001: name, one-line description naming freeform Blender MCP work, mcp, and autonomy."""
    fields = parse_frontmatter(SKILL.read_text(encoding="utf-8"))
    assert fields["name"] == "model-asset"
    description = fields["description"]
    assert description
    assert "\n" not in description
    assert "freeform" in description
    assert "Blender MCP" in description
    assert fields["required_mcp"] == "[blender]"
    assert fields["unattended_safe"] == "true"


def test_flow_runs_the_loop_in_order_without_waiting() -> None:
    """SCN002: the Flow lists the loop steps in order and has no approval wait."""
    text = SKILL.read_text(encoding="utf-8")
    flow = _flow(text)
    positions = []
    for marker in FLOW_ORDER:
        assert flow.count(marker) >= 1, f"Flow is missing the step marker {marker!r}"
        positions.append(flow.index(marker))
    assert positions == sorted(positions), f"Flow steps are out of order: {FLOW_ORDER}"

    lowered = flow.lower()
    for phrase in WAITING_PHRASES:
        assert phrase not in lowered, f"Flow waits on the developer: {phrase!r}"


def test_flow_reviews_with_the_renders_and_the_inspection() -> None:
    """SCN002: the review step names inspect_asset, render_review, and look together."""
    flow = _flow(SKILL.read_text(encoding="utf-8"))
    review = flow[flow.index("Inspect and review") :]
    review = review[: review.index("\n6.")]
    for name in ("inspect_asset", "render_review", "look"):
        assert name in review, f"the inspection step does not name {name}"


def test_skill_names_no_asset_type() -> None:
    """SCN002: the skill stays asset-type agnostic."""
    assert ASSET_TYPE_NOUNS.search(SKILL.read_text(encoding="utf-8")) is None
    reference = REPO_ROOT / "skills" / "model-asset" / "references" / "blender-api.md"
    assert ASSET_TYPE_NOUNS.search(reference.read_text(encoding="utf-8")) is None


def test_failure_modes_name_the_required_codes() -> None:
    """AC1/FR1: the skill documents the codes its loop can raise."""
    text = SKILL.read_text(encoding="utf-8")
    for code in (
        "inspect.collection_missing",
        "inspect.unknown_asset_class",
        "mcp.blender.unreachable",
    ):
        assert code in text, f"SKILL.md does not document {code}"


def test_consumer_doc_names_the_loop_rules_and_codes() -> None:
    """SCN008: the doc names the four blocking rules and both inspect.* codes."""
    text = DOC.read_text(encoding="utf-8")
    for rule in ("floating", "non_manifold", "over_budget", "interpenetration"):
        assert f"`{rule}`" in text, f"the doc does not name the {rule} rule"
    assert re.search(r"`interpenetration`\s*\|\s*No\b", text), "interpenetration must not block"
    for rule in ("floating", "non_manifold", "over_budget"):
        assert re.search(rf"`{rule}`\s*\|\s*Yes\b", text), f"{rule} must block"
    for code in ("inspect.collection_missing", "inspect.unknown_asset_class"):
        assert code in text, f"the doc does not name {code}"
    for field in ("passed", "headroom", "non_manifold_edges", "gap_tolerance"):
        assert f"`{field}`" in text, f"the doc does not describe the {field} field"


def test_changelog_cites_127_under_added() -> None:
    """SCN008: the changelog has an Added entry for the skill, citing #127.

    The entry starts under [Unreleased]; the release bump moves it into a versioned section,
    so read whichever section holds the #127 bullet.
    """
    text = CHANGELOG.read_text(encoding="utf-8")
    sections = text.split("## [Unreleased]", 1)[1].split("\n## [")
    section = next(part for part in sections if "(#127)" in part)
    assert "### Added" in section
    assert "/model-asset" in section
