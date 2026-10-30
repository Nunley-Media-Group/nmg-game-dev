from __future__ import annotations


class VariantError(Exception):
    """A variant step that must stop, carrying the code, message, and remediation to report."""

    def __init__(self, code: str, message: str, remediation: str) -> None:
        super().__init__(f"{code}: {message} — {remediation}")
        self.code = code
        self.message = message
        self.remediation = remediation
