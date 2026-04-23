"""Typed prompt model for the NMG asset generation pipeline.

Every public function that drives the pipeline starts with a validated Prompt.
Validation happens at construction — invalid inputs raise pydantic.ValidationError
before any MCP call is made.
"""

from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Tier = Literal["standard", "hero"]


class Prompt(BaseModel):
    """Immutable, validated description of an asset generation request.

    The ``stable_hash`` method produces a deterministic SHA-256 hex digest
    that is stable across Python processes, making it safe to use as a
    content-addressed cache key component.
    """

    model_config = {"frozen": True}

    category: str = Field(pattern=r"^[A-Z][A-Za-z0-9]*$")
    name: str = Field(pattern=r"^[A-Z][A-Za-z0-9]*$")
    tier: Tier
    description: str = Field(min_length=1, max_length=512)

    @field_validator("description")
    @classmethod
    def _trim(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("description must not be blank after stripping whitespace")
        return stripped

    def stable_hash(self) -> str:
        """Return SHA-256 hex digest over the canonical JSON projection.

        Uses pydantic v2's ``model_dump_json()`` which serialises fields in
        declaration order — stable across processes.  Do NOT pass sort_keys;
        pydantic v2 does not accept that kwarg.
        """
        payload = self.model_dump_json().encode()
        return hashlib.sha256(payload).hexdigest()
