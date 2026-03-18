"""Vision fixer — maps vision findings back to document paragraphs and applies fixes.

The trickiest component: vision findings reference page locations, not paragraph
indices. We use page break analysis + fuzzy text matching to locate the right
paragraphs, then apply fixes using the same mechanisms as deterministic rules.
"""

from __future__ import annotations

import re
import uuid
from difflib import SequenceMatcher

from docx import Document

from ...models.enums import ChangeSource, Severity
from ...models.schemas import Change, StyleProfile, VisionFinding
from ...utils.docx_helpers import (
    find_page_breaks,
    get_full_text,
    set_paragraph_spacing,
    set_run_font_properties,
    str_to_alignment,
)

# Minimum confidence to attempt auto-fix
AUTO_FIX_CONFIDENCE = 0.7

# Minimum text similarity to match a paragraph
TEXT_MATCH_THRESHOLD = 0.6


def apply_vision_fixes(
    document: Document,
    findings: list[VisionFinding],
    profile: StyleProfile,
) -> list[Change]:
    """Apply fixes identified by the vision pipeline.

    Args:
        document: The python-docx Document to modify.
        findings: Vision findings from the analyzer.
        profile: The document's style profile.

    Returns:
        List of Change records (both auto-fixed and flagged for manual review).
    """
    changes: list[Change] = []
    page_breaks = find_page_breaks(document)
    page_ranges = _compute_page_ranges(document, page_breaks)

    for finding in findings:
        try:
            change = _process_finding(document, finding, profile, page_ranges)
            if change:
                changes.append(change)
        except Exception:
            # Create a manual-review change
            changes.append(
                Change(
                    change_id=str(uuid.uuid4()),
                    category=finding.category,
                    location=finding.location,
                    description=f"[Manual review needed] {finding.description}",
                    severity=Severity.MAJOR,
                    source=ChangeSource.VISION,
                )
            )

    return changes


def _compute_page_ranges(
    document: Document, page_breaks: list[int]
) -> dict[int, tuple[int, int]]:
    """Map page numbers to paragraph index ranges.

    Args:
        document: The document.
        page_breaks: List of paragraph indices with page breaks.

    Returns:
        Dict mapping page_number (1-indexed) to (start_idx, end_idx) inclusive.
    """
    total_paras = len(document.paragraphs)
    if not page_breaks:
        # Single page or no detectable breaks — all paragraphs are on page 1
        return {1: (0, total_paras - 1)}

    ranges = {}
    sorted_breaks = sorted(set(page_breaks))

    # Page 1: start to first break
    ranges[1] = (0, sorted_breaks[0] - 1 if sorted_breaks[0] > 0 else 0)

    # Subsequent pages
    for i in range(len(sorted_breaks)):
        page_num = i + 2
        start = sorted_breaks[i]
        end = sorted_breaks[i + 1] - 1 if i + 1 < len(sorted_breaks) else total_paras - 1
        ranges[page_num] = (start, end)

    return ranges


def _process_finding(
    document: Document,
    finding: VisionFinding,
    profile: StyleProfile,
    page_ranges: dict[int, tuple[int, int]],
) -> Change | None:
    """Process a single vision finding."""
    # Determine if we can auto-fix or just flag
    if finding.confidence < AUTO_FIX_CONFIDENCE:
        return Change(
            change_id=str(uuid.uuid4()),
            category=finding.category,
            location=finding.location,
            description=f"[Manual review needed] {finding.description}. Suggested fix: {finding.suggested_fix}",
            severity=finding.severity,
            source=ChangeSource.VISION,
        )

    # Try to locate the paragraph
    para_idx = _locate_paragraph(document, finding, page_ranges)

    if para_idx is not None:
        # Attempt auto-fix based on category
        fixed = _apply_category_fix(document, para_idx, finding, profile)
        status = "Auto-fixed" if fixed else "Manual review needed"
    else:
        status = "Manual review needed — could not locate paragraph"

    return Change(
        change_id=str(uuid.uuid4()),
        category=finding.category,
        location=finding.location,
        description=f"[{status}] {finding.description}",
        severity=finding.severity,
        source=ChangeSource.VISION,
    )


def _locate_paragraph(
    document: Document,
    finding: VisionFinding,
    page_ranges: dict[int, tuple[int, int]],
) -> int | None:
    """Try to locate the paragraph that a vision finding refers to."""
    page = finding.page_number
    if page not in page_ranges:
        return None

    start, end = page_ranges[page]
    location_text = finding.location + " " + finding.description

    # Extract any quoted text from the finding
    quoted_texts = re.findall(r'["\u201C](.+?)["\u201D]', location_text)

    best_idx = None
    best_score = 0.0

    for idx in range(start, min(end + 1, len(document.paragraphs))):
        para_text = get_full_text(document.paragraphs[idx]).strip()
        if not para_text:
            continue

        # Check quoted text matches
        for qt in quoted_texts:
            ratio = SequenceMatcher(None, qt.lower(), para_text.lower()).ratio()
            if ratio > best_score and ratio >= TEXT_MATCH_THRESHOLD:
                best_score = ratio
                best_idx = idx

        # Also check if the paragraph text contains key terms from the description
        words = set(location_text.lower().split())
        para_words = set(para_text.lower().split())
        overlap = len(words & para_words)
        if overlap > 3:
            score = overlap / max(len(words), 1)
            if score > best_score and score >= 0.3:
                best_score = score
                best_idx = idx

    return best_idx


def _apply_category_fix(
    document: Document,
    para_idx: int,
    finding: VisionFinding,
    profile: StyleProfile,
) -> bool:
    """Apply a category-specific fix. Returns True if fixed, False otherwise."""
    para = document.paragraphs[para_idx]
    category = finding.category

    if category == "heading_style":
        level_match = re.search(r"[Hh]eading\s+(\d+)", finding.description)
        if level_match:
            level = int(level_match.group(1))
            if level in profile.heading_styles:
                spec = profile.heading_styles[level]
                for run in para.runs:
                    set_run_font_properties(
                        run,
                        bold=spec.bold,
                        underline=spec.underline,
                        font_name=spec.font_name,
                        font_size=spec.font_size_pt,
                    )
                return True

    elif category == "paragraph_format":
        if profile.body_alignment:
            alignment = str_to_alignment(profile.body_alignment)
            if alignment is not None:
                para.paragraph_format.alignment = alignment
                return True

    elif category == "quote_style":
        # Apply smart quote conversion
        for run in para.runs:
            text = run.text
            text = text.replace('"', '\u201C').replace('"', '\u201D')
            # Simple replacement — more sophisticated logic in deterministic rule
            run.text = text
        return True

    return False
