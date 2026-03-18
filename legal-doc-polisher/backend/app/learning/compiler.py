"""Learning compiler — compiles examples into rule hints and vision prompts."""

from __future__ import annotations

from collections import defaultdict

from ..models.schemas import Example


def compile_for_deterministic(examples: list[Example]) -> dict[str, list[dict]]:
    """Group examples by category and extract detection hints for rules.

    Returns:
        Dict mapping category -> list of hint dicts.
    """
    hints: dict[str, list[dict]] = defaultdict(list)

    for ex in examples:
        hint = {
            "description": ex.description,
            "before": ex.before_context,
            "after": ex.after_context,
        }
        hints[ex.category].append(hint)

    return dict(hints)


def compile_for_vision(
    examples: list[Example],
    document_type: str = "",
) -> list[dict]:
    """Select and format the most relevant examples for vision prompts.

    Args:
        examples: All available examples.
        document_type: Current document type for relevance filtering.

    Returns:
        List of formatted example dicts, capped at 5.
    """
    # Prefer examples matching the document type
    relevant = [e for e in examples if e.document_type == document_type]
    if len(relevant) < 5:
        # Fill with general examples
        general = [e for e in examples if e not in relevant]
        relevant.extend(general[: 5 - len(relevant)])

    return [
        {
            "category": ex.category,
            "description": ex.description,
            "before_context": ex.before_context[:150],
            "after_context": ex.after_context[:150],
        }
        for ex in relevant[:5]
    ]
