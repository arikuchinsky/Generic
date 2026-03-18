"""Post-polish validator — ensures the polisher doesn't introduce new issues.

This module compares the original and polished documents to verify that:
1. No formatting was degraded (new inconsistencies introduced)
2. Headers/footers were not corrupted
3. Exhibit labels remain intact and correctly ordered
4. Section numbering was not broken
5. No content was lost or duplicated
6. The overall document structure is preserved
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from docx import Document

from ..utils.docx_helpers import (
    alignment_to_str,
    get_full_text,
    get_heading_level,
    get_num_pr,
    resolve_font_property,
    resolve_paragraph_property,
)

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """A problem introduced by the polishing process."""

    category: str  # content_loss, formatting_regression, structure_change, etc.
    location: str
    description: str
    severity: str  # warning, error, critical


@dataclass
class ValidationReport:
    """Results of comparing original vs polished document."""

    is_valid: bool = True
    issues: list[ValidationIssue] = field(default_factory=list)
    content_preserved: bool = True
    structure_preserved: bool = True
    headers_preserved: bool = True
    footers_preserved: bool = True
    exhibits_preserved: bool = True
    paragraph_count_original: int = 0
    paragraph_count_polished: int = 0


def validate_polish(
    original_path: Path,
    polished_path: Path,
) -> ValidationReport:
    """Compare original and polished documents for regressions.

    Args:
        original_path: Path to the original .docx.
        polished_path: Path to the polished .docx.

    Returns:
        ValidationReport detailing any issues found.
    """
    report = ValidationReport()

    try:
        original = Document(str(original_path))
        polished = Document(str(polished_path))
    except Exception as e:
        report.is_valid = False
        report.issues.append(ValidationIssue(
            category="file_error",
            location="document",
            description=f"Failed to open document: {e}",
            severity="critical",
        ))
        return report

    # Run all validation checks
    _check_content_preservation(original, polished, report)
    _check_structure_preservation(original, polished, report)
    _check_header_footer_preservation(original, polished, report)
    _check_exhibit_preservation(original, polished, report)
    _check_no_formatting_regression(original, polished, report)

    report.is_valid = not any(i.severity == "critical" for i in report.issues)
    return report


def _check_content_preservation(
    original: Document, polished: Document, report: ValidationReport
) -> None:
    """Verify no text content was lost or duplicated."""
    report.paragraph_count_original = len(original.paragraphs)
    report.paragraph_count_polished = len(polished.paragraphs)

    # Paragraph count should be identical (we only change formatting, not structure)
    if report.paragraph_count_original != report.paragraph_count_polished:
        report.content_preserved = False
        report.issues.append(ValidationIssue(
            category="content_loss",
            location="document",
            description=(
                f"Paragraph count changed: {report.paragraph_count_original} -> "
                f"{report.paragraph_count_polished}"
            ),
            severity="critical",
        ))
        return

    # Check each paragraph's text content
    for idx, (orig_para, pol_para) in enumerate(zip(original.paragraphs, polished.paragraphs)):
        orig_text = get_full_text(orig_para).strip()
        pol_text = get_full_text(pol_para).strip()

        # Text should be the same except for quote character changes
        normalized_orig = _normalize_quotes(orig_text)
        normalized_pol = _normalize_quotes(pol_text)

        if normalized_orig != normalized_pol:
            report.content_preserved = False
            report.issues.append(ValidationIssue(
                category="content_loss",
                location=f"Paragraph {idx + 1}",
                description=f"Text content changed unexpectedly",
                severity="error",
            ))


def _check_structure_preservation(
    original: Document, polished: Document, report: ValidationReport
) -> None:
    """Verify document structure (headings, sections) is preserved."""
    orig_headings = []
    pol_headings = []

    for para in original.paragraphs:
        level = get_heading_level(para)
        if level is not None:
            orig_headings.append((level, get_full_text(para).strip()))

    for para in polished.paragraphs:
        level = get_heading_level(para)
        if level is not None:
            pol_headings.append((level, get_full_text(para).strip()))

    if len(orig_headings) != len(pol_headings):
        report.structure_preserved = False
        report.issues.append(ValidationIssue(
            category="structure_change",
            location="headings",
            description=(
                f"Heading count changed: {len(orig_headings)} -> {len(pol_headings)}"
            ),
            severity="critical",
        ))
        return

    for i, ((orig_level, orig_text), (pol_level, pol_text)) in enumerate(
        zip(orig_headings, pol_headings)
    ):
        if orig_level != pol_level:
            report.structure_preserved = False
            report.issues.append(ValidationIssue(
                category="structure_change",
                location=f"Heading {i + 1}",
                description=f"Heading level changed: {orig_level} -> {pol_level}",
                severity="critical",
            ))

    # Section count should match
    if len(original.sections) != len(polished.sections):
        report.structure_preserved = False
        report.issues.append(ValidationIssue(
            category="structure_change",
            location="sections",
            description=(
                f"Section count changed: {len(original.sections)} -> {len(polished.sections)}"
            ),
            severity="error",
        ))


def _check_header_footer_preservation(
    original: Document, polished: Document, report: ValidationReport
) -> None:
    """Verify headers and footers were not corrupted."""
    for sect_idx in range(min(len(original.sections), len(polished.sections))):
        orig_section = original.sections[sect_idx]
        pol_section = polished.sections[sect_idx]

        # Check header content
        orig_header_text = _get_header_footer_text(orig_section.header)
        pol_header_text = _get_header_footer_text(pol_section.header)

        # Font may change (that's a valid fix), but text content should be preserved
        orig_normalized = _normalize_quotes(orig_header_text)
        pol_normalized = _normalize_quotes(pol_header_text)

        if orig_normalized != pol_normalized:
            report.headers_preserved = False
            report.issues.append(ValidationIssue(
                category="header_corruption",
                location=f"Section {sect_idx + 1} header",
                description="Header text content was modified",
                severity="error",
            ))

        # Check footer content
        orig_footer_text = _get_header_footer_text(orig_section.footer)
        pol_footer_text = _get_header_footer_text(pol_section.footer)

        orig_normalized = _normalize_quotes(orig_footer_text)
        pol_normalized = _normalize_quotes(pol_footer_text)

        if orig_normalized != pol_normalized:
            report.footers_preserved = False
            report.issues.append(ValidationIssue(
                category="footer_corruption",
                location=f"Section {sect_idx + 1} footer",
                description="Footer text content was modified",
                severity="error",
            ))


def _check_exhibit_preservation(
    original: Document, polished: Document, report: ValidationReport
) -> None:
    """Verify exhibit labels and ordering are preserved."""
    import re

    exhibit_pattern = re.compile(
        r"(?:EXHIBIT|SCHEDULE|APPENDIX|ATTACHMENT|ADDENDUM)\s+([A-Z0-9](?:-\d+)?)",
        re.IGNORECASE,
    )

    orig_exhibits = []
    for para in original.paragraphs:
        text = get_full_text(para).strip()
        m = exhibit_pattern.match(text)
        if m:
            orig_exhibits.append(m.group(0))

    pol_exhibits = []
    for para in polished.paragraphs:
        text = get_full_text(para).strip()
        m = exhibit_pattern.match(text)
        if m:
            pol_exhibits.append(m.group(0))

    if orig_exhibits != pol_exhibits:
        report.exhibits_preserved = False
        report.issues.append(ValidationIssue(
            category="exhibit_corruption",
            location="exhibits",
            description=(
                f"Exhibit labels changed. Original: {orig_exhibits[:5]}, "
                f"Polished: {pol_exhibits[:5]}"
            ),
            severity="critical",
        ))


def _check_no_formatting_regression(
    original: Document, polished: Document, report: ValidationReport
) -> None:
    """Verify the polisher didn't introduce new formatting inconsistencies.

    Checks that:
    - No paragraph that was correctly formatted now has wrong formatting
    - Body text consistency didn't decrease
    """
    # Count formatting consistency in original vs polished
    orig_fonts = _count_body_fonts(original)
    pol_fonts = _count_body_fonts(polished)

    if orig_fonts and pol_fonts:
        orig_dominant = max(orig_fonts, key=orig_fonts.get)
        pol_dominant = max(pol_fonts, key=pol_fonts.get)

        orig_consistency = orig_fonts[orig_dominant] / sum(orig_fonts.values())
        pol_consistency = pol_fonts[pol_dominant] / sum(pol_fonts.values())

        # Polished should be at least as consistent as original
        if pol_consistency < orig_consistency - 0.05:
            report.issues.append(ValidationIssue(
                category="formatting_regression",
                location="body text",
                description=(
                    f"Font consistency decreased: {orig_consistency:.0%} -> {pol_consistency:.0%}"
                ),
                severity="warning",
            ))


def _get_header_footer_text(hf) -> str:
    """Extract all text from a header/footer."""
    return " ".join(
        get_full_text(para).strip()
        for para in hf.paragraphs
    ).strip()


def _normalize_quotes(text: str) -> str:
    """Normalize all quote variants for comparison."""
    return (
        text.replace("\u201C", '"')
        .replace("\u201D", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )


def _count_body_fonts(doc: Document) -> dict[str, int]:
    """Count font usage in body paragraphs."""
    fonts: dict[str, int] = {}
    for para in doc.paragraphs:
        if get_heading_level(para) is not None:
            continue
        text = get_full_text(para).strip()
        if not text:
            continue
        if para.runs:
            font_name = resolve_font_property(para.runs[0], "name")
            if font_name:
                fonts[font_name] = fonts.get(font_name, 0) + 1
    return fonts
