"""Contract for the /generate-audio skill: frontmatter, one take, instrumental music, prompts.

FR1 (frontmatter and flow), AC5 (music is instrumental unless vocals come with lyrics), and AC6
(prompts come only from the brief, one take, import_audio). The hook that enforces one take is
covered by tests/unit/test_generate_audio_guard_hook.py.
"""

from __future__ import annotations

from tests.ship_fakes import REPO_ROOT, parse_frontmatter

SKILL = REPO_ROOT / "skills" / "generate-audio" / "SKILL.md"

# Body phrases the contract requires. Each must appear in the SKILL.md body.
REQUIRED_PHRASES = [
    "creative_get_model_schema",
    "instrumental",
    "lyrics",
    "creative_get_model_guide",
    "docs/design/systems/audio.md",
    "generations_count: 1",
    "import_audio",
    "Add no genre, instrument, mood, or vocal element",
]


def _text() -> str:
    return SKILL.read_text(encoding="utf-8")


def _flow(text: str) -> str:
    start = text.index("## Flow")
    end = text.index("## Failure modes and remediation")
    return text[start:end]


def _failure_modes(text: str) -> str:
    start = text.index("## Failure modes and remediation")
    end = text.index("## Test fixtures")
    return text[start:end]


def test_frontmatter_declares_the_fr1_contract() -> None:
    """FR1: name, a one-line trigger description, the MCPs, no env, and autonomy."""
    text = _text()
    fields = parse_frontmatter(text)
    assert fields["name"] == "generate-audio"
    description = fields["description"]
    assert description
    assert "\n" not in description
    # A colon followed by a space ends a YAML plain scalar, so the frontmatter would not parse.
    assert ": " not in description
    assert "ElevenLabs" in description
    assert "sound effect" in description
    assert "music" in description
    assert "speech" in description
    assert fields["required_mcp"] == "[elevenlabs, finalize]"
    assert fields["required_env"] == "[]"
    assert fields["unattended_safe"] == "true"


def test_body_carries_the_required_rules() -> None:
    """AC5, AC6: the body names the schema, guide, instrumental, lyrics, one take, and import."""
    text = _text()
    for phrase in REQUIRED_PHRASES:
        assert phrase in text, f"SKILL.md does not contain {phrase!r}"


def test_flow_reads_the_schema_before_generating() -> None:
    """AC5: the model schema, and its instrumental option, are read before any generation call."""
    flow = _flow(_text())
    schema = flow.index("creative_get_model_schema")
    instrumental = flow.index("instrumental")
    generate = flow.index("Generate and wait")
    assert schema < generate
    assert instrumental < generate


def test_music_is_instrumental_unless_vocals_come_with_lyrics() -> None:
    """AC5: instrumental stays set unless vocals are asked for with lyrics; then only lyrics."""
    flow = _flow(_text())
    assert "unless the developer explicitly asked for vocals and supplied lyrics" in flow
    assert "only the developer's lyrics" in flow


def test_prompt_comes_only_from_the_brief() -> None:
    """AC6: the prompt is built from the request and the design-doc entry, and nothing else."""
    flow = _flow(_text())
    read_brief = flow.index("Read the brief")
    write_prompt = flow.index("Write the prompt")
    assert read_brief < write_prompt
    assert "docs/design/systems/audio.md" in flow
    assert "Add no genre, instrument, mood, or vocal element" in flow


def test_flow_takes_one_take_then_downloads_and_imports() -> None:
    """AC6: one take on every call, then the download and import_audio step, in that order."""
    flow = _flow(_text())
    one_take = flow.index("generations_count: 1")
    download = flow.index("Download and import")
    assert one_take < download
    assert "import_audio" in flow[download:]
    assert "PascalCase" in flow[download:]


def test_failure_modes_cover_the_denial_and_the_missing_brief() -> None:
    """FR1: a denied call is retried once at 1, and a missing design entry adds nothing."""
    failures = _failure_modes(_text())
    assert "generations_count: 1" in failures
    assert "retry it once" in failures
    assert "design docs have no entry" in failures
    assert "add nothing" in failures
