"""Vision prompt builder — constructs structured prompts for Claude Vision.

Builds prompts that include the document's style profile, focus areas,
and learned examples to guide Claude's visual formatting analysis.
"""

from __future__ import annotations

from ...models.schemas import Example, PrePolishOptions, StyleProfile


def build_vision_prompt(
    profile: StyleProfile,
    options: PrePolishOptions,
    examples: list[Example] | None = None,
    page_number: int = 1,
    total_pages: int = 1,
) -> str:
    """Build a structured prompt for Claude Vision to analyze a document page.

    Args:
        profile: The document's inferred style profile.
        options: User-selected polish options.
        examples: Optional learned examples for context.
        page_number: Current page number (1-indexed).
        total_pages: Total number of pages.

    Returns:
        The complete prompt string.
    """
    sections = []

    # Context section
    sections.append(_build_context_section(profile, options, page_number, total_pages))

    # Task section
    sections.append(_build_task_section(options))

    # Style profile section
    sections.append(_build_profile_section(profile))

    # Examples section (if available)
    if examples:
        sections.append(_build_examples_section(examples, options.document_type.value))

    # Output format section
    sections.append(_build_output_format_section())

    return "\n\n".join(sections)


def _build_context_section(
    profile: StyleProfile,
    options: PrePolishOptions,
    page_number: int,
    total_pages: int,
) -> str:
    focus_str = ", ".join(fa.value for fa in options.focus_areas) if options.focus_areas else "all areas"
    return (
        f"You are reviewing page {page_number} of {total_pages} of a legal "
        f"{options.document_type.value} document.\n"
        f"Focus areas requested: {focus_str}.\n"
        f"Your task is to identify visual formatting inconsistencies on this page."
    )


def _build_task_section(options: PrePolishOptions) -> str:
    task = (
        "TASK: Carefully examine this page image for formatting inconsistencies.\n\n"
        "Look for:\n"
        "1. **Heading inconsistencies**: Different fonts, sizes, bold/underline patterns "
        "within the same heading level\n"
        "2. **Quote style issues**: Straight quotes (\", ') that should be smart quotes "
        "(\u201C\u201D, \u2018\u2019)\n"
        "3. **List numbering errors**: Duplicate numbers, gaps in sequence, mixed formats\n"
        "4. **Paragraph formatting**: Inconsistent alignment, spacing, or indentation\n"
        "5. **Cross-reference issues**: Section/exhibit references that appear malformed\n"
        "6. **Signature block issues**: Misaligned fields, inconsistent spacing\n"
        "7. **Header/footer issues**: Font changes, inconsistent page numbering\n"
        "8. **Definition formatting**: Inconsistent bold/quoting of defined terms\n"
        "9. **General visual issues**: Any other formatting anomaly that looks unintentional"
    )

    if options.notes:
        task += f"\n\nAdditional instructions from the user: {options.notes}"

    return task


def _build_profile_section(profile: StyleProfile) -> str:
    lines = ["ESTABLISHED STYLE PROFILE (from document analysis):"]

    if profile.heading_styles:
        lines.append("\nHeadings:")
        for level, spec in sorted(profile.heading_styles.items()):
            parts = []
            if spec.bold is not None:
                parts.append(f"bold={spec.bold}")
            if spec.underline is not None:
                parts.append(f"underline={spec.underline}")
            if spec.font_name:
                parts.append(f"font='{spec.font_name}'")
            if spec.font_size_pt:
                parts.append(f"size={spec.font_size_pt}pt")
            if spec.alignment:
                parts.append(f"align={spec.alignment}")
            lines.append(f"  Heading {level}: {', '.join(parts)}")

    if profile.body_font.name or profile.body_font.size_pt:
        parts = []
        if profile.body_font.name:
            parts.append(f"font='{profile.body_font.name}'")
        if profile.body_font.size_pt:
            parts.append(f"size={profile.body_font.size_pt}pt")
        if profile.body_alignment:
            parts.append(f"align={profile.body_alignment}")
        lines.append(f"\nBody text: {', '.join(parts)}")

    return "\n".join(lines)


def _build_examples_section(examples: list[Example], document_type: str) -> str:
    # Filter and cap examples
    relevant = [e for e in examples if not e.document_type or e.document_type == document_type]
    if not relevant:
        relevant = examples
    relevant = relevant[:5]  # Cap at 5 to avoid token bloat

    if not relevant:
        return ""

    lines = ["PREVIOUSLY FOUND ISSUES (for reference):"]
    for i, ex in enumerate(relevant, 1):
        lines.append(f"\n{i}. [{ex.category}] {ex.description}")
        if ex.before_context:
            lines.append(f"   Before: {ex.before_context[:100]}")
        if ex.after_context:
            lines.append(f"   After: {ex.after_context[:100]}")

    return "\n".join(lines)


def _build_output_format_section() -> str:
    return (
        "OUTPUT FORMAT: Return your findings as a JSON array. Each finding should have:\n"
        "```json\n"
        "[\n"
        "  {\n"
        '    "location": "Description of where on the page (e.g., \'3rd paragraph, left side\')",\n'
        '    "category": "heading_style|quote_style|list_labels|paragraph_format|'
        'cross_references|definition_format|signature_block|header_footer|other",\n'
        '    "description": "What the issue is",\n'
        '    "suggested_fix": "How to fix it",\n'
        '    "severity": "minor|moderate|major",\n'
        '    "confidence": 0.0 to 1.0\n'
        "  }\n"
        "]\n"
        "```\n\n"
        "If no issues are found on this page, return an empty array: []\n"
        "Be thorough but avoid false positives. Only report genuine formatting inconsistencies."
    )
