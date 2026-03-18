"""Abstract base class for deterministic formatting rules."""

from __future__ import annotations

from abc import ABC, abstractmethod

from docx import Document

from ....models.schemas import Change, Finding, StyleProfile, Example


class Rule(ABC):
    """Base class for all formatting rules.

    Each rule implements detect() to find issues and fix() to correct them.
    Rules operate on the python-docx Document object and the inferred StyleProfile.
    """

    name: str = ""
    category: str = ""

    @abstractmethod
    def detect(
        self,
        document: Document,
        profile: StyleProfile,
        config: dict,
        examples: list[Example] | None = None,
    ) -> list[Finding]:
        """Scan the document and return all findings for this rule.

        Args:
            document: The python-docx Document object.
            profile: The inferred style profile for the document.
            config: Rule-specific configuration from YAML.
            examples: Optional learned examples to enhance detection.

        Returns:
            List of Finding objects describing detected issues.
        """

    @abstractmethod
    def fix(self, document: Document, finding: Finding, profile: StyleProfile) -> Change:
        """Apply the fix for a single finding.

        Args:
            document: The python-docx Document to modify.
            finding: The specific issue to fix.
            profile: The style profile to conform to.

        Returns:
            A Change record describing what was done.
        """
