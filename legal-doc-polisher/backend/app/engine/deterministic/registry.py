"""Rule registry — auto-discovers and loads all Rule subclasses."""

from __future__ import annotations

from .rules.base import Rule
from .rules.heading_style import HeadingStyleRule
from .rules.quote_style import QuoteStyleRule
from .rules.list_labels import ListLabelsRule
from .rules.paragraph_format import ParagraphFormatRule
from .rules.cross_references import CrossReferencesRule
from .rules.definition_format import DefinitionFormatRule
from .rules.signature_block import SignatureBlockRule
from .rules.header_footer import HeaderFooterRule


# All available rules (base + CRE-specific)
_ALL_RULES: list[type[Rule]] = [
    HeadingStyleRule,
    QuoteStyleRule,
    ListLabelsRule,
    ParagraphFormatRule,
    CrossReferencesRule,
    DefinitionFormatRule,
    SignatureBlockRule,
    HeaderFooterRule,
]


def get_enabled_rules(config: dict) -> list[Rule]:
    """Return instantiated Rule objects filtered by the config's enabled flags.

    Args:
        config: The rules section of the YAML configuration, e.g.:
                {"heading_style": {"enabled": true, ...}, ...}

    Returns:
        List of enabled Rule instances.
    """
    enabled = []
    rules_config = config.get("rules", config)

    for rule_cls in _ALL_RULES:
        rule_name = rule_cls.name
        rule_config = rules_config.get(rule_name, {})
        if rule_config.get("enabled", True):
            enabled.append(rule_cls())

    return enabled


def register_rule(rule_cls: type[Rule]) -> None:
    """Register an additional rule class (e.g., CRE-specific rules)."""
    if rule_cls not in _ALL_RULES:
        _ALL_RULES.append(rule_cls)
