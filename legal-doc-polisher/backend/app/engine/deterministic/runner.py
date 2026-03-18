"""Deterministic rules runner — executes all enabled rules on a document."""

from __future__ import annotations

from docx import Document

from ...models.schemas import Change, Example, StyleProfile
from .registry import get_enabled_rules


def run_deterministic_pass(
    document: Document,
    profile: StyleProfile,
    rules_config: dict,
    examples: list[Example] | None = None,
) -> tuple[Document, list[Change]]:
    """Run all enabled deterministic rules on the document.

    Args:
        document: The python-docx Document to process.
        profile: The inferred StyleProfile.
        rules_config: Configuration dict from default_rules.yaml.
        examples: Optional learned examples to enhance detection.

    Returns:
        Tuple of (modified Document, list of Change records).
    """
    all_changes: list[Change] = []
    rules = get_enabled_rules(rules_config)
    rules_section = rules_config.get("rules", rules_config)

    for rule in rules:
        rule_config = rules_section.get(rule.name, {})

        # Detect issues
        findings = rule.detect(document, profile, rule_config, examples)

        # Fix each finding
        for finding in findings:
            try:
                change = rule.fix(document, finding, profile)
                all_changes.append(change)
            except Exception as e:
                # Log but don't halt — other fixes can still proceed
                import logging
                logging.getLogger(__name__).warning(
                    f"Failed to fix {rule.name} finding at {finding.location}: {e}"
                )

    return document, all_changes
