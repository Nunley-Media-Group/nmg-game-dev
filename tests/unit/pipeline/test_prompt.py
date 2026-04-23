"""Unit tests for the Prompt pydantic model (T016)."""

from __future__ import annotations

import hashlib

import pytest
from pydantic import ValidationError

from nmg_game_dev.pipeline.prompt import Prompt

_DESC = "wooden supply crate"
_PROMPT_KWARGS = dict(category="Props", name="TestCrate", tier="standard", description=_DESC)


class TestPromptValidation:
    def test_valid_prompt_constructs(self) -> None:
        p = Prompt(**_PROMPT_KWARGS)  # type: ignore[arg-type]
        assert p.category == "Props"
        assert p.name == "TestCrate"
        assert p.tier == "standard"
        assert p.description == _DESC

    def test_invalid_category_lowercase(self) -> None:
        with pytest.raises(ValidationError):
            Prompt(category="props", name="TestCrate", tier="standard", description="desc")

    def test_invalid_category_spaces(self) -> None:
        with pytest.raises(ValidationError):
            Prompt(category="Props Items", name="TestCrate", tier="standard", description="desc")

    def test_invalid_name_lowercase(self) -> None:
        with pytest.raises(ValidationError):
            Prompt(category="Props", name="testCrate", tier="standard", description="desc")

    def test_invalid_tier(self) -> None:
        with pytest.raises(ValidationError):
            Prompt(
                category="Props",
                name="TestCrate",
                tier="legendary",  # type: ignore[arg-type]
                description="desc",
            )

    def test_description_trimmed(self) -> None:
        p = Prompt(category="Props", name="TestCrate", tier="standard", description="  trimmed  ")
        assert p.description == "trimmed"

    def test_description_blank_after_strip_raises(self) -> None:
        with pytest.raises(ValidationError):
            Prompt(category="Props", name="TestCrate", tier="standard", description="   ")

    def test_description_too_long(self) -> None:
        with pytest.raises(ValidationError):
            Prompt(category="Props", name="TestCrate", tier="standard", description="x" * 513)

    def test_description_max_length(self) -> None:
        p = Prompt(category="Props", name="TestCrate", tier="standard", description="x" * 512)
        assert len(p.description) == 512

    def test_hero_tier(self) -> None:
        p = Prompt(
            category="Guards", name="Patrol", tier="hero", description="futuristic patrol guard"
        )
        assert p.tier == "hero"

    def test_frozen_immutable(self) -> None:
        p = Prompt(category="Props", name="TestCrate", tier="standard", description="desc")
        # Pydantic v2 frozen models raise ValidationError on direct attribute assignment.
        with pytest.raises(ValidationError):
            p.category = "Weapons"  # noqa: PGH003 — pydantic runtime enforcement


class TestStableHash:
    def test_same_prompt_same_hash(self) -> None:
        p1 = Prompt(**_PROMPT_KWARGS)  # type: ignore[arg-type]
        p2 = Prompt(**_PROMPT_KWARGS)  # type: ignore[arg-type]
        assert p1.stable_hash() == p2.stable_hash()

    def test_different_prompt_different_hash(self) -> None:
        p1 = Prompt(**_PROMPT_KWARGS)  # type: ignore[arg-type]
        p2 = Prompt(category="Props", name="TestCrate", tier="hero", description=_DESC)
        assert p1.stable_hash() != p2.stable_hash()

    def test_hash_is_sha256_hex(self) -> None:
        p = Prompt(**_PROMPT_KWARGS)  # type: ignore[arg-type]
        h = p.stable_hash()
        assert len(h) == 64
        int(h, 16)  # must be valid hex

    def test_hash_is_deterministic_across_calls(self) -> None:
        p = Prompt(category="Props", name="TestCrate", tier="standard", description="desc")
        assert p.stable_hash() == p.stable_hash()

    def test_hash_matches_manual_sha256(self) -> None:
        p = Prompt(category="Props", name="TestCrate", tier="standard", description="desc")
        expected = hashlib.sha256(p.model_dump_json().encode()).hexdigest()
        assert p.stable_hash() == expected
